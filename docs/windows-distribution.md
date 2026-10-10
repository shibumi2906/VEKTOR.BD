# Windows-дистрибутив PinuiRAG

Персональный однофайловый установщик `dist/PinuiRAG-Setup-Windows-x64.exe`, Windows 10/11 x64. Он поставляет Python 3.12.15, PostgreSQL 16.15, Qdrant 1.15.5, локальные ONNX INT8 embeddings/reranker, Poppler 26.09, Tesseract 5.5.3 с Hebrew traineddata и подготовленную БД. Дополнительная установка Python, Docker, runtime или скачивание моделей при запуске не требуется. Для GPT-5.4 mini необходим интернет и собственный ключ.

Установка от текущего пользователя; ярлыки запускают `PinuiRAG.exe`, который использует поставляемый `pythonw.exe`. Окно запуска показывает этап подготовки и кнопку остановки. UI открывается в браузере. Все службы слушают loopback на свободных портах и принадлежат Windows Job Object. Остановка завершает только процессы этой копии приложения.

Данные находятся в `%LOCALAPPDATA%\PinuiRAG\data`. При первом запуске восстанавливаются реестр, оригиналы и индекс; последующие запуски используют эту рабочую папку. Обновление/удаление программы не удаляет её. PostgreSQL получает новый случайный пароль локально. API-ключ вводится в «Настройки GPT-5.4 mini», проверяется до сохранения и защищается DPAPI текущего пользователя. `.env`, ключ разработчика и история запросов/расходов не включены в комплект. Сборка содержит текущие персональные договоры.

В корпусе 18 документов и 3664 активных чанка: 15 общих источников, два договора и один явно помеченный синтетический OCR fixture. Упаковка не подтверждает полноту законодательства или актуальность непроверенных документов; прежние ограничения источников сохранены.

## Подготовка и сборка

Подготовленные build-only компоненты находятся в `data/windows-build/`: Python от python-build-standalone через UV, PostgreSQL из официального архива EDB, Qdrant из GitHub qdrant/qdrant, Tesseract из tesseract-ocr/tesseract, Hebrew tessdata из tesseract-ocr/tessdata_fast, Poppler Windows от oschwartz10612/poppler-windows, Microsoft VC runtime из официального vc_redist.x64.exe, Inno Setup из jrsoftware/issrc. Хеши скачанных компонентов и third-party notices поставляются с комплектом; лицензии Microsoft и других runtime включены.

`scripts/export_desktop_config.py` экспортирует только разрешённые несекретные настройки. `scripts/export_windows_vectors.py` сохраняет точные векторы и payloads переносимым gzip JSONL; Linux RocksDB snapshot не переносится напрямую на Windows. PostgreSQL seed — `pg_dump -Fc` без истории запросов, заданий и расходов. Оригиналы/pipeline экспортированы средствами backup проекта. Исходные Docker volumes не изменяются сборкой.

После подготовки компонентов и seed:

```powershell
& data/windows-build/python-managed/cpython-3.12.15-windows-x86_64-none/python.exe scripts/build_windows.py
$bundleDir = (Resolve-Path data/windows-build/bundle).Path
$outputDir = (Resolve-Path dist).Path
& .tools/inno/ISCC.exe ('/DBundleDir='+$bundleDir) ('/DOutputDir='+$outputDir) packaging/windows/setup.iss
```

Скрипт сборки использует существующий Windows .NET compiler для маленького EXE-launcher. Компоненты устанавливаются только в build-папку; команда выше не выполняет автоматическое скачивание недостающих входов.

## Проверки и границы

`scripts/test_windows_bundle.py` запускается именно поставляемым Python из установленной папки. Он исключает системные Python/Docker из PATH, включает блокировку внешних Python-соединений, проверяет UI/API, отсутствие ключа, общий поиск и поиск по каждому договору, совпадение цитат с оригинальными блоками PostgreSQL, все 3664 вектора/payloads, DPAPI roundtrip, загрузку VC DLL из поставляемого комплекта и остановку.

Проверка не отправляет договоры в OpenAI и не вызывает платный API. Дополнительно выполнены полный набор 141 regression tests, Ruff, 11 targeted tests после изменения Windows OCR subprocess; native Hebrew OCR использовал поставляемые Poppler/Tesseract. Фактические отчёты находятся в `data/windows-build/*acceptance*.json`; итог установки/рестарта записан в `docs/progress.md`.

Чистая Windows VM / Windows Sandbox на этом компьютере недоступны. Проверки выполнены в отдельной установленной папке на текущей Windows с ограниченным PATH и отключённой внешней Python-сетью. Это подтверждает независимость проверенного сценария от системных Python/Docker; совместимость с чистой VM пока не подтверждена. Live GPT-ответы и сравнение договоров этой сборкой в offline-проверку не входят.
