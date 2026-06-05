# Settings.AUTO_RENEW_ENABLED

Phase 4 config flag (default True). Master switch for auto-renewal: hides the autopay button, skips the cancel control, and short-circuits auto_renew_job when False. Joined by TRAFFIC_ALERT_PERCENT (default 80, 0-100, 0=off; threshold % of plan.traffic_gb for one-off traffic alerts) and STAR_SUBSCRIPTION_PLAN_DAYS (default 30, >0; plan.days that qualifies for a native Telegram Star subscription matching billing.SUBSCRIPTION_PERIOD_SECONDS).
