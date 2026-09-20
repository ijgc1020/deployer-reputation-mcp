"""Apify entry point: validate supplied edges, store one auditable result."""
import asyncio
import json

from deployer_reputation_mcp import tool_cluster_launches, tool_deployer_reputation
from validation import MAX_BODY_BYTES


def run_input(data):
    """Process an Actor input without fetching chain data or claiming attribution."""
    if not isinstance(data, dict) or set(data) - {'edges', 'operation'}:
        raise ValueError('Input requires edges and optional operation')
    if len(json.dumps(data).encode()) > MAX_BODY_BYTES:
        raise ValueError('Input too large')
    operation = data.get('operation', 'score')
    if operation not in ('score', 'cluster'):
        raise ValueError('operation must be score or cluster')
    handler = tool_deployer_reputation if operation == 'score' else tool_cluster_launches
    return handler({'edges': data.get('edges')})


async def main():
    """Persist result only after the full batch passes validation."""
    from apify import Actor
    async with Actor:
        result = run_input(await Actor.get_input())
        await Actor.set_value('OUTPUT', result)
        await Actor.push_data(result)


if __name__ == '__main__':
    asyncio.run(main())
