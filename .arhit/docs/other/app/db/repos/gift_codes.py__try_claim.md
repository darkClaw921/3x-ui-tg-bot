# app/db/repos/gift_codes.py::try_claim

Атомарный claim подарочного кода до провижининга (claim-first): под BEGIN IMMEDIATE guarded UPDATE status active→redeemed + redeemed_by/redeemed_at (subscription_id остаётся NULL). Возвращает GiftCode при выигрыше (rowcount=1) или None (нет кода/уже claimed/гонка). Пара к link_subscription (привязка sub после провижининга) и set_status (компенсация→active при XuiError).
