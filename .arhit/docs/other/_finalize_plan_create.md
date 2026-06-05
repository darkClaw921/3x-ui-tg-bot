# _finalize_plan_create

Helper: сохраняет тариф из FSM-данных, очищает state, рисует карточку тарифа. Параметр edit: bool=False определяет вывод: edit=True (вызов из cb_inbounds_done) редактирует сообщение мульти-селекта в карточку через edit_text; edit=False — answer. Через send = message.edit_text if edit else message.answer.
