"""Language picker router.

Lets a user switch the bot's UI language at runtime. Two callbacks:

* :func:`cb_open` — ``LangCB(action='open')`` (the «🌐 Язык / Language»
  button in :func:`app.keyboards.user.user_main_menu`): render the language
  menu with the user's current language check-marked.
* :func:`cb_set` — ``LangCB(action='set', lang=<code>)``: validate the chosen
  code against :data:`app.i18n.SUPPORTED_LANGS`, persist it via
  :func:`app.db.repos.users.set_lang`, and re-render the menu in the **new**
  language so the change is immediately visible.

The chosen language is stored on the ``users.lang`` column and surfaced to
every subsequent update through :class:`app.middlewares.user_ctx` (``data['lang']``),
so no global state is needed here.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.engine import get_conn
from app.db.repos import users as users_repo
from app.db.repos.users import User
from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from app.keyboards.user import LangCB, language_menu_kb

router = Router(name="user_language")


@router.callback_query(LangCB.filter(F.action == "open"))
async def cb_open(
    callback: CallbackQuery, user: User | None = None, lang: str = DEFAULT_LANG
) -> None:
    """Render the language picker with the current language check-marked."""
    current = user.lang if user is not None else lang
    if callback.message is not None:
        await callback.message.edit_text(
            t("lang.choose", current),
            reply_markup=language_menu_kb(current),
        )
    await callback.answer()


@router.callback_query(LangCB.filter(F.action == "set"))
async def cb_set(
    callback: CallbackQuery,
    callback_data: LangCB,
    user: User | None = None,
    lang: str = DEFAULT_LANG,
) -> None:
    """Persist the chosen language and re-render the menu in that language.

    Guards:

    * ``user`` must be present (set by :mod:`app.middlewares.user_ctx`).
    * the requested ``lang`` must be one of :data:`app.i18n.SUPPORTED_LANGS`;
      a crafted callback with an unknown code is rejected with an alert.
    """
    if user is None:
        await callback.answer(t("menu.need_start", lang), show_alert=True)
        return

    new_lang = callback_data.lang
    if new_lang not in SUPPORTED_LANGS:
        await callback.answer(t("lang.unsupported", lang), show_alert=True)
        return

    async with get_conn() as conn:
        await users_repo.set_lang(conn, user.id, new_lang)

    if callback.message is not None:
        await callback.message.edit_text(
            t("lang.choose", new_lang),
            reply_markup=language_menu_kb(new_lang),
        )
    await callback.answer(t("lang.changed", new_lang))


__all__ = ["router"]
