#!/bin/bash
# Phase 7: Upgrade PostgreSQL 16 -> 17 on jones
# Uses pg_upgradecluster in dump mode (safest for small DBs with extensions).
# Run as: sudo bash scripts/phase7-upgrade-to-pg17.sh
# One-shot — not intended to be re-run.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

echo "==> Current clusters:"
pg_lsclusters

echo "==> Pre-upgrade safety backup"
DUMP_DIR="/var/backups/kb"
install -d -o postgres -g postgres -m 0700 "${DUMP_DIR}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
SAFETY_DUMP="${DUMP_DIR}/pre-upgrade-${TS}.dump"
sudo -u postgres /usr/lib/postgresql/16/bin/pg_dump \
  --format=custom --compress=9 --no-owner --no-acl \
  -d kb --file "${SAFETY_DUMP}"
ls -lh "${SAFETY_DUMP}"

echo "==> Pre-upgrade row counts"
sudo -u postgres /usr/lib/postgresql/16/bin/psql -d kb -c \
  "SELECT 'sources' AS t, count(*) FROM sources
   UNION ALL SELECT 'chunks', count(*) FROM chunks
   UNION ALL SELECT 'tags', count(*) FROM tags
   UNION ALL SELECT 'source_tags', count(*) FROM source_tags;"

echo "==> Stopping kb services"
systemctl stop kb-mcp.service kb-slack.service

echo "==> Installing PostgreSQL 17 server + pgvector (PGDG repo already configured)"
apt-get update -qq
apt-get install -y postgresql-17 postgresql-17-pgvector

echo "==> Dropping the auto-created empty PG17 cluster so upgradecluster can own 17/main"
if pg_lsclusters -h | awk '{print $1"/"$2}' | grep -q "^17/main$"; then
  pg_dropcluster --stop 17 main
fi

echo "==> Running pg_upgradecluster 16 main (dump mode)"
pg_upgradecluster -m dump 16 main

echo "==> Cluster state after upgrade:"
pg_lsclusters

echo "==> Verifying via new PG17 cluster on port 5432"
PGPASSWORD="$(cat /root/.kb-db-password)" psql -h localhost -U kb -d kb \
  -c "SELECT version();" \
  -c "SELECT extname, extversion FROM pg_extension ORDER BY extname;" \
  -c "SELECT 'sources' AS t, count(*) FROM sources
      UNION ALL SELECT 'chunks', count(*) FROM chunks
      UNION ALL SELECT 'tags', count(*) FROM tags
      UNION ALL SELECT 'source_tags', count(*) FROM source_tags;"

echo "==> Dropping old PG16 cluster"
pg_dropcluster --stop 16 main

echo "==> Removing PG16 server packages (keeps client-17 already installed)"
apt-get remove -y postgresql-16 postgresql-16-pgvector
apt-get autoremove -y

echo "==> Updating backup script to use PG17 pg_dump"
if [[ -f /usr/local/bin/kb-backup.sh ]]; then
  sed -i 's|/usr/lib/postgresql/16/bin/pg_dump|/usr/lib/postgresql/17/bin/pg_dump|' /usr/local/bin/kb-backup.sh
  echo "Updated /usr/local/bin/kb-backup.sh"
  grep PG_DUMP= /usr/local/bin/kb-backup.sh
fi

echo "==> Restarting kb services"
systemctl start kb-mcp.service kb-slack.service
sleep 2
systemctl is-active kb-mcp.service kb-slack.service

echo
echo "==> DONE. Safety backup kept at ${SAFETY_DUMP}"
pg_lsclusters
