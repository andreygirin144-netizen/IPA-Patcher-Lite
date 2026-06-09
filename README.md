<div align="center">

# ⚙️ IPA Patcher Lite

**Патч iOS `.ipa` файлов на чистом Python**  
Без компилятора. Без зависимостей. Работает прямо на iPhone.

[![Python 3.6+](https://img.shields.io/badge/Python-3.6+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pythonista 3.4](https://img.shields.io/badge/Pythonista-3.4-FF6B35?style=flat-square)](http://omz-software.com/pythonista/)
[![Platform](https://img.shields.io/badge/Platform-iOS%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![License MIT](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)

</div>

-----

## Содержание

- [Что делает](#что-делает)
- [Как это работает](#как-это-работает)
- [Структура проекта](#структура-проекта)
- [Установка](#установка)
- [Использование](#использование)
- [FAQ](#faq)

-----

## Что делает

|Функция                 |Описание                                                             |
|------------------------|---------------------------------------------------------------------|
|📦 **Распаковка IPA**    |Извлекает содержимое `.ipa` во временную папку                       |
|🔑 **Смена Bundle ID**   |Меняет идентификатор приложения в `Info.plist` и всех связанных полях|
|🧹 **Удаление подписи**  |Удаляет `_CodeSignature`, `embedded.mobileprovision`, `CodeResources`|
|📁 **Сборка IPA**        |Упаковывает результат обратно с сохранением Unix-прав доступа        |
|📱 **Нативный UI на iOS**|Файловый пикер и диалоги через Pythonista 3 — без терминала          |

-----

## Как это работает

```
┌─────────────────────────────────────────────────┐
│                  IPA Patcher Lite               │
└─────────────────────────────────────────────────┘

  [Выбрать .ipa]
        │
        ▼
  Распаковка ZIP ──▶ /tmp/ipa_patch_XXXXX/
        │
        ▼
  Читаем Info.plist ──▶ текущий Bundle ID
        │
        ▼
  [Ввести новый Bundle ID]
        │
        ├──▶ Обновление Bundle ID
        │       · Info.plist
        │       · CFBundleURLTypes
        │       · WKAppBundleIdentifier
        │       · NSExtension
        │       · PlugIns/*.appex
        │
        ├──▶ Удаление файлов подписи
        │       · _CodeSignature/
        │       · SC_Info/
        │       · embedded.mobileprovision
        │
        ▼
  Упаковка ──▶ имя_patched.ipa
        │
        ▼
  Сохранение в ~/Documents/ (Pythonista) или по пути (CLI)
```

-----

## Структура проекта

```
ipa-patcher/
├── ipa_patch3.py     # Основной скрипт: UI, логика патча
└── unpack.py         # Распаковка и упаковка .ipa с сохранением прав
```

-----

## Установка

### 📱 iPhone / iPad — Pythonista 3

1. Установи [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) из App Store
1. Скопируй оба файла в **Pythonista → Documents**:
- `ipa_patch3.py`
- `unpack.py`
1. Готово — никаких `pip install`

### 🖥️ macOS / Linux

```bash
git clone https://github.com/andreygirin144-netizen/ipa-patcher.git
cd ipa-patcher
python3 ipa_patch3.py
```

-----

## Использование

### Pythonista 3 (iOS)

1. Открой `ipa_patch3.py` в Pythonista
1. Нажми **▶ Run**
1. Выбери `.ipa` через файловый пикер
1. Введи новый Bundle ID — например, `com.yourname.appname`
1. Готовый файл появится в `Documents/имя_patched.ipa`
1. Нажми на файл → **Поделиться** → выбери AltStore или SideStore

### macOS / Linux (терминал)

```bash
python3 ipa_patch3.py
```

-----

### Что удаляется из подписи

|Файл / Папка              |Назначение                 |
|--------------------------|---------------------------|
|`_CodeSignature/`         |Хэши всех файлов приложения|
|`SC_Info/`                |Данные подписи SuperCert   |
|`embedded.mobileprovision`|Профиль распространения    |
|`CodeResources`           |Список ресурсов с подписью |

### Где обновляется Bundle ID

Скрипт меняет идентификатор во всех нужных местах:

- `Info.plist` — `CFBundleIdentifier`, `CFBundleURLTypes`, `WKAppBundleIdentifier`, `NSExtension`
- `PlugIns/*.appex/Info.plist` — расширения приложения

-----

## FAQ

**Q: Нужен ли jailbreak?**  
A: Нет. Установка через AltStore / SideStore работает на стоковом iOS.

**Q: Какая версия Pythonista нужна?**  
A: Pythonista 3.4.

**Q: Можно использовать `ipa_patch3.py` без `unpack.py`?**  
A: Нет, оба файла обязательны.

**Q: Тратится ли лимит слотов AltStore?**  
A: Нет. Смена Bundle ID позволяет системе считать приложение новым — отдельный слот не расходуется.

-----

<div align="center">

Сделано для iOS · работает на Pythonista 3

</div>
