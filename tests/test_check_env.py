"""ops/deploy/check_env.py: a deploy is refused with a demo .env and allowed with a proper one."""
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops" / "deploy"))
import check_env  # noqa: E402

GOOD = {
    "REGISTRY": "ghcr.io/usrazz", "IMAGE_TAG": "v0.2.0", "OPENAI_API_KEY": "sk-x",
    "GATEWAY_URL": "http://gateway:8000", "RISK_URL": "http://risk:8000", "API_URL": "http://api:8000",
    "APPROVAL_HMAC_KEY": "a" * 64, "INTERNAL_SERVICE_TOKEN": "b" * 64, "AUDIT_VERIFY_TOKEN": "c" * 64,
    "POSTGRES_PASSWORD": "d" * 24, "N8N_ENCRYPTION_KEY": "e" * 64,
    "DATABASE_URL": "postgresql+psycopg://app:" + "f" * 24 + "@ep-x.eu-central-1.aws.neon.tech/securefin",
    "BACKUP_DATABASE_URL": "postgresql://securefin_backup:" + "g" * 24 + "@ep-x.eu-central-1.aws.neon.tech/securefin",
    "GATEWAY_ENABLED": "true", "BACKEND": "api",
}


@pytest.mark.parametrize("stage", ["staging", "production"])
def test_good_env_passes(stage):
    assert check_env.problems(stage, GOOD) == []


@pytest.mark.parametrize("change,expected", [
    ({"APPROVAL_HMAC_KEY": "change-me"}, "APPROVAL_HMAC_KEY is empty or a placeholder"),
    ({"INTERNAL_SERVICE_TOKEN": "short"}, "INTERNAL_SERVICE_TOKEN is shorter than 32"),
    ({"GATEWAY_ENABLED": "false"}, "GATEWAY_ENABLED must be true"),
    ({"BACKEND": "mock"}, "BACKEND must be api"),
    ({"DEV_LOGIN": "1"}, "DEV_LOGIN=1 is not allowed"),
    ({"DATABASE_URL": "postgresql+psycopg://securefin:change-me@db.example/securefin"}, "default password"),
    ({"DATABASE_URL": "postgresql+psycopg://securefin:" + "x" * 20 + "@postgres:5432/securefin"}, "compose postgres"),
    ({"IMAGE_TAG": "latest"}, "release tag"),
    ({"AUDIT_VERIFY_TOKEN": "a" * 64}, "reuse a value"),
    ({"BACKUP_DATABASE_URL": ""}, "BACKUP_DATABASE_URL is empty"),
])
def test_production_refuses(change, expected):
    found = check_env.problems("production", {**GOOD, **change})
    assert any(expected in p for p in found), found


def test_staging_allows_compose_postgres_and_staging_tag():
    env = {**GOOD, "IMAGE_TAG": "staging", "BACKUP_DATABASE_URL": "", "N8N_ENCRYPTION_KEY": "",
           "DATABASE_URL": "postgresql+psycopg://securefin:" + "x" * 20 + "@postgres:5432/securefin"}
    assert check_env.problems("staging", env) == []


def test_cli_never_prints_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# demo\nAPPROVAL_HMAC_KEY=supersecretvalue  # too short\nexport DEV_LOGIN=1\n")
    r = subprocess.run([sys.executable, str(REPO / "ops" / "deploy" / "check_env.py"), "production", str(env)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "supersecretvalue" not in r.stdout + r.stderr
    assert "DEV_LOGIN=1 is not allowed" in r.stdout and "APPROVAL_HMAC_KEY is shorter" in r.stdout


def test_example_template_is_refused_until_filled():
    env = check_env.parse(REPO / "ops" / "deploy" / "deploy.env.example")
    assert check_env.problems("staging", env)  # empty secrets must not pass
