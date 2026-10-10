# Состояние PinuiRAG

Дата: 10.10.2026 (Asia/Jerusalem). **Локальное приложение запущено: http://localhost:8510. Вход и роли в интерфейсе удалены по поручению пользователя; AUTH_MODE=local, все документы доступны владельцу компьютера.** API/UI публикуются только на loopback.

Реализованы реестр, PDF/DOCX/OCR, чанки настоящего tokenizer, hybrid Qdrant search, reranker, durable jobs, перевод/ответы/тематическое сравнение, источники/актуальность, API, UI и backup/restore. **Полная приёмка всех T01–T14 ещё не завершена:** live сравнение частных договоров ожидает разрешения на отправку фрагментов в OpenAI; нет реальных проверенных цепочек 16 законов и 2 актов о шамае; остаётся ручная Hebrew/табличная и multilingual QA. Незавершённые проверки не объявлены passed.

## D01 — однофайловая Windows-сборка — 10.10.2026

Исправление доступа к вводу ключа после демонстрации: на скриншоте пользователя был порт 56127 — завершённая QA-копия из `entrypoint-profile`, оставшаяся в Chrome. Статус CONNECTING блокировал все поля; код ввода ключа уже присутствовал. Установлена обычная рабочая копия в `%LOCALAPPDATA%\Programs\PinuiRAG`, используется постоянная рабочая папка `%LOCALAPPDATA%\PinuiRAG\data`. Открыт и оставлен работающим интерфейс `http://127.0.0.1:62684`; реальная browser-проверка подтвердила активное password field и кнопку сохранения, тестовый текст введён и очищен без submit/OpenAI calls. Screenshot: `data/windows-build/key-entry-working.png`. Ключ пользователя не читался и не вводился агентом. Изменять/пересобирать установщик для этого не требовалось.

Создан `dist/PinuiRAG-Setup-Windows-x64.exe`: 471571754 байта (~450 MiB), SHA256 `e917c8951ab7a06308e90ffd6799cef3b754ef72e8c1257bfae9cf3bd8fa3d2a`. Включены Python 3.12.15, PostgreSQL 16.15, Qdrant 1.15.5, две локальные ONNX модели, Poppler/Tesseract Hebrew OCR, реестр/оригиналы и 3664 вектора для 18 документов. Отдельная установка Python/Docker и скачивание моделей при запуске не требуются. Установщик личный, содержит текущие договоры; API-ключ разработчика и история запросов/расходов исключены.

Добавлены Windows launcher с окном состояния, однофайловая сборка Inno Setup, локальная DPAPI защита ключа, portable vector export/import, отдельная рабочая папка данных и Windows Job Object для завершения процессов. Linux RocksDB snapshot оказался непереносимым; заменён точным экспортом векторов/payloads, без повторного вычисления embeddings. Системные сервисы и исходные Docker volumes не изменялись.

Passed: 141 regression tests с PostgreSQL/Qdrant, Ruff; после последнего изменения OCR — 11 targeted tests; documentation checker — 277 требований. Native комплект запускался с PATH без системных Python/Docker и блокировкой внешней Python-сети: 18 документов, 3664 вектора, поиск по общим документам и обоим договорам (6/2/1 citations), все цитаты сверены с оригиналами, все векторы/payloads совпали, 0 платных вызовов. UI health HTTP 200. DPAPI encrypted save/restore — passed; VC runtime действительно загружен из комплекта. Native Hebrew OCR — passed (1289 символов, confidence 90.771, 38 строк координат).

Первый и финальный установщики успешно установлены в отдельную папку с пробелом, exit code 0. Финальная offline-приёмка на новой рабочей базе passed: `data/windows-build/installed-acceptance-final.json` — первый запуск 30.05 s, полный контроль 81.16 s; 18 документов, 3664 точных вектора/payloads и 6/2/1 citations, DPAPI и bundled VC DLL passed. Это измерение текущего компьютера, не универсальный performance target. Настоящий `PinuiRAG.exe` также запущен с отдельным тестовым LOCALAPPDATA: UI HTTP 200, все 18 оригиналов скачаны с серверной проверкой hash, встроенный OCR passed (`exe-entrypoint-acceptance.json`). После остановки все 12 служебных процессов двух проверок завершились. Контроль рестарта и удаления тестовой установки записывается отдельно ниже. Отчёты подготовки: `native-acceptance.json`, `native-acceptance-restart.json`, `runtime-dependencies.json`, `installer-build-final.log`. Инструкция: `docs/windows-distribution.md`.

Not_run: чистая Windows VM / Sandbox недоступны на этом компьютере; проверка текущей Windows в отдельной папке с ограниченным PATH не выдаётся за VM. Новые live GPT-вызовы и сравнение частных договоров не выполнялись. GPT-5.4 mini требует интернет и свой ключ; непроверенный законодательный корпус остаётся непроверенным. Следующий отдельный контроль совместимости — установка на чистую Windows 10/11 x64.

Финальный рестарт passed: `installed-acceptance-final-restart.json` — запуск 8.55 s, полный контроль 65.98 s, сохранены 18 документов и все 3664 точных вектора/payloads; 6/2/1 citations, DPAPI и DLL audit прошли повторно. Все запросы offline, платных вызовов 0. Тестовая программа удалена штатным uninstaller (exit code 0): рабочая БД, все 18 оригиналов и защищённый тестовый ключ сохранены отдельно, установленный launcher удалён (`uninstall-acceptance.json`). Все процессы финальной проверки завершены. Сам EXE в `dist` сохранён; исходное приложение Docker не менялось.

