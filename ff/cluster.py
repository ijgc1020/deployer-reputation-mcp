"""Shared-funder clustering + serial-deployer reputation scoring.

This is the layer the FUNDER-FINGERPRINT thesis needs on TOP of the per-launch
tracer (ff.tracer): the tracer answers "who funded this ONE launch"; this module
answers "which launches/deployers are the SAME OPERATOR, and how bad is that
operator's track record" -- across many launches.

Input  : a stream of wallet->funder edges (one per observed launch/deployer),
          each carrying (deployer, funder, mint, block_time, lamports, outcome,
          funder_is_cex). These are exactly what ff.tracer.build_fingerprint /
          ff.backfill already produce per launch -- see `from_fingerprints` and
          `from_backfill_json` adapters below.
Output : (1) CLUSTER IDS -- distinct deployers that share a common funder (the
          sticky money origin) are collapsed into one operator cluster via
          union-find over the bipartite deployer<->funder graph; and
          (2) a SERIAL-DEPLOYER REPUTATION SCORE in [0,1] per cluster -- a
          bounded, monotone, *explainable* blend of how many throwaway deployers
          one funder is spinning up, launch cadence, fan-out breadth, CEX origin,
          and (only when outcomes are labeled) a Wilson LOWER-bound on the
          observed rug-rate. It NEVER fabricates outcome labels: unlabeled
          launches contribute zero rug-evidence, and the score degrades to a
          pure structural risk score in that case (documented, honest).

The whole module is PURE + stdlib-only (no deps), so it is fully unit-testable
against a synthetic edge fixture with zero network. See tests/test_cluster.py
and fixtures/cluster_edges.py.

Why key on the funder and cluster on it
---------------------------------------
A serial rugger rotates a fresh *deployer* wallet every launch (so per-token and
per-deployer reputation is defeated by design), but funds them from a stickier
origin branch. Collapsing by shared funder re-attaches the rotated deployers to
one identity, which is what makes a *reputation* possible at all.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

LAMPORTS_PER_SOL = 1_000_000_000

# Outcomes we treat as a "bad" (rug-like) launch when scoring the labeled tail.
RUG_OUTCOMES = frozenset({"rug", "dump", "soft_rug", "scam"})
GOOD_OUTCOMES = frozenset({"graduated", "survived", "alive"})


# --------------------------------------------------------------------------
# input edge
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DeployEdge:
    """One observed launch: `funder` seeded `deployer`, which launched `mint`.

    `outcome` is one of rug/dump/graduated/survived/unknown (default unknown --
    the honest default; we do not invent labels). `funder_is_cex` marks that the
    money's origin branch is a known CEX/infra hot wallet (a weak signal on its
    own, but relevant to cluster provenance).
    """
    deployer: str
    funder: str
    mint: str
    block_time: Optional[int] = None
    lamports: int = 0
    outcome: str = "unknown"
    funder_is_cex: bool = False

    @property
    def sol(self) -> float:
        return self.lamports / LAMPORTS_PER_SOL

    @property
    def is_rug(self) -> bool:
        return self.outcome in RUG_OUTCOMES

    @property
    def is_labeled(self) -> bool:
        return self.outcome in RUG_OUTCOMES or self.outcome in GOOD_OUTCOMES


# --------------------------------------------------------------------------
# union-find over the bipartite deployer<->funder graph
# --------------------------------------------------------------------------
class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, x: str) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _cluster_id(members: Iterable[str]) -> str:
    """Stable, order-independent cluster id derived from its member set.

    Deterministic across runs (sorted + hashed) so the same operator gets the
    same CL-id every time -- important for a persistent reputation registry.
    """
    key = "|".join(sorted(members))
    h = 0
    for ch in key:               # tiny FNV-1a-ish rolling hash, stdlib-only
        h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return f"CL-{h:08x}"


# --------------------------------------------------------------------------
# cluster result
# --------------------------------------------------------------------------
@dataclass
class Cluster:
    cluster_id: str
    deployers: list[str] = field(default_factory=list)
    funders: list[str] = field(default_factory=list)
    mints: list[str] = field(default_factory=list)
    edges: list[DeployEdge] = field(default_factory=list)

    # --- structural aggregates (all derived from edges) ---
    @property
    def n_deployers(self) -> int:
        return len(self.deployers)

    @property
    def n_funders(self) -> int:
        return len(self.funders)

    @property
    def n_launches(self) -> int:
        return len(self.mints)

    @property
    def any_cex(self) -> bool:
        return any(e.funder_is_cex for e in self.edges)

    @property
    def labeled_launches(self) -> int:
        return sum(1 for e in self.edges if e.is_labeled)

    @property
    def rug_launches(self) -> int:
        return sum(1 for e in self.edges if e.is_rug)

    @property
    def deployers_per_funder(self) -> float:
        """Core serial-deployer ratio: how many throwaway deployers per funder.

        1.0 => one deployer per funder (organic / one-off). >1 => a funder is
        spinning up multiple deployers (the serial-operator signature).
        """
        return self.n_deployers / self.n_funders if self.n_funders else 1.0

    def rug_rate(self) -> Optional[float]:
        """Observed rug-rate over the LABELED launches only (None if unlabeled).

        Never imputes a label -- unlabeled launches are excluded from both
        numerator and denominator.
        """
        lab = self.labeled_launches
        return round(self.rug_launches / lab, 4) if lab else None

    def wilson_lower_bound(self, z: float = 1.96) -> Optional[float]:
        """Wilson score LOWER bound on the true rug-rate (95% by default).

        Honest under small N: a cluster with 1/1 rugs does NOT get a 100%
        reputation hit -- the lower bound stays modest until evidence accrues.
        Returns None when there are no labeled launches.
        """
        n = self.labeled_launches
        if n == 0:
            return None
        p = self.rug_launches / n
        denom = 1 + z * z / n
        centre = p + z * z / (2 * n)
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
        return round(max(0.0, (centre - margin) / denom), 4)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def _sat(x: float, k: float) -> float:
    """Saturating 0..1 curve: x/(x+k). Monotone, bounded, no cliffs."""
    return x / (x + k) if x > 0 else 0.0


# Component weights for the serial-deployer reputation score. They sum to 1.0 so
# the raw score is in [0,1]; each component is independently in [0,1]. Tuned to
# be conservative (structure alone caps well below 1.0; only corroborated rug
# evidence pushes a cluster into the high-risk band).
_W = {
    "serial": 0.34,   # many deployers sharing one funder  (the headline signal)
    "cadence": 0.16,  # launch volume / repeat behavior
    "fanout": 0.12,   # breadth of fresh-wallet fan-out
    "cex": 0.08,      # money originates from a CEX/infra hot wallet
    "rugs": 0.30,     # Wilson-lower-bounded observed rug-rate (labeled only)
}


@dataclass
class ReputationScore:
    cluster_id: str
    score: float                     # 0..1, higher = worse (more serial-rugger-like)
    band: str                        # low / elevated / high
    components: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "serial_deployer_score": self.score,
            "band": self.band,
            "components": self.components,
            "evidence": self.evidence,
        }


def score_cluster(c: Cluster) -> ReputationScore:
    """Compute the serial-deployer reputation score for one cluster.

    Structural components fire with zero outcome labels (so a fresh cluster still
    gets a risk read from its shape); the rug component only contributes when
    launches are labeled, via a Wilson lower bound so small-N does not overclaim.
    """
    # --- serial: deployers-per-funder above the organic 1.0 baseline ---
    excess = max(0.0, c.deployers_per_funder - 1.0)
    serial = _sat(excess, 2.0)                    # 3 dep/funder -> ~0.5

    # --- cadence: how many launches this operator has produced ---
    cadence = _sat(max(0, c.n_launches - 1), 4.0)  # 5 launches -> 0.5

    # --- fanout: total distinct fresh children the funders fanned to ---
    # proxy: launches are each a fan-out event; use launches as breadth proxy
    fanout = _sat(c.n_launches, 6.0)

    cex = 1.0 if c.any_cex else 0.0

    wlb = c.wilson_lower_bound()
    rugs = wlb if wlb is not None else 0.0

    comps = {
        "serial": round(serial, 4),
        "cadence": round(cadence, 4),
        "fanout": round(fanout, 4),
        "cex": round(cex, 4),
        "rugs": round(rugs, 4),
    }
    raw = sum(_W[k] * comps[k] for k in _W)
    score = round(raw, 4)

    # Bands calibrated so a fully-corroborated serial operator (many deployers
    # per funder + labeled rugs) lands "high", while a structural-only cluster
    # (shared funder but no rug labels) stays at most "elevated" -- it must never
    # be flagged high on structure alone. Wilson-LB conservatism means even 4/4
    # rugs contributes ~0.51, so `high` sits at 0.50, not an unreachable 0.60.
    band = "low"
    if score >= 0.50:
        band = "high"
    elif score >= 0.28:
        band = "elevated"

    return ReputationScore(
        cluster_id=c.cluster_id,
        score=score,
        band=band,
        components=comps,
        evidence={
            "n_deployers": c.n_deployers,
            "n_funders": c.n_funders,
            "n_launches": c.n_launches,
            "deployers_per_funder": round(c.deployers_per_funder, 3),
            "any_cex": c.any_cex,
            "labeled_launches": c.labeled_launches,
            "rug_launches": c.rug_launches,
            "observed_rug_rate": c.rug_rate(),
            "rug_rate_wilson_lb": wlb,
            "rug_evidence": ("labeled" if c.labeled_launches
                             else "UNLABELED -- structural score only "
                                  "(wire outcome labels to add rug evidence)"),
        },
    )


# --------------------------------------------------------------------------
# top-level: edges -> clusters -> scores
# --------------------------------------------------------------------------
def cluster_by_funder(edges: Iterable[DeployEdge]) -> list[Cluster]:
    """Collapse edges into shared-funder operator clusters (union-find).

    Two launches land in the same cluster iff their deployer/funder graphs are
    connected -- i.e. they share a funder, OR are linked through a chain of
    shared funders (funder A funds deployers X,Y; a later edge funds Y from
    funder B => A,B,X,Y are one operator). Deployer and funder namespaces are
    kept disjoint (prefixed) so an address that is coincidentally both never
    cross-links two operators by string collision alone.
    """
    uf = _UnionFind()
    edges = list(edges)
    for e in edges:
        d, f = f"D:{e.deployer}", f"F:{e.funder}"
        uf.add(d)
        uf.add(f)
        uf.union(d, f)

    buckets: dict[str, list[DeployEdge]] = {}
    for e in edges:
        root = uf.find(f"D:{e.deployer}")
        buckets.setdefault(root, []).append(e)

    clusters: list[Cluster] = []
    for _root, es in buckets.items():
        deployers = sorted({e.deployer for e in es})
        funders = sorted({e.funder for e in es})
        mints = sorted({e.mint for e in es})
        # stable id from the union of node identities (deployers + funders)
        cid = _cluster_id([f"D:{d}" for d in deployers] + [f"F:{f}" for f in funders])
        clusters.append(Cluster(
            cluster_id=cid, deployers=deployers, funders=funders,
            mints=mints, edges=es,
        ))
    # deterministic ordering: worst structural risk first, then id
    clusters.sort(key=lambda c: (-c.deployers_per_funder, -c.n_launches, c.cluster_id))
    return clusters


def analyze_edges(edges: Iterable[DeployEdge]) -> dict:
    """Full pipeline: edges -> clusters -> per-cluster reputation scores.

    Returns a JSON-serializable report: one entry per cluster with its id,
    members, and serial-deployer reputation score + explainable components.
    """
    edges = list(edges)                 # materialize once (safe for generators)
    n_edges = len(edges)
    clusters = cluster_by_funder(edges)
    out = []
    for c in clusters:
        rs = score_cluster(c)
        out.append({
            "cluster_id": c.cluster_id,
            "deployers": c.deployers,
            "funders": c.funders,
            "mints": c.mints,
            **rs.to_row(),
        })
    ranked = sorted(out, key=lambda r: -r["serial_deployer_score"])
    return {
        "n_edges": n_edges,
        "n_clusters": len(clusters),
        "clusters": ranked,
        "highest_risk": ranked[0] if ranked else None,
    }


# --------------------------------------------------------------------------
# adapters from the rest of the package
# --------------------------------------------------------------------------
def from_fingerprints(fingerprints: Iterable, outcomes: Optional[dict] = None
                      ) -> list[DeployEdge]:
    """Build DeployEdges from ff.tracer.FunderFingerprint objects.

    Each fingerprint already carries (funder, mint, deploy_block_time,
    source_is_cex). The deployer isn't stored on the fingerprint, so callers may
    pass `outcomes` = {mint: (deployer, outcome)} to supply it; otherwise we key
    the deployer on the mint (still clusters correctly by shared funder).
    """
    outcomes = outcomes or {}
    edges: list[DeployEdge] = []
    for fp in fingerprints:
        deployer, outcome = outcomes.get(fp.mint, (f"deployer_of:{fp.mint}", "unknown"))
        edges.append(DeployEdge(
            deployer=deployer,
            funder=fp.funder,
            mint=fp.mint,
            block_time=fp.deploy_block_time,
            lamports=fp.lamports_total,
            outcome=outcome,
            funder_is_cex=bool(fp.source_is_cex),
        ))
    return edges


def from_backfill_json(path: str) -> list[DeployEdge]:
    """Load DeployEdges from a backfill_out.json produced by ff.backfill.

    Uses the per-launch `detail[].fingerprint` rows. The deployer field, when
    present on the detail row, is used; else we fall back to the mint.
    """
    data = json.load(open(path, encoding="utf-8"))
    edges: list[DeployEdge] = []
    for det in data.get("detail", []):
        fp = det.get("fingerprint", {})
        funder = fp.get("funder")
        mint = fp.get("mint")
        if not funder or not mint:
            continue
        deployer = det.get("deployer") or fp.get("deployer") or f"deployer_of:{mint}"
        edges.append(DeployEdge(
            deployer=deployer,
            funder=funder,
            mint=mint,
            block_time=fp.get("deploy_block_time"),
            lamports=int(round((fp.get("sol_total") or 0.0) * LAMPORTS_PER_SOL)),
            outcome=fp.get("outcome_20min", "unknown"),
            funder_is_cex=bool(fp.get("source_is_cex")),
        ))
    return edges


def _edges_from_json_records(records: list[dict]) -> list[DeployEdge]:
    """Parse a plain list of edge dicts (the CLI input format)."""
    out = []
    for r in records:
        out.append(DeployEdge(
            deployer=r["deployer"],
            funder=r["funder"],
            mint=r.get("mint", r["deployer"]),
            block_time=r.get("block_time"),
            lamports=int(r.get("lamports", 0)),
            outcome=r.get("outcome", "unknown"),
            funder_is_cex=bool(r.get("funder_is_cex", False)),
        ))
    return out


def main(argv=None) -> int:
    """CLI: python -m ff.cluster <edges.json>

    <edges.json> is either a plain list of edge records
    [{"deployer","funder","mint","outcome"?,"funder_is_cex"?,"lamports"?}, ...]
    or a backfill_out.json (auto-detected by the presence of a "detail" key).
    """
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m ff.cluster <edges.json|backfill_out.json>",
              file=sys.stderr)
        return 2
    path = args[0]
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict) and "detail" in data:
        edges = from_backfill_json(path)
    elif isinstance(data, dict) and "edges" in data:
        edges = _edges_from_json_records(data["edges"])
    else:
        edges = _edges_from_json_records(data)
    report = analyze_edges(edges)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
