# app/handlers/user/language.py

Роутер выбора языка (user_language). cb_open (LangCB open) - рисует language_menu_kb с текущим языком. cb_set (LangCB set,lang) - валидирует код против SUPPORTED_LANGS, users_repo.set_lang, перерисовывает меню на новом языке. Зарегистрирован в user/__init__ перед help.
