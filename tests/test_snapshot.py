"""按“渠道 + 日期”复原消费者当时看到的页面（包装正反面、广告话术、代言）。"""

from datetime import date

from src.compliance import IssueCode, MaterialSlot
from util import issue_codes


def test_snapshot_rebuilds_page_at_complaint_date(seeded):
    pages = seeded.snapshot("short-video", date(2026, 5, 10))
    assert [p.version.version_id for p in pages] == ["lozenge-page@v1"]
    page = pages[0]
    assert page.product.name == "蓝芩喉糖"
    # 包装正反面、广告话术、代言内容均可复原
    assert page.claims_in(MaterialSlot.PACKAGE_FRONT)[0].text == "蓝芩喉糖"
    assert "薄荷脑" in page.claims_in(MaterialSlot.PACKAGE_BACK)[0].text
    assert len(page.claims_in(MaterialSlot.AD_COPY)) == 2
    assert "喉糖版口服液" in page.claims_in(MaterialSlot.ENDORSEMENT)[0].text


def test_snapshot_marks_issues_at_complaint_date(seeded):
    page = seeded.snapshot("short-video", date(2026, 5, 10))[0]
    codes = issue_codes(page.evaluation)
    # 旧配方证据已被取代且过期、抽检报告过期、功效表达被新规禁止、审核依据失效
    assert IssueCode.CLAIM_EVIDENCE_SUPERSEDED in codes
    assert IssueCode.CLAIM_EVIDENCE_EXPIRED in codes
    assert IssueCode.CLAIM_PROHIBITED in codes
    assert IssueCode.STALE_APPROVAL in codes


def test_snapshot_shows_page_was_compliant_when_published(seeded):
    page = seeded.snapshot("short-video", date(2025, 6, 1))[0]
    assert page.version.version_id == "lozenge-page@v1"
    assert page.evaluation.ok  # 当时适用的证据与法规下，该页面是合规的


def test_snapshot_tracks_version_replacement_per_channel(seeded):
    old = seeded.snapshot("tmall-flagship", date(2025, 6, 1))
    assert [p.version.version_id for p in old] == ["lozenge-page@v1"]
    new = seeded.snapshot("tmall-flagship", date(2025, 10, 1))
    assert [p.version.version_id for p in new] == ["lozenge-page@v2"]
    # 短视频渠道从未更新，仍是在架的旧版本
    stale = seeded.snapshot("short-video", date(2025, 10, 1))
    assert [p.version.version_id for p in stale] == ["lozenge-page@v1"]


def test_current_evidence_reflects_as_of_date(seeded):
    assert (
        seeded.current_evidence("formula-lozenge", date(2025, 6, 1)).evidence_id
        == "ev-formula-v1"
    )
    assert (
        seeded.current_evidence("formula-lozenge", date(2025, 10, 1)).evidence_id
        == "ev-formula-v2"
    )
