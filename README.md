# Async Equipment Provisioning Service

## 📌 Описание

Реализация микросервисной архитектуры для асинхронной конфигурации оборудования через очередь сообщений.

Проект состоит из трёх компонентов:

- **Service B** — основной HTTP API, который создает задачи и отслеживает их статус;
- **Worker** — слушает очередь задач, вызывает внешний сервис и отправляет результат;
- **Service A (stub)** — заглушка внешнего конфигурационного сервиса, симулирующая ответ через 60 секунд;
- **Redis** — хранилище задач;
- **RabbitMQ** — брокер сообщений.

---
## Диаграмма взаимодействия

На диаграмме ниже показан полный жизненный цикл задачи от создания до проверки результата.

```mermaid
sequenceDiagram
    participant Client
    participant Service B
    participant RabbitMQ
    participant Redis
    participant Worker
    participant Service A

    %% --- Фаза 1: Создание задачи ---
    Client->>+Service B: POST /api/v1/equipment/cpe/{id} (создать задачу)
    Service B->>RabbitMQ: publish(сообщение с задачей в tasks_queue)
    Service B->>Redis: SETEX(task_id, status="pending")
    Service B-->>-Client: 200 OK ({"taskId": "..."})

    %% --- Фаза 2: Обработка задачи Воркером ---
    Worker->>RabbitMQ: consume(сообщение из tasks_queue)
    Worker->>+Service A: POST /api/v1/equipment/cpe/{id} (выполнить конфигурацию)
    Note over Service A: Ждет 60 секунд...
    Service A-->>-Worker: 200 OK ({"message": "success"})
    Worker->>RabbitMQ: publish(результат в results_queue)
    
    %% --- Фаза 3: Обработка результата в Сервисе B ---
    Note over Service B: Фоновый consumer слушает results_queue
    Service B->>RabbitMQ: consume(сообщение с результатом)
    Service B->>Redis: SET(task_id, status="completed", result)

    %% --- Фаза 4: Проверка статуса Клиентом ---
    Client->>+Service B: GET /api/v1/equipment/cpe/{id}/task/{task_id}
    Service B->>Redis: GET(task_id)
    Service B-->>-Client: 200 OK ({"message": "Completed"})
```

## Описание компонентов
*   **Service A**: Синхронный сервис-заглушка...
*   **Service B**: Основной асинхронный API...
*   **Worker**: Обработчик задач из очереди...
*   **RabbitMQ**: Брокер сообщений...
*   **Redis**: Хранилище временных статусов задач...


## Как запустить

```bash
1. git clone https://github.com/BurkovAleksandr/Rostelecom.git
2. cd Rostelecom
Сгенерируйте SSL-сертификаты:
3. cd service_b/cert
4. openssl req -x509 -newkey rsa:2048 -nodes   -keyout ./key.pem -out ./cert.pem -days 365

Запуск:
5. docker compose up --build
```
