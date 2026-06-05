# _enter_inbounds_step

Helper мастера тарифов: загружает inbounds из 3x-ui, кэширует их в FSM (inbound_options), переводит в PlanCreate.waiting_inbounds и рисует мульти-селект. Параметр edit: bool=False управляет способом вывода — при edit=True используется message.edit_text (путь инлайн-кнопки из cb_plan_preset gb-шага), при edit=False — message.answer (путь текстового ввода из st_traffic_gb). Внутри: send = message.edit_text if edit else message.answer применяется ко всем веткам (ошибка xui, пустой список, успешный вывод).
