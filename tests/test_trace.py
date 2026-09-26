import unittest
from pathlib import Path

from src.compliance import load_store, render_trace, trace_complaint


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store(Path("fixtures"))
        cls.trace = trace_complaint(cls.store, "K-01")

    def test_complaint_resolves_to_material_seen_that_day(self):
        self.assertEqual(self.trace["product"], "蓝芩喉糖")
        self.assertEqual(self.trace["category"], "普通食品")
        ids = [item["publication_id"] for item in self.trace["items"]]
        self.assertEqual(ids, ["PUB-04"])
        item = self.trace["items"][0]
        self.assertEqual(item["material_id"], "M-LIVE")
        self.assertEqual(item["status_on_observed"], "在架")

    def test_claims_carry_evidence_versions_and_findings(self):
        item = self.trace["items"][0]
        claims = {c["claim_id"]: c for c in item["claims"]}
        eff2 = claims["C-EFF2"]
        self.assertEqual(
            {(b["evidence_id"], b["version"]) for b in eff2["evidence"]},
            {("E-TM", 1), ("E-INSP", 1)},
        )
        self.assertTrue(any(f["level"] == "违规" for f in eff2["findings"]))

    def test_reviews_and_dispositions_chained(self):
        item = self.trace["items"][0]
        self.assertEqual({r["review_id"] for r in item["reviews"]}, {"R-02", "R-03"})
        dtypes = [d["dtype"] for d in item["dispositions"]]
        self.assertEqual(dtypes, ["下架", "澄清"])
        self.assertTrue(any("K-01" in d["reason"] for d in item["dispositions"]))

    def test_render_for_management(self):
        report = render_trace(self.trace)
        self.assertIn("K-01", report)
        self.assertIn("抗病毒", report)
        self.assertIn("下架", report)


if __name__ == "__main__":
    unittest.main()
