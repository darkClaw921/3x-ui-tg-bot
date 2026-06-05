# health_check_job

Scheduler job (app/scheduler.py), CronTrigger minute='0,30' (~every 30 min), max_instances=1. Probes 3x-ui panel via app.services.health.check_xui_health (list_inbounds under 10s timeout), persists state to health_status table via app.db.repos.health.record (returns changed flag), refreshes health.set_cached_status snapshot for keyboards, and alerts admins (ADMIN_IDS + SUPPORT_CHAT_ID, via _alert_admins) ONLY on an up<->down transition. Registered in setup_scheduler as the 5th job.
