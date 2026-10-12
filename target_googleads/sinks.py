"""GoogleAds target sink class, which handles writing streams."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from hotglue_singer_sdk.exceptions import FatalAPIError, RetriableAPIError

from target_googleads.client import GoogleAdsBatchSink, GoogleAdsRecordSink

_SECONDS_PER_DAY = 86400
DEFAULT_MEMBERSHIP_DURATION = "2592000s"  # 30 days
_INVALID_MEMBERSHIP_DURATION = (
    "membershipDuration must be a whole number of days as {days * 86400}s"
)
DEFAULT_INGESTED_USER_LIST_INFO = {
    "contactIdInfo": {
        "dataSourceType": "DATA_SOURCE_TYPE_FIRST_PARTY",
    },
    "uploadKeyTypes": ["CONTACT_ID"],
}
_HEX_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})
_INVALID_EMAIL = "Email address must be of the form user@domain"
_INVALID_PHONE = "Phone number contains no digits"
MAX_MEMBERS_PER_REQUEST = 10000


def _api_error_message(exc: FatalAPIError | RetriableAPIError) -> str:
    """Return the API body when the exception kept the response."""
    response = getattr(exc, "response", None)
    if response is not None and response.text:
        return response.text
    return str(exc)


def _membership_duration(value: str) -> str:
    """Return a membership duration that is a whole number of days.

    Google Data Manager requires ``{days * 86400}s``.
    """
    if not isinstance(value, str):
        raise ValueError(_INVALID_MEMBERSHIP_DURATION)
    seconds_text, suffix, remainder = value.partition("s")
    if suffix != "s" or remainder or not seconds_text.isdigit():
        raise ValueError(_INVALID_MEMBERSHIP_DURATION)
    if int(seconds_text) % _SECONDS_PER_DAY:
        raise ValueError(_INVALID_MEMBERSHIP_DURATION)
    return value


def _is_hashed(value: str) -> bool:
    return bool(_HEX_SHA256.match(value))


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_and_hash_email(email: str) -> str:
    """Normalize an email per Data Manager rules and return its SHA-256 hex digest.

    Whitespace is removed and the address is lowercased. For ``gmail.com`` and
    ``googlemail.com``, dots and ``+`` tags in the local part are removed.
    A value that is already a 64-character hex digest is returned unchanged.
    """
    if _is_hashed(email):
        return email.lower()

    normalized = re.sub(r"\s+", "", email).lower()
    local, separator, domain = normalized.partition("@")
    if not separator or not local or not domain or "@" in domain:
        raise ValueError(_INVALID_EMAIL)
    if domain in _GMAIL_DOMAINS:
        local = local.split("+", 1)[0].replace(".", "")
        if not local:
            raise ValueError(_INVALID_EMAIL)
    return _sha256_hex(f"{local}@{domain}")


def normalize_and_hash_phone(phone: str) -> str:
    """Normalize a phone number to E.164 and return its SHA-256 hex digest.

    Non-digits are removed and a leading ``+`` is added. The digits must already
    include the country code. A value that is already a 64-character hex digest
    is returned unchanged.
    """
    if _is_hashed(phone):
        return phone.lower()

    digits = re.sub(r"\D", "", phone)
    if not digits:
        raise ValueError(_INVALID_PHONE)
    return _sha256_hex(f"+{digits}")


class AudiencesSink(GoogleAdsRecordSink):
    """Create Customer Match audiences (UserLists) in Google Ads."""

    name = "Audiences"

    @property
    def endpoint(self) -> str:
        return f"/accountTypes/GOOGLE_ADS/accounts/{self.customer_id}/userLists"

    def preprocess_record(self, record: dict, context: dict) -> dict:
        display_name = record.get("displayName") or record.get("name")
        if not display_name:
            raise ValueError("Audiences records require displayName (or name)")

        membership_duration = record.get("membershipDuration", DEFAULT_MEMBERSHIP_DURATION)
        if membership_duration:
            membership_duration = _membership_duration(membership_duration)

        payload = {
            "displayName": display_name,
            "description": record.get("description"),
            "integrationCode": record.get("integrationCode"),
            "membershipDuration": membership_duration,
            "ingestedUserListInfo": record.get("ingestedUserListInfo")
            or DEFAULT_INGESTED_USER_LIST_INFO,
        }
        return self.clean_payload(payload)

    def upsert_record(self, record: dict, context: dict) -> tuple:
        headers = {}
        if self.login_account_id:
            headers["login-account"] = f"accountTypes/GOOGLE_ADS/accounts/{self.login_account_id}"
        response = self.request_api("POST", request_data=record, headers=headers)
        body = response.json() if response.content else {}
        # productDestinationId for later AudienceMembers ingest
        record_id = body.get("id")
        state_updates = {}
        if body.get("name"):
            state_updates["name"] = body["name"]
        return record_id, response.ok, state_updates


class AudienceMembersBatchSink(GoogleAdsBatchSink):
    """Send hashed contact identifiers to a Customer Match audience endpoint."""

    max_size = MAX_MEMBERS_PER_REQUEST

    def process_batch_record(self, record: dict, _index: int) -> dict:
        product_destination_id = (
            record.get("productDestinationId")
            or record.get("audienceId")
            or record.get("userListId")
            or self.config.get("product_destination_id")
        )
        if not product_destination_id:
            raise ValueError(
                f"{self.name} records require productDestinationId "
                "(or audienceId / userListId / config product_destination_id)"
            )

        external_id = record.get("externalId") or record.get("id")
        return {
            "_externalId": str(external_id) if external_id is not None else None,
            "_productDestinationId": str(product_destination_id),
            "member": self._build_audience_member(record),
        }

    def request_fields(self) -> dict:
        """Fields added to the shared destinations and audienceMembers body."""
        return {}

    def make_batch_request(self, records: list[dict]) -> list[dict[str, Any]]:
        """Send one request per productDestinationId group.

        A 4xx, or a 429/5xx after retries, is stored on that group and the
        remaining groups are still sent. Returns ``{"records", "response"}``
        or ``{"records", "error"}`` for ``handle_batch_response``.
        """
        groups: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            groups[record["_productDestinationId"]].append(record)

        results: list[dict[str, Any]] = []
        for product_destination_id, group in groups.items():
            destination = {
                "operatingAccount": {
                    "accountType": "GOOGLE_ADS",
                    "accountId": self.customer_id,
                },
                "productDestinationId": product_destination_id,
            }
            if self.login_account_id:
                destination["loginAccount"] = {
                    "accountType": "GOOGLE_ADS",
                    "accountId": self.login_account_id,
                }
            payload = {
                "destinations": [destination],
                "audienceMembers": [item["member"] for item in group],
                "encoding": "HEX",
                **self.request_fields(),
            }
            try:
                response = self.request_api("POST", self.endpoint, request_data=payload)
            except (FatalAPIError, RetriableAPIError) as exc:
                error = _api_error_message(exc)
                self.logger.exception(
                    "%s request failed for productDestinationId %s: %s",
                    self.name,
                    product_destination_id,
                    error,
                )
                results.append({"records": group, "error": error})
                continue
            results.append({"records": group, "response": response})
        return results

    def handle_batch_response(self, response: list[dict[str, Any]]) -> dict:
        state_updates = []
        for result in response:
            if "error" in result:
                for item in result["records"]:
                    state_updates.append(
                        {
                            "externalId": item.get("_externalId"),
                            "success": False,
                            "error": result["error"],
                        }
                    )
                continue

            api_response = result["response"]
            body = api_response.json() if api_response.content else {}
            request_id = body.get("requestId")
            warnings = body.get("fieldWarnings") or []
            warning_message = str(warnings) if warnings else None

            for item in result["records"]:
                state = {
                    "externalId": item.get("_externalId"),
                    "success": api_response.ok,
                    "id": request_id,
                }
                if warning_message:
                    state["warning"] = warning_message
                state_updates.append(state)
        return {"state_updates": state_updates}

    def _build_audience_member(self, record: dict) -> dict:
        if record.get("compositeData"):
            return {"compositeData": record["compositeData"]}
        if record.get("userData"):
            return {
                "compositeData": {
                    "userData": self._normalize_user_data(record["userData"]),
                }
            }
        if record.get("mobileData"):
            return {"mobileData": record["mobileData"]}
        if record.get("userIdData"):
            return {"userIdData": record["userIdData"]}

        user_identifiers = self._collect_user_identifiers(record)
        if not user_identifiers:
            raise ValueError(
                f"{self.name} records require email/emails, phoneNumber/"
                "phoneNumbers, userIdentifiers, userData, or compositeData"
            )
        return {"compositeData": {"userData": {"userIdentifiers": user_identifiers}}}

    def _normalize_user_data(self, user_data: dict) -> dict:
        identifiers = user_data.get("userIdentifiers") or []
        return {
            "userIdentifiers": [
                self._normalize_user_identifier(identifier) for identifier in identifiers
            ]
        }

    def _collect_user_identifiers(self, record: dict) -> list[dict]:
        identifiers: list[dict] = []

        for identifier in record.get("userIdentifiers") or []:
            identifiers.append(self._normalize_user_identifier(identifier))

        emails = record.get("emails") or []
        if record.get("email"):
            emails = [record["email"], *emails]
        for email in emails:
            if email:
                identifiers.append({"emailAddress": normalize_and_hash_email(str(email))})

        phones = record.get("phoneNumbers") or []
        phone = record.get("phoneNumber") or record.get("phone")
        if phone:
            phones = [phone, *phones]
        for phone_number in phones:
            if phone_number:
                identifiers.append({"phoneNumber": normalize_and_hash_phone(str(phone_number))})

        return identifiers

    def _normalize_user_identifier(self, identifier: dict) -> dict:
        normalized = dict(identifier)
        if normalized.get("emailAddress"):
            normalized["emailAddress"] = normalize_and_hash_email(str(normalized["emailAddress"]))
        if normalized.get("phoneNumber"):
            normalized["phoneNumber"] = normalize_and_hash_phone(str(normalized["phoneNumber"]))
        return normalized


class AudienceMembersSink(AudienceMembersBatchSink):
    """Ingest hashed contact identifiers into a Customer Match audience."""

    name = "AudienceMembers"
    endpoint = "/audienceMembers:ingest"

    def request_fields(self) -> dict:
        return {
            "consent": {
                "adUserData": "CONSENT_GRANTED",
                "adPersonalization": "CONSENT_GRANTED",
            },
            "termsOfService": {
                "customerMatchTermsOfServiceStatus": "ACCEPTED",
            },
        }


class RemoveAudienceMembersSink(AudienceMembersBatchSink):
    """Remove hashed contact identifiers from a Customer Match audience."""

    name = "RemoveAudienceMembers"
    endpoint = "/audienceMembers:remove"
