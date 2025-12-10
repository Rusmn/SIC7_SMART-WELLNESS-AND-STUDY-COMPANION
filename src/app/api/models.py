from pydantic import BaseModel


class PlanRequest(BaseModel):
    duration_min: int


class AckRequest(BaseModel):
    milestone_id: int


class ClothingRequest(BaseModel):
    insulation: int
