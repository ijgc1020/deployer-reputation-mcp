# Deployer Reputation: supplied-edge heuristic

Scores and groups **caller-supplied launch records**. No Solana RPC fetch, wallet lookup,
verified ownership attribution, fraud finding, calibrated probability, or investment recommendation.
Shared non-exchange funding creates an association, not proof of a common operator.
Known exchange funders never join distinct deployers, even when only one record flags that funder.
The same deployer's launches can still group together. Caller labels are trusted as input, not verified.

## Input and result

All transports use the same validation and scorer. Submit an object containing `edges`:

```json
{"edges":[{"deployer":"wallet-A","funder":"wallet-B","mint":"unique-mint-A","outcome":"rugged","funder_is_cex":false}]}
```

Identifiers are required nonempty opaque strings, max 128 characters, without whitespace/control
characters or Unicode surrogates. They are not checked as Solana addresses. Supply **one record per distinct mint**;
missing, duplicate and conflicting mints are rejected. Batches contain 1–1000 edges.
Unknown fields are rejected. Optional fields:

- `outcome`: `rugged` (mapped to `rug`), `rug`, `alive`, `graduated`, `unknown` (default).
- `funder_is_cex`: strict boolean, default false. Mark exchange/infra funders accurately.
- `lamports`: nonnegative integer up to 18446744073709551615; default 0.
- `block_time`: nonnegative Unix integer up to 253402300799, or null.

Scoring returns clusters, heuristic scores 0–1, bands, components, and raw launch/label counts.
Grouping returns associated deployers/funders/mints and launch counts. Structural components may
raise scores without outcome labels. The inherited CEX component is a heuristic, not evidence
of misconduct. Research AUC, lift and p-values from separate studies **do not validate this scorer**.
No performance or profitability claim is made. Launch timestamps currently do not affect scoring;
the component called cadence measures launch count, not elapsed time.

## MCP stdio

Python standard library only; HTTP/Actor dependencies are unnecessary for stdio:

```sh
python deployer_reputation_mcp.py
python deployer_reputation_mcp.py --selftest
```

Tools: `deployer_reputation` and `cluster_launches`. Newline-delimited JSON-RPC objects;
512000-byte maximum line. No JSON-RPC batches. Malformed messages return errors and the process
continues. Notifications have no response. Advertised protocol: 2024-11-05.
`mcp-client-config.json` contains the client registration example; replace its absolute path.

## HTTP deployment

```sh
pip install -r requirements.txt
# Set REPUTATION_API_KEY to a securely generated value of at least 32 characters.
uvicorn api:app --host 127.0.0.1 --port 8080 --workers 1 --limit-concurrency 16 --timeout-keep-alive 5
```

`GET /health` is public. `POST /score` and `/cluster` require `X-API-Key`.
Missing/trivial server key prevents startup. Actual streamed body size is limited to 512000 bytes;
edge count is independently limited. Invalid auth/JSON/input/body size return 401/400/422/413.
Use TLS at a reverse proxy before public exposure; retain request-header/body timeouts and a rate limit
there. Bind Docker's port to loopback behind that proxy, e.g. `-p 127.0.0.1:8080:8080`.
Dockerfile runs as an unprivileged user, one worker, 16 concurrent connections.
The app does not store submitted edges or log request bodies. Infrastructure operators can still
observe requests; avoid secrets in edge metadata. No billing, customer account system, API-key
issuance, or monetization is implemented. Deployment status is external to this package.

## Apify Actor packaging

`.actor/actor.json`, `Dockerfile.actor`, and `actor.py` package the same scorer.
Input adds optional `operation`: `score` (default) or `cluster`.
The default dataset is the sole result destination: one object per delivered batch, regardless
of its cluster count. No result is copied into a key-value record. Read the dataset to determine
whether a result was delivered; a successful process exit alone does not prove delivery or payment.
Invalid batches fail the run before any result is persisted. No chain requests are made.
Apify stores submitted input/output: account/platform access and retention rules apply.
Platform pricing is configured separately from this source. The saved private Actor configuration
on 2026-09-21 charges $0.005 per analysis result through the synthetic
`apify-default-dataset-item` event, with no start or custom event. Its minimum run charge cap is
$0.00501. Confirm current pricing in Apify before running; use an explicit `maxTotalChargeUsd`
cap (for example 0.01). Do not add a custom charge for the same result.
This local dataset-only change requires a new build and billing validation before publication.
Prior owner functional tests do not establish customer payment, settled revenue, or billing
behavior for this change. The output schema links only the dataset, with an overview view.

## Validation

```sh
pip install httpx
python -m unittest discover -v
```

Regression tests cover rug mapping, mint accounting, exchange separation, type/range limits,
stdio recovery, notification silence, API authentication/body limits, and Actor scorer parity.
These tests establish software behavior, not predictive validity.
