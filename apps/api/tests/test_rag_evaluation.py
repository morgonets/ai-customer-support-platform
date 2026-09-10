import asyncio
from uuid import UUID

import pytest

from app.rag.evaluation import EvaluationCase, evaluate
from app.rag.models import Answer, Citation

SOURCE_ID = UUID("10000000-0000-0000-0000-000000000001")


async def _answer(question: str) -> Answer:
    if question == "known":
        return Answer(
            text="Known",
            insufficient_context=False,
            citations=(
                Citation(
                    source_id=SOURCE_ID,
                    version_id=UUID("20000000-0000-0000-0000-000000000001"),
                    version_number=1,
                    source_title="Synthetic",
                    source_kind="article",
                    locator={"kind": "text"},
                    excerpt="Known",
                    answer_start=0,
                    answer_end=5,
                ),
            ),
        )
    return Answer(text="No answer", insufficient_context=True, citations=())


def test_synthetic_evaluation_reports_answer_state_and_source_recall() -> None:
    report = asyncio.run(
        evaluate(
            [
                EvaluationCase("known", "known", True, SOURCE_ID),
                EvaluationCase("unknown", "unknown", False),
                EvaluationCase(
                    "wrong source",
                    "known",
                    True,
                    UUID("10000000-0000-0000-0000-000000000002"),
                ),
            ],
            _answer,
        )
    )
    assert report.answer_state_accuracy == 1
    assert report.expected_source_recall == 0.5


def test_evaluation_requires_cases_and_can_have_no_source_metric() -> None:
    with pytest.raises(ValueError, match="at least one"):
        asyncio.run(evaluate([], _answer))
    report = asyncio.run(evaluate([EvaluationCase("unknown", "unknown", False)], _answer))
    assert report.expected_source_recall is None
