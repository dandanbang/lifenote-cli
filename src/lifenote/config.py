"""Runtime config — base URL, env-var token fallback, keyring service name."""
import os

DEFAULT_BASE_URL = "https://www.mylifenote.ai"
KEYRING_SERVICE = "mylifenote"
KEYRING_USERNAME = "agent-token"                 # device-login session (access + refresh)
KEYRING_PAT_USERNAME = "personal-access-token"   # `lifenote token create --save`
ENV_TOKEN_VAR = "LIFENOTE_TOKEN"
ENV_TOKEN_VAR_LEGACY = "LIFENOTE_API_TOKEN"      # still honored
ENV_BASE_URL_VAR = "LIFENOTE_BASE_URL"

# Exit codes (documented in the README; scripts and cron rely on them).
EXIT_OK = 0
EXIT_USAGE = 2      # bad flag or value, or the server rejected the request as invalid
EXIT_AUTH = 3       # not signed in, or the token is expired, revoked, or invalid
EXIT_NETWORK = 4    # could not reach Life Note
EXIT_SERVER = 5     # Life Note answered with an error (5xx, rate limit)


def base_url() -> str:
    return os.environ.get(ENV_BASE_URL_VAR, DEFAULT_BASE_URL).rstrip("/")
