"""Apify entry point: validate supplied edges, store one auditable result."""
import asyncio
import json

from dataset_input import dataset_id_from, fetch_dataset_records
from deployer_reputation_mcp import tool_cluster_launches, tool_deployer_reputation
from validation import MAX_BODY_BYTES

ALLOWED_KEYS = {'edges', 'operation', 'datasetId', 'payload'}


def run_input(data):
    """Process an Actor input without fetching chain data or claiming attribution.

    Edges arrive inline, or by dataset reference: explicit `datasetId`, or the implicit
    integration payload's `resource.defaultDatasetId`. References fetch platform datasets
    only - never arbitrary URLs or caller credentials."""
    if not isinstance(data, dict) or set(data) - ALLOWED_KEYS:
        raise ValueError('Input requires edges and optional operation')
    if len(json.dumps(data).encode()) > MAX_BODY_BYTES:
        raise ValueError('Input too large')
    operation = data.get('operation', 'score')
    if operation not in ('score', 'cluster'):
        raise ValueError('operation must be score or cluster')
    edges = data.get('edges')
    if edges is None:
        dataset_id = dataset_id_from(data)
        if dataset_id:
            edges = fetch_dataset_records(dataset_id)
    handler = tool_deployer_reputation if operation == 'score' else tool_cluster_launches
    return handler({'edges': edges})


async def main():
    """Publish validated results only through the platform-metered dataset."""
    from apify import Actor
    async with Actor:
        result = run_input(await Actor.get_input())
        await Actor.push_data(result)


if __name__ == '__main__':
    asyncio.run(main())
