# _relax_subscription_notifications_kind

Engine migration (app/db/engine.py): conditionally drops the legacy CHECK(kind IN ...) on subscription_notifications via a data-preserving table rebuild so new notification kinds (e.g. 'traffic80') can be inserted on existing DBs. Idempotent: inspects sqlite_master.sql and is a no-op when no CHECK remains. Toggles foreign_keys off during the swap and restores it. kind validation now lives in subscriptions.try_mark_notification_sent against NOTIFICATION_KINDS.
