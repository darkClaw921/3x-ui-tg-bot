# app/handlers/user/_keys.py

deliver_keys(bot,xui,chat_id,sub,*,header=None,lang=DEFAULT_LANG): шлёт vless URI+QR+Subscription URL. Тексты локализованы через i18n.t (keys.* namespace), header=None резолвится в keys.header_active. lang прокидывается из хендлеров.
