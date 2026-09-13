import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient


def main() -> None:
    load_dotenv()
    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is missing from backend/.env")
    client = InferenceClient(provider=os.getenv("HF_PROVIDER", "nscale"), api_key=token)
    response = client.chat_completion(
        model=os.getenv("HF_MODEL", "Qwen/Qwen3-32B"),
        # messages=[{"role": "user", "content": "Say hello in one short sentence."}],
        messages=[{"role": "user", "content": "Name three fruits."}],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
