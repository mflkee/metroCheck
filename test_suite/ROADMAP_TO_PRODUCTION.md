# Дорожная карта: metroCheck к production-ready состоянию

**Статус на 2026-06-24:** production pipeline протестирован на 37 ARSHIN-matched протоколах. Средняя точность **85.9%** без использования LLM/vision fallback. Основные расхождения — разные события поверки одного серийника в АРШИН, а не ошибки парсинга.

## Что уже сделано

| Компонент | Что сделано | Файл |
|-----------|-------------|------|
| File detection | Magic bytes вместо расширений | `backend/app/services/protocol_scanner.py` |
| OCR pipeline | Текстовый слой PDF → OCR fallback; препроцессинг; OSD авто-поворот | `backend/app/services/protocol_scanner.py` |
| Regex extraction | Богатые шаблоны для всех полей, включая device_name/type/range, methodology | `backend/app/services/protocol_extraction_service.py` |
| AI fallback | OpenRouter chain (kimi-k2.6, gemini, nemotron) | `backend/app/services/ai_extraction_service.py` |
| Vision fallback | GPT-4o, Claude, Llama-vision для JPG/PNG | `backend/app/services/ai_extraction_service.py` |
| Production test runner | Тесты используют тот же код, что и бэкенд | `test_suite/prod_test_runner.py` |
| Report system | summary.md + errors.json/csv + per_file.json + recommendations.md | `test_suite/prod_test_runner.py` |
| Error analysis | Актуальный анализ расхождений с АРШИН | `test_suite/ERROR_ANALYSIS.md` |

## Текущие метрики (production pipeline, без LLM)

| Поле | Точность | Комментарий |
|------|----------|-------------|
| serial_number | 100% | Идеально |
| result | 100% | Идеально |
| device_name | 89.2% | Осталось 4 сложных случая |
| mit_number | 89.2% | 4 расхождения; часто разные госреестры в разное время |
| verification_date | 51.4% | **Не ошибка парсинга** — разные события поверки в АРШИН |

## Что нужно доделать для production-ready

### 1. Улучшить сравнение с АРШИН (высокий приоритет)

**Проблема:** ARSHIN public API по `mi_number` возвращает только последнюю запись. Если серийник поверялся несколько раз, протокол и АРШИН могут иметь разные даты/MIT.

**Решение:**
- Запрашивать у АРШИН **все** записи по серийнику (`rows=100` или пагинация).
- Считать совпадением, если дата протокола присутствует среди записей АРШИН.
- Добавить статус `arshin_multi_event` — предупреждение, а не ошибка.
- Для `mit_number` — если протокольный MIT есть в истории записей АРШИН, считать OK.

**Где менять:** `backend/app/services/arshin_service.py`, `backend/app/integrations/arshin_client.py`.

### 2. Per-field extraction method tracking (высокий приоритет)

**Зачем:** понимать, какой источник дал каждое поле: regex / OCR / LLM / vision. Это нужно для аудита и отладки.

**Решение:**
- Возвращать из `ProtocolExtractionService.extract()` не только `content`, но и `sources: dict[str, str]`.
- Примеры источников: `regex`, `ocr_fallback`, `llm`, `vision`, `filename`.
- Сохранять в БД в отдельную колонку или JSONB.

**Где менять:** `backend/app/services/protocol_extraction_service.py`, модель `ProtocolFile`/`ProtocolCheck`.

### 3. Confidence-based routing (высокий приоритет)

**Цель:** автоматически решать, когда звать LLM, а когда отправлять на ручную проверку.

**Текущая логика:**
- confidence < 0.6 + missing critical → AI fallback.
- confidence < 0.35 + image → vision fallback.
- status = manual_review если confidence < 0.4.

**Рекомендуемые улучшения:**
- Если confidence < 0.5 после regex → LLM fallback.
- Если LLM не восполнил critical fields (`serial_number`, `verification_date`, `result`, `owner`) → manual_review.
- Если confidence >= 0.8 → skip LLM для экономии.
- Добавить поле `needs_review_reason`.

### 4. Обработка оставшихся ошибок device_name (средний приоритет)

