#!/usr/bin/env bash
# Deploy one image tag to this Docker host (owner: M4 Ziad).
#   ops/deploy/deploy.sh staging            # IMAGE_TAG from .env
#   ops/deploy/deploy.sh production v0.2.0  # pins IMAGE_TAG for this run
# Steps: check .env -> pull images -> migrate the database -> start -> wait for /health. Stops at the first failure,
# so a failed migration never starts new code against an old schema. Rollback: run again with the previous tag
# (migrations are not rolled back automatically: read ops/deploy/README.md).
set -euo pipefail
cd "$(dirname "$0")/../.."

stage="${1:-}"
[[ "$stage" == staging || "$stage" == production ]] || { echo "usage: $0 staging|production [IMAGE_TAG]" >&2; exit 2; }
[[ -f .env ]] || { echo ".env not found in $(pwd) (see ops/deploy/deploy.env.example)" >&2; exit 2; }
if [[ -n "${2:-}" ]]; then export IMAGE_TAG="$2"; fi

echo "== 1/5 check .env for $stage"
python3 ops/deploy/check_env.py "$stage" .env
if [[ "$stage" == production && -z "${2:-}" ]]; then
  echo "production deploys name their tag: $0 production vX.Y.Z" >&2; exit 2
fi

compose=(docker compose -f docker-compose.yml -f ops/deploy/compose.deploy.yaml)
echo "== 2/5 pull images (${IMAGE_TAG:-from .env})"
"${compose[@]}" pull api agent gateway risk extractor

echo "== 3/5 migrate the database (alembic upgrade head, from the api image)"
"${compose[@]}" up -d --wait postgres
"${compose[@]}" run --rm --no-deps api alembic upgrade head

echo "== 4/5 start"
"${compose[@]}" up -d --no-build --remove-orphans --wait --wait-timeout 180 api agent gateway risk extractor

echo "== 5/5 health"
ok=1
for i in 1 2 3 4 5 6; do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null; then ok=0; break; fi
  sleep 5
done
if [[ $ok -ne 0 ]]; then
  echo "api did not answer /health: '${compose[*]} logs api' and roll back with the previous tag" >&2
  exit 1
fi
"${compose[@]}" ps
echo "deployed $stage ${IMAGE_TAG:-(tag from .env)}"
