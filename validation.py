"""Shared bounded input contract for every public transport."""
import unicodedata
from ff.cluster import DeployEdge

MAX_EDGES = 1000
MAX_BODY_BYTES = 512_000
MAX_IDENTIFIER_LENGTH = 128
MAX_TIMESTAMP = 253_402_300_799
MAX_LAMPORTS = 18_446_744_073_709_551_615
OUTCOMES = ('rugged', 'rug', 'alive', 'graduated', 'unknown')
FIELDS = frozenset(('deployer', 'funder', 'mint', 'block_time', 'lamports', 'outcome', 'funder_is_cex'))


def identifier(value, name):
    """Accept bounded opaque identifiers, without claiming on-chain validation."""
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f'{name} must be a nonempty string of at most {MAX_IDENTIFIER_LENGTH} characters')
    if any(c.isspace() or unicodedata.category(c) in ('Cc', 'Cs') for c in value):
        raise ValueError(f'{name} cannot contain whitespace, control characters, or Unicode surrogates')
    return value


def integer(value, name, maximum):
    """Require a bounded integer, rejecting boolean and coercion."""
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be an integer between 0 and {maximum}')
    return value


def edge(raw):
    """Validate one launch before constructing a scoring record."""
    if not isinstance(raw, dict) or raw.keys() - FIELDS:
        raise ValueError('Each edge must be an object with only documented fields')
    ids = {name: identifier(raw.get(name), name) for name in ('deployer', 'funder', 'mint')}
    outcome = raw.get('outcome', 'unknown')
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise ValueError('Invalid outcome')
    cex = raw.get('funder_is_cex', False)
    if type(cex) is not bool:
        raise ValueError('funder_is_cex must be boolean')
    timestamp = raw.get('block_time')
    if timestamp is not None:
        timestamp = integer(timestamp, 'block_time', MAX_TIMESTAMP)
    return DeployEdge(**ids, outcome='rug' if outcome == 'rugged' else outcome,
                      funder_is_cex=cex, block_time=timestamp,
                      lamports=integer(raw.get('lamports', 0), 'lamports', MAX_LAMPORTS))


def parse_edges(args):
    """Reject missing, duplicate, or conflicting launches and oversized batches."""
    if not isinstance(args, dict) or set(args) != {'edges'}:
        raise ValueError('Input must be an object containing only edges')
    raw = args['edges']
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_EDGES:
        raise ValueError(f'edges must contain 1..{MAX_EDGES} launches')
    records = [edge(item) for item in raw]
    if len({item.mint for item in records}) != len(records):
        raise ValueError('Duplicate or conflicting mint: supply exactly one record per launch')
    return records


def input_schema():
    """Build a fresh schema matching the runtime input contract."""
    ids = {name: {'type': 'string', 'minLength': 1, 'maxLength': MAX_IDENTIFIER_LENGTH,
                  'pattern': r'^[^\s\u0000-\u001f\u007f-\u009f\ud800-\udfff]+$'} for name in ('deployer', 'funder', 'mint')}
    props = dict(ids, outcome={'type': 'string', 'enum': list(OUTCOMES)},
                 funder_is_cex={'type': 'boolean'},
                 lamports={'type': 'integer', 'minimum': 0, 'maximum': MAX_LAMPORTS},
                 block_time={'type': ['integer', 'null'], 'minimum': 0, 'maximum': MAX_TIMESTAMP})
    descriptions = {
        'deployer': 'Required caller-resolved launch deployer. Opaque identifier, not a verified address or token holder.',
        'funder': 'Required caller-resolved wallet that seeded this deployer before the launch. Never substitute a pool or unknown placeholder.',
        'mint': 'Required launched token identifier, unique within this batch. One edge per mint; not a trading-pair address.',
        'outcome': 'Caller-supplied label; defaults to unknown. rugged maps to rug. Unknown is missing evidence, not safe; labels are not verified.',
        'funder_is_cex': 'Strict boolean, default false. Mark known exchange/infrastructure funders; any true flag prevents that funder joining distinct deployers across this batch.',
        'lamports': 'Nonnegative integer funding amount in lamports, not SOL or a string; defaults to 0. Currently does not affect scoring.',
        'block_time': 'Nonnegative Unix timestamp in seconds or null, not ISO text or milliseconds. Currently does not affect scoring.',
    }
    for name, spec in props.items():
        spec['title'] = name.replace('_', ' ').title()
        spec['description'] = descriptions[name]
    return {'type': 'object', 'additionalProperties': False, 'required': ['edges'],
            'properties': {'edges': {'type': 'array', 'minItems': 1, 'maxItems': MAX_EDGES,
                'description': '1-1000 caller-enriched launches with distinct mints. Required per edge: deployer, funder, mint. No RPC, wallet lookup or label verification; token-only rows are insufficient. Calls are stateless.',
                'items': {'type': 'object', 'additionalProperties': False,
                          'required': ['deployer', 'funder', 'mint'], 'properties': props}}}}
