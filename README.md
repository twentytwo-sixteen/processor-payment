# Payment Processor

Асинхронный процессинг платежей: FastAPI принимает запрос, PostgreSQL сохраняет
платеж и Outbox, один consumer FastStream вызывает эмулятор шлюза и отправляет webhook.
Идемпотентность защищает от дублей; доставка использует три попытки с задержками
2 / 4 секунды и DLQ. Ошибка webhook не повторяет оплату.

## Запуск

Требуется Docker с Compose. Команды выполняются из корня проекта.

```bash
cp .env.example .env
make up
```

Если `.env` уже существует, используйте его текущие настройки.
`make up` собирает образ, выполняет миграции и запускает все сервисы с demo receiver.

| Сервис | Адрес |
| --- | --- |
| API | [http://127.0.0.1:18081](http://127.0.0.1:18081) |
| PostgreSQL | localhost:15433 |
| RabbitMQ AMQP | localhost:15683 |
| RabbitMQ Management | [http://127.0.0.1:15684](http://127.0.0.1:15684) |
| Demo receiver | [http://127.0.0.1:18082](http://127.0.0.1:18082) |
| Worker metrics | [http://127.0.0.1:19001/metrics](http://127.0.0.1:19001/metrics) |

## API

Все эндпоинты требуют `X-API-Key`. Для создания обязателен `Idempotency-Key`.
Сумма передается строкой, валюты: RUB / USD / EUR. В примерах ключ из `.env.example`.

```bash
curl -i http://127.0.0.1:18081/api/v1/payments \
  -H 'X-API-Key: local-development-api-key-change-me' \
  -H 'Idempotency-Key: example-order-001' \
  -H 'Content-Type: application/json' \
  -d '{"amount":"100.00","currency":"RUB","description":"Order 001","metadata":{"order_id":"001"},"webhook_url":"http://webhook-receiver:8080/success"}'

curl http://127.0.0.1:18081/api/v1/payments/PAYMENT_ID \
  -H 'X-API-Key: local-development-api-key-change-me'
```

Создание возвращает `202` с payment_id, status и created_at. Повтор с тем же ключом
и содержимым возвращает исходный платеж; другое содержимое дает `409`.
GET возвращает данные платежа и состояние webhook.

Demo receiver поддерживает `/success`, `/fail-twice`, `/always-fail`; события доступны по `/events`.

## Проверки

```bash
make check
make test-all
make benchmark
```

Проверки выполняются в Docker; `make test-all` поднимает стенд самостоятельно.
Сквозные тесты временно останавливают сервисы Compose: запускайте их на локальном стенде.
JUnit-отчеты: `work/test-results/`. Benchmark измеряет прием запросов отдельно от процессинга.

## Управление

```bash
docker compose logs -f api consumer
make down
```
