"""English locale catalog (full fallback translation).

``en`` is the :data:`app.i18n.FALLBACK_LANG`: every key present in
:mod:`app.i18n.locales.ru` MUST also exist here so a missing translation in any
other language degrades to English rather than to a raw key. The coverage test
in ``tests/test_i18n.py`` enforces RU ⊆ EN.
"""

from __future__ import annotations

MESSAGES: dict[str, str | dict[str, str]] = {
    # ----- menu.* ---------------------------------------------------------
    "menu.greeting": "Main menu. What would you like to do?",
    "menu.btn_my": "📦 My subscription",
    "menu.btn_buy": "🛒 Buy",
    "menu.btn_promo": "🎟 Activate promo code",
    "menu.btn_help": "❓ Help",
    "menu.btn_lang": "🌐 Язык / Language",
    "menu.btn_back": "◀ To menu",
    "menu.btn_cancel": "✖ Cancel",
    "menu.cancelled": "Cancelled",
    "menu.need_start": "Press /start first.",
    "menu.start_greeting": "Hi! This is the VPN subscription bot. Choose an action:",
    "menu.admin_greeting": "Admin menu. Choose a section:",
    "menu.btn_back_short": "◀ Back",

    # ----- kb.* (shared keyboard labels) ----------------------------------
    "kb.plan_label": "{title} · {days}d · {price}⭐",
    "kb.inbound_label": "{remark} (port {port})",
    "kb.inbound_fallback_remark": "Location #{id}",
    "kb.btn_pay": "💳 Pay",
    "kb.btn_apply_promo": "🎟 Apply promo code",
    "kb.btn_new_sub": "🆕 New subscription",
    "kb.btn_extend_sub": "🔄 Extend #{sub_id} · {remark}",
    "kb.btn_resend_key": "🔑 Get the key again",
    "kb.btn_cancel_back": "◀ Cancel",

    # ----- lang.* ---------------------------------------------------------
    "lang.choose": "🌐 Choose the interface language:",
    "lang.changed": "Language changed.",
    "lang.unsupported": "This language is not supported.",

    # ----- help.* ---------------------------------------------------------
    "help.text": (
        "<b>How to connect to the VPN</b>\n\n"
        "1️⃣ Install any client with VLESS/Reality support:\n"
        "• <b>v2rayNG</b> — Android (Play Market / GitHub)\n"
        "• <b>Streisand</b> — iOS / iPadOS (App Store)\n"
        "• <b>Hiddify</b> — Windows / macOS / Linux\n\n"
        "2️⃣ After payment the bot sends three key variants — use any:\n"
        "• <code>vless://</code> link — copy it, then tap "
        "«Import from clipboard» in the client.\n"
        "• Subscription URL — in the client tap «Add subscription», paste the "
        "link and refresh. Convenient because you never have to reconfigure on "
        "renewal.\n"
        "• QR code — tap «Scan QR code» (camera) in the client.\n\n"
        "3️⃣ Turn the connection on in the client — the status icon turns green.\n\n"
        "If something doesn't work — message the administrator."
    ),

    # ----- keys.* ---------------------------------------------------------
    "keys.header_active": "✅ Subscription is active.",
    "keys.valid_until": "Valid until: <code>{expires_at}</code> UTC",
    "keys.qr_caption": "📱 Scan the QR code in your client to add the connection.",
    "keys.sub_url_title": "<b>Subscription URL</b>\n<code>{sub_url}</code>",
    "keys.sub_url_unavailable": "<b>Subscription URL</b>\n<i>unavailable</i>",
    "keys.btn_sub_url": "🌐 Subscription URL",
    "keys.btn_resend": "🔑 Get the key again",

    # ----- mysub.* --------------------------------------------------------
    "mysub.subs_plural": {
        "one": "subscription",
        "other": "subscriptions",
    },
    "mysub.days_until": "⏳ Expires in {days} day(s).",
    "mysub.expires_today": "⏳ Expires today",
    "mysub.expired_today": "⌛ Expired today",
    "mysub.expired_ago": "⌛ Expired {days} day(s) ago",
    "mysub.status_revoked": "🚫 Status: revoked",
    "mysub.status_expired": "❌ Status: expired",
    "mysub.status_active": "✅ Status: active",
    "mysub.card_title": "<b>Subscription #{sub_id}</b>",
    "mysub.card_expires": "📅 Expires: <code>{expires_at}</code> UTC",
    "mysub.card_traffic": "📊 Traffic: ↑ {up} / ↓ {down}",
    "mysub.card_traffic_unavailable": "📊 Traffic: could not fetch (panel unavailable)",
    "mysub.more_footer": "… and {count} more {plural}",
    "mysub.no_subscription": (
        "You don't have a subscription yet.\n\n"
        "Tap «Buy subscription» to pick a plan and pay."
    ),
    "mysub.btn_buy_new": "🆕 Buy a new subscription",
    "mysub.btn_keys_n": "🔑 Keys #{sub_id}",
    "mysub.btn_extend_n": "🛒 Extend #{sub_id}",
    "mysub.btn_buy": "🛒 Buy subscription",
    "mysub.keys_header_active": "🔑 Your access keys.",
    "mysub.keys_header_expired": "🔑 Keys from the expired subscription (to copy).",
    "mysub.no_sub_specified": "No subscription specified.",
    "mysub.sub_not_found": "Subscription not found.",
    "mysub.chat_undetermined": "Could not determine the chat.",
    "mysub.keys_unavailable": (
        "Could not fetch the keys: the panel is temporarily unavailable. "
        "Try again later."
    ),

    # ----- promo.* --------------------------------------------------------
    "promo.enter_code": "Enter the promo code in a single message:",
    "promo.need_start": "Press /start to begin.",
    "promo.invalid_retry": "{error} Enter it again:",
    "promo.default_invalid": "The promo code is invalid.",
    "promo.only_on_purchase": (
        "This promo code applies only when buying a plan. "
        "Tap «Buy» in the menu and apply the code there."
    ),
    "promo.inbounds_unavailable": (
        "Could not fetch the list of connections. Try again later."
    ),
    "promo.no_inbounds": "No connections available. Try again later.",
    "promo.has_active_choose": "You have active subscriptions. Choose an action:",
    "promo.choose_inbound": "Choose a connection to activate the promo code:",
    "promo.no_longer_available": "The promo code is no longer available.",
    "promo.became_invalid": "The promo code has become invalid.",
    "promo.became_invalid_retry": "{error} Try another code.",
    "promo.apply_on_purchase": "This promo code must be applied when buying a plan.",
    "promo.activation_failed": (
        "Could not activate the promo code — try again later. "
        "If the problem persists, message the administrator."
    ),
    "promo.activated_alert": "Promo code activated.",
    "promo.header_extended": (
        "✅ Promo code <code>{code}</code> applied to subscription #{sub_id}."
    ),
    "promo.header_activated": "✅ Promo code <code>{code}</code> activated.",
    "promo.no_sub_specified": "No subscription specified.",
    "promo.session_expired": "Session expired. Enter the promo code again.",
    "promo.sub_unavailable_extend": "Subscription is not available for extension.",
    "promo.inbound_unavailable_pick": "Connection unavailable. Pick from the list.",

    # ----- buy.* ----------------------------------------------------------
    "buy.confirm_header_extend": "🔄 <b>Extend subscription #{sub_id}</b>",
    "buy.confirm_header_new": "🆕 <b>New subscription</b>",
    "buy.confirm_header_new_on": "🆕 <b>New subscription</b> on {remark}",
    "buy.confirm_header_extend_remark": "🔄 <b>Extend subscription #{sub_id}</b> · {remark}",
    "buy.confirm_plan": "<b>Plan:</b> {title}",
    "buy.confirm_term": "<b>Term:</b> {days} day(s)",
    "buy.confirm_term_bonus": "<b>Term:</b> {days} day(s) + {extra} bonus day(s)",
    "buy.confirm_valid_until": "<b>Valid until:</b> {date}",
    "buy.confirm_promo": "<b>Promo code:</b> <code>{code}</code>",
    "buy.confirm_discount_percent": "<b>Discount:</b> −{value}%",
    "buy.confirm_discount_flat": "<b>Discount:</b> −{value}⭐",
    "buy.confirm_bonus_days": "<b>Bonus:</b> +{value} day(s)",
    "buy.confirm_total": "<b>To pay:</b> {stars}⭐",
    "buy.has_active_choose": "You have active subscriptions. Choose an action:",
    "buy.no_plans": "No plans available right now. Check back later.",
    "buy.choose_plan": "Choose a plan:",
    "buy.need_start": "Press /start first.",
    "buy.no_sub_specified": "No subscription specified.",
    "buy.sub_unavailable_extend": "Subscription is not available for extension.",
    "buy.plan_unavailable": "Plan unavailable.",
    "buy.plan_no_inbounds": "The plan has no available connections. Contact the administrator.",
    "buy.inbounds_unavailable": "Could not fetch the list of connections. Try again later.",
    "buy.no_inbounds_for_plan": "No connections available for this plan.",
    "buy.choose_inbound": "Choose a connection (server):",
    "buy.inbound_unavailable_for_plan": "Connection unavailable for this plan.",
    "buy.enter_promo": "Enter the promo code in a single message:",
    "buy.need_start_full": "Press /start to begin.",
    "buy.plan_gone": "The plan is no longer available. Return to the menu.",
    "buy.promo_invalid_retry": "{error} Enter it again:",
    "buy.promo_default_invalid": "The promo code is invalid.",
    "buy.promo_applied": "✅ Promo code applied.\n\n",
    "buy.promo_became_invalid": "The promo code has become invalid, try again.",
    "buy.chat_undetermined": "Could not determine the chat.",
    "buy.inbound_unavailable_pick": "Connection unavailable for this plan. Pick another.",
    "buy.plan_no_inbounds_retry": (
        "The plan has no available connections right now. Try again later."
    ),
    "buy.precheckout_bad_order": "Invalid order.",
    "buy.precheckout_plan_gone": "The plan is no longer available.",
    "buy.precheckout_promo_invalid": "The promo code has become invalid.",
    "buy.precheckout_user_undetermined": "Could not determine the user.",
    "buy.precheckout_sub_unavailable": "Subscription is not available for extension.",
    "buy.precheckout_inbound_gone": "The connection is no longer available.",
    "buy.payment_unparseable": (
        "Payment received, but we could not parse the order. "
        "Contact support — we'll refund or activate the subscription manually."
    ),
    "buy.payment_plan_deleted": (
        "Payment received, but the plan was deleted. Message the administrator — we'll sort it out."
    ),
    "buy.payment_success_header": "✅ Payment succeeded. Subscription is active.",
    "buy.payment_provision_failed": (
        "Payment received, but we could not activate the key in the VPN panel. "
        "We recorded the payment and an administrator will activate the "
        "subscription manually shortly."
    ),

    # ----- admin.* --------------------------------------------------------
    "admin.greeting": "Admin menu. Choose a section:",
    "admin.cancelled_greeting": "Cancelled. Admin menu. Choose a section:",
    "admin.cancelled": "Cancelled",
    # admin keyboard labels (admin.kb.*)
    "admin.kb.plans": "📋 Plans",
    "admin.kb.promos": "🎟 Promo codes",
    "admin.kb.users": "👥 Users",
    "admin.kb.stats": "📊 Stats",
    "admin.kb.broadcast": "📣 Broadcast",
    "admin.kb.tickets": "💬 Tickets",
    "admin.kb.audit": "📜 Audit",
    "admin.kb.send": "✅ Send",
    "admin.kb.cancel": "✖ Cancel",
    "admin.kb.back": "◀ To menu",
    "admin.kb.back_short": "◀ Back",
    "admin.kb.plan_label": "{marker}{title} · {days}d · {price}⭐",
    "admin.kb.create_plan": "➕ Create plan",
    "admin.kb.edit": "✏ Edit",
    "admin.kb.deactivate": "🚫 Deactivate",
    "admin.kb.field_title": "Title",
    "admin.kb.field_days": "Term (days)",
    "admin.kb.field_price": "Price (⭐)",
    "admin.kb.field_traffic": "Traffic limit (GB)",
    "admin.kb.field_inbounds": "🔌 Connections",
    "admin.kb.inbound_label": "{marker} {remark} (port {port})",
    "admin.kb.done": "✅ Done",
    "admin.kb.manual": "✏ Enter manually",
    "admin.kb.preset_days": "{value} days",
    "admin.kb.preset_price": "{value} ⭐",
    "admin.kb.preset_gb_unlimited": "0 (unlimited)",
    "admin.kb.preset_gb": "{value} GB",
    "admin.kb.create_promo": "➕ Create promo code",
    "admin.kb.promo_label": "{marker}{code} · {type}:{value}",
    "admin.kb.type_percent": "% (percent)",
    "admin.kb.type_flat": "⭐ flat_stars",
    "admin.kb.type_free": "📆 free_days",
    "admin.kb.preset_percent": "{value}%",
    "admin.kb.preset_days_short": "{value} days",
    "admin.kb.preset_max_unlimited": "0 (∞)",
    "admin.kb.preset_plain": "{value}",
    "admin.kb.preset_expires_never": "no expiry",
    "admin.kb.preset_expires_days": "+{value}d",
    "admin.kb.redemptions": "👀 Redemptions",
    "admin.kb.revoke_sub": "🚫 Revoke active subscription",
    "admin.kb.unset_admin": "🛡 Remove admin",
    "admin.kb.set_admin": "🛡 Make admin",
    "admin.kb.grant_sub": "🎁 Grant subscription",
    "admin.kb.block_user": "🚫 Block",
    "admin.kb.unblock_user": "🟢 Unblock",
    "admin.kb.find_another": "🔎 Find another",
    "admin.kb.period_7d": "Last 7 days",
    "admin.kb.period_30d": "Last 30 days",
    "admin.kb.period_all": "All time",
    "admin.kb.period_active": "· {text} ·",
    "admin.kb.refresh": "🔄 Refresh",

    # ----- wallet.* -------------------------------------------------------
    "wallet.invoice_title": "Balance top-up",
    "wallet.invoice_label": "Wallet top-up",
    "wallet.invoice_description": "Top up the balance by {stars}⭐.",
    "wallet.topup_success": (
        "✅ Balance topped up by {stars}⭐.\n"
        "Current balance: {balance}⭐."
    ),
    "wallet.btn_open": "👛 Wallet",
    "wallet.screen_title": "<b>👛 Wallet</b>",
    "wallet.balance_line": "Balance: <b>{balance}⭐</b>",
    "wallet.history_title": "<b>Recent transactions:</b>",
    "wallet.history_empty": "No transactions yet.",
    "wallet.history_row": "{sign}{amount}⭐ · {label}",
    "wallet.topup_prompt": "Choose a top-up amount:",
    "wallet.btn_topup_preset": "➕ {stars}⭐",
    "wallet.btn_topup": "➕ Top up",
    "wallet.no_presets": "Top-up is temporarily unavailable.",
    "wallet.type_topup": "Top-up",
    "wallet.type_spend": "Subscription payment",
    "wallet.type_refund": "Refund",
    "wallet.type_referral_bonus": "Referral bonus",
    "wallet.type_admin_grant": "Admin grant",
    "wallet.type_payment": "Payment",
    "wallet.pay_from_balance": "💰 Pay from balance",
    "wallet.insufficient": "Insufficient wallet balance.",
    "wallet.paid_from_balance_header": "✅ Paid from balance. Subscription is active.",
    "wallet.pay_failed": (
        "Could not pay from balance — try again or pay with Stars."
    ),

    # ----- reminder.* -----------------------------------------------------
    "reminder.3d": (
        "⏳ Your VPN subscription expires in 3 days.\n"
        "Open «My subscription» and renew it so you don't lose access."
    ),
    "reminder.1d": (
        "⏳ Your VPN subscription expires tomorrow.\n"
        "Renew it via the «My subscription» menu to avoid an interruption."
    ),
    "reminder.0d": (
        "⚠️ Your VPN subscription expires today.\n"
        "Renew it right now, otherwise access will be turned off automatically."
    ),
    "reminder.expired": (
        "❌ Your VPN subscription has expired, access is temporarily off.\n"
        "To keep using the service, renew it via the «Buy subscription» menu."
    ),
    "reminder.btn_renew": "🔁 Renew in 1 tap",

    # ----- traffic.* (traffic-quota alerts) -------------------------------
    "traffic.alert": (
        "📊 You've used {percent}% of the traffic on subscription #{sub_id}.\n"
        "Once the quota runs out, access will be limited. Renew this "
        "subscription or buy a new one to stay connected."
    ),

    # ----- autorenew.* (auto-renewal) -------------------------------------
    "autorenew.btn_subscribe": "🔁 Subscription (auto-renew)",
    "autorenew.subscribe_prompt": (
        "🔁 Set up auto-renewal — Telegram will renew your subscription "
        "automatically every 30 days until you cancel it.\n"
        "Tap the button below to subscribe."
    ),
    "autorenew.btn_cancel": "⏹ Cancel auto-renewal",
    "autorenew.btn_enable": "🔁 Enable auto-renewal",
    "autorenew.cancelled": "⏹ Auto-renewal cancelled.",
    "autorenew.enabled": "🔁 Auto-renewal enabled.",
    "autorenew.cancel_failed": "Couldn't change auto-renewal. Please try again later.",
    "autorenew.renewed_dm": (
        "🔁 Subscription #{sub_id} was renewed automatically for {stars}⭐ "
        "from your balance.\nValid until {date}."
    ),
    "autorenew.insufficient_dm": (
        "⚠️ Couldn't auto-renew subscription #{sub_id}: your balance is short "
        "by {stars}⭐. Top up your wallet or renew the subscription manually."
    ),

    # ----- trial.* --------------------------------------------------------
    "trial.btn": "🎁 Free trial",
    "trial.need_start": "Please press /start to begin.",
    "trial.disabled": "The free trial is not available right now.",
    "trial.already_used": "You have already used your free trial.",
    "trial.choose_inbound": "Choose a connection for the free trial:",
    "trial.inbounds_unavailable": (
        "Couldn't fetch the list of connections. Please try again later."
    ),
    "trial.no_inbounds": "No connections available. Please try again later.",
    "trial.activation_failed": (
        "Couldn't activate the free trial. Please try again later."
    ),
    "trial.header_activated": "🎁 Your {days}-day free trial is now active!",

    # ----- referral.* -----------------------------------------------------
    "referral.btn": "👥 Invite a friend",
    "referral.need_start": "Please press /start to begin.",
    "referral.screen_title": "<b>👥 Invite a friend</b>",
    "referral.screen_body": (
        "Share your link with friends. After their first payment you'll get "
        "<b>{stars}⭐</b> on your balance."
    ),
    "referral.screen_body_no_bonus": (
        "Share your link with friends to invite them to the service."
    ),
    "referral.link_line": "Your link:\n<code>{link}</code>",
    "referral.count_line": "Friends invited: <b>{count}</b>",
    "referral.reward_dm": (
        "🎉 Your friend bought their first subscription — you've been credited "
        "{stars}⭐!"
    ),

    # ----- gift.* ---------------------------------------------------------
    "gift.btn_buy": "🎁 Gift a subscription",
    "gift.btn_redeem": "🎁 I have a gift",
    "gift.need_start": "Please press /start to begin.",
    "gift.minted_dm": (
        "🎁 Your gift code is ready!\n\n"
        "Code: <code>{code}</code>\n"
        "Activation link:\n<code>{link}</code>\n\n"
        "Send it to whoever you'd like to give the subscription to."
    ),
    "gift.enter_code": "Send the gift code in a single message:",
    "gift.code_not_found": "Gift code not found.",
    "gift.code_not_active": "This gift code has already been used or is invalid.",
    "gift.redeem_failed": "Couldn't activate the gift. Please try again later.",
    "gift.redeemed_header": "🎁 Your gift subscription is now active!",
    "gift.buyer_notified_dm": (
        "🎁 Your gift code <code>{code}</code> was activated by the recipient!"
    ),

    # ----- blocked.* ------------------------------------------------------
    "blocked.refused": "🚫 Access to the bot is blocked.",

    # ----- support.* (tickets) --------------------------------------------
    "support.btn": "❓ Support",
    "support.need_start": "Please press /start first.",
    "support.intro": (
        "💬 <b>Support</b>\n\n"
        "Describe your issue in a single message — we'll forward it to support "
        "and reply right here in this chat."
    ),
    "support.prompt": "Type your message to support:",
    "support.empty": "The message can't be empty. Please type something:",
    "support.sent": (
        "✅ Your message was sent to support (ticket #{ticket_id}). "
        "We'll reply here."
    ),
    "support.reply_received": (
        "💬 <b>Support reply</b> (ticket #{ticket_id}):\n\n{text}"
    ),
    "support.closed_notice": (
        "✅ Ticket #{ticket_id} was closed. If you still need help, write again."
    ),
    "support.admin_notify": (
        "💬 <b>New ticket #{ticket_id}</b>\n"
        "From: {user}\n\n{text}"
    ),
    "support.failed": "Couldn't send your message. Please try again later.",

    # ----- admin.tickets.* ------------------------------------------------
    "admin.tickets.title": "💬 <b>Open tickets</b>",
    "admin.tickets.empty": "No open tickets.",
    "admin.tickets.list_item": "#{ticket_id} · {status} · from {user} · {updated_at}",
    "admin.tickets.not_found": "Ticket not found.",
    "admin.tickets.card_header": (
        "💬 <b>Ticket #{ticket_id}</b>\n"
        "User: {user}\n"
        "Status: {status}\n"
    ),
    "admin.tickets.history_title": "<b>Conversation:</b>",
    "admin.tickets.msg_user": "👤 {text}",
    "admin.tickets.msg_admin": "🛟 {text}",
    "admin.tickets.btn_reply": "✍ Reply",
    "admin.tickets.btn_close": "✅ Close ticket",
    "admin.tickets.btn_back": "◀ To list",
    "admin.tickets.reply_prompt": "Type your reply to the user (ticket #{ticket_id}):",
    "admin.tickets.reply_empty": "The reply can't be empty. Please type something:",
    "admin.tickets.reply_sent": "✅ Reply sent to the user.",
    "admin.tickets.reply_failed": (
        "Reply saved, but couldn't be delivered to the user "
        "(they may have blocked the bot)."
    ),
    "admin.tickets.closed": "✅ Ticket #{ticket_id} closed.",
    "admin.tickets.status_open": "🟡 open",
    "admin.tickets.status_answered": "🟢 answered",
    "admin.tickets.status_closed": "⚪ closed",

    # ----- admin.grant.* (manual subscription grant) ----------------------
    "admin.grant.choose_plan": (
        "🎁 <b>Grant subscription</b>\n\nChoose a plan (term is taken from the "
        "plan, or set a custom one on the next step):"
    ),
    "admin.grant.no_plans": "No plans available to grant.",
    "admin.grant.enter_days": (
        "Enter the number of days as a number "
        "(or '-' to use the plan's term of {days}d):"
    ),
    "admin.grant.bad_days": "Enter a positive number of days or '-':",
    "admin.grant.plan_not_found": "Plan not found.",
    "admin.grant.success": (
        "✅ Subscription granted to {user}: {days}d "
        "(subscription #{sub_id}, until {expires_at} UTC)."
    ),
    "admin.grant.user_notified": (
        "🎁 An administrator granted you a {days}-day subscription!"
    ),
    "admin.grant.failed": "Couldn't grant the subscription: {error}",

    # ----- admin.ban.* ----------------------------------------------------
    "admin.ban.blocked": "🚫 User blocked.",
    "admin.ban.unblocked": "🟢 User unblocked.",
    "admin.ban.self": "You can't block yourself.",
    "admin.ban.cannot_block_admin": "You can't block an administrator.",

    # ----- admin.audit.* --------------------------------------------------
    "admin.audit.title": "📜 <b>Admin action audit</b>",
    "admin.audit.empty": "No records yet.",
    "admin.audit.item": "{created_at} · {admin} · <b>{action}</b>{target}{details}",
    "admin.audit.btn_prev": "◀ Back",
    "admin.audit.btn_next": "Next ▶",
    "admin.audit.btn_back": "◀ To menu",

    # ----- health.* (panel health-check alerts) ---------------------------
    "health.alert_down": (
        "🔴 <b>The 3x-ui panel is unreachable!</b>\n\n"
        "The health-check could not reach the panel.\n"
        "Reason: <code>{error}</code>\n\n"
        "New subscriptions may fail to provision — check the server."
    ),
    "health.alert_up": (
        "🟢 <b>The 3x-ui panel is reachable again.</b>\n\n"
        "Connectivity to the panel has been restored; service is back to normal."
    ),
    "health.status_up": "🟢 online",
    "health.status_down": "🔴 unreachable",
    "health.status_unknown": "⚪ no data",

    # ----- location.* (inbound availability indicator) --------------------
    "location.indicator_up": "🟢",
    "location.indicator_down": "🔴",
    "location.label": "{indicator} {remark}",
    "location.label_with_port": "{indicator} {remark} (port {port})",

    # ----- admin.export.* (CSV statistics export) -------------------------
    "admin.export.btn": "📥 Download CSV",
    "admin.export.caption_payments": "💳 Payments ({rows} rows)",
    "admin.export.caption_subscriptions": "🔑 Subscriptions ({rows} rows)",
    "admin.export.caption_users": "👥 Users ({rows} rows)",
    "admin.export.done": "📥 Export sent as files.",
    "admin.export.failed": "Could not build the export. Please try again later.",

    # ----- keys.howto.* (client deep-link import guides) ------------------
    "keys.howto.title": "<b>📲 How to connect</b>",
    "keys.howto.intro": (
        "Copy the import link for your client and open it, or paste the "
        "Subscription URL manually:"
    ),
    "keys.howto.happ": (
        "<b>Happ (iOS / Android / Windows / macOS) — recommended:</b>\n"
        "<code>{link}</code>\n"
        "If the link doesn't open — in Happ tap «+» → «Add subscription» and "
        "paste the Subscription URL:\n<code>{sub_url}</code>"
    ),
    "keys.howto.v2rayng": (
        "<b>v2RayNG / v2RayTun (Android):</b>\n<code>{link}</code>"
    ),
    "keys.howto.hiddify": (
        "<b>Hiddify (Android/iOS/Desktop):</b>\n<code>{link}</code>"
    ),
    "keys.howto.streisand": (
        "<b>Streisand (iOS):</b>\n<code>{link}</code>"
    ),
    "keys.howto.manual": (
        "If the link doesn't open — copy the Subscription URL and add the "
        "subscription manually via 'Import from clipboard'."
    ),
    "keys.howto.btn": "📲 How to connect",
}


__all__ = ["MESSAGES"]
