"""只增不删的记录仓库。

所有实体一经写入即不可修改、不可删除；状态变化（如下线、处置）一律通过
追加新记录表达，保证任何历史时点都可以被完整复原。
"""

from __future__ import annotations

from datetime import date

from .models import (
    Approval,
    Channel,
    Complaint,
    Disposition,
    Evidence,
    Material,
    MaterialVersion,
    Product,
    Publication,
    PublicationEnd,
    Regulation,
)


class ComplianceStore:
    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self.channels: dict[str, Channel] = {}
        self.evidence: dict[str, Evidence] = {}
        self.regulations: dict[str, Regulation] = {}
        self.materials: dict[str, Material] = {}
        self.versions: dict[str, MaterialVersion] = {}
        self.approvals: list[Approval] = []
        self.publications: list[Publication] = []
        self.publication_ends: list[PublicationEnd] = []
        self.dispositions: list[Disposition] = []
        self.complaints: dict[str, Complaint] = {}

    @staticmethod
    def _put(table: dict, key: str, record, label: str) -> None:
        if key in table:
            raise ValueError(f"{label}已存在：{key}")
        table[key] = record

    def add_product(self, record: Product) -> None:
        self._put(self.products, record.product_id, record, "产品")

    def add_channel(self, record: Channel) -> None:
        self._put(self.channels, record.channel_id, record, "渠道")

    def add_evidence(self, record: Evidence) -> None:
        self._put(self.evidence, record.evidence_id, record, "证据")

    def add_regulation(self, record: Regulation) -> None:
        self._put(self.regulations, record.regulation_id, record, "法规")

    def add_material(self, record: Material) -> None:
        self._put(self.materials, record.material_id, record, "素材")

    def add_version(self, record: MaterialVersion) -> None:
        self._put(self.versions, record.version_id, record, "素材版本")

    def add_complaint(self, record: Complaint) -> None:
        self._put(self.complaints, record.complaint_id, record, "投诉")

    def add_approval(self, record: Approval) -> None:
        if any(a.approval_id == record.approval_id for a in self.approvals):
            raise ValueError(f"审核记录已存在：{record.approval_id}")
        self.approvals.append(record)

    def add_publication(self, record: Publication) -> None:
        if any(p.publication_id == record.publication_id for p in self.publications):
            raise ValueError(f"发布记录已存在：{record.publication_id}")
        self.publications.append(record)

    def add_publication_end(self, record: PublicationEnd) -> None:
        self.publication_ends.append(record)

    def add_disposition(self, record: Disposition) -> None:
        if any(d.disposition_id == record.disposition_id for d in self.dispositions):
            raise ValueError(f"处置记录已存在：{record.disposition_id}")
        self.dispositions.append(record)

    def current_evidence(self, series_id: str, on: date) -> Evidence | None:
        """指定日期某证据系列的现行版本（valid_from 最晚者）。"""
        candidates = [
            e
            for e in self.evidence.values()
            if e.series_id == series_id and e.valid_from <= on
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: (e.valid_from, e.version))

    def current_regulation(self, series_id: str, on: date) -> Regulation | None:
        """指定日期某法规系列的现行版本。"""
        candidates = [
            r
            for r in self.regulations.values()
            if r.series_id == series_id and r.covers(on)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: (r.effective_from, r.version))

    def publication_live_at(self, pub: Publication, on: date) -> bool:
        """页面在指定日期是否可见：已上线且当日之前未被下线。"""
        if pub.started_on > on:
            return False
        return not any(
            e.publication_id == pub.publication_id and e.ended_on <= on
            for e in self.publication_ends
        )
