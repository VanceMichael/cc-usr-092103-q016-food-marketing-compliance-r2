"""表达-证据绑定与审核规则：注册商标或抽检合格不能单独替所有宣传放行。"""

from datetime import date

import pytest

from src.compliance import (
    ClaimCategory,
    ClaimTopic,
    ComplianceError,
    Decision,
    EvidenceKind,
    IssueCode,
)
from util import approve, issue_codes, make_claim


def _food_version(world, claims, material_id="m-1", created_on=date(2025, 3, 1)):
    world.create_material(material_id, "p-food", "测试素材")
    return world.add_version(material_id, created_on, claims)


def test_unbound_claim_is_flagged(world):
    version = _food_version(world, [make_claim(evidence=())])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.CLAIM_UNBOUND in issue_codes(evaluation)


def test_trademark_alone_cannot_clear_ingredient_claim(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-tm",))
    version = _food_version(world, [claim])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.CLAIM_EVIDENCE_KIND_MISMATCH in issue_codes(evaluation)


def test_trademark_alone_cannot_clear_quality_claim(world):
    claim = make_claim(topic=ClaimTopic.QUALITY, evidence=("ev-tm",))
    version = _food_version(world, [claim])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.CLAIM_EVIDENCE_KIND_MISMATCH in issue_codes(evaluation)


def test_inspection_alone_cannot_clear_efficacy_claim(world):
    claim = make_claim(topic=ClaimTopic.EFFICACY, evidence=("ev-insp",))
    version = _food_version(world, [claim])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.CLAIM_EVIDENCE_KIND_MISMATCH in issue_codes(evaluation)


def test_trademark_clears_brand_claim(world):
    claim = make_claim(topic=ClaimTopic.BRAND, evidence=("ev-tm",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal", "quality"), date(2025, 3, 2))
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert evaluation.ok


def test_inspection_clears_quality_claim_within_validity(world):
    claim = make_claim(topic=ClaimTopic.QUALITY, evidence=("ev-insp",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal", "quality"), date(2025, 3, 2))
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert evaluation.ok


def test_drug_efficacy_category_prohibited_for_ordinary_food(world):
    claim = make_claim(
        category=ClaimCategory.DRUG_EFFICACY,
        topic=ClaimTopic.EFFICACY,
        evidence=("ev-legal",),
    )
    version = _food_version(world, [claim])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.CLAIM_PROHIBITED in issue_codes(evaluation)


def test_expired_evidence_is_flagged(world):
    claim = make_claim(topic=ClaimTopic.QUALITY, evidence=("ev-insp",))
    version = _food_version(world, [claim])
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 8, 1))
    assert IssueCode.CLAIM_EVIDENCE_EXPIRED in issue_codes(evaluation)


def test_superseded_evidence_is_flagged(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = _food_version(world, [claim])
    world.add_evidence(
        "ev-f2", "formula", EvidenceKind.FORMULA, 2, "配方 v2", "", date(2025, 6, 1)
    )
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 6, 15))
    assert IssueCode.CLAIM_EVIDENCE_SUPERSEDED in issue_codes(evaluation)


def test_publish_refused_until_all_parallel_roles_approve(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal",), date(2025, 3, 2))
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.MISSING_APPROVAL in issue_codes(evaluation)
    with pytest.raises(ComplianceError):
        world.publish(version.version_id, "ch-a", date(2025, 3, 10))
    approve(world, version.version_id, ("quality",), date(2025, 3, 3))
    assert world.evaluate(version.version_id, "ch-a", date(2025, 3, 10)).ok


def test_rejection_blocks_publication(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal",), date(2025, 3, 2))
    world.submit_approval(
        version.version_id, "quality", Decision.REJECTED, date(2025, 3, 3), ("ch-a",)
    )
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.REJECTED_APPROVAL in issue_codes(evaluation)
    with pytest.raises(ComplianceError):
        world.publish(version.version_id, "ch-a", date(2025, 3, 10))


def test_approval_scoped_to_other_channel_does_not_cover_reuse(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal", "quality"), date(2025, 3, 2))
    evaluation = world.evaluate(version.version_id, "ch-b", date(2025, 3, 10))
    assert IssueCode.APPROVAL_CHANNEL_MISMATCH in issue_codes(evaluation)


def test_approval_goes_stale_when_evidence_superseded(world):
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = _food_version(world, [claim])
    approve(world, version.version_id, ("legal", "quality"), date(2025, 3, 2))
    world.add_evidence(
        "ev-f2", "formula", EvidenceKind.FORMULA, 2, "配方 v2", "", date(2025, 6, 1)
    )
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 6, 15))
    assert IssueCode.STALE_APPROVAL in issue_codes(evaluation)


def test_drug_efficacy_claim_requires_legal_and_medical(world):
    world.create_material("m-drug", "p-drug", "药品素材")
    claim = make_claim(
        category=ClaimCategory.DRUG_EFFICACY,
        topic=ClaimTopic.EFFICACY,
        evidence=("ev-legal",),
    )
    version = world.add_version("m-drug", date(2025, 3, 1), [claim])
    approve(world, version.version_id, ("legal",), date(2025, 3, 2))
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.MISSING_APPROVAL in issue_codes(evaluation)
    missing_roles = {i.role for i in evaluation.issues if i.code == IssueCode.MISSING_APPROVAL}
    assert missing_roles == {"medical"}
    approve(world, version.version_id, ("medical",), date(2025, 3, 3))
    assert world.evaluate(version.version_id, "ch-a", date(2025, 3, 10)).ok


def test_unknown_role_rejected(world):
    version = _food_version(world, [make_claim(evidence=("ev-legal",))])
    with pytest.raises(ValueError):
        world.submit_approval(
            version.version_id, "intern", Decision.APPROVED, date(2025, 3, 2)
        )
