# build_import_links

Строит deep-link схемы импорта подписки в VPN-клиенты по Subscription URL. Ключи: happ (happ://import/<encoded>, кросс-платформенный, рекомендуемый), v2rayng (v2rayng://install-config?url=<encoded>), hiddify (hiddify://import/<encoded>), streisand (streisand://import/<encoded>). sub_url percent-encoded через quote(safe=''). Пустой sub_url -> {}. Telegram не принимает кастомные схемы в кнопках/href — показываются копируемыми <code>-блоками в гайде build_howto_text. Для Happ дан ручной fallback: добавить Subscription URL через «Добавить подписку».
