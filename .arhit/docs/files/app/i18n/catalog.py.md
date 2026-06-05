# app/i18n/catalog.py

catalog.py: собирает CATALOG {lang: {key: value}} из модулей locales/{ru,en,uk,fa,zh}. lookup(key, lang) реализует политику резолва lang->en (FALLBACK), возвращает str | dict (плюральная категория) | None; не падает к raw key (этот шаг в t()).
