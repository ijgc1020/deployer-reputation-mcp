# Is this the right tool for your workflow?

Maintained by Ultrathink Labs, the publisher of both linked Actors. Start with the input you already have; neither tool collects missing evidence for you.

## Tender CSV/JSON audit

**Fits:** you already collect tender notices and need to check submission deadlines, monetary values, duplicates, and optional stage labels before using the results in a spreadsheet or downstream system.

**Does not fit:** you need another scraper, bid-writing service, verified eligibility decision, or conversion of contract completion dates into submission deadlines. A field called `endDate` is not enough to establish deadline meaning. Caller-supplied `tender` stage labels are not independently verified.

- [Open the tender Actor](https://apify.com/ultrathink-labs/tender-feed-normalizer).
- [Use the fictional first-run and selective-retry inputs](workflows/tender-normalizer/README.md).
- Save the delivered dataset plus REPORT and AUDIT records. SHA-256 checks verify consistency of the selected parsed input, effective settings, and delivered output—not source truth, completeness, or eligibility.
- Current listed event arithmetic: $0.001 per delivered clean row + $0.00005 start at the default 128 MB. One start and 100 delivered clean rows = $0.10005. Rejected rows are not clean-row events. Check current Store prices and a suitable maximum charge before running. Upstream collection is separate.

For repeat use, provide each new source snapshot, retain input/output receipts, and retry only corrected rejected rows when appropriate. Re-running an old dataset does not collect new tenders.

## Supplied-edge reputation heuristic

**Fits:** you already hold supported deployer/funder/mint edges and want explainable grouping plus an uncalibrated heuristic over that evidence.

**Does not fit:** you have only a mint list, prices, or a creator field without resolved funding provenance. This tool does not fetch RPC evidence or predict fraud. Shared funding does not prove common ownership. Low does not mean safe.

- [Open the reputation Actor](https://apify.com/ultrathink-labs/deployer-reputation-heuristic).
- [Read the exact input contract and offline option](README.md).
- $0.005 per delivered analysis batch, up to 1,000 distinct-mint edges—not per edge or nested cluster. Check current Store prices and maximum-charge settings before running. Enrichment costs are separate.

For repeat use, rebuild an evidence snapshot with new observations and supported labels; each delivered analysis is another charge. Arbitrary chunks can split connected groups. Identical-input reruns add no evidence.

## One next step: request a workflow-fit check

[Open a workflow-fit request](https://github.com/ijgc1020/deployer-reputation-mcp/issues/new?template=workflow-fit.md).

Tell us the task you want to complete, which tool you are considering, the source schema, expected batch size/frequency, and where the result must go. A public documentation link or synthetic field-name example is enough for first contact. No purchase is required to ask; this is a product-fit discussion, not a promised custom integration or response-time guarantee.

**GitHub issues are public and require a GitHub account. Never post tokens, private datasets or dataset IDs, personal data, transaction documents, billing receipts, or confidential procurement records.** Do not make a private dataset public to obtain support. If your schema itself is confidential, do not post it; use an existing private support channel agreed with the publisher.

We will separate four outcomes: supported as documented; a specific mapping needs validation; required evidence is missing; or the tool is not a fit. A request, free run, owner demonstration, clone, or directory listing is not proof of a sale.
