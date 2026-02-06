from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class DepsHealthResponse(BaseModel):
    redis: str
    postgresql: str
