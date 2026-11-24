# Backup runner (owner: M4 Ziad). pg_dump must be at least the server's major version, so this starts from the
# same postgres:16 image the database uses and adds only Python + psycopg for the scripts.
FROM postgres:16-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-psycopg \
 && rm -rf /var/lib/apt/lists/*
COPY ops/backup /ops/backup
RUN mkdir -p /backups && chown postgres:postgres /backups  # a new named volume copies this owner
USER postgres
WORKDIR /backups
# One backup now, then one every BACKUP_INTERVAL_HOURS (default 24). A failed run exits so the restart policy and
# `docker compose ps` show it, instead of a loop that silently keeps failing.
ENTRYPOINT ["/bin/sh", "-c", "while true; do python3 /ops/backup/backup.py --out-dir /backups || exit 1; sleep $(( ${BACKUP_INTERVAL_HOURS:-24} * 3600 )); done"]
