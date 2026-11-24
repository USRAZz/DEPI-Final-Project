"""Backup and restore drill against a real PostgreSQL (owner: M4 Ziad).

Skipped unless TEST_DATABASE_URL (a superuser on a throwaway server) is set and pg_dump/pg_restore/psql are on
PATH. Builds a database owned by a non-superuser (as on Neon), migrates and seeds it, writes hash-chained audit
rows through the gateway's own code, then proves: the owner login is refused, the backup login works, the dump
restores with every row, the chains verify and the append-only trigger is back, and a damaged dump is caught.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops" / "backup"))
URL = os.environ.get("TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(
    not URL or not all(shutil.which(t) for t in ("pg_dump", "pg_restore", "psql")),
    reason="set TEST_DATABASE_URL and install the PostgreSQL client tools")

DB, OWNER, BACKUP_PW = "securefin_backup_test", "sf_bk_owner", "backup-test-pw"


def _package(name: str, folder: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, folder / "__init__.py", submodule_search_locations=[str(folder)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[name] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "ops" / "backup" / script), *args],
                          capture_output=True, text=True, env={**os.environ, "DATABASE_URL": ""})


@pytest.fixture(scope="module")
def urls():
    import pgutil
    import psycopg
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    admin = pgutil.libpq_url(URL)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        c.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{OWNER}') THEN "
                  f"CREATE ROLE {OWNER} LOGIN CREATEROLE PASSWORD 'owner'; END IF; END $$")
        c.execute(f"CREATE DATABASE {DB} OWNER {OWNER}")
    subprocess.run(["psql", admin, "-v", "ON_ERROR_STOP=1", "-v", f"pw='{BACKUP_PW}'",
                    "-f", str(REPO / "ops" / "backup" / "create_backup_role.sql")], check=True, capture_output=True)

    base = make_url(URL).set(drivername="postgresql+psycopg", database=DB)
    owner_url = base.set(username=OWNER, password="owner").render_as_string(hide_password=False)
    from alembic import command
    from alembic.config import Config
    os.environ["DATABASE_URL"] = owner_url
    try:
        cfg = Config(str(REPO / "services" / "api" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO / "services" / "api" / "migrations"))
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("DATABASE_URL", None)
    with psycopg.connect(admin, autocommit=True) as c:  # the roles may predate this owner (cluster-wide)
        c.execute(f"GRANT securefin_app, securefin_gateway TO {OWNER}")

    from securefin_contracts import AuditEvent
    engine = create_engine(owner_url)
    api = REPO / "services" / "api" / "app"
    _package("securefin_api", api)
    store = importlib.import_module("securefin_api.store")
    importlib.import_module("securefin_api.sql_store").SqlStore(engine).load(store.seeded_store())
    _package("securefin_gateway", REPO / "services" / "gateway" / "app")
    log = importlib.import_module("securefin_gateway.audit_log").PostgresAuditLog(engine)
    for company, action in ((1, "approval"), (1, "execute_check"), (2, "approval"), (1, "approval")):
        log.append(AuditEvent(company_id=company, user_id=None, action=action, decision="ALLOW",
                              source_service="gateway", parameters={"payment_request_id": 1}))
    engine.dispose()
    yield {"admin": admin, "owner": pgutil.libpq_url(owner_url),
           "backup": pgutil.libpq_url(base.set(username="securefin_backup", password=BACKUP_PW)
                                      .render_as_string(hide_password=False))}
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")


@needs_pg
def test_owner_login_is_refused(urls, tmp_path):
    r = _run("backup.py", "--url", urls["owner"], "--out-dir", str(tmp_path))
    assert r.returncode == 3, r.stderr
    assert "row-level security" in r.stderr
    assert not list(tmp_path.glob("*.dump"))


@needs_pg
def test_backup_then_restore_is_proven(urls, tmp_path):
    r = _run("backup.py", "--url", urls["backup"], "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    manifest = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert manifest["rows"]["audit_log"] == 4 and manifest["rows"]["approvals"] == 0
    assert manifest["rows"]["payment_requests"] > 0 and manifest["policies"] > 0

    r = _run("restore_check.py", "--url", urls["admin"], "--backup-dir", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "restore proven" in r.stdout


@needs_pg
def test_damaged_dump_is_caught(urls, tmp_path):
    assert _run("backup.py", "--url", urls["backup"], "--out-dir", str(tmp_path)).returncode == 0
    dump = next(tmp_path.glob("*.dump"))
    dump.write_bytes(dump.read_bytes()[:-10] + b"0123456789")
    r = _run("restore_check.py", "--url", urls["admin"], "--backup-dir", str(tmp_path))
    assert r.returncode == 4, r.stderr


def test_retention_keeps_newest(tmp_path):
    import backup
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (tmp_path / f"securefin-{stamp}.dump").write_bytes(b"x")
        (tmp_path / f"securefin-{stamp}.json").write_text("{}")
    removed = backup.prune(tmp_path, keep=2)
    assert removed == ["securefin-20260101T000000Z.dump", "securefin-20260101T000000Z.json"]
    assert len(list(tmp_path.iterdir())) == 4


@needs_pg
def test_missing_rows_fail_the_check(urls, tmp_path):
    assert _run("backup.py", "--url", urls["backup"], "--out-dir", str(tmp_path)).returncode == 0
    manifest_file = next(tmp_path.glob("*.json"))
    manifest = json.loads(manifest_file.read_text())
    manifest["rows"]["audit_log"] += 1  # the backup claims a row the dump does not hold
    manifest_file.write_text(json.dumps(manifest))
    r = _run("restore_check.py", "--url", urls["admin"], "--backup-dir", str(tmp_path))
    assert r.returncode == 1 and "audit_log: 4 rows, backup had 5" in r.stderr, r.stderr
