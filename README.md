<div align="center">

# 🔧 IPA Patcher

**Патч iOS `.ipa` файлов на чистом Python — без компилятора, без зависимостей**

[![Python](https://img.shields.io/badge/Python-3.6+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pythonista](https://img.shields.io/badge/Pythonista-3.4-orange?style=flat-square)](https://omz-software.com/pythonista/)
[![Platform](https://img.shields.io/badge/Platform-iOS%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/andreygirin144-netizen/ipa-patcher)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

-----

## 📖 Содержание

- [Что делает](#-что-делает)
- [Как это работает](#-как-это-работает)
- [Структура проекта](#-структура-проекта)
- [Установка](#-установка)
- [Использование](#-использование)
- [Технические детали](#-технические-детали)
- [Ограничения](#-ограничения)
- [FAQ](#-faq)

-----

## ✨ Что делает

|Функция                   |Описание                                                              |
|--------------------------|----------------------------------------------------------------------|
|📦 **Распаковка IPA**      |Извлекает содержимое `.ipa` во временную папку                        |
|🔑 **Смена Bundle ID**     |Меняет идентификатор приложения в `Info.plist` и всех связанных полях |
|🔬 **Патч Mach-O**         |Заменяет жёсткие зависимости на слабые, чтобы приложение не крашилось |
|🧹 **Удаление подписи**    |Удаляет `_CodeSignature`, `embedded.mobileprovision`, `CodeResources` |
|🗑️ **Удаление фреймворков**|Убирает проблемные библиотеки (`StoreKit`, `Firebase`, `Adjust` и др.)|
|📁 **Сборка IPA**          |Упаковывает результат обратно с сохранением Unix-прав доступа         |
|📱 **Нативный UI на iOS**  |Файловый пикер и диалоги через `Pythonista 3` вместо терминала        |

-----

## 🔍 Как это работает

```
┌─────────────────────────────────────────────────────────────┐
│                        IPA Patcher                          │
└─────────────────────────────────────────────────────────────┘

  [Выбрать .ipa]
        │
        ▼
  Распаковка ZIP → /tmp/ipa_patch_XXXXX/
        │
        ▼
  Читаем Info.plist → старый Bundle ID
        │
        ▼
  [Ввести новый Bundle ID]
        │
        ├──▶ Патч Mach-O бинарников (macho_patch.py)
        │       LC_LOAD_DYLIB → LC_LOAD_WEAK_DYLIB
        │       (до удаления фреймворков — важен порядок!)
        │
        ├──▶ Обновление Bundle ID
        │       Info.plist, CFBundleURLTypes, WKAppBundleIdentifier,
        │       NSExtension, вложенные .appex
        │
        ├──▶ Удаление файлов подписи
        │       _CodeSignature/, SC_Info/, embedded.mobileprovision
        │
        ├──▶ Удаление проблемных фреймворков
        │       StoreKit, Firebase, Adjust, AppStore...
        │
        ▼
  Упаковка → имя_patched.ipa (с сохранением прав доступа)
        │
        ▼
  Сохранение в ~/Documents/ (Pythonista) или по пути (CLI)
```

-----

## 📂 Структура проекта

```
ipa-patcher/
├── ipa_patch3.py     # Главный скрипт — запускай его
└── macho_patch.py    # Модуль патча Mach-O — нужен рядом
```

> **Важно:** оба файла должны лежать в одной папке. `macho_patch.py` — это модуль, он сам по себе не запускается.

-----

## 🚀 Установка

### На iPhone / iPad (Pythonista 3)

**Шаг 1.** Установи [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) из App Store

**Шаг 2.** Скачай оба файла и перенеси их в Pythonista:

```
Files → На моём iPhone → Pythonista 3 → Documents
```

Положи туда:

- `ipa_patch3.py`
- `macho_patch.py`

**Шаг 3.** Готово — никаких `pip install` не нужно, только стандартная библиотека Python.

-----

### На macOS / Linux

```bash
# Клонируй репозиторий
git clone https://github.com/andreygirin144-netizen/ipa-patcher.git
cd ipa-patcher

# Запускай — зависимостей нет
python3 ipa_patch3.py
```

Требования: **Python 3.6+**

-----

## 📱 Использование

### Pythonista 3 (iOS)

1. Открой `ipa_patch3.py` в Pythonista
1. Нажми кнопку **▶ Run**
1. Откроется стандартное окно **Files** — выбери `.ipa` из любого места (iCloud, Downloads, локальное хранилище)
1. Введи новый Bundle ID в диалоговом окне, например: `com.yourname.appname`
1. Скрипт всё сделает автоматически
1. Готовый файл появится в:

```
Files → На моём iPhone → Pythonista 3 → Documents → имя_patched.ipa
```

1. Нажми на файл → **Поделиться** → выбери **AltStore** или **SideStore**

-----

### macOS / Linux (терминал)

```bash
python3 ipa_patch3.py
```

```
Путь к исходному .ipa файлу: ~/Downloads/MyApp.ipa
Текущий Bundle ID: com.original.app
Новый Bundle ID: com.yourname.myapp
Путь для сохранения нового .ipa: ~/Downloads/MyApp_patched.ipa
```

-----

## 🔬 Технические детали

### Патч Mach-O (`macho_patch.py`)

Скрипт патчит бинарники на уровне байт — без сторонних библиотек (`lief`, `macholib`).

**Поддерживаемые форматы:**

- Тонкие бинарники: `arm64`, `armv7`, `x86_64`
- FAT/Universal бинарники (`0xCAFEBABE` / `0xBEBAFECA`)
- Little-endian и big-endian заголовки

**Что меняется в бинарнике:**

```
До:   LC_LOAD_DYLIB      (0x0000000C)
После: LC_LOAD_WEAK_DYLIB (0x80000018)
```

Это означает, что `dyld` при отсутствии библиотеки возвращает `NULL` вместо того чтобы завершить процесс с `SIGABRT`. Приложение продолжает работать.

**Патч происходит ДО физического удаления фреймворков** — иначе патчить уже нечего.

-----

### Удаляемые фреймворки

|Файл                     |Причина удаления     |
|-------------------------|---------------------|
|`StoreKit.framework`     |Проверки App Store   |
|`AppStore.framework`     |Проверки App Store   |
|`iTunesStore.framework`  |Проверки iTunes Store|
|`Adjust.framework`       |Аналитика / трекинг  |
|`AppsFlyer.framework`    |Аналитика / атрибуция|
|`Firebase.framework`     |Аналитика Google     |
|`SecurityCheck.framework`|Проверка целостности |
|`ProtectorLib.dylib`     |Защита от модификации|

-----

### Удаляемые файлы подписи

|Файл / Папка              |Описание                   |
|--------------------------|---------------------------|
|`_CodeSignature/`         |Хэши всех файлов приложения|
|`SC_Info/`                |Данные подписи SuperCert   |
|`embedded.mobileprovision`|Профиль распространения    |
|`CodeResources`           |Список ресурсов с подписью |

-----

### Обновление Bundle ID

Скрипт меняет идентификатор во всех местах, где он встречается:

```
Info.plist
  ├── CFBundleIdentifier          ← главный ID
  ├── CFBundleURLTypes
  │     ├── CFBundleURLName       ← если содержит старый ID
  │     └── CFBundleURLSchemes[]  ← если содержит старый ID
  ├── WKAppBundleIdentifier
  ├── WKCompanionAppBundleIdentifier
  └── NSExtension
        └── NSExtensionAttributes
              └── WKAppBundleIdentifier

PlugIns/*.appex/Info.plist        ← расширения приложения
```

-----

## ⚠️ Ограничения

**Что скрипт НЕ делает:**

- Не переподписывает `.dylib` по отдельности — для этого нужен `codesign` (macOS) или `zsign`
- Не создаёт stub-заглушки с реальными символами — нужен компилятор
- Не обходит jailbreak detection в коде приложения

**Если приложение крашится после установки:**

1. Проверь вывод скрипта — он укажет на подозрительные `.dylib`
1. Переподпиши вложенные `.dylib` через `zsign` или `codesign` на macOS
1. Возможно, приложение использует дополнительную проверку целостности в коде — это за пределами возможностей файлового патча

-----

## ❓ FAQ

**Q: Нужен ли jailbreak?**  
A: Нет. Скрипт работает с файлами, а не с системой. Установка готового IPA через AltStore / SideStore тоже не требует jailbreak.

**Q: Почему приватный репозиторий?**  
A: Инструмент предназначен для личного использования. Публичное распространение модифицированных IPA может нарушать условия использования App Store.

**Q: Какую версию Pythonista скачать?**  
A: Pythonista **3.4** — последняя актуальная версия с Python 3.10.

**Q: Можно ли использовать только `ipa_patch3.py` без `macho_patch.py`?**  
A: Да. Скрипт выдаст предупреждение и продолжит работу — смена Bundle ID и удаление подписи сработают. Но без патча Mach-O приложение может крашиться если удалённые фреймворки были жёсткими зависимостями.

**Q: Лимит AltStore не тратится?**  
A: Да. Смена Bundle ID позволяет AltStore воспринять его как отдельное приложение, не занимающее слот уже установленного.

-----

<div align="center">

Сделано для использования на iOS с [Pythonista 3](https://omz-software.com/pythonista/)

</div>