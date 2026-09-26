"""投诉追踪：从投诉一路核对到实际素材、审核依据和后续行动。"""

import json
from datetime import date

from src.compliance import DispositionKind
from src.compliance.reports import trace_complaint


def test_trace_links_complaint_to_material_evidence_and_approvals(seeded):
    report = trace_complaint(seeded, "cmp-001")
    complaint = report["complaint"]
    assert complaint["observed_on"] == "2026-05-10"
    assert complaint["channel_id"] == "short-video"

    matched = report["matched_publications"]
    assert len(matched) == 1
    page = matched[0]
    assert page["version_id"] == "lozenge-page@v1"
    assert page["product_name"] == "蓝芩喉糖"

    claims = {c["claim_id"]: c for c in page["claims"]}
    # 消费者复述的原文定位到具体表达
    assert claims["c-endorse"]["matched_quotes"] == ["就像随身带的喉糖版口服液"]
    assert claims["c-eff-ad"]["matched_quotes"] == ["清咽利喉"]
    # 每条表达绑定的证据版本及其在投诉日的状态
    ingredient_evidence = claims["c-ingredients-back"]["evidence"][0]
    assert ingredient_evidence["evidence_id"] == "ev-formula-v1"
    assert ingredient_evidence["status"] == "expired"
    assert ingredient_evidence["superseded"] is True
    assert ingredient_evidence["current_evidence_id"] == "ev-formula-v2"
    quality_evidence = claims["c-quality-ad"]["evidence"][0]
    assert quality_evidence["status"] == "expired"
    # 当时适用的法规边界
    assert claims["c-endorse"]["prohibitions"][0]["regulation_id"] == "reg-ad-2026"
    assert claims["c-brand-front"]["prohibitions"] == []
    # 审核依据：谁、何时、授权哪些渠道
    approvers = {a["role"] for a in page["approvals"]}
    assert approvers == {"legal", "quality"}
    assert all(a["decision"] == "approved" for a in page["approvals"])
    # 投诉日页面的问题清单非空（审核依据已失效）
    assert page["evaluation_issues"]


def test_trace_report_is_json_serializable(seeded):
    report = trace_complaint(seeded, "cmp-001")
    json.dumps(report, ensure_ascii=False)


def test_follow_ups_accumulate_without_erasing_history(seeded):
    seeded.record_disposition(
        "lozenge-page",
        DispositionKind.TAKEDOWN,
        date(2026, 5, 12),
        "法务-林某",
        "投诉成立，短视频渠道下架",
        channel_id="short-video",
    )
    seeded.record_disposition(
        "lozenge-page",
        DispositionKind.CLARIFICATION,
        date(2026, 5, 13),
        "公关-赵某",
        "发布澄清声明",
    )
    report = trace_complaint(seeded, "cmp-001")
    follow_up_kinds = [d["kind"] for d in report["follow_ups"]]
    assert follow_up_kinds == ["takedown", "clarification"]
    # 历史页面仍可核对：投诉当日看到的仍是 v1
    assert report["matched_publications"][0]["version_id"] == "lozenge-page@v1"
    assert seeded.snapshot("short-video", date(2026, 5, 10))
