import unittest
from datetime import date
from pathlib import Path

from src.compliance import (
    impacts_from_channel_reuse,
    impacts_from_regulation,
    impacts_from_resurface,
    load_store,
    parallel_review_conflicts,
)


class ImpactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store(Path("fixtures"))

    def test_regulation_change_flags_published_materials(self):
        impacts = impacts_from_regulation(self.store, "REG-02")
        by_pub = {}
        for impact in impacts:
            by_pub.setdefault(impact.publication_id, impact)
        # 包装背面 v2 含“缓解咽喉不适”，新法规生效时仍在架
        self.assertIn("PUB-03", by_pub)
        self.assertEqual(by_pub["PUB-03"].status, "在架")
        # 直播话术已下架，仍被指出但状态可区分
        self.assertIn("PUB-04", by_pub)
        self.assertEqual(by_pub["PUB-04"].status, "已下架")
        # 包装正面不含禁用词，不受影响
        self.assertNotIn("PUB-01", by_pub)

    def test_resurface_flags_stale_version_and_expired_evidence(self):
        impacts = impacts_from_resurface(self.store, "img-back-v1", date(2025, 9, 15))
        details = [i.detail for i in impacts]
        self.assertTrue(any("已存在 v2" in d for d in details))
        self.assertTrue(any("不在有效期内" in d for d in details))
        self.assertTrue(all(i.kind == "旧图回流" for i in impacts))

    def test_channel_reuse_flags_restriction_and_violation(self):
        impacts = impacts_from_channel_reuse(self.store, "M-POSTER", 1, "CH-LIVE", date(2025, 9, 10))
        details = [i.detail for i in impacts]
        self.assertTrue(any("对比宣传" in d and "限制" in d for d in details))
        self.assertTrue(any("违规" in d for d in details))

    def test_parallel_review_conflict_detected(self):
        conflicts = parallel_review_conflicts(self.store)
        self.assertTrue(any(i.material_id == "M-LIVE" and i.material_version == 1 for i in conflicts))


if __name__ == "__main__":
    unittest.main()
