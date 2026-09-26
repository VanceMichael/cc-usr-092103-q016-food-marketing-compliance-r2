"""表达合规规则：普通食品与药品功效的边界、证据充分性与审核权限。

核心原则：
- 普通食品不得宣称疾病治疗、预防等药品功效，不得与药品混淆对比；
- 每条表达按其类型绑定必需种类的证据版本，且证据在观察当日有效；
- 注册商标或抽检合格都不能单独替所有宣传放行——审核结论必须
  覆盖素材内每条表达所需的证据种类，审核人角色不得越权。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Claim, ClaimType, EvidenceKind, ProductCategory, Review
from .store import Store

#: 各表达类型放行所需的证据种类
REQUIRED_EVIDENCE: dict[ClaimType, frozenset[EvidenceKind]] = {
    ClaimType.INGREDIENT: frozenset({EvidenceKind.FORMULA}),
    ClaimType.EFFICACY: frozenset({EvidenceKind.FORMULA, EvidenceKind.LEGAL_OPINION}),
    ClaimType.TRADEMARK_USE: frozenset({EvidenceKind.TRADEMARK}),
    ClaimType.QUALITY: frozenset({EvidenceKind.INSPECTION}),
    ClaimType.ENDORSEMENT: frozenset({EvidenceKind.LEGAL_OPINION}),
    ClaimType.COMPARISON: frozenset({EvidenceKind.LEGAL_OPINION}),
}

LEVEL_VIOLATION = "违规"
LEVEL_MISSING = "缺证"
LEVEL_FORBIDDEN = "越权"


@dataclass(frozen=True)
class Finding:
    level: str  # 违规/缺证/越权
    message: str
    claim_id: str | None = None


def _kinds_of(store: Store, refs, on: date | None, findings: list[Finding], claim_id: str) -> set[EvidenceKind]:
    kinds: set[EvidenceKind] = set()
    for ref in refs:
        evidence = store.evidence.get((ref.evidence_id, ref.version))
        if evidence is None:
            findings.append(Finding(LEVEL_MISSING, f"证据 {ref.evidence_id} v{ref.version} 不存在", claim_id))
            continue
        kinds.add(evidence.kind)
        if on is not None and not evidence.covers(on):
            findings.append(
                Finding(LEVEL_MISSING, f"证据《{evidence.title}》v{evidence.version} 在 {on} 不在有效期内", claim_id)
            )
    return kinds


def claim_findings(store: Store, claim: Claim, on: date) -> list[Finding]:
    """检查一条表达在指定日期的合规性。"""
    findings: list[Finding] = []
    product = store.products[claim.product_id]

    if product.category is ProductCategory.FOOD:
        if claim.claim_type is ClaimType.EFFICACY:
            for reg in store.regulations_effective(on):
                hits = [t for t in reg.prohibited_terms if t in claim.text]
                if hits:
                    findings.append(
                        Finding(
                            LEVEL_VIOLATION,
                            f"普通食品功效表述命中《{reg.name}》禁用词：{'、'.join(hits)}",
                            claim.claim_id,
                        )
                    )
        if claim.claim_type is ClaimType.COMPARISON:
            for other in store.products.values():
                if other.category is ProductCategory.DRUG and other.name in claim.text:
                    findings.append(
                        Finding(
                            LEVEL_VIOLATION,
                            f"普通食品不得与药品「{other.name}」作对比或混淆宣传",
                            claim.claim_id,
                        )
                    )

    kinds = _kinds_of(store, claim.evidence, on, findings, claim.claim_id)
    missing = REQUIRED_EVIDENCE[claim.claim_type] - kinds
    if missing:
        names = "、".join(sorted(k.value for k in missing))
        findings.append(
            Finding(
                LEVEL_MISSING,
                f"「{claim.claim_type.value}」缺少{names}类证据；商标或抽检证据不能单独放行此类表达",
                claim.claim_id,
            )
        )
    return findings


def review_findings(store: Store, review: Review) -> list[Finding]:
    """检查一次审核的权限与依据充分性。"""
    findings: list[Finding] = []
    claims = store.material_claims(review.material_id, review.material_version)

    allowed = store.permissions.get(review.role)
    if allowed is None:
        findings.append(Finding(LEVEL_FORBIDDEN, f"未知审核角色：{review.role}"))
    else:
        for claim in claims:
            if claim.claim_type not in allowed:
                findings.append(
                    Finding(
                        LEVEL_FORBIDDEN,
                        f"角色「{review.role}」无权审核「{claim.claim_type.value}」类表达",
                        claim.claim_id,
                    )
                )

    cited_kinds = _kinds_of(store, review.cited_evidence, None, findings, None)
    for claim in claims:
        bound_kinds = {
            store.evidence[(ref.evidence_id, ref.version)].kind
            for ref in claim.evidence
            if (ref.evidence_id, ref.version) in store.evidence
        }
        missing = REQUIRED_EVIDENCE[claim.claim_type] - bound_kinds - cited_kinds
        if missing:
            names = "、".join(sorted(k.value for k in missing))
            findings.append(
                Finding(
                    LEVEL_MISSING,
                    f"审核依据不足以放行「{claim.claim_type.value}」：仍缺少{names}类证据",
                    claim.claim_id,
                )
            )
    return findings
