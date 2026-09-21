"""Offline evaluation kit: score bundled demo scenarios and check golden outputs.

Demonstrates, with no RPC/HTTP/external data:
  1. a serial deployer cluster with supplied rugged outcomes scores above clean deployers;
  2. independent clean deployers stay separate and low;
  3. a shared exchange funder does NOT merge distinct deployers into one cluster.

  python scripts/demo_reputation.py            verify against golden outputs
  python scripts/demo_reputation.py --regen    regenerate goldens after an intended scorer change

Prints PASS/FAIL per scenario and exits non-zero on any mismatch.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import deployer_reputation_mcp as scorer      # noqa: E402

EDGES = ROOT / 'examples' / 'demo_edges.json'
GOLDEN = ROOT / 'examples' / 'expected_demo_output.json'


def run_scenarios():
    scenarios = json.loads(EDGES.read_text(encoding='utf-8'))
    results = {}
    for name, edges in scenarios.items():
        results[name] = scorer.tool_deployer_reputation({'edges': edges})
    return results


def structural_checks(results):
    """Invariants the demo exists to teach; independent of exact numeric scores."""
    problems = []
    serial = results['serial_rugger']['clusters'][0]
    clean = results['clean_independents']
    cex = results['shared_cex_funder']
    if serial['band'] not in ('high',):
        problems.append(f"serial rugger band {serial['band']} != high (positive rug labels present)")
    if serial['score'] <= max(c['score'] for c in clean['clusters']):
        problems.append('serial rugger must outscore clean independents')
    if clean['clusters'][0]['band'] != 'low':
        problems.append(f"clean independent band {clean['clusters'][0]['band']} != low")
    if cex['n_clusters'] != 2:
        problems.append(f"shared CEX funder merged deployers: n_clusters={cex['n_clusters']} != 2")
    return problems


def main():
    regen = '--regen' in sys.argv
    results = run_scenarios()
    problems = structural_checks(results)
    if regen:
        GOLDEN.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print('goldens regenerated - review the diff before trusting them')
    else:
        expected = json.loads(GOLDEN.read_text(encoding='utf-8'))
        if results != expected:
            problems.append('outputs differ from golden (run --regen after an intended scorer change)')
    for name, result in results.items():
        top = result['clusters'][0]
        print(f"{name}: {result['n_clusters']} cluster(s), top {top['cluster_id'][:20]}... "
              f"score={top['score']} band={top['band']} components={top['components']}")
    for problem in problems:
        print(f'FAIL: {problem}')
    print('DEMO PASS' if not problems else 'DEMO FAIL')
    print('Supplied-edge heuristic only; scores are not calibrated probabilities or fraud findings.')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
