# План реализации PinuiRAG

Версия 1.3 · 10 октября 2026

Основание: `docs/specification.md`, версия 1.6. Корневой specification.md содержит указатель; DOCX не синхронизирован. Уточнения T01 и существующие runtime описаны в ADR-001.

## Цель и границы

Создать демонстрационный сервис для 1–2 пользователей: скачать документы на иврите, построить локальными моделями индекс Qdrant, предоставить поиск и общение через интерфейс. При настроенной LLM вопрос на поддерживаемом языке переводится на иврит, поиск выполняется на иврите, ответ формируется на языке обращения. Цитаты сохраняют оригинальный текст, редакцию и страницу PDF либо абзац/таблицу DOCX.

Без внешнего API-ключа доступны загрузка, индексация и поиск на иврите с выдачей выдержек. Перевод, связные ответы и тематическое сравнение требуют LLM. Запуск не должен требовать ключа. Отсутствие локальной модели или инфраструктуры отражается в readiness; незавершённые функции не заменяются production mocks.

Сравнение охватывает конкретную тему в двух договорах. Вопрос без темы требует уточнения. Полное сравнение, выравнивание всех пунктов и исчерпывающий список изменений исключены. По решению пользователя приложение личное: вход/роли в UI отсутствуют, все локальные документы доступны, порты только loopback. Проверка источников/актуальности и восстановление данных остаются обязательными.

## Порядок работы

Дополнение 10.10.2026: следующий этап D01 — один установщик Windows по REQ-DIST-01, без отдельной установки runtime/Docker и скачивания моделей. Настройка собственного API-ключа через интерфейс (REQ-KEY-01–02) реализуется перед упаковкой. D01 должен включать подбор совместимых поставляемых компонентов, сборку, исключение секретов, сохранение пользовательских данных и проверку на чистой Windows без сети. До этой проверки установщик не объявлять готовым.

D01, фактическое состояние 10.10.2026: однофайловая сборка создана; собственные Windows Python/PostgreSQL/Qdrant/OCR и модели поставляются внутри. Установка в отдельную папку и автономный поиск проверяются скриптом `scripts/test_windows_bundle.py` с PATH без системных Python/Docker, запретом внешней сети и сверкой всех векторов/цитат. Чистая Windows VM недоступна на текущем компьютере; эта отдельная проверка остаётся not_run. Сборка не объявляется прошедшей чистую VM. Итоговые отчёты и статус: `docs/progress.md`, `docs/windows-distribution.md`.

| Этап | Результат | Зависимости | Состояние |
|---|---|---|---|
| T01 | Воспроизводимый каркас и рабочие документы | Спецификация | done |
| C01 | Сначала скачать законодательный корпус и создать реестр источников | T01 | partial: 15 retained PDFs, 16 consolidated laws + 2 appraiser acts missing |
| T02 | Реестр документов, редакции и доступ | C01 | done: local registry/API/aliases; migrations verified |
| T03 | PDF/DOCX/OCR и исходные locators | T02 | partial: PDF/DOCX/OCR/tables implemented; ambiguous structures and Hebrew manual review pending |
| T04 | Структурные chunks и точные spans | T03 | implemented: model tokenizer, exact spans, 3664 active chunks; manual corpus QA pending |
| T05 | Проверочный набор и выбор локальных моделей | T04 | done: local development/holdout benchmark and pinned models |
| T06 | Qdrant и hybrid search | T05 | done: real Qdrant hybrid retrieval; holdout HTTP passed |
| T07 | Устойчивая индексация и переиндексация скриптами | T06 | done: checkpoints/cache verification/leases; forced restart recovered |
| T08 | Язык вопроса, перевод и ограничения поиска | T07 | partial: translation/languages/filters implemented; live translation not_run without key |
| T09 | Поиск без ключа и ответы с LLM | T08 | partial: Hebrew search accepted; validated LLM answers implemented, live not_run |
| T10 | Тематическое сравнение двух договоров | T09 | partial: thematic pipeline/clarification implemented; live comparison not_run |
| T11 | Проверка актуальности, обновления источников и завершение интеграции корпуса | C01, T07; независимый движок по поручению пользователя | partial: reviewed-chain compiler and source checks implemented; 16 laws + 2 acts missing |
| T12 | Завершённые HTTP-контракты и E2E | T10, T11 | partial: API/contracts/local E2E implemented; live provider E2E not_run |
| T13 | Интерфейс поиска, общения и сравнения | T12 | implemented: personal UI without login; local search verified, live features pending |
| T14 | Приёмка, стоимость и восстановление | T13 | partial: local quality/performance/restore tested; live cost/quality and real legal coverage pending |

