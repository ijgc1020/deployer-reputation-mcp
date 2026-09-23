# Deployer Reputation: supplied-edge heuristic

Group launch records by funding associations and inspect explainable heuristic scores.
**Bring your own deployer, funder, and mint edges. This product does not fetch Solana RPC data,
look up wallets, discover funding transactions, or verify caller labels.**

Use it after your data pipeline has resolved launch and funding provenance. A token-address list,
price feed, or generic token-scanner dataset is not enough. Shared funding is an association,
not verified common ownership. Scores are not fraud findings, predictions, probabilities, or
investment recommendations. **Low does not mean safe.**

- [Run on Apify](https://apify.com/ultrathink-labs/deployer-reputation-heuristic): $0.005 per delivered analysis batch, up to 1,000 edges.
- [Source and reusable examples](https://github.com/ijgc1020/deployer-reputation-mcp): local scoring and MCP stdio use Python's standard library, without an Apify account or charge.

## First result in five minutes

### Option A: Apify, no local installation

1. Open the Actor and switch its input to JSON.
2. Replace the complete input with this **fictional example**. These identifiers are not real wallets or mints.

```json
{
  "operation": "score",
  "edges": [
    {"deployer": "DemoDeployerA", "funder": "DemoSharedFunder", "mint": "DemoMintA", "outcome": "unknown"},
    {"deployer": "DemoDeployerB", "funder": "DemoSharedFunder", "mint": "DemoMintB", "outcome": "unknown"},
    {"deployer": "DemoDeployerC", "funder": "DemoOtherFunder", "mint": "DemoMintC", "outcome": "unknown"}
  ]
}
```

3. Check current Store pricing before starting. This example produces one $0.005 analysis result, not three charges.
4. Set the run's maximum total charge to $0.01 (`maxTotalChargeUsd` for API callers), then start it.
5. Open the run's **default dataset** and view or download its JSON. There is one result object containing nested `clusters`.

Expected from this fictional input: `n_edges: 3`, `n_clusters: 2`. A and B group through
`DemoSharedFunder`; C stays separate. Both clusters have `evidence.labelCoverage: 0`,
`observed_rug_rate: null`, and `rug_rate_wilson_lb: null`. Missing labels do not establish a zero rug rate.
A structural score can still be nonzero; it is not a safety verdict.

The same input is saved as `examples/apify_input/reputation_first_run.json` in the source repository.
The dataset, not a key-value `OUTPUT` record, is the result destination. A successful process exit
alone does not prove delivery or payment.

### Option B: offline, no account or network call

Install Python 3.13 and download or clone the source repository. Run this command from its root;
no `pip install` is needed for inline scoring or MCP stdio:

```sh
python -c "import json; from pathlib import Path; from actor import run_input; print(json.dumps(run_input(json.loads(Path('examples/apify_input/reputation_first_run.json').read_text(encoding='utf-8'))), indent=2))"
```

This calls the real shared Actor input/scoring function, without launching an Apify run.
All bundled demonstration identifiers and labels are fictional. They demonstrate software behavior,
not actual wallets, model accuracy, customer demand, or profitable trading.

## Your input: one observed launch per edge

An edge means **the supplied funder seeded the supplied deployer, which launched the supplied mint**.
You must resolve those relationships before calling this product. Keep transaction references,
source URLs, observation times, and label policy in your own evidence store, keyed by mint.
Extra provenance fields cannot be included in an edge: unknown fields are rejected.

| Field | Contract | Your responsibility |
| --- | --- | --- |
| `deployer` | Required nonempty string | Identify the launch deployer from evidence; a token holder or swap wallet is not a substitute. |
| `funder` | Required nonempty string | Resolve funding of that deployer before the launch. Do not substitute a pool address, mint, or common `unknown` placeholder. |
| `mint` | Required nonempty string; unique within the batch | Supply the launched token identifier, not its trading-pair address. |
| `outcome` | Optional: `unknown` (default), `rug`, `rugged`, `alive`, `graduated` | Supply only supported labels you can substantiate. `rugged` maps to `rug`. Missing evidence stays `unknown`. |
| `funder_is_cex` | Optional strict boolean; default `false` | Mark known exchange/infrastructure funders. The default is not verification that a wallet is non-exchange. |
| `lamports` | Optional integer, 0–18446744073709551615; default 0 | Funding amount in lamports, not SOL or a numeric string. Currently does not affect the score. |
| `block_time` | Optional Unix timestamp in seconds, 0–253402300799, or `null` | Do not pass an ISO date or milliseconds. Currently does not affect the score. |

Identifiers are opaque strings of at most 128 characters, without whitespace, control characters,
or Unicode surrogates. They are not validated as Solana addresses. Preserve exact identifier spelling.
If a required deployer or funder is missing, keep that launch in your enrichment queue; do not invent an edge.

Batches require **1–1,000 edges with distinct mints**. Missing, duplicate, or conflicting mints
reject the whole batch. Multiple funding observations for one mint must be resolved upstream into
one supported edge under your documented selection rule; this is not a general transaction-graph importer.

HTTP and local MCP tool arguments contain only `{"edges": [...]}`. Apify input also accepts
`operation` (`score` by default, or `cluster`), `datasetId`, and `payload`.
Inline Actor input, HTTP bodies, and individual stdio lines are limited to 512000 bytes;
the edge-count limit applies independently to inline and dataset inputs.

## Read the result before using the score

`score` returns `clusters`, `n_clusters`, `n_edges`, `model`, `scorerVersion`,
`clusterIdVersion`, and `caveat`. Clusters are ordered by descending heuristic score.

| Cluster field | Interpretation |
| --- | --- |
| `cluster_id` | `CL2-` plus SHA-256 of supplied deployer/funder membership. An association key, not a persistent operator identity. |
| `deployers`, `funders`, `mints`, `n_launches` | Membership and launch counts within this batch only. |
| `score`, `band` | Uncalibrated 0–1 heuristic and policy band: `low`, `elevated`, or `high`. A score of 0.6 does not mean 60% fraud probability. |
| `components` | `serial`, `cadence`, `fanout`, `cex`, and `rugs`: the component values behind the score. |
| `evidence.labeled_launches`, `rug_launches`, `labelCoverage` | Caller-supplied label counts and labeled/total launch fraction. Check these before interpreting the band. |
| `evidence.observed_rug_rate`, `rug_rate_wilson_lb` | Statistics over supplied labeled launches only; both are `null` with no labels. Not population-level fraud estimates. |
| `evidence.notes`, `rug_evidence` | Missing/incomplete outcome warnings and the low-is-not-safe caveat. |

Structural components can raise scores without outcome labels. `cadence` measures launch count,
not elapsed time. `high` requires a score of at least 0.50 **and** a positive supplied rug label;
otherwise a score of at least 0.28 is `elevated`. These thresholds are policy, not calibrated risk levels.
The inherited CEX component is a heuristic, not evidence of misconduct.

A funder flagged `funder_is_cex: true` anywhere in the batch never joins distinct deployers through
that funder. The same deployer's launches can still group together. Funding associations can be transitive.
No chain lookup verifies any of this. Separate research AUC, lift, or p-values do not validate this scorer.
No performance, predictive-accuracy, or profitability claim is made.

`cluster` returns only membership groups, counts, and `clusterIdVersion`; it does not return scores,
bands, or label evidence. Both operations deliver one dataset object per Actor run.

## Repeat use: refresh evidence, not just the score

Each call is **stateless**. The Actor does not remember prior launches, append historical evidence,
refresh outcomes, or watch wallets. Re-running identical input does not collect new information.

For a scheduled review workflow:

1. Collect new launch/funding evidence in your own pipeline. Resolve exchange flags and outcome labels there.
2. Rebuild your chosen analysis snapshot, including relevant older launches. Replace old rows when labels change; never append duplicate mints.
3. Project only the documented fields. Record the snapshot time, source coverage, and label policy outside the Actor input.
4. Keep related deployers and non-exchange funding groups together when dividing work into batches of at most 1,000 edges.
5. Run one batch per input or dataset. Save the result, input snapshot, scorer version, and Apify run/dataset IDs together.
6. Compare membership, evidence coverage, and components before treating a score change as meaningful.

Arbitrary chunks can split a funding group and change scores. Separate batches are never joined later
by this product. If a connected analysis set exceeds 1,000 edges, this interface cannot analyze that
whole set in one call; document the coverage reduction rather than claiming a full-graph result.

### Runnable fictional refresh

`examples/apify_input/reputation_repeat.json` retains the first-run snapshot, adds `DemoMintD`
from existing `DemoDeployerA`, and changes `DemoMintA` to a fictional `rugged` label. No real event is claimed.

```sh
python -c "import json; from pathlib import Path; from actor import run_input; print(json.dumps(run_input(json.loads(Path('examples/apify_input/reputation_repeat.json').read_text(encoding='utf-8'))), indent=2))"
```

Expected: four edges and two clusters. The shared-funder cluster now contains three launches,
one supplied rug label, and `labelCoverage: 0.3333`. Both cluster IDs stay unchanged because their
deployer/funder membership is unchanged. Adding/removing a deployer or funder can change IDs;
changing only mints or outcomes does not. Use mint membership to reconcile changed groups across snapshots.

For Apify, paste this repeat file as the next run's complete JSON input. Each delivered refresh is
another analysis result, including when it repeats earlier input. Existing `reputation_score.json`
and `reputation_cluster.json` provide fictional labeled and exchange-separation examples.

## Dataset handoff: transport support is not schema compatibility

The Actor can read **already-enriched edge rows** from an Apify dataset. Each dataset item must be
one edge object, not an `edges` wrapper or a previous score result. The dataset must contain 1–1,000
rows; fetching pages does not split it into multiple analysis batches.

For a manual handoff, replace `YOUR_DATASET_ID` below with the real dataset ID, not its URL:

```json
{"datasetId": "YOUR_DATASET_ID", "operation": "score"}
```

**Remove `edges` entirely, including the form's fictional prefill.** Non-null inline `edges` take
precedence over every dataset reference; even an empty list fails instead of falling back.
Explicit `datasetId` takes precedence over `payload.resource.defaultDatasetId`.

For an [Actor-to-Actor integration](https://docs.apify.com/integrations/actors), select **run succeeded**
as the trigger on your enrichment Actor. Set this static input with no `edges` or `datasetId`:

```json
{"operation": "score"}
```

Apify adds `payload.resource.defaultDatasetId` for the triggering run. Alternatively, the integration
form can interpolate an explicit reference:

```json
{"datasetId": "{{resource.defaultDatasetId}}", "operation": "score"}
```

That expression works in the integration form, not as a literal dataset ID in a manual/API call.
The reader accepts alphanumeric Apify IDs of 10–32 characters, never arbitrary caller URLs or credentials.
It tries dataset access without a token first, then the Actor's run token on an authorization failure.
`LIMITED_PERMISSIONS` does not guarantee access to another dataset. If access is denied, either grant
appropriate storage access or share that specific dataset by link only when disclosure is acceptable.
Do not make sensitive data public just to clear an error.

A saved task with a fixed dataset ID keeps reading that same dataset. Use the integration's dynamic
run dataset or update the task input before scheduling a new snapshot. This Actor performs no enrichment.

### Published upstream schema audit

Schema descriptions inspected on 2026-09-22; **no live upstream runs or end-to-end compatibility certification**:

| Upstream product | Published fields | Missing work before this Actor |
| --- | --- | --- |
| [Pump.fun New Token Listings Scraper](https://apify.com/automation-lab/pumpfun-new-token-listings-scraper.md) | `mint`, `creator`, ISO `launchTimestamp`, market/listing fields | No `funder`. Verify what `creator` means, resolve the deployer and its pre-launch funding, then project the supported fields. Do not assume `creator` is an evidenced deployer. |
| [DexScreener Scraper](https://apify.com/muhammetakkurtt/dexscreener-scraper.md) | `baseToken.address`, `pairAddress`, prices, volume, liquidity, `pairCreatedAt` | No deployer/funder edge. Resolve both from independent evidence; distinguish mint from pair. Price/volume fields and pair timestamps are not funding provenance. |

Neither published schema supports direct dataset pass-through. A field rename cannot manufacture
missing funding evidence. Unknown extra fields also cause rejection. A compatible handoff requires an
upstream enrichment/projection step and a check of actual output rows; no built-in scanner adapter is provided.

## Cost per batch and per repeat

The Store listed **$5.00 per 1,000 analysis results** on 2026-09-22: **$0.005 per delivered batch**,
not per edge and not per nested cluster. Platform pricing is configured outside this source;
check the Store before each workflow launch. Apify's current pricing and credit terms govern actual charges.

| Edges in one batch | Analysis-result price | Effective price per edge |
| --- | --- | --- |
| 1 | $0.005 | $0.005 |
| 100 | $0.005 | $0.00005 |
| 1,000 | $0.005 | $0.000005 |

One delivered batch per day for 30 days is **$0.15** at that rate. Thirty separate runs with the same
input still produce thirty billable results. Both `score` and `cluster` use the same one-result delivery.
Upstream scraping, RPC, enrichment, and your own hosting costs are not included in this comparison.

The Actor publishes only through the default dataset, using the platform's synthetic
`apify-default-dataset-item` event. It adds no custom duplicate charge. Rejected input produces no
analysis-result item. Inspect both dataset delivery and platform charge records; neither owner test
runs nor the displayed unit price establish seller revenue. Apify stores submitted input/output;
account/platform access and retention rules apply.

## MCP quickstart: local stdio, no hosted service required

The local server uses Python's standard library. No HTTP/Actor dependencies, API key, RPC endpoint,
or Apify account is needed. Start it from the repository root:

```sh
python deployer_reputation_mcp.py
```

It waits for JSON-RPC input; there is no banner or HTTP listener. Your MCP client normally starts this
process. Copy `mcp-client-config.json` into your client's MCP configuration and replace `{{INSTALL_DIR}}`
with the absolute repository path. For example, a checkout in `C:/tools/deployer-reputation-mcp` uses:

```json
{
  "mcpServers": {
    "deployer-reputation": {
      "command": "python",
      "args": ["C:/tools/deployer-reputation-mcp/deployer_reputation_mcp.py"]
    }
  }
}
```

Use your real path, and the full Python executable path if the client cannot find `python`.
The script resolves its bundled scorer relative to itself, not the client's working directory.

Tools: `deployer_reputation` and `cluster_launches`. Both accept only `{"edges": [...]}`;
Actor-only `operation`, `datasetId`, and `payload` are not local MCP arguments.
The server advertises protocol `2024-11-05`, with one newline-delimited JSON-RPC object per line
and a 512000-byte line limit. It does not implement JSON-RPC batch arrays or HTTP/SSE transport.

### Executable handshake and calls

`examples/mcp_quickstart.jsonl` includes initialization, the initialized notification, tool discovery,
a score call, a grouping call, a deliberately incomplete edge, and a final ping. All data is fictional.

PowerShell, from the repository root:

```powershell
Get-Content examples/mcp_quickstart.jsonl | python deployer_reputation_mcp.py
```

POSIX shell:

```sh
python deployer_reputation_mcp.py < examples/mcp_quickstart.jsonl
```

Expected replies:

| Request ID | Result |
| --- | --- |
| 1 | Initialization reports server `deployer-reputation`, version `2.0.0`, protocol `2024-11-05`. |
| 2 | `tools/list` exposes the two named tools and their input schemas. |
| 3 | Successful score call: three edges, two clusters, no outcome labels. |
| 4 | Successful grouping call: two clusters, no scores. |
| 5 | Intentional negative control: mint-only input returns `result.isError: true`, not a fabricated deployer/funder or score. |
| 6 | Ping returns an empty result object, demonstrating recovery after rejected input. |

Notifications produce no reply. Successful tool calls use `result.isError: false` and put the JSON
payload **inside the string** `result.content[0].text`; parse that string as JSON to access `clusters`.
For request 5, that text is an error message, not a JSON result. Malformed requests do not stop the stream.

Apify's [hosted MCP configuration](https://apify.com/ultrathink-labs/deployer-reputation-heuristic.md)
is a separate route to the cloud Actor, with OAuth sign-in and normal Actor pricing. Local stdio
calls do not execute or bill an Apify Actor. Discovering hosted tools is not proof of an Actor run.

## Optional self-hosted HTTP

```sh
python -m pip install -r requirements.txt
# Set REPUTATION_API_KEY securely to a value of at least 32 characters.
uvicorn api:app --host 127.0.0.1 --port 8080 --workers 1 --limit-concurrency 16 --timeout-keep-alive 5
```

`GET /health` is public. `POST /score` and `/cluster` require `X-API-Key` and accept only an `edges`
object. Missing/trivial server keys prevent startup. Invalid auth/JSON/input/body size return
401/400/422/413 respectively. Use TLS, timeouts, and rate limits at a reverse proxy before public exposure.
Bind Docker to loopback behind that proxy, for example `-p 127.0.0.1:8080:8080`.
The Docker image runs as an unprivileged user with one worker and 16 concurrent connections.

The app does not store submitted edges or log request bodies; infrastructure operators can still
observe requests. No self-hosted billing, customer account system, or API-key issuance is implemented.
Deployment status is external to this package. Never submit credentials in edge data.

## Offline verification for maintainers

```sh
python -m pip install -r requirements.txt httpx
python -m unittest discover -q
python scripts/demo_reputation.py
python scripts/verify_all.py
```

The demo covers fictional labeled launches, independent deployers, and shared-exchange separation.
Regression tests cover input limits, duplicate mints, exchange separation, stdio recovery,
authentication/body limits, dataset handoff, and dataset-only Actor delivery.
These checks establish software behavior, not predictive validity or paid demand.

## Scorer 2.0.0 ID migration

IDs use `CL2-` plus full SHA-256 of the canonical JSON array of sorted unique role-prefixed
deployer/funder identifiers (`ensure_ascii=True`, compact separators). This replaces ambiguous
serialization and 32-bit `CL-` IDs. Recompute IDs from original membership; old IDs cannot be converted reliably.
Score results include `scorerVersion`; both operations include `clusterIdVersion`.
Numeric weights remain unchanged from the prior scorer. Batch-wide CEX classification applies to
clustering, evidence, and components, so conflicting exchange flags can change scores.
