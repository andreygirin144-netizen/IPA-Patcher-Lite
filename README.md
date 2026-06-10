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

|Функция                        |Описание                                                                        |
|-------------------------------|--------------------------------------------------------------------------------|
|📦 **Распаковка IPA**           |Извлекает содержимое `.ipa` во временную папку с прогресс-баром                 |
|✏️ **Редактирование Info.plist**|Интерактивное меню: имя, версия, номер сборки, Bundle ID                        |
|🔑 **Смена Bundle ID**          |Меняет идентификатор в `Info.plist` и всех связанных полях, включая расширения  |
|📁 **Поддержка файлов**         |Включает iTunes File Sharing и открытие документов из сторонних приложений      |
|🔍 **Просмотр файлов .app**     |Показывает список файлов внутри `.app` (первые 50)                              |
|🧹 **Удаление подписи**         |Удаляет `_CodeSignature`, `SC_Info`, `embedded.mobileprovision`, `CodeResources`|
|📦 **Сборка IPA**               |Упаковывает результат обратно с сохранением Unix-прав доступа                   |
|📱 **Нативный UI на iOS**       |Файловый пикер и диалоги через Pythonista 3 — без терминала                     |

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
  Читаем Info.plist ──▶ текущие данные приложения
        │
        ▼
  ┌─────────────────────────────────────┐
  │  Интерактивное меню редактирования  │
  │  1. Имя приложения                  │
  │  2. Версия (CFBundleShortVersionString) │
  │  3. Номер сборки (CFBundleVersion)  │
  │  4. Bundle ID                       │
  │  5. Поддержка файлов                │
  │  6. Просмотр файлов .app            │
  │  7. Применить и собрать IPA         │
  └─────────────────────────────────────┘
        │
        ├──▶ Обновление Bundle ID (если изменён)
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
        │       · CodeResources
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
└── ipa_patch3.py     # Основной скрипт: UI, логика патча, упаковка/распаковка
```

> **Примечание:** Файл `unpack.py` не требуется — вся логика распаковки и упаковки встроена в `ipa_patch3.py`.

-----

## Установка

### 📱 iPhone / iPad — Pythonista 3

1. Установи [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) из App Store
1. Скопируй `ipa_patch3.py` в **Pythonista → Documents**
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
1. В интерактивном меню выбери нужные действия (изменить имя, версию, Bundle ID и т.д.)
1. Выбери пункт **7 — Применить изменения и собрать IPA**
1. Подтверди сводку изменений
1. Готовый файл появится в `Documents/имя_patched.ipa`
1. Нажми на файл → **Поделиться** → выбери AltStore или SideStore

### macOS / Linux (терминал)

```bash
python3 ipa_patch3.py
# Введи путь к .ipa файлу
# Работай с интерактивным меню
# Укажи путь для сохранения нового .ipa
```

-----

## Меню редактирования

|Пункт|Действие                                                            |
|-----|--------------------------------------------------------------------|
|`1`  |Изменить имя приложения (`CFBundleDisplayName` / `CFBundleName`)    |
|`2`  |Изменить версию (`CFBundleShortVersionString`)                      |
|`3`  |Изменить номер сборки (`CFBundleVersion`)                           |
|`4`  |Изменить Bundle ID (`CFBundleIdentifier`)                           |
|`5`  |Включить поддержку файлов (iTunes File Sharing, открытие документов)|
|`6`  |Просмотреть файлы внутри `.app` (первые 50)                         |
|`7`  |Показать сводку изменений, подтвердить и собрать IPA                |
|`0`  |Выйти без сохранения                                                |

Перед сборкой скрипт показывает **сводку всех изменений** и запрашивает подтверждение.

-----

## Что удаляется из подписи

|Файл / Папка              |Назначение                 |
|--------------------------|---------------------------|
|`_CodeSignature/`         |Хэши всех файлов приложения|
|`SC_Info/`                |Данные подписи SuperCert   |
|`embedded.mobileprovision`|Профиль распространения    |
|`CodeResources`           |Список ресурсов с подписью |

## Что включает поддержка файлов

|Ключ Info.plist                    |Назначение                                        |
|-----------------------------------|--------------------------------------------------|
|`UIFileSharingEnabled`             |Доступ к папке приложения через iTunes / Finder   |
|`LSSupportsOpeningDocumentsInPlace`|Открытие документов напрямую из другого приложения|
|`UISupportsDocumentBrowser`        |Поддержка системного браузера файлов              |

-----

## FAQ

**Q: Нужен ли jailbreak?**  
A: Нет. Установка через AltStore / SideStore работает на стоковом iOS.

**Q: Какая версия Pythonista нужна?**  
A: Pythonista 3.4.

**Q: Нужен ли `unpack.py`?**  
A: Нет. В текущей версии (`ipa_patch3.py`) вся логика распаковки и упаковки встроена в один файл.

**Q: Тратится ли лимит слотов AltStore?**  
A: Нет. Смена Bundle ID позволяет системе считать приложение новым — отдельный слот не расходуется.

**Q: Можно ли откатить изменения?**  
A: Скрипт не изменяет исходный `.ipa` — результат всегда сохраняется в новый файл с суффиксом `_patched`.

-----

<div align="center">

Сделано для iOS · работает на Pythonista 3

</div>
