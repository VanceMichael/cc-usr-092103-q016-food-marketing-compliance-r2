from datetime import date
from pathlib import Path

import pytest

from src.compliance import (
    ClaimCategory,
    ClaimTopic,
    ComplianceService,
    EvidenceKind,
    ReviewPolicy,
)
from src.compliance.seed import load_seed


@pytest.fixture
def policy():
    return ReviewPolicy(
        roles=frozenset({"legal", "quality", "medical"}),
        required_roles={
            ClaimCategory.ORDINARY_FOOD: frozenset({"legal", "quality"}),
            ClaimCategory.DRUG_EFFICACY: frozenset({"legal", "medical"}),
        },
        topic_evidence={
            ClaimTopic.GENERAL: frozenset(
                {
                    EvidenceKind.FORMULA,
                    EvidenceKind.INSPECTION,
                    EvidenceKind.LEGAL_OPINION,
                }
            ),
            ClaimTopic.INGREDIENT: frozenset(
                {EvidenceKind.FORMULA, EvidenceKind.LEGAL_OPINION}
            ),
            ClaimTopic.QUALITY: frozenset(
                {EvidenceKind.INSPECTION, EvidenceKind.LEGAL_OPINION}
            ),
            ClaimTopic.BRAND: frozenset(
                {EvidenceKind.TRADEMARK, EvidenceKind.LEGAL_OPINION}
            ),
            ClaimTopic.EFFICACY: frozenset({EvidenceKind.LEGAL_OPINION}),
        },
    )


@pytest.fixture
def service(policy):
    return ComplianceService(policy)


@pytest.fixture
def world(service):
    """最小合规世界：食品与药品各一、两个渠道、四类证据、一条禁用法规。"""
    from src.compliance import ProductType, RegulationRule

    service.add_product("p-food", "某喉糖", ProductType.ORDINARY_FOOD)
    service.add_product("p-drug", "某口服液", ProductType.DRUG)
    service.add_channel("ch-a", "旗舰店", "e-commerce")
    service.add_channel("ch-b", "药店", "retail")
    service.add_evidence(
        "ev-f1", "formula", EvidenceKind.FORMULA, 1, "配方 v1", "",
        date(2025, 1, 1), date(2025, 12, 31),
    )
    service.add_evidence(
        "ev-tm", "tm", EvidenceKind.TRADEMARK, 1, "商标注册证", "", date(2024, 1, 1)
    )
    service.add_evidence(
        "ev-insp", "insp", EvidenceKind.INSPECTION, 1, "抽检合格报告", "",
        date(2025, 1, 1), date(2025, 6, 30),
    )
    service.add_evidence(
        "ev-legal", "legal", EvidenceKind.LEGAL_OPINION, 1, "法律意见", "",
        date(2025, 1, 1),
    )
    service.add_regulation(
        "reg-1",
        "ad",
        "食品广告合规规定",
        1,
        date(2024, 1, 1),
        (
            RegulationRule(
                ProductType.ORDINARY_FOOD,
                ClaimCategory.DRUG_EFFICACY,
                None,
                "普通食品不得宣称疾病治疗功能",
            ),
        ),
    )
    return service


@pytest.fixture
def seeded():
    return load_seed(Path("fixtures/compliance_seed.json"))
