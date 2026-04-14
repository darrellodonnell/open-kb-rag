#!/bin/bash
# Phase 6: Nightly pg_dump of kb DB → local + s3://claude-backups/open-kb-rag/
# Run on jones as: sudo bash scripts/phase6-setup-backups.sh
# Idempotent — safe to re-run.

set -euo pipefail

BUCKET="claude-backups-56daf950"
PREFIX="open-kb-rag"
REGION="us-east-1"
BACKUP_USER="darrellodonnell"
BACKUP_HOME="/home/${BACKUP_USER}"
BIN_PATH="/usr/local/bin/kb-backup.sh"
SERVICE_UNIT="/etc/systemd/system/kb-backup.service"
TIMER_UNIT="/etc/systemd/system/kb-backup.timer"
LOCAL_DUMP_DIR="${BACKUP_HOME}/backups/kb"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

echo "==> Creating local dump dir: ${LOCAL_DUMP_DIR}"
install -d -o "${BACKUP_USER}" -g "${BACKUP_USER}" -m 0700 "${LOCAL_DUMP_DIR}"

echo "==> Ensuring S3 bucket s3://${BUCKET}"
if ! sudo -u "${BACKUP_USER}" aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  # us-east-1 doesn't accept LocationConstraint
  if [[ "${REGION}" == "us-east-1" ]]; then
    sudo -u "${BACKUP_USER}" aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
  else
    sudo -u "${BACKUP_USER}" aws s3api create-bucket --bucket "${BUCKET}" \
      --region "${REGION}" \
      --create-bucket-configuration LocationConstraint="${REGION}"
  fi
fi

echo "==> Block all public access"
sudo -u "${BACKUP_USER}" aws s3api put-public-access-block --bucket "${BUCKET}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "==> Enable default encryption (SSE-S3)"
sudo -u "${BACKUP_USER}" aws s3api put-bucket-encryption --bucket "${BUCKET}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'

echo "==> Enable versioning"
sudo -u "${BACKUP_USER}" aws s3api put-bucket-versioning --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

echo "==> Apply lifecycle rule for prefix ${PREFIX}/"
cat > /tmp/kb-lifecycle.json <<JSON
{
  "Rules": [
    {
      "ID": "open-kb-rag-transitions",
      "Filter": { "Prefix": "${PREFIX}/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "GLACIER" }
      ],
      "Expiration": { "Days": 180 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
    }
  ]
}
JSON
sudo -u "${BACKUP_USER}" aws s3api put-bucket-lifecycle-configuration \
  --bucket "${BUCKET}" \
  --lifecycle-configuration file:///tmp/kb-lifecycle.json
rm /tmp/kb-lifecycle.json

echo "==> Installing ${BIN_PATH}"
cat > "${BIN_PATH}" <<'SCRIPT'
#!/bin/bash
# Nightly backup of the kb PostgreSQL database.
# Invoked by kb-backup.service on a daily timer.

set -euo pipefail

BUCKET="claude-backups-56daf950"
PREFIX="open-kb-rag"
DUMP_DIR="${HOME}/backups/kb"
LOCAL_RETAIN_DAYS=7

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${DUMP_DIR}/kb-${TS}.dump"

# Pin pg_dump to PG 16 (matches server version) so any pg_restore 16+ can read.
# The postgresql-client-17 we installed for the Supabase migration can silently
# shadow this — never use bare "pg_dump" here.
PG_DUMP="/usr/lib/postgresql/16/bin/pg_dump"

echo "[$(date -Iseconds)] starting backup → ${OUT}"
PGPASSWORD="$(cat "${HOME}/.kb-db-password")" \
  "${PG_DUMP}" --format=custom --compress=9 --no-owner --no-acl \
          -h localhost -U kb -d kb \
          --file "${OUT}"

SIZE=$(stat -c %s "${OUT}")
echo "[$(date -Iseconds)] dump size: ${SIZE} bytes"

echo "[$(date -Iseconds)] uploading to s3://${BUCKET}/${PREFIX}/"
aws s3 cp "${OUT}" "s3://${BUCKET}/${PREFIX}/kb-${TS}.dump" \
  --storage-class STANDARD --only-show-errors

echo "[$(date -Iseconds)] pruning local dumps older than ${LOCAL_RETAIN_DAYS} days"
find "${DUMP_DIR}" -name 'kb-*.dump' -mtime "+${LOCAL_RETAIN_DAYS}" -delete

echo "[$(date -Iseconds)] DONE"
SCRIPT
chmod 0755 "${BIN_PATH}"

echo "==> Installing ${SERVICE_UNIT}"
cat > "${SERVICE_UNIT}" <<UNIT
[Unit]
Description=Nightly backup of kb PostgreSQL database
Wants=network-online.target
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=${BACKUP_USER}
Group=${BACKUP_USER}
WorkingDirectory=${BACKUP_HOME}
ExecStart=${BIN_PATH}
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UNIT

echo "==> Installing ${TIMER_UNIT}"
cat > "${TIMER_UNIT}" <<'UNIT'
[Unit]
Description=Daily timer for kb-backup.service

[Timer]
OnCalendar=*-*-* 10:00:00 UTC
RandomizedDelaySec=5m
Persistent=true
Unit=kb-backup.service

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now kb-backup.timer

echo
echo "==> DONE. Next scheduled run:"
systemctl list-timers kb-backup.timer --no-pager | head -5
echo
echo "To run an immediate test: sudo systemctl start kb-backup.service"
echo "To view logs:             journalctl -u kb-backup.service -n 50"
