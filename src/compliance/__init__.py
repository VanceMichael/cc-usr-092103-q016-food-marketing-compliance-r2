"""营销合规审校后台。

表达绑定证据版本，处置只追加不改写历史；旧图回流、跨渠道复用、
并行审批、法规生效日变化时指出受影响的已发布素材，并支持从投诉
一路核对到素材、审核依据与后续行动。
"""

from .impact import (
    Impact,
    impacts_from_channel_reuse,
    impacts_from_regulation,
    impacts_from_resurface,
    parallel_review_conflicts,
)
from .loader import load_store
from .models import (
    Channel,
    Claim,
    ClaimType,
    Complaint,
    Disposition,
    DispositionType,
    Evidence,
    EvidenceKind,
    EvidenceRef,
    Material,
    Product,
    ProductCategory,
    Publication,
    Regulation,
    Review,
)
from .rules import REQUIRED_EVIDENCE, Finding, claim_findings, review_findings
from .store import Store
from .trace import render_trace, trace_complaint

__all__ = [
    "Channel",
    "Claim",
    "ClaimType",
    "Complaint",
    "Disposition",
    "DispositionType",
    "Evidence",
    "EvidenceKind",
    "EvidenceRef",
    "Finding",
    "Impact",
    "Material",
    "Product",
    "ProductCategory",
    "Publication",
    "REQUIRED_EVIDENCE",
    "Regulation",
    "Review",
    "Store",
    "claim_findings",
    "impacts_from_channel_reuse",
    "impacts_from_regulation",
    "impacts_from_resurface",
    "load_store",
    "parallel_review_conflicts",
    "render_trace",
    "review_findings",
    "trace_complaint",
]
