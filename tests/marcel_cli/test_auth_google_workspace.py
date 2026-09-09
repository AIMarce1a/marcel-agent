"""Google Workspace OAuth contract tests for Marcel."""

from datetime import datetime
from unittest.mock import patch

from marcel_cli.auth import (
    GOOGLE_WORKSPACE_ACCESS_TOKEN_ENV,
    GOOGLE_WORKSPACE_REFRESH_TOKEN_ENV,
    GOOGLE_WORKSPACE_SCOPES_ENV,
    GOOGLE_WORKSPACE_TOKEN_EXPIRY_ENV,
    get_google_workspace_credentials,
    google_workspace_scopes,
    login_google_workspace,
)


class _Credentials:
    refresh_token = "refresh-value"
    token = "initial-access"
    expiry = datetime(2030, 1, 1)

    def refresh(self, request):
        assert request == "safe-request"
        self.token = "verified-access"
        self.expiry = datetime(2030, 1, 1)


class _Flow:
    def __init__(self):
        self.credentials = _Credentials()
        self.run_kwargs = None

    def run_local_server(self, **kwargs):
        self.run_kwargs = kwargs
        return self.credentials


def test_google_workspace_scopes_include_only_selected_services():
    scopes = google_workspace_scopes(["gmail", "sheets"])
    assert any("gmail" in scope for scope in scopes)
    assert any("spreadsheets" in scope for scope in scopes)
    assert not any("calendar" in scope for scope in scopes)
    assert not any("/drive" in scope for scope in scopes)


def test_google_workspace_login_opens_consent_verifies_and_saves_env_only():
    flow = _Flow()
    saved = {}

    def flow_factory(config, *, scopes):
        assert config["installed"]["client_id"] == "client-id"
        assert "calendar" not in " ".join(scopes)
        return flow

    def save(key, value):
        saved[key] = value
        return {"success": True}

    env = {
        "GOOGLE_WORKSPACE_CLIENT_ID": "client-id",
        "GOOGLE_WORKSPACE_CLIENT_SECRET": "client-secret",
    }
    with (
        patch(
            "marcel_cli.config.get_env_value_prefer_dotenv",
            side_effect=lambda key: env.get(key),
        ),
        patch("marcel_cli.config.save_env_value_secure", side_effect=save),
    ):
        result = login_google_workspace(
            ["gmail"],
            _flow_factory=flow_factory,
            _request_factory=lambda: "safe-request",
            _verify=lambda _credentials, services: assert_services(services),
        )

    assert result["verified"] is True
    assert flow.run_kwargs["open_browser"] is True
    assert saved[GOOGLE_WORKSPACE_REFRESH_TOKEN_ENV] == "refresh-value"
    assert saved[GOOGLE_WORKSPACE_ACCESS_TOKEN_ENV] == "verified-access"
    assert "gmail" in saved[GOOGLE_WORKSPACE_SCOPES_ENV]
    assert "client-secret" not in str(result)


def assert_services(services):
    assert list(services) == ["gmail"]


def test_env_credentials_refresh_when_access_token_expiry_is_unknown():
    from google.oauth2.credentials import Credentials

    saved = {}
    env = {
        "GOOGLE_WORKSPACE_CLIENT_ID": "client-id",
        "GOOGLE_WORKSPACE_CLIENT_SECRET": "client-secret",
        "GOOGLE_WORKSPACE_REFRESH_TOKEN": "refresh-value",
        "GOOGLE_WORKSPACE_ACCESS_TOKEN": "expired-access",
        "GOOGLE_WORKSPACE_SCOPES": "https://www.googleapis.com/auth/gmail.modify",
    }
    with (
        patch(
            "marcel_cli.config.get_env_value_prefer_dotenv",
            side_effect=lambda key: env.get(key),
        ),
        patch(
            "marcel_cli.config.save_env_value_secure",
            side_effect=lambda key, value: saved.__setitem__(key, value),
        ),
        patch.object(
            Credentials,
            "refresh",
            new=lambda credentials, request: refresh_real_credentials(
                credentials, request
            ),
        ),
    ):
        resolved = get_google_workspace_credentials(
            _request_factory=lambda: "safe-request",
        )
    assert resolved.token == "verified-access"
    assert saved[GOOGLE_WORKSPACE_ACCESS_TOKEN_ENV] == "verified-access"
    assert saved[GOOGLE_WORKSPACE_TOKEN_EXPIRY_ENV] == "2030-01-01T00:00:00"


def refresh_real_credentials(credentials, request):
    assert request == "safe-request"
    credentials.token = "verified-access"
    credentials.expiry = datetime(2030, 1, 1)