## Подключение OpenAI — 10.10.2026

Ключ введён пользователем локально в .env, значение не выводилось. Перезапущен только API. Model access HTTP 200; live /query по публичному стандарту 21.1: answered / ru, одна подтверждённая claim и две цитаты; translation, generation, semantic validation использовали gpt-5.4-mini. Отчёт без ключа и текста договоров: data/openai-live-check.json. Автоматическая проверка разрешений отклонила отправку частных договоров для сравнения; запрошено отдельное разрешение пользователя. Полная приёмка и сравнение пока не подтверждены.

## Направление текста, терминология и область поиска — 10.10.2026

Решение пользователя: искать во всех документах, включая договоры. Default API/UI — all_documents; current_norms остаётся строгим выбором, непроверенные юридические цепочки исключены. Native dir=auto на textarea/text inputs (MutationObserver только DOM оформления), auto/isolated paragraph direction на ответах, цитатах и сравнении; browser verified Hebrew RTL и Russian LTR. Добавлен source-labelled словарь config/terminology.json для адвоката собственников, собственников, оценщика, организатора и застройщика; это словарь перевода, не юридическое доказательство. Перевод проверяет сохранение роли. Generation/verdict проверяют оригинальный вопрос и роль, требуют маркировать рекомендации/договоры.

126 tests passed с PostgreSQL/Qdrant; Ruff passed. Live GPT-5.4 mini: термин адвоката переведён правильно, public lawyer guidance даёт ответ с 6 цитатами; тот же вопрос в current_norms возвращает insufficient_evidence, без ответа про оценщика. Локальный поиск по каждому частному договору: search_results, 15 и 11 источников; фрагменты договоров в OpenAI в этих проверках не отправлялись. data/language-fix-report.json и data/rtl-ui-check.png. После уточнения маркировки источников повторный live public answer: answered / 1 citation, рекомендация обозначена в тексте ответа; итоговые 19 targeted tests passed, Ruff passed. Полная multilingual/legal приёмка остаётся незавершённой.

## Исправление CITATION_SCOPE_MISMATCH — 10.10.2026

Убрана генерация моделью block/chunk UUID и Unicode offsets. В context каждому оригинальному span назначен request-local evidence_id; строгая schema ограничивает evidence_ids enum текущего запроса. Backend разрешает ID в точные сохранённые координаты, проверяет original_text и scope. Неизвестная ссылка исключает весь claim; координаты не округляются и не расширяются. Второй semantic verdict и revalidation сохранены. Изменение REQ-CITE-01 — способ привязки, требования точности не ослаблены.

128 tests passed с PG/Qdrant, Ruff passed. Live GPT-5.4 mini по общим документам: исходный русский вопрос об адвокате answered / 5 sources / 11.17 s; Hebrew вопрос об оплате оценщика answered / 1 source / 7.17 s. Все цитаты отдельно сверены с оригинальными блоками PG. Частные договоры не отправлены во внешнюю модель в этих тестах; полная live проверка с ними остаётся pending. Метрики: data/citation-fix-live-report.json. API пересобран и перезапущен.

## Понятный ответ и компактные источники — 10.10.2026

UI показывает проверенные claims группами по исходным документам/редакциям, с нумерованными ссылками. Договор, проект договора, образец и рекомендации имеют отдельные подписи. Полные цитаты на иврите, актуальность, официальный URL и оригинал доступны в свёрнутом блоке. Режимы ответа подписаны по-русски. Поиск по умолчанию all_documents сохранён.

app/citations/presentation.py добавляет отдельную короткую переводную выдержку и перевод названия. quote_excerpt — точная подстрока оригинала до 240 символов; quote, offsets и immutable citations не изменяются. Проверяются язык, числовые маркеры и семантическая верность отдельным verdict; одна ограниченная повторная попытка только для отсутствующих переводов. Ошибка optional-перевода сохраняет ответ; исчерпание бюджета получает понятное пояснение в UI. Все вызовы используют существующие ограничения затрат.

Passed: 134 tests с PostgreSQL/Qdrant, Ruff; после последнего изменения пояснений о бюджете 16 targeted tests passed. Live public UI: answered / ru, 5 claims / 6 sources, пронумерованные ссылки, оригиналы свёрнуты; фактические вызовы gpt-5.4-mini. Последний запрос не выполнил перевод цитат из-за дневного резерва 0.996348 USD при лимите 1 USD. Лимиты и учёт не сбрасывались. Отдельная предыдущая live проверка слоя перевода дала 5/5 принятых переводов с сохранёнными числами. Это не объявляется полной multilingual приёмкой. Частные договоры в этих live проверках не отправлялись в OpenAI.

Метрики последнего PUBLIC ответа: data/readable-answer-check.json; screenshot: data/readable-answer-ui.png. scripts/check_presentation_report.py экспортирует только публичный отчёт после проверки project_id, печатает только метрики. API/UI пересобраны и запущены.

## Текущее состояние этапов

Дополнение: REQ-KEY-01–02 реализованы. Боковая панель «Настройки GPT-5.4 mini»: password input, проверка/сохранение, проверка текущего ключа, понятные ошибки. API /settings/openai доступен только в личном режиме, возвращает статус без секрета. Проверка — GET модели в OpenAI, без отправки документов или генерации. Новый ключ атомарно сохраняется в runtime/openai-key.json (0600 в Docker) после проверки, восстанавливается при запуске и активируется сразу. Это локальное файловое хранение, не заявляется шифрование Windows. Секрет не добавляется в образ/репозиторий. Некорректная замена сохраняет прежний ключ.

