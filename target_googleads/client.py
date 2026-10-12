"""HTTP client and sink base classes for GoogleAds."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from hotglue_singer_sdk.target_sdk.client import HotglueBaseSink, HotglueBatchSink, HotglueSink


class GoogleAdsSink(HotglueBaseSink):
    """GoogleAds Base target sink class for sinks."""

    base_url = "https://datamanager.googleapis.com/v1"
    auth_state = {}

    def __init__(
        self,
        target: Any,
        stream_name: str,
        schema: dict,
        key_properties: list[str] | None,
    ) -> None:
        """Build one authenticator and reuse it for every request from this sink."""
        super().__init__(target, stream_name, schema, key_properties)
        authenticator_class, auth_endpoint = target.access_token_support(target)
        self.authenticator = authenticator_class(target, self.auth_state, auth_endpoint)

    @property
    def customer_id(self) -> str:
        """Google Ads customer ID without dashes."""
        return str(self.config["customer_id"]).replace("-", "")

    @property
    def login_account_id(self) -> str | None:
        """Manager account customer ID without dashes, when configured."""
        login_account_id = self.config.get("login_account_id")
        if not login_account_id:
            return None
        return str(login_account_id).replace("-", "")


class GoogleAdsRecordSink(GoogleAdsSink, HotglueSink):
    """GoogleAds Record target sink class for record sinks."""

    name = "GoogleAdsRecordSink"

    def preprocess_record(self, record: dict, context: dict) -> dict:
        return record

    def upsert_record(self, record: dict, context: dict) -> tuple:
        response = self.request_api("POST", request_data=record)
        body = response.json() if response.content else {}
        record_id = body.get("id")
        return record_id, response.ok, {}


class GoogleAdsBatchSink(GoogleAdsSink, HotglueBatchSink):
    """GoogleAds Batch target sink class for batch sinks."""

    name = "GoogleAdsBatchSink"

    def process_batch_record(self, record: dict, _index: int) -> dict:
        return record

    @abstractmethod
    def make_batch_request(self, records: list[dict]) -> Any:
        method = "POST"
        endpoint = self.endpoint
        response = self.request_api(method, endpoint, request_data=records)
        return response

    def handle_batch_response(self, _response: Any) -> dict:
        """Parse batch API response into per-record state updates.

        Returns:
            Dict with ``state_updates`` — one entry per input record.
        """
        return {"state_updates": []}
