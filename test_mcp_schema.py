"""Consumer-visible schema and negotiated stdio contracts (test-only jsonschema dependency)."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
from validation import input_schema, parse_edges, MAX_EDGES, MAX_LAMPORTS, MAX_TIMESTAMP

ROOT = Path(__file__).parent
EDGE = {'deployer': 'DemoDeployerA', 'funder': 'DemoFunder', 'mint': 'DemoMintA'}
MIXED = [dict(EDGE, outcome='rugged'),
         dict(EDGE, deployer='DemoDeployerB', mint='DemoMintB'),
         dict(EDGE, deployer='DemoDeployerC', funder='DemoExchange',
              mint='DemoMintC', funder_is_cex=True)]


def request(mid, method, params=None):
    return {'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': params or {}}


def initialize(version):
    return request(1, 'initialize', {'protocolVersion': version, 'capabilities': {},
                                    'clientInfo': {'name': 'schema-regression', 'version': '1'}})


def call(mid, name, edges):
    return request(mid, 'tools/call', {'name': name, 'arguments': {'edges': edges}})


def exchange(requests):
    process = subprocess.run([sys.executable, '-B', str(ROOT / 'deployer_reputation_mcp.py')],
                             input='\n'.join(json.dumps(item) for item in requests) + '\n',
                             capture_output=True, text=True, cwd=ROOT, timeout=10, check=True)
    return {reply['id']: reply for reply in map(json.loads, process.stdout.splitlines())}


class McpSchemaTests(unittest.TestCase):
    def test_modern_outputs_cover_nullable_evidence_and_both_tools(self):
        replies = exchange([initialize('2025-11-25'), request(2, 'tools/list'),
                            call(3, 'deployer_reputation', MIXED), call(4, 'cluster_launches', MIXED)])
        tools = {tool['name']: tool for tool in replies[2]['result']['tools']}
        for mid, name in ((3, 'deployer_reputation'), (4, 'cluster_launches')):
            with self.subTest(tool=name):
                schema = tools[name]['outputSchema']
                Draft202012Validator.check_schema(schema)
                result = replies[mid]['result']
                self.assertFalse(result['isError'])
                payload = result['structuredContent']
                Draft202012Validator(schema).validate(payload)
                self.assertEqual(json.loads(result['content'][0]['text']), payload)
                self.assertEqual(payload['n_clusters'], 2)
        scored = replies[3]['result']['structuredContent']
        evidence = [group['evidence'] for group in scored['clusters']]
        labeled = next(item for item in evidence if item['labeled_launches'])
        unlabeled = next(item for item in evidence if not item['labeled_launches'])
        self.assertEqual(labeled['labelCoverage'], 0.5)
        self.assertEqual(labeled['observed_rug_rate'], 1)
        self.assertIsNone(unlabeled['observed_rug_rate'])
        self.assertIsNone(unlabeled['rug_rate_wilson_lb'])
        self.assertTrue(unlabeled['any_cex'])
        validator = Draft202012Validator(tools['deployer_reputation']['outputSchema'])
        missing_component = copy.deepcopy(scored)
        del missing_component['clusters'][0]['components']['rugs']
        self.assertFalse(validator.is_valid(missing_component))
        invalid_evidence = copy.deepcopy(scored)
        invalid_evidence['clusters'][0]['evidence']['labelCoverage'] = 1.1
        self.assertFalse(validator.is_valid(invalid_evidence))
        fabricated_output = copy.deepcopy(scored)
        fabricated_output['clusters'][0]['prediction'] = 'safe'
        self.assertFalse(validator.is_valid(fabricated_output))
        grouped = replies[4]['result']['structuredContent']
        self.assertFalse(validator.is_valid(grouped))
        self.assertFalse(Draft202012Validator(tools['cluster_launches']['outputSchema']).is_valid(scored))

    def test_rejection_union_and_protocol_error_recover_without_partial_results(self):
        replies = exchange([initialize('2025-11-25'), request(2, 'tools/list'),
                            call(3, 'deployer_reputation', [EDGE, dict(EDGE, outcome='rug')]),
                            call(4, 'cluster_launches', [{'mint': 'DemoMintOnly'}]),
                            call(5, 'not_a_tool', [EDGE]), request(6, 'ping')])
        tools = {tool['name']: tool for tool in replies[2]['result']['tools']}
        for mid, name in ((3, 'deployer_reputation'), (4, 'cluster_launches')):
            result = replies[mid]['result']
            self.assertTrue(result['isError'])
            payload = result['structuredContent']
            self.assertEqual(set(payload), {'error'})
            self.assertIsInstance(payload['error'], str)
            self.assertEqual(json.loads(result['content'][0]['text']), payload)
            validator = Draft202012Validator(tools[name]['outputSchema'])
            validator.validate(payload)
            self.assertFalse(validator.is_valid({'error': None}))
        self.assertEqual(replies[5]['error']['code'], -32602)
        self.assertNotIn('result', replies[5])
        self.assertEqual(replies[6]['result'], {})

    def test_legacy_clients_keep_text_results_and_unstructured_errors(self):
        replies = exchange([initialize('2024-11-05'), request(2, 'tools/list'),
                            call(3, 'deployer_reputation', MIXED),
                            call(4, 'cluster_launches', [EDGE, EDGE]), request(5, 'ping')])
        self.assertEqual(replies[1]['result']['protocolVersion'], '2024-11-05')
        for tool in replies[2]['result']['tools']:
            self.assertNotIn('outputSchema', tool)
            self.assertNotIn('annotations', tool)
        success = replies[3]['result']
        self.assertNotIn('structuredContent', success)
        self.assertFalse(success['isError'])
        self.assertEqual(json.loads(success['content'][0]['text'])['n_edges'], 3)
        failure = replies[4]['result']
        self.assertTrue(failure['isError'])
        self.assertNotIn('structuredContent', failure)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(failure['content'][0]['text'])
        self.assertEqual(replies[5]['result'], {})

    def test_june_revision_and_unsupported_version_negotiate_structured_results(self):
        for requested, expected in (('2025-06-18', '2025-06-18'), ('future-version', '2025-11-25')):
            with self.subTest(requested=requested):
                replies = exchange([initialize(requested), request(2, 'tools/list'),
                                    call(3, 'cluster_launches', [EDGE])])
                self.assertEqual(replies[1]['result']['protocolVersion'], expected)
                tool = next(t for t in replies[2]['result']['tools'] if t['name'] == 'cluster_launches')
                payload = replies[3]['result']['structuredContent']
                Draft202012Validator(tool['outputSchema']).validate(payload)
                self.assertEqual(payload['clusters'][0]['mints'], ['DemoMintA'])

    def test_published_example_runs_through_advertised_contract(self):
        replies = exchange([initialize('2025-11-25'), request(2, 'tools/list')])
        for tool in replies[2]['result']['tools']:
            schema = tool['inputSchema']
            Draft202012Validator.check_schema(schema)
            example = schema['examples'][0]
            Draft202012Validator(schema).validate(example)
            result = exchange([initialize('2025-11-25'),
                               request(2, 'tools/call', {'name': tool['name'], 'arguments': example})])[2]['result']
            self.assertFalse(result['isError'])
            payload = result['structuredContent']
            Draft202012Validator(tool['outputSchema']).validate(payload)
            self.assertEqual(payload['n_clusters'], 1)
            self.assertEqual(payload['clusters'][0]['mints'], ['DemoMintA'])

    def test_identifier_schema_matches_unicode_and_length_rejection_boundaries(self):
        validator = Draft202012Validator(input_schema())
        valid = ['a' * 128, 'Mint\u00f1', 'Mint\U0001f600', 'Mint\ufeff']
        invalid = ['', 'a' * 129, 'Mint\n', 'Mint\u00a0', 'Mint\u0085', '\ud800', '\udfff']
        for value in valid:
            data = {'edges': [dict(EDGE, mint=value)]}
            with self.subTest(value=ascii(value)):
                validator.validate(data)
                self.assertEqual(parse_edges(data)[0].mint, value)
        for value in invalid:
            data = {'edges': [dict(EDGE, mint=value)]}
            with self.subTest(value=ascii(value)):
                self.assertFalse(validator.is_valid(data))
                with self.assertRaises(ValueError):
                    parse_edges(data)

    def test_batch_and_numeric_limits_agree_without_coercion(self):
        validator = Draft202012Validator(input_schema())
        bounded = dict(EDGE, lamports=MAX_LAMPORTS, block_time=MAX_TIMESTAMP)
        data = {'edges': [dict(bounded, mint=f'm{i}') for i in range(MAX_EDGES)]}
        validator.validate(data)
        self.assertEqual(len(parse_edges(data)), MAX_EDGES)
        invalid = [{'edges': data['edges'] + [dict(EDGE, mint='overflow')]},
                   {'edges': [dict(EDGE, lamports=MAX_LAMPORTS + 1)]},
                   {'edges': [dict(EDGE, block_time=MAX_TIMESTAMP + 1)]},
                   {'edges': [dict(EDGE, lamports=True)]},
                   {'edges': [dict(EDGE, funder_is_cex='false')]}]
        for args in invalid:
            with self.subTest(boundary=str(args)[:100]):
                self.assertFalse(validator.is_valid(args))
                with self.assertRaises(ValueError):
                    parse_edges(args)

    def test_runtime_rejects_constraints_json_schema_cannot_express(self):
        validator = Draft202012Validator(input_schema())
        # JSON Schema counts 1.0 as an integer; this interface requires integer JSON tokens.
        # Distinct-mint projection cannot be enforced by uniqueItems on whole edge objects.
        for args in ({'edges': [dict(EDGE, lamports=1.0)]},
                     {'edges': [EDGE, dict(EDGE, outcome='rug')]}):
            validator.validate(args)
            with self.assertRaises(ValueError):
                parse_edges(args)


if __name__ == '__main__':
    unittest.main()
