"""End-to-end operational journeys: alerts, reminders, support, admin ops, i18n.

Same approach as the other ``test_e2e_*`` modules — multi-step journeys with
real DB assertions between steps, mocking only the Telegram Bot API and 3x-ui.

Covered journeys:

* **I. Traffic alert** — crossing the quota threshold sends one alert; the next
  snapshot does not duplicate it (dedup via ``subscription_notifications``).
* **J. Renewal reminder** — the reminders job sends a reminder carrying a
  one-tap «продлить» inline button for an active, soon-to-expire subscription.
* **K. Tickets (two-way chat)** — a user opens a ticket (admins notified) → an
  admin replies (user receives it, status open→answered) → the transcript is
  persisted in the DB.
* **L. Admin grant + ban + audit** — an admin grants a subscription (provisioned
  + delivered + audited) and bans a user; the ``BlockedUserMiddleware`` then
  rejects that user's next update; both actions are in ``audit_log``.
* **M. Health-check** — panel down → admins alerted; recovery → admins alerted;
  a steady state does not re-alert.
* **N. CSV export** — the admin export sends one CSV document per dataset and the
  subscriptions CSV does not leak ``xui_client_uuid``.
* **O. i18n** — switching the language to ``en`` persists ``users.lang='en'`` and
  subsequent rendering returns the English string.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock


# --------------------------------------------------------------------------- #
# Shared helpers.
# --------------------------------------------------------------------------- #


def _state(data: dict | None = None):
    s = AsyncMock()
    s.get_data = AsyncMock(return_value=data or {})
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _admin_obj(user_id: int = 99, tg_id: int = 1):
    from app.db.repos.users import User

    return User(
        id=user_id, tg_id=tg_id, username="adm", first_name="Adm",
        is_admin=True, created_at="2025",
    )


def _paged_traffic(email: str, up: int, down: int):
    return {"items": [{"email": email, "traffic": {"up": up, "down": down}}], "total": 1}


# --------------------------------------------------------------------------- #
# I. Traffic alert fires once and dedups on the next snapshot.
# --------------------------------------------------------------------------- #


async def test_e2e_traffic_alert_fires_once_then_dedups(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app import scheduler as sch_module

    gb = 1024**3
    async with get_conn() as conn:
        user = await make_user(conn, tg_id=5)
        plan = await make_plan(conn, traffic_gb=1, inbound_ids=[1])
        await make_subscription(
            conn, user_id=user.id, plan_id=plan.id, xui_client_email="quota@x",
        )

    xui = AsyncMock()
    # 0.9 GB of a 1 GB quota → 90% ≥ TRAFFIC_ALERT_PERCENT.
    xui.request_json = AsyncMock(
        return_value=_paged_traffic("quota@x", up=int(0.5 * gb), down=int(0.4 * gb))
    )
    monkeypatch.setattr(sch_module, "get_xui_client", AsyncMock(return_value=xui))

    # --- First snapshot: one alert. ---
    await sch_module.traffic_snapshot_job(mock_bot)
    assert mock_bot.send_message.await_count == 1

    # --- Second snapshot: no duplicate alert (kind='traffic80' deduped). ---
    mock_bot.send_message.reset_mock()
    await sch_module.traffic_snapshot_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()


# --------------------------------------------------------------------------- #
# J. Reminder with a one-tap renewal button.
# --------------------------------------------------------------------------- #


async def test_e2e_reminder_carries_renew_button(
    file_db, make_user, make_subscription, mock_bot
):
    from app.db.engine import get_conn
    from app.keyboards.user import BuyCB
    from app import scheduler as sch_module

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=42)
        sub = await make_subscription(
            conn, user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=28),  # ~1d window
        )

    await sch_module.reminders_job(mock_bot)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    markup = kwargs["reply_markup"]
    assert markup is not None
    btn = markup.inline_keyboard[0][0]
    cb = BuyCB.unpack(btn.callback_data)
    assert cb.action == "extend"
    assert cb.sub_id == sub.id


# --------------------------------------------------------------------------- #
# K. Tickets — user opens, admin replies, status + transcript verified.
# --------------------------------------------------------------------------- #


async def test_e2e_ticket_open_admin_reply_roundtrip(
    file_db, make_user, monkey_settings
):
    from app.db.engine import get_conn
    from app.db.repos import tickets as tickets_repo
    from app.db.repos import users as users_repo
    from app.handlers.admin import tickets as admin_tickets
    from app.handlers.user import support as user_support

    # Make the seeded admin (tg_id=1) the only notification target.
    monkey_settings(ADMIN_IDS=[1], SUPPORT_CHAT_ID=0)

    async with get_conn() as conn:
        await users_repo.create(conn, tg_id=1, username="adm",
                                first_name="Adm", is_admin=True)
        owner = await make_user(conn, tg_id=555, username="joe", first_name="Joe")

    # --- Step 1: user opens a ticket (sends a support message). ---
    bot = AsyncMock()
    state = _state()
    msg = MagicMock()
    msg.text = "my vpn is down"
    msg.message_id = 11
    msg.answer = AsyncMock()
    await user_support.st_message(msg, state, bot, user=owner, lang="ru")

    # Admin(s) notified + a ticket persisted as 'open'.
    assert bot.send_message.await_count >= 1
    assert bot.send_message.await_args_list[0].args[0] == 1  # admin tg_id
    async with get_conn() as conn:
        open_tickets = await tickets_repo.list_open(conn)
    assert len(open_tickets) == 1
    ticket = open_tickets[0]
    assert ticket.status == "open"

    # --- Step 2: admin replies → user receives it; status flips to answered. ---
    async with get_conn() as conn:
        admin = await users_repo.get_by_tg_id(conn, 1)
    reply_bot = AsyncMock()
    reply_state = _state({"reply_ticket_id": ticket.id})
    reply_msg = MagicMock()
    reply_msg.text = "we restarted the node, try now"
    reply_msg.message_id = 12
    reply_msg.answer = AsyncMock()
    await admin_tickets.st_reply(reply_msg, reply_state, reply_bot,
                                 user=admin, lang="ru")

    # The reply was delivered to the ticket owner.
    assert reply_bot.send_message.await_count == 1
    assert reply_bot.send_message.await_args.args[0] == owner.tg_id

    # --- Step 3: DB — status answered + full transcript persisted. ---
    async with get_conn() as conn:
        refreshed = await tickets_repo.get(conn, ticket.id)
        msgs = await tickets_repo.list_messages(conn, ticket.id)
    assert refreshed.status == "answered"
    senders = [(m.sender, m.text) for m in msgs]
    assert ("user", "my vpn is down") in senders
    assert ("admin", "we restarted the node, try now") in senders


# --------------------------------------------------------------------------- #
# L. Admin grant + ban + audit, then BlockedUserMiddleware enforces the ban.
# --------------------------------------------------------------------------- #


async def test_e2e_admin_grant_then_ban_then_blocked(
    file_db, make_user, make_plan, monkey_settings, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo
    from app.db.repos import subscriptions as subs_repo
    from app.db.repos import users as users_repo
    from app.handlers.admin import users as admin_users
    from app.keyboards.admin import GrantCB, UserCB
    from app.middlewares.blocked import BlockedUserMiddleware

    monkey_settings(ADMIN_IDS=[1])
    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)
        target = await make_user(conn, tg_id=700)
        plan = await make_plan(conn, days=30, inbound_ids=[7])

    xui = AsyncMock()
    xui.request_json = AsyncMock(return_value={"id": "u", "email": "e"})
    monkeypatch.setattr(admin_users, "get_xui_client", AsyncMock(return_value=xui))
    monkeypatch.setattr(admin_users, "deliver_keys", AsyncMock())

    # --- Step 1: admin opens grant wizard → picks plan → enters term. ---
    cb_open = MagicMock()
    cb_open.message = MagicMock()
    cb_open.message.edit_text = AsyncMock()
    cb_open.answer = AsyncMock()
    state = _state()
    await admin_users.cb_grant_open(
        cb_open, UserCB(action="grant_sub", id=target.id), state, lang="ru"
    )
    grant_data = state.update_data.await_args.kwargs
    assert grant_data["grant_user_id"] == target.id

    cb_plan = MagicMock()
    cb_plan.message = MagicMock()
    cb_plan.message.edit_text = AsyncMock()
    cb_plan.answer = AsyncMock()
    state2 = _state({"grant_user_id": target.id})
    await admin_users.cb_grant_plan(
        cb_plan, GrantCB(action="plan", plan_id=plan.id), state2, lang="ru"
    )
    inbound_id = state2.update_data.await_args.kwargs["grant_inbound_id"]

    bot = AsyncMock()
    days_msg = MagicMock()
    days_msg.text = "-"  # use the plan's default term
    days_msg.answer = AsyncMock()
    grant_state = _state({
        "grant_user_id": target.id, "grant_plan_id": plan.id,
        "grant_inbound_id": inbound_id,
    })
    await admin_users.st_grant_days(days_msg, grant_state, bot,
                                    user=admin, lang="ru")

    async with get_conn() as conn:
        subs = await subs_repo.list_for_user(conn, target.id)
        audit = await audit_repo.list_recent(conn, limit=20)
    assert len(subs) == 1 and subs[0].plan_id == plan.id
    assert any(a.action == "user.grant_sub" for a in audit)
    admin_users.deliver_keys.assert_awaited()  # keys delivered to the target

    # --- Step 2: admin bans the target. ---
    cb_block = MagicMock()
    cb_block.message = MagicMock()
    cb_block.message.edit_text = AsyncMock()
    cb_block.answer = AsyncMock()
    await admin_users.cb_toggle_block(
        cb_block, UserCB(action="toggle_block", id=target.id),
        user=admin, lang="ru",
    )
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, target.id)
        audit = await audit_repo.list_recent(conn, limit=20)
    assert refreshed.is_blocked is True
    assert any(a.action == "user.block" for a in audit)

    # --- Step 3: BlockedUserMiddleware now drops the banned user's update. ---
    from aiogram.types import CallbackQuery, Update
    from aiogram.types import User as TgUser

    mw = BlockedUserMiddleware()
    downstream = AsyncMock(return_value="handled")

    # A real-shaped Update carrying a callback from the banned user (tg_id=700).
    # ``_extract_tg_user`` only walks fields on an ``isinstance(event, Update)``
    # object, so we spec the mocks to satisfy that check.
    upd = MagicMock(spec=Update)
    for attr in (
        "message", "edited_message", "channel_post", "edited_channel_post",
        "callback_query", "inline_query", "chosen_inline_result",
        "shipping_query", "pre_checkout_query", "poll_answer",
        "my_chat_member", "chat_member", "chat_join_request",
    ):
        setattr(upd, attr, None)
    inner_cb = MagicMock(spec=CallbackQuery)
    inner_cb.from_user = MagicMock(spec=TgUser, id=700)
    inner_cb.answer = AsyncMock()
    upd.callback_query = inner_cb

    res = await mw(downstream, upd, {})
    downstream.assert_not_awaited()  # handler never invoked for a banned user
    inner_cb.answer.assert_awaited()  # refusal alert shown
    assert res is None


# --------------------------------------------------------------------------- #
# M. Health-check transitions: down alerts, recovery alerts, steady is silent.
# --------------------------------------------------------------------------- #


async def test_e2e_health_check_down_up_transitions(
    file_db, mock_bot, monkeypatch, monkey_settings
):
    from app.db.engine import get_conn
    from app.db.repos import health as health_repo
    from app import scheduler as sch_module

    monkey_settings(ADMIN_IDS=[1, 2], SUPPORT_CHAT_ID=0)

    def _probe(result):
        monkeypatch.setattr(
            sch_module, "get_xui_client", AsyncMock(return_value=AsyncMock())
        )
        monkeypatch.setattr(
            sch_module.health_service, "check_xui_health",
            AsyncMock(return_value=result),
        )

    # --- Seed a steady 'up' baseline (first up alerts, second is steady). ---
    _probe((True, None))
    await sch_module.health_check_job(mock_bot)
    mock_bot.send_message.reset_mock()
    await sch_module.health_check_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()  # steady up — no spam

    # --- Panel goes DOWN → one alert per admin. ---
    _probe((False, "panel unreachable"))
    await sch_module.health_check_job(mock_bot)
    assert mock_bot.send_message.await_count == 2  # ADMIN_IDS = {1, 2}
    bodies = [c.args[1] for c in mock_bot.send_message.await_args_list]
    assert all("panel unreachable" in b for b in bodies)
    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row.status == "down"

    # --- Steady DOWN → no further alert. ---
    mock_bot.send_message.reset_mock()
    await sch_module.health_check_job(mock_bot)
    mock_bot.send_message.assert_not_awaited()

    # --- Recovery UP → one alert per admin. ---
    _probe((True, None))
    mock_bot.send_message.reset_mock()
    await sch_module.health_check_job(mock_bot)
    assert mock_bot.send_message.await_count == 2
    async with get_conn() as conn:
        row = await health_repo.get(conn)
    assert row.status == "up"


# --------------------------------------------------------------------------- #
# N. CSV export — three documents; subscriptions CSV hides xui_client_uuid.
# --------------------------------------------------------------------------- #


async def test_e2e_csv_export_documents_and_no_uuid_leak(
    file_db, make_user, make_plan, make_subscription, mock_bot, monkeypatch
):
    from app.db.engine import get_conn
    from app.db.repos import audit as audit_repo
    from app.handlers.admin import stats as stats_mod
    from app.keyboards.admin import StatsCB
    from aiogram.types import BufferedInputFile

    async with get_conn() as conn:
        admin = await make_user(conn, tg_id=1, is_admin=True)
        plan = await make_plan(conn, inbound_ids=[1])
        await make_subscription(
            conn, user_id=admin.id, plan_id=plan.id,
            xui_client_uuid="secret-uuid-xyz",
        )

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.chat.id = 4242
    cb.answer = AsyncMock()
    bot = AsyncMock()
    bot.send_document = AsyncMock()

    await stats_mod.cb_export(
        cb, StatsCB(action="export", field="all"), bot, user=admin, lang="ru"
    )

    # Three CSV documents (payments / subscriptions / users) to the admin chat.
    assert bot.send_document.await_count == 3
    docs: dict[str, bytes] = {}
    for call in bot.send_document.await_args_list:
        assert call.args[0] == 4242
        doc = call.kwargs["document"]
        assert isinstance(doc, BufferedInputFile)
        assert doc.filename.endswith(".csv")
        docs[doc.filename.split("-")[0]] = doc.data

    # The subscriptions CSV must be parseable and must NOT leak the panel UUID.
    subs_csv = docs["subscriptions"].decode("utf-8")
    rows = list(csv.reader(io.StringIO(subs_csv)))
    assert len(rows) >= 1  # at least a header row
    header = rows[0]
    assert "xui_client_uuid" not in header
    assert "secret-uuid-xyz" not in subs_csv

    # One audit entry recorded for the export.
    async with get_conn() as conn:
        entries = await audit_repo.list_recent(conn, limit=10)
    assert any(e.action == "stats.export" for e in entries)


# --------------------------------------------------------------------------- #
# O. i18n — switch to English persists users.lang and renders English copy.
# --------------------------------------------------------------------------- #


async def test_e2e_language_switch_persists_and_renders_english(
    file_db, make_user
):
    from app.db.engine import get_conn
    from app.db.repos import users as users_repo
    from app.handlers.user import language as lang_module
    from app.i18n import t
    from app.keyboards.user import LangCB

    async with get_conn() as conn:
        user = await make_user(conn, tg_id=800)
    assert user.lang == "ru"  # default

    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    await lang_module.cb_set(
        cb, LangCB(action="set", lang="en"), user=user, lang="ru"
    )

    # DB: the language flipped to English.
    async with get_conn() as conn:
        refreshed = await users_repo.get_by_id(conn, user.id)
    assert refreshed.lang == "en"

    # Subsequent rendering in the stored language is English, not Russian.
    rendered = t("menu.start_greeting", refreshed.lang)
    assert rendered == t("menu.start_greeting", "en")
    assert rendered != t("menu.start_greeting", "ru")