Порядок исправлен по поручению пользователя: **C01 скачать законы → T02–T07 подготовить текст и построить векторную БД → проверить поиск → T08–T10 подключить перевод, ответы и тематическое сравнение → T12–T13 завершить интерфейс → T14 приёмка**. Уже выполненный каркас T01 сохраняется. Скачивание не откладывать до реализации общения и интерфейса. T11 относится к проверке полноты редакций, интеграции и автоматическим повторным проверкам; его независимые части выполнять после T07, не ждать T09.

API и проверки развивать вместе с модулями. Скачанные законы использовать для parsing и выбора локальных моделей; реальные договоры — локально либо в обезличенных копиях. Синтетические fixtures нужны для граничных тестов, но не заменяют реальный corpus. Скачивание официального PDF не означает подтверждение действующей консолидированной редакции: сомнительные источники остаются manual_review и не активируются в current_norms.

T05 использует изолированный benchmark index adapter, разрешённый спецификацией, чтобы выбрать модели до production retrieval. Для T05 обязательны локальный Hebrew retrieval и выбор моделей. Проверки внешнего перевода и ответов перенесены на T08–T10: отсутствие API-ключа не блокирует скачивание, выбор embeddings или построение векторной БД.

## Правила выполнения и фиксации результатов

- Каждая задача начинается с чтения актуальной спецификации, связанных контрактов и текущего progress.
- Состояния: `pending`, `in_progress`, `partial`, `implemented`, `blocked`, `done`. implemented означает наличие кода без полной live/ручной приёмки; partial — незакрытые условия. Для blocked указывать конкретное препятствие и независимую работу.
- Проверки записывать как `passed`, `failed`, `not_run` с командой, средой и причиной. Этот план не является отчётом о выполненных проверках.
- В той же задаче обновлять `docs/progress.md` и `docs/requirements-traceability.md`.
- Внешние платные вызовы запускать только с настроенными credentials, тарифами и лимитами. Ключ хранить в `.env` вне Git; скачивание весов локальных моделей документировать отдельно от вызовов LLM.
- Каждый новый язык обращения проверять по переводу вопроса, retrieval и соответствию ответа evidence. Начальные контрольные языки — he и ru; архитектура и API не ограничены ими.

## T01 — Каркас и воспроизводимый запуск

**Цель:** подготовить основу проекта без зависимости от API-ключа.

**Зависимости:** нет. **Состояние:** done.

**Требования:** REQ-CONTRACT-01, REQ-LANG-04; разделы 37–38, 54–56.

**Вход:** спецификация 1.3, этот план, установленный Docker; секреты не требуются.

**Модули и контракты:** `app/config/`, `app/api/`, `app/models/`, Compose для api/worker/scheduler/ui/postgres/qdrant; Settings, error envelope, `/health`, `/status` и capabilities.

**Работы:** создать Python 3.12 проект, `pyproject.toml`, `uv.lock`, Dockerfile, Compose, `.env.example`, README, AGENTS, CI; точные версии проверить и зафиксировать. Создать progress и traceability, присвоить стабильные IDs обязательным ненумерованным требованиям. Сформировать предварительный перечень категорий источников и локальных файлов без выдуманных URL. Зафиксировать ADR только для решений, требующих обоснования.

