"""Runtime config — base URL, env-var token fallback, keyring service name."""
import os

DEFAULT_BASE_URL = "https://www.mylifenote.ai"
KEYRING_SERVICE = "mylifenote"
KEYRING_USERNAME = "agent-token"
ENV_TOKEN_VAR = "LIFENOTE_API_TOKEN"
ENV_BASE_URL_VAR = "LIFENOTE_BASE_URL"


def base_url() -> str:
    return os.environ.get(ENV_BASE_URL_VAR, DEFAULT_BASE_URL).rstrip("/")
