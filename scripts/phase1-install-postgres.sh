#!/bin/bash
# Phase 1: Install PostgreSQL 16 + pgvector on jones.quagga-chicken.ts.net
# Run on the VM as: sudo bash scripts/phase1-install-postgres.sh
# Idempotent — safe to re-run.

set -euo pipefail

DB_NAME="kb"
DB_ROLE="kb"
PW_FILE="/root/.kb-db-password"
TAILNET_CIDR="100.64.0.0/10"
PG_VERSION="16"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

echo "==> Installing PostgreSQL ${PG_VERSION} and pgvector"
apt-get update -qq
apt-get install -y "postgresql-${PG_VERSION}" "postgresql-${PG_VERSION}-pgvector"

systemctl enable --now postgresql

echo "==> Generating DB password (stored at ${PW_FILE})"
if [[ ! -f "${PW_FILE}" ]]; then
  umask 077
  openssl rand -base64 24 > "${PW_FILE}"
  chmod 600 "${PW_FILE}"
fi
DB_PASSWORD=$(cat "${PW_FILE}")

echo "==> Creating role '${DB_ROLE}' and database '${DB_NAME}'"
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_ROLE}') THEN
    CREATE ROLE ${DB_ROLE} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_ROLE} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;
SQL

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres createdb -O "${DB_ROLE}" "${DB_NAME}"

echo "==> Installing pgvector extension in ${DB_NAME}"
sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "==> Configuring listen_addresses and pg_hba.conf for Tailscale"
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

if ! grep -qE "^listen_addresses\s*=\s*'localhost,100" "${PG_CONF}"; then
  sed -i "s|^#\?listen_addresses\s*=.*|listen_addresses = 'localhost,100.105.173.93'|" "${PG_CONF}"
fi

if ! grep -qF "${TAILNET_CIDR}" "${PG_HBA}"; then
  echo "# Tailnet access (added by phase1-install-postgres.sh)" >> "${PG_HBA}"
  echo "host    ${DB_NAME}    ${DB_ROLE}    ${TAILNET_CIDR}    scram-sha-256" >> "${PG_HBA}"
fi

systemctl restart postgresql

echo "==> Verifying"
sudo -u postgres psql -d "${DB_NAME}" -c "\dx vector"
sudo -u postgres psql -d "${DB_NAME}" -c "SELECT current_database(), current_user;"

echo
echo "==> DONE"
echo "DB password stored at ${PW_FILE} (root-only, 600)"
echo "Connection string (from this VM):"
echo "  postgresql://${DB_ROLE}:<password>@localhost/${DB_NAME}"
echo "Connection string (from Tailnet):"
echo "  postgresql://${DB_ROLE}:<password>@jones.quagga-chicken.ts.net/${DB_NAME}"
echo
echo "Next: apply sql/init.sql from the repo checkout on this VM."
