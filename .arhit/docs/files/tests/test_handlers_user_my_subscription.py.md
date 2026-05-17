# tests/test_handlers_user_my_subscription.py

Tests for app.handlers.user.my_subscription after Phase 4 (multi-subscription screen).

## Coverage

- **Pure helpers**: _format_bytes (0/KB/GB/negative), _parse_iso, _days_delta (future/past), _pluralize_subs (1 / 2-4 / 5+), _format_status_line (active/revoked/expired), _format_days_line (today/yesterday).
- **_fetch_traffics**: bad int from panel, unexpected exception — both must return ok=False without crashing.
- **_sort_subs**: active first by expires_at DESC, inactive after.
- **cb_open_my**:
  - test_cb_open_my_no_subs_renders_buy_cta — empty state with BuyCB(open) shortcut.
  - test_cb_open_my_single_active_sub_renders_card_with_actions — full layout pinned: top 🆕 Купить новую (BuyCB new), per-sub 🔑 Ключи #N + 🛒 Продлить #N, bottom ◀ В меню.
  - test_cb_open_my_renders_all_subscriptions — ≥2 active subs each get their own keys+extend buttons.
  - test_cb_open_my_expired_sub_has_no_extend_button — expired sub gets only Ключи #N; top buy-new still present.
  - test_cb_open_my_caps_at_5_and_shows_footer — 7 subs → 5 cards + '… и ещё 2 подписки'; keyboard buttons mirror the cap.
  - test_cb_open_my_active_sorted_by_expiry_desc — long/mid/short expiries appear in the right order.
  - test_cb_open_my_active_before_inactive — even when inactive row is newer, active comes first.
  - test_cb_open_my_top_button_is_buy_new — first row is always BuyCB(new).
  - test_cb_open_my_xui_error — panel down falls back to soft notice.
  - test_cb_open_my_user_none — missing user triggers alert via callback.answer.
  - test_cb_open_my_multiple_subs / test_cb_open_my_lots_of_inactive — smoke + footer rendering.
- **cb_resend_keys**: no_user / no_sub_id / ownership_mismatch / no_message / happy / xui_error_message.

## Test helpers

- _kb_buttons(markup) — list-of-rows of (text, callback_data) tuples.
- _flat_buttons(markup) — flat list across all rows; the workhorse for asserting individual buttons exist.
- _mock_callback() — MagicMock CallbackQuery with awaited edit_text + answer.
- _make_sub(...) — in-memory Subscription factory for direct _sort_subs / formatter assertions, bypassing the DB layer.
