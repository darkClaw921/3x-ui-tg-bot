# app/i18n/plural.py

plural.py: реестр плюральных селекторов. plural_category(n, lang) -> one/few/many/other. RU-селектор зеркалит _pluralize_subs из my_subscription.py (3 формы 1/2-4/5-20). uk использует RU-правило, en - one/other, остальные _plural_other (always other).
