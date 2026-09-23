"""Shared bounded input contract for every public transport."""
import unicodedata
from ff.cluster import DeployEdge, SCORER_VERSION

MAX_EDGES = 1000
MAX_BODY_BYTES = 512_000
MAX_IDENTIFIER_LENGTH = 128
MAX_TIMESTAMP = 253_402_300_799
MAX_LAMPORTS = 18_446_744_073_709_551_615
OUTCOMES = ('rugged', 'rug', 'alive', 'graduated', 'unknown')
FIELDS = frozenset(('deployer', 'funder', 'mint', 'block_time', 'lamports', 'outcome', 'funder_is_cex'))
# Match identifier() in Python and ECMA-262 validators, including a strict end anchor.
IDENTIFIER_PATTERN = (r'^[^\u0000-\u0020\u007f-\u00a0\u1680\u2000-\u200a'
                      r'\u2028-\u2029\u202f\u205f\u3000\ud800-\udfff]+(?![\s\S])')


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
    """Describe the accepted values; duplicate mints and wire bytes are checked at runtime."""
    ids = {name: {'type': 'string', 'minLength': 1, 'maxLength': MAX_IDENTIFIER_LENGTH,
                  'pattern': IDENTIFIER_PATTERN} for name in ('deployer', 'funder', 'mint')}
    props = dict(ids, outcome={'type': 'string', 'enum': list(OUTCOMES), 'default': 'unknown'},
                 funder_is_cex={'type': 'boolean', 'default': False},
                 lamports={'type': 'integer', 'minimum': 0, 'maximum': MAX_LAMPORTS, 'default': 0},
                 block_time={'type': ['integer', 'null'], 'minimum': 0,
                             'maximum': MAX_TIMESTAMP, 'default': None})
    descriptions = {
        'deployer': 'Caller-resolved launch deployer. Opaque, case-sensitive identifier; not address-validated. No whitespace, control characters or Unicode surrogates.',
        'funder': 'Caller-resolved wallet that seeded this deployer before launch. Same identifier rules as deployer. Never substitute a pool or shared unknown placeholder.',
        'mint': 'Launched token identifier, not its trading-pair address. Same identifier rules as deployer. Must be unique across the batch, even when other fields differ.',
        'outcome': 'Caller-supplied label; rugged maps to rug. unknown is excluded from labeled-launch counts and rug-rate denominators. Labels are not verified.',
        'funder_is_cex': 'Strict boolean. Any true flag excludes this funder from joining distinct deployers across the entire batch; same-deployer launches still group. false is not verified non-exchange status.',
        'lamports': 'Integer funding amount in lamports, not SOL, a numeric string or boolean. Validated but not used in grouping or scoring.',
        'block_time': 'Integer Unix timestamp in seconds or null, not ISO text, milliseconds or boolean. Validated but not used in grouping or scoring.',
    }
    examples = {'deployer': ['DemoDeployerA'], 'funder': ['DemoSharedFunder'],
                'mint': ['DemoMintA'], 'outcome': ['unknown', 'rugged'],
                'funder_is_cex': [False, True], 'lamports': [1_000_000_000],
                'block_time': [1_700_000_000, None]}
    for name, spec in props.items():
        spec.update(title=name.replace('_', ' ').title(), description=descriptions[name],
                    examples=examples[name])
    return {'type': 'object', 'additionalProperties': False, 'required': ['edges'],
            'description': f'Caller-enriched snapshot; no datasetId, operation or payload. Each complete stdio request line, including JSON-RPC envelope and newline, must fit {MAX_BODY_BYTES} bytes. Examples use fictional identifiers.',
            'examples': [{'edges': [{'deployer': 'DemoDeployerA', 'funder': 'DemoSharedFunder',
                                    'mint': 'DemoMintA'}]}],
            'properties': {'edges': {'type': 'array', 'minItems': 1, 'maxItems': MAX_EDGES,
                'description': f'1-{MAX_EDGES} launches with distinct mints; required per edge: deployer, funder, mint. Resolve multiple funding observations upstream into one edge per launch. Keep connected groups together: arbitrary batch splits change results. Invalid rows reject the whole batch.',
                'items': {'type': 'object', 'additionalProperties': False,
                          'required': ['deployer', 'funder', 'mint'], 'properties': props}}}}


