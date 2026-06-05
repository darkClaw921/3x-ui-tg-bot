# app/db/repos/subscriptions.py::has_trial

Возвращает True, если у пользователя уже есть trial-подписка (is_trial=1). Дешёвый race-tolerant SELECT перед activate_trial; жёсткая гарантия 'один trial на юзера' обеспечивается partial-unique индексом idx_subscriptions_one_trial. Используется для скрытия кнопки 'Пробный период' и как предпроверка.
