# build_howto_text

app/handlers/user/_keys.py: build_howto_text(sub_url, lang) composes the localized '📲 How to connect' guide (keys.howto.* i18n keys, RU+EN) listing per-client deep-link import URLs from build_import_links as copyable <code> blocks + a manual fallback hint. Returns '' for empty sub_url. deliver_keys sends this as an extra message after the subscription-URL message.
