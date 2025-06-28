import asyncio
import os
import aio_pika
import json
import logging
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
TASK_QUEUE_NAME = "tasks_queue"
RESULT_QUEUE_NAME = "results_queue"

A_SERVICE_URL = os.getenv("A_SERVICE_URL", "localhost")


async def handle_task(
    message: aio_pika.IncomingMessage,
    result_channel: aio_pika.Channel,
):
    async with message.process():
        try:
            data = json.loads(message.body.decode())
            logger.info(f"Received task: {data}")
            cpe_id = data.get("cpe_id")
            task_id = data.get("task_id")
            parameters = data.get("request")

            # Имитируем вызов внешнего сервиса A
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        A_SERVICE_URL + f"api/v1/equipment/cpe/{cpe_id}",
                        json=parameters,
                        timeout=70,
                    ) as resp:
                        result = await resp.json()
                        status = "completed" if resp.status == 200 else "failed"
                except Exception as e:
                    logger.error(f"Failed to call service A: {e}")
                    status = "failed"
                    result = {"error": str(e)}

            # Публикуем результат

            response = {
                "cpe_id": cpe_id,
                "task_id": task_id,
                "result": {
                    "status": status,
                    "timestamp": asyncio.get_event_loop().time(),
                    "payload": result,
                },
            }
            await result_channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(response).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=RESULT_QUEUE_NAME,
            )
            logger.info(f"Task {task_id} completed with status {status}")
        except Exception as e:
            logger.exception(f"Error handling message: {e}")


async def connect_rabbitmq(url):
    for i in range(10):
        try:
            connection = await aio_pika.connect_robust(url)
            return connection
        except Exception as e:
            print(f"Failed to connect to RabbitMQ, retrying in {2**i} seconds...")
            await asyncio.sleep(2**i)
    raise Exception("Could not connect to RabbitMQ after retries")


async def main():

    connection = await connect_rabbitmq(url=RABBITMQ_URL)
    # Канал для чтения задач
    task_channel = await connection.channel()
    task_queue = await task_channel.declare_queue(TASK_QUEUE_NAME, durable=True)

    # Канал для записи результатов
    result_channel = await connection.channel()
    await result_channel.declare_queue(RESULT_QUEUE_NAME, durable=True)
    await task_queue.consume(
        lambda msg: asyncio.create_task(handle_task(msg, result_channel=result_channel))
    )
    logger.info("Worker started.")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