def _object_schema(properties, description):
    """All declared output fields are present; undeclared fields are rejected."""
    return {'type': 'object', 'description': description, 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _count_schema(description, minimum=0):
    return {'type': 'integer', 'minimum': minimum, 'maximum': MAX_EDGES,
            'description': description}


def _membership_schema():
    properties = {
        'cluster_id': {'type': 'string', 'pattern': r'^CL2-[0-9a-f]{64}(?![\s\S])',
                       'description': 'SHA-256 of sorted role-prefixed deployer/funder membership, not operator identity. Mint/label-only changes keep the ID; membership changes can change it.'},
        'n_launches': _count_schema('Distinct supplied mints in this group.', 1),
    }
    for name in ('deployers', 'funders', 'mints'):
        properties[name] = {'type': 'array', 'minItems': 1, 'maxItems': MAX_EDGES,
                            'uniqueItems': True,
                            'description': f'Sorted unique supplied {name} in this group.',
                            'items': {'type': 'string', 'minLength': 1,
                                      'maxLength': MAX_IDENTIFIER_LENGTH,
                                      'pattern': IDENTIFIER_PATTERN}}
    return _object_schema(properties, 'Funding association within this batch, not common ownership.')


def _components_schema():
    meanings = {
        'serial': 'Saturating excess of deployers per funder above one; weight 0.34.',
        'cadence': 'Saturating launch-count excess above one, not elapsed time; weight 0.16.',
        'fanout': 'Saturating launch-count proxy for breadth; weight 0.12.',
        'cex': 'One if any funder is batch-wide exchange-flagged, otherwise zero; weight 0.08. Not evidence of misconduct.',
        'rugs': 'Wilson lower bound from supplied labels, or zero if none are labeled; weight 0.30. Zero is not evidence of safety.',
    }
    return _object_schema({name: {'type': 'number', 'minimum': 0, 'maximum': 1,
                                  'description': meaning}
                           for name, meaning in meanings.items()},
                          'Unweighted component values, rounded to four decimals.')


def _evidence_schema():
    properties = {
        'n_deployers': _count_schema('Distinct deployers in this group.', 1),
        'n_funders': _count_schema('Distinct funders, including flagged exchange funders.', 1),
        'n_launches': _count_schema('Distinct supplied launches in this group.', 1),
        'deployers_per_funder': {'type': 'number', 'minimum': 1 / MAX_EDGES,
                                'maximum': MAX_EDGES,
                                'description': 'n_deployers / n_funders, rounded to three decimals.'},
        'any_cex': {'type': 'boolean', 'description': 'Any funder is exchange-flagged anywhere in this batch; caller supplied, not verified.'},
        'labeled_launches': _count_schema('Launches labeled rug, rugged, alive or graduated; excludes unknown.'),
        'rug_launches': _count_schema('Launches labeled rug or rugged.'),
        'labelCoverage': {'type': 'number', 'minimum': 0, 'maximum': 1,
                          'description': 'labeled_launches / n_launches, rounded to four decimals.'},
        'notes': {'type': 'array', 'items': {'type': 'string'},
                  'description': 'Caveats about supplied labels, missing or incomplete outcomes, and low not meaning safe.'},
        'observed_rug_rate': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1,
                              'description': 'rug_launches / labeled_launches, rounded to four decimals; null without labels. Not a population estimate.'},
        'rug_rate_wilson_lb': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1,
                              'description': 'Wilson lower bound using z=1.96 on supplied labeled launches, rounded to four decimals; null without labels. Does not validate label quality or sampling.'},
        'rug_evidence': {'type': 'string', 'description': 'labeled when any labels are supplied; otherwise an UNLABELED structural-only warning.'},
    }
    return _object_schema(properties, 'Evidence only from this submitted snapshot; nothing fetched or verified.')


def _output_schema(properties):
    success = _object_schema(properties, 'Successful analysis; MCP isError is false.')
    failure = _object_schema({'error': {'type': 'string', 'minLength': 1,
                                       'description': 'Input rejection reason; correct the batch and retry.'}},
                             'Rejected input; MCP isError is true. No partial analysis returned.')
    return {'type': 'object', 'oneOf': [success, failure],
            'description': 'MCP structuredContent for supported 2025 revisions, also serialized in content[0].text. Protocol-envelope and unknown-tool failures are separate JSON-RPC errors, not analysis objects.'}


def reputation_output_schema():
    """Describe every scoring payload field, nullable evidence, and input-error alternative."""
    membership = _membership_schema()
    scored = _object_schema(dict(membership['properties'],
        score={'type': 'number', 'minimum': 0, 'maximum': 1,
               'description': 'Weighted heuristic sum rounded to four decimals, not a probability, prediction or safety verdict.'},
        band={'type': 'string', 'enum': ['low', 'elevated', 'high'],
              'description': 'high requires score >=0.50 and at least one supplied rug label; otherwise >=0.28 is elevated, else low. Policy thresholds, not calibrated risk.'},
        components=_components_schema(), evidence=_evidence_schema()),
        'Scored funding-association group. Structural signals can be nonzero without labels.')
    return _output_schema({
        'clusters': {'type': 'array', 'minItems': 1, 'maxItems': MAX_EDGES, 'items': scored,
                     'description': 'Groups ordered by descending score; inspect components and label coverage before interpreting the band.'},
        'n_clusters': _count_schema('Number of returned groups.', 1),
        'n_edges': _count_schema('Number of validated supplied launches.', 1),
        'model': {'type': 'string', 'const': 'ff.cluster supplied-edge heuristic'},
        'scorerVersion': {'type': 'string', 'const': SCORER_VERSION,
                          'description': 'Scoring policy version, independent of the MCP server release.'},
        'clusterIdVersion': {'type': 'string', 'const': 'CL2-SHA256'},
        'caveat': {'type': 'string', 'description': 'Uncalibrated, caller-supplied-evidence and attribution limits.'},
    })


def cluster_output_schema():
    """Describe grouping-only results and the same input-error alternative."""
    return _output_schema({
        'clusters': {'type': 'array', 'minItems': 1, 'maxItems': MAX_EDGES,
                     'items': _membership_schema(),
                     'description': 'Groups ordered by descending deployers-per-funder, then launch count, then cluster ID. No score or label evidence.'},
        'n_clusters': _count_schema('Number of returned groups.', 1),
        'clusterIdVersion': {'type': 'string', 'const': 'CL2-SHA256'},
    })
