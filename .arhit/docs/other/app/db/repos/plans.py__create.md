# app/db/repos/plans.py::create

Insert a new active plan into the plans table.

Signature: create(conn, title, days, price_stars, traffic_gb=0) -> Plan

Parameters:
- conn (aiosqlite.Connection)
- title (str): tariff name.
- days (int): subscription duration (>0 enforced by SQL CHECK).
- price_stars (int): price in Telegram Stars (>=0 enforced by SQL CHECK).
- traffic_gb (int, default 0): traffic limit in GB. 0 means unlimited and matches the xui totalGB convention. Stored with CHECK (traffic_gb >= 0).

Returns the freshly-inserted Plan via get(). Commits on success.
