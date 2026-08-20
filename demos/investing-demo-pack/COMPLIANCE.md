# Compliance Notes

This demo pack is a fictional, redacted fixture for product demonstration.

## Not investment advice

Furnace is demonstrated here as a research-material organization, provenance, judgment, and review workflow. This pack does not provide:

- buy, sell, hold, allocation, sizing, timing, or portfolio advice;
- return forecasts or performance promises;
- market data, backtests, signal services, or automated trading;
- due diligence on any real issuer.

All entities are fictional. "示例半导体 A", "示例设备商 B", and "示例云厂商 C" are invented names.

## LLM data flow

When a user configures an LLM provider, the provider may receive prompts and task context assembled from selected vault content. API keys are expected to live in the user's local configuration, but the task content sent to the configured provider depends on the operation being run.

This fixture marks receipts as `demo_fixture: true` and contains no real secrets. Do not use unredacted confidential material in a public demo.

## Local-first is not offline-only

The vault, wiki pages, outputs, and receipts are local files. However, LLM providers, web fetching, notification webhooks, package registries, and other configured integrations may access the network.

Offline use is limited to local file reading/writing and deterministic checks that do not require external models or network services.

## No fake 14/30-day proof

This pack does not claim any 14-day or 30-day natural proof has passed. Cross-cycle review is represented as a fixture narrative with explicit demo dates and synthetic evidence. A real long-window PASS can only come from actual wall-clock operation and review receipts.

## Redaction rules used

- Company, product, customer, channel, and person names are fictional.
- Dates are demo dates, not real event timestamps.
- Metrics are rounded qualitative bands or synthetic index values.
- No private client data, holdings, trades, API keys, or unpublished real company information is included.
