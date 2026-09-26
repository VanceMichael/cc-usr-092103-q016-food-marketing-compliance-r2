import unittest
from datetime import date
from pathlib import Path

from src.compliance import Disposition, DispositionType, load_store


class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store(Path("fixtures"))

    def test_history_page_kept_after_takedown(self):
        # 下架只追加处置记录，历史发布页面仍可复原
        pubs = self.store.publications_on("CH-LIVE", date(2025, 7, 10))
        self.assertIn("PUB-04", [p.publication_id for p in pubs])

    def test_status_overlay_is_append_only(self):
        self.assertEqual(self.store.publication_status("PUB-04", date(2025, 7, 10)), "在架")
        self.assertEqual(self.store.publication_status("PUB-04", date(2025, 7, 20)), "已下架")

    def test_disposition_seq_monotonic(self):
        seqs = [d.seq for d in self.store.dispositions]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_duplicate_records_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_disposition(
                Disposition(
                    seq=0,
                    disposition_id="D-01",
                    dtype=DispositionType.CLARIFY,
                    material_id="M-LIVE",
                    publication_id=None,
                    reason="重复写入",
                    actor="测试",
                    created_at=date(2025, 7, 19),
                )
            )

    def test_claim_binding_to_unknown_evidence_rejected(self):
        from src.compliance import Claim, ClaimType, EvidenceRef

        with self.assertRaises(ValueError):
            self.store.add_claim(
                Claim(
                    claim_id="C-X",
                    product_id="P-LOZ",
                    claim_type=ClaimType.QUALITY,
                    text="绑定不存在的证据",
                    evidence=(EvidenceRef("E-NOPE", 1),),
                )
            )


if __name__ == "__main__":
    unittest.main()
