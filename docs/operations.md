# Эксплуатация — 10.10.2026

Приложение: http://localhost:8510; OpenAPI: http://localhost:8010/docs. Порты только loopback. Другие Docker-проекты не изменять.

## Настройка и подготовка

Существующий .env сохраняется. AUTH_MODE=local: входа, токенов и ролей в интерфейсе нет; документы и операции доступны владельцу компьютера. API/UI слушают host loopback и отклоняют чужие Host/Origin. Старые поля токенов в .env не используются локальным режимом.

APP_MODE=production, закреплённые embedding/reranker/revisions и порог должны совпадать с config/local-models.json и индексом. MODEL_STORAGE_PATH=/workspace/data/models, INDEX_STORAGE_PATH=/workspace/data, RAW_STORAGE_PATH=/data/raw. Локальные модели не требуют OpenAI.

Для переноса на новый компьютер сохраните оригиналы/реестр/config и загрузите модели:
```powershell
docker compose up --build -d
docker compose run --rm --no-deps --user root api python -m scripts.download_models
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps --user root api python -m scripts.registry import
docker compose run --rm --no-deps --user root api python -m scripts.create_chunks --store
docker compose run --rm --no-deps --user root -v "${PWD}:/source" -w /source api /workspace/.venv/bin/python -m scripts.import_contracts
docker compose run --rm --no-deps --user root api python -m scripts.index_corpus
docker compose restart api ui
```

Для первичного импорта используется data/corpus-manifest.json. После восстановления PG и pipeline.tar.gz индекс строится по active parsing revisions реестра; первоначальный chunks/manifest.json необязателен. При утрате parsing artifacts запустите scripts.parse_registered_corpus по сохранённым оригиналам, затем scripts.index_corpus. Пустая data/ не является готовым корпусом; downloader не заменяет подтверждение юридической актуальности.

## Ключ и языки

Для перевода/ответов/сравнения добавьте OPENAI_API_KEY в локальный .env и выполните docker compose up -d --force-recreate api. Модели: gpt-5.4-mini, fallback gpt-4.1-mini. OPENAI_STORE=false. Начальные поддерживаемые языки he/ru; список SUPPORTED_QUERY_LANGUAGES расширяем, например ["he","ru","en"]. Каждый добавленный язык требует live и ручной проверки. Автоопределение реализовано для Hebrew/Cyrillic/Latin; другие языки задавайте явно.

Лимиты: $0.20 запрос, $0.40 сравнение, $1.00 сутки по Asia/Jerusalem. Provider резервирует оценку перед вызовом, сохраняет usage; неопределённые ошибки не освобождают резерв. В /status наличие ключа означает конфигурацию, не успешную live-проверку аккаунта.

## Загрузки и задания

POST /documents: multipart file + metadata JSON, Idempotency-Key. PDF/DOCX ≤50 MiB, обязательный project_id. Ответ 202 содержит job_id. Повтор с тем же actor/route/key/body возвращает то же задание; изменённое тело — 409.

GET /jobs/{id}, POST /jobs/{id}/cancel. POST /documents/{id}/reindex повторно разбирает документ; POST /documents/index создаёт индекс всего зарегистрированного корпуса. Worker сохраняет checkpoints, heartbeat/lease и retries. Устаревший worker не может активировать поколение. Старая версия остаётся активной до проверки payload/векторов и атомарной смены PG. Запрос при смене поколения получает 409 и может быть повторён.

Кэш data/all-vectors.npy проверяется по контрольной сумме и полному model fingerprint; повреждение означает перерасчёт. Модель нельзя менять без нового поколения и перезапуска API. Ручная активация непроверенных staging generations запрещена. Для rollback состояния используйте согласованный backup; предыдущие immutable revisions сохраняются.

## Актуальность и источники

POST /sources/{source_id}/check создаёт безопасную проверку allowlisted official URL, DNS/IP, redirects, размера и SHA-256. Неизменный PDF не доказывает отсутствие более новой редакции. Новые bytes сохраняются pending, требуют review; автоматическая проверка не продлевает reviewed-through документа.

POST /documents/{id}/review требует исходный SHA, дату проверки сегодня и inventory source URL/SHA, notes; audit сохраняется. Laws требуют полного legal_chain review и compiler. Исторический ответ по необработанным редакциям блокируется; цепочка законов собирается отдельно на заданную дату. Неполная/просроченная цепочка не выдаёт нормативный текст.

## Backup/restore

Остановите новые записи и дождитесь завершения jobs. Для согласованного snapshot остановите api/ui/worker/scheduler (только этот проект); PostgreSQL и Qdrant оставьте работающими. Сохраните PG dump в новый каталог data/backups/<идентификатор>:
```powershell
docker compose exec -T postgres pg_dump -U pinui -d pinui -Fc -f /tmp/pinui_backup.dump
docker compose cp postgres:/tmp/pinui_backup.dump data/backups/<идентификатор>/postgres.dump
docker compose run --rm --no-deps --user root api python -m scripts.backup_data data/backups/<идентификатор>
```

backup_data сохраняет оригиналы, config, model/index manifests, parsing/chunk artifacts в pipeline.tar.gz, Qdrant snapshot и SHA-256. .env и веса модели не включаются; credentials сохраняйте отдельно, веса воспроизводимы из pinned revisions. Папка содержит частные договоры: храните в каталоге с ограниченными Windows ACL или на шифрованном носителе. .gitignore не заменяет ACL/шифрование.

Проверка восстановления выполняется в отдельной БД pinui_restore_<цифры>, не поверх рабочей:
```powershell
docker compose exec -T postgres createdb -U pinui pinui_restore_<цифры>
docker compose exec -T postgres pg_restore -U pinui -d pinui_restore_<цифры> /tmp/pinui_backup.dump
docker compose run --rm --no-deps --user root api python -m scripts.verify_restore data/backups/<идентификатор> pinui_restore_<цифры>
docker compose exec -T postgres dropdb -U pinui pinui_restore_<цифры>
docker compose start api ui worker scheduler
```

verify_restore реально извлекает originals в isolated temporary directory, проверяет SHA, PG active fingerprints/counts, восстанавливает Qdrant в отдельную collection и сравнивает все payload/dense/sparse vectors, удаляет только scratch collection. Рабочую collection не заменяет. Для аварийного возврата полного состояния сначала восстановите изолированно и проверьте, затем переключите конфигурацию на восстановленные данные.

## Приёмка

python -m scripts.accept_local проверяет реальный HTTP retrieval, точность исходных цитат, holdout и negatives, нагрузку 1–2 запросами. scripts/benchmark_local.py выбирает модели по development и отдельно измеряет holdout; исходные baseline reports защищены от перезаписи. scripts/calibrate_threshold.py использует development negatives.

Без ключа не объявлять принятыми перевод, groundedness ответов и тематическое сравнение. Отдельно нужны ручной Hebrew review, полные реальные legal chains, live provider/cost tests. docs/progress.md содержит фактический статус.

## Поиск и языки (решение 10.10.2026)

По умолчанию API/UI ищут во всех доступных документах (all_documents), в том числе договорах. Явный выбор документов ограничивает поиск выбранными документами. Отдельно доступны current_norms, общие документы с рекомендациями, документы проекта и historical. Договоры/рекомендации сохраняют тип и статус; непроверенные цепочки законов исключены. Словарь config/terminology.json помогает переводить роли и содержит ссылки на источники; сам словарь не считается юридическим доказательством. Поля и ответы автоматически выбирают RTL/LTR.
