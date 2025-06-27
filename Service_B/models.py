from pydantic import BaseModel

class ProvisioningParams(BaseModel):
    username: str
    password: str
    vlan: int | None = None
    interfaces: list[int]


class ProvisioningRequest(BaseModel):
    timeoutInSeconds: int
    parameters: list[ProvisioningParams]


class TaskCreationResponse(BaseModel):
    code: int = 202
    taskId: str
