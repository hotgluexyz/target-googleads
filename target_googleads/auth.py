"""Authentication helpers for GoogleAds."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import requests
from hotglue_singer_sdk.target_sdk.auth import OAuthAuthenticator


class GoogleAdsAuthenticator(OAuthAuthenticator):
    """OAuth 2.0 refresh-token authenticator for GoogleAds."""

    def __init__(
        self,
        target,
        state,
        auth_endpoint: Optional[str] = None,
    ) -> None:
        """Initialize the authenticator.

        Args:
            target: The Singer target instance.
            state: Authentication state.
            auth_endpoint: Token endpoint URL (from ``target.access_token_support``).
        """
        super().__init__(target, state, auth_endpoint=auth_endpoint)

    @property
    def oauth_request_body(self) -> dict:
        """OAuth request body for the refresh-token grant."""
        return {
            "refresh_token": self._config["refresh_token"],
            "grant_type": "refresh_token",
            "client_id": self._config["client_id"],
            "client_secret": self._config["client_secret"],
        }

    def _update_access_token_locally(self) -> None:
        """Refresh the access token.

        Google often omits ``refresh_token`` on refresh responses; keep the existing
        refresh token when that happens.
        """
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        self.logger.info(
            "OAuth request - endpoint: %s, grant_type: refresh_token",
            self._auth_endpoint,
        )
        token_response = requests.post(
            self._auth_endpoint,
            data=self.oauth_request_body,
            headers=headers,
            timeout=30,
        )

        try:
            token_response.raise_for_status()
            self.logger.info("OAuth authorization attempt was successful.")
        except Exception as ex:
            try:
                error_body = token_response.json()
            except Exception:
                error_body = token_response.text
            self.state.update({"auth_error_response": error_body})
            raise RuntimeError(
                f"Failed OAuth login, response was '{error_body}'. {ex}"
            ) from ex

        token_json = token_response.json()
        self.access_token = token_json["access_token"]
        self._config["access_token"] = token_json["access_token"]

        if token_json.get("refresh_token"):
            self._config["refresh_token"] = token_json["refresh_token"]

        now = round(datetime.utcnow().timestamp())
        self._config["expires_in"] = int(token_json["expires_in"]) + now

        if self._config_file_path:
            with open(self._config_file_path, "w") as outfile:
                json.dump(self._config, outfile, indent=4)
