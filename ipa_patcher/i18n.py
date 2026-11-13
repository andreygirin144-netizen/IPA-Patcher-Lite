# -*- coding: utf-8 -*-
import os
import json
import locale

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

_HOME = os.path.expanduser("~")
if os.path.basename(_HOME).lower() == "documents":
    _WORKSPACE_DIR = os.path.join(_HOME, "IPA_Workspace")
else:
    _WORKSPACE_DIR = os.path.join(_HOME, "Documents", "IPA_Workspace")

_CONFIG_FILE = os.path.join(_WORKSPACE_DIR, "config.json")

_CURRENT_LANG = "en"
_STRINGS = {}
_FALLBACK = {}
_LOADED = False


def _load_lang_bundle(lang):
    merged = {}
    if not os.path.isdir(_LOCALES_DIR):
        return merged

    files = [f"{lang}.json"] + sorted(
        f for f in os.listdir(_LOCALES_DIR)
        if f.startswith(f"{lang}_") and f.endswith(".json")
    )
    for fname in files:
        path = os.path.join(_LOCALES_DIR, fname)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        merged.update(data)
            except Exception:
                pass
    return merged


def _detect_system_lang():
    try:
        from objc_util import ObjCClass
        langs = ObjCClass("NSLocale").preferredLanguages()
        if langs and len(langs) > 0:
            first = str(langs[0]).lower()
            if first.startswith("ru"):
                return "ru"
            if first.startswith("en"):
                return "en"
    except Exception:
        pass

    for env_var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(env_var, "").lower()
        if val.startswith("ru"):
            return "ru"
        if val.startswith("en"):
            return "en"

    try:
        loc = locale.getlocale()[0]
        if loc and loc.lower().startswith("ru"):
            return "ru"
    except Exception:
        pass

    try:
        loc = locale.getdefaultlocale()[0]
        if loc and loc.lower().startswith("ru"):
            return "ru"
    except Exception:
        pass

    return "en"


def load_saved_lang():
    if os.path.isfile(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            lang = str(cfg.get("lang", "")).lower()
            if lang in ("ru", "en"):
                return lang
        except Exception:
            pass
    return None


def save_lang(lang):
    if lang not in ("ru", "en"):
        return
    try:
        os.makedirs(_WORKSPACE_DIR, exist_ok=True)
        cfg = {}
        if os.path.isfile(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}
            except Exception:
                cfg = {}
        cfg["lang"] = lang
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def init_i18n(lang=None, persist=False):
    global _CURRENT_LANG, _STRINGS, _FALLBACK, _LOADED
    if lang is None:
        lang = load_saved_lang() or _detect_system_lang()
    else:
        lang = lang.lower()
        if lang not in ("ru", "en"):
            lang = "en"

    _CURRENT_LANG = lang
    _FALLBACK = _load_lang_bundle("en")
    _STRINGS = _load_lang_bundle(lang) if lang != "en" else _FALLBACK
    _LOADED = True

    if persist:
        save_lang(lang)


def set_lang(lang, persist=True):
    init_i18n(lang=lang, persist=persist)


def get_lang():
    if not _LOADED:
        init_i18n()
    return _CURRENT_LANG


def t(key, **kwargs):
    if not _LOADED:
        init_i18n()
    text = _STRINGS.get(key)
    if text is None:
        text = _FALLBACK.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
