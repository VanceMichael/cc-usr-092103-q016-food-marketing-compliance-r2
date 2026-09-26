"""营销合规审校领域模型。

所有实体均为不可变记录；审核、下架、澄清、修改等动作只追加新记录，
不改写历史页面，保证任何时点都能复原"当时看到了什么、依据是什么"。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ProductCategory(str, Enum):
    FOOD = "普通食品"
    DRUG = "药品"


class EvidenceKind(str, Enum):
    FORMULA = "配料表"
    TRADEMARK = "商标注册证"
    INSPECTION = "抽检报告"
    LEGAL_OPINION = "法律意见"


class ClaimType(str, Enum):
    INGREDIENT = "成分描述"
    EFFICACY = "功效表述"
    TRADEMARK_USE = "商标使用"
    QUALITY = "质量表述"
    ENDORSEMENT = "代言背书"
    COMPARISON = "对比宣传"


class DispositionType(str, Enum):
    TAKEDOWN = "下架"
    CLARIFY = "澄清"
    MODIFY = "修改"
    REPUBLISH = "复投"


@dataclass(frozen=True)
class Product:
    product_id: str
    name: str
    category: ProductCategory
    ingredients: tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    """一份证据的特定版本；配料表、商标、抽检、法律意见各自独立生效。"""

    evidence_id: str
    version: int
    kind: EvidenceKind
    title: str
    issuer: str
    valid_from: date
    valid_to: date | None  # None 表示长期有效
    summary: str = ""

    def covers(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)


@dataclass(frozen=True)
class EvidenceRef:
    """表达与证据版本的绑定。"""

    evidence_id: str
    version: int


@dataclass(frozen=True)
class Claim:
    """一条对外表达（包装图文/广告话术/代言内容），必须绑定证据版本。"""

    claim_id: str
    product_id: str
    claim_type: ClaimType
    text: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Material:
    """素材的特定版本；content_hash 用于识别旧图回流与跨渠道复用。"""

    material_id: str
    version: int
    product_id: str
    kind: str  # 包装正面/包装背面/广告片/直播话术/代言海报
    content_hash: str
    claim_ids: tuple[str, ...]
    created_at: date


@dataclass(frozen=True)
class Channel:
    channel_id: str
    name: str
    channel_type: str  # 电商/直播/线下/社媒
    restricted_claim_types: tuple[ClaimType, ...] = ()


@dataclass(frozen=True)
class Publication:
    """素材版本在某渠道的投放窗口；记录本身只增不改。"""

    publication_id: str
    material_id: str
    material_version: int
    channel_id: str
    start: date
    end: date | None  # None 表示仍在投放


@dataclass(frozen=True)
class Review:
    """一次审核结论及其引用的证据版本；审核人角色决定可审的表达类型。"""

    review_id: str
    material_id: str
    material_version: int
    reviewer: str
    role: str
    decision: str  # 通过/驳回/有条件通过
    cited_evidence: tuple[EvidenceRef, ...]
    created_at: date
    note: str = ""


@dataclass(frozen=True)
class Disposition:
    """处置记录：下架/澄清/修改/复投，只追加、不抹去历史页面。"""

    seq: int
    disposition_id: str
    dtype: DispositionType
    material_id: str
    publication_id: str | None
    reason: str
    actor: str
    created_at: date
    note: str = ""


@dataclass(frozen=True)
class Complaint:
    complaint_id: str
    product_id: str
    channel_id: str
    observed_at: date
    description: str


@dataclass(frozen=True)
class Regulation:
    regulation_id: str
    name: str
    effective_from: date
    prohibited_terms: tuple[str, ...]
    note: str = ""
