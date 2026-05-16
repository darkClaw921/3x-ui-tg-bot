# app/handlers/user/menu.py

Главное меню пользователя. cmd_menu (/menu) и cb_menu (UserCB area=menu) → user_main_menu с приоритетом 'Моя подписка' если subs_repo.get_active_for_user вернул запись. cb_cancel (UserCB area=cancel) очищает FSM и возвращает в меню. _send_main_menu(edit=bool) — единая точка рендера для edit_text/answer.
