"""User "My subscription" screen.

Handlers
--------

* :func:`cb_open_my` — callback ``UserCB(area='my')``: render a single
  message containing per-subscription cards for **all** of the user's
  subscriptions. Active subscriptions are listed first (sorted by
  ``expires_at`` DESC), then expired / revoked ones (sorted by
  ``created_at`` DESC, which matches ``list_for_user`` ordering). The
  first five subscriptions are rendered in full; if more exist, the
  card list is capped with a ``«… и ещё N подписок»`` footer so the
  message stays under Telegram's 4096-byte limit.

  The inline keyboard mirrors the cards:

  * a single ``«🆕 Купить новую подписку»`` row at the top (always
    visible — it doubles as the only CTA when every existing sub is
    expired);
  * one row per visible subscription with two side-by-side buttons:
    ``«🔑 Ключи #N»`` (re-deliver keys, ``SubCB(action='keys')``) and
    ``«🛒 Продлить #N»`` (jump into the buy flow pre-pinned to that
    subscription, ``BuyCB(action='extend', sub_id=N)``). The «Продлить»
    button is shown **only for active subscriptions** because the
    subscription service rejects extending non-active rows;
  * a trailing ``«◀ В меню»`` row.

  When the user has no subscriptions at all the friendly «У вас пока
  нет подписки» screen is shown instead, with the same buy CTA.

* :func:`cb_resend_keys` — callback ``SubCB(action='keys', sub_id)``:
  re-deliver vless URI + QR + Subscription URL for the chosen
  subscription via the shared :func:`app.handlers.user._keys.deliver_keys`
  helper. Guards: ownership check (``sub.user_id == user.id``) so a
  crafted callback cannot dump someone else's keys.

Status / traffic line
---------------------

For every rendered card we hit
:func:`app.xui.clients.get_client_traffics` to pull live counters from
the panel. If the panel call fails (network blip, client deleted out of
band, etc.) we still render the DB-side info — the user always sees
status + expiry — and append a soft notice instead of crashing.

Days-left line
--------------

* ``active``  — ``«истекает через N дн.»`` (``N=0`` → «истекает сегодня»).
* ``expired`` — ``«истекла N дн. назад»`` (or «истекла сегодня»).
* Negative deltas are formatted using ``abs(delta)`` so the absolute
  number reads naturally.

Buy / extend entry points
-------------------------

The buy flow exposes two stateless callbacks
(:class:`BuyCB(action='extend', sub_id=N)` and
:class:`BuyCB(action='new')`) registered without an FSM state filter
specifically so the «Моя подписка» screen can route directly into the
plan picker — skipping the «продлить vs новая» action screen that the
main-menu «🛒 Купить» button shows when the user already has multiple
active subscriptions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from app.db.engine import get_conn
from app.db.repos import subscriptions as subs_repo
from app.db.repos.subscriptions import Subscription
from app.db.repos.users import User
from app.handlers.user._keys import deliver_keys
from app.keyboards.user import BuyCB, SubCB, UserCB
from app.xui import XuiError, get_xui_client
from app.xui.clients import get_client_traffics

router = Router(name="user_my_subscription")


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _format_bytes(value: int | float) -> str:
    """Return ``value`` rendered as a human-readable string.

    Uses binary units (1024 step) with a single decimal once we leave the
    ``B`` bucket — matching the convention used by 3x-ui itself in its
    web UI (so a user comparing values won't see a mismatch).

    Examples
    --------
    >>> _format_bytes(0)
    '0 B'
    >>> _format_bytes(1024)
    '1.0 KB'
    >>> _format_bytes(5 * 1024 ** 3)
    '5.0 GB'
    """
    n = float(max(0, int(value)))
    idx = 0
    while n >= 1024.0 and idx < len(_BYTE_UNITS) - 1:
        n /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(n)} {_BYTE_UNITS[idx]}"
    return f"{n:.1f} {_BYTE_UNITS[idx]}"


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string from the DB into a UTC-aware datetime.

    The repo serialises with ``sep=' '`` and seconds resolution, but we
    accept ``'T'`` too so ad-hoc rows from external tools still load.
    """
    text = value.replace(" ", "T") if " " in value and "T" not in value else value
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _days_delta(expires_at: str) -> int:
    """Return ``floor((expires_at - now).total_seconds() / 86400)``.

    Positive when the subscription is still valid, negative when it has
    already expired. We deliberately use ``//`` so "expires in 12 hours"
    rounds *down* to 0 (the user reads "истекает сегодня"), and
    "expired 6 hours ago" rounds *down* to ``-1`` (the user reads
    "истекла 1 день назад") — both are the friendlier framings.
    """
    now = datetime.now(UTC)
    delta = _parse_iso(expires_at) - now
    seconds = int(delta.total_seconds())
    # Python's `//` floors toward negative infinity which is exactly what
    # we want for the "истекла 1 день назад" rendering.
    return seconds // 86400


def _is_active(sub: Subscription) -> bool:
    """Return ``True`` iff ``status='active'`` AND ``expires_at`` is in the future."""
    if sub.status != "active":
        return False
    return _parse_iso(sub.expires_at) > datetime.now(UTC)


def _format_days_line(sub: Subscription) -> str:
    """Return the «осталось / истекла» line for a subscription."""
    days = _days_delta(sub.expires_at)
    if days > 0:
        return f"⏳ Истекает через {days} дн."
    if days == 0:
        # Edge: today is the expiry date.
        return "⏳ Истекает сегодня"
    # days < 0
    n = abs(days)
    if n == 0:
        return "⌛ Истекла сегодня"
    return f"⌛ Истекла {n} дн. назад"


def _format_status_line(sub: Subscription) -> str:
    """Return a translated status line.

    Combines the DB ``status`` with a "is currently valid" check so a row
    with ``status='active'`` whose ``expires_at`` is already in the past
    (the expire-job hasn't run yet — Phase 8) still reads as "истекла"
    to the user, instead of misleading "active".
    """
    if sub.status == "revoked":
        return "🚫 Статус: отозвана"
    if sub.status == "expired" or not _is_active(sub):
        return "❌ Статус: истекла"
    return "✅ Статус: активна"


async def _fetch_traffics(
    sub: Subscription,
) -> tuple[int | None, int | None, bool]:
    """Pull live traffic counters from the 3x-ui panel.

    Returns ``(up_bytes, down_bytes, ok)``:

    * ``ok=True``  — both counters came back from the panel.
    * ``ok=False`` — the panel call failed (``XuiError`` or unexpected
      shape). Counters are ``None`` and the caller renders a "не удалось
      получить" notice.

    Wrapped in a broad ``try / except`` against :class:`XuiError` so the
    "Моя подписка" screen always renders — even when the panel is down.
    """
    try:
        xui = await get_xui_client()
        info = await get_client_traffics(xui, sub.xui_client_email)
    except XuiError as exc:
        logger.warning(
            "my_sub: get_client_traffics({}) failed for sub={}: {}",
            sub.xui_client_email,
            sub.id,
            exc,
        )
        return None, None, False
    except Exception as exc:  # noqa: BLE001 — defensive: never crash the screen
        logger.warning(
            "my_sub: unexpected error fetching traffic for sub={}: {}",
            sub.id,
            exc,
        )
        return None, None, False

    if not info:
        # Panel returned ``success=true`` with ``obj=null`` — the client
        # row is gone (deleted manually in the panel). Render the card
        # without traffic and let the user re-purchase.
        return None, None, False

    up_raw = info.get("up", 0)
    down_raw = info.get("down", 0)
    try:
        up = int(up_raw)
        down = int(down_raw)
    except (TypeError, ValueError):
        return None, None, False
    return up, down, True


def _format_sub_card(sub: Subscription, traffic: tuple[int | None, int | None, bool]) -> str:
    """Build the HTML card body for a single subscription.

    The card has four lines: status, expiry timestamp, days-delta, and a
    traffic line that either renders live counters or falls back to a
    "панель недоступна" notice. We deliberately separate "the subscription
    exists" from "we could reach the panel" so a panel outage never hides
    the parts the bot already knows.
    """
    up, down, ok = traffic
    lines: list[str] = [
        f"<b>Подписка #{sub.id}</b>",
        _format_status_line(sub),
        f"📅 Истекает: <code>{sub.expires_at}</code> UTC",
        _format_days_line(sub),
    ]
    if ok and up is not None and down is not None:
        lines.append(
            f"📊 Трафик: ↑ {_format_bytes(up)} / ↓ {_format_bytes(down)}",
        )
    else:
        lines.append("📊 Трафик: не удалось получить (панель недоступна)")
    return "\n".join(lines)


_MAX_VISIBLE_SUBS = 5


def _sort_subs(subs: list[Subscription]) -> list[Subscription]:
    """Return ``subs`` sorted active-first.

    Order:

    * Active subscriptions (status ``active`` AND not yet expired) come
      first, sorted by ``expires_at`` DESC so the latest extension is
      at the top.
    * The remainder (``expired``, ``revoked``, or ``active`` rows whose
      ``expires_at`` is already in the past — the expire job hasn't run
      yet) follow, sorted by ``created_at`` DESC.

    Ties are broken by ``id`` DESC for determinism. The ordering is
    pinned by tests in
    :mod:`tests.test_handlers_user_my_subscription` so future
    sort-key tweaks need a matching test update.
    """
    active = [s for s in subs if _is_active(s)]
    inactive = [s for s in subs if not _is_active(s)]
    active.sort(key=lambda s: (s.expires_at, s.id), reverse=True)
    inactive.sort(key=lambda s: (s.created_at, s.id), reverse=True)
    return active + inactive


def _build_subs_keyboard(visible: list[Subscription]) -> InlineKeyboardBuilder:
    """Build the inline keyboard for the «Моя подписка» screen.

    Layout (top → bottom):

    1. ``🆕 Купить новую подписку`` (``BuyCB(action='new')``) — always
       rendered, even when every existing sub is expired. This is the
       canonical entry point into the buy flow with ``sub_id=0``.
    2. For each visible subscription — one row with
       ``🔑 Ключи #N`` (``SubCB(action='keys', sub_id=N)``) and, when
       the subscription is currently active, ``🛒 Продлить #N``
       (``BuyCB(action='extend', sub_id=N)``). For inactive subs the
       row contains only the keys button — ``cb_pick_action_extend``
       in :mod:`app.handlers.user.buy` rejects non-active rows.
    3. ``◀ В меню`` (``UserCB(area='menu')``) — back to the main menu.

    ``visible`` MUST already be capped to :data:`_MAX_VISIBLE_SUBS` by
    the caller — this helper does not enforce the cap so it can be
    reused for screens that paginate differently.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🆕 Купить новую подписку",
        callback_data=BuyCB(action="new"),
    )
    builder.adjust(1)
    for sub in visible:
        if _is_active(sub):
            builder.row(
                _btn(f"🔑 Ключи #{sub.id}", SubCB(action="keys", sub_id=sub.id)),
                _btn(f"🛒 Продлить #{sub.id}", BuyCB(action="extend", sub_id=sub.id)),
            )
        else:
            builder.row(
                _btn(f"🔑 Ключи #{sub.id}", SubCB(action="keys", sub_id=sub.id)),
            )
    builder.row(_btn("◀ В меню", UserCB(area="menu")))
    return builder


def _btn(text: str, cb):
    """Tiny helper: build an ``InlineKeyboardButton`` from a callback factory.

    ``InlineKeyboardBuilder.row(*buttons)`` expects already-constructed
    buttons, so we materialise them here instead of going through
    ``builder.button(...)`` (which appends to the implicit pending row).
    Centralising this keeps the keyboard composition in
    :func:`_build_subs_keyboard` compact and easy to audit.
    """
    from aiogram.types import InlineKeyboardButton

    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _no_subscription_kb() -> InlineKeyboardBuilder:
    """Keyboard shown when the user has no subscription history at all."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить подписку", callback_data=BuyCB(action="open"))
    builder.button(text="◀ В меню", callback_data=UserCB(area="menu"))
    builder.adjust(1)
    return builder


