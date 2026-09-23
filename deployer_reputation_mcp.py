"""Bounded supplied-edge heuristic exposed over MCP stdio."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FF_ROOT = Path(__file__).resolve().parent   # ff/ ships in this repo
PROTOCOL_VERSION = "2025-11-25"
LEGACY_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = (LEGACY_PROTOCOL_VERSION, "2025-06-18", PROTOCOL_VERSION)
SERVER_NAME = "deployer-reputation"
SERVER_VERSION = "2.1.0"

from validation import (input_schema, parse_edges, MAX_BODY_BYTES,
                        reputation_output_schema, cluster_output_schema)

TOOLS = [
    {
        "name": "deployer_reputation",
        "description": (
            "Score funding-association groups in supplied Solana launch records with explainable "
            "0-1 heuristic components and label-coverage evidence. Use after your pipeline resolves "
            "deployer, pre-launch funder and mint; choose cluster_launches for membership only. "
            "Not for wallet/token lookup, prediction, ownership attribution or safety decisions; "
            "scores are not probabilities and low does not mean safe.\n"
            "Supply 1-1000 distinct-mint edges. Keep connected groups together: splitting batches "
            "changes results. A funder_is_cex flag anywhere prevents that funder joining distinct "
            "deployers; it does not separate the same deployer's launches. lamports and block_time "
            "are validated but do not affect scores; cadence measures launch count, not time.\n"
            "Stateless local computation: no network/RPC, label verification, storage writes, "
            "credentials or external side effects. Each full stdio request line is limited to "
            "512000 bytes. Returns score-sorted clusters, membership, components, evidence, counts "
            "and versions. Check labelCoverage and notes: rug-rate evidence is null without labels, "
            "not zero. Invalid input rejects the whole batch with isError=true; correct it and retry."
        ),
        "inputSchema": input_schema(),
        "outputSchema": reputation_output_schema(),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "cluster_launches",
        "description": (
            "Group supplied launches by transitive non-exchange funding associations. Use when "
            "you need membership and launch counts only; choose deployer_reputation for heuristic "
            "scores and label evidence. Requires 1-1000 distinct-mint edges with caller-resolved "
            "deployer, pre-launch funder and mint; token-only rows are insufficient. A funder_is_cex "
            "flag anywhere prevents that funder joining distinct deployers, while same-deployer "
            "launches remain grouped. outcome, lamports and block_time are validated but do not "
            "affect grouping.\n"
            "Stateless local computation, no network/RPC, label verification, credentials, storage "
            "writes or external side effects. Returns cluster IDs, sorted member identifiers, "
            "launch counts, group count and ID version; no scores or safety/ownership claims. "
            "Keep connected groups in one batch; separate calls are never joined. Full stdio "
            "request lines are limited to 512000 bytes. Invalid input rejects the whole batch "
            "with isError=true; correct it and retry."
        ),
        "inputSchema": input_schema(),
        "outputSchema": cluster_output_schema(),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
]


# ------------------------------------------------------------------------ core
def _ff():
    """Import the tested module. The bundled scoring module is used by every transport."""
    if str(FF_ROOT) not in sys.path:
        sys.path.insert(0, str(FF_ROOT))
    from ff import cluster  # noqa: E402
    return cluster




def tool_deployer_reputation(args: dict) -> dict:
    ff = _ff()
    clusters = ff.cluster_by_funder(parse_edges(args))
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
        "model": "ff.cluster supplied-edge heuristic",
        "scorerVersion": ff.SCORER_VERSION,
        "clusterIdVersion": "CL2-SHA256",
        "caveat": (
            "Supplied-edge heuristic only: scores are not calibrated probabilities. "
            "No chain lookup or verified ownership attribution. Labels are caller supplied. "
            "Separate research AUC does not validate this scorer."
        ),
    }


def tool_cluster_launches(args: dict) -> dict:
    ff = _ff()
    clusters = ff.cluster_by_funder(parse_edges(args))
    return {
        "clusters": [
            {"cluster_id": c.cluster_id, "deployers": c.deployers, "funders": c.funders,
             "mints": c.mints, "n_launches": len(c.edges)}
            for c in clusters
        ],
        "n_clusters": len(clusters),
        "clusterIdVersion": "CL2-SHA256",
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


def _tool_call(mid, params, protocol_version):
    name = params.get("name")
    if not isinstance(name, str) or name not in HANDLERS:
        _reply(mid, error={"code": -32602, "message": "Unknown tool"})
        return
    try:
        payload = HANDLERS[name](params.get("arguments"))
        text, is_error = json.dumps(payload), False
    except ValueError as exc:
        payload, is_error = {"error": str(exc)}, True
        text = str(exc) if protocol_version == LEGACY_PROTOCOL_VERSION else json.dumps(payload)
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if protocol_version != LEGACY_PROTOCOL_VERSION:
        result["structuredContent"] = payload
    _reply(mid, result)


def handle(msg, protocol_version=LEGACY_PROTOCOL_VERSION):
    """Reply to one request, returning a newly negotiated version only on initialize."""
    if not isinstance(msg, dict):
        _reply(None, error={"code": -32600, "message": "Expected JSON-RPC object"})
        return
    valid_id = "id" not in msg or msg["id"] is None or type(msg["id"]) in (str, int)
    if msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str) or not valid_id:
        _reply(None, error={"code": -32600, "message": "Invalid JSON-RPC request"})
        return
    if "id" not in msg:
        return
    mid, method, params = msg["id"], msg["method"], msg.get("params", {})
    if not isinstance(params, dict):
        _reply(mid, error={"code": -32602, "message": "params must be an object"})
        return
    if method == "initialize":
        requested = params.get("protocolVersion")
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        _reply(mid, {"protocolVersion": negotiated,
                     "capabilities": {"tools": {"listChanged": False}},
                     "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
        return negotiated
    elif method == "tools/list":
        tools = TOOLS if protocol_version != LEGACY_PROTOCOL_VERSION else [
            {key: tool[key] for key in ("name", "description", "inputSchema")} for tool in TOOLS
        ]
        _reply(mid, {"tools": tools})
    elif method == "tools/call":
        _tool_call(mid, params, protocol_version)
    elif method == "ping":
        _reply(mid, {})
    else:
        _reply(mid, error={"code": -32601, "message": "Method not found"})


def serve():
    """Consume bounded newline-delimited JSON, recovering after malformed input."""
    stream = sys.stdin.buffer
    protocol_version = LEGACY_PROTOCOL_VERSION
    while True:
        line = stream.readline(MAX_BODY_BYTES + 1)
        if not line:
            return 0
        if len(line) > MAX_BODY_BYTES:
            while line and not line.endswith(b"\n"):
                line = stream.readline(MAX_BODY_BYTES + 1)
            _reply(None, error={"code": -32600, "message": "Request too large"})
            continue
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            protocol_version = handle(msg, protocol_version) or protocol_version
        except (ValueError, UnicodeError, RecursionError):
            _reply(None, error={"code": -32700, "message": "Invalid JSON"})


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
    print("Supplied-edge heuristic; separate research does not validate this scorer.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(serve())
