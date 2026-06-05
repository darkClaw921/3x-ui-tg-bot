# audit

Репозиторий app/db/repos/audit.py — таблица audit_log (трейл админ-действий). AuditEntry(id,admin_id,action,target_type,target_id,details(JSON),created_at). add (append), get, list_recent (newest first, пагинация limit/offset), count. admin_id — FK users.id ON DELETE SET NULL.
