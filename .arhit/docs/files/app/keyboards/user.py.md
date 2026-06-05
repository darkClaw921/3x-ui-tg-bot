# app/keyboards/user.py

Добавлены: WalletCB(prefix='uw', action=open|topup|pick, stars). Кнопка '👛 Кошелёк' (t wallet.btn_open, WalletCB action='open') в user_main_menu. wallet_screen_kb(*,has_presets,lang) — кнопка '➕ Пополнить' (если presets) + '◀ В меню'. wallet_topup_kb(presets,lang) — кнопка на каждый пресет (WalletCB action='pick' stars) + '◀ Назад' (WalletCB action='open'). Экспортированы WalletCB, wallet_screen_kb, wallet_topup_kb.
