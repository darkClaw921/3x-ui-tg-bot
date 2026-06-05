# tests/test_i18n.py

Тесты i18n: константы (DEFAULT/FALLBACK/SUPPORTED/LANG_NAMES), t() резолв+fallback (lang->en->key, дефолт ru, uk/fa/zh->en, plural-only ключ возвращает key), безопасный format_map (пропущенный/лишний параметр), pluralize RU(1/2-4/5-20)+EN формы, resolve_lang (en-US->en, zh-Hans->zh, unsupported/None->ru), покрытие RU⊆EN + плюральные dict в обоих + stub-ключи имеют EN-fallback.
