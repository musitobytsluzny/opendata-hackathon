"""Build the configured Google Gen AI client without exposing credentials."""

import json

import google.auth
from google import genai
from google.genai import types

from app.database.connection import settings


def create_gemini_client(*, retry_attempts: int = 3) -> genai.Client:
    http_options = types.HttpOptions(
        timeout=settings.gemini_timeout_seconds * 1000,
        retry_options=types.HttpRetryOptions(
            attempts=retry_attempts,
            http_status_codes=[500, 502, 503, 504],
        ),
    )
    if settings.gemini_provider == "vertex":
        adc_json = settings.google_adc_json.get_secret_value().strip()
        if adc_json:
            credentials, _ = google.auth.load_credentials_from_dict(
                json.loads(adc_json),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return genai.Client(
                enterprise=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                credentials=credentials,
                http_options=http_options,
            )
        return genai.Client(
            enterprise=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            http_options=http_options,
        )
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        vertexai=False,
        http_options=http_options,
    )
