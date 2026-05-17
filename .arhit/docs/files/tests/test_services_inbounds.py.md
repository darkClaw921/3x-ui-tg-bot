# tests/test_services_inbounds.py

Тесты для app.services.inbounds.list_user_inbounds — TTL-кэш + фильтрация enable.

Покрывает:
- Фильтрация: inbound с enable=False отбрасывается.
- Кэширование: второй вызов в течение TTL (30s) не дёргает xui (counter==1).
- Истечение TTL: monkeypatch на time.monotonic, перескакиваем на >30s — counter становится 2.
- clear_cache(): сбрасывает кэш, следующий вызов обращается к панели.
- Распространение исключений: при ошибке xui исключение пробрасывается, кэш не обновляется.
- Skip malformed: записи без id или с битым типом id пропускаются (logger.warning).

Фикстура autouse=_reset_cache: сбрасывает модульный кэш перед и после каждого теста.

См. также: app/services/inbounds.py.
