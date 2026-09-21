"""Read records from an Apify dataset by ID - the integration input path.

Other Actors hand over only a dataset ID (via `payload.resource.defaultDatasetId` or an
explicit `datasetId` input), never credentials and never arbitrary URLs. This module fetches
that one bounded dataset: platform host only, alphanumeric ID, at most MAX_ROWS items.
"""
import json
import os
import re
import urllib.request

DATASET_PAGE = 1000
MAX_ROWS = 10000
REQUEST_TIMEOUT = 30


def dataset_id_from(data):
    """Explicit datasetId input wins; otherwise the implicit integration payload supplies it."""
    if not isinstance(data, dict):
        return None
    explicit = data.get('datasetId')
    if explicit is not None:
        if not isinstance(explicit, str):
            raise ValueError('datasetId must be a string')
        return explicit
    resource = (data.get('payload') or {}).get('resource') or {}
    implicit = resource.get('defaultDatasetId')
    return implicit if isinstance(implicit, str) else None


def fetch_page(base, dataset_id, offset, token):
    """One page of dataset items, with or without the run token."""
    url = f'{base}/v2/datasets/{dataset_id}/items?offset={offset}&limit={DATASET_PAGE}'
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        page = json.load(response)
    if not isinstance(page, list):
        raise ValueError('dataset response was not an item array')
    return page


def fetch_dataset_records(dataset_id):
    """Return up to MAX_ROWS items from one Apify dataset. Reads without credentials first
    (works for datasets shared as view-by-link); on 401/403 retries with the run token, then
    tells the operator exactly how to share the dataset."""
    if not re.fullmatch(r'[A-Za-z0-9]{10,32}', dataset_id or ''):
        raise ValueError('datasetId must be the alphanumeric ID of an Apify dataset')
    base = os.environ.get('APIFY_API_BASE_URL', 'https://api.apify.com').rstrip('/')
    token = os.environ.get('APIFY_TOKEN')
    try:
        first = fetch_page(base, dataset_id, 0, None)
        authed = False
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403) or not token:
            raise ValueError(f'dataset unreadable: HTTP {exc.code}') from None
        try:
            first = fetch_page(base, dataset_id, 0, token)
            authed = True
        except urllib.error.HTTPError as retry:
            raise ValueError(
                f'dataset unreadable: HTTP {retry.code}. Share the dataset for anyone with the '
                'link (Settings -> generalAccess ANYONE_WITH_ID_CAN_READ), or run with storage '
                'permissions') from None
    items, offset = list(first), DATASET_PAGE
    while len(first) == DATASET_PAGE and len(items) < MAX_ROWS:
        page = fetch_page(base, dataset_id, offset, token if authed else None)
        items.extend(page)
        if len(page) < DATASET_PAGE:
            break
        offset += DATASET_PAGE
    return items[:MAX_ROWS]
