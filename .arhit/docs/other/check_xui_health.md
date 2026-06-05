# check_xui_health

app/services/health.py: async probe of the 3x-ui panel. Calls app.xui.inbounds.list_inbounds wrapped in asyncio.wait_for(timeout=10s). Returns (ok: bool, error: str|None). Catches TimeoutError, XuiError and any exception -> (False, reason). Companion get_cached_status()/set_cached_status() hold a process-local HealthState snapshot ('up'|'down'|None) read by location keyboards to render a green/red indicator without hitting the panel.
