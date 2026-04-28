from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ProjectSpecData(BaseModel):
    project_name: str
    problem_statement: str
    target_users: List[str]
    goals: List[str]
    non_goals: List[str]
    functional_requirements: List[str]
    non_functional_requirements: List[str]
    core_entities: List[str]
    assumptions: List[str]
    constraints: List[str]
    open_questions: List[str]


class VersionedSpec(BaseModel):
    version: str = Field(default="v1")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = Field(default="draft")  # draft / approved
    data: ProjectSpecData