**Проверки:** чистая установка, `docker compose config`, health API/PostgreSQL/Qdrant, запуск без OPENAI_API_KEY, корректные capabilities, Ruff и отсутствие секретов в отслеживаемых файлах. На этом этапе readiness не обещает готовый retrieval.

**Definition of Done:** запуск повторяется по README; ключ необязателен; конфигурационные ошибки понятны; рабочие документы и CI созданы. Локальный поиск без ключа принимается на T09.

## C01 — Скачать законодательный корпус до построения БД

**Цель:** собрать официальные исходники на иврите для последующей локальной индексации.

Дополнительно обязательны рекомендации об организаторах, адвокатах и представительстве жильцов, профильные решения по этике и опубликованные образцы договоров. Эти материалы скачаны и перечислены в corpus-status; тип источника и орган/автор сохраняются отдельно. Остаются два оригинала по назначению/оплате шамая.

Стандарт 21.1 обязателен. Оригинал gov.il проверен 09.10.2026: утверждение 01.06.2022, начало действия 13.06.2022 (пункты 10–11). Отдельные инструкции 22.12.2025 и 25.02.2026 скачаны; их применимость проверять отдельно с учётом стадии плана. Краткое изложение или проект стандарта не заменяют полный документ.

**Зависимости:** T01. **Состояние:** partial: real verified consolidated laws missing.

**Требования:** REQ-SRC-01–04, REQ-ING-01, REQ-SEC-01; разделы 2–4 спецификации.

**Вход:** предметные категории спецификации, официальные публикации правительства/Кнессета, локальные договоры (сохранить отдельно).

**Модули и контракты:** `scripts/download_corpus.py`, `config/sources.yaml`, `config/corpus-downloads.json`, `data/raw/legislation/`, corpus manifest и `docs/corpus-status.md`. Пока без загрузки в PostgreSQL/Qdrant.

**Работы:** по решению пользователя от 09.10.2026 собрать один полный подтверждённый действующий текст каждого закона, включая вступившие в силу изменения; отдельные поправки, исправления, предыдущие варианты и дубли не хранить в рабочем нормативном корпусе. Старые неподтверждённые законодательные публикации удалены явной административной очисткой; требуется получить 16 полных актуальных редакций, а также 2 отсутствующих акта о шамае. Отдельно сохранить regulations, стандарт 21 и рекомендации/шаблоны с собственными статусами проверки. Сохранить bytes, URL/provenance, SHA-256, дату получения, размер и результат проверки. Статусы не выводить из даты скачивания; недоступный полный текст отмечать gap. Частную или самостоятельно собранную редакцию не выдавать за подтверждённый официальный текст.

**Проверки:** воспроизводимый download, HTTPS allowlist/redirects, размер/magic bytes, открытие PDF и число страниц, Hebrew text либо OCR-needed; повторный запуск проверяет hashes и не перезаписывает изменённые оригиналы; manifest содержит все успехи и ошибки; отчёт перечисляет охваченные законы и реальные gaps.

**Definition of Done:** документы из установленного перечня скачаны либо конкретная внешняя недоступность зафиксирована после попыток; источники и hashes сохранены; не заявлена юридическая актуальность без доказательств. При недоступном обязательном документе corpus отмечается partial, а независимая подготовка скачанных файлов продолжается. Следующий этап — T02/T03, затем локальная векторизация T04–T07.

## T02 — Реестр, редакции и доступ

**Цель:** сохранить документы и права независимо от поискового индекса.

**Зависимости:** T01/C01. **Состояние:** done: local registry/API/aliases; migrations verified.

**Выполненный срез (09.10.2026):** Alembic 0001_registry, PostgreSQL schema registry, document_versions/families/topics, source_registry/checks, coverage_gaps, audit регистрации и представление document_register. Административный импорт идемпотентен, проверяет hashes, сохраняет оригиналы в raw-data volume. Семейства исходных публикаций отделены от тематических связей законов; загрузка не подтверждает юридическую актуальность. По поручению пользователя этот независимый срез выполняется при двух внешних пробелах C01.

**Требования:** REQ-DATA-01, REQ-VER-01/02, REQ-SEC-01; раздел 52.