141 tests с PG/Qdrant passed, Ruff passed; 7 новых credential tests используют только synthetic key и mock HTTP. Browser UI проверен: кнопка проверки существующего ключа вернула «Доступ к GPT-5.4 mini подтверждён»; документы не передавались, новый реальный ключ в тестах не вводился. Screenshot data/api-key-settings-ui.png. Последующая Windows-сборка и DPAPI проверка описаны выше в D01.

| Этап | Состояние | Результат / оставшееся условие |
|---|---|---|
| T01 | done | Docker, runtime, frozen lock, документация |
| C01 | partial | 15 сохранённых public PDF; 16 сводных законов и 2 акта отсутствуют |
| T02 | done locally | Реестр, проекты, review/audit, resolver, pagination, local access; миграции с пустой БД |
| T03 | partial | PDF/DOCX/OCR/табличные координаты работают; неоднозначные структуры и Hebrew требуют ручной проверки |
| T04 | implemented | Tokenizer E5, точные spans, immutable revisions; ручная corpus QA остаётся |
| T05 | done locally | Две embedding-модели, reranker 256/512, development/holdout, SHA/revisions/licenses |
| T06 | done locally | Реальный hybrid dense/BM25/RRF + reranking в ограниченном PG scope |
| T07 | done locally | Atomic activation, vector verification/cache, lease/heartbeat/checkpoints; forced-restart recovery |
| T08 | partial | Языки, перевод, сохранение чисел, ограничения реализованы; live RU→HE translation passed на стандарте 21.1; broader multilingual QA pending |
| T09 | partial | Hebrew search принят; LLM claims/citations/verdict реализованы, live русский ответ по стандарту 21.1 с двумя источниками passed; broader QA pending |
| T10 | partial | Отдельный поиск A/B, тема/уточнение, проверка difference; live compare not_run |
| T11 | partial | Compiler/provenance/date/facts gate и safe source rechecks; реальные цепочки отсутствуют |
| T12 | partial | HTTP/OpenAPI/DTO/errors/jobs/upload/local E2E; live translation/answer HTTP E2E passed; comparison pending |
| T13 | implemented locally | Streamlit без входа, четыре вкладки, RTL quotes, originals, jobs; live features pending |
| T14 | partial | Local quality/performance + restore passed; live cost/groundedness/comparison и ручная QA pending |

## Данные и модели

15 общих PDF, 205 страниц; два локальных договора 04.2025 DOCX и 08.2025 PDF (78 страниц). Третий закрытый проект содержит один явно помеченный синтетический Hebrew OCR fixture для E2E; это не реальный нормативный документ. Всего **18 indexed documents / 3664 active chunks**: 950 public, 2713 private contract, 1 synthetic OCR.

Стандарт 21.1 verified/current/in_force; остальные 14 общих источников manual_review/unknown. Договор DOCX draft_contract, PDF contract; подписание/применимость не подтверждены. 16 legal_laws, **0 reviewed chains / 0 реальных юридических снимков**. Удалённые исторические PDF и поправки не возвращены. Current norms не используют неизвестные/просроченные документы. Неизменный PDF не продлевает юридическую проверку.

Выбран intfloat/multilingual-e5-small (384 dimensions, ONNX INT8, query:/passage:) и cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 (512 tokens, ONNX INT8). Фиксированные revisions/SHA; actual model tokenizer, 480/16 chunking. GPT-5.4 mini + GPT-4.1 mini fallback, Responses JSON schema/store=false. OPENAI_API_KEY настроен; API перезапущен, доступ к gpt-5.4-mini подтверждён HTTP 200. Решения и первичные benchmark metrics: docs/model-decisions.md.

Hardware: Windows, 12 logical CPU, 15.7 GiB RAM; Docker около 7.6 GiB, другие проекты сохранены. ORT 2 CPU threads / inter-op 1. uv.lock: 90 resolved packages; Linux install 85.

## Реализованное поведение и ограничения

- OOXML body order, paragraph/table/row/cell locators, inherited list styles/start overrides, letters/Roman/Hebrew labels. Исходный текст не дописывается автоматически номерами; label хранится как structure metadata. Unsupported formats предупреждают. DOCX не получает выдуманные PDF pages.
- PDF text layer, page-level Hebrew OCR (confidence ≥80), bbox/TSV line mapping; real synthetic scan confidence 92.34. PDF table cell сопоставляется только однозначно с исходным диапазоном; сложная/неоднозначная структура помечается для review. Полная ручная верификация всех таблиц/колонтитулов/сносок не завершена.
- Hybrid retrieval с доступом/фильтрами до поиска, exact clause lookup, bounded glossary expansion, calibrated rerank cutoff, immutable generation checks. Backend восстанавливает цитаты из PG; overlapping search citations объединяются по document/revision/block. Не найденное условие не объявляется отсутствующим.
- Перевод проверяет числа/даты; answer состоит из claims с validated original spans и отдельным evidence verdict. Сравнение имеет citations A/B, difference только после проверки обеих сторон. Offline provider tests не доказывают реальное качество GPT.
- Persistent jobs, idempotency conflicts, source checks, checksummed vector cache, per-attempt lease fencing перед activation. Stale worker не переключает активный индекс. Active collection fingerprint bb337bae2d12f3e35769d187a7dd33ffdeb1689a0ecf4843fcc1cc292df9051d.
- Резервы цены до provider calls: $0.20/query, $0.40/compare, $1/day. Actual provider usage сохраняется; Первый live RU→HE→RU ответ: 10.21 s, 3 вызова gpt-5.4-mini, 1 claim / 2 sources, расчётная стоимость по сохранённому usage $0.007689.
- Personal local UI открывает документы без токена. Чужие Host/Origin отклоняются. Совместимый token backend сохранён технически, но не используется личным UI. .env/договоры/data/backups исключены из Git; ACL/шифрование backup не объявлены настроенными.

