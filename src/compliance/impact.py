"""影响面分析：旧图回流、跨渠道复用、并行审批、法规生效日变化。

每当外部条件变化，指出哪些已发布素材受到影响、原因是什么，
供管理层决定下架、澄清或修改。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import ClaimType
from .rules import claim_findings
from .store import Store

KIND_REGULATION = "法规生效日变化"
KIND_RESURFACE = "旧图回流"
KIND_REUSE = "跨渠道复用"
KIND_PARALLEL = "并行审批"


@dataclass(frozen=True)
class Impact:
    kind: str
    material_id: str
    material_version: int
    publication_id: str | None
    channel_id: str | None
    status: str | None  # 该发布在观察日的状态（在架/已下架/已结束）
    detail: str


def impacts_from_regulation(store: Store, regulation_id: str) -> list[Impact]:
    """法规（含生效日调整）落地时，仍覆盖生效日的已发布素材。"""
    reg = store.regulations[regulation_id]
    on = reg.effective_from
    impacts: list[Impact] = []
    for pub in store.publications:
        if not (pub.start <= on and (pub.end is None or on <= pub.end)):
            continue
        status = store.publication_status(pub.publication_id, on)
        for claim in store.material_claims(pub.material_id, pub.material_version):
            hits = [t for t in reg.prohibited_terms if t in claim.text]
            if hits:
                impacts.append(
                    Impact(
                        KIND_REGULATION,
                        pub.material_id,
                        pub.material_version,
                        pub.publication_id,
                        pub.channel_id,
                        status,
                        f"《{reg.name}》{on} 生效，表达「{claim.text}」命中禁用词：{'、'.join(hits)}，需按新法规复核审核依据",
                    )
                )
    return impacts


def impacts_from_resurface(store: Store, content_hash: str, on: date) -> list[Impact]:
    """同一内容（旧图/旧话术）在观察日仍在投放时，检查版本与证据时效。"""
    versions = [m for m in store.materials.values() if m.content_hash == content_hash]
    impacts: list[Impact] = []
    for material in versions:
        latest = store.latest_material_version(material.material_id)
        for pub in store.publications_for_material(material.material_id, material.version):
            if not (pub.start <= on and (pub.end is None or on <= pub.end)):
                continue
            status = store.publication_status(pub.publication_id, on)
            if material.version < latest:
                impacts.append(
                    Impact(
                        KIND_RESURFACE,
                        material.material_id,
                        material.version,
                        pub.publication_id,
                        pub.channel_id,
                        status,
                        f"旧图回流：{material.material_id} 已存在 v{latest}，{on} 仍在投放 v{material.version}",
                    )
                )
            for claim in store.material_claims(material.material_id, material.version):
                for finding in claim_findings(store, claim, on):
                    impacts.append(
                        Impact(
                            KIND_RESURFACE,
                            material.material_id,
                            material.version,
                            pub.publication_id,
                            pub.channel_id,
                            status,
                            f"旧图回流：[{finding.level}] {finding.message}",
                        )
                    )
    return impacts


def impacts_from_channel_reuse(
    store: Store, material_id: str, version: int, channel_id: str, on: date
) -> list[Impact]:
    """素材复用到新渠道前，检查渠道限制与表达在当日的合规性。"""
    channel = store.channels[channel_id]
    impacts: list[Impact] = []
    for claim in store.material_claims(material_id, version):
        if claim.claim_type in channel.restricted_claim_types:
            impacts.append(
                Impact(
                    KIND_REUSE,
                    material_id,
                    version,
                    None,
                    channel_id,
                    None,
                    f"渠道「{channel.name}」限制「{claim.claim_type.value}」类表达：「{claim.text}」",
                )
            )
        for finding in claim_findings(store, claim, on):
            impacts.append(
                Impact(
                    KIND_REUSE,
                    material_id,
                    version,
                    None,
                    channel_id,
                    None,
                    f"复用到「{channel.name}」时：[{finding.level}] {finding.message}",
                )
            )
    return impacts


def parallel_review_conflicts(store: Store) -> list[Impact]:
    """同一素材版本被并行审批且结论冲突时指出。"""
    groups: dict[tuple[str, int], list] = {}
    for review in store.reviews:
        groups.setdefault((review.material_id, review.material_version), []).append(review)
    impacts: list[Impact] = []
    for (material_id, version), reviews in groups.items():
        decisions = {r.decision for r in reviews}
        if len(reviews) > 1 and len(decisions) > 1:
            detail = "；".join(f"{r.reviewer}（{r.role}）{r.decision}" for r in reviews)
            impacts.append(
                Impact(
                    KIND_PARALLEL,
                    material_id,
                    version,
                    None,
                    None,
                    None,
                    f"同一素材版本并行审批结论冲突：{detail}，需以有权角色的最终结论为准",
                )
            )
    return impacts
