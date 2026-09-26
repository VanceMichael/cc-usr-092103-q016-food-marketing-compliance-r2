"""影响分析与投诉追踪。

覆盖四类触发场景：
- 旧图回流：旧版本素材再次上线前，复核证据与法规是否已变化；
- 跨渠道复用：审核按渠道授权，复用到未授权渠道会被指出；
- 并行审批：多角色审批的分歧与失效一目了然；
- 法规生效日变化 / 证据版本更替：列出所有受影响的在架素材。

投诉追踪报告把投诉、实际素材、审核依据与后续行动串成一条链，
供管理层逐环核对。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import Approval, Disposition, MaterialVersion, Publication, Regulation
from .service import (
    ComplianceService,
    Evaluation,
    EvidenceStatus,
    IssueCode,
)


@dataclass(frozen=True)
class ImpactItem:
    """一条受影响的在架发布。"""

    publication_id: str
    material_id: str
    version_id: str
    channel_id: str
    claim_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ResurfaceReport:
    """旧图回流 / 跨渠道复用前的复核结果。"""

    evaluation: Evaluation
    superseded_evidence: tuple[EvidenceStatus, ...]
    expired_evidence: tuple[EvidenceStatus, ...]
    new_regulations: tuple[Regulation, ...]
    missing_channel_roles: tuple[str, ...]


@dataclass(frozen=True)
class RoleApprovals:
    """并行审批中某角色的全部决定。"""

    role: str
    required: bool
    records: tuple[Approval, ...]
    latest: Approval | None
    conflict: bool  # 同一版本既被通过又被驳回


def _live(service: ComplianceService, on: date):
    for pub in service.store.publications:
        if service.store.publication_live_at(pub, on):
            yield pub, service.store.versions[pub.version_id]


def impacts_for_evidence(
    service: ComplianceService, series_id: str, on: date
) -> list[ImpactItem]:
    """证据版本更替后，仍绑定旧版本或已失效证据的在架素材。"""
    items = []
    for pub, version in _live(service, on):
        claim_ids: list[str] = []
        reasons: list[str] = []
        for claim in version.claims:
            for evidence_id in claim.evidence_ids:
                evidence = service.store.evidence.get(evidence_id)
                if evidence is None or evidence.series_id != series_id:
                    continue
                current = service.store.current_evidence(series_id, on)
                if not evidence.covers(on):
                    reasons.append(
                        f"表达「{claim.text}」绑定的 {evidence.evidence_id}"
                        f"（{evidence.title}）在 {on} 已失效"
                    )
                    claim_ids.append(claim.claim_id)
                if current is not None and current.evidence_id != evidence.evidence_id:
                    reasons.append(
                        f"表达「{claim.text}」绑定的 {evidence.evidence_id}"
                        f"（{evidence.title}）已被 {current.evidence_id} 取代"
                    )
                    claim_ids.append(claim.claim_id)
        if claim_ids:
            items.append(
                ImpactItem(
                    pub.publication_id,
                    version.material_id,
                    version.version_id,
                    pub.channel_id,
                    tuple(dict.fromkeys(claim_ids)),
                    tuple(reasons),
                )
            )
    return items


def impacts_for_regulation(
    service: ComplianceService, regulation_id: str, on: date | None = None
) -> list[ImpactItem]:
    """法规新版本生效后，表达自生效日起被禁止的在架素材。"""
    regulation = service.store.regulations[regulation_id]
    on = on or regulation.effective_from
    before = on - timedelta(days=1)
    items = []
    for pub, version in _live(service, on):
        material = service.store.materials[version.material_id]
        product = service.store.products[material.product_id]
        claim_ids = []
        reasons = []
        for claim in version.claims:
            hits = [
                h
                for h in service.prohibitions(product.product_type, claim, on)
                if h.regulation.series_id == regulation.series_id
            ]
            previously = service.prohibitions(product.product_type, claim, before)
            if hits and not previously:
                notes = "；".join(h.rule.note for h in hits if h.rule.note)
                reasons.append(
                    f"表达「{claim.text}」自 {on} 起违反"
                    f" {regulation.name}（{notes}）"
                )
                claim_ids.append(claim.claim_id)
        if claim_ids:
            items.append(
                ImpactItem(
                    pub.publication_id,
                    version.material_id,
                    version.version_id,
                    pub.channel_id,
                    tuple(claim_ids),
                    tuple(reasons),
                )
            )
    return items


def resurface_check(
    service: ComplianceService, version_id: str, channel_id: str, on: date
) -> ResurfaceReport:
    """旧版本素材回流或跨渠道复用前的复核。

    汇总该版本在目标渠道、目标日期的全部问题：被取代 / 已失效的证据、
    版本创建后新生效的禁用法规、以及缺失或未授权该渠道的审批角色。
    """
    evaluation = service.evaluate(version_id, channel_id, on)
    version = service.store.versions[version_id]
    material = service.store.materials[version.material_id]
    product = service.store.products[material.product_id]
    superseded: list[EvidenceStatus] = []
    expired: list[EvidenceStatus] = []
    for assessment in evaluation.claims:
        for status in assessment.evidence:
            if status.superseded:
                superseded.append(status)
            if status.status in ("expired", "not_yet_valid"):
                expired.append(status)
    new_regulations = {
        hit.regulation
        for claim in version.claims
        for hit in service.prohibitions(product.product_type, claim, on)
        if hit.regulation.effective_from > version.created_on
    }
    missing_roles = tuple(
        view.role
        for view in evaluation.approvals
        if any(
            issue.code
            in (IssueCode.MISSING_APPROVAL, IssueCode.APPROVAL_CHANNEL_MISMATCH)
            for issue in view.issues
        )
    )
    return ResurfaceReport(
        evaluation,
        tuple(superseded),
        tuple(expired),
        tuple(sorted(new_regulations, key=lambda r: (r.effective_from, r.regulation_id))),
        missing_roles,
    )


def approval_conflicts(
    service: ComplianceService, version_id: str
) -> list[RoleApprovals]:
    """并行审批视图：每个角色的全部决定、最新决定与分歧。"""
    version = service.store.versions[version_id]
    required: set[str] = set()
    for claim in version.claims:
        required |= service.policy.required_roles.get(claim.category, frozenset())
    roles = required | {
        a.role for a in service.store.approvals if a.version_id == version_id
    }
    views = []
    for role in sorted(roles):
        records = tuple(
            a
            for a in service.store.approvals
            if a.version_id == version_id
            and a.role == role
            and a.decided_on >= version.created_on
        )
        latest = (
            max(records, key=lambda a: (a.decided_on, a.approval_id))
            if records
            else None
        )
        decisions = {a.decision for a in records}
        views.append(
            RoleApprovals(role, role in required, records, latest, len(decisions) > 1)
        )
    return views


def trace_complaint(service: ComplianceService, complaint_id: str) -> dict:
    """从投诉一路核对到实际素材、审核依据与后续行动（JSON 可序列化）。"""
    complaint = service.store.complaints[complaint_id]
    matched = []
    material_ids: set[str] = set()
    for pub in service.store.publications:
        if pub.channel_id != complaint.channel_id:
            continue
        if not service.store.publication_live_at(pub, complaint.observed_on):
            continue
        version = service.store.versions[pub.version_id]
        material = service.store.materials[version.material_id]
        if material.product_id != complaint.product_id:
            continue
        material_ids.add(material.material_id)
        product = service.store.products[material.product_id]
        evaluation = service.evaluate(
            version.version_id, pub.channel_id, complaint.observed_on
        )
        matched.append(
            {
                "publication_id": pub.publication_id,
                "channel_id": pub.channel_id,
                "started_on": pub.started_on.isoformat(),
                "material_id": material.material_id,
                "material_title": material.title,
                "product_name": product.name,
                "version_id": version.version_id,
                "claims": [
                    _claim_dict(assessment, complaint.quotes)
                    for assessment in evaluation.claims
                ],
                "approvals": [
                    _approval_dict(a)
                    for a in service.store.approvals
                    if a.version_id == version.version_id
                ],
                "evaluation_issues": [
                    _issue_dict(issue) for issue in evaluation.issues
                ],
            }
        )
    dispositions = [
        d for d in service.store.dispositions if d.material_id in material_ids
    ]
    return {
        "complaint": {
            "complaint_id": complaint.complaint_id,
            "product_id": complaint.product_id,
            "channel_id": complaint.channel_id,
            "observed_on": complaint.observed_on.isoformat(),
            "description": complaint.description,
            "quotes": list(complaint.quotes),
        },
        "matched_publications": matched,
        "dispositions": [_disposition_dict(d) for d in dispositions],
        "follow_ups": [
            _disposition_dict(d)
            for d in dispositions
            if d.created_on >= complaint.observed_on
        ],
    }


def _claim_dict(assessment, quotes) -> dict:
    claim = assessment.claim
    return {
        "claim_id": claim.claim_id,
        "slot": claim.slot.value,
        "text": claim.text,
        "category": claim.category.value,
        "topic": claim.topic.value,
        "matched_quotes": [
            q for q in quotes if q in claim.text or claim.text in q
        ],
        "evidence": [
            {
                "evidence_id": s.evidence.evidence_id,
                "kind": s.evidence.kind.value,
                "version": s.evidence.version,
                "valid_from": s.evidence.valid_from.isoformat(),
                "valid_to": s.evidence.valid_to.isoformat()
                if s.evidence.valid_to
                else None,
                "status": s.status,
                "superseded": s.superseded,
                "current_evidence_id": s.current_evidence_id,
            }
            for s in assessment.evidence
        ],
        "prohibitions": [
            {
                "regulation_id": h.regulation.regulation_id,
                "regulation": h.regulation.name,
                "effective_from": h.regulation.effective_from.isoformat(),
                "note": h.rule.note,
            }
            for h in assessment.prohibitions
        ],
        "issues": [_issue_dict(i) for i in assessment.issues],
    }


def _approval_dict(approval: Approval) -> dict:
    return {
        "approval_id": approval.approval_id,
        "role": approval.role,
        "decision": approval.decision.value,
        "decided_on": approval.decided_on.isoformat(),
        "channels": list(approval.channels),
        "comment": approval.comment,
    }


def _disposition_dict(disposition: Disposition) -> dict:
    return {
        "disposition_id": disposition.disposition_id,
        "material_id": disposition.material_id,
        "kind": disposition.kind.value,
        "created_on": disposition.created_on.isoformat(),
        "actor": disposition.actor,
        "reason": disposition.reason,
        "channel_id": disposition.channel_id,
        "linked_version_id": disposition.linked_version_id,
    }


def _issue_dict(issue) -> dict:
    return {
        "code": issue.code,
        "message": issue.message,
        "claim_id": issue.claim_id,
        "role": issue.role,
    }
