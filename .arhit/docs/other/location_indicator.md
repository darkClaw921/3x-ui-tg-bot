# location_indicator

app/keyboards/user.py: location_indicator(lang) -> str. Maps the process-local panel health snapshot (app.services.health.get_cached_status, refreshed by scheduler health_check_job) to a 🟢 (up) / 🔴 (down) / ⚪ (None/unknown) marker via i18n location.indicator_* keys. Synchronous; used by inbound_select_kb to prefix each location button. The snapshot updates every ~30 min on each health probe.
