<div align="center">🔧 IPA Patcher Lite

Патч iOS .ipa файлов на чистом Python — без компилятора, без зависимостей

https://img.shields.io/badge/Python-3.6+-3776AB?style=flat-square&logo=python&logoColor=white
https://img.shields.io/badge/Pythonista-3.4-orange?style=flat-square
https://img.shields.io/badge/Platform-iOS%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square
https://img.shields.io/badge/License-MIT-green?style=flat-square

</div>---

📖 Содержание

· Что делает
· Как это работает
· Структура проекта
· Установка
· Использование
· FAQ

---

✨ Что делает

Функция Описание
📦 Распаковка IPA Извлекает содержимое .ipa во временную папку
🔑 Смена Bundle ID Меняет идентификатор приложения в Info.plist и всех связанных полях
🧹 Удаление подписи Удаляет _CodeSignature, embedded.mobileprovision, CodeResources
📁 Сборка IPA Упаковывает результат обратно с сохранением Unix-прав доступа
📱 Нативный UI на iOS Файловый пикер и диалоги через Pythonista 3 вместо терминала

---

🔍 Как это работает

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
        ├──▶ Обновление Bundle ID
        │       Info.plist, CFBundleURLTypes, WKAppBundleIdentifier,
        │       NSExtension, вложенные .appex
        │
        ├──▶ Удаление файлов подписи
        │       _CodeSignature/, SC_Info/, embedded.mobileprovision
        │
        ▼
  Упаковка → имя_patched.ipa
        │
        ▼
  Сохранение в ~/Documents/ (Pythonista) или по пути (CLI)
```

---

📂 Структура проекта

```
ipa-patcher/
├── ipa_patch3.py     # Главный скрипт
└── unpack.py         # Распаковка и упаковка .ipa
```

---

🚀 Установка

На iPhone / iPad (Pythonista 3)

1. Установи Pythonista 3 из App Store
2. Скачай оба файла и перенеси в Pythonista 3 → Documents:
   · ipa_patch3.py
   · unpack.py
3. Готово — никаких pip install

На macOS / Linux

```bash
git clone https://github.com/andreygirin144-netizen/ipa-patcher.git
cd ipa-patcher
python3 ipa_patch3.py
```

---

📱 Использование

Pythonista 3 (iOS)

1. Открой ipa_patch3.py в Pythonista
2. Нажми ▶ Run
3. Выбери .ipa через окно Files
4. Введи новый Bundle ID (например, com.yourname.appname)
5. Готовый файл появится в Documents/имя_patched.ipa
6. Нажми на файл → Поделиться → выбери AltStore или SideStore

macOS / Linux (терминал)

```bash
python3 ipa_patch3.py
```

Удаляемые файлы подписи

Файл/папка Описание
_CodeSignature/ Хэши всех файлов приложения
SC_Info/ Данные подписи SuperCert
embedded.mobileprovision Профиль распространения
CodeResources Список ресурсов с подписью

Обновление Bundle ID

Скрипт меняет идентификатор в:

· Info.plist (CFBundleIdentifier, CFBundleURLTypes, WKAppBundleIdentifier, NSExtension)
· PlugIns/*.appex/Info.plist (расширения)

---

❓ FAQ

Q: Нужен ли jailbreak?
A: Нет. Установка через AltStore/SideStore не требует jailbreak.

Q: Какую версию Pythonista скачать?
A: Pythonista 3.4.

Q: Можно ли использовать только ipa_patch3.py без unpack.py?
A: Нет.

Q: Лимит AltStore не тратится?
A: Да. Смена Bundle ID позволяет установить приложение как отдельное.

---

<div align="center">Сделано для iOS с Pythonista 3

</div>