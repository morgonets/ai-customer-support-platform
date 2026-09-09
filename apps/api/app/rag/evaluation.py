from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.rag.models import Answer


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    question: str
    expect_answer: bool
    expected_source_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_name: str
    answer_state_correct: bool
    expected_source_cited: bool | None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    results: tuple[EvaluationResult, ...]

    @property
    def answer_state_accuracy(self) -> float:
        return sum(item.answer_state_correct for item in self.results) / len(self.results)

    @property
    def expected_source_recall(self) -> float | None:
        scored = [
            item.expected_source_cited
            for item in self.results
            if item.expected_source_cited is not None
        ]
        return None if not scored else sum(scored) / len(scored)


AnswerCallable = Callable[[str], Awaitable[Answer]]


async def evaluate(cases: Sequence[EvaluationCase], answer: AnswerCallable) -> EvaluationReport:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    results = []
    for case in cases:
        actual = await answer(case.question)
        cited = None
        if case.expected_source_id is not None:
            cited = any(item.source_id == case.expected_source_id for item in actual.citations)
        results.append(
            EvaluationResult(
                case_name=case.name,
                answer_state_correct=case.expect_answer != actual.insufficient_context,
                expected_source_cited=cited,
            )
        )
    return EvaluationReport(results=tuple(results))
