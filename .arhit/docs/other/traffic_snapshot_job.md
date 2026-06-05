# traffic_snapshot_job

Scheduler job (app/scheduler.py): every 6h snapshots each active subscription's up/down from the panel into traffic_snapshots, then calls _maybe_alert_traffic to compare cumulative up+down against plan.traffic_gb*1024^3 and, at settings.TRAFFIC_ALERT_PERCENT (default 80), sends a one-off DM with renew_reminder_kb, deduped via subscription_notifications kind 'traffic80'. Per-sub try/except so one failure doesn't break the job. Unlimited plans (traffic_gb=0), plan_id NULL, or percent=0 skip alerting.
