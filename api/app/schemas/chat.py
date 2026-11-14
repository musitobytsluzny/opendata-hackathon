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
Metric = Literal["population", "seniors_pct", "children_pct", "greenery_pct", "ndvi", "area_m2"]


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    result_ids: list[str] = Field(default_factory=list, max_length=8)
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
    layer_actions: list["LayerAction"] = Field(default_factory=list, max_length=12)
    artifacts: list["ChatArtifact"] = Field(default_factory=list, max_length=12)
    sample: bool = False
    metric: str | None = None
    short: str | None = None
    unit: str | None = None
    signed: bool = False
    rows: list[AnswerRow] | None = None
    source: AnswerSource | None = None


class ResultColumn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(max_length=160)
    numeric: bool = False
    additive: bool = False
    unit: str = Field(default="", max_length=30)


class ChatArtifact(BaseModel):
    result_id: str = Field(max_length=60)
    title: str = Field(max_length=300)
    view: Literal["table", "map", "bar", "line", "pie"] = "table"
    columns: list[ResultColumn] = Field(max_length=8)
    rows: list[dict[str, str | Annotated[float, Field(allow_inf_nan=False)] | bool | None]] = Field(
        max_length=50
    )
    features: list[dict] = Field(default_factory=list, max_length=256)
    sources: list[dict] = Field(default_factory=list, max_length=8)
    note: str = Field(default="", max_length=2000)
    sample: bool = False
    value_key: str | None = None
    label_key: str | None = None


class LayerAction(BaseModel):
    result_id: str = Field(max_length=60)
    visible: bool


ChatAnswer.model_rebuild()
