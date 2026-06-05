"""Russian locale catalog (source of truth).

All strings here are verbatim copies of the texts previously hard-coded in the
handlers and keyboards. Keeping them 1:1 guarantees the existing test-suite
(which asserts Russian substrings like «Админ», «активна», «истекла»,
«Купить», «истёкших», and the plural forms «подписка/подписки/подписок»)
stays green after the migration to :func:`app.i18n.t`.

Keys are namespaced ``<area>.<name>``. Plural-sensitive entries store a dict of
plural categories instead of a flat string (see :mod:`app.i18n.plural`).
"""

from __future__ import annotations

MESSAGES: dict[str, str | dict[str, str]] = {
    # ----- menu.* ---------------------------------------------------------
    "menu.greeting": "Главное меню. Что делаем?",
    "menu.btn_my": "📦 Моя подписка",
    "menu.btn_buy": "🛒 Купить",
    "menu.btn_promo": "🎟 Активировать промокод",
    "menu.btn_help": "❓ Помощь",
    "menu.btn_lang": "🌐 Язык / Language",
    "menu.btn_back": "◀ В меню",
    "menu.btn_cancel": "✖ Отмена",
    "menu.cancelled": "Отменено",
    "menu.need_start": "Сначала нажмите /start.",
    "menu.start_greeting": "Привет! Это бот VPN-подписок. Выберите действие:",
    "menu.admin_greeting": "Админ-меню. Выберите раздел:",
    "menu.btn_back_short": "◀ Назад",

    # ----- kb.* (shared keyboard labels) ----------------------------------
    "kb.plan_label": "{title} · {days}д · {price}⭐",
    "kb.inbound_label": "{remark} (port {port})",
    "kb.inbound_fallback_remark": "Локация #{id}",
    "kb.btn_pay": "💳 Оплатить",
    "kb.btn_apply_promo": "🎟 Применить промокод",
    "kb.btn_new_sub": "🆕 Новая подписка",
    "kb.btn_extend_sub": "🔄 Продлить #{sub_id} · {remark}",
    "kb.btn_resend_key": "🔑 Получить ключ ещё раз",
    "kb.btn_cancel_back": "◀ Отмена",

    # ----- lang.* ---------------------------------------------------------
    "lang.choose": "🌐 Выберите язык интерфейса:",
    "lang.changed": "Язык изменён.",
    "lang.unsupported": "Этот язык не поддерживается.",

    # ----- help.* ---------------------------------------------------------
    "help.text": (
        "<b>Как подключиться к VPN</b>\n\n"
        "1️⃣ Установите любой клиент с поддержкой VLESS/Reality:\n"
        "• <b>v2rayNG</b> — Android (Play Market / GitHub)\n"
        "• <b>Streisand</b> — iOS / iPadOS (App Store)\n"
        "• <b>Hiddify</b> — Windows / macOS / Linux\n\n"
        "2️⃣ После оплаты бот пришлёт три варианта ключа — используйте любой:\n"
        "• <code>vless://</code> ссылку — скопируйте, в клиенте нажмите "
        "«Импорт из буфера обмена».\n"
        "• Subscription URL — в клиенте «Добавить подписку», вставьте ссылку, "
        "обновите. Удобно тем, что при продлении ничего перенастраивать не "
        "нужно.\n"
        "• QR-код — в клиенте «Сканировать QR-код» (камера).\n\n"
        "3️⃣ Включите подключение в клиенте — иконка статуса станет зелёной.\n\n"
        "Если что-то не работает — напишите администратору."
    ),

    # ----- keys.* ---------------------------------------------------------
    "keys.header_active": "✅ Подписка активна.",
    "keys.valid_until": "Срок действия: <code>{expires_at}</code> UTC",
    "keys.qr_caption": "📱 Отсканируйте QR-код в клиенте, чтобы добавить подключение.",
    "keys.sub_url_title": "<b>Subscription URL</b>\n<code>{sub_url}</code>",
    "keys.sub_url_unavailable": "<b>Subscription URL</b>\n<i>недоступен</i>",
    "keys.btn_sub_url": "🌐 Subscription URL",
    "keys.btn_resend": "🔑 Получить ключ ещё раз",

    # ----- mysub.* --------------------------------------------------------
    "mysub.subs_plural": {
        "one": "подписка",
        "few": "подписки",
        "many": "подписок",
    },
    "mysub.days_until": "⏳ Истекает через {days} дн.",
    "mysub.expires_today": "⏳ Истекает сегодня",
    "mysub.expired_today": "⌛ Истекла сегодня",
    "mysub.expired_ago": "⌛ Истекла {days} дн. назад",
    "mysub.status_revoked": "🚫 Статус: отозвана",
    "mysub.status_expired": "❌ Статус: истекла",
    "mysub.status_active": "✅ Статус: активна",
    "mysub.card_title": "<b>Подписка #{sub_id}</b>",
    "mysub.card_expires": "📅 Истекает: <code>{expires_at}</code> UTC",
    "mysub.card_traffic": "📊 Трафик: ↑ {up} / ↓ {down}",
    "mysub.card_traffic_unavailable": "📊 Трафик: не удалось получить (панель недоступна)",
    "mysub.more_footer": "… и ещё {count} {plural}",
    "mysub.no_subscription": (
        "У вас пока нет подписки.\n\n"
        "Нажмите «Купить подписку», чтобы выбрать тариф и оплатить."
    ),
    "mysub.btn_buy_new": "🆕 Купить новую подписку",
    "mysub.btn_keys_n": "🔑 Ключи #{sub_id}",
    "mysub.btn_extend_n": "🛒 Продлить #{sub_id}",
    "mysub.btn_buy": "🛒 Купить подписку",
    "mysub.keys_header_active": "🔑 Ваши ключи доступа.",
    "mysub.keys_header_expired": "🔑 Ключи от истёкшей подписки (для копирования).",
    "mysub.no_sub_specified": "Подписка не указана.",
    "mysub.sub_not_found": "Подписка не найдена.",
    "mysub.chat_undetermined": "Не удалось определить чат.",
    "mysub.keys_unavailable": (
        "Не удалось получить ключи: панель временно недоступна. "
        "Попробуйте позже."
    ),

    # ----- promo.* --------------------------------------------------------
    "promo.enter_code": "Введите промокод одним сообщением:",
    "promo.need_start": "Нужно нажать /start, чтобы начать.",
    "promo.invalid_retry": "{error} Введите ещё раз:",
    "promo.default_invalid": "Промокод недействителен.",
    "promo.only_on_purchase": (
        "Этот промокод применяется только при покупке тарифа. "
        "Нажмите «Купить» в меню и примените код там."
    ),
    "promo.inbounds_unavailable": (
        "Не удалось получить список подключений. Попробуйте позже."
    ),
    "promo.no_inbounds": "Нет доступных подключений. Попробуйте позже.",
    "promo.has_active_choose": "У вас есть активные подписки. Выберите действие:",
    "promo.choose_inbound": "Выберите подключение для активации промокода:",
    "promo.no_longer_available": "Промокод больше недоступен.",
    "promo.became_invalid": "Промокод стал недействителен.",
    "promo.became_invalid_retry": "{error} Попробуйте другой код.",
    "promo.apply_on_purchase": "Этот промокод нужно применять при покупке тарифа.",
    "promo.activation_failed": (
        "Не удалось активировать промокод — попробуйте позже. "
        "Если проблема повторится, напишите администратору."
    ),
    "promo.activated_alert": "Промокод активирован.",
    "promo.header_extended": (
        "✅ Промокод <code>{code}</code> применён к подписке #{sub_id}."
    ),
    "promo.header_activated": "✅ Промокод <code>{code}</code> активирован.",
    "promo.no_sub_specified": "Подписка не указана.",
    "promo.session_expired": "Сессия устарела. Введите промокод заново.",
    "promo.sub_unavailable_extend": "Подписка недоступна для продления.",
    "promo.inbound_unavailable_pick": "Подключение недоступно. Выберите из списка.",

    # ----- buy.* ----------------------------------------------------------
    "buy.confirm_header_extend": "🔄 <b>Продление подписки #{sub_id}</b>",
    "buy.confirm_header_new": "🆕 <b>Новая подписка</b>",
    "buy.confirm_header_new_on": "🆕 <b>Новая подписка</b> на {remark}",
    "buy.confirm_header_extend_remark": "🔄 <b>Продление подписки #{sub_id}</b> · {remark}",
    "buy.confirm_plan": "<b>Тариф:</b> {title}",
    "buy.confirm_term": "<b>Срок:</b> {days} дн.",
    "buy.confirm_term_bonus": "<b>Срок:</b> {days} дн. + {extra} бонусных дн.",
    "buy.confirm_valid_until": "<b>Действует до:</b> {date}",
    "buy.confirm_promo": "<b>Промокод:</b> <code>{code}</code>",
    "buy.confirm_discount_percent": "<b>Скидка:</b> −{value}%",
    "buy.confirm_discount_flat": "<b>Скидка:</b> −{value}⭐",
    "buy.confirm_bonus_days": "<b>Бонус:</b> +{value} дн.",
    "buy.confirm_total": "<b>К оплате:</b> {stars}⭐",
    "buy.has_active_choose": "У вас есть активные подписки. Выберите действие:",
    "buy.no_plans": "Сейчас нет доступных тарифов. Загляните позже.",
    "buy.choose_plan": "Выберите тариф:",
    "buy.need_start": "Нужно нажать /start.",
    "buy.no_sub_specified": "Подписка не указана.",
    "buy.sub_unavailable_extend": "Подписка недоступна для продления.",
    "buy.plan_unavailable": "Тариф недоступен.",
    "buy.plan_no_inbounds": "У тарифа нет доступных подключений. Обратитесь к администратору.",
    "buy.inbounds_unavailable": "Не удалось получить список подключений. Попробуйте позже.",
    "buy.no_inbounds_for_plan": "Нет доступных подключений для этого тарифа.",
    "buy.choose_inbound": "Выберите подключение (сервер):",
    "buy.inbound_unavailable_for_plan": "Подключение недоступно для этого тарифа.",
    "buy.enter_promo": "Введите промокод одним сообщением:",
    "buy.need_start_full": "Нужно нажать /start, чтобы начать.",
    "buy.plan_gone": "Тариф больше недоступен. Вернитесь в меню.",
    "buy.promo_invalid_retry": "{error} Введите ещё раз:",
    "buy.promo_default_invalid": "Промокод недействителен.",
    "buy.promo_applied": "✅ Промокод применён.\n\n",
    "buy.promo_became_invalid": "Промокод стал недействителен, попробуйте ещё раз.",
    "buy.chat_undetermined": "Не удалось определить чат.",
    "buy.inbound_unavailable_pick": "Подключение недоступно для этого тарифа. Выберите другое.",
    "buy.plan_no_inbounds_retry": (
        "У тарифа сейчас нет доступных подключений. Попробуйте позже."
    ),
    "buy.precheckout_bad_order": "Некорректный заказ.",
    "buy.precheckout_plan_gone": "Тариф больше недоступен.",
    "buy.precheckout_promo_invalid": "Промокод стал недействителен.",
    "buy.precheckout_user_undetermined": "Не удалось определить пользователя.",
    "buy.precheckout_sub_unavailable": "Подписка недоступна для продления.",
    "buy.precheckout_inbound_gone": "Подключение больше недоступно.",
    "buy.payment_unparseable": (
        "Платёж получен, но мы не смогли разобрать заказ. "
        "Свяжитесь с поддержкой — мы вернём средства или активируем подписку вручную."
    ),
    "buy.payment_plan_deleted": (
        "Платёж получен, но тариф удалён. Напишите администратору — мы решим."
    ),
    "buy.payment_success_header": "✅ Оплата прошла. Подписка активна.",
    "buy.payment_provision_failed": (
        "Оплата получена, но не удалось активировать ключ в панели VPN. "
        "Мы зафиксировали платёж и в ближайшее время администратор активирует "
        "подписку вручную."
    ),

    # ----- admin.* --------------------------------------------------------
    "admin.greeting": "Админ-меню. Выберите раздел:",
    "admin.cancelled_greeting": "Отменено. Админ-меню. Выберите раздел:",
    "admin.cancelled": "Отменено",
    # admin keyboard labels (admin.kb.*)
    "admin.kb.plans": "📋 Тарифы",
    "admin.kb.promos": "🎟 Промокоды",
    "admin.kb.users": "👥 Пользователи",
    "admin.kb.stats": "📊 Статистика",
    "admin.kb.broadcast": "📣 Рассылка",
    "admin.kb.tickets": "💬 Тикеты",
    "admin.kb.audit": "📜 Аудит",
    "admin.kb.send": "✅ Разослать",
    "admin.kb.cancel": "✖ Отмена",
    "admin.kb.back": "◀ В меню",
    "admin.kb.back_short": "◀ Назад",
    "admin.kb.plan_label": "{marker}{title} · {days}д · {price}⭐",
    "admin.kb.create_plan": "➕ Создать тариф",
    "admin.kb.edit": "✏ Редактировать",
    "admin.kb.deactivate": "🚫 Деактивировать",
    "admin.kb.field_title": "Название",
    "admin.kb.field_days": "Срок (дней)",
    "admin.kb.field_price": "Цена (⭐)",
    "admin.kb.field_traffic": "Лимит трафика (ГБ)",
    "admin.kb.field_inbounds": "🔌 Подключения",
    "admin.kb.inbound_label": "{marker} {remark} (port {port})",
    "admin.kb.done": "✅ Готово",
    "admin.kb.manual": "✏ Ввести вручную",
    "admin.kb.preset_days": "{value} дней",
    "admin.kb.preset_price": "{value} ⭐",
    "admin.kb.preset_gb_unlimited": "0 (без лимита)",
    "admin.kb.preset_gb": "{value} ГБ",
    "admin.kb.create_promo": "➕ Создать промокод",
    "admin.kb.promo_label": "{marker}{code} · {type}:{value}",
    "admin.kb.type_percent": "% (percent)",
    "admin.kb.type_flat": "⭐ flat_stars",
    "admin.kb.type_free": "📆 free_days",
    "admin.kb.preset_percent": "{value}%",
    "admin.kb.preset_days_short": "{value} дней",
    "admin.kb.preset_max_unlimited": "0 (∞)",
    "admin.kb.preset_plain": "{value}",
    "admin.kb.preset_expires_never": "бессрочно",
    "admin.kb.preset_expires_days": "+{value}д",
    "admin.kb.redemptions": "👀 Redemptions",
    "admin.kb.revoke_sub": "🚫 Отозвать активную подписку",
    "admin.kb.unset_admin": "🛡 Снять админа",
    "admin.kb.set_admin": "🛡 Сделать админом",
    "admin.kb.grant_sub": "🎁 Выдать подписку",
    "admin.kb.block_user": "🚫 Заблокировать",
    "admin.kb.unblock_user": "🟢 Разблокировать",
    "admin.kb.find_another": "🔎 Найти другого",
    "admin.kb.period_7d": "За 7 дней",
    "admin.kb.period_30d": "За 30 дней",
    "admin.kb.period_all": "За всё время",
    "admin.kb.period_active": "· {text} ·",
    "admin.kb.refresh": "🔄 Обновить",

    # ----- wallet.* -------------------------------------------------------
    "wallet.invoice_title": "Пополнение баланса",
    "wallet.invoice_label": "Пополнение кошелька",
    "wallet.invoice_description": "Пополнение баланса на {stars}⭐.",
    "wallet.topup_success": (
        "✅ Баланс пополнен на {stars}⭐.\n"
        "Текущий баланс: {balance}⭐."
    ),
    "wallet.btn_open": "👛 Кошелёк",
    "wallet.screen_title": "<b>👛 Кошелёк</b>",
    "wallet.balance_line": "Баланс: <b>{balance}⭐</b>",
    "wallet.history_title": "<b>Последние операции:</b>",
    "wallet.history_empty": "Операций пока нет.",
    "wallet.history_row": "{sign}{amount}⭐ · {label}",
    "wallet.topup_prompt": "Выберите сумму пополнения:",
    "wallet.btn_topup_preset": "➕ {stars}⭐",
    "wallet.btn_topup": "➕ Пополнить",
    "wallet.no_presets": "Пополнение временно недоступно.",
    "wallet.type_topup": "Пополнение",
    "wallet.type_spend": "Оплата подпиской",
    "wallet.type_refund": "Возврат",
    "wallet.type_referral_bonus": "Реферальный бонус",
    "wallet.type_admin_grant": "Начисление администратором",
    "wallet.type_payment": "Платёж",
    "wallet.pay_from_balance": "💰 Оплатить с баланса",
    "wallet.insufficient": "Недостаточно средств на балансе.",
    "wallet.paid_from_balance_header": "✅ Оплачено с баланса. Подписка активна.",
    "wallet.pay_failed": (
        "Не удалось оплатить с баланса — попробуйте ещё раз или оплатите звёздами."
    ),

    # ----- reminder.* -----------------------------------------------------
    "reminder.3d": (
        "⏳ Ваша VPN-подписка истекает через 3 дня.\n"
        "Откройте «Моя подписка» и продлите её, чтобы не остаться без доступа."
    ),
    "reminder.1d": (
        "⏳ Ваша VPN-подписка истекает завтра.\n"
        "Продлите её через меню «Моя подписка», чтобы избежать перерыва."
    ),
    "reminder.0d": (
        "⚠️ Ваша VPN-подписка истекает сегодня.\n"
        "Продлите её прямо сейчас, иначе доступ будет отключён автоматически."
    ),
    "reminder.expired": (
        "❌ Срок вашей VPN-подписки истёк, доступ временно отключён.\n"
        "Чтобы продолжить пользоваться сервисом, оформите продление в меню "
        "«Купить подписку»."
    ),
    "reminder.btn_renew": "🔁 Продлить в 1 тап",

    # ----- traffic.* (traffic-quota alerts) -------------------------------
    "traffic.alert": (
        "📊 Вы израсходовали {percent}% трафика по подписке #{sub_id}.\n"
        "Когда лимит закончится, доступ будет ограничен. Продлите подписку "
        "или приобретите новую, чтобы не остаться без связи."
    ),

    # ----- autorenew.* (auto-renewal) -------------------------------------
    "autorenew.btn_subscribe": "🔁 Подписка (автопродление)",
    "autorenew.subscribe_prompt": (
        "🔁 Оформите автопродление — Telegram будет автоматически продлевать "
        "подписку каждые 30 дней, пока вы не отмените её.\n"
        "Нажмите кнопку ниже, чтобы оформить."
    ),
    "autorenew.btn_cancel": "⏹ Отменить автопродление",
    "autorenew.btn_enable": "🔁 Включить автопродление",
    "autorenew.cancelled": "⏹ Автопродление отменено.",
    "autorenew.enabled": "🔁 Автопродление включено.",
    "autorenew.cancel_failed": (
        "Не удалось изменить автопродление. Попробуйте позже."
    ),
    "autorenew.renewed_dm": (
        "🔁 Подписка #{sub_id} автоматически продлена за {stars}⭐ с баланса.\n"
        "Действует до {date}."
    ),
    "autorenew.insufficient_dm": (
        "⚠️ Не удалось автоматически продлить подписку #{sub_id}: на балансе "
        "не хватает {stars}⭐. Пополните кошелёк или продлите подписку вручную."
    ),

    # ----- trial.* --------------------------------------------------------
    "trial.btn": "🎁 Пробный период",
    "trial.need_start": "Нужно нажать /start, чтобы начать.",
    "trial.disabled": "Пробный период сейчас недоступен.",
    "trial.already_used": "Вы уже активировали пробный период.",
    "trial.choose_inbound": "Выберите подключение для пробного периода:",
    "trial.inbounds_unavailable": (
        "Не удалось получить список подключений. Попробуйте позже."
    ),
    "trial.no_inbounds": "Нет доступных подключений. Попробуйте позже.",
    "trial.activation_failed": (
        "Не удалось активировать пробный период. Попробуйте позже."
    ),
    "trial.header_activated": (
        "🎁 Пробный период на {days} дн. активирован!"
    ),

    # ----- referral.* -----------------------------------------------------
    "referral.btn": "👥 Пригласить друга",
    "referral.need_start": "Нужно нажать /start, чтобы начать.",
    "referral.screen_title": "<b>👥 Пригласить друга</b>",
    "referral.screen_body": (
        "Делитесь ссылкой с друзьями. После их первой оплаты вы получите "
        "<b>{stars}⭐</b> на баланс."
    ),
    "referral.screen_body_no_bonus": (
        "Делитесь ссылкой с друзьями, чтобы приглашать их в сервис."
    ),
    "referral.link_line": "Ваша ссылка:\n<code>{link}</code>",
    "referral.count_line": "Приглашено друзей: <b>{count}</b>",
    "referral.reward_dm": (
        "🎉 Ваш друг оформил первую подписку — вам начислено {stars}⭐ на баланс!"
    ),

    # ----- gift.* ---------------------------------------------------------
    "gift.btn_buy": "🎁 Подарить подписку",
    "gift.btn_redeem": "🎁 У меня есть подарок",
    "gift.need_start": "Нужно нажать /start, чтобы начать.",
    "gift.minted_dm": (
        "🎁 Подарочный код готов!\n\n"
        "Код: <code>{code}</code>\n"
        "Ссылка для активации:\n<code>{link}</code>\n\n"
        "Отправьте её тому, кому хотите подарить подписку."
    ),
    "gift.enter_code": "Введите подарочный код одним сообщением:",
    "gift.code_not_found": "Подарочный код не найден.",
    "gift.code_not_active": "Этот подарочный код уже использован или недействителен.",
    "gift.redeem_failed": (
        "Не удалось активировать подарок. Попробуйте позже."
    ),
    "gift.redeemed_header": "🎁 Подарочная подписка активирована!",
    "gift.buyer_notified_dm": (
        "🎁 Ваш подарочный код <code>{code}</code> активирован получателем!"
    ),

    # ----- blocked.* ------------------------------------------------------
    "blocked.refused": "🚫 Доступ к боту заблокирован.",

    # ----- support.* (tickets) --------------------------------------------
    "support.btn": "❓ Поддержка",
    "support.need_start": "Сначала нажмите /start.",
    "support.intro": (
        "💬 <b>Поддержка</b>\n\n"
        "Опишите вашу проблему одним сообщением — мы передадим её в поддержку "
        "и ответим прямо здесь, в этом чате."
    ),
    "support.prompt": "Напишите ваше сообщение в поддержку:",
    "support.empty": "Сообщение не может быть пустым. Напишите текст:",
    "support.sent": (
        "✅ Сообщение отправлено в поддержку (тикет #{ticket_id}). "
        "Мы ответим вам здесь."
    ),
    "support.reply_received": (
        "💬 <b>Ответ поддержки</b> (тикет #{ticket_id}):\n\n{text}"
    ),
    "support.closed_notice": (
        "✅ Тикет #{ticket_id} закрыт. Если вопрос остался — напишите снова."
    ),
    "support.admin_notify": (
        "💬 <b>Новый тикет #{ticket_id}</b>\n"
        "От: {user}\n\n{text}"
    ),
    "support.failed": "Не удалось отправить сообщение. Попробуйте позже.",

    # ----- admin.tickets.* ------------------------------------------------
    "admin.tickets.title": "💬 <b>Открытые тикеты</b>",
    "admin.tickets.empty": "Открытых тикетов нет.",
    "admin.tickets.list_item": "#{ticket_id} · {status} · от {user} · {updated_at}",
    "admin.tickets.not_found": "Тикет не найден.",
    "admin.tickets.card_header": (
        "💬 <b>Тикет #{ticket_id}</b>\n"
        "Пользователь: {user}\n"
        "Статус: {status}\n"
    ),
    "admin.tickets.history_title": "<b>Переписка:</b>",
    "admin.tickets.msg_user": "👤 {text}",
    "admin.tickets.msg_admin": "🛟 {text}",
    "admin.tickets.btn_reply": "✍ Ответить",
    "admin.tickets.btn_close": "✅ Закрыть тикет",
    "admin.tickets.btn_back": "◀ К списку",
    "admin.tickets.reply_prompt": "Напишите ответ пользователю (тикет #{ticket_id}):",
    "admin.tickets.reply_empty": "Ответ не может быть пустым. Напишите текст:",
    "admin.tickets.reply_sent": "✅ Ответ отправлен пользователю.",
    "admin.tickets.reply_failed": (
        "Ответ сохранён, но не удалось доставить пользователю "
        "(возможно, он заблокировал бота)."
    ),
    "admin.tickets.closed": "✅ Тикет #{ticket_id} закрыт.",
    "admin.tickets.status_open": "🟡 открыт",
    "admin.tickets.status_answered": "🟢 отвечен",
    "admin.tickets.status_closed": "⚪ закрыт",

    # ----- admin.grant.* (manual subscription grant) ----------------------
    "admin.grant.choose_plan": (
        "🎁 <b>Выдать подписку</b>\n\nВыберите тариф (срок берётся из тарифа "
        "или укажите свой на следующем шаге):"
    ),
    "admin.grant.no_plans": "Нет доступных тарифов для выдачи.",
    "admin.grant.enter_days": (
        "Введите количество дней подписки числом "
        "(или «-», чтобы взять срок из тарифа {days}д):"
    ),
    "admin.grant.bad_days": "Введите положительное число дней или «-»:",
    "admin.grant.plan_not_found": "Тариф не найден.",
    "admin.grant.success": (
        "✅ Подписка выдана пользователю {user}: {days}д "
        "(подписка #{sub_id}, до {expires_at} UTC)."
    ),
    "admin.grant.user_notified": (
        "🎁 Администратор выдал вам подписку на {days}д!"
    ),
    "admin.grant.failed": "Не удалось выдать подписку: {error}",

    # ----- admin.ban.* ----------------------------------------------------
    "admin.ban.blocked": "🚫 Пользователь заблокирован.",
    "admin.ban.unblocked": "🟢 Пользователь разблокирован.",
    "admin.ban.self": "Нельзя заблокировать самого себя.",
    "admin.ban.cannot_block_admin": "Нельзя заблокировать администратора.",

    # ----- admin.audit.* --------------------------------------------------
    "admin.audit.title": "📜 <b>Аудит админ-действий</b>",
    "admin.audit.empty": "Записей пока нет.",
    "admin.audit.item": "{created_at} · {admin} · <b>{action}</b>{target}{details}",
    "admin.audit.btn_prev": "◀ Назад",
    "admin.audit.btn_next": "Вперёд ▶",
    "admin.audit.btn_back": "◀ В меню",

    # ----- health.* (panel health-check alerts) ---------------------------
    "health.alert_down": (
        "🔴 <b>Панель 3x-ui недоступна!</b>\n\n"
        "Health-check не смог достучаться до панели.\n"
        "Причина: <code>{error}</code>\n\n"
        "Новые подписки могут не выдаваться — проверьте сервер."
    ),
    "health.alert_up": (
        "🟢 <b>Панель 3x-ui снова доступна.</b>\n\n"
        "Связь с панелью восстановлена, сервис работает штатно."
    ),
    "health.status_up": "🟢 онлайн",
    "health.status_down": "🔴 недоступна",
    "health.status_unknown": "⚪ нет данных",

    # ----- location.* (inbound availability indicator) --------------------
    "location.indicator_up": "🟢",
    "location.indicator_down": "🔴",
    "location.label": "{indicator} {remark}",
    "location.label_with_port": "{indicator} {remark} (порт {port})",

    # ----- admin.export.* (CSV statistics export) -------------------------
    "admin.export.btn": "📥 Скачать CSV",
    "admin.export.caption_payments": "💳 Платежи ({rows} строк)",
    "admin.export.caption_subscriptions": "🔑 Подписки ({rows} строк)",
    "admin.export.caption_users": "👥 Пользователи ({rows} строк)",
    "admin.export.done": "📥 Экспорт отправлен файлами.",
    "admin.export.failed": "Не удалось сформировать экспорт. Попробуйте позже.",

    # ----- keys.howto.* (client deep-link import guides) ------------------
    "keys.howto.title": "<b>📲 Как подключиться</b>",
    "keys.howto.intro": (
        "Скопируйте ссылку-импорт для вашего клиента и откройте её, либо "
        "вставьте Subscription URL вручную:"
    ),
    "keys.howto.happ": (
        "<b>Happ (iOS / Android / Windows / macOS) — рекомендуем:</b>\n"
        "<code>{link}</code>\n"
        "Если ссылка не открывается — в Happ нажмите «+» → «Добавить подписку» "
        "и вставьте Subscription URL:\n<code>{sub_url}</code>"
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
        "Если ссылка не открывается — скопируйте Subscription URL и добавьте "
        "подписку вручную через «Импорт из буфера обмена»."
    ),
    "keys.howto.btn": "📲 Как подключиться",
}


__all__ = ["MESSAGES"]
