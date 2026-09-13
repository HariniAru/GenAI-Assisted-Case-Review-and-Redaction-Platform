from typing import Protocol

from huggingface_hub import InferenceClient

from app.config import get_settings
from app.schemas import AIRecommendationResponse, AISummaryResponse


class RecommendationProvider(Protocol):
    def recommend(self, description: str, types: list[str]) -> AIRecommendationResponse: ...
    def summarize(self, text: str) -> AISummaryResponse: ...


class HuggingFaceRecommendationProvider:
    def summarize(self, text: str) -> AISummaryResponse:
        settings = get_settings()
        if not settings.hf_token:
            raise RuntimeError("Hugging Face is not configured")
        client = InferenceClient(provider=settings.hf_provider, api_key=settings.hf_token)
        response = client.chat_completion(
            model=settings.hf_model,
            messages=[
                {
                    "role": "system",
                    "content": "Write one concise factual summary of this synthetic automotive case. Do not invent details. Return JSON with a summary string.\n/no_think",
                },
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "AISummaryResponse",
                    "schema": AISummaryResponse.model_json_schema(),
                    "strict": True,
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Hugging Face returned no summary")
        return AISummaryResponse.model_validate_json(content)

    def recommend(self, description: str, types: list[str]) -> AIRecommendationResponse:
        settings = get_settings()
        if not settings.hf_token:
            raise RuntimeError("Hugging Face is not configured")
        client = InferenceClient(provider=settings.hf_provider, api_key=settings.hf_token)
        prompt = (
            """You are assisting a reviewer of synthetic automotive customer-service case notes.
Suggest only clearly supported spans, and never save anything yourself.
PERSONAL_INFO: names, phone numbers, account numbers, addresses, or other identifying details. Example: '(555) 014-7821'.
CONFIDENTIAL: internal financial, pricing, settlement, or authorization information. Example: 'maximum settlement authorization is $4,000'.
PRIVILEGED: legal advice, counsel communications, or litigation strategy. Example: 'Co counsel adv team not to admit liability until investigation is complete.'.
HIGHLIGHT: an important safety, incident, or outcome phrase a reviewer should notice. Example: 'veh accelerated unexpectedly'.
Copy every suggested redaction exactly from the source, preserve punctuation and whitespace, and use a zero-based Unicode code-point starting position. Do not rewrite, normalize, expand abbreviations, or invent text. Return an empty list only when no supported span exists. Available types: """
            + ", ".join(types)
            + "\n/no_think"
        )
        response = client.chat_completion(
            model=settings.hf_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": description},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "AIRecommendationResponse",
                    "schema": AIRecommendationResponse.model_json_schema(),
                    "strict": True,
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Hugging Face returned no recommendations")
        return AIRecommendationResponse.model_validate_json(content)
