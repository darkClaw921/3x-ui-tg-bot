# app/handlers/user/buy.py::cb_gift_buy

Вход в покупку подарка (GiftCB action='buy'): clear FSM, set gift=1+sub_id=0, показать список планов (всегда new-sub flow, action-экран продлить/новая пропущен). Поле gift протянуто через FSM и confirm_kb во всех new-sub ветках (cb_pick_plan/cb_pick_inbound/cb_apply_promo/msg_promo_code); cb_confirm при gift=1 шлёт billing.send_gift_invoice. Поле gift:int добавлено в BuyCB и confirm_kb.
