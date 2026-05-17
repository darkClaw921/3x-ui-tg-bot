# app/handlers/user/my_subscription.py

User-facing «Моя подписка» screen handlers.

Renders **all** subscriptions of the user (not only the primary one). The screen has two main handlers and a set of pure helpers.

## Handlers

- **cb_open_my** — callback UserCB(area='my'). Loads subs_repo.list_for_user, sorts via _sort_subs (active first by expires_at DESC, then inactive by created_at DESC, ties by id DESC), caps the list to _MAX_VISIBLE_SUBS=5, renders one card per visible sub joined by ━━━━━ separator, appends '… и ещё N подписк{а|и|ок}' footer when more than 5 exist. The card text comes from _format_sub_card (status / expiry / days delta / live traffic via _fetch_traffics). When no subs exist — friendly 'У вас пока нет подписки' screen with _no_subscription_kb (uses BuyCB action='open').

- **cb_resend_keys** — callback SubCB(action='keys', sub_id=N). Re-delivers vless URI + QR + subscription URL via deliver_keys helper. Ownership check (sub.user_id == user.id) prevents leaking foreign keys; identical 'не найдена' alert for not-found and not-yours to avoid info leak. XuiError surfaces a soft 'панель временно недоступна' message via bot.send_message.

## Keyboard layout (_build_subs_keyboard)

1. Top: 🆕 Купить новую подписку — BuyCB(action='new'), stateless entry registered in buy.py without state filter (Phase 2). Bypasses the 'продлить vs новая' action screen.
2. Per visible sub: a row with 🔑 Ключи #N — SubCB(action='keys', sub_id=N) plus, only when _is_active(sub) is True, 🛒 Продлить #N — BuyCB(action='extend', sub_id=N). Extend is gated on active because cb_pick_action_extend in buy.py rejects non-active subs.
3. Bottom: ◀ В меню — UserCB(area='menu').

## Helpers

- _format_bytes / _parse_iso / _days_delta / _is_active — pure formatting/parsing.
- _format_days_line — 'Истекает через N дн.' / 'Истекает сегодня' / 'Истекла N дн. назад'.
- _format_status_line — '✅ активна' / '🚫 отозвана' / '❌ истекла'.
- _fetch_traffics — pulls live up/down from 3x-ui via get_client_traffics; never raises (returns ok=False on any error).
- _format_sub_card — 5-line HTML card (header + 3 lines + traffic line).
- _sort_subs — active-first ordering described above.
- _build_subs_keyboard — composes the inline keyboard via a tiny _btn helper.
- _pluralize_subs — Russian plural (1 / 2-4 / 5+) for 'подписк-'.
- _MAX_VISIBLE_SUBS = 5 — Telegram 4096-byte friendly cap.

## Routing

- router = Router(name='user_my_subscription').
- Registered via app.handlers.user package init.

## Tests

tests/test_handlers_user_my_subscription.py covers: empty state, single active, multiple active, expired-only, panel error fallback, ownership mismatch on keys, sort order, cap+footer, plural forms.
