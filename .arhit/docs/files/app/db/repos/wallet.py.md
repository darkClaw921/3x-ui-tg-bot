# app/db/repos/wallet.py

Добавлена get_by_ref(conn,ref)->WalletTxn|None — поиск строки ledger по уникальному non-null ref (idx_wallet_ref). Используется pay-from-balance для восстановления id вставленного spend-txn после try_spend, чтобы записать синтетический payments.telegram_charge_id='wallet:<txn_id>'. Добавлен в __all__.
