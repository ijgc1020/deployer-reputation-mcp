"""Ensure invalid or withheld dataset delivery cannot expose an alternate result."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from actor import main, run_input

EXAMPLE = {'operation': 'score', 'edges': [
    {'deployer': 'ExampleDeployer', 'funder': 'ExampleFunder',
     'mint': 'ExampleMint', 'outcome': 'unknown', 'funder_is_cex': False}]}


def fake_actor(data):
    """Return a monitored SDK boundary without real storage or charging."""
    actor = MagicMock()
    actor.get_input = AsyncMock(return_value=data)
    actor.push_data = AsyncMock()
    actor.set_value = AsyncMock()
    return actor


def execute(actor):
    """Execute the actual Actor entry point using a local SDK stand-in."""
    with patch.dict('sys.modules', {'apify': SimpleNamespace(Actor=actor)}):
        asyncio.run(main())


class DeliveryTests(unittest.TestCase):
    def test_score_and_cluster_deliver_unchanged_single_result(self):
        for operation in ('score', 'cluster'):
            data = dict(EXAMPLE, operation=operation)
            actor = fake_actor(data)
            execute(actor)
            actor.push_data.assert_awaited_once_with(run_input(data))
            actor.set_value.assert_not_called()

    def test_push_failure_leaves_no_alternate_output(self):
        actor = fake_actor(EXAMPLE)
        actor.push_data.side_effect = RuntimeError('dataset storage or budget rejection')
        with self.assertRaises(RuntimeError):
            execute(actor)
        actor.set_value.assert_not_called()

    def test_silent_withholding_has_no_alternate_output(self):
        actor = fake_actor(EXAMPLE)
        actor.push_data.return_value = None
        execute(actor)
        actor.push_data.assert_awaited_once()
        actor.set_value.assert_not_called()

    def test_invalid_batch_never_reaches_storage(self):
        actor = fake_actor({'edges': [dict(EXAMPLE['edges'][0], mint='\ud800')]})
        with self.assertRaises(ValueError):
            execute(actor)
        actor.push_data.assert_not_called()
        actor.set_value.assert_not_called()

    def test_output_schema_only_advertises_dataset(self):
        schema = json.loads((Path(__file__).parent / '.actor/output_schema.json').read_text())
        self.assertEqual(set(schema['properties']), {'dataset'})
        self.assertEqual(schema['properties']['dataset']['template'], '{{links.apiDefaultDatasetUrl}}/items')


if __name__ == '__main__':
    unittest.main()
