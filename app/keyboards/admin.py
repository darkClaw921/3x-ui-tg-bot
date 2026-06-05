"""Inline keyboards for the admin flow.

Every keyboard is a thin builder around :class:`InlineKeyboardBuilder` and
returns a ready-to-send :class:`InlineKeyboardMarkup`. Callback payloads are
encoded via :class:`aiogram.filters.callback_data.CallbackData` factories
declared at the top of this module — that keeps the wire format short
(<=64 bytes, Telegram's hard limit) and gives handlers a typed view of the
payload through the ``F`` filter and ``callback_data: AdminCB`` arg.

Callback namespaces
-------------------

* ``AdminCB`` — coarse navigation buttons (``area=main|plans|promos|users|stats``
  with ``action`` like ``open``, ``back``, ``cancel``).
* ``PlanCB`` — plan CRUD (``action=list|create|card|edit|deactivate``,
  optional ``id`` and ``field``).
* ``PromoCB`` — promo CRUD (``action=list|create|card|deactivate|redemptions|type``,
  optional ``id`` and ``type``).
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repos.plans import Plan
from app.db.repos.promos import Promo
from app.i18n import DEFAULT_LANG, t
from app.services.inbounds import InboundOption


# ---------------------------------------------------------------------------
# Callback factories
# ---------------------------------------------------------------------------


class AdminCB(CallbackData, prefix="adm"):
    """Top-level admin navigation: open an area / go back / cancel.

    The ``broadcast`` area additionally uses ``action="send"`` to confirm
    the post fan-out from the confirmation screen (see
    :func:`broadcast_confirm_kb` and :mod:`app.handlers.admin.broadcast`).
    """

    area: str  # main | plans | promos | users | stats | broadcast | tickets | audit
    action: str  # open | back | cancel | send


class PlanCB(CallbackData, prefix="admp"):
    """Plan CRUD callbacks.

    ``action``:
    * ``list``           — show plan list (no ``id``).
    * ``create``         — start :class:`PlanCreate` FSM (no ``id``).
    * ``card``           — open a plan card.
    * ``edit_menu``      — open the «choose field to edit» keyboard.
    * ``edit``           — start :class:`PlanEdit` FSM for a specific field
      (``field`` = ``title``/``days``/``price_stars``/``traffic_gb``/
      ``inbounds``).
    * ``deactivate``     — soft-disable the plan.
    * ``preset``         — preset button inside the create-plan wizard
      (``field`` = ``days``/``price``/``gb``; ``id`` carries the chosen
      integer value).
    * ``manual``         — «введу вручную» button inside the create-plan
      wizard (``field`` = ``days``/``price``/``gb``).
    * ``toggle_inbound`` — flip the selection of one inbound inside the
      multi-select screen (``id`` carries the ``inbound_id``).
    * ``inbounds_done``  — confirm the inbound multi-select and proceed
      (no ``id``; used both in the create wizard and in the edit flow).
    """

    action: str
    id: int = 0
    field: str = ""  # title | days | price_stars | traffic_gb | inbounds (edit); days|price|gb (preset/manual)


class UserCB(CallbackData, prefix="admu"):
    """Admin "Пользователи" callbacks.

    ``action``:
    * ``search``       — start :class:`AdminSearchUser` (no ``id``).
    * ``card``         — open the user card by ``users.id``.
    * ``revoke``       — revoke a subscription; ``id`` is the
      ``subscriptions.id``, ``user_id`` is the parent user (so the
      handler can re-render the card after the revoke).
    * ``toggle_admin`` — flip the ``is_admin`` flag; ``id`` is
      ``users.id``.
    * ``grant_sub``    — start :class:`app.states.admin.AdminGrantSub` to
      manually grant / extend a subscription; ``id`` is ``users.id``.
    * ``toggle_block`` — flip the ``is_blocked`` flag (ban / unban);
      ``id`` is ``users.id``.
    """

    action: str
    id: int = 0
    user_id: int = 0


class GrantCB(CallbackData, prefix="admg"):
    """Manual subscription-grant callbacks (admin «🎁 Выдать подписку» flow).

    ``action``:
    * ``plan`` — the admin picked a plan to grant (``plan_id``). Used inside
      :class:`app.states.admin.AdminGrantSub.waiting_plan` so it does not
      collide with the plan-management :class:`PlanCB` ``card`` callback.
    """

    action: str  # plan
    plan_id: int = 0


class TicketCB(CallbackData, prefix="admt"):
    """Admin support-ticket callbacks («💬 Тикеты»).

    ``action``:
    * ``list``  — render the open-ticket list.
    * ``card``  — open a ticket card by ``id`` (``tickets.id``) with its
      transcript.
    * ``reply`` — start :class:`app.states.admin.AdminTicketReply` to type a
      reply to ticket ``id``.
    * ``close`` — close ticket ``id`` (terminal).
    """

    action: str  # list | card | reply | close
    id: int = 0


class AuditCB(CallbackData, prefix="adma"):
    """Admin audit-log callbacks («📜 Аудит»).

    ``action``:
    * ``open`` — render the audit page at ``page`` (0-based).
    """

    action: str  # open
    page: int = 0


class StatsCB(CallbackData, prefix="adms"):
    """Admin "Статистика" callbacks.

    ``action``:
    * ``open``    — render the stats screen with the default 30-day
      window.
    * ``period``  — switch the headline period. ``field`` carries the
      window key (``7d`` / ``30d`` / ``all``).
    * ``refresh`` — re-render with the currently selected period
      (carried in ``field`` for stateless edits).
    * ``export``  — dump the core tables as CSV documents. ``field``
      carries the dataset selector (``all`` exports payments,
      subscriptions and users).
    """

    action: str
    field: str = ""


class PromoCB(CallbackData, prefix="admpr"):
    """Promo CRUD callbacks.

    ``action``:
    * ``list``        — show promo list (no ``id``).
    * ``create``      — start :class:`PromoCreate` FSM (no ``id``).
    * ``card``        — open a promo card.
    * ``deactivate``  — soft-disable the promo (sets ``expires_at=now``).
    * ``redemptions`` — show redemption history for a promo.
    * ``type``        — chosen during FSM ``waiting_type`` (``field`` carries
      ``percent|flat_stars|free_days``).
    * ``preset``      — preset button inside the create-promo wizard
      (``field`` = ``value``/``max_uses``/``expires``; ``id`` carries the
      chosen integer; for ``expires`` it is the number of days from now,
      with ``0`` meaning «бессрочно»).
    * ``manual``      — «введу вручную» button inside the create-promo
      wizard (``field`` = ``value``/``max_uses``/``expires``).
    """

    action: str
    id: int = 0
    field: str = ""


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------


def admin_main_menu(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Top-level admin menu shown by ``/admin``.

    Seven buttons (one per row for readability on mobile): Plans, Promos,
    Users, Stats, Broadcast, Tickets, Audit.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("admin.kb.plans", lang), callback_data=AdminCB(area="plans", action="open"))
    builder.button(text=t("admin.kb.promos", lang), callback_data=AdminCB(area="promos", action="open"))
    builder.button(text=t("admin.kb.users", lang), callback_data=AdminCB(area="users", action="open"))
    builder.button(text=t("admin.kb.stats", lang), callback_data=AdminCB(area="stats", action="open"))
    builder.button(text=t("admin.kb.broadcast", lang), callback_data=AdminCB(area="broadcast", action="open"))
    builder.button(text=t("admin.kb.tickets", lang), callback_data=AdminCB(area="tickets", action="open"))
    builder.button(text=t("admin.kb.audit", lang), callback_data=AdminCB(area="audit", action="open"))
    builder.adjust(1)
    return builder.as_markup()


def broadcast_confirm_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Confirmation keyboard for the broadcast wizard.

    «✅ Разослать» fires :class:`AdminCB` ``area=broadcast, action=send``
    (handled in :mod:`app.handlers.admin.broadcast` under the
    ``BroadcastCreate.confirming`` state); «✖ Отмена» reuses the canonical
    cancel callback so the shared :func:`cancel_fsm` handler clears state.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("admin.kb.send", lang),
        callback_data=AdminCB(area="broadcast", action="send"),
    )
    builder.button(
        text=t("admin.kb.cancel", lang),
        callback_data=AdminCB(area="main", action="cancel"),
    )
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Single «◀ В меню» button — used as a fallback footer keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    return builder.as_markup()


def cancel_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Single «✖ Отмена» button used during any FSM wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    return builder.as_markup()


# ---------------- Plans ----------------


def plans_list_kb(plans: Sequence[Plan], lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Plan list: one button per plan plus «Создать» and «В меню».

    Inactive plans get a leading ``🔒`` so admins still see them but
    recognise their state at a glance.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        marker = "" if plan.is_active else "🔒 "
        label = t(
            "admin.kb.plan_label",
            lang,
            marker=marker,
            title=plan.title,
            days=plan.days,
            price=plan.price_stars,
        )
        builder.button(
            text=label,
            callback_data=PlanCB(action="card", id=plan.id),
        )
    builder.button(text=t("admin.kb.create_plan", lang), callback_data=PlanCB(action="create"))
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


def plan_card_kb(
    plan_id: int, *, is_active: bool = True, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Plan card: Edit / Deactivate / Back. Hides Deactivate if already off."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("admin.kb.edit", lang),
        callback_data=PlanCB(action="edit_menu", id=plan_id),
    )
    if is_active:
        builder.button(
            text=t("admin.kb.deactivate", lang),
            callback_data=PlanCB(action="deactivate", id=plan_id),
        )
    builder.button(text=t("admin.kb.back_short", lang), callback_data=PlanCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def plan_edit_fields_kb(plan_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Choose which plan field to edit (title / days / price / traffic_gb / inbounds)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("admin.kb.field_title", lang),
        callback_data=PlanCB(action="edit", id=plan_id, field="title"),
    )
    builder.button(
        text=t("admin.kb.field_days", lang),
        callback_data=PlanCB(action="edit", id=plan_id, field="days"),
    )
    builder.button(
        text=t("admin.kb.field_price", lang),
        callback_data=PlanCB(action="edit", id=plan_id, field="price_stars"),
    )
    builder.button(
        text=t("admin.kb.field_traffic", lang),
        callback_data=PlanCB(action="edit", id=plan_id, field="traffic_gb"),
    )
    builder.button(
        text=t("admin.kb.field_inbounds", lang),
        callback_data=PlanCB(action="edit", id=plan_id, field="inbounds"),
    )
    builder.button(text=t("admin.kb.back_short", lang), callback_data=PlanCB(action="card", id=plan_id))
    builder.adjust(1)
    return builder.as_markup()


def plan_inbounds_select_kb(
    options: Sequence[InboundOption],
    selected: set[int],
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Multi-select keyboard over the available xui inbounds for a plan.

    Used by both :class:`PlanCreate` (step ``waiting_inbounds``) and the
    ``field='inbounds'`` branch of the plan-edit flow.

    Each row corresponds to one inbound and is prefixed with ``☑`` when
    its id is present in ``selected`` and ``☐`` otherwise; tapping the
    row sends ``PlanCB(action='toggle_inbound', id=inbound_id)`` which
    the handler uses to flip the selection in FSM data. An inbound whose
    panel ``remark`` is empty falls back to ``Локация #<id>`` so the admin
    never sees a blank label.

    Two trailing rows close the screen: «✅ Готово»
    (:class:`PlanCB` ``action='inbounds_done'``) confirms the choice;
    «✖ Отмена» (:class:`AdminCB` ``area='main'`` / ``action='cancel'``)
    aborts the wizard — the latter reuses the universal admin cancel
    callback to share routing logic with the other wizards.
    """
    builder = InlineKeyboardBuilder()
    for option in options:
        marker = "☑" if option.id in selected else "☐"
        remark = option.remark or t("kb.inbound_fallback_remark", lang, id=option.id)
        builder.button(
            text=t(
                "admin.kb.inbound_label",
                lang,
                marker=marker,
                remark=remark,
                port=option.port,
            ),
            callback_data=PlanCB(action="toggle_inbound", id=option.id),
        )
    builder.button(text=t("admin.kb.done", lang), callback_data=PlanCB(action="inbounds_done"))
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Plan wizard presets ----------------


