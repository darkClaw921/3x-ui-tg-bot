# app/states/admin.py::PlanCreate

FSM group for the create-plan wizard. Flow: waiting_title (text) → waiting_days (preset or text, int>0) → waiting_price (preset or text, int≥0) → waiting_traffic_gb (preset or text, int≥0; 0 = unlimited) → DB write + clear. Each numeric step shows a preset keyboard; manual text entry is always available.
