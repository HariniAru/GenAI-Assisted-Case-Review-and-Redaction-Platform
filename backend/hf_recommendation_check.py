"""Standalone smoke test for the structured Hugging Face recommendation call."""

import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    redaction_type: str = Field(description="PERSONAL_INFO, CONFIDENTIAL, PRIVILEGED, or HIGHLIGHT")
    redaction_text: str = Field(description="Exact substring copied from the source")
    starting_position: int = Field(description="Zero-based character position")
    reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]


def main() -> None:
    load_dotenv()
    token = os.getenv("HF_TOKEN")
    model = os.getenv("HF_MODEL", "Qwen/Qwen3-32B")
    provider = os.getenv("HF_PROVIDER", "nscale")
    print(f"HF token loaded: {bool(token)}")
    print(f"Model: {model}")
    print(f"Provider: {provider}")
    if not token:
        raise SystemExit("HF_TOKEN is missing from backend/.env")

    description = (
        "Cust Priya Shah called from (555) 016-4402 re acct 998231. "
        "Internal review notes provisional reimbursement cap of $2,200. "
        "Counsel advises preserve inspection photos. Safety concern: brake pedal felt soft."
    )
    prompt = """Return useful redaction recommendations from this exact synthetic automotive case note.
PERSONAL_INFO means names, phone numbers, account numbers, and addresses.
CONFIDENTIAL means internal pricing, reimbursement, settlement, or authorization details.
PRIVILEGED means legal advice or counsel communications.
HIGHLIGHT means an important safety or incident phrase.
Copy text exactly, preserve punctuation, and use zero-based positions. Return JSON matching the schema. Do not return an empty list when clear examples exist.
/no_think"""
    client = InferenceClient(provider=provider, api_key=token)
    response = client.chat_completion(
        model=model,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": description}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "RecommendationResponse",
                "schema": RecommendationResponse.model_json_schema(),
                "strict": True,
            },
        },
    )
    content = response.choices[0].message.content
    print("Raw content:")
    print(content)
    if not content:
        raise SystemExit("The model returned empty content")
    parsed = RecommendationResponse.model_validate_json(content)
    print("Parsed recommendations:")
    for item in parsed.recommendations:
        end = item.starting_position + len(item.redaction_text)
        print(
            f"- {item.redaction_type}: {item.redaction_text!r} [{item.starting_position}:{end}] — {item.reason}"
        )


if __name__ == "__main__":
    main()
