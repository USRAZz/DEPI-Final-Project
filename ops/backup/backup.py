"""Back up the SecureFin database (owner: M4 Ziad).

    python ops/backup/backup.py --url "$BACKUP_DATABASE_URL" --out-dir backups --keep 14

Writes  backups/securefin-<UTC time>.dump      pg_dump custom format (schema, data, grants, policies)
        backups/securefin-<UTC time>.json      manifest: alembic revision, row count per table, sha256 of the dump
and deletes the oldest pairs beyond --keep.

The login MUST bypass row-level security (a superuser, or a role WITH BYPASSRLS). approvals and audit_log force
RLS even for their owner: pg_dump as the owner fails on them, and with --enable-row-security it would silently
leave their rows out. This script checks the login first and refuses instead of writing an incomplete backup.

Needs pg_dump >= the server's major version on PATH (or PG_BIN=folder with pg_dump).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pgutil  # noqa: E402
import psycopg  # noqa: E402


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def prune(out_dir: pathlib.Path, keep: int) -> list[str]:
    dumps = sorted(out_dir.glob("securefin-*.dump"))
    removed = []
    for old in dumps[:-keep] if keep > 0 else []:
        for p in (old, old.with_suffix(".json")):
            if p.exists():
                p.unlink()
                removed.append(p.name)
    return removed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("BACKUP_DATABASE_URL") or os.environ.get("DATABASE_URL"))
    ap.add_argument("--out-dir", default="backups")
    ap.add_argument("--keep", type=int, default=int(os.environ.get("BACKUP_KEEP", "14")))
    args = ap.parse_args(argv)
    if not args.url:
        print("set --url or BACKUP_DATABASE_URL", file=sys.stderr)
        return 2

    url = pgutil.libpq_url(args.url)
    problem = pgutil.check_backup_login(url)
    if problem:
        print(f"refusing to back up: {problem}", file=sys.stderr)
        return 3

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump = out_dir / f"securefin-{stamp}.dump"
    tmp = dump.with_suffix(".partial")
    bare_url, env = pgutil.split_password(url)  # password via PGPASSWORD, never on the command line

    # Count and dump from ONE snapshot: the gateway keeps appending audit rows, and counts taken a moment
    # before pg_dump would not match the dump (restore_check would then fail a good backup).
    with psycopg.connect(url, autocommit=True) as c:  # autocommit: our BEGIN sets the isolation level
        c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_id = c.execute("SELECT pg_export_snapshot()").fetchone()[0]
        manifest = pgutil.snapshot(conn=c)
        result = subprocess.run([pgutil.tool("pg_dump"), "--format=custom", "--no-password", f"--snapshot={snapshot_id}",
                                 f"--file={tmp}", f"--dbname={bare_url}"], capture_output=True, text=True, env=env)
        c.execute("ROLLBACK")
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    manifest.update({"file": dump.name, "bytes": tmp.stat().st_size, "sha256": sha256(tmp),
                     "created_at": datetime.now(UTC).isoformat(timespec="seconds")})
    # manifest first, then the dump: restore_check only looks at dumps that have one
    dump.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.move(tmp, dump)
    removed = prune(out_dir, args.keep)
    print(f"backup written: {dump} ({manifest['bytes']} bytes, {sum(manifest['rows'].values())} rows, "
          f"revision {manifest['alembic_revision']})")
    if removed:
        print("removed old: " + ", ".join(removed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