**Вход:** две синтетические редакции одного договора, actors admin/reader, project grants.

**Модули и контракты:** `app/db/`, `app/registry/`, `app/api/`, migrations; UUID документов и семейств, aliases, Scope, CRUD DTO.

**Работы:** миграции PostgreSQL, registry CRUD, неизменяемая идентичность редакций, отдельные legal/version/verification/ingestion статусы, aliases и resolver; hash токенов, actors/grants, audit events. Определить назначение credentials каждому actor и способ управления доступом. Явно реализовать административные операции подтверждения редакции и выбора current с audit, дополнить их DTO/OpenAPI без обхода проверки прав.

**Проверки:** миграции с нуля и обновление schema; запрет current из другого семейства; одинаковые aliases в разных проектах; неоднозначность и FILTER_CONFLICT; 401/403/404; повтор hash не раскрывает чужой документ.

**Definition of Done:** две редакции доступны своему actor, разрешаются отдельно и не раскрываются постороннему; выбор current не означает подтверждение подписи.

## T03 — Хранение оригиналов и parsing

**Цель:** получить текст на иврите с адресацией к оригиналу.

**Зависимости:** T02. **Состояние:** partial: PDF/DOCX/OCR/tables implemented; ambiguous structures and Hebrew manual review pending.

**Требования:** REQ-PARSE-01/02, REQ-SEC-01.

**Вход:** безопасные PDF с текстом, сканированные и смешанные PDF; DOCX с абзацами, нумерацией, таблицами и RTL; повреждённые файлы.

**Модули и контракты:** `app/parsing/`, raw storage, registry; DocumentParser → ParsedDocument, blocks, extraction warnings и locators.

**Работы:** immutable storage и SHA-256; PDF text extraction, постраничный OCR he, DOCX в XML-порядке с numbering/restart; original_text/search_text/mapping; восстановление структуры и предупреждения. Выбрать OCR adapter по фикстурам, проверить лицензии и зафиксировать версии. Защитить upload по magic bytes, размеру и распаковке ZIP.

**Проверки:** порядок paragraph/table, вложенные таблицы, RTL, numbering restart, PDF OCR/text/mixed, malformed/oversized файлы, воспроизводимость исходного текста. DOCX не получает выдуманную страницу.

**Definition of Done:** каждый пригодный блок имеет locator; все пропуски и OCR отмечены; оригинал скачивается только авторизованно.

## T04 — Chunking и fingerprints

**Цель:** подготовить поисковые фрагменты без потери источников цитирования.

**Зависимости:** T03. **Состояние:** implemented: model tokenizer, exact spans, 3664 active chunks; manual corpus QA pending.

**Требования:** REQ-CHUNK-01, REQ-CONTRACT-01.

**Вход:** structured documents T03; начальные лимиты 800/100 tokens; кандидат tokenizer с фиксированной версией, согласуемый на T05.

**Модули и контракты:** `app/chunking/`, blocks/chunks/spans; Chunker → ChunkDraft, deterministic UUIDv5 и fingerprint.

**Работы:** сохранять целые помещающиеся пункты, делить большие блоки, учитывать таблицы и заголовки; overlap только внутри одного большого блока; оригинальные диапазоны хранить независимо от search_text. Изменение tokenizer на T05 требует новой chunking revision и повторной проверки.

**Проверки:** границы пунктов, multi-page locators, все пригодные blocks покрыты, лимиты tokens, повторяемые IDs, отсутствие двойной цитаты из overlap.

**Definition of Done:** все chunks связаны с точными исходными spans, fingerprints воспроизводимы.

## T05 — Dataset и выбор локальных моделей

**Цель:** выбрать embeddings и reranker на измерениях поиска по ивриту.

**Зависимости:** T04. **Состояние:** done: local development/holdout benchmark and pinned models.

**Требования:** REQ-QA-01/03, REQ-RET-02, REQ-LANG-01–03, REQ-COST-01.

