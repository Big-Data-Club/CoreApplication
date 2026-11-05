from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class NotebookAnnotation(BaseModel):
    version: Literal[1] = 1
    content_id: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=15000)
    prefix: str = Field(default="", max_length=80)
    suffix: str = Field(default="", max_length=80)
    start: int = Field(ge=0, le=2_000_000)
    end: int = Field(gt=0, le=2_000_000)
    color: Literal["yellow", "green", "blue", "pink"] = "yellow"

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("annotation end must follow start")
        return self


class NotebookSaveRequest(BaseModel):
    user_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=100000)
    course_id: Optional[int] = Field(default=None, gt=0)
    node_id: Optional[int] = None
    annotation: Optional[NotebookAnnotation] = None
