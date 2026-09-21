"""Integration input tests: edges via dataset reference (datasetId / payload)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import actor
import dataset_input


class DatasetIdTests(unittest.TestCase):
    def test_explicit_and_payload_resolution(self):
        self.assertEqual(dataset_input.dataset_id_from({'datasetId': 'abc1234567'}), 'abc1234567')
        self.assertEqual(dataset_input.dataset_id_from(
            {'payload': {'resource': {'defaultDatasetId': 'xyz9876543'}}}), 'xyz9876543')
        self.assertIsNone(dataset_input.dataset_id_from({'payload': {'resource': {}}}))
        with self.assertRaises(ValueError):
            dataset_input.dataset_id_from({'datasetId': 42})

    def test_id_shape_enforced(self):
        for bad in ['not a dataset!', 'short', '', None]:
            with self.assertRaises(ValueError, msg=str(bad)):
                dataset_input.fetch_dataset_records(bad)


class IntegrationRunTests(unittest.TestCase):
    EDGES = [{'deployer': 'd1', 'funder': 'f1', 'mint': 'm1', 'outcome': 'rugged'},
             {'deployer': 'd2', 'funder': 'f1', 'mint': 'm2', 'outcome': 'rugged'}]

    def test_edges_via_dataset_id(self):
        with patch.object(actor, 'fetch_dataset_records', return_value=self.EDGES):
            result = actor.run_input({'datasetId': 'abc1234567'})
        self.assertEqual(result['n_edges'], 2)
        self.assertEqual(result['n_clusters'], 1)

    def test_edges_via_payload(self):
        with patch.object(actor, 'fetch_dataset_records', return_value=self.EDGES):
            result = actor.run_input({'payload': {'resource': {'defaultDatasetId': 'abc1234567'}}})
        self.assertEqual(result['n_clusters'], 1)

    def test_inline_edges_win_over_dataset(self):
        with patch.object(actor, 'fetch_dataset_records', side_effect=AssertionError('must not fetch')):
            result = actor.run_input({'edges': self.EDGES, 'datasetId': 'abc1234567'})
        self.assertEqual(result['n_edges'], 2)

    def test_unknown_keys_still_rejected(self):
        with self.assertRaises(ValueError):
            actor.run_input({'edges': self.EDGES, 'webhook': 'https://evil.example'})
        with self.assertRaises(ValueError):
            actor.run_input({'edges': self.EDGES, 'url': 'https://evil.example'})

    def test_missing_edges_and_dataset_fails(self):
        with self.assertRaises(ValueError):
            actor.run_input({'operation': 'score'})


if __name__ == '__main__':
    unittest.main()
