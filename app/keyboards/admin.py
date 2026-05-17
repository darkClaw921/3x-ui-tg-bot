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
from app.services.inbounds import InboundOption


# ---------------------------------------------------------------------------
# Callback factories
# ---------------------------------------------------------------------------


class AdminCB(CallbackData, prefix="adm"):
    """Top-level admin navigation: open an area / go back / cancel."""

    area: str  # main | plans | promos | users | stats
    action: str  # open | back | cancel


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
    """

    action: str
    id: int = 0
    user_id: int = 0


class StatsCB(CallbackData, prefix="adms"):
    """Admin "Статистика" callbacks.

    ``action``:
    * ``open``    — render the stats screen with the default 30-day
      window.
    * ``period``  — switch the headline period. ``field`` carries the
      window key (``7d`` / ``30d`` / ``all``).
    * ``refresh`` — re-render with the currently selected period
      (carried in ``field`` for stateless edits).
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


def admin_main_menu() -> InlineKeyboardMarkup:
    """Top-level admin menu shown by ``/admin``.

    Four buttons (one per row for readability on mobile): Plans, Promos,
    Users, Stats. The latter two are implemented in Phase 7 — buttons are
    here from day one so the layout stays stable.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Тарифы", callback_data=AdminCB(area="plans", action="open"))
    builder.button(text="🎟 Промокоды", callback_data=AdminCB(area="promos", action="open"))
    builder.button(text="👥 Пользователи", callback_data=AdminCB(area="users", action="open"))
    builder.button(text="📊 Статистика", callback_data=AdminCB(area="stats", action="open"))
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    """Single «◀ В меню» button — used as a fallback footer keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ В меню", callback_data=AdminCB(area="main", action="back"))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Single «✖ Отмена» button used during any FSM wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✖ Отмена", callback_data=AdminCB(area="main", action="cancel"))
    return builder.as_markup()


# ---------------- Plans ----------------


