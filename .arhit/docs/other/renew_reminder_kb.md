# renew_reminder_kb

Keyboard builder (app/keyboards/user.py): single «🔁 Продлить в 1 тап» button carrying BuyCB(action='extend', sub_id=N). Attached by scheduler.reminders_job to 3d/1d/0d expiry reminders so the user renews from the message via the existing extend flow (buy.cb_pick_action_extend). i18n key reminder.btn_renew (RU+EN).
