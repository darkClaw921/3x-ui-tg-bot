# app/services/inbounds.py

Сервис доступа к 3x-ui inbound-ам с TTL-кэшированием.

Назначение:
- Единая точка получения списка inbound-ов панели для бот-флоу (выбор inbound при покупке, мульти-селект в админ-карточке тарифа).
- Сглаживает нагрузку на 3x-ui: один запрос к /panel/api/inbounds/list в кэш на 30 секунд используется всеми параллельными хендлерами.

Ключевые элементы:
- InboundOption (frozen dataclass slots): {id:int, remark:str, port:int, enabled:bool} — проекция inbound-а с теми полями, что нужны клавиатурам и хендлерам.
- list_user_inbounds(xui: XuiClient) -> list[InboundOption]: основная функция. При кэш-хите возвращает без сетевого вызова. При промахе под asyncio.Lock делает double-check freshness и вызывает app.xui.inbounds.list_inbounds, фильтрует enable=True, кладёт в модульный _cache. Малформированные inbound-ы (без id/enable) логируются и пропускаются (а не падают).
- clear_cache(): сброс кэша для тестов и админ-действий, меняющих состояние inbound-ов на панели.

Реализация TTL-кэша:
- Модульные переменные _cache (list[InboundOption] | None), _ts (float, time.monotonic), _lock (asyncio.Lock).
- _CACHE_TTL_SEC = 30.0; time.monotonic() для устойчивости к скачкам системных часов.
- При исключении из 3x-ui кэш НЕ обновляется (исключение пробрасывается).

Зависимости:
- app.xui.XuiClient, app.xui.inbounds.list_inbounds.
- loguru для предупреждений о малформированных записях.

Контракт безопасности (asyncio):
- Lock защищает только обновление; чтение свежего кэша без лока — допустимо, переменные присваиваются атомарно (тип list/None).
