"""Deployer Reputation -- an MCP server over stdio, listing-ready.

Wraps the TESTED asset: fleet-build/funder-fingerprint/ff/cluster.py (52/52 tests).
The server adds no modelling of its own -- it exposes what the tested module computes,
so the listing's claims and the code cannot drift apart.

Transport: MCP stdio -- newline-delimited JSON-RPC 2.0 on stdin/stdout.
Methods:   initialize, notifications/initialized, tools/list, tools/call, ping.
Zero third-party dependencies: json + sys + the local ff package.

What the numbers in the listing mean, stated exactly:
  - 52/52 tests        tests/ in fleet-build/funder-fingerprint (pytest, no network)
  - sub-50ms           the ff.cluster scoring path is pure list/dict arithmetic on
                       already-fetched edges. The RPC FETCH is not sub-50ms; the
                       on-chain acquisition is the slow part and is NOT in this server.
  - OOS AUC 0.667      conditional-on-repeat-deployer separation, survivorship-clean,
                       firehose N=1,338,180 -- from solana-edge-hunt/edge2_deployer
  - elite-tail lift 27x  walk-forward OOS 17.5% graduation vs 0.642% base, N=57,
                       Wilson-LB 9.8%
  - p=0.005 (0.0052)   the FADE arm's flagged-vs-clean death separation
This server returns cluster/score output. It does NOT return those study statistics;
they are published performance claims, and mixing them into a per-call response would
be the exact dishonesty this estate's rules forbid.

Run:  python deployer_reputation_mcp.py          (stdio; an MCP client drives it)
Test: python deployer_reputation_mcp.py --selftest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FF_ROOT = Path(__file__).resolve().parent   # ff/ ships in this repo
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "deployer-reputation"
SERVER_VERSION = "1.0.0"

TOOLS = [
    {
        "name": "deployer_reputation",
        "description": (
            "Score a Solana deployer cluster for serial-rugger risk. Input is the "
            "deployer's launches with the funding wallet of each: shared-funder "
            "clustering collapses rotated throwaway deployers onto one operator, then "
            "the cluster is scored 0..1 (higher = more serial-rugger-like) with "
            "explainable components and a low/elevated/high band. Returns the cluster, "
            "the score, why it scored that way, and the raw counts behind each component."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "edges": {
                    "type": "array",
                    "description": "One entry per launch. deployer = the wallet that created the token; funder = the wallet that paid the create fee.",
                    "items": {
                        "type": "object",
                        "required": ["deployer", "funder"],
                        "properties": {
                            "deployer": {"type": "string", "description": "Solana base58 deployer address"},
                            "funder": {"type": "string", "description": "Solana base58 wallet that funded the deployer's create"},
                            "mint": {"type": "string", "description": "Token mint address"},
                            "block_time": {"type": "integer", "description": "Unix seconds of the create"},
                            "lamports": {"type": "integer", "description": "SOL lamports transferred to the deployer"},
                            "outcome": {"type": "string", "enum": ["rugged", "alive", "graduated", "unknown"], "description": "Known outcome for this launch, if any"},
                            "funder_is_cex": {"type": "boolean", "description": "True when the funder is a known exchange hot wallet -- these are NOT operator attributions"},
                        },
                    },
                },
            },
            "required": ["edges"],
        },
    },
    {
        "name": "cluster_launches",
        "description": (
            "Group launches into operator clusters by shared funding wallet, without "
            "scoring. Use this when you want the grouping only -- for example to "
            "de-duplicate a copier/buyer graph so one operator's wallets do not count "
            "as independent participants."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"edges": {"type": "array", "items": {"type": "object"}}},
            "required": ["edges"],
        },
    },
]


# ------------------------------------------------------------------------ core
def _ff():
    """Import the tested module. It must come from the fleet-build tree, not a copy."""
    if str(FF_ROOT) not in sys.path:
        sys.path.insert(0, str(FF_ROOT))
    from ff import cluster  # noqa: E402
    return cluster


def _edges(raw: list) -> list:
    ff = _ff()
    return [
        ff.DeployEdge(
            deployer=str(e["deployer"]),
            funder=str(e["funder"]),
            mint=str(e.get("mint", "")),
            block_time=e.get("block_time"),
            lamports=int(e.get("lamports", 0)),
            outcome=str(e.get("outcome", "unknown")),
            funder_is_cex=bool(e.get("funder_is_cex", False)),
        )
        for e in raw
    ]


def tool_deployer_reputation(args: dict) -> dict:
    import dataclasses

    ff = _ff()
    clusters = ff.cluster_by_funder(_edges(args.get("edges", [])))
    out = []
    for c in clusters:
        s = ff.score_cluster(c)
        # The score alone is not the product; the components are. A caller acting on a
        # bare number cannot audit it, and an unauditable risk score is a liability.
        out.append({
            "cluster_id": s.cluster_id,
            "score": round(s.score, 4),
            "band": s.band,
            "deployers": c.deployers,
            "funders": c.funders,
            "mints": c.mints,
            "components": {k: round(v, 4) if isinstance(v, float) else v for k, v in (s.components or {}).items()},
            "evidence": s.evidence,
            "n_launches": len(c.edges),
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return {
        "clusters": out,
        "n_clusters": len(out),
        "n_edges": len(args.get("edges", [])),
        "model": "ff.cluster serial-deployer reputation (Wilson-LB blended, weights sum to 1.0)",
        "caveat": (
            "Structural components fire without outcome labels, so a fresh cluster still "
            "gets a risk read from shape alone. On reachable data the shared-funder "
            "mechanism contributed ~nothing (13/120 funders traceable to 2 shared) -- the "
            "dominant live signal is the deployer's own prior record. Treat this as a "
            "risk filter to EXCLUDE from a long sleeve, not as standalone alpha."
        ),
    }


def tool_cluster_launches(args: dict) -> dict:
    ff = _ff()
    clusters = ff.cluster_by_funder(_edges(args.get("edges", [])))
    return {
        "clusters": [
            {"cluster_id": c.cluster_id, "deployers": c.deployers, "funders": c.funders,
             "mints": c.mints, "n_launches": len(c.edges)}
            for c in clusters
        ],
        "n_clusters": len(clusters),
    }


HANDLERS = {"deployer_reputation": tool_deployer_reputation, "cluster_launches": tool_cluster_launches}


# -------------------------------------------------------------------- transport
def _reply(msg_id, result=None, error=None) -> None:
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    sys.stdout.write(json.dumps(body) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        _reply(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method in ("notifications/initialized", "initialized"):
        return                                   # notification: no reply, ever
    elif method == "tools/list":
        _reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            _reply(mid, error={"code": -32602, "message": f"unknown tool: {name}"})
            return
        try:
            payload = fn(params.get("arguments") or {})
            _reply(mid, {"content": [{"type": "text", "text": json.dumps(payload, indent=1)}], "isError": False})
        except Exception as exc:                  # a tool error is a result, not a transport error
            _reply(mid, {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True})
    elif method == "ping":
        _reply(mid, {})
    elif mid is not None:
        _reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            continue
    return 0


# --------------------------------------------------------------------- selftest
SAMPLE = [
    {"deployer": f"Dep{i}", "funder": "FunderA", "mint": f"Mint{i}", "outcome": "rugged", "lamports": 2_000_000_000}
    for i in range(6)
] + [
    {"deployer": "Clean1", "funder": "FunderB", "mint": "MintC1", "outcome": "alive", "lamports": 1_000_000_000},
    {"deployer": "Clean2", "funder": "FunderC", "mint": "MintC2", "outcome": "graduated", "lamports": 1_000_000_000},
]


def selftest() -> int:
    import time

    print(f"server      {SERVER_NAME} {SERVER_VERSION}")
    print(f"ff module   {FF_ROOT}/ff/cluster.py  (exists={FF_ROOT.joinpath('ff/cluster.py').exists()})")
    print(f"tools       {[t['name'] for t in TOOLS]}")

    t0 = time.perf_counter()
    result = tool_deployer_reputation({"edges": SAMPLE})
    ms = (time.perf_counter() - t0) * 1000
    top = result["clusters"][0]
    print(f"\nscore path  {ms:.1f} ms for {len(SAMPLE)} edges, {result['n_clusters']} clusters")
    print(f"top cluster {top['cluster_id']}  score={top['score']}  band={top['band']}  "
          f"deployers={len(top['deployers'])}  components={top['components']}")
    assert result["n_clusters"] == 3, result["n_clusters"]
    assert top["score"] > result["clusters"][-1]["score"], "serial cluster must outscore clean ones"
    print("\nSELFTEST PASS -- clustering separates the 6-launch serial cluster from the clean pairs.")
    print("NOT claimed here: the OOS AUC / 27x-lift / p=0.005 study numbers. Those are published")
    print("performance claims about a firehose sample; this process returns per-call cluster scores.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(serve())
