from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
DistrictId = Literal[
    "CZ0321000000",
    "CZ0322000000",
    "CZ0323000000",
    "CZ0324000000",
    "CZ0325000000",
    "CZ0326000000",
    "CZ0327000000",
]
Metric = Literal["population", "seniors_pct", "children_pct", "greenery_pct", "ndvi"]


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    question: Question
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)


class AnswerRow(BaseModel):
    okres: DistrictId
    value: float = Field(allow_inf_nan=False)


class AnswerSource(BaseModel):
    name: str
    publisher: str
    period: str


class MapAnswer(BaseModel):
    metric: str
    short: str
    unit: str
    signed: bool = False
    rows: list[AnswerRow] = Field(max_length=7)
    source: AnswerSource


class ChatAnswer(BaseModel):
    text: str
    sample: bool = False
    metric: str | None = None
    short: str | None = None
    unit: str | None = None
    signed: bool = False
    rows: list[AnswerRow] | None = None
    source: AnswerSource | None = None
