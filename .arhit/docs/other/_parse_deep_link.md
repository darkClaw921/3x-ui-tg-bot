# _parse_deep_link

app/handlers/start.py — классифицирует /start deep-link аргумент. Возвращает (kind,value): 'ref_123'→('ref','123'), 'gift_ABC'→('gift','ABC'). None для пустого/неизвестного аргумента или пустого значения после префикса (ref_/gift_). Префиксы _REF_PREFIX='ref_', _GIFT_PREFIX='gift_'.