**Вход:** обезличенный Hebrew corpus subset; минимум 60 dev и 30 отдельных holdout cases; доступные CPU/RAM/GPU; ключ и лимит только для внешних экспериментов.

**Модули и контракты:** `benchmarks/`, `app/embeddings/`, `app/reranking/`, `docs/model-decisions.md`; embed_documents/embed_queries, rank.

**Работы:** разметить expected blocks, claims, citations и answerability; отделить holdout до настройки; сравнить минимум две локальные embedding конфигурации и два варианта reranking. Проверить ресурсы, Hebrew quality, licenses, revisions и tokenizer; создать model decisions, baseline manifest, черновик acceptance-profile. Оценить перевод вопроса отдельным экспериментом с LLM, без подмены окончательной приёмки pipeline.

**Проверки:** Recall@5/@10, MRR, точные числа/пункты, negative cases, baseline с reranking и без него; отдельно по языкам исходного вопроса. Проверить выбранные модели после скачивания без внешнего API-ключа.

**Definition of Done:** локальные модели, dimension, revisions и порог reranker выбраны по отчёту; dataset разделён, baseline не перезаписывается автоматически; внешние непроведённые проверки отражены явно.

## T06 — Qdrant и hybrid retrieval

**Цель:** построить рабочий dense/sparse поиск на иврите.

**Зависимости:** T05. **Состояние:** done: real Qdrant hybrid retrieval; holdout HTTP passed.

**Требования:** REQ-INDEX-01, REQ-RET-01, REQ-CONTRACT-01.

**Вход:** выбранные local models, chunks, tokenizer, реальный Qdrant, lexical generation settings.

**Модули и контракты:** `app/vector_db/`, `app/retrieval/`, lexical vocabulary в PostgreSQL; stage/verify/search, named dense/lexical vectors, Scope.

**Работы:** physical collections и alias по fingerprint, payload indexes, BM25-compatible encoder с IDF только в Qdrant, immutable token dimensions, dense/sparse prefetch и RRF; диагностический trace. Применять одинаковые фильтры до поиска в обеих ветках.

**Проверки:** реальные Qdrant integration tests, согласованность query/document encoder, Hebrew niqqud, числовые пункты, unknown tokens, несовместимая dimension, фильтры редакции и доступа, baseline regression.

**Definition of Done:** гибридный поиск воспроизводим, работает локально и возвращает только разрешённые chunks активных generations.

## T07 — Скрипты индексации и устойчивые jobs

**Цель:** построить и обновлять индекс без дублей и частичной активации.

**Зависимости:** T06. **Состояние:** done: checkpoints/cache verification/leases; forced restart recovered.

**Требования:** REQ-ING-01–04, REQ-JOB-01, REQ-INDEX-01.

**Вход:** document IDs, raw files, local models, PostgreSQL/Qdrant; configured limits и checkpoint policy.

**Модули и контракты:** `scripts/`, `app/jobs/`, registry/index repositories; ingest/index/reindex jobs, lease/heartbeat, manifests и activation.

**Работы:** CLI для ingestion, indexing, reindex и reconciliation; PostgreSQL worker/scheduler, checkpoints, retries и idempotency; staging → integrity check → transactional activation. Сохранить прежние generations и цитаты до успешной замены, определить retention orphan generations.

**Проверки:** повтор команды, kill worker mid-index, outage Qdrant, повтор delivery, конкурентные generations, переключение и rollback; отсутствие внешних вызовов при локальной индексации.

**Definition of Done:** скрипт превращает безопасный корпус в проверенный активный индекс; повтор не создаёт дублей; сбой возобновляется и не открывает неполный индекс.

## T08 — Планирование запроса и перевод

**Цель:** искать на иврите по вопросу на поддерживаемом языке.

**Зависимости:** T07. **Состояние:** partial: translation/languages/filters implemented; live translation not_run without key.

**Требования:** REQ-SRC-01/02, REQ-VER-02, REQ-RET-01/02, REQ-LANG-01/02, REQ-COST-01.

