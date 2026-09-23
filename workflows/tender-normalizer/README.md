# Tender Feed Normalizer workflow inputs

Reusable input JSON for Ultrathink Labs' [Tender Feed Normalizer](https://apify.com/ultrathink-labs/tender-feed-normalizer). This directory contains buyer inputs, **not the normalizer's source code**. The parent repository's reputation scorer is a separate product.

## Start with one small, auditable result

1. Open `tender_normalizer_records.json`, choose **Raw**, and copy the complete JSON.
2. Open the Actor's JSON input and replace everything, including its prefill.
3. Keep default 256 MB; set Maximum charge per run to $0.01 in run options.
4. Start only after checking current Store prices. The fictional input yields one clean USD row and one EUR rejection in `REPORT`. At the published $0.001/clean row plus $0.00005/start, expected event charge is $0.00105—not the $0.01 ceiling.
5. Inspect the default dataset and `REPORT`. Use `tender_normalizer_retry_eur.json` to process only the rejected fictional EUR notice in a second run. That run has its own charge.

No supplied notice is a real procurement opportunity. Date-dependent `expired` changes over time. A clean row is not proof that a notice is genuine or still open.

| Input file | Status and use |
|---|---|
| `tender_normalizer_records.json` | Complete fictional first-run input; intentional currency mismatch. |
| `tender_normalizer_retry_eur.json` | Complete fictional selective retry; does not resend the already delivered USD record. |
| `tender_normalizer_dataset.json` | Manual/API template: replace dataset-ID placeholder with an accessible real Apify ID. |
| `tender_normalizer_samgov_sample.json` | Complete fictional fixture using published SAM.gov scraper field names and explicit field mapping. Software mapping can be tested; this is not a real upstream run. |
| `tender_normalizer_samgov_integration.json` | Actor-to-Actor integration template. The integration form replaces `{{resource.defaultDatasetId}}`; the Actor itself does not expand it. |
| `tender_normalizer_sourceurl.json` | Public HTTPS CSV/JSON template; `example.org` is a placeholder, not a working feed. |

## Recurring handoff

Use the latest successful upstream run's dataset through Actor-to-Actor Integrations; remove `records` and `sourceUrl` when using a dataset. A saved task with yesterday's fixed dataset ID does not discover today's data. Inspect actual output rows before connecting a producer. A shared dataset is readable by anyone who knows its ID; do not expose sensitive data to clear a permission error.

The SAM.gov field map is based on [Scrape Sage's published schema](https://apify.com/scrapesage/sam-gov-scraper). It is not an endorsement or certification of an upstream Actor run. Confirm `responseDeadline` is present, enable the producer's full-details option where needed, and inspect normalized dates. A contract end date or award period is not a tender submission deadline.

Import clean rows into your destination, route `REPORT.issues` to review, and keep source namespace + notice ID for your own cross-run deduplication/amendment policy. Normalizer deduplication is per run only. Repeated input can produce repeated charges. The Actor fetches at most the first 10,000 dataset rows; partition larger feeds before handoff.

No subscription, schedule, upstream scraping, or price change is created by these files. Set a separate cap for every upstream/downstream Actor. Follow the [Store README](https://apify.com/ultrathink-labs/tender-feed-normalizer) for exact parsing, errors, provenance, billing and privacy limits.
