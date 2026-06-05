# app/keyboards/user.py::user_main_menu

Главное меню юзера. Параметры: has_subscription (порядок Моя/Купить), can_trial (показ кнопки 🎁 Пробный период = TRIAL_DAYS>0 AND not has_trial), lang. Кнопки: Моя/Купить, [trial.btn если can_trial], wallet.btn_open, menu.btn_promo, referral.btn (ReferralCB open), gift.btn_buy (GiftCB buy), gift.btn_redeem (GiftCB redeem), help, lang. Новые callback-фабрики: TrialCB(action), ReferralCB(action), GiftCB(action). BuyCB получил поле gift:int=0.
