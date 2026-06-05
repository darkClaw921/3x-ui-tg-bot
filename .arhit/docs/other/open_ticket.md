# open_ticket

app/services/tickets.py — сервис машины статусов тикетов. open_ticket (reuse-or-create non-closed тикета юзера + статус open), reply_user (open), reply_admin (answered), close_ticket (closed, идемпотентно). Framework-agnostic (только БД), ретрансляцию в Telegram делают хендлеры.