**Осталось 4 кейса:**

| Файл | Извлечено | АРШИН |
|------|-----------|-------|
| `2025.06.27 №D704D40104E` | Уровнемер микроимпульсный Levelflex M | 26355-09 (в АРШИН вместо названия — MIT) |
| `2024.03.20 - 9479` | Термопреобразователь с унифицированным выходным сигналом ТСМУ-205 | Преобразователи термоэлектрические |
| `2025.06.10 № 2456` | (пусто) | Системы газоаналитические |
| `2025.04.24 - 9439073` | Преобразователь давления измерительный 2051 С | Датчики давления |

**Решение:**
- Для пустых или низко-confidence названий — принудительный LLM fallback.
- Добавить шаблоны для нестандартных протоколов (газоанализаторы, системы).
- Учитывать `mit_title` из АРШИН как подсказку для LLM.

### 5. MIT number — повысить точность (средний приоритет)

**Ошибки:**
- `242-0714` вместо `28041-08` — спарсился номер методики, а не госреестра.
- `15200-06` vs `61084-15` — разные записи АРШИН.
- `72341-18` vs `66815-17` — разные записи АРШИН.
- `26355-09` vs пусто — в АРШИН для этого СИ нет MIT.

**Решение:**
- Искать MIT только в секции «Государственный реестр», а не во всём тексте.
- Исключать номера методик (`МП-242-0714`) из кандидатов.
- Если regex не уверен — спрашивать LLM.

### 6. Мониторинг и алёртинг (средний приоритет)

**Метрики для Grafana:**
- Доля `manual_review` по месяцу.
- Количество OCR-ошибок.
- Средний confidence.
- Распределение источников полей (regex / LLM / vision).
- Стоимость LLM-запросов.

**Алерты:**
- manual_review > 5% за сутки.
- OCR errors > 0 за час.
- LLM fallback failure rate > 20%.

### 7. Тестирование на реальных месяцах (высокий приоритет)

**Что сделать:**
- Прогнать `prod_test_runner.py` на 2025-11 и 2025-12 (пользователь говорил, что там почти всё зелёное).
- Сравнить с промежуточными отчётами из продакшена.
- Если расхождения — разобрать кейсы и дополнить regex.

### 8. Документация и обучение операторов (низкий приоритет)

- Страница «Требования к фото протоколов» в веб-интерфейсе.
- Подсказки при upload: минимальное разрешение, контраст, отсутствие бликов.

## План деплоя

1. **Смержить текущие изменения** в `main`:
   - `protocol_extraction_service.py` — улучшения `_extract_device_name`.
   - `ai_extraction_service.py` — защита от пустого OPENROUTER_API_KEY.
   - `test_suite/prod_test_runner.py` — новый production test runner.
   - `test_suite/accuracy_test.py` — улучшенный stem.
   - `test_suite/ERROR_ANALYSIS.md` и `ROADMAP_TO_PRODUCTION.md`.

2. **Задеплоить на staging** через GitHub Actions.

3. **Проверить staging:**
   - health endpoint;
   - загрузить 10–20 реальных протоколов;
   - убедиться, что confidence и статусы корректны.

4. **Промоут в production** через GitHub UI.

5. **После деплоя:**
   - запустить тест на 2025-11/12;
   - настроить мониторинг manual_review.

## Критерий готовности

metroCheck считается production-ready, когда:
- [x] PDF с текстовым слоем обрабатываются без OCR.
- [x] Сканы обрабатываются OCR + препроцессингом.
- [x] При низком confidence есть LLM fallback.
- [x] При плохом OCR у изображений есть vision fallback.
- [x] Файлы определяются по magic bytes.
- [ ] Сравнение с АРШИН учитывает несколько поверок одного серийника.
- [ ] Есть мониторинг manual_review + алёрты.
- [ ] Протестировано на 2025-11 и 2025-12.
- [ ] Задеплоено в production.

## Следующий шаг

Рекомендую начать с **пункта 1** — улучшить сравнение с АРШИН. Это сразу поднимет `verification_date` и `mit_number` до реальных 90%+, потому что большинство «ошибок» сейчас — это просто другие события поверки.
