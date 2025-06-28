import asyncio
from enum import Enum
import json
import logging
import os
from fastapi import Depends, FastAPI, HTTPException, Path, Response
from fastapi.concurrency import asynccontextmanager
import uuid
from models import ProvisioningRequest, TaskCreationResponse
import pika
import redis
import aio_pika

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


redis_pool: redis.ConnectionPool | None = None

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
REDIS_URL = os.getenv("REDIS_URL", "localhost")
TASK_QUEUE_NAME = "tasks_queue"
RESULT_QUEUE_NAME = "results_queue"


def get_redis() -> redis.Redis:
    if redis_pool is None:
        raise RuntimeError("Redis pool is not initialized yet")
    return redis.Redis(connection_pool=redis_pool)


async def results_consumer():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue(RESULT_QUEUE_NAME, durable=True)

    redis_client = get_redis()
    logger.info("Results queue listener started")
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                try:
                    body = json.loads(message.body.decode())
                    task_id = body.get("task_id")
                    cpe_id = body.get("cpe_id")
                    result = body.get("result", {})

                    redis_key = f"cpe:{cpe_id}:task:{task_id}"
                    redis_client.setex(redis_key, 60 * 5, json.dumps(result))
                    logger.info(f"Saved result for {redis_key} -> {result}")
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool
    redis_pool = redis.ConnectionPool(
        host=REDIS_URL, port=6379, db=0, decode_responses=True
    )
    logger.info("Redis client initialized")

    consumer_task = asyncio.create_task(results_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        logger.info("RabbitMQ consumer task cancelled")

    redis_pool.close()
    logger.info("Redis connection closed")


app = FastAPI(lifespan=lifespan)


class TaskStatus(Enum):
    RUNNING = "Task is still running"
    COMPLETED = "Completed"


async def send_to_queue(body: dict):
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.declare_queue(TASK_QUEUE_NAME, durable=True)

    message = aio_pika.Message(
        body=json.dumps(body).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await channel.default_exchange.publish(message, routing_key=TASK_QUEUE_NAME)
    await connection.close()


@app.post("/api/v1/equipment/cpe/{cpe_id}")
async def task_creation_api(
    request_body: ProvisioningRequest,
    cpe_id: str = Path(..., pattern=r"^[a-zA-Z0-9]{6,}$"),
    redis_client: redis.Redis = Depends(get_redis),
) -> TaskCreationResponse:
    task_id = str(uuid.uuid4())

    message = {
        "cpe_id": cpe_id,
        "task_id": task_id,
        "request": request_body.model_dump(),
    }
    redis_client.setex(
        f"cpe:{cpe_id}:task:{task_id}",
        60 * 5,
        json.dumps({"status": "pending"}),
    )
    await send_to_queue(message)

    logger.info(f"Task request for equipment {cpe_id} with task_id: {task_id}.")

    return TaskCreationResponse(taskId=task_id)


@app.get("/api/v1/equipment/cpe/{id}/task/{task_id}")
def result_check_api(
    id: str = Path(..., pattern=r"^[a-zA-Z0-9]{6,}$"),
    task_id: uuid.UUID = Path(...),
    redis_client: redis.Redis = Depends(get_redis),
):
    redis_key = f"cpe:{id}:task:{str(task_id)}"
    raw_value = redis_client.get(redis_key)

    if raw_value is None:
        raise HTTPException(status_code=404, detail="The requested task is not found")

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Internal provisioning exception")

    status = value.get("status")

    if status == "pending":
        return Response(
            content=json.dumps({"code": 204, "message": "Task is still running"}),
            status_code=200,
            media_type="application/json",
        )

    if status == "failed":
        raise HTTPException(status_code=500, detail="Internal provisioning exception")

    return {"code": 200, "message": "Completed"}
