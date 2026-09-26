import unittest
from datetime import date
from pathlib import Path

from src.compliance import claim_findings, load_store, review_findings


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store(Path("fixtures"))

    def test_food_efficacy_hits_prohibited_terms(self):
        claim = self.store.claims["C-EFF2"]
        findings = claim_findings(self.store, claim, date(2025, 7, 10))
        levels = {f.level for f in findings}
        self.assertIn("违规", levels)
        self.assertTrue(any("抗病毒" in f.message for f in findings))

    def test_trademark_and_inspection_cannot_clear_efficacy(self):
        # C-EFF2 只绑定了商标注册证与抽检报告，不能放行功效表述
        claim = self.store.claims["C-EFF2"]
        findings = claim_findings(self.store, claim, date(2025, 7, 10))
        self.assertTrue(any(f.level == "缺证" and "法律意见" in f.message for f in findings))

    def test_expired_evidence_flagged(self):
        # 配料表 v1 有效期至 2025-08-31，旧图上的成分描述在 9 月失效
        claim = self.store.claims["C-ING"]
        findings = claim_findings(self.store, claim, date(2025, 9, 15))
        self.assertTrue(any(f.level == "缺证" and "不在有效期内" in f.message for f in findings))

    def test_food_compared_with_drug_flagged(self):
        claim = self.store.claims["C-CMP"]
        findings = claim_findings(self.store, claim, date(2025, 7, 10))
        self.assertTrue(any(f.level == "违规" and "蓝芩口服液" in f.message for f in findings))

    def test_review_role_overreach_and_weak_basis(self):
        # 质量角色无权审功效表述，且仅凭商标+抽检不能放行
        review = next(r for r in self.store.reviews if r.review_id == "R-01")
        findings = review_findings(self.store, review)
        levels = {f.level for f in findings}
        self.assertIn("越权", levels)
        self.assertIn("缺证", levels)

    def test_legal_role_within_permission(self):
        review = next(r for r in self.store.reviews if r.review_id == "R-02")
        findings = review_findings(self.store, review)
        self.assertFalse(any(f.level == "越权" for f in findings))


if __name__ == "__main__":
    unittest.main()
