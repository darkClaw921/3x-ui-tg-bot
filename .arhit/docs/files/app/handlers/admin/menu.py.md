# app/handlers/admin/menu.py

Хэндлеры команды /admin и навигации в админ-меню. router = Router(name='admin_menu'). cmd_admin(message) на Command('admin') — отвечает _GREETING + admin_main_menu(). open_main(callback) на AdminCB(area=main, action in {open,back}) — edit_text обратно в главное меню. cancel_fsm(callback, state) на AdminCB(action=cancel) — state.clear() + возврат в главное меню; используется как единая Cancel-точка во всех wizard'ах.
