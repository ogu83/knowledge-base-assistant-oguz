#!/usr/bin/env bash
set -euo pipefail

# Ensure data dir exists and is owned by postgres BEFORE initdb
mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"

# Prepare PostgreSQL data directory if it's empty
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "Initializing new PostgreSQL cluster at $PGDATA"
  # Discover postgres binary dir dynamically and run initdb as postgres
  PG_BIN=$(dirname $(realpath /usr/lib/postgresql/*/bin/initdb))
  gosu postgres $PG_BIN/initdb -D "$PGDATA"

  # Allow remote connections and listen on all interfaces
  echo "host all all 0.0.0.0/0 md5" >> "$PGDATA/pg_hba.conf"
  echo "listen_addresses='*'" >> "$PGDATA/postgresql.conf"
fi

# Ensure permissions (idempotent)
chown -R postgres:postgres "$PGDATA"
