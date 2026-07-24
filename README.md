<div align="center">

# ⚙️ IPA Patcher Lite

Патч iOS `.ipa` файлов на чистом Python — без компилятора, без зависимостей, прямо на iPhone.

[![Python 3.6+](https://img.shields.io/badge/Python-3.6+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pythonista 3.4](https://img.shields.io/badge/Pythonista-3.4-FF6B35?style=flat-square)](http://omz-software.com/pythonista/)
[![Platform](https://img.shields.io/badge/Platform-iOS%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![License GPLv3](https://img.shields.io/badge/License-GPLv3-red?style=flat-square)](LICENSE)

</div>

-----

## Что умеет

|Функция                    |Описание                                                                        |
|---------------------------|--------------------------------------------------------------------------------|
|📦 Распаковка IPA           |Извлекает содержимое `.ipa` во временную папку с прогресс-баром                 |
|✏️ Редактирование Info.plist|Имя, версия, номер сборки, Bundle ID через интерактивное меню                   |
|🔑 Смена Bundle ID          |Обновляет идентификатор в `Info.plist`, расширениях и связанных полях           |
|💉 Инъекция твиков          |Вставляет `.dylib` или `.zip` с твиками, патчит пути загрузки                   |
|🖼️ Замена иконки            |Заменяет все иконки приложения своим PNG или JPEG                               |
|📁 Поддержка файлов         |Включает iTunes File Sharing и открытие документов сторонними приложениями      |
|🔍 Просмотр `.app`          |Показывает список файлов внутри бандла (первые 50)                              |
|🧹 Удаление подписи         |Удаляет `_CodeSignature`, `SC_Info`, `embedded.mobileprovision`, `CodeResources`|
|📦 Сборка IPA               |Упаковывает результат обратно с сохранением Unix-прав доступа                   |
|📱 Нативный UI на iOS       |Файловый пикер и диалоги через Pythonista 3 — без терминала                     |

-----

## Как это работает

```
[Выбрать .ipa]
      │
      ▼
Распаковка ZIP → /tmp/ipa_patch_XXXXX/
      │
      ▼
Читаем Info.plist → текущие данные приложения
      │
      ▼
┌──────────────────────────────────────┐
│  Интерактивное меню                  │
│  1. Имя приложения                   │
│  2. Версия                           │
│  3. Номер сборки                     │
│  4. Bundle ID                        │
│  5. Поддержка файлов                 │
│  6. Замена иконки                    │
│  7. Инъекция твиков                  │
│  8. Просмотр файлов .app             │
│  9. Собрать IPA                      │
└──────────────────────────────────────┘
      │
      ├→ Обновление Bundle ID
      │     · Info.plist
      │     · CFBundleURLTypes
      │     · WKAppBundleIdentifier
      │     · NSExtension
      │     · PlugIns/*.appex
      │
      ├→ Удаление подписи
      │     · _CodeSignature/
      │     · SC_Info/
      │     · embedded.mobileprovision
      │     · CodeResources
      │
      ▼
Упаковка → имя_patched.ipa
```

-----

## Структура проекта

```
ipa_patcher/
├── main.py            # Точка входа: UI и основная логика
├── plist_editor.py    # Чтение, запись и патч Info.plist
├── ipa_utils.py       # Распаковка, упаковка, файловые диалоги
├── libsubstrate.dylib # Субтрапт для твиков CYDIA
├── macho.py           # Парсинг Mach-O: LC_LOAD_DYLIB, LC_RPATH, шифрование
├── signature.py       # Удаление файлов и папок подписи
├── substrate.py       # Копирование libsubstrate.dylib в Frameworks/
├── patch_strings.py   # Побайтовая замена строк в бинарниках
└── constants.py       # Константы Mach-O и списки файлов подписи
```

-----

## Установка

### 📱 iPhone / iPad — Pythonista 3

1. Установи [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) из App Store
1. Скопируй все файлы проекта в **Pythonista → Documents**
1. Готово — никаких `pip install`

### 🖥️ macOS / Linux

```bash
git clone https://github.com/andreygirin144-netizen/ipa-patcher.git
cd ipa-patcher
python3 main.py
```

-----

## Использование

### Pythonista 3 (iOS)

1. Открой `main.py` в Pythonista
1. Нажми **▶ Run**
1. Выбери `.ipa` через файловый пикер
1. В меню выбери нужные действия
1. Выбери пункт **9 — Применить изменения и собрать IPA**
1. Подтверди сводку изменений
1. Готовый файл появится в `Documents/имя_patched.ipa`
1. Нажми на файл → **Поделиться** → AltStore или SideStore

### macOS / Linux

```bash
python3 main.py
# Введи путь к .ipa файлу
# Работай с интерактивным меню
# Укажи путь для сохранения нового .ipa
```

-----

## Меню редактирования

|Пункт|Действие                                             |
|-----|-----------------------------------------------------|
|`1`  |Изменить имя (`CFBundleDisplayName` / `CFBundleName`)|
|`2`  |Изменить версию (`CFBundleShortVersionString`)       |
|`3`  |Изменить номер сборки (`CFBundleVersion`)            |
|`4`  |Изменить Bundle ID (`CFBundleIdentifier`)            |
|`5`  |Включить поддержку файлов                            |
|`6`  |Заменить иконку приложения (PNG / JPEG)              |
|`7`  |Инъекция твиков (`.dylib` или `.zip`)                |
|`8`  |Просмотреть файлы внутри `.app` (первые 50)          |
|`9`  |Показать сводку изменений и собрать IPA              |
|`10` |Переключить тип пути: `@rpath` / `@executable_path`  |
|`11` |Переключить встраивание `libsubstrate.dylib`         |
|`0`  |Выйти без сохранения                                 |

Перед сборкой скрипт показывает **сводку всех изменений** и запрашивает подтверждение.

-----

## Инъекция твиков

Перед инъекцией скрипт проверяет, зашифрован ли бинарник (`LC_ENCRYPTION_INFO`). Если IPA зашифрован — инъекция невозможна; его нужно предварительно расшифровать.

Поддерживаемые форматы:

- **`.dylib`** — вставляется напрямую
- **`.zip`** — извлекается, затем все `.dylib` и `.bundle` внутри инъектируются по очереди

Что происходит при инъекции:

1. `libsubstrate.dylib` копируется в `Frameworks/` (встроенная версия или своя)
1. `.dylib` копируется в `Frameworks/`
1. В главный бинарник добавляется `LC_LOAD_DYLIB` с путём к твику
1. Если выбран `@rpath` — добавляется также `LC_RPATH`
1. `.bundle`-ресурсы копируются в корень `.app`

-----

## Что удаляется из подписи

|Файл / Папка              |Назначение                 |
|--------------------------|---------------------------|
|`_CodeSignature/`         |Хэши всех файлов приложения|
|`SC_Info/`                |Данные подписи SuperCert   |
|`embedded.mobileprovision`|Профиль распространения    |
|`CodeResources`           |Список ресурсов с подписью |

-----

## FAQ

**Q: Нужен ли jailbreak?**  
A: Нет. Установка через AltStore или SideStore работает на стоковом iOS.

**Q: Какая версия Pythonista нужна?**  
A: Pythonista 3.4.

**Q: Можно ли откатить изменения?**  
A: Скрипт не изменяет исходный `.ipa` — результат всегда сохраняется в новый файл с суффиксом `_patched`.

---

## Требования

- Python 3.6+
- Стандартная библиотека Python (`zipfile`, `plistlib`, `struct`, `shutil`, `tempfile`)
- Для iOS: [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) (App Store, платное)
- Для инъекции твиков: расшифрованный IPA + `libsubstrate.dylib` (опционально)

---

<div align="center">

Сделано для iOS · работает на Pythonista 3 · GPLv3 License

</div>
