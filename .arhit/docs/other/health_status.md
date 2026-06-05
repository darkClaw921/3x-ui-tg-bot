# health_status

DB table (schema.sql + engine.create_table_migrations): one row per component (default 'xui'). Columns: id, component UNIQUE, status CHECK in ('up','down'), last_error TEXT NULL, changed_at TIMESTAMP. Repo app/db/repos/health.py: get(conn, component) -> HealthRow|None; record(conn, *, status, last_error, component) upserts and returns (HealthRow, changed) where changed is True only on a real state flip (changed_at bumped only on flip). Drives the health-check alert-on-transition behaviour.
