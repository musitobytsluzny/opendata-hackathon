"""Explicit, small live check. Never print the key or provider exception body."""

from app.database.connection import settings
from google import genai
from google.genai import errors, types


def main():
    if not settings.gemini_api_key.get_secret_value().strip():
        raise SystemExit("GEMINI_API_KEY is missing")
    try:
        with genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        ) as client:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents="Reply with exactly the single word OK.",
                config=types.GenerateContentConfig(
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_level="low")
                    if settings.gemini_model.startswith("gemini-3")
                    else None,
                ),
            )
            if not response.text:
                raise SystemExit("Gemini returned no text")
        print(f"Gemini live check OK ({settings.gemini_model})")
    except errors.APIError as error:
        raise SystemExit(f"Gemini live check failed: HTTP {error.code}") from None


if __name__ == "__main__":
    main()
