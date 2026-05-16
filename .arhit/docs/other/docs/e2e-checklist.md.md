# docs/e2e-checklist.md

Ручной end-to-end чек-лист для прогона на staging-инстансе 3x-ui и dev-аккаунте Telegram-бота (Stars test mode).

Структура:
- Подготовка: требования к staging-окружению (3x-ui inbound, .env, ADMIN_IDS, XRay-клиент, чистая БД).
- Админ-флоу: /start под админом, создание тарифа Test-30d, создание трёх промокодов (percent TEST10, flat_stars TESTFLAT, free_days TESTFREE).
- Пользовательский флоу: /start, покупка тарифа через Stars, получение vless+QR+sub URL, подключение XRay-клиентом, проверка роста трафика.
- Покупка со скидкой percent и flat_stars: проверка пересчёта суммы и инкремента used_count.
- Активация free_days: проверка продления подписки и used_count.
- Админ: деактивация тарифа (исчезает у юзера), сводная статистика.
- Scheduler: имитация истечения (UPDATE subscriptions SET expires_at), проверка disabled в 3x-ui и нотификации.
- Завершение: фиксация багов в br, синхронизация architecture.md и README.

Используется: перед промо-релизом и после изменений в services.subscriptions, services.billing, xui/*, handlers/user/buy, handlers/admin/*, scheduler.