## Итоговые проверки

| Проверка | Статус | Результат / доказательство |
|---|---|---|
| Полная регрессия с PostgreSQL/Qdrant | passed | **122 passed**, одна upstream Starlette/AnyIO deprecation; Docker Python 3.12 |
| Ruff check / format | passed | app/tests/scripts/ui; final source check |
| Все миграции | passed | Отдельная пустая БД → 0004 → 0008; временная БД удалена |
| Parsing всего зарегистрированного корпуса | passed | scripts.parse_registered_corpus; data/parsing-final-report.json |
| Staged index / payload / dense+sparse vectors | passed | 18 documents, 3664 points, проверка каждого Qdrant point, exact PG generation links |
| Development / independent holdout baseline | passed | 60 dev/30 holdout; E5 rerank-512 MRR 0.8491 dev / 0.9111 holdout, R@10 0.9667 / 1.0; первоначальный parsing baseline, reports не перезаписаны |
| HTTP holdout на окончательном индексе | passed | **30/30** ожидаемых clauses; все цитаты exact original spans; 0/5 negative false accepts |
| Нагрузка 1–2 пользователя | passed locally | p95 **6.27s / 11.43s**, 5 / 10 запросов; data/acceptance-local.json |
| Повторная индексация без legacy manifest | passed | PG active revisions → тот же fingerprint/3664 points; старый manifest восстановлен после проверки |
| Crash / resume drill | passed | Worker SIGKILL; job 5ce9435f-6469-49db-badd-5ae9f1fa4f32 completed attempt=2; parse checkpoint сохранён, прежний индекс оставался активным |
| HTTP личного режима | passed | Без Authorization видны все 18 документов и 2 договора; pagination/resolver/original SHA/Query DTO/clarification/missing-key/foreign-origin/errors — data/http-final-report.json |
| UI без входа | passed | Browser: четыре вкладки, token field отсутствует; AppTest: Hebrew search_results, 6 exact sources, exceptions/errors отсутствуют |
| Backup / restore | passed | data/backups/20261010-final: PG, raw files реально extracted/SHA-verified, config, **84 parsing artifacts**, Qdrant restored in isolated collection, все 3664 payload/dense/sparse vectors совпали |
| Документация / secrets exclusions | passed | 274 unique REQ IDs, 58 sections, 14 stages; .env/data/contracts ignored |
| Live GPT / перевод / groundedness / topic accuracy / стоимость | not_run | OPENAI_API_KEY absent |
| Ручная Hebrew/multilingual/complex-table QA | not_run / partial | Требуется независимая проверка корпуса/ответов; синтетические tests её не заменяют |
| Юридическая комплектность | blocked by data | 16 реальных цепочек и 2 акта отсутствуют; неподтверждённые нормы не индексируются как действующие |
| Remote CI | not_run | Репозиторий не опубликован, commits/push не выполнялись |

Targets в benchmarks/acceptance-profile.yaml — предложены после local baseline, не предзарегистрированная полная приёмка. Indexing throughput и live comparison p95 ещё не измерены. Небольшой Hebrew holdout с explicit document scopes не подтверждает качество всех языков, всего открытого корпуса или юридическую полноту.

В процессе исправлены устаревшее ожидание registered в тесте реестра, ошибки OCR page indexing, numbering inheritance, overlapping citations, admission of historical originals без reviewed snapshot, cancellation/lease fencing. HTTP verifier сначала ожидал отсутствовавшие size/SHA metadata: document details расширен, итоговая проверка прошла. Acceptance CLI сначала не находил benchmarks внутри image: Dockerfile исправлен. Итоговый Ruff исправил unused import. Старые/неуспешные попытки не выдаются за итоговый passed.

## Оставшаяся работа

Настроить OPENAI_API_KEY локально и выполнить бюджетные live-проверки GPT-5.4 mini (перевод/ответы/тематическое сравнение), затем ручную quality/cost приёмку. Получить документальные основания и проверить реальные legal chains 16 законов и 2 недостающих акта. Проверить неоднозначные Hebrew таблицы/структуру и расширить negatives/ручной эталон. Исторический режим по необработанным оригиналам блокируется; исторические законы поддерживает reviewed-chain compiler.

Настройки/команды: docs/operations.md. Приложение работает без LLM-ключа; отсутствующие внешние данные/ключ не скрыты ложным состоянием полного выполнения.

---

## Исторический журнал до выполнения полного плана

# Состояние PinuiRAG

