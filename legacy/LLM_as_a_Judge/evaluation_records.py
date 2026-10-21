"""評估流程共用的狀態與 token 紀錄模型。"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class StageUsage:
    """單題、單階段或單次 repair 的 token 使用紀錄。"""

    question_id: int
    stage: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    status: str = "not_started"
    attempt: Optional[int] = None
    model: str = ""

    def __post_init__(self):
        self.input_tokens = int(self.input_tokens or 0)
        self.output_tokens = int(self.output_tokens or 0)
        self.total_tokens = int(self.total_tokens or 0)
        self.calls = int(self.calls or 0)
        if not self.total_tokens:
            self.total_tokens = self.input_tokens + self.output_tokens

    def to_dict(self):
        return asdict(self)


@dataclass
class QuestionRunRecord:
    """每題不依賴 Judge 是否啟用的統一執行狀態。"""

    question_id: int
    question_text: str
    status: str = "pending"
    execution_success: Optional[bool] = None
    execution_error: str = ""
    repair_attempts: int = 0
    judge_status: str = "not_requested"
    code_correct: Optional[bool] = None
    needs_review: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class EvaluationLedger:
    """集中保存逐題狀態與逐階段用量，避免例外造成分帳遺失。"""

    stage_usages: List[StageUsage] = field(default_factory=list)
    questions: Dict[int, QuestionRunRecord] = field(default_factory=dict)

    def start_question(self, question_id, question_text):
        record = QuestionRunRecord(
            question_id=int(question_id),
            question_text=str(question_text),
        )
        self.questions[record.question_id] = record
        return record

    def update_question(self, question_id, **changes):
        record = self.questions[int(question_id)]
        for name, value in changes.items():
            if not hasattr(record, name):
                raise ValueError(f"未知的題目狀態欄位: {name}")
            setattr(record, name, value)
        return record

    def record_stage(
        self,
        question_id,
        stage,
        usage=None,
        *,
        status="completed",
        calls=1,
        attempt=None,
        model="",
    ):
        usage = usage or {}
        record = StageUsage(
            question_id=int(question_id),
            stage=str(stage),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            calls=calls,
            status=status,
            attempt=attempt,
            model=model,
        )
        self.stage_usages.append(record)
        return record

    def usage_for_question(self, question_id, exclude_stages=()):
        excluded = set(exclude_stages)
        records = [
            item for item in self.stage_usages
            if item.question_id == int(question_id)
            and item.stage not in excluded
        ]
        return {
            "input_tokens": sum(item.input_tokens for item in records),
            "output_tokens": sum(item.output_tokens for item in records),
            "total_tokens": sum(item.total_tokens for item in records),
            "calls": sum(item.calls for item in records),
        }

    def usage_for_stage(self, stage):
        records = [
            item for item in self.stage_usages
            if item.stage == stage
        ]
        return {
            "input_tokens": sum(item.input_tokens for item in records),
            "output_tokens": sum(item.output_tokens for item in records),
            "total_tokens": sum(item.total_tokens for item in records),
            "calls": sum(item.calls for item in records),
        }

    def stage_dicts(self):
        return [item.to_dict() for item in self.stage_usages]

    def question_dicts(self):
        return [
            self.questions[key].to_dict()
            for key in sorted(self.questions)
        ]