**Вход:** построенная векторная БД T07, dataset, aliases, SUPPORTED_QUERY_LANGUAGES, configured LLM для перевода, бюджеты; fakes только для offline tests.

**Модули и контракты:** QueryPlanner, LanguageResolver, TranslationAdapter, Scope, retrieval/reranker; original_question, detected_language, answer_language, search_question_he.

**Работы:** разрешить IDs и доступ до поиска; определить язык; переводить не-he вопрос один раз с сохранением чисел, имён, дат и пунктов; все query variants и reranker на he. Реализовать exact lookup, current/project/historical и controlled expansion; перевод не зависит от переключателя expansion. Не расширять пустой Scope на весь corpus.

**Проверки:** HE без перевода, RU и дополнительный язык после quality проверки, короткий смешанный ввод, UNSUPPORTED_LANGUAGE, TRANSLATION_UNAVAILABLE, отсутствие ключа, conflicts, stale norms, смена источника во время запроса.

**Definition of Done:** поиск не выходит за Scope и выбранные редакции; исходный язык не ограничен русским; перевод и его стоимость отражены в trace/usage.

## T09 — Ответы, citations и поиск без ключа

**Цель:** выдавать подтверждённые ответы либо исходные результаты локального поиска.

**Зависимости:** T08. **Состояние:** partial: Hebrew search accepted; validated LLM answers implemented, live not_run.

**Требования:** REQ-CITE-01/02, REQ-API-02, REQ-LANG-01–04, REQ-COST-01.

**Вход:** evidence contexts, spans, output/context budgets; configured LLM для answer, Hebrew queries без ключа.

**Модули и контракты:** `app/llm/`, `app/citations/`, query service; ProposedClaims → VerifiedClaims → QueryResponse; response_mode auto/answer/search.

**Работы:** Responses adapter со store=false, structured output, fallback по допустимым ошибкам, token/cost limiter. Backend строит quotes и metadata из original_text, проверяет offsets; answer только из verified claims. Ответ на языке обращения, quote_translation отдельно. В search: answer=null, claims=[], Hebrew sources, без внешних вызовов; настроенный провайдер не заменять молча локальным режимом при сбое.

**Проверки:** неверные IDs/spans, неподтверждающая цитата, truncation, insufficient_evidence, fallback, real-provider smoke и manual groundedness. Без ключа проверить старт, indexing, Hebrew search, capabilities и LLM_NOT_CONFIGURED для генерации/иноязычного запроса.

**Definition of Done:** каждое выданное утверждение имеет допустимую citation; ответы проверены на he/ru и отдельно на добавляемых языках; search без ключа работает с реальными локальными моделями.

## T10 — Тематическое сравнение договоров

**Цель:** ответить «в договоре A — это, в договоре B — это; отличие — такое» с раздельными доказательствами.

**Зависимости:** T09. **Состояние:** partial: thematic pipeline/clarification implemented; live comparison not_run.

**Требования:** REQ-CMP-01/02, REQ-API-03, REQ-LANG-01–04, REQ-COST-01.

**Вход:** две безопасные Hebrew редакции, golden topics по площади/парковке/срокам/гарантиям; configured LLM и TOPIC_COMPARE_COST_LIMIT.

**Модули и контракты:** `app/comparison/`, POST /compare; CompareRequest/Response, findings, evidence_status_a/b, clarification_topics.

**Работы:** проверить права и ready обеих редакций; один перевод вопроса → отдельные retrieval/reranking A/B → отдельные statements/citations → подтверждённое difference на языке обращения. Если тема не указана — clarification_required до retrieval. Нет evidence одной стороны — соответствующий statement=null, difference=null, явное предупреждение; нет с обеих — insufficient_evidence. Сохранять snapshots и результаты с request_id; включить оба поиска и все LLM вызовы в единый бюджет.

**Проверки:** одинаковые и разные условия, изменённые числа, таблицы/OCR, evidence только одной стороны либо ни одной; SAME_DOCUMENT, запрет доступа, отсутствие ключа, общий вопрос без темы, смешивание редакций, превышение бюджета. Manual review корректности выводов и citations A/B.

