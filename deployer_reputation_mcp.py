"""Bounded supplied-edge heuristic exposed over MCP stdio."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FF_ROOT = Path(__file__).resolve().parent   # ff/ ships in this repo
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "deployer-reputation"
SERVER_VERSION = "1.1.0"

from validation import input_schema, parse_edges, MAX_BODY_BYTES

TOOLS = [
    {"name": "deployer_reputation", "description": "Explainable heuristic score of supplied launch edges; not a probability or verified operator identity.", "inputSchema": input_schema()},
    {"name": "cluster_launches", "description": "Group supplied launches by non-exchange funding associations; not proof of common ownership.", "inputSchema": input_schema()},
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
        "model": "ff.cluster serial-deployer reputation (Wilson-LB blended, weights sum to 1.0)",
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


def _tool_call(mid, params):
    name = params.get("name")
    if not isinstance(name, str) or name not in HANDLERS:
        _reply(mid, error={"code": -32602, "message": "Unknown tool"})
        return
    try:
        payload = HANDLERS[name](params.get("arguments"))
        _reply(mid, {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False})
    except ValueError as exc:
        _reply(mid, {"content": [{"type": "text", "text": str(exc)}], "isError": True})


def handle(msg):
    """Handle one JSON-RPC object; arrays and invalid envelopes never kill stdio."""
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
        _reply(mid, {"protocolVersion": PROTOCOL_VERSION,
                     "capabilities": {"tools": {"listChanged": False}},
                     "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
    elif method == "tools/list":
        _reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        _tool_call(mid, params)
    elif method == "ping":
        _reply(mid, {})
    else:
        _reply(mid, error={"code": -32601, "message": "Method not found"})


def serve():
    """Consume bounded newline-delimited JSON, recovering after malformed input."""
    stream = sys.stdin.buffer
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
            handle(msg)
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