def plans_list_kb(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    """Plan list: one button per plan plus «Создать» and «В меню».

    Inactive plans get a leading ``🔒`` so admins still see them but
    recognise their state at a glance.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        marker = "" if plan.is_active else "🔒 "
        label = f"{marker}{plan.title} · {plan.days}д · {plan.price_stars}⭐"
        builder.button(
            text=label,
            callback_data=PlanCB(action="card", id=plan.id),
        )
    builder.button(text="➕ Создать тариф", callback_data=PlanCB(action="create"))
    builder.button(text="◀ В меню", callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


def plan_card_kb(plan_id: int, *, is_active: bool = True) -> InlineKeyboardMarkup:
    """Plan card: Edit / Deactivate / Back. Hides Deactivate if already off."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏ Редактировать",
        callback_data=PlanCB(action="edit_menu", id=plan_id),
    )
    if is_active:
        builder.button(
            text="🚫 Деактивировать",
            callback_data=PlanCB(action="deactivate", id=plan_id),
        )
    builder.button(text="◀ Назад", callback_data=PlanCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def plan_edit_fields_kb(plan_id: int) -> InlineKeyboardMarkup:
    """Choose which plan field to edit (title / days / price / traffic_gb / inbounds)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Название",
        callback_data=PlanCB(action="edit", id=plan_id, field="title"),
    )
    builder.button(
        text="Срок (дней)",
        callback_data=PlanCB(action="edit", id=plan_id, field="days"),
    )
    builder.button(
        text="Цена (⭐)",
        callback_data=PlanCB(action="edit", id=plan_id, field="price_stars"),
    )
    builder.button(
        text="Лимит трафика (ГБ)",
        callback_data=PlanCB(action="edit", id=plan_id, field="traffic_gb"),
    )
    builder.button(
        text="🔌 Подключения",
        callback_data=PlanCB(action="edit", id=plan_id, field="inbounds"),
    )
    builder.button(text="◀ Назад", callback_data=PlanCB(action="card", id=plan_id))
    builder.adjust(1)
    return builder.as_markup()


def plan_inbounds_select_kb(
    options: Sequence[InboundOption],
    selected: set[int],
) -> InlineKeyboardMarkup:
    """Multi-select keyboard over the available xui inbounds for a plan.

    Used by both :class:`PlanCreate` (step ``waiting_inbounds``) and the
    ``field='inbounds'`` branch of the plan-edit flow.

    Each row corresponds to one inbound and is prefixed with ``☑`` when
    its id is present in ``selected`` and ``☐`` otherwise; tapping the
    row sends ``PlanCB(action='toggle_inbound', id=inbound_id)`` which
    the handler uses to flip the selection in FSM data.

    Two trailing rows close the screen: «✅ Готово»
    (:class:`PlanCB` ``action='inbounds_done'``) confirms the choice;
    «✖ Отмена» (:class:`AdminCB` ``area='main'`` / ``action='cancel'``)
    aborts the wizard — the latter reuses the universal admin cancel
    callback to share routing logic with the other wizards.
    """
    builder = InlineKeyboardBuilder()
    for option in options:
        marker = "☑" if option.id in selected else "☐"
        builder.button(
            text=f"{marker} {option.remark} (port {option.port})",
            callback_data=PlanCB(action="toggle_inbound", id=option.id),
        )
    builder.button(text="✅ Готово", callback_data=PlanCB(action="inbounds_done"))
    builder.button(text="✖ Отмена", callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Plan wizard presets ----------------


def _plan_preset_kb(field: str, values: Sequence[int], labels: Sequence[str]) -> InlineKeyboardMarkup:
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
        text="✏ Ввести вручную",
        callback_data=PlanCB(action="manual", field=field),
    )
    builder.button(text="✖ Отмена", callback_data=AdminCB(area="main", action="cancel"))
    # 3 presets per row + manual/cancel on their own rows for a compact mobile layout.
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()


def plan_days_presets_kb() -> InlineKeyboardMarkup:
    """Preset days for ``PlanCreate.waiting_days``: 7/14/30/90/180/365."""
    values = [7, 14, 30, 90, 180, 365]
    labels = [f"{v} дней" for v in values]
    return _plan_preset_kb("days", values, labels)


def plan_price_presets_kb() -> InlineKeyboardMarkup:
    """Preset prices for ``PlanCreate.waiting_price``: 0/50/100/200/500/1000."""
    values = [0, 50, 100, 200, 500, 1000]
    labels = [f"{v} ⭐" for v in values]
    return _plan_preset_kb("price", values, labels)


def plan_gb_presets_kb() -> InlineKeyboardMarkup:
    """Preset traffic limits for ``PlanCreate.waiting_traffic_gb``.

    ``0`` means «без лимита» (matches xui ``totalGB`` semantics); the
    rest are common per-client monthly quotas.
    """
    values = [0, 10, 50, 100, 250, 500]
    labels = ["0 (без лимита)", "10 ГБ", "50 ГБ", "100 ГБ", "250 ГБ", "500 ГБ"]
    return _plan_preset_kb("gb", values, labels)


# ---------------- Promos ----------------


def promos_list_kb(promos: Sequence[Promo]) -> InlineKeyboardMarkup:
    """Promo list: one button per promo plus «Создать» and «В меню»."""
    builder = InlineKeyboardBuilder()
    for promo in promos:
        # All promos in this list are considered viewable; we mark already-
        # exhausted ones with 🔒 (used_count >= max_uses, max_uses>0).
        exhausted = promo.max_uses != 0 and promo.used_count >= promo.max_uses
        marker = "🔒 " if exhausted else ""
        builder.button(
            text=f"{marker}{promo.code} · {promo.type}:{promo.value}",
            callback_data=PromoCB(action="card", id=promo.id),
        )
    builder.button(text="➕ Создать промокод", callback_data=PromoCB(action="create"))
    builder.button(text="◀ В меню", callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


def promo_type_kb() -> InlineKeyboardMarkup:
    """Three buttons used during ``PromoCreate.waiting_type``."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="% (percent)",
        callback_data=PromoCB(action="type", field="percent"),
    )
    builder.button(
        text="⭐ flat_stars",
        callback_data=PromoCB(action="type", field="flat_stars"),
    )
    builder.button(
        text="📆 free_days",
        callback_data=PromoCB(action="type", field="free_days"),
    )
    builder.button(text="✖ Отмена", callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Promo wizard presets ----------------


def _promo_preset_kb(
    field: str,
    values: Sequence[int],
    labels: Sequence[str],
    *,
    adjust: Sequence[int] = (3, 2, 1, 1),
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
        text="✏ Ввести вручную",
        callback_data=PromoCB(action="manual", field=field),
    )
    builder.button(text="✖ Отмена", callback_data=AdminCB(area="main", action="cancel"))
    builder.adjust(*adjust)
    return builder.as_markup()


def promo_value_presets_kb(promo_type: str) -> InlineKeyboardMarkup:
    """Preset values for ``PromoCreate.waiting_value``, parameterised by type.

    * ``percent``    — 5/10/15/25/50%
    * ``flat_stars`` — 25/50/100/250/500 ⭐
    * ``free_days``  — 1/3/7/14/30 дней

    Unknown types fall back to a manual-only keyboard (no presets) so the
    handler can still recover via the «Ввести вручную» button.
    """
    if promo_type == "percent":
        values = [5, 10, 15, 25, 50]
        labels = [f"{v}%" for v in values]
    elif promo_type == "flat_stars":
        values = [25, 50, 100, 250, 500]
        labels = [f"{v} ⭐" for v in values]
    elif promo_type == "free_days":
        values = [1, 3, 7, 14, 30]
        labels = [f"{v} дней" for v in values]
    else:
        values = []
        labels = []
    return _promo_preset_kb("value", values, labels, adjust=(3, 2, 1, 1))


def promo_max_uses_presets_kb() -> InlineKeyboardMarkup:
    """Preset max_uses for ``PromoCreate.waiting_max_uses``.

    ``0`` means «без лимита» (matches DB semantics — see
    :class:`~app.db.repos.promos.Promo`).
    """
    values = [0, 1, 5, 10, 50, 100]
    labels = ["0 (∞)", "1", "5", "10", "50", "100"]
    return _promo_preset_kb("max_uses", values, labels, adjust=(3, 3, 1, 1))


def promo_expires_presets_kb() -> InlineKeyboardMarkup:
    """Preset expires_at for ``PromoCreate.waiting_expires_at``.

    The callback id carries the number of days from «сейчас»: ``0`` means
    «бессрочно» (``expires_at=None``), the rest are converted by the
    handler to an ISO-8601 string ``now + N days`` in the same format as
    :func:`_parse_expires_at`.
    """
    values = [0, 7, 30, 90, 365]
    labels = ["бессрочно", "+7д", "+30д", "+90д", "+365д"]
    return _promo_preset_kb("expires", values, labels, adjust=(3, 2, 1, 1))


def promo_card_kb(promo_id: int, *, is_active: bool = True) -> InlineKeyboardMarkup:
    """Promo card: Redemptions / Deactivate / Back."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="👀 Redemptions",
        callback_data=PromoCB(action="redemptions", id=promo_id),
    )
    if is_active:
        builder.button(
            text="🚫 Деактивировать",
            callback_data=PromoCB(action="deactivate", id=promo_id),
        )
    builder.button(text="◀ Назад", callback_data=PromoCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Users ----------------


def user_card_kb(
    user_id: int,
    *,
    active_sub_id: int | None = None,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """User card actions: revoke active sub, toggle admin, back to menu.

    ``active_sub_id`` is the id of the user's currently-active
    subscription (if any) — the "Отозвать" button is hidden when the
    user has nothing to revoke. ``is_admin`` flips the toggle label
    between "Сделать админом" and "Снять админа".
    """
    builder = InlineKeyboardBuilder()
    if active_sub_id is not None:
        builder.button(
            text="🚫 Отозвать активную подписку",
            callback_data=UserCB(
                action="revoke",
                id=active_sub_id,
                user_id=user_id,
            ),
        )
    toggle_label = "🛡 Снять админа" if is_admin else "🛡 Сделать админом"
    builder.button(
        text=toggle_label,
        callback_data=UserCB(action="toggle_admin", id=user_id),
    )
    builder.button(
        text="🔎 Найти другого",
        callback_data=UserCB(action="search"),
    )
    builder.button(text="◀ В меню", callback_data=AdminCB(area="main", action="back"))
    builder.adjust(1)
    return builder.as_markup()


# ---------------- Stats ----------------


def stats_kb(active_period: str = "30d") -> InlineKeyboardMarkup:
    """Stats screen footer: period switcher + refresh + back.

    Three period buttons (7д / 30д / Всё время). The currently-active
    one is prefixed with «· » so it reads as the selected option without
    needing a separate label layout. The Refresh button carries the
    current ``field`` so the handler can re-run the same window.
    """

    def _label(key: str, text: str) -> str:
        return f"· {text} ·" if key == active_period else text

    builder = InlineKeyboardBuilder()
    builder.button(
        text=_label("7d", "За 7 дней"),
        callback_data=StatsCB(action="period", field="7d"),
    )
    builder.button(
        text=_label("30d", "За 30 дней"),
        callback_data=StatsCB(action="period", field="30d"),
    )
    builder.button(
        text=_label("all", "За всё время"),
        callback_data=StatsCB(action="period", field="all"),
    )
    builder.button(
        text="🔄 Обновить",
        callback_data=StatsCB(action="refresh", field=active_period),
    )
    builder.button(text="◀ В меню", callback_data=AdminCB(area="main", action="back"))
    builder.adjust(3, 1, 1)
    return builder.as_markup()


__all__ = [
    "AdminCB",
    "PlanCB",
    "PromoCB",
    "StatsCB",
    "UserCB",
    "admin_main_menu",
    "back_to_main_kb",
    "cancel_kb",
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
    "user_card_kb",
]
