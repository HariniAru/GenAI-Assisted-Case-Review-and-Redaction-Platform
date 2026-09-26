"""Shared generation helpers; neither endpoint nor graph validation saves drafts."""

from collections.abc import Collection
from typing import Protocol

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.ai_grounding import MAX_DESCRIPTION_CHARS, GroundingContext, build_grounding
from app.redaction_validation import matches_span
from app.schemas import AIRecommendation, GroundedAIRecommendation


class ActivityText(Protocol):
    description: str
    activity_uid: str


def retrieve_grounding(
    activity: ActivityText, retriever: BaseRetriever
) -> tuple[list[Document], GroundingContext]:
    if len(activity.description) > MAX_DESCRIPTION_CHARS:
        raise ValueError("Activity exceeds the AI recommendation input limit")
    documents = retriever.invoke(activity.description)
    return documents, build_grounding(documents, activity.activity_uid)


def valid(activity: ActivityText, types: Collection[str], recommendation: AIRecommendation) -> bool:
    return recommendation.redaction_type in types and matches_span(
        activity.description, recommendation.redaction_text, recommendation.starting_position
    )


def normalize_position(
    activity: ActivityText, recommendation: AIRecommendation
) -> AIRecommendation:
    """Correct an offset only when its exact text has one unambiguous match."""
    text = recommendation.redaction_text
    starts = [
        i for i in range(len(activity.description)) if activity.description.startswith(text, i)
    ]
    if len(starts) == 1 and starts[0] != recommendation.starting_position:
        return recommendation.model_copy(update={"starting_position": starts[0]})
    return recommendation


def validate_suggestions(
    activity: ActivityText,
    types: tuple[str, ...] | list[str],
    recommendations: list[AIRecommendation],
    grounding: GroundingContext,
    saved_spans: set[tuple[str, int]],
) -> list[GroundedAIRecommendation]:
    seen = set()
    output = []
    for suggestion in recommendations:
        rec = normalize_position(activity, suggestion)
        key = (rec.redaction_type, rec.redaction_text, rec.starting_position)
        if (
            key not in seen
            and rec.redaction_type in grounding.policies
            and valid(activity, types, rec)
            and (rec.redaction_text, rec.starting_position) not in saved_spans
        ):
            seen.add(key)
            output.append(
                GroundedAIRecommendation(
                    **rec.model_dump(), supporting_policy=grounding.policies[rec.redaction_type]
                )
            )
    return output