Дата: 2026-10-09 (Asia/Jerusalem). T01: done. C01: partial (после очистки отсутствуют 16 полных актуальных законов и 2 акта о шамае). T02: partial — отдельный реестр содержит 15 документов; доступ/CRUD/resolver ещё pending. T11: partial — реализовано ядро проверки актуальности законов; реальные цепочки и подключение поиска pending. T03/T04: partial — 15 PDF, 1262 блока, 842 staged чанка. Остальные T05–T14 (кроме T11): pending.

## Выполненная работа

- Созданы структура проекта, Settings, system DTO, FastAPI health/readiness и единые безопасные ошибки с request_id.
- Созданы lifecycle worker/scheduler (обработка jobs ещё не реализована) и Streamlit страница состояния.
- Docker использует существующие Python 3.12/uv и PostgreSQL 16-alpine образы по digest; отсутствующий Qdrant v1.15.5 скачан и закреплён по digest.
- Прямые установленные Python-пакеты переиспользованы по версиям, полный граф фиксируется uv.lock (74 packages, 69 установлены на Linux Python 3.12). Исключение: FastAPI 0.121.3/Starlette 0.50.0 выбраны для совместимости с установленным Streamlit 1.58.0; конфликт и решение зафиксированы в ADR-001. Глобальные пакеты Windows не изменены.
- Спецификация перенесена в docs/specification.md, версия 1.4; добавлены стабильные REQ-EXT IDs, матрица требований, AGENTS, README, ADR-001, CI, inventory и placeholders моделей/приёмки/эксплуатации.
- Инициализирован локальный Git без коммитов/remote. .env с локальными credentials создан без вывода секретов; OPENAI_API_KEY пуст. Договоры и .env исключены из Git и Docker context.

## Изменённые контракты

APP_MODE=bootstrap явно разрешает запуск T01 до выбора моделей. Production validation требует настройки local models; production pipeline пока отклоняется, не подменяется mock. `/status` scope=bootstrap_infrastructure; компоненты незавершённых pipeline имеют not_implemented, соответствующие capabilities=false независимо от наличия ключа.

## Проверки

| Проверка | Результат | Доказательство / причина |
|---|---|---|
| Инвентаризация runtime и Docker | passed | Python 3.13.2 Windows; существующий Docker Python 3.12.12/uv 0.9.30; Docker Engine 28.0.1 |
| uv lock | passed | Итоговый lock: 74 packages; создан на Python 3.12.12, uv 0.9.30 |
| docker compose config --quiet | passed | Код выхода 0 перед build |
| Clean install / build | passed | docker compose up --build -d, зависимости установлены по --frozen lock |
| Ruff lint | passed | docker compose run --rm --no-deps api uv run --frozen --group dev ruff check . |
| Ruff format | passed | Аналогично ruff format --check .; дополнительно проверены host sources |
| Unit tests | passed | Аналогично pytest -q: 10 passed; конфигурация, отказ зависимостей, heartbeat, no-key startup, redaction, error envelope |
| Запуск API и инфраструктуры без LLM-ключа | passed | Все шесть сервисов запущены; PostgreSQL, Qdrant и lifecycle процессов проверены реальным /status |
| HTTP health/readiness и UI | passed | python scripts/smoke_bootstrap.py: /health 200, /status 200, UI root/health 200; llm_configured=false, product capabilities=false |
| Выполнение страницы Streamlit | passed | AppTest.from_file('ui/main.py').run() внутри ui container; app.exception пуст |
| Целостность требований и плана | passed | python scripts/check_documents.py: 269 уникальных IDs, полная матрица, 58 разделов, 14 этапов |
| Исключение секретов и договоров из Git | passed | git check-ignore подтвердил .env и оба локальных договора; Git без коммитов/remote |
| CI в удалённом runner | not_run | Репозиторий не опубликован; workflow только создан |
| Backup/restore и production quality | not_run | T07/T14; не входят в T01 |

## Нерешённые вопросы

Модели/OCR, acceptance limits и реальные LLM credentials пока не выбраны/не заполнены; первичный corpus и sources.yaml подготовлены на C01, юридическая актуальность pending; это результаты последующих задач. CI не запускался в удалённом сервисе. DOCX не синхронизирован; актуален Markdown.

При первых проверках исправлены разбор OPENAI_STORE=false и несовместимость старого FastAPI со Streamlit. Попытка unit tests в глобальном Windows Python завершилась отсутствием asyncpg; принятая среда — Docker, в ней тесты прошли. HTTP из sandbox был недоступен, проверки повторены с разрешённым локальным сетевым доступом. Smoke до завершения пересборки UI не прошёл; итоговая проверка после запуска прошла. В unit runner остаётся upstream DeprecationWarning Starlette/AnyIO; отказов нет. AppTest выводит ожидаемое предупреждение о ScriptRunContext в bare mode; исключений страницы нет.

## Следующий шаг

Первое незавершённое требование пользователя — C01: получить по одной полной подтверждённой актуальной редакции 16 законов. Старые тексты удалены по поручению пользователя; недоступность сводных текстов явно отражена в coverage_gaps (ещё 2 пробела — акты о шамае). У пользователя нет доступа к Нево/Такдин. Независимая часть T02 — actors/grants, защищённый CRUD, aliases/resolver и подтверждение/current с audit — ещё pending. Текущий UI показывает состояние, поиск ещё не реализован. Контейнеры проекта запущены: API http://localhost:8010, UI http://localhost:8510.

## C01 — исправленный порядок и скачивание корпуса

