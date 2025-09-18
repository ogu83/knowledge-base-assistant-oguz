\
# Base image with Python (backend) on Debian and system tools available
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PGDATA=/var/lib/postgresql/data

# Install PostgreSQL server + curl + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gosu supervisor \
      postgresql postgresql-contrib postgresql-common \
    && rm -rf /var/lib/apt/lists/*

# Create runtime users, dirs
RUN useradd -m -s /bin/bash appuser && \
    mkdir -p /app/backend /app/frontend /var/log/supervisor && \
    chown -R appuser:appuser /app /var/log/supervisor

# COPY Backend
COPY ./backend/requirements.txt /app/backend/requirements.txt
COPY ./backend/*.py /app/backend/
COPY ./backend/data/ /app/backend/data/

# COPY Frontend
COPY ./frontend/index.html /app/frontend/index.html
COPY ./frontend/style.css /app/frontend/style.css

# Docker/runtime helpers
COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY ./init_pg.sh /usr/local/bin/init_pg.sh
COPY ./entrypoint.sh /usr/local/bin/entrypoint.sh
 # Normalize Windows CRLF and strip UTF-8 BOM, then chmod
RUN sed -i 's/\r$//' /etc/supervisor/conf.d/supervisord.conf /usr/local/bin/init_pg.sh /usr/local/bin/entrypoint.sh \
 && sed -i '1s/^\xEF\xBB\xBF//' /etc/supervisor/conf.d/supervisord.conf /usr/local/bin/init_pg.sh /usr/local/bin/entrypoint.sh \
 && chmod +x /usr/local/bin/init_pg.sh /usr/local/bin/entrypoint.sh


# Install Python deps
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Expose service ports
EXPOSE 8000 8001

# Switch to non-root for app processes; postgres will still run as 'postgres' user via gosu
# USER appuser

# Entrypoint will escalate where needed to init the database
# ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
ENTRYPOINT ["bash", "/usr/local/bin/entrypoint.sh"]