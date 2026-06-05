# plan_inbounds_select_kb

app/keyboards/admin.py: multi-select keyboard over xui inbounds for plan create/edit. Each row: ☑/☐ marker + remark + (port). Empty panel remark falls back to 'Локация #<id>' (kb.inbound_fallback_remark, RU+EN) so admins never see a blank label. Rows send PlanCB(action='toggle_inbound', id). Admin plan wizard (handlers/admin/plans.py cb_inbounds_done) persists the selection via plans_repo.set_inbounds in both create and edit flows.
