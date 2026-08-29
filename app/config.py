"""Central configuration, loaded from environment variables (see .env.example)."""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_settings() -> dict:
    """Read and cache all runtime settings from the environment."""
    return {
        # -- Google AI -------------------------------------------------------
        # Gemini access. Use GEMINI_API_KEY (Gemini API) and/or GEMINI_PROJECT
        # + GEMINI_LOCATION (Vertex AI). ADK resolves the credential via the
        # genai SDK, just like it does for `Agent(model=...)`.
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "gemini_project": os.getenv("GEMINI_PROJECT", ""),
        "gemini_location": os.getenv("GEMINI_LOCATION", "us-central1"),
        # The Gemin model identifier. Defaults to Google Flash for low cost.
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        # -- Storage ---------------------------------------------------------
        # firestore | local  (local = a JSON file tree, for a GCP-free demo)
        "store_backend": os.getenv("STORE_BACKEND", "firestore"),
        # For firestore: the project + collection prefix (if different from ADC)
        "firestore_project": os.getenv("FIRESTORE_PROJECT", ""),
        "firestore_prefix": os.getenv("FIRESTORE_PREFIX", "atlas"),
        # For local backend this file/dir is created at runtime.
        "local_store_path": os.getenv("LOCAL_STORE_PATH", "./atlas_data"),
        # -- Runtime ---------------------------------------------------------
        "max_steps_per_task": int(os.getenv("MAX_STEPS_PER_TASK", "30")),
        "max_turns_per_step": int(os.getenv("MAX_TURNS_PER_STEP", "8")),
        "spring_batch": int(os.getenv("SPRING_BATCH", "5")),
        "app_host": os.getenv("APP_HOST", "0.0.0.0"),
        "app_port": int(os.getenv("APP_PORT", "8080")),
        # -- Optional integrations -------------------------------------------
        # If present, the web_search tool can do real searches via SerpAPI.
        "serpapi_key": os.getenv("SERPAPI_KEY", ""),
    }


def get(key: str):
    return get_settings()[key]
