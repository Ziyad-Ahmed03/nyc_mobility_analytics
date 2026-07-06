#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nyc_user') THEN
            CREATE USER nyc_user WITH PASSWORD 'nyc_pass_2025';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nyc_readonly') THEN
            CREATE USER nyc_readonly WITH PASSWORD 'readonly_2025';
        END IF;
    END
    \$\$;

    SELECT 'CREATE DATABASE nyc_mobility OWNER nyc_user'
    WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = 'nyc_mobility'
    )\gexec

    GRANT ALL PRIVILEGES ON DATABASE nyc_mobility TO nyc_user;
EOSQL

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "nyc_mobility" \
    -f /docker-entrypoint-initdb.d/01_schema.sql

echo "Database initialized ✓"
