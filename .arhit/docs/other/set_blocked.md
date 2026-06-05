# set_blocked

app/db/repos/users.py::set_blocked/is_blocked — бан/разбан юзера. set_blocked(conn,user_id,blocked) выставляет users.is_blocked; is_blocked(conn,tg_id)->bool узкий lookup для BlockedUserMiddleware (False для неизвестного). User dataclass получил поле is_blocked (дефолт False) + from_row терпит row без колонки.