Статус: partial — законы скачаны, дополнительные нормативные документы ещё требуют загрузки. План 1.2 и спецификация 1.5 согласованы с поручением пользователя: документы → БД → интерфейс. Официальные файлы скачиваются до T02, актуальность редакций проверяется отдельно. API-ключ для этого не требуется.

Сохранены 207 официальных PDF, 3285 страниц; основные тексты 16 законов, поправки и errata. URL/hashes/ошибки: `data/corpus-manifest.json`; список пробелов и покрытие: `docs/corpus-status.md`. БД пока не наполнена.

| Проверка C01 | Состояние | Доказательство |
|---|---|---|
| Реальное скачивание | passed_with_gaps | 207 PDF; пять ошибок URL сохранены, часть имеет официальные альтернативы; пять дополнительных нормативных документов пока не получены |
| SHA-256 / открытие PDF / все page objects | passed | inspect_corpus.py: 207 passed, 0 failed, 3285 pages |
| Иврит в первых трёх страницах | passed | во всех 207 PDF; это не полная проверка OCR/RTL |
| Визуальные образцы | passed | первые страницы законов 2006, 1965 и 2026 через pypdfium2 |
| Security/immutability tests | passed | 10 новых offline tests в существующем Docker |
| Ruff | passed | ruff check . |
| Требования/план | passed | 270 IDs, 58 sections, T01–T14 + C01 |
| Действующие сводные редакции | pending | manual_review; current_norms не активирован |
| Векторная индексация | not_run | T02–T07; ключ LLM не нужен |

Следующий незавершённый пункт — дополнить нормативный комплект C01 по corpus-status.md; затем T02–T07 создают БД, после этого общение и интерфейс. HTTP 403 официальных приложений и недоступные полные подзаконные акты не скрыты.

Итоговая регрессия: pytest -q — 20 passed (одно ранее известное upstream предупреждение); ruff check . и format --check новых файлов — passed.

## C01 — обязательный стандарт 21.1

По поручению пользователя стандарт 21.1 закреплён как обязательный в REQ-SRC-04 и плане C01. Полный утверждённый документ июня 2022 скачан из архива минаэлет Холона; исходный gov.il URL с HTTP 403 сохранён как provenance, альтернативный источник внесён в sources.yaml. SHA-256, approval_date и URL зарегистрированы.

Текущий итог: 208 PDF, 3309 страниц; четыре обязательных подзаконных документа ещё не получены. C01 остаётся partial. Индексация и проверка юридической актуальности не выполнены.

Проверки: inspect_corpus.py — passed (208 PDF, 0 failures, hash и все page objects); титульная страница — passed (визуально подтверждены номер 21.1, 24 страницы и утверждение 01.06.2022); tests/test_corpus_download.py — passed (13 tests); check_documents.py — passed (270 IDs, 58 sections, 14 tasks). Ruff check и format --check изменённых файлов — passed.

## C01 — подтверждение стандарта 21.1

Проверка 09.10.2026: оригинал gov.il успешно получен через установленный PowerShell Invoke-WebRequest. Утверждение 01.06.2022; публикация и начало действия 13.06.2022 прямо указаны в пункте 10. Переходные правила пункта 11 сохраняются. Подтверждено продолжение использования базового стандарта в официальных инструкциях 22.12.2025 и 25.02.2026; заменяющая редакция в проверенных источниках не найдена. gov_standard21: verified/current/in_force; доказательства, checked_at и source_checks сохранены. Это проверка конкретного профессионального стандарта, а не подтверждение всего законодательного корпуса.

Дополнения 2025/2026 скачаны и сохранены отдельно; пункт 7 каждого ограничивает применение стадией плана. Их даты/применимость остаются manual_review до отдельной проверки. Не применять автоматически к договорам 04.2025/08.2025. Копия из Холона сохранена; SHA-256 отличается, текстовые различия на страницах 1/22 проверены. Предпочтительный источник — gov.il.

Текущий корпус: 211 PDF, 3343 страницы. Проверки PDF/hash/page objects — passed (211, 0 failures); визуальная проверка страницы 19 — passed; БД и индекс — not_run (T02–T07). Проверка документов — passed (270 IDs). C01 остаётся partial из-за остальных четырёх подзаконных документов.

## C01 — организаторы, адвокаты и обязательные источники

По поручению пользователя скачаны 12 новых PDF: рекомендации об организаторах и их оплате (2024), рекомендации об адвокатах (2022), решение по этике ат/67/21, руководство и формы представительства жильцов, образец договора юридических услуг, образец договора с застройщиком и руководство к нему, полные нормативные публикации о собрании и отмене сделки. Для всех зарегистрированы орган/автор, тип источника, URL, SHA-256 и retrieval headers при наличии.

REQ-EXT-25-01 уточнён: всегда показывать источник, редакцию/дату, страницу/пункт и тип документа; рекомендации/образцы не представлять как обязательные нормы или подписанные договоры. Реализация answer/citation pipeline остаётся T09, не заявлена работающей.

Текущий корпус: 223 PDF, 3514 страниц. inspect_corpus.py — passed (223, 0 failures); Hebrew sample text — passed; визуальные образцы адвокат/организатор/этика/КТ9992 — passed. Security tests — passed (20 tests); Ruff check и format --check — passed. check_documents.py — passed (270 IDs); curated URLs/source IDs и уникальность download_id — passed. Первая format-проверка потребовала форматирования нового условия allowlist; после исправления passed.

