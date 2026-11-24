"""Refuse to deploy with an unsafe .env (owner: M4 Ziad). Standard library only.

    python ops/deploy/check_env.py staging .env
    python ops/deploy/check_env.py production .env

Prints every problem (names only, never values) and exits 1 if there is any. ops/deploy/deploy.sh runs it first.
The rules are the ones a demo .env breaks: placeholder or short secrets, the gateway switched off, the mock
backend, the development login left on, a database password still at its default.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

PLACEHOLDERS = {"", "change-me", "changeme", "secret", "password", "test", "securefin"}

# name -> minimum length; every one must be set and not a placeholder
SECRETS = {
    "APPROVAL_HMAC_KEY": 32,      # gateway: signs approvals (services/gateway/app/approvals.py)
    "INTERNAL_SERVICE_TOKEN": 32,  # risk -> api service calls
    "AUDIT_VERIFY_TOKEN": 32,     # n8n -> gateway /v1/audit/verify
    "POSTGRES_PASSWORD": 16,
}
REQUIRED = ("DATABASE_URL", "REGISTRY", "IMAGE_TAG", "OPENAI_API_KEY", "GATEWAY_URL", "RISK_URL", "API_URL")
# name -> value it must have
FIXED = {"GATEWAY_ENABLED": "true", "BACKEND": "api"}
FORBIDDEN = {"DEV_LOGIN": "1"}  # name -> value it must not have
PRODUCTION_ONLY_SECRETS = {"N8N_ENCRYPTION_KEY": 32, "BACKUP_DATABASE_URL": 1}


def parse(path: Path) -> dict[str, str]:
    """KEY=VALUE lines like docker compose reads them; '# ...' after a space is a comment."""
    env = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        env[key.strip().removeprefix("export ").strip()] = value
    return env


def problems(stage: str, env: dict[str, str]) -> list[str]:
    found = []
    secrets = dict(SECRETS, **(PRODUCTION_ONLY_SECRETS if stage == "production" else {}))
    for name, minimum in secrets.items():
        value = env.get(name, "")
        if value.lower() in PLACEHOLDERS:
            found.append(f"{name} is empty or a placeholder")
        elif len(value) < minimum:
            found.append(f"{name} is shorter than {minimum} characters (openssl rand -hex 32)")
    for name in REQUIRED:
        if not env.get(name):
            found.append(f"{name} is not set")
    for name, value in FIXED.items():
        if env.get(name, "").lower() != value:
            found.append(f"{name} must be {value}")
    for name, value in FORBIDDEN.items():
        if env.get(name) == value:
            found.append(f"{name}={value} is not allowed outside local development (anyone could sign in as anyone)")

    url = env.get("DATABASE_URL", "")
    if url:
        parts = urlsplit(url)
        if (parts.password or "").lower() in PLACEHOLDERS:
            found.append("DATABASE_URL has an empty or default password")
        if stage == "production" and parts.hostname in ("postgres", "localhost", "127.0.0.1"):
            found.append("production DATABASE_URL points at the compose postgres: use the managed database (Neon)")
    if stage == "production" and not re.fullmatch(r"v\d+\.\d+\.\d+", env.get("IMAGE_TAG", "")):
        found.append("production IMAGE_TAG must be a release tag such as v0.2.0 (not latest, staging or sha-...)")
    shared = [n for n in ("APPROVAL_HMAC_KEY", "INTERNAL_SERVICE_TOKEN", "AUDIT_VERIFY_TOKEN")
              if env.get(n) and list(env.values()).count(env[n]) > 1]
    if shared:
        found.append("these secrets reuse a value set elsewhere in the file: " + ", ".join(shared))
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("staging", "production"):
        print("usage: check_env.py staging|production PATH_TO_ENV", file=sys.stderr)
        return 2
    stage, path = argv[0], Path(argv[1])
    if not path.is_file():
        print(f"{path}: not found", file=sys.stderr)
        return 2
    env = parse(path)
    if os.environ.get("IMAGE_TAG"):  # deploy.sh pins the tag for one run
        env["IMAGE_TAG"] = os.environ["IMAGE_TAG"]
    found = problems(stage, env)
    for p in found:
        print(f"REFUSED  {p}")
    print(f"{stage} env check: {'OK' if not found else f'{len(found)} problem(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
