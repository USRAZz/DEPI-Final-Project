# Environments: local, staging, production (owner: M4 Ziad)

| | Local | Staging | Production |
|---|---|---|---|
| What runs | `docker compose up` on your machine, built from your checkout | images of the newest `dev` | images of one release tag |
| Images | built locally | `ghcr.io/usrazz/securefin-<service>:staging` (also `:sha-<7>`) | `ghcr.io/usrazz/securefin-<service>:vX.Y.Z` |
| Built by | you | `.github/workflows/images.yml` on every push to `dev` | the same workflow when a `vX.Y.Z` tag is pushed |
| Database | compose `postgres` | compose `postgres` or a Neon branch | Neon (direct host), never the compose container |
| Sign-in | `X-User-Id` dev login on | dev login **off** | dev login **off** |
| Ports | every service on 8000-8004 | only api, on `127.0.0.1:8000` behind a TLS proxy | same as staging |
| Backups | none | optional | `ops/compose.yaml` backup container + monthly drill (`ops/README.md`) |
| Who deploys | everyone | Ziad (or Karim), any time | Karim as release owner, after the release checklist |

Release flow (team plan, section 7): PRs go into `dev` → images `:staging` → deploy staging → test there →
merge `dev` into `main` → tag `vX.Y.Z` on `main` → images `:vX.Y.Z` → deploy production with that tag.

## Files

| File | Job |
|---|---|
| `compose.deploy.yaml` | override on top of `docker-compose.yml`: GHCR images, restart policy, log size caps, ports closed, dev login off, no dev-server frontend |
| `deploy.env.example` | the `.env` lines a server needs on top of `.env.example` |
| `check_env.py` | refuses placeholder/short/reused secrets, `GATEWAY_ENABLED=false`, `BACKEND=mock`, `DEV_LOGIN=1`, a default DB password; in production also the compose DB and a non-release tag |
| `deploy.sh` | check `.env` → pull → `alembic upgrade head` → start → wait for `/health` |
| `../../.github/workflows/images.yml` | builds and pushes the five service images |

## First deploy of a server (staging or production)

Any Linux host with Docker Compose v2.24+ (the override uses `!reset`/`!override`).

```bash
git clone https://github.com/USRAZz/DEPI-Final-Project.git securefin && cd securefin
git checkout dev                     # production: git checkout vX.Y.Z (compose files match the images)
cp .env.example .env                 # then edit .env with the lines from ops/deploy/deploy.env.example
python3 ops/deploy/check_env.py staging .env
echo "$GHCR_READ_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin   # only if the packages are private
ops/deploy/deploy.sh staging
```

Put a reverse proxy with TLS (Caddy or nginx) in front of `127.0.0.1:8000`. The built frontend is served
separately (Karim: Vercel static site or the same proxy); the compose `frontend` service is the dev server and
is not started here.

## Every later deploy

```bash
git pull                              # compose files and scripts
ops/deploy/deploy.sh staging             # newest :staging
ops/deploy/deploy.sh production v0.2.0   # production always names its tag
```

`deploy.sh` stops at the first failed step, so a failed migration never starts new code on an old schema.

## Rollback

`ops/deploy/deploy.sh production <previous tag>`. Migrations are not reversed automatically. Rule for every
migration: a release only adds (expand now, remove in a later release), so the previous version still runs on
the newer schema. If a release has to undo a
migration, restore the pre-release backup instead (`ops/README.md`, "Restore for real") — take one right before
every production deploy (backup container from `ops/compose.yaml`):

```bash
docker compose -f docker-compose.yml -f ops/deploy/compose.deploy.yaml --profile ops \
    run --rm --no-deps --entrypoint python3 backup /ops/backup/backup.py --out-dir /backups
```

## Known gaps (to fix with their owners)

- **Dev login.** `services/api/app/deps.py` switches the `X-User-Id` sign-in off only when `VERCEL` is set, so
  `compose.deploy.yaml` sets `VERCEL=1` on the api (this also makes it use no connection pool, which is fine at
  our size). Karim: replace with an explicit `DEV_LOGIN` default-off, or JWT, then drop that line.
- **`.env.example` has no `APPROVAL_HMAC_KEY`**, the key the gateway really reads (it lists `HMAC_SECRET`,
  which nothing reads). `deploy.env.example` has the right name; Anan: fix the shared example.
- Not tested here: pulling from GHCR and a real deploy (the build machine has no registry access). Tested:
  the compose override renders (`docker compose ... config`), `check_env.py` (tests/test_check_env.py),
  `deploy.sh` syntax, and the workflow with actionlint.