def _plan_preset_kb(
    field: str, values: Sequence[int], labels: Sequence[str], lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Build a preset keyboard for one of the create-plan wizard steps.

    Each preset button carries ``PlanCB(action="preset", field=<field>,
    id=<value>)``; the «✏ Ввести вручную» button switches back to text
    input via ``PlanCB(action="manual", field=<field>)``; finally a
    universal cancel button drops the wizard.
    """
    builder = InlineKeyboardBuilder()
    for value, label in zip(values, labels, strict=True):
        builder.button(
            text=label,
            callback_data=PlanCB(action="preset", field=field, id=value),
        )
    builder.button(
        text=t("admin.kb.manual", lang),
        callback_data=PlanCB(action="manual", field=field),
    )
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    # 3 presets per row + manual/cancel on their own rows for a compact mobile layout.
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()


def plan_days_presets_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset days for ``PlanCreate.waiting_days``: 7/14/30/90/180/365."""
    values = [7, 14, 30, 90, 180, 365]
    labels = [t("admin.kb.preset_days", lang, value=v) for v in values]
    return _plan_preset_kb("days", values, labels, lang)


def plan_price_presets_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset prices for ``PlanCreate.waiting_price``: 0/50/100/200/500/1000."""
    values = [0, 50, 100, 200, 500, 1000]
    labels = [t("admin.kb.preset_price", lang, value=v) for v in values]
    return _plan_preset_kb("price", values, labels, lang)


def plan_gb_presets_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset traffic limits for ``PlanCreate.waiting_traffic_gb``.

    ``0`` means «без лимита» (matches xui ``totalGB`` semantics); the
    rest are common per-client monthly quotas.
    """
    values = [0, 10, 50, 100, 250, 500]
    labels = [
        t("admin.kb.preset_gb_unlimited", lang)
        if v == 0
        else t("admin.kb.preset_gb", lang, value=v)
        for v in values
    ]
    return _plan_preset_kb("gb", values, labels, lang)


# ---------------- Promos ----------------


def promos_list_kb(promos: Sequence[Promo], lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Promo list: one button per promo plus «Создать» and «В меню»."""
    builder = InlineKeyboardBuilder()
    for promo in promos:
        # All promos in this list are considered viewable; we mark already-
        # exhausted ones with 🔒 (used_count >= max_uses, max_uses>0).
        exhausted = promo.max_uses != 0 and promo.used_count >= promo.max_uses
        marker = "🔒 " if exhausted else ""
        builder.button(
            text=t(
                "admin.kb.promo_label",
                lang,
                marker=marker,
                code=promo.code,
                type=promo.type,
                value=promo.value,
            ),
            callback_data=PromoCB(action="card", id=promo.id),
        )
    builder.button(text=t("admin.kb.create_promo", lang), callback_data=PromoCB(action="create"))
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


def promo_type_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Three buttons used during ``PromoCreate.waiting_type``."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("admin.kb.type_percent", lang),
        callback_data=PromoCB(action="type", field="percent"),
    )
    builder.button(
        text=t("admin.kb.type_flat", lang),
        callback_data=PromoCB(action="type", field="flat_stars"),
    )
    builder.button(
        text=t("admin.kb.type_free", lang),
        callback_data=PromoCB(action="type", field="free_days"),
    )
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Promo wizard presets ----------------


def _promo_preset_kb(
    field: str,
    values: Sequence[int],
    labels: Sequence[str],
    *,
    adjust: Sequence[int] = (3, 2, 1, 1),
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Build a preset keyboard for one of the create-promo wizard steps.

    Each preset button carries ``PromoCB(action="preset", field=<field>,
    id=<value>)``; the «✏ Ввести вручную» button switches to text input
    via ``PromoCB(action="manual", field=<field>)``; finally a universal
    cancel button drops the wizard.
    """
    builder = InlineKeyboardBuilder()
    for value, label in zip(values, labels, strict=True):
        builder.button(
            text=label,
            callback_data=PromoCB(action="preset", field=field, id=value),
        )
    builder.button(
        text=t("admin.kb.manual", lang),
        callback_data=PromoCB(action="manual", field=field),
    )
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(*adjust)
    return builder.as_markup()


def promo_value_presets_kb(promo_type: str, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset values for ``PromoCreate.waiting_value``, parameterised by type.

    * ``percent``    — 5/10/15/25/50%
    * ``flat_stars`` — 25/50/100/250/500 ⭐
    * ``free_days``  — 1/3/7/14/30 дней

    Unknown types fall back to a manual-only keyboard (no presets) so the
    handler can still recover via the «Ввести вручную» button.
    """
    if promo_type == "percent":
        values = [5, 10, 15, 25, 50]
        labels = [t("admin.kb.preset_percent", lang, value=v) for v in values]
    elif promo_type == "flat_stars":
        values = [25, 50, 100, 250, 500]
        labels = [t("admin.kb.preset_price", lang, value=v) for v in values]
    elif promo_type == "free_days":
        values = [1, 3, 7, 14, 30]
        labels = [t("admin.kb.preset_days_short", lang, value=v) for v in values]
    else:
        values = []
        labels = []
    return _promo_preset_kb("value", values, labels, adjust=(3, 2, 1, 1), lang=lang)


def promo_max_uses_presets_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset max_uses for ``PromoCreate.waiting_max_uses``.

    ``0`` means «без лимита» (matches DB semantics — see
    :class:`~app.db.repos.promos.Promo`).
    """
    values = [0, 1, 5, 10, 50, 100]
    labels = [
        t("admin.kb.preset_max_unlimited", lang)
        if v == 0
        else t("admin.kb.preset_plain", lang, value=v)
        for v in values
    ]
    return _promo_preset_kb("max_uses", values, labels, adjust=(3, 3, 1, 1), lang=lang)


def promo_expires_presets_kb(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Preset expires_at for ``PromoCreate.waiting_expires_at``.

    The callback id carries the number of days from «сейчас»: ``0`` means
    «бессрочно» (``expires_at=None``), the rest are converted by the
    handler to an ISO-8601 string ``now + N days`` in the same format as
    :func:`_parse_expires_at`.
    """
    values = [0, 7, 30, 90, 365]
    labels = [
        t("admin.kb.preset_expires_never", lang)
        if v == 0
        else t("admin.kb.preset_expires_days", lang, value=v)
        for v in values
    ]
    return _promo_preset_kb("expires", values, labels, adjust=(3, 2, 1, 1), lang=lang)


def promo_card_kb(
    promo_id: int, *, is_active: bool = True, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Promo card: Redemptions / Deactivate / Back."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("admin.kb.redemptions", lang),
        callback_data=PromoCB(action="redemptions", id=promo_id),
    )
    if is_active:
        builder.button(
            text=t("admin.kb.deactivate", lang),
            callback_data=PromoCB(action="deactivate", id=promo_id),
        )
    builder.button(text=t("admin.kb.back_short", lang), callback_data=PromoCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Users ----------------


def user_card_kb(
    user_id: int,
    *,
    active_sub_id: int | None = None,
    is_admin: bool = False,
    is_blocked: bool = False,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """User card actions: revoke sub, grant sub, toggle admin, block, back.

    ``active_sub_id`` is the id of the user's currently-active
    subscription (if any) — the "Отозвать" button is hidden when the
    user has nothing to revoke. ``is_admin`` flips the admin-toggle label
    between "Сделать админом" and "Снять админа"; ``is_blocked`` flips the
    block-toggle label between «🚫 Заблокировать» and «🟢 Разблокировать».

    The «🎁 Выдать подписку» button starts the manual-grant FSM
    (:class:`app.states.admin.AdminGrantSub`). The block toggle is hidden
    entirely when the card targets ``user_id == 0`` (the "not found"
    placeholder card).
    """
    builder = InlineKeyboardBuilder()
    if active_sub_id is not None:
        builder.button(
            text=t("admin.kb.revoke_sub", lang),
            callback_data=UserCB(
                action="revoke",
                id=active_sub_id,
                user_id=user_id,
            ),
        )
    if user_id:
        builder.button(
            text=t("admin.kb.grant_sub", lang),
            callback_data=UserCB(action="grant_sub", id=user_id),
        )
    toggle_label = (
        t("admin.kb.unset_admin", lang) if is_admin else t("admin.kb.set_admin", lang)
    )
    builder.button(
        text=toggle_label,
        callback_data=UserCB(action="toggle_admin", id=user_id),
    )
    if user_id:
        block_label = (
            t("admin.kb.unblock_user", lang)
            if is_blocked
            else t("admin.kb.block_user", lang)
        )
        builder.button(
            text=block_label,
            callback_data=UserCB(action="toggle_block", id=user_id),
        )
    builder.button(
        text=t("admin.kb.find_another", lang),
        callback_data=UserCB(action="search"),
    )
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Stats ----------------


def stats_kb(active_period: str = "30d", lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Stats screen footer: period switcher + refresh + back.

    Three period buttons (7д / 30д / Всё время). The currently-active
    one is prefixed with «· » so it reads as the selected option without
    needing a separate label layout. The Refresh button carries the
    current ``field`` so the handler can re-run the same window.
    """

    def _label(key: str, text: str) -> str:
        return t("admin.kb.period_active", lang, text=text) if key == active_period else text

    builder = InlineKeyboardBuilder()
    builder.button(
        text=_label("7d", t("admin.kb.period_7d", lang)),
        callback_data=StatsCB(action="period", field="7d"),
    )
    builder.button(
        text=_label("30d", t("admin.kb.period_30d", lang)),
        callback_data=StatsCB(action="period", field="30d"),
    )
    builder.button(
        text=_label("all", t("admin.kb.period_all", lang)),
        callback_data=StatsCB(action="period", field="all"),
    )
    builder.button(
        text=t("admin.kb.refresh", lang),
        callback_data=StatsCB(action="refresh", field=active_period),
    )
    builder.button(
        text=t("admin.export.btn", lang),
        callback_data=StatsCB(action="export", field="all"),
    )
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    builder.adjust(3, 1, 1, 1)
    return builder.as_markup()


# ---------------- Manual grant ----------------


def grant_plans_kb(plans: Sequence[Plan], lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Plan picker for the manual «🎁 Выдать подписку» flow.

    One button per active plan (``GrantCB(action='plan', plan_id=<id>)``) plus a
    trailing «✖ Отмена». Reuses the ``admin.kb.plan_label`` label format.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        label = t(
            "admin.kb.plan_label",
            lang,
            marker="",
            title=plan.title,
            days=plan.days,
            price=plan.price_stars,
        )
        builder.button(text=label, callback_data=GrantCB(action="plan", plan_id=plan.id))
    builder.button(text=t("admin.kb.cancel", lang), callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Tickets ----------------


def tickets_list_kb(
    tickets: Sequence[tuple[int, str]], lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Open-ticket list: one button per ticket + «◀ В меню».

    ``tickets`` is a sequence of ``(ticket_id, label)`` pairs (the handler
    pre-formats the label with status / user so this keyboard stays dumb).
    Tapping a row opens the ticket card (``TicketCB(action='card', id=<id>)``).
    """
    builder = InlineKeyboardBuilder()
    for ticket_id, label in tickets:
        builder.button(
            text=label,
            callback_data=TicketCB(action="card", id=int(ticket_id)),
        )
    builder.button(text=t("admin.kb.back", lang), callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


def ticket_card_kb(
    ticket_id: int, *, is_closed: bool = False, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Ticket card actions: reply / close / back to list.

    The «✍ Ответить» and «✅ Закрыть тикет» buttons are hidden once the ticket
    is closed (``is_closed``) — a closed ticket is read-only.
    """
    builder = InlineKeyboardBuilder()
    if not is_closed:
        builder.button(
            text=t("admin.tickets.btn_reply", lang),
            callback_data=TicketCB(action="reply", id=ticket_id),
        )
        builder.button(
            text=t("admin.tickets.btn_close", lang),
            callback_data=TicketCB(action="close", id=ticket_id),
        )
    builder.button(
        text=t("admin.tickets.btn_back", lang),
        callback_data=TicketCB(action="list"),
    )
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Audit ----------------


def audit_kb(
    *, page: int = 0, has_prev: bool = False, has_next: bool = False, lang: str = DEFAULT_LANG
) -> InlineKeyboardMarkup:
    """Audit-log footer: optional prev / next page buttons + «◀ В меню».

    Pagination buttons are shown only when there is a page to go to, so the
    first page with no overflow renders just the back button.
    """
    builder = InlineKeyboardBuilder()
    if has_prev:
        builder.button(
            text=t("admin.audit.btn_prev", lang),
            callback_data=AuditCB(action="open", page=max(0, page - 1)),
        )
    if has_next:
        builder.button(
            text=t("admin.audit.btn_next", lang),
            callback_data=AuditCB(action="open", page=page + 1),
        )
    builder.button(
        text=t("admin.audit.btn_back", lang),
        callback_data=AdminCB(area="main", action="back"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


__all__ = [
    "AdminCB",
    "AuditCB",
    "GrantCB",
    "PlanCB",
    "PromoCB",
    "StatsCB",
    "TicketCB",
    "UserCB",
    "admin_main_menu",
    "audit_kb",
    "back_to_main_kb",
    "broadcast_confirm_kb",
    "cancel_kb",
    "grant_plans_kb",
    "plan_card_kb",
    "plan_days_presets_kb",
    "plan_edit_fields_kb",
    "plan_gb_presets_kb",
    "plan_inbounds_select_kb",
    "plan_price_presets_kb",
    "plans_list_kb",
    "promo_card_kb",
    "promo_expires_presets_kb",
    "promo_max_uses_presets_kb",
    "promo_type_kb",
    "promo_value_presets_kb",
    "promos_list_kb",
    "stats_kb",
    "ticket_card_kb",
    "tickets_list_kb",
    "user_card_kb",
]