# --------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------- #


@router.callback_query(UserCB.filter(F.area == "my"))
async def cb_open_my(callback: CallbackQuery, user: User | None = None) -> None:
    """Render the "Моя подписка" screen — list of all subscriptions.

    Branches:

    1. **No user / no subscriptions ever** — show the "no subscription"
       screen with a single "Купить" CTA.
    2. **One or more subscriptions** — list per-subscription cards
       (active first, then expired/revoked) with per-sub action buttons
       in the keyboard. The card list is capped to
       :data:`_MAX_VISIBLE_SUBS` entries; when the user has more, a
       trailing ``«… и ещё N подписок»`` line indicates the remainder.
       The capped subset is also what the keyboard reflects, so the
       button count never exceeds Telegram's per-message limit.
    """
    if user is None:
        await callback.answer("Сначала нажмите /start.", show_alert=True)
        return

    async with get_conn() as conn:
        all_subs = await subs_repo.list_for_user(conn, user.id)

    if not all_subs:
        text = (
            "У вас пока нет подписки.\n\n"
            "Нажмите «Купить подписку», чтобы выбрать тариф и оплатить."
        )
        if callback.message is not None:
            await callback.message.edit_text(
                text,
                reply_markup=_no_subscription_kb().as_markup(),
            )
        await callback.answer()
        return

    ordered = _sort_subs(all_subs)
    visible = ordered[:_MAX_VISIBLE_SUBS]
    hidden_count = max(0, len(ordered) - _MAX_VISIBLE_SUBS)

    # Render one card per visible subscription. We fetch traffic per
    # sub so a healthy panel surfaces live counters for every line; if
    # the panel is down or a particular client is missing,
    # ``_fetch_traffics`` returns ``ok=False`` and ``_format_sub_card``
    # falls back to the soft notice. Cards are separated by a divider
    # line so the user can scan boundaries quickly even with hyphens
    # rendered in monospace by some clients.
    blocks: list[str] = []
    for sub in visible:
        traffic = await _fetch_traffics(sub)
        blocks.append(_format_sub_card(sub, traffic))
    body = "\n\n━━━━━━━━━━━━━━━\n\n".join(blocks)
    if hidden_count:
        body = (
            f"{body}\n\n"
            f"… и ещё {hidden_count} "
            f"{_pluralize_subs(hidden_count)}"
        )

    kb = _build_subs_keyboard(visible).as_markup()
    if callback.message is not None:
        await callback.message.edit_text(body, reply_markup=kb)
    await callback.answer()


