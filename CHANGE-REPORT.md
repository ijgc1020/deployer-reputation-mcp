# Buyer onboarding and reusable workflows — 2026-09-22 mission

- Added exact fictional first-run and refreshed-snapshot inputs; documented required enrichment, unknown outcomes, strict schema, stateless runs, batch limits and honest per-batch economics.
- Added executable local MCP handshake/discovery/score/group/error/recovery JSONL. Input-schema descriptions now explain data responsibility; validation rules, numeric scoring and billing behavior unchanged.
- Added public tender-normalizer input library under workflows/tender-normalizer. It contains JSON inputs, not private normalizer source; named upstream mapping remains a schema candidate, not a verified upstream run.
- Completed the pre-existing MIT license's truncated warranty/liability paragraph from the standard SPDX MIT text; permission grant unchanged.
- Main executed 29 reputation regressions and verify_all three times, plus real local stdio and first/refresh/missing-edge smoke paths. These are software checks using fictional fixtures, not predictive validity, paid demand or customer revenue.
- Deployment evidence belongs to the actual Apify run/build records and GitHub release, not an embedded stale build-number claim.

## Historical scorer audit

# Local reputation scorer audit fixes

Status: independent QA PASSED (fleet audit 2026-09-21 handoff report); DEPLOYED as build 1.1.6 on 2026-09-21 with cloud validation.

Modified: ff/cluster.py, deployer_reputation_mcp.py, README.md.
Added: test_scorer_policy.py, CHANGE-REPORT.md.
Backup: operator launch-backups archive, fleet-audit-20260921/reputation/audit-20260920-211252.

- R1: CL2 full SHA-256 IDs over sorted unique role-prefixed membership encoded as compact ASCII JSON. IDs depend on membership, not operator identity. README explains migration.
- R2: high band requires positive rug_launches; weights/formula unchanged. Fourteen unknown-only or alive-only launches retain score 0.501 but become elevated.
- R3: copy frozen edges with batch-wide CEX classification before grouping; evidence and score agree without changing caller inputs. Mixed CEX flags can therefore change scores, as intended.
- Added labelCoverage and explicit missing/incomplete outcome notes, low-is-not-safe warning, scorerVersion 2.0.0 and clusterIdVersion CL2-SHA256 metadata. Removed ownership/calibrated-band claims from core comments.
- README describes live 1.1.5 baseline separately from pending local scorer changes. Actor billing/delivery, schemas, validation and dependencies untouched.

Validation: python -m unittest discover -q, 22 tests PASS on three consecutive runs (0.171s, 0.158s, 0.156s). Existing Starlette/httpx deprecation warning only. New tests cover delimiter collision, reorder stability, membership sensitivity, unchanged structural numeric score, positive-rug high policy, global CEX consistency/immutability, coverage notes and output isolation. Existing transport and dataset-only delivery tests pass.

Pending: review/change cloud metadata if deploying; approved cloud build and functional verification. No network, spending, cloud actions or commits performed for this patch.
