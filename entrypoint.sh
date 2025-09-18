\
#!/usr/bin/env bash
set -euo pipefail

# We expect a .env (or env vars) to provide PG_HOST/PORT/USER/PASSWORD/DBNAME and OPENAI_*.
# See .env.example in the repo.

# 1) Initialize postgres data directory if needed
echo "[entrypoint] Ensuring PostgreSQL data dir"
/usr/local/bin/init_pg.sh

# 2) Start supervisord which launches postgres, then init_db.py, then API + frontend
echo "[entrypoint] Starting supervisor (postgres, init_db, api, frontend)"
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