def _pluralize_subs(n: int) -> str:
    """Return the Russian plural form for «подписка» given ``n``.

    Russian uses three plural forms: 1 / 2-4 / 5-20. ``n`` is the
    *displayed* count (always positive in our caller), so the function
    only needs to cover the three nominal buckets — there is no zero
    branch.
    """
    mod10 = n % 10
    mod100 = n % 100
    if mod10 == 1 and mod100 != 11:
        return "подписка"
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return "подписки"
    return "подписок"


@router.callback_query(SubCB.filter(F.action == "keys"))
async def cb_resend_keys(
    callback: CallbackQuery,
    callback_data: SubCB,
    bot: Bot,
    user: User | None = None,
) -> None:
    """Re-deliver vless / QR / subscription URL for the given subscription.

    Guards:

    * ``user`` must be present (set by :mod:`app.middlewares.user_ctx`).
    * ``sub.user_id == user.id`` — a crafted ``sub_id`` MUST NOT leak
      another user's keys.
    * Subscription must exist; otherwise we tell the user and stay on
      the same message.

    The actual delivery is delegated to
    :func:`app.handlers.user._keys.deliver_keys` (shared with
    :mod:`app.handlers.user.buy` and :mod:`app.handlers.user.promo`).
    """
    if user is None:
        await callback.answer("Сначала нажмите /start.", show_alert=True)
        return

    sub_id = callback_data.sub_id
    if not sub_id:
        await callback.answer("Подписка не указана.", show_alert=True)
        return

    async with get_conn() as conn:
        sub = await subs_repo.get(conn, sub_id)

    if sub is None or sub.user_id != user.id:
        # Same error message for "not found" and "not yours" — no
        # information leak.
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id is None:
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return

    xui = await get_xui_client()
    header = (
        "🔑 Ваши ключи доступа."
        if _is_active(sub)
        else "🔑 Ключи от истёкшей подписки (для копирования)."
    )
    try:
        await deliver_keys(bot, xui, chat_id=chat_id, sub=sub, header=header)
    except XuiError as exc:
        logger.warning(
            "my_sub: deliver_keys failed for sub={} user={}: {}",
            sub.id,
            user.id,
            exc,
        )
        await bot.send_message(
            chat_id,
            "Не удалось получить ключи: панель временно недоступна. "
            "Попробуйте позже.",
        )
    await callback.answer()


__all__ = ["router"]
