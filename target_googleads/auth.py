"""Authentication helpers for GoogleAds."""

from __future__ import annotations

from hotglue_singer_sdk.target_sdk.auth import OAuthAuthenticator


class GoogleAdsAuthenticator(OAuthAuthenticator):
    """OAuth 2.0 refresh-token authenticator for GoogleAds."""
