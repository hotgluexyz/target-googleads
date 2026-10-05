"""GoogleAds target class."""

from __future__ import annotations

from hotglue_singer_sdk import typing as th
from hotglue_singer_sdk.target_sdk.target import TargetHotglue
from target_googleads.auth import GoogleAdsAuthenticator
from target_googleads.sinks import AudienceMembersSink, AudiencesSink


class TargetGoogleAds(TargetHotglue):
    """Target for GoogleAds."""

    name = "target-googleads"
    SINK_TYPES = [AudiencesSink, AudienceMembersSink]

    config_jsonschema = th.PropertiesList(
        th.Property(
            "client_id",
            th.StringType(),
            required=True,
            description="OAuth client ID for the Google token endpoint",
        ),
        th.Property(
            "client_secret",
            th.StringType(),
            required=True,
            description="OAuth client secret for the Google token endpoint",
        ),
        th.Property(
            "refresh_token",
            th.StringType,
            required=True,
            description="Refresh token used to obtain new access tokens",
        ),
        th.Property(
            "access_token",
            th.StringType,
            required=False,
            description="Current access token (usually populated after refresh)",
        ),
        th.Property(
            "expires_in",
            th.IntegerType,
            required=False,
            description="Epoch seconds when the access token expires (updated on refresh)",
        ),
        th.Property(
            "customer_id",
            th.StringType(),
            required=True,
            description="Google Ads customer ID (with or without dashes)",
        ),
        th.Property(
            "product_destination_id",
            th.StringType(),
            required=False,
            description=(
                "Default Customer Match user list ID used as productDestinationId "
                "for AudienceMembers when not set on the record"
            ),
        ),
    ).to_dict()

    @classmethod
    def access_token_support(cls, connector=None):
        return (
            GoogleAdsAuthenticator,
            "https://oauth2.googleapis.com/token",
        )


if __name__ == "__main__":
    TargetGoogleAds.cli()
