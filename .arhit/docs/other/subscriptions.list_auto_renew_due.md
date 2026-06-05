# subscriptions.list_auto_renew_due

Repo query returning active wallet-fallback subscriptions due for renewal: status='active' AND auto_renew=1 AND tg_sub_charge_id IS NULL AND expires_at <= now+within_hours (default 24). Ordered by expires_at asc. Native Star subscriptions are excluded (Telegram bills them). Drives app.scheduler.auto_renew_job.
