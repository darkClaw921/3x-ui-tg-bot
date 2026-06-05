# cb_export

app/handlers/admin/stats.py: StatsCB(action='export', field='all') handler. Builds 3 CSV blobs (payments/subscriptions/users) via app.services.exports, sends each as BufferedInputFile document to the admin chat with localized caption (admin.export.caption_*), records one stats.export audit entry, answers with admin.export.done toast. Best-effort: build/send failures fall back to admin.export.failed alert. Button '📥 Download CSV' (admin.export.btn) added to stats_kb.
