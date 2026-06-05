# export_payments_csv

app/services/exports.py: async export_payments_csv/export_subscriptions_csv/export_users_csv(conn) -> bytes. Use stdlib csv + io.StringIO, encode utf-8-sig (BOM) for Excel/Cyrillic. Each writes a fixed header row then SELECT ... ORDER BY id rows; NULL -> empty cell. subscriptions export OMITS xui_client_uuid (connection secret). Consumed by admin stats handler cb_export which sends each as BufferedInputFile via bot.send_document and logs a stats.export audit entry.
