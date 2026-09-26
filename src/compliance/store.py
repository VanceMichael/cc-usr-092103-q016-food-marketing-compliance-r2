"""只追加的合规记录库。

所有记录只追加不修改：下架、澄清、修改均体现为新的处置记录，
历史发布页面（Publication）保持原样，可按日期复原任一渠道当时
实际展示的素材版本。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from .models import (
    Channel,
    Claim,
    ClaimType,
    Complaint,
    Disposition,
    DispositionType,
    Evidence,
    Material,
    Product,
    Publication,
    Regulation,
    Review,
)


def _put(table: dict, key, record) -> None:
    if key in table:
        raise ValueError(f"记录已存在，不允许改写：{key}")
    table[key] = record


class Store:
    """领域记录的唯一入口。"""

    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self.evidence: dict[tuple[str, int], Evidence] = {}
        self.claims: dict[str, Claim] = {}
        self.materials: dict[tuple[str, int], Material] = {}
        self.channels: dict[str, Channel] = {}
        self.publications: list[Publication] = []
        self.reviews: list[Review] = []
        self.dispositions: list[Disposition] = []
        self.complaints: dict[str, Complaint] = {}
        self.regulations: dict[str, Regulation] = {}
        self.permissions: dict[str, frozenset[ClaimType]] = {}
        self._pub_index: dict[str, Publication] = {}

    # ---- 登记（只追加） ----

    def add_product(self, product: Product) -> None:
        _put(self.products, product.product_id, product)

    def add_evidence(self, evidence: Evidence) -> None:
        _put(self.evidence, (evidence.evidence_id, evidence.version), evidence)

    def add_claim(self, claim: Claim) -> None:
        if claim.product_id not in self.products:
            raise ValueError(f"表达指向未知产品：{claim.product_id}")
        for ref in claim.evidence:
            if (ref.evidence_id, ref.version) not in self.evidence:
                raise ValueError(f"表达 {claim.claim_id} 绑定了不存在的证据版本：{ref}")
        _put(self.claims, claim.claim_id, claim)

    def add_material(self, material: Material) -> None:
        for cid in material.claim_ids:
            if cid not in self.claims:
                raise ValueError(f"素材 {material.material_id} 引用了未知表达：{cid}")
        _put(self.materials, (material.material_id, material.version), material)

    def add_channel(self, channel: Channel) -> None:
        _put(self.channels, channel.channel_id, channel)

    def add_publication(self, publication: Publication) -> None:
        if (publication.material_id, publication.material_version) not in self.materials:
            raise ValueError(f"发布指向未知素材版本：{publication.material_id} v{publication.material_version}")
        if publication.channel_id not in self.channels:
            raise ValueError(f"发布指向未知渠道：{publication.channel_id}")
        _put(self._pub_index, publication.publication_id, publication)
        self.publications.append(publication)

    def add_review(self, review: Review) -> None:
        if (review.material_id, review.material_version) not in self.materials:
            raise ValueError(f"审核指向未知素材版本：{review.material_id} v{review.material_version}")
        if any(r.review_id == review.review_id for r in self.reviews):
            raise ValueError(f"审核记录已存在：{review.review_id}")
        self.reviews.append(review)

    def add_disposition(self, disposition: Disposition) -> Disposition:
        """追加处置记录并分配递增序号；历史页面不受影响。"""
        if any(d.disposition_id == disposition.disposition_id for d in self.dispositions):
            raise ValueError(f"处置记录已存在：{disposition.disposition_id}")
        if (disposition.material_id, 1) not in self.materials and not any(
            mid == disposition.material_id for (mid, _) in self.materials
        ):
            raise ValueError(f"处置指向未知素材：{disposition.material_id}")
        if disposition.publication_id is not None and disposition.publication_id not in self._pub_index:
            raise ValueError(f"处置指向未知发布：{disposition.publication_id}")
        stored = replace(disposition, seq=len(self.dispositions) + 1)
        self.dispositions.append(stored)
        return stored

    def add_complaint(self, complaint: Complaint) -> None:
        if complaint.product_id not in self.products:
            raise ValueError(f"投诉指向未知产品：{complaint.product_id}")
        if complaint.channel_id not in self.channels:
            raise ValueError(f"投诉指向未知渠道：{complaint.channel_id}")
        _put(self.complaints, complaint.complaint_id, complaint)

    def add_regulation(self, regulation: Regulation) -> None:
        _put(self.regulations, regulation.regulation_id, regulation)

    def set_permissions(self, permissions: dict[str, frozenset[ClaimType]]) -> None:
        self.permissions = dict(permissions)

    # ---- 查询 ----

    def material_claims(self, material_id: str, version: int) -> list[Claim]:
        material = self.materials[(material_id, version)]
        return [self.claims[cid] for cid in material.claim_ids]

    def latest_material_version(self, material_id: str) -> int:
        versions = [v for (mid, v) in self.materials if mid == material_id]
        if not versions:
            raise ValueError(f"未知素材：{material_id}")
        return max(versions)

    def publications_on(self, channel_id: str, on: date) -> list[Publication]:
        """按投放窗口复原某渠道当日展示的素材版本（历史原样，不看处置）。"""
        return [
            p
            for p in self.publications
            if p.channel_id == channel_id and p.start <= on and (p.end is None or on <= p.end)
        ]

    def publications_for_material(self, material_id: str, version: int) -> list[Publication]:
        return [
            p
            for p in self.publications
            if p.material_id == material_id and p.material_version == version
        ]

    def publication_status(self, publication_id: str, on: date) -> str:
        """投放窗口叠加处置记录后的当日状态；处置只追加，状态可重算。"""
        pub = self._pub_index[publication_id]
        if on < pub.start:
            return "未上架"
        if pub.end is not None and on > pub.end:
            return "已结束"
        status = "在架"
        for d in self.dispositions:
            if d.publication_id != publication_id or d.created_at > on:
                continue
            if d.dtype is DispositionType.TAKEDOWN:
                status = "已下架"
            elif d.dtype is DispositionType.REPUBLISH:
                status = "在架"
        return status

    def live_publications(self, on: date) -> list[Publication]:
        return [p for p in self.publications if self.publication_status(p.publication_id, on) == "在架"]

    def reviews_for(self, material_id: str, version: int) -> list[Review]:
        return [
            r
            for r in self.reviews
            if r.material_id == material_id and r.material_version == version
        ]

    def dispositions_for(
        self, material_id: str | None = None, publication_id: str | None = None
    ) -> list[Disposition]:
        return [
            d
            for d in self.dispositions
            if (material_id is None or d.material_id == material_id)
            and (publication_id is None or d.publication_id == publication_id)
        ]

    def regulations_effective(self, on: date) -> list[Regulation]:
        return [r for r in self.regulations.values() if r.effective_from <= on]
