# Решения о моделях — 10.10.2026

LLM: **gpt-5.4-mini**, fallback **gpt-4.1-mini**, OpenAI Responses API, store=false, строгая JSON schema. Перевод, формирование утверждений и проверка их опоры на источники, тематическое сравнение. Ключ необязателен для локального поиска. Реальный API не проверен: OPENAI_API_KEY отсутствует.

Модели загружены с закреплёнными revisions; SHA-256 весов и tokenizer проверяются при загрузке. Конфигурация: config/local-models.json. Реальные manifests и результаты находятся в игнорируемой папке data/.

| Назначение | Модель | Revision | Лицензия / параметры |
|---|---|---|---|
| Выбранный embedding | intfloat/multilingual-e5-small | 614241f622f53c4eeff9890bdc4f31cfecc418b3 | MIT; ONNX INT8 CPU; 384 dimensions; 512 tokens; query:/passage: |
| Проверенный кандидат | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | e8f8c211226b894fcb81acc59f3b34ba3efd5f42 | Apache-2.0; ONNX INT8; 384 dimensions; 128 tokens |
| Reranker | cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 | 1427fd652930e4ba29e8149678df786c240d8825 | Apache-2.0; ONNX INT8 CPU; 512 tokens |

Веса каждого варианта около 118 MB. ORT: два CPU threads и один inter-op thread. Chunking по настоящему tokenizer embedding: максимум 480 tokens, overlap 16, исходные spans сохраняются. Reranker явно обрезает только вторую последовательность.

Development: 20 тематических групп × 3 вопроса = 60; holdout: 10 других групп × 3 = 30. Ключи document/clause не пересекаются. По 5 отрицательных вопросов. Оценка ищет ожидаемый пункт в явно выбранном документе; это ещё не ручной эталон каждого block ID и не оценка юридической правильности ответов.

| Вариант | Development MRR | Recall@10 |
|---|---:|---:|
| E5 dense | 0.7564 | 0.9167 |
| E5 + reranker 256 | 0.8435 | 0.9667 |
| **E5 + reranker 512** | **0.8491** | **0.9667** |
| MiniLM dense | 0.6078 | 0.8333 |
| MiniLM + reranker 512 | 0.7464 | 0.9000 |

Holdout выбранного варианта: MRR **0.9111**, Recall@10 **1.0**. Порог −3.0190533638000487 выбран по development negatives (maximum + 0.1); holdout false accepts **0/5**. Пять отрицательных примеров — ограниченная проверка; нужны близкие по теме вопросы и ручная оценка Hebrew. Обучение mMARCO само по себе не доказывает качество на иврите. Внешние embedding/reranker не вызывались.

PDF: pypdf 5.9.0; таблицы pdfplumber 0.11.10 с точным сопоставлением диапазонов, неоднозначные ячейки требуют review. OCR: Tesseract 5.3.0, Hebrew traineddata 4.1, Poppler 22.12, 300 DPI, средний confidence ≥80. Реальный синтетический скан: 92.34; это не приёмка всех сканированных документов. DOCX: безопасный OOXML v2, body order, таблицы, наследование numbering/styles, decimal/letters/Roman/Hebrew numbering; unsupported formats требуют проверки.

Цены config/provider-prices.json проверены 09.10.2026: GPT-5.4 mini input/output $0.75/$4.50 за миллион tokens, GPT-4.1 mini $0.40/$1.60. Cached inputs учитываются по полной цене. Лимиты: запрос $0.20, сравнение $0.40, сутки $1.00. Резервы до каждого вызова сохраняются в PostgreSQL; неопределённый отказ расходует резерв. Реальная стоимость не измерена.

Источники: [E5](https://huggingface.co/intfloat/multilingual-e5-small), [MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [reranker](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), [pdfplumber](https://pypi.org/project/pdfplumber/), [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
