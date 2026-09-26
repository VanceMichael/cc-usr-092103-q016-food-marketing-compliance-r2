"""营销合规审校后台的领域模型。

所有记录均为不可变对象：下架、澄清、修改只追加新记录，历史页面永不改写。
日期一律使用 ``datetime.date``，与投诉所指的“具体日期”对齐。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ProductType(str, Enum):
    """产品法定属性，决定可使用的表达边界。"""

    ORDINARY_FOOD = "ordinary_food"
    DRUG = "drug"


class EvidenceKind(str, Enum):
    """证据种类。注册商标、抽检合格等单一证据不能单独替所有宣传放行。"""

    FORMULA = "formula"  # 配料 / 配方依据
    TRADEMARK = "trademark"  # 商标注册证
    INSPECTION = "inspection"  # 抽检报告
    LEGAL_OPINION = "legal_opinion"  # 法律意见


class ClaimCategory(str, Enum):
    """表达类别：普通食品表达与药品功效表达的边界。"""

    ORDINARY_FOOD = "ordinary_food"
    DRUG_EFFICACY = "drug_efficacy"


class ClaimTopic(str, Enum):
    """表达话题，决定需要哪一类证据支撑。"""

    GENERAL = "general"
    INGREDIENT = "ingredient"  # 成分 / 配料
    QUALITY = "quality"  # 品质 / 抽检
    BRAND = "brand"  # 品牌 / 商标
    EFFICACY = "efficacy"  # 功效相关表述


class MaterialSlot(str, Enum):
    """素材版面位置，对应法务需要复原的页面结构。"""

    PACKAGE_FRONT = "package_front"  # 包装正面
    PACKAGE_BACK = "package_back"  # 包装背面
    AD_COPY = "ad_copy"  # 广告话术
    ENDORSEMENT = "endorsement"  # 代言内容


class Decision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class DispositionKind(str, Enum):
    """处置方式：只追加记录，不抹去历史页面。"""

    TAKEDOWN = "takedown"  # 下架
    CLARIFICATION = "clarification"  # 澄清
    CORRECTION = "correction"  # 修改


@dataclass(frozen=True)
class Product:
    product_id: str
    name: str
    product_type: ProductType
    note: str = ""


@dataclass(frozen=True)
class Channel:
    channel_id: str
    name: str
    kind: str  # 渠道形态，如电商、线下零售、社媒


@dataclass(frozen=True)
class Evidence:
    """一条证据的一个版本。同一 series 内按 valid_from 先后更替。"""

    evidence_id: str
    series_id: str
    kind: EvidenceKind
    version: int
    title: str
    summary: str
    valid_from: date
    valid_to: date | None = None  # 含当日；None 表示持续有效

    def covers(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)


@dataclass(frozen=True)
class RegulationRule:
    """一条禁用规则：某类产品在某类表达（可限定话题）上被禁止。"""

    product_type: ProductType
    category: ClaimCategory
    topic: ClaimTopic | None  # None 表示不限话题
    note: str = ""


@dataclass(frozen=True)
class Regulation:
    """法规的一个版本，按生效日更替。"""

    regulation_id: str
    series_id: str
    name: str
    version: int
    effective_from: date
    rules: tuple[RegulationRule, ...]
    effective_to: date | None = None

    def covers(self, on: date) -> bool:
        return self.effective_from <= on and (
            self.effective_to is None or on <= self.effective_to
        )


@dataclass(frozen=True)
class Claim:
    """一条表达，绑定其依据的证据版本（evidence_ids）。"""

    claim_id: str
    slot: MaterialSlot
    text: str
    category: ClaimCategory
    topic: ClaimTopic
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Material:
    material_id: str
    product_id: str
    title: str


@dataclass(frozen=True)
class MaterialVersion:
    """素材的一个版本；修改素材即产生新版本，旧版本保留可查。"""

    version_id: str
    material_id: str
    version: int
    created_on: date
    claims: tuple[Claim, ...]
    note: str = ""


@dataclass(frozen=True)
class Approval:
    """一次审核记录。channels 为空表示不限渠道。"""

    approval_id: str
    version_id: str
    role: str
    decision: Decision
    decided_on: date
    channels: tuple[str, ...] = ()
    comment: str = ""


@dataclass(frozen=True)
class Publication:
    """一次发布：某素材版本自某日起在某渠道可见。"""

    publication_id: str
    version_id: str
    channel_id: str
    started_on: date


@dataclass(frozen=True)
class PublicationEnd:
    """页面下线事件（追加记录，原 Publication 不改动）。

    ended_on 当日起页面不再可见；disposition_id 为空表示被新版本自然替换。
    """

    publication_id: str
    ended_on: date
    disposition_id: str | None = None


@dataclass(frozen=True)
class Disposition:
    """处置记录：下架 / 澄清 / 修改，只追加。"""

    disposition_id: str
    material_id: str
    kind: DispositionKind
    created_on: date
    actor: str
    reason: str
    channel_id: str | None = None  # None 表示全部渠道
    linked_version_id: str | None = None  # 修改处置指向新版本


@dataclass(frozen=True)
class Complaint:
    """消费者投诉：指明渠道与看到页面的具体日期。"""

    complaint_id: str
    product_id: str
    channel_id: str
    observed_on: date
    description: str
    quotes: tuple[str, ...] = ()  # 消费者复述的原文片段
