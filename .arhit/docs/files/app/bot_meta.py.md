# app/bot_meta.py

Кэш идентичности бота. get_bot_username(bot) — Bot.get_me() один раз, мемоизация по bot.id (для ссылок ?start=ref_/gift_). clear_cache() для тестов. Fallback '' если username отсутствует.
