# Tender Feed Normalizer workflow inputs

Reusable inputs and checksum verifier for Ultrathink Labs' [Tender Feed Normalizer](https://apify.com/ultrathink-labs/tender-feed-normalizer). This directory contains buyer workflows, **not the normalizer's source code**. The parent repository's reputation scorer is a separate product.

## Start with one small, auditable result

1. Open `tender_normalizer_records.json`, choose **Raw**, and copy the complete JSON.
2. Open the Actor's JSON input and replace everything, including its prefill.
3. Use the validated default 128 MB; set Maximum charge per run to $0.01 in run options. Large individual fields may need more memory even below the row cap.
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

## Stage-safe procurement audit companion

`tender_normalizer_stage_sample.json` is a complete fictional tender/award example: only the supplied tender-stage row is delivered; the award remains in REPORT. `tender_normalizer_ciel_integration.json` is a **published-schema candidate**, not a verified live Ciel Labs integration. The upstream already harmonizes/deduplicates; use an extra audit step only when common cross-source error/checksum receipts add value.

`stageField` names an exact top-level source column. Only the string `tender` passes (case/outer whitespace ignored); missing and other values receive separate error codes. Labels do not prove source truth. Contract `endDate` is no longer an implicit deadline alias. Explicitly map it only when the source really means submission deadline.

### Verify an exported receipt offline

Download the complete default dataset as JSON to `dataset.json` and the `AUDIT` key-value record to `audit.json`, then run:

```sh
python verify_audit.py --audit audit.json --dataset dataset.json
```

Optional `--input-records records.json` checks the selected parsed row array too (not the full Actor input wrapper or original CSV bytes). No packages, credentials or network calls required. All checks must be true; exit 1 means mismatch. Hashes preserve object/array order and normalize integral floats to integers, matching Apify's numeric storage round trip. Keep downloaded JSON key order intact. A mismatch can indicate reformatting, changed serialization or changed content; it is not automatically fraud. Checksums certify consistency, **never source authenticity or procurement eligibility**.

Run and schema limits remain in the Store README. Prices unchanged. No customer, revenue, or universal upstream-compatibility claim.
