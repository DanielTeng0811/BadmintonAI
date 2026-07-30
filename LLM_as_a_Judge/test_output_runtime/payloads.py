"""領域無關、不可攜帶任意程式碼的標準呈現 payload。"""

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional, Sequence


MAX_ROWS = 1_000
MAX_POINTS = 10_000
MAX_SERIES = 12
MAX_BAR_SERIES = 6
MAX_PANELS = 4
MAX_TEXT_LENGTH = 5_000
MAX_LABEL_LENGTH = 120

ScalarValue = Optional[str | int | float | bool]


def _validate_text(value: str, field: str, limit=MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} 必須是字串")
    if len(value) > limit:
        raise ValueError(f"{field} 超過長度上限 {limit}")
    return value


def _validate_scalar(value: Any, field: str) -> ScalarValue:
    if value is not None and type(value) not in {str, int, float, bool}:
        raise TypeError(f"{field} 只能是 JSON scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field} 不可為 NaN 或無限值")
    if isinstance(value, str):
        _validate_text(value, field)
    return value


def _validate_labels(labels: Sequence[Any], field: str) -> tuple[str, ...]:
    labels = tuple(labels)
    for label in labels:
        if type(label) not in {str, int, float, bool}:
            raise TypeError(f"{field} 只能包含 scalar")
        if isinstance(label, float) and not math.isfinite(label):
            raise ValueError(f"{field} 不可包含 NaN 或無限值")
    result = tuple(str(label) for label in labels)
    for label in result:
        _validate_text(label, field, MAX_LABEL_LENGTH)
    return result


@dataclass(frozen=True)
class ScalarResult:
    """單一數值或短文字結果。"""

    label: str
    value: ScalarValue
    unit: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        _validate_text(self.label, "label", MAX_LABEL_LENGTH)
        _validate_scalar(self.value, "value")
        _validate_text(self.unit, "unit", MAX_LABEL_LENGTH)
        _validate_text(self.note, "note")


@dataclass(frozen=True)
class RecordResult:
    """欄位一致的 record 清單；不接受巢狀物件。"""

    records: Sequence[Mapping[str, ScalarValue]]
    columns: Sequence[str] = ()
    title: str = ""

    def __post_init__(self) -> None:
        records = tuple(dict(record) for record in self.records)
        if len(records) > MAX_ROWS:
            raise ValueError(f"records 最多 {MAX_ROWS} 筆")
        columns = tuple(self.columns)
        if not columns:
            columns = tuple(dict.fromkeys(
                key for record in records for key in record
            ))
        _validate_labels(columns, "columns")
        column_set = set(columns)
        for index, record in enumerate(records):
            if any(not isinstance(key, str) for key in record):
                raise TypeError("record key 必須是字串")
            if set(record) - column_set:
                raise ValueError(f"第 {index} 筆 record 含未宣告欄位")
            for key, value in record.items():
                _validate_scalar(value, f"records[{index}].{key}")
        _validate_text(self.title, "title", MAX_LABEL_LENGTH)
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "columns", columns)


@dataclass(frozen=True)
class TableResult:
    """明確欄名與列資料的表格。"""

    columns: Sequence[str]
    rows: Sequence[Sequence[ScalarValue]]
    title: str = ""

    def __post_init__(self) -> None:
        columns = _validate_labels(self.columns, "columns")
        rows = tuple(tuple(row) for row in self.rows)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"rows 最多 {MAX_ROWS} 筆")
        for row_index, row in enumerate(rows):
            if len(row) != len(columns):
                raise ValueError(f"第 {row_index} 列長度與 columns 不一致")
            for col_index, value in enumerate(row):
                _validate_scalar(value, f"rows[{row_index}][{col_index}]")
        _validate_text(self.title, "title", MAX_LABEL_LENGTH)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True)
class ChartSeries:
    """圖表序列；scatter 以 labels 表示 X、values 表示 Y。"""

    name: str
    labels: Sequence[Any]
    values: Sequence[int | float]

    def __post_init__(self) -> None:
        _validate_text(self.name, "name", MAX_LABEL_LENGTH)
        labels = _validate_labels(self.labels, "labels")
        values = tuple(self.values)
        if len(labels) != len(values):
            raise ValueError("labels 與 values 長度必須一致")
        if len(values) > MAX_POINTS:
            raise ValueError(f"每個 series 最多 {MAX_POINTS} 點")
        for value in values:
            if type(value) not in {int, float}:
                raise TypeError("chart values 只能是數值")
            if not math.isfinite(value):
                raise ValueError("chart values 不可為 NaN 或無限值")
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class HeatmapPoints:
    """連續二維點資料；可選非負權重。"""

    x: Sequence[int | float]
    y: Sequence[int | float]
    weights: Optional[Sequence[int | float]] = None

    def __post_init__(self) -> None:
        x = tuple(self.x)
        y = tuple(self.y)
        weights = tuple(self.weights) if self.weights is not None else None
        if len(x) != len(y):
            raise ValueError("heatmap x 與 y 長度必須一致")
        if len(x) > MAX_POINTS:
            raise ValueError(f"heatmap 最多 {MAX_POINTS} 點")
        if weights is not None and len(weights) != len(x):
            raise ValueError("heatmap weights 長度必須與座標一致")
        for value in (*x, *y, *(weights or ())):
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError("heatmap 座標與權重必須是有限數值")
        if weights is not None and any(value < 0 for value in weights):
            raise ValueError("heatmap weights 不可為負值")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "weights", weights)


COMPOSITE_KINDS = {
    "text", "table", "bar", "pie", "line", "scatter", "heatmap"
}


@dataclass(frozen=True)
class CompositeItem:
    """複合輸出的單一受限面板。"""

    kind: str
    payload: Any
    title: str = ""

    def __post_init__(self) -> None:
        if self.kind not in COMPOSITE_KINDS:
            raise ValueError("composite kind 不在白名單")
        _validate_text(self.title, "title", MAX_LABEL_LENGTH)


@dataclass(frozen=True)
class CompositeResult:
    """最多四個文字、表格或圖表面板。"""

    items: Sequence[CompositeItem]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if not items:
            raise ValueError("composite 至少需要一個 item")
        if len(items) > MAX_PANELS:
            raise ValueError(f"composite 最多 {MAX_PANELS} 個面板")
        if any(not isinstance(item, CompositeItem) for item in items):
            raise TypeError("composite items 必須是 CompositeItem")
        object.__setattr__(self, "items", items)