**Definition of Done:** тематическое сравнение подтверждено golden cases; retrieval miss не объявляется отсутствием условия. Нет full comparison endpoint/job, выравнивания всех блоков и обещания полного покрытия.

## T11 — Скачивание документов и актуальный корпус

**Цель:** наполнить базу реальными документами на иврите из подтверждённых источников.

**Зависимости:** C01 и T07; окончательный corpus benchmark после T10. **Состояние:** partial: reviewed-chain compiler and source checks implemented; 16 laws + 2 acts missing.

**Требования:** REQ-SRC-01–03, REQ-SRC-05–08, REQ-ING-01, REQ-SEC-01.

**Вход:** исходники, URLs и manifest C01, два имеющихся договора, правила доступа/обезличивания и свежести.

**Модули и контракты:** `config/sources.yaml`, `app/acquisition/`, source checks, download/ingestion scripts, corpus manifest.

**Работы:** интегрировать уже скачанный corpus C01 в registry/index; дополнить обнаруженные gaps и проверить полноту комплектов поправок, действительность и актуальность. Инвентаризировать договоры 04.2025/08.2025, не считать подписанными без подтверждения. Реальные файлы хранить вне Git; безопасные копии регистрировать отдельно. Реализовать ETag/hash и scheduled rechecks; изменения активировать после parsing/indexing/verification.

**Проверки:** безопасные redirects и запрет private IP, ограничения скачивания, unchanged hash, новая ещё не действующая редакция, отменённая норма, ошибка freshness, ручное подтверждение; полный corpus manifest по категориям. Проверить retrieval и тематическое сравнение на реальном безопасном корпусе.

**Definition of Done:** все обязательные категории представлены или недостаток явно фиксируется как незакрытое требование; каждый активный нормативный документ имеет доказательство актуальности. Скрипты скачивания и индексации воспроизводимы, corpus не объявляется полным по одному числу файлов.

**Независимый реализованный срез (поручение 09.10.2026):** модели LawChain/Amendment/ChainReview, exact-text hashes, даты/отмена/AND/OR переходные условия, детерминированные снимки с provenance, immutable PostgreSQL evidence, audit и current-chain FK. Scope блокирует поиск при неполной цепочке; каждый hit привязан к актуальному snapshot/span; повторная проверка после поиска и перед ответом обязательна. Правовые verified/current flags у raw PDF не обходят компилятор. Реальные 16 законов зарегистрированы как ожидающие проверенных цепочек. Конкретные контракты и ограничения — docs/legal-currentness.md.

## T12 — Завершение API

**Цель:** подтвердить единые HTTP-контракты всей системы.

**Зависимости:** T10, T11. **Состояние:** partial: API/contracts/local E2E implemented; live provider E2E not_run.

**Требования:** REQ-API-01–03, REQ-JOB-01, REQ-SEC-01, REQ-LANG-04.

**Вход:** рабочие services, Pydantic DTO, corpus и роли; API endpoints уже реализованы в соответствующих задачах.

**Модули и контракты:** `app/api/`, `app/models/`, generated OpenAPI; query/compare/documents/projects/jobs/sources/health/status.

**Работы:** pagination, uniform errors/request_id, idempotency, upload metadata, authorization downloads/debug/admin operations; проверить capabilities и отсутствие obsolete full comparison contracts.

**Проверки:** HTTP E2E upload → job → ready → query → citations → topic compare; reader/admin/project scopes; 413/415/422/503, LLM_NOT_CONFIGURED, search_results, clarification_required; совпадение схем и документации.

**Definition of Done:** все обязательные маршруты доступны и проверены через HTTP; UI не потребует прямого доступа к БД.

## T13 — Интерфейс

**Цель:** предоставить понятный интерфейс общения и демонстрации векторного поиска.

**Зависимости:** T12. **Состояние:** implemented: personal UI without login; local search verified, live features pending.

**Требования:** REQ-API-01, REQ-LANG-01–04, REQ-CMP-01/02, REQ-SEC-01; разделы 31–32.

