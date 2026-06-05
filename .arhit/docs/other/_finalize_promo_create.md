# _finalize_promo_create

Helper: создаёт промокод из FSM-данных, очищает state, рисует карточку. Параметр edit: bool=False определяет вывод: edit=True (вызов из cb_promo_preset на шаге expires) редактирует сообщение через edit_text — и при успехе, и при IntegrityError; edit=False (вызов из st_expires_at, текстовый ввод) — answer. Через send = message.edit_text if edit else message.answer.
