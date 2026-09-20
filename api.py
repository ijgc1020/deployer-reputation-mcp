"""Authenticated, bounded HTTP access to the same supplied-edge scorer."""
import hmac
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from deployer_reputation_mcp import tool_cluster_launches, tool_deployer_reputation
from validation import MAX_BODY_BYTES


@asynccontextmanager
async def lifespan(app):
    """Refuse deployment with an absent or trivial API key."""
    key = os.environ.get('REPUTATION_API_KEY', '')
    if len(key) < 32:
        raise RuntimeError('REPUTATION_API_KEY must contain at least 32 characters')
    app.state.api_key = key
    yield


app = FastAPI(title='Supplied-edge Reputation Heuristic', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


async def payload(request):
    """Authenticate before reading a streaming body and enforce actual byte count."""
    supplied = request.headers.get('x-api-key', '')
    if not hmac.compare_digest(supplied.encode(), request.app.state.api_key.encode()):
        raise HTTPException(401, 'Invalid API key')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, 'Request too large')
        body.extend(chunk)
    try:
        return json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, 'Invalid JSON') from None


def execute(handler, data):
    """Map shared contract errors onto HTTP client errors."""
    try:
        return handler(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get('/health')
def health():
    """Expose liveness without customer inputs or credentials."""
    return {'status': 'ok', 'version': '1.1.0', 'mode': 'supplied-edge-heuristic'}


@app.post('/score')
async def score(request: Request):
    """Return a heuristic score for a bounded launch batch."""
    return execute(tool_deployer_reputation, await payload(request))


@app.post('/cluster')
async def cluster(request: Request):
    """Return associations for a bounded launch batch."""
    return execute(tool_cluster_launches, await payload(request))
