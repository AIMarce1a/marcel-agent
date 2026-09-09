"""Single source of truth for release infrastructure readiness."""

MARCEL_RELEASE_PROVISIONED = True
MARCEL_RELEASE_REPOSITORY = "AIMarce1a/marcel-agent"
MARCEL_RELEASE_HTTPS_URL = "https://github.com/AIMarce1a/marcel-agent.git"
MARCEL_RELEASE_SSH_URL = "git@github.com:AIMarce1a/marcel-agent.git"
MARCEL_RELEASE_ARCHIVE_URL = "https://github.com/AIMarce1a/marcel-agent/archive/{ref}.zip"
MARCEL_RELEASE_BASE_URL = "https://github.com/AIMarce1a/marcel-agent"

# Attribution/comparison only. Never use this coordinate to install executable
# code into a Marcel environment.
UPSTREAM_COMPARISON_REPOSITORY = "https://github.com/NousResearch/hermes-agent.git"


def require_release_repository() -> str:
    if not MARCEL_RELEASE_PROVISIONED:
        raise RuntimeError("Marcel release infrastructure is not provisioned.")
    return MARCEL_RELEASE_REPOSITORY