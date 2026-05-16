# _expires_days_to_iso

Конвертер 'N дней от сейчас' в ISO-8601 строку в app/handlers/admin/promos.py. days<=0 → None ('бессрочно'); иначе now+N days с замером 23:59:59 UTC (microsecond=0), формат isoformat(sep=' ') — совместим с _parse_expires_at и колонкой promos.expires_at.