C01 partial: два обязательных оригинала по назначению и оплате шамая не получены; официальный/муниципальный источник не найден после повторных поисков. Закрыты пробелы загрузки собраний и отмены сделки. БД не наполнена; новые документы manual_review, шаблоны template/not_applicable.

## T02 — отдельный реестр скачанных документов

По прямому поручению пользователя создана отдельная схема registry в PostgreSQL этого проекта; Alembic revision 0001_registry применена к реальной БД. document_register показывает документы и происхождение независимо от Qdrant. Реестр содержит 223 PDF (3514 страниц), 7 источников, 228 записей загрузок/проверок, включая 5 ошибок, 2 coverage gaps и 223 audit events регистрации. Оригиналы проверены по SHA-256 и скопированы в закрытый raw-data volume; project contracts пока не импортированы до реализации grants.

Сохранены названия, типы, авторы/органы, URL, даты/редакции, hashes, страницы, подробные metadata/provenance и раздельные legal/version/verification/ingestion статусы. Все документы ingestion_status=registered; векторного индекса ещё нет. Семейства обозначают исходные публикации; тематические связи с несколькими законами находятся в document_topics. Повторный импорт не сбрасывает ручное подтверждение и не создаёт дубликатов; новая контрольная сумма создаёт отдельную редакцию.

Проверки: Alembic upgrade на пустой БД и повторный upgrade — passed; повторный импорт — passed (счётчики неизменны); оригиналы/hash — passed; PostgreSQL constraints и создание схемы в пустом изолированном namespace с rollback — passed; полная pytest регрессия — 36 passed (одно известное upstream предупреждение). Ruff check и format --check — passed после исправления длинной SQL строки теста. Проверка документации — passed (270 IDs, 58 sections, 14 tasks).

T02 остаётся partial: защищённые HTTP CRUD, projects/actors/grants, aliases/resolver и административные операции подтверждения/current с audit ещё не реализованы. CLI — локальный административный инструмент, HTTP-доступ к реестру не открыт. Следующий шаг — завершение оставшейся части T02, затем parsing и векторизация T03–T07. C01 остаётся partial из-за двух отсутствующих обязательных оригиналов.


## C01 — один действующий текст, удаление старых публикаций

Поручение пользователя 09.10.2026: один закон/документ — один полный действующий вариант; удалить предыдущие варианты и отдельные поправки. Удалены 208 записей PDF: 180 публикаций поправок, 9 исправлений, 18 законодательных публикаций и копия стандарта из Холона. Удалены originals из рабочей папки и raw-data volume; отдельно обнаружена и удалена незарегистрированная копия pinui_base_2006.pdf с hash удалённого исходного закона. Старые PDF не архивировались. Удалены связанные source_checks/text metadata и topics; оставлен минимальный audit регистрации и отдельный user_corpus_cleanup event. Проектные договоры 04.2025/08.2025 не затронуты.

Осталось 15 документов, 205 страниц: стандарт 21.1 (1), guidance (8), regulations (2), model agreements (2), model form (1), ethics decision (1). У только gov_standard21 подтверждены verified/current/in_force; остальные статусы не изменялись и не объявлены действующими нормами. Полные актуальные редакции 16 законов отсутствуют; они занесены в coverage_gaps вместе с 2 актами о шамае. Полная замена корпуса действующими текстами **не завершена**.

Исследование источников: официальный реестр Кнессета показывает исходный закон и последующие поправки, что подтверждает about/FAQ; скачать последнюю поправку недостаточно для полного текста. У оценщиков официальная карточка указывает изменение 09.02.2023, у planning — 29.07.2026; у нового закона о восстановлении найдено исправление 04.05.2026. Старые/частичные copies не объявлены актуальными. Кнессет из локальной среды вернул HTTP 247; доступ внешнего web к карточке ограничен geo-maintenance. Нево web недоступен по robots. Пользователь сообщил, что доступа к Нево/Такдин нет. Обход ограничений не выполнялся.

retention_policy=current_only в config/manifest, policy validation в download/import блокирует возврат удалённых исторических типов. consolidated_law допускается только с verified/current/in_force и consolidation_verified_as_of; это требование к проверке, а не автоматическое юридическое подтверждение. Безопасная очистка ограничивает пути raw storage, проверяет manifest/hash и состояние registered. Первая сверка обнаружила одну старую незарегистрированную копию; после удаления полная сверка passed: host/volume/DB по 15 PDF, 18 gaps, sole eligible norm gov_standard21. Повторный import — passed: 15 versions, 15 source checks, 18 gaps, 224 audit events; старые документы не вернулись.

Проверки: pytest — 46 passed (одно известное upstream предупреждение); Ruff check и format --check — passed; PDF/hash/page objects — 15 passed, 0 failed, 205 страниц; documentation checks — passed (270 requirements). Тексты рекомендаций проверены только выборочно; актуальность 14 оставшихся вспомогательных документов не подтверждена. Следующий незавершённый результат — получить проверенные полные редакции законов из доступного источника, не подменяя их исходными публикациями.


## T11 — цепочки поправок и проверка актуальности

По поручению пользователя реализованы типизированные связи закона, пунктов и поправок; даты вступления и окончания действия, отмена закона, переходные условия AND/OR. Детерминированный сборщик проверяет контрольную сумму предшествующего текста при каждом изменении и сохраняет источник каждого действующего пункта. Проверенная исходная редакция, полный перечень изменений и ручное подтверждение полноты цепочки обязательны. Автоматического юридического разбора PDF и автоматического доказательства полноты нет.

