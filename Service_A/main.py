import asyncio
import logging
from typing import Any
import fastapi
from fastapi.params import Path
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = fastapi.FastAPI()


class ProvisioningParams(BaseModel):
    username: str
    password: str
    vlan: int | None = None
    interfaces: list[int]


class ProvisioningRequest(BaseModel):
    timeoutInSeconds: int
    parameters: list[ProvisioningParams]


@app.post(path="/api/v1/equipment/cpe/{id}")
async def configure_equipment(
    request_body: ProvisioningRequest, id: str = Path(..., regex=r"^[a-zA-Z0-9]{6,}$")
) -> dict[str, Any]:
    """
    Функция конфигурации
    Добавил несколько специфичных id на которые заглушка будет реагировать по разному
    """
    logger.info(
        f"Received request for equipment {id} with timeout {request_body.timeoutInSeconds}s."
    )
    if id == "error500":
        logger.warning(f"Simulating internal error for {id}")
        raise fastapi.HTTPException(
            status_code=500,
            detail={"code": 500, "message": "Internal provisioning exception"},
        )
    if id == "notfound404":
        logger.warning(f"Simulating not found error for {id}")
        raise fastapi.HTTPException(
            status_code=404,
            detail={"code": 404, "message": "The requested equipment is not found"},
        )
    logger.info(f"Starting 60-second wait for {id}...")
    await asyncio.sleep(60)
    logger.info(f"Finished waiting for {id}. Sending success response.")

    return {"code": 200, "message": "success"}
