"""Regression tests for launch accounting, exchange separation and transport safety."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from actor import run_input
from api import app
from deployer_reputation_mcp import tool_deployer_reputation as score, tool_cluster_launches as cluster
from validation import MAX_BODY_BYTES, MAX_EDGES

EDGE = {'deployer': 'd1', 'funder': 'f1', 'mint': 'm1', 'outcome': 'rugged'}
KEY = 'test-only-api-key-with-at-least-32-characters'


class ScoringTests(unittest.TestCase):
    def test_rugged_maps_to_rug_and_launch_count(self):
        result = score({'edges': [EDGE]})['clusters'][0]
        self.assertEqual(result['evidence']['rug_launches'], 1)
        self.assertEqual(result['evidence']['labeled_launches'], 1)
        self.assertEqual(result['evidence']['n_launches'], result['n_launches'])
        self.assertGreater(result['components']['rugs'], 0)

    def test_missing_duplicate_conflicting_mints(self):
        bad = [{k: v for k, v in EDGE.items() if k != 'mint'}, dict(EDGE, mint='')]
        for edge in bad:
            with self.assertRaises(ValueError):
                score({'edges': [edge]})
        for edge in (EDGE, dict(EDGE, deployer='different', outcome='alive')):
            with self.assertRaises(ValueError):
                score({'edges': [EDGE, edge]})

    def test_cex_excluded_globally_but_same_deployer_retained(self):
        edges = [dict(EDGE, funder_is_cex=True), dict(EDGE, deployer='d2', mint='m2')]
        self.assertEqual(cluster({'edges': edges})['n_clusters'], 2)
        edges[1]['deployer'] = 'd1'
        self.assertEqual(cluster({'edges': edges})['n_clusters'], 1)
        edges[0]['funder_is_cex'] = False
        edges[1]['deployer'] = 'd2'
        self.assertEqual(cluster({'edges': edges})['n_clusters'], 1)

    def test_invalid_types_ranges_and_shapes(self):
        for field, value in [('lamports', True), ('lamports', -1), ('lamports', '2'),
                             ('block_time', 1.5), ('outcome', []), ('funder_is_cex', 'false'),
                             ('mint', ' '), ('deployer', 'a'*129), ('unexpected', 1)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                score({'edges': [dict(EDGE, **{field: value})]})
        for data in (None, [], {}, {'edges': []}, {'edges': [None]}, {'edges': 'bad'},
                     {'edges': [EDGE]*(MAX_EDGES+1)}):
            with self.subTest(data=str(data)[:30]), self.assertRaises(ValueError):
                score(data)

    def test_order_and_no_cross_call_mutation(self):
        edges = [EDGE, dict(EDGE, mint='m2', deployer='d2')]
        original = copy.deepcopy(edges)
        self.assertEqual(score({'edges': edges}), score({'edges': edges[::-1]}))
        result = score({'edges': edges})
        result['clusters'][0]['components']['rugs'] = 999
        self.assertLess(score({'edges': edges})['clusters'][0]['score'], 1)
        self.assertEqual(edges, original)

    def test_control_and_surrogate_identifiers_rejected(self):
        for field in ('deployer', 'funder', 'mint'):
            for value in ('\ud800', '\udfff', '\x7f', '\x85', '\x00'):
                with self.subTest(field=field, value=ascii(value)), self.assertRaises(ValueError):
                    score({'edges': [dict(EDGE, **{field: value})]})

    def test_actor_uses_same_scorer(self):
        self.assertEqual(run_input({'edges': [EDGE]}), score({'edges': [EDGE]}))
        self.assertEqual(run_input({'edges': [EDGE], 'operation': 'cluster'}), cluster({'edges': [EDGE]}))
        with self.assertRaises(ValueError):
            run_input({'edges': [EDGE], 'operation': 'missing'})


class TransportTests(unittest.TestCase):
    def test_stdio_recovers_and_notifications_silent(self):
        requests = ['[]', '{', 'null', json.dumps({'jsonrpc':'2.0','method':'ping'}),
                    json.dumps({'jsonrpc':'2.0','id':4,'method':'tools/call','params':[]}),
                    json.dumps({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':[]}}),
                    json.dumps({'jsonrpc':'2.0','id':6,'method':'ping'})]
        process = subprocess.run([sys.executable, 'deployer_reputation_mcp.py'],
                                 input='\n'.join(requests)+'\n', capture_output=True, text=True,
                                 cwd=Path(__file__).parent, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(replies), 6)
        self.assertEqual(replies[-1], {'jsonrpc':'2.0','id':6,'result':{}})
        self.assertEqual(replies[0]['error']['code'], -32600)
        self.assertEqual(replies[1]['error']['code'], -32700)

    def test_stdio_oversize_recovery(self):
        data = ' '* (MAX_BODY_BYTES+10) + '\n' + json.dumps({'jsonrpc':'2.0','id':1,'method':'ping'})+'\n'
        process = subprocess.run([sys.executable, 'deployer_reputation_mcp.py'], input=data,
                                 capture_output=True, text=True, cwd=Path(__file__).parent, timeout=10)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertIn('error', replies[0])
        self.assertEqual(replies[1]['result'], {})

    def test_api_auth_limits_errors_and_success(self):
        with patch.dict(os.environ, {'REPUTATION_API_KEY': KEY}), TestClient(app) as client:
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.post('/score', json={'edges':[EDGE]}).status_code, 401)
            headers = {'X-API-Key':KEY}
            self.assertEqual(client.post('/score', headers=headers, content='{').status_code, 400)
            self.assertEqual(client.post('/score', headers=headers, json=[]).status_code, 422)
            self.assertEqual(client.post('/score', headers=headers, content=b'x'*(MAX_BODY_BYTES+1)).status_code, 413)
            self.assertEqual(client.post('/score', headers=headers, json={'edges':[EDGE]}).json(), score({'edges':[EDGE]}))
            self.assertEqual(client.post('/cluster', headers=headers, json={'edges':[EDGE]}).status_code, 200)

    def test_api_requires_secret_on_start(self):
        with patch.dict(os.environ, {'REPUTATION_API_KEY':''}), self.assertRaises(RuntimeError):
            with TestClient(app):
                pass

    def test_api_surrogate_is_client_error_and_recovers(self):
        with patch.dict(os.environ, {'REPUTATION_API_KEY': KEY}), TestClient(app, raise_server_exceptions=False) as client:
            headers = {'X-API-Key': KEY}
            invalid = json.dumps({'edges': [dict(EDGE, mint='\ud800')]})
            self.assertEqual(client.post('/score', headers=headers, content=invalid).status_code, 422)
            self.assertEqual(client.post('/score', headers=headers, json={'edges': [EDGE]}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
