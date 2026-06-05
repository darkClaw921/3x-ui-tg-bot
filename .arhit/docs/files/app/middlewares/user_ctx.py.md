# app/middlewares/user_ctx.py

UserContextMiddleware (outer middleware на dp.update). На каждый апдейт извлекает from_user (_extract_tg_user), вызывает users_repo.get_or_create(..., language_code=tg_user.language_code) и кладёт data['user']=User, data['lang']=user.lang. При отсутствии from_user или ошибке БД: data['user']=None, data['lang']=DEFAULT_LANG. lang доступен хендлерам для прямой передачи в i18n.t.
