# tickets

Репозиторий app/db/repos/tickets.py — таблицы tickets + ticket_messages (двусторонний чат поддержки). Ticket(id,user_id,status,created_at,updated_at) со статусами open→answered→closed; TicketMessage(id,ticket_id,sender('user'|'admin'),text,tg_message_id,created_at). Функции: create_ticket, add_message (бампит updated_at, статус не меняет), get, list_open (non-closed по updated_at DESC), list_for_user, get_open_for_user (reuse тикета), set_status, list_messages.
