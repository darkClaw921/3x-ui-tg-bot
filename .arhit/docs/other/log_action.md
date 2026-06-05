# log_action

app/services/audit.py — crash-safe запись админ-действия в audit_log. log_action(conn,admin_id,action,target_type,target_id,details) сериализует details в JSON, любое исключение проглатывает (возврат None), чтобы аудит-фейл не ломал само действие. Вызывается из plan/promo CRUD, user revoke/toggle_admin/grant_sub/block, broadcast, ticket reply/close.