PostgreSQL хранит неизменяемые цепочки, поправки и снимки текста; выбор цепочки записывается в audit. Миграции 0002/0003 применены к реальной БД. Обычный флаг verified/current у PDF закона больше не разрешает обход проверки цепочки. Поисковый шлюз проверяет все запрошенные законы до поиска, связывает результаты с точным снимком и фрагментом текста и повторно проверяет источники после поиска. Повторная проверка перед выдачей будущего ответа также обязательна.

В реестре созданы 16 реальных семейств законов без подтверждённых цепочек. Проверка pinui на 2026-10-09 возвращает chain_incomplete и пустой текст. Синтетические примеры использованы только в тестах с откатом транзакций. Корпус содержит прежние 15 PDF; удалённые публикации не восстановлены. В source_registry добавлен официальный реестр законов Кнессета: всего 8 источников.

Проверки: полная регрессия с PostgreSQL — 77 passed, одно известное upstream предупреждение Starlette/AnyIO. Проверены границы дат, переходные условия, неполная цепочка, устаревшее подтверждение, конфликт текста, отмена, неизменяемость записей, повторный импорт и запрет поиска по неподтверждённым законам. Формат административного ввода и границы реализации описаны в docs/legal-currentness.md; REQ-SRC-05–08 добавлены в спецификацию и матрицу.

Финальные проверки: Ruff check и format --check — passed; документация — passed (274 уникальных требования, 58 разделов, 14 этапов). После регрессии в реальной БД: 16 законов, 0 цепочек, 0 поправок, 0 снимков, 8 источников, 224 audit events; тестовый источник отсутствует.

T11 остаётся partial: необходимо получить и вручную проверить реальные тексты и полные цепочки изменений, затем подключить сборщик к Qdrant, обработчику вопросов и генерации ответа. Эти части ещё не реализованы; наличие ядра не означает подтверждённую актуальность 16 законов. Следующий шаг — подготовка и проверка реальных цепочек C01; без них поиск по законам блокируется.

## T03/T04 — программа создания чанков, запуск и исправление результата

Поручение пользователя: написать программу, выполнить её на сохранённом корпусе и проверить/исправить результат. Созданы scripts/create_chunks.py (--store выполняет также загрузку в PostgreSQL), app/chunking/core.py, repository.py, scripts/chunk_registry.py и config/chunking.json. Зафиксирован установленный pypdf 5.9.0; uv.lock содержит 75 пакетов. Docker-образ проекта пересобран по frozen lock. В Windows запись в bind mount требует --user root для административной команды создания артефактов; обычные сервисы продолжают использовать пользователя pinui.

Извлечён текст всех 205 страниц 15 PDF. Четыре слабые страницы визуально просмотрены: пустые/декоративные обложки; явные исключения сохранены в конфигурации. Визуально сверены пример определения стандарта и пункт 1.20 типового договора. Пригодных страниц 201, OCR-required страниц 0. Созданы 1262 исходных блока и 842 чанка; значения section/clause эвристические с medium/low confidence, исходный текст для цитирования не нормализуется. Поисковые колонтитулы исключены, но сохранены в оригинальных блоках. Проверяются hashes оригиналов, воспроизводимость IDs, page/block offsets, точное соответствие spans и покрытие всех пригодных блоков.

Первый запуск выявил неправильное распознавание номеров сносок и попадание адресного колонтитула в чанки договора. Правила исправлены; parser revision зафиксирована как pdf-text-structural-v3. В одной транзакции промежуточный набор 849 неактивных чанков заменён на 842 исправленных, с отдельным audit event. Повторные создания и импорт не изменили IDs/counts и не создали дубликатов. Оригиналы 15 PDF и юридические статусы не изменены. Удалённые ранее законы/поправки не восстановлены.

Миграция 0004 применена к предыдущей реальной schema revision и проверена вместе с необходимыми таблицами на пустом изолированном namespace с rollback. PostgreSQL запрещает UPDATE исходных блоков/чанков; сохранены статусы документов и отдельный staged_unreviewed у чанков. Индекс/generation не создавался, eligibility у каждого чанка false. Raw consolidated_law явно отклоняется; адаптер проверенных юридических снимков pending.

Проверки: полный запуск --store в новом Docker-образе — passed (15 PDF, 205 страниц, 1262 блока, 842 чанка); независимая сверка всех записей БД с артефактами — passed (текст, spans, locator, hash, metadata). Фактические totals: 15 parsing revisions, 1262 blocks, 842 chunks, 15 document versions, 0 legal chains, 255 audit events. Полная регрессия с PostgreSQL — 97 passed; одно ранее известное upstream предупреждение. Ruff check и format --check — passed. Документация — passed (274 уникальных требования, 58 разделов, 14 этапов).

T03/T04 остаются partial относительно полной спецификации: DOCX/OOXML numbering, OCR he, bbox/ячейки таблиц, восстановление заголовков/сносок и активные index generations ещё не реализованы. Таблицы пока представлены исходным извлечённым текстом с предупреждениями. Временный tokenizer Unicode word/punctuation с лимитами 800/100 должен быть заменён или проверен tokenizer выбранной embedding-модели до T06; эти 800 токенов не объявлены её лимитом. Детали запуска и границы реализации: docs/chunking.md. Следующая независимая работа над готовым PDF-корпусом — T05, выбор и проверка локальных embeddings, при сохранении C01/T11 pending для юридических цепочек.

