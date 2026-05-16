# app/main.py

Точка входа приложения (python -m app.main). async def main(): setup_logging(); await init_db(); Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)); Dispatcher(storage=MemoryStorage()); register_routers(dp); scheduler = setup_scheduler(bot); scheduler.start(); await dp.start_polling(bot); finally: scheduler.shutdown(wait=False), await close_xui_client(), await bot.session.close(). Каждый шаг shutdown в try/except — best-effort. __main__ блок ловит KeyboardInterrupt/SystemExit для graceful exit.
