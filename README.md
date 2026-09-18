# Deployer Reputation -- MCP server

Scores a Solana deployer cluster for serial-rugger risk from that deployer's launches
and the funding wallet behind each one.

Rotating a fresh deployer wallet per launch defeats per-token and per-deployer
reputation by design. The funding wallet is stickier, so collapsing shared-funder
groups re-attaches the rotated deployers to one operator -- which is what makes a
reputation possible at all.

## Install

Nothing to install. The server uses only the Python standard library, and the `ff`
package it wraps ships in this repository.

## Run it (stdio)

```bash
python deployer_reputation_mcp.py
```

## Add it to an MCP client

```json
{
  "mcpServers": {
    "deployer-reputation": {
      "command": "python",
      "args": ["/absolute/path/to/deployer_reputation_mcp.py"]
    }
  }
}
```

## Tools

### `deployer_reputation`

Input `edges[]` -- one entry per launch:

| field | meaning |
|---|---|
| `deployer` | the wallet that created the token |
| `funder` | the wallet that paid the create fee |
| `mint` | token mint address (optional) |
| `block_time` | unix seconds of the create (optional) |
| `lamports` | lamports transferred to the deployer (optional) |
| `outcome` | `rugged` / `alive` / `graduated` / `unknown` (optional) |
| `funder_is_cex` | true when the funder is an exchange hot wallet -- not an attribution (optional) |

Returns clusters ranked by risk: `{cluster_id, score, band, deployers, funders, mints,
components{serial,cadence,fanout,cex,rugs}, evidence, n_launches}`.

The score alone is not the product. The components and the raw counts behind them are
returned so a caller can audit the number instead of trusting it.

### `cluster_launches`

Same input, grouping only -- no score. Use it to de-duplicate a wallet graph so one
operator's wallets do not count as independent participants.

## Honest limits

* This is a **risk filter, not standalone alpha.** Use it to *exclude* a high-rug cohort
  from a long sleeve. It does not select winners by itself.
* On reachable data the shared-funder mechanism contributed ~nothing (13 of 120 funders
  traceable, 2 shared). The dominant live signal is the deployer's own prior record.
* Unconditional AUC on the true firehose population is **0.492 -- no edge.** The 0.667
  figure is *conditional* on the deployer having any track record.
* The elite tail is real but tiny: ~0.7-2 qualifying launches/day across all of pump.fun.
* The server scores edges you supply. It does not fetch from Solana and does not label
  outcomes.

## Provenance of the published study numbers

The separation statistics (conditional OOS AUC 0.667, elite-tail 27x lift, FADE
p=0.0052) come from a survivorship-clean, no-lookahead, permutation-tested study in
`solana-edge-hunt/edge2_deployer/`. They are properties of that study, **not** output of
a tool call, and the server does not return them as if they were.

## Tests

```bash
python deployer_reputation_mcp.py --selftest
```
