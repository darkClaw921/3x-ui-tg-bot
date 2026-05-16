# test_handlers_admin_promos

Тесты для app/handlers/admin/promos.py (tests/test_handlers_admin_promos.py). Покрывают: _parse_expires_at, _promo_is_active, cb_list/cb_card/cb_deactivate/cb_redemptions, FSM-хендлеры cb_create/st_code/cb_type/st_value/st_max_uses/st_expires_at, а также пресет-callbacks cb_promo_preset (value для percent/flat_stars/free_days, max_uses 0/finite, expires 0→None и +30д→ISO с допуском по секундам), cb_promo_manual для всех полей, и helper _expires_days_to_iso.
