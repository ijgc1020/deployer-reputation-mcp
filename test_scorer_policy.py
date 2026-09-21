"""Regressions for membership IDs, label policy, and reconciled exchange evidence."""
import copy
import unittest
from ff.cluster import DeployEdge, cluster_by_funder
from deployer_reputation_mcp import tool_deployer_reputation as score, tool_cluster_launches as cluster


def rows(n, outcome="unknown"):
    return [dict(deployer=f"d{i}", funder="f", mint=f"m{i}", outcome=outcome) for i in range(n)]


class ScorerPolicyTests(unittest.TestCase):
    def test_delimiter_collision_and_order(self):
        edges = [dict(deployer="a", funder="b|F:c", mint="m1"),
                 dict(deployer="a|F:b", funder="c", mint="m2")]
        result = cluster({"edges": edges})
        ids = [c["cluster_id"] for c in result["clusters"]]
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(i.startswith("CL2-") and len(i) == 68 for i in ids))
        self.assertEqual(result, cluster({"edges": edges[::-1]}))

    def test_membership_changes_id_labels_and_mints_do_not(self):
        edge = rows(1)[0]
        cid = lambda e: cluster({"edges": [e]})["clusters"][0]["cluster_id"]
        self.assertEqual(cid(edge), cid(dict(edge, mint="new", outcome="rug")))
        self.assertNotEqual(cid(edge), cid(dict(edge, deployer="new")))
        self.assertNotEqual(cid(edge), cid(dict(edge, funder="new")))

    def test_unknown_and_good_only_not_high_numeric_score_unchanged(self):
        for outcome in ("unknown", "alive"):
            c = score({"edges": rows(14, outcome)})["clusters"][0]
            self.assertAlmostEqual(c["score"], 0.501)
            self.assertEqual(c["band"], "elevated")
            self.assertEqual(c["evidence"]["rug_launches"], 0)
        self.assertEqual(score({"edges": rows(14, "rug")})["clusters"][0]["band"], "high")

    def test_global_cex_consistent_and_inputs_unchanged(self):
        edges = rows(2)
        edges[0]["funder_is_cex"] = True
        before = copy.deepcopy(edges)
        result = score({"edges": edges})
        self.assertEqual(result["n_clusters"], 2)
        for c in result["clusters"]:
            self.assertTrue(c["evidence"]["any_cex"])
            self.assertEqual(c["components"]["cex"], 1.0)
            self.assertAlmostEqual(c["score"], 0.0971)
        self.assertEqual(edges, before)
        originals = [DeployEdge(**e) for e in edges]
        groups = cluster_by_funder(originals)
        self.assertFalse(originals[1].funder_is_cex)
        self.assertTrue(all(e.funder_is_cex for g in groups for e in g.edges))

    def test_coverage_notes_versions_and_output_isolation(self):
        edges = rows(2)
        result = score({"edges": edges})
        c = result["clusters"][0]
        self.assertEqual(c["evidence"]["labelCoverage"], 0)
        self.assertIn("Insufficient", " ".join(c["evidence"]["notes"]))
        self.assertIn("Low does not mean safe", " ".join(c["evidence"]["notes"]))
        self.assertEqual(result["scorerVersion"], "2.0.0")
        self.assertEqual(result["clusterIdVersion"], "CL2-SHA256")
        c["evidence"]["notes"].append("mutated")
        self.assertNotIn("mutated", score({"edges": edges})["clusters"][0]["evidence"]["notes"])
        edges[0]["outcome"] = "alive"
        c = score({"edges": edges})["clusters"][0]
        self.assertEqual(c["evidence"]["labelCoverage"], 0.5)
        self.assertIn("Incomplete", " ".join(c["evidence"]["notes"]))


if __name__ == "__main__":
    unittest.main()
