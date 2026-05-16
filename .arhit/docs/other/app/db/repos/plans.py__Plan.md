# app/db/repos/plans.py::Plan

Plan dataclass (frozen, slots) for rows of the plans table.

Fields:
- id (int): primary key.
- title (str): human-readable tariff name.
- days (int): subscription duration in days (>0).
- price_stars (int): price in Telegram Stars (>=0).
- traffic_gb (int): per-client traffic limit in GB forwarded to 3x-ui as totalGB; 0 means unlimited (xui semantics).
- is_active (bool): coerced from is_active INTEGER (0/1).
- created_at (str): timestamp.

Construction:
- from_row(row) reads id/title/days/price_stars/traffic_gb/is_active/created_at from aiosqlite.Row.
