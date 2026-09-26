"""影响分析：旧图回流、跨渠道复用、并行审批、法规生效日与证据版本变化。"""

from datetime import date

from src.compliance import Decision, IssueCode
from src.compliance.reports import (
    approval_conflicts,
    impacts_for_evidence,
    impacts_for_regulation,
    resurface_check,
)
from util import approve, issue_codes, make_claim
from src.compliance import ClaimTopic


def test_evidence_supersession_flags_live_old_material(seeded):
    items = impacts_for_evidence(seeded, "formula-lozenge", date(2025, 10, 1))
    hit = {(i.version_id, i.channel_id) for i in items}
    # 短视频渠道仍在架的旧版本绑定了被取代的配方
    assert ("lozenge-page@v1", "short-video") in hit
    # 旗舰店已换绑新配方，不受影响
    assert ("lozenge-page@v2", "tmall-flagship") not in hit


def test_evidence_expiry_flags_all_channels_still_binding_it(seeded):
    items = impacts_for_evidence(seeded, "inspection-lozenge", date(2026, 1, 15))
    hit = {(i.version_id, i.channel_id) for i in items}
    assert ("lozenge-page@v1", "short-video") in hit
    assert ("lozenge-page@v2", "tmall-flagship") in hit


def test_regulation_change_flags_materials_live_at_effective_date(seeded):
    items = impacts_for_regulation(seeded, "reg-ad-2026")
    hit = {(i.version_id, i.channel_id): i for i in items}
    assert ("lozenge-page@v1", "short-video") in hit
    assert ("lozenge-page@v2", "tmall-flagship") in hit
    # 受影响的是功效类表达；品牌与配料表达不受该新规影响
    v1_claims = hit[("lozenge-page@v1", "short-video")].claim_ids
    assert "c-eff-ad" in v1_claims and "c-endorse" in v1_claims
    assert "c-brand-front" not in v1_claims


def test_resurface_check_for_old_version_on_new_channel(seeded):
    # 旧图回流 + 跨渠道复用：把 v1 重新投放到连锁药店
    report = resurface_check(
        seeded, "lozenge-page@v1", "retail-pharmacy", date(2026, 6, 1)
    )
    assert not report.evaluation.ok
    # 审核范围不含该渠道
    assert set(report.missing_channel_roles) == {"legal", "quality"}
    # 配方证据已被取代、抽检报告已过期
    superseded_ids = {s.evidence.evidence_id for s in report.superseded_evidence}
    expired_ids = {s.evidence.evidence_id for s in report.expired_evidence}
    assert "ev-formula-v1" in superseded_ids
    assert "ev-inspection-2025" in expired_ids
    # 版本创建后新生效的法规被点名
    assert [r.regulation_id for r in report.new_regulations] == ["reg-ad-2026"]


def test_resurface_check_clean_for_current_version(world):
    world.create_material("m-1", "p-food", "素材")
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = world.add_version("m-1", date(2025, 3, 1), [claim])
    approve(world, version.version_id, ("legal", "quality"), date(2025, 3, 2))
    report = resurface_check(world, version.version_id, "ch-a", date(2025, 3, 10))
    assert report.evaluation.ok
    assert report.new_regulations == ()
    assert report.missing_channel_roles == ()


def test_parallel_approval_conflicts_are_visible(world):
    world.create_material("m-1", "p-food", "素材")
    claim = make_claim(topic=ClaimTopic.INGREDIENT, evidence=("ev-f1",))
    version = world.add_version("m-1", date(2025, 3, 1), [claim])
    approve(world, version.version_id, ("legal",), date(2025, 3, 2))
    world.submit_approval(
        version.version_id, "quality", Decision.REJECTED, date(2025, 3, 3), ("ch-a",)
    )
    world.submit_approval(
        version.version_id, "quality", Decision.APPROVED, date(2025, 3, 4), ("ch-a",)
    )
    views = {v.role: v for v in approval_conflicts(world, version.version_id)}
    assert views["quality"].conflict  # 同一角色先后驳回又通过，分歧留痕
    assert views["quality"].latest.decision is Decision.APPROVED
    assert not views["legal"].conflict
    assert views["legal"].required and views["quality"].required
    # 最新决定为通过后，评估不再阻塞
    evaluation = world.evaluate(version.version_id, "ch-a", date(2025, 3, 10))
    assert IssueCode.REJECTED_APPROVAL not in issue_codes(evaluation)
