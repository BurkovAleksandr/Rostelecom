import json
from unittest.mock import AsyncMock
from uuid import UUID
import uuid
import fakeredis
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from redis import Redis
from main import app, get_redis, get_sender


# @pytest.fixture()
# def redis_client():
#     return Redis(host="localhost", port=6379, db=0, decode_responses=True)


@pytest.fixture
def mocked_sender():
    mock = AsyncMock()
    return mock


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(mocked_sender, fake_redis):
    app.dependency_overrides[get_sender] = lambda: mocked_sender
    app.dependency_overrides[get_redis] = lambda: fake_redis
    with TestClient(app=app) as client:
        yield client
    app.dependency_overrides.clear()


def test_configuration_api_good(client: TestClient, fake_redis: fakeredis.FakeRedis):
    """Тест когда все данные правильные"""
    cpe_id = 123123123
    data = {
        "timeoutInSeconds": 0,
        "parameters": [
            {"username": "string", "password": "string", "vlan": 0, "interfaces": [0]}
        ],
    }
    response = client.post(f"/api/v1/equipment/cpe/{cpe_id}", json=data)
    print(response)
    assert response.status_code == 200
    data: dict = response.json()
    assert isinstance(data, dict)
    assert data.get("code") == 202
    assert data.get("taskId")
    assert UUID(data.get("taskId"))
    task_id = data.get("taskId")
    assert isinstance(task_id, str)
    redis_key = f"cpe:{cpe_id}:task:{task_id}"
    value = fake_redis.get(redis_key)
    assert value

    redis_data = json.loads(value)
    assert redis_data["status"] == "pending"


def test_configuration_api_bad_cpe_id(client: TestClient):
    """Тест с неправильным cpe_id"""
    cpe_id = 123
    data = {
        "timeoutInSeconds": 0,
        "parameters": [
            {"username": "string", "password": "string", "vlan": 0, "interfaces": [0]}
        ],
    }
    response = client.post(f"/api/v1/equipment/cpe/{cpe_id}", json=data)
    assert response.status_code == 422


def test_configuration_api_bad_data(client: TestClient):
    """Тест с неправильными параметрами"""
    cpe_id = 123
    data = {
        "parameters": [
            {"username": "string", "password": "string", "vlan": 0, "interfaces": [0]}
        ],
    }

    response = client.post(f"/api/v1/equipment/cpe/{cpe_id}", json=data)
    assert response.status_code == 422


def test_get_result_good(client: TestClient, fake_redis: fakeredis.FakeRedis):
    cpe_id = "ABC123"
    task_id = str(uuid.uuid4())
    redis_key = f"cpe:{cpe_id}:task:{task_id}"
    fake_redis.set(redis_key, json.dumps({"status": "completed"}))

    response = client.get(f"/api/v1/equipment/cpe/{cpe_id}/task/{task_id}")

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "Completed"}


def test_get_result_pending(client: TestClient, fake_redis: fakeredis.FakeRedis):
    cpe_id = "ABC123"
    task_id = str(uuid.uuid4())
    redis_key = f"cpe:{cpe_id}:task:{task_id}"
    fake_redis.set(redis_key, json.dumps({"status": "pending"}))

    response = client.get(f"/api/v1/equipment/cpe/{cpe_id}/task/{task_id}")

    assert response.status_code == 200
    assert response.json() == {"code": 204, "message": "Task is still running"}


def test_get_result_not_found(client: TestClient):
    cpe_id = "ABC123"
    task_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/equipment/cpe/{cpe_id}/task/{task_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "The requested task is not found"}


def test_get_result_500_error(client: TestClient, fake_redis):
    cpe_id = "ABC123"
    task_id = str(uuid.uuid4())
    redis_key = f"cpe:{cpe_id}:task:{task_id}"
    fake_redis.set(redis_key, "invalid")

    response = client.get(f"/api/v1/equipment/cpe/{cpe_id}/task/{task_id}")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal provisioning exception"}


def test_get_result_500_error_task_failed(client: TestClient, fake_redis):
    cpe_id = "XYZ456"
    task_id = str(uuid.uuid4())
    redis_key = f"cpe:{cpe_id}:task:{task_id}"

    fake_redis.set(redis_key, json.dumps({"status": "failed"}))

    response = client.get(f"/api/v1/equipment/cpe/{cpe_id}/task/{task_id}")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal provisioning exception"}
