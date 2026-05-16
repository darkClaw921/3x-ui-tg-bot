# app/logger.py

Настройка loguru и мост со стандартным модулем logging. Класс InterceptHandler(logging.Handler) перенаправляет записи stdlib logging в loguru, сохраняя имя уровня и корректный кадр-источник. Функция setup_logging(level: str | None = None) удаляет дефолтный sink, добавляет sink на sys.stderr с форматом time|level|name:function:line|message, монтирует InterceptHandler через logging.basicConfig (force=True), отдельно перенастраивает aiogram/aiogram.event/httpx/httpcore/apscheduler. Импорт модуля побочных эффектов не имеет. Параметр level переопределяет settings.LOG_LEVEL.