**Вход:** API и capabilities, Hebrew corpus, договоры, проверенный список языков.

**Модули и контракты:** `ui/` Streamlit client; server-side credential, только HTTP API.

**Работы:** поле вопроса, язык ответа/auto, выбор проекта/документа/редакции, режим поиска, ответ и citations, viewer original/locators, jobs/upload; сравнение двух документов с явной темой. Показать доступность перевода и генерации без требования ключа при открытии приложения. Admin debug демонстрирует candidates/ranks/scores без chain-of-thought; данные экранировать и разделять RTL/LTR.

**Проверки:** Hebrew RTL, ответ LTR и Hebrew citations, цифры/ссылки/пунктуация; выбор версии, уточнение темы, insufficient evidence, отсутствие ключа, недоступная БД, admin-only debug, PDF/DOCX locators.

**Definition of Done:** пользователь может найти пункт на иврите без ключа, получить ответ на языке обращения с ключом и сравнить конкретную тему двух договоров; состояния и ограничения видны в UI.

## T14 — Приёмка и восстановление

**Цель:** подтвердить готовность сервиса и воспроизводимость демонстрации.

**Зависимости:** T13. **Состояние:** partial: local quality/performance/restore tested; live cost/quality and real legal coverage pending.

**Требования:** REQ-ACC-01–07, REQ-QA-02/03, REQ-PERF-01, REQ-COST-01, REQ-SEC-01.

**Вход:** итоговый corpus, модели и fingerprints, независимый holdout, machine profile, configured prices/budgets и разрешённые реальные provider calls.

**Модули и контракты:** benchmarks/reports, acceptance-profile, `docs/operations.md`, backup/restore scripts, final traceability.

**Работы:** измерить качество по языкам, groundedness, citations и thematic correctness; определить численные targets и p95 при 1–2 concurrent users. Измерить indexing throughput, стоимость перевода/ответа/сравнения; зафиксировать hardware/corpus/settings. Проверить backup PostgreSQL/raw/config и Qdrant backup либо rebuild, document restore/rollback. Подготовить сценарий демонстрации и отчёт о приёмке.

**Проверки:** unit/integration/E2E, holdout без настройки по его результатам, manual Hebrew/multilingual review, clean Docker deployment без ключа и с ключом, нагрузка 1–2 пользователя, restore drill и совпадение fingerprints, контроль секретов/PII.

**Definition of Done:** численные quality/performance/cost targets достигнуты, REQ-ACC закрыты доказательствами, restore реально выполнен, обязательные TODO отсутствуют. При отсутствии ключа локальный сценарий может быть проверен, но перевод/генерация/сравнение не объявляются принятыми.

## Сценарии итоговой демонстрации

1. По инструкции скачать безопасный corpus и построить индекс скриптами, без LLM-ключа.
2. Запустить UI без ключа, задать Hebrew вопрос и открыть найденный исходный пункт.
3. Настроить ключ server-side, задать вопрос на русском и другом проверенном языке, получить ответы на языке обращения с Hebrew citations.
4. Выбрать 04.2025 и 08.2025, сравнить конкретную тему; проверить цитаты каждой стороны.
5. Задать вопрос без темы и вопрос без evidence; увидеть уточнение и корректное сообщение о недостатке данных.
6. Перезапустить сервис и проверить сохранность корпуса, повторить индексацию без дублей; восстановить данные из backup по инструкции.

## Оставшиеся условия приёмки

Локальный индекс и интерфейс запущены, вход удалён по поручению пользователя. 15 общих PDF + 2 договора + 1 закрытый синтетический OCR fixture; 3664 активных чанка. Старые законы/поправки не возвращены.

Для полной приёмки нужны настроенный OPENAI_API_KEY и live-проверка перевода, ответов, тематического сравнения и стоимости; ручная Hebrew/табличная QA; документально проверенные цепочки 16 законов и 2 отсутствующих акта о шамае. Неподтверждённые нормы заблокированы. Фактические проверки и статус каждого этапа: docs/progress.md.
