# target-googleads

`target-googleads` is a Singer target for **GoogleAds**, built with the [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK) (`TargetHotglue`, HTTP sinks, SDK authenticators).

This project was generated from the Hotglue target cookiecutter with:

| Option | Value |
|--------|--------|
| `auth_method` | `OAuth2` |
| `sinks` | `AudienceMembers | batch` |
| `base_url` | `https://datamanager.googleapis.com/v1` |

## Project layout

| Path | Role |
|------|------|
| `target_googleads/target.py` | `TargetGoogleAds` — config schema, `SINK_TYPES`, optional `default_sink_class` and `access_token_support` |
| `target_googleads/client.py` | `GoogleAdsSink` base class, `RecordSink` / `BatchSink` stubs, `authenticator` |
| `target_googleads/sinks.py` | Per-stream sink classes (`FallbackSink` or named `*Sink` classes) |
| `target_googleads/auth.py` | Present only when generated with **OAuth2** (removed by cookiecutter hook otherwise) |
| `.secrets/config.json` | Sample config matching your `auth_method` |

## Configuration

Settings are defined in `config_jsonschema` on `TargetGoogleAds` in `target_googleads/target.py`.
For this project (**OAuth2**), config includes: `client_id`, `client_secret`, `refresh_token`, and optional `access_token` / `expires_in`.

`customer_id` is the Google Ads account that owns the audience. `login_account_id` is optional. Set it to the manager (MCC) customer ID when the OAuth user belongs to a manager account that can access `customer_id`. Omit it for direct access to the client account. Dashes are ignored on both IDs.

When `login_account_id` is set:

- Audience creation sends the `login-account` header `accountTypes/GOOGLE_ADS/accounts/{login_account_id}`.
- Audience member ingest sets `destinations[].loginAccount` to that manager account. `operatingAccount` stays `customer_id`.

Inspect the live schema:

```bash
target-googleads --about
target-googleads --about --format=markdown
```

Local secrets: edit `.secrets/config.json` (shape matches `auth_method` above).

## Authentication

| `auth_method` | Implementation |
|---------------|----------------|
| **OAuth2** | `GoogleAdsAuthenticator` in `auth.py`; `TargetGoogleAds.access_token_support()` returns the authenticator class and token URL (replace the TODO endpoint in `target.py`). |
| **Bearer Token** | `BearerTokenAuthenticator` in `client.py` |
| **Basic Auth** | `BasicAuthenticator` with `username` / `password` |
| **API Key** | `ApiAuthenticator` with configurable header name/prefix |

HTTP calls use `base_url` on `GoogleAdsSink` (`https://datamanager.googleapis.com/v1` unless you change it in `client.py`).

## Sinks

Sinks are declared at scaffold time as `StreamName | record` or `StreamName | batch`, comma-separated.

Generated with: `AudienceMembers | batch`
**Named sinks:** `sinks.py` defines one class per stream; `target.py` registers them in `SINK_TYPES`. Implement `endpoint` (and request logic) per sink in `sinks.py` / overrides on `client.py` bases.

Shared HTTP behavior lives in `client.py` (`GoogleAdsRecordSink` / `GoogleAdsBatchSink` as generated).

## Usage

```bash
target-googleads --version
target-googleads --help
tap-smoke-test | target-googleads --config /path/to/config.json
```

## Developer setup

Prerequisites: Python 3.10+, [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
uv run target-googleads --help
tox -e lint    # ruff check + format
```

For implementation notes and conventions, see `AGENTS.md` (or `CLAUDE.md` if that was selected at generation).

## References

- [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK)
