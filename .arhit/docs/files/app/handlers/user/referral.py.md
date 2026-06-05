# app/handlers/user/referral.py

Роутер экрана 'Пригласить друга'. cb_open (ReferralCB action='open'): строит ссылку https://t.me/<bot_username>?start=ref_<tg_id> (username через app.bot_meta.get_bot_username — кэш per bot.id), показывает count_for_referrer + рекламу бонуса (referral.screen_body при REFERRAL_BONUS_STARS>0 иначе screen_body_no_bonus). Тексты referral.* (RU+EN).
