#!/bin/bash
# Install PostgreSQL 17 client tools (pg_dump, psql) from the official PGDG repo.
# Server stays on 16; this only adds version-17 client binaries.
# Run as: sudo bash scripts/install-pg17-client.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME}")

if [[ ! -f /etc/apt/sources.list.d/pgdg.list ]]; then
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
fi

apt-get update -qq
apt-get install -y postgresql-client-17

echo "==> Installed:"
/usr/lib/postgresql/17/bin/pg_dump --version
