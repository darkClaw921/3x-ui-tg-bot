# app/handlers/start.py::cmd_start

Обработчик /start. Парсит deep-link через _parse_deep_link: ref_<tg_id> → _handle_ref_deep_link (register_referral, привязка на первом /start, защита self-ref, best-effort); gift_<code> → _handle_gift_deep_link (redeem_gift → deliver_keys получателю + _notify_gift_buyer DM покупателю; на GiftRedeemError/XuiError — сообщение об ошибке; True=ранний выход без приветствия). Затем: админ-меню или user_main_menu(has_subscription, can_trial=(TRIAL_DAYS>0 and not has_trial)). Добавлен параметр bot:Bot|None.
