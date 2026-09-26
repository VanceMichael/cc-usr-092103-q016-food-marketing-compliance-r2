"""从种子资料文件装载一个完整的合规审校后台。

资料格式见 ``contracts/compliance-seed.schema.json``；
示例见 ``fixtures/compliance_seed.json``（全部为虚构数据）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import (
    Claim,
    ClaimCategory,
    ClaimTopic,
    Decision,
    MaterialSlot,
    ProductType,
    RegulationRule,
)
from .policy import ReviewPolicy
from .service import ComplianceService

_PRODUCT_TYPE = {p.value: p for p in ProductType}


def load_seed(path: str | Path) -> ComplianceService:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    service = ComplianceService(ReviewPolicy.from_dict(data["review_policy"]))

    for p in data.get("products", []):
        service.add_product(p["product_id"], p["name"], p["product_type"], p.get("note", ""))
    for c in data.get("channels", []):
        service.add_channel(c["channel_id"], c["name"], c["kind"])
    for e in data.get("evidence", []):
        service.add_evidence(
            e["evidence_id"],
            e["series_id"],
            e["kind"],
            e["version"],
            e["title"],
            e.get("summary", ""),
            _date(e["valid_from"]),
            _date(e["valid_to"]) if e.get("valid_to") else None,
        )
    for r in data.get("regulations", []):
        rules = tuple(
            RegulationRule(
                _PRODUCT_TYPE[rule["product_type"]],
                ClaimCategory(rule["category"]),
                ClaimTopic(rule["topic"]) if rule.get("topic") else None,
                rule.get("note", ""),
            )
            for rule in r["rules"]
        )
        service.add_regulation(
            r["regulation_id"],
            r["series_id"],
            r["name"],
            r["version"],
            _date(r["effective_from"]),
            rules,
            _date(r["effective_to"]) if r.get("effective_to") else None,
        )
    for m in data.get("materials", []):
        service.create_material(m["material_id"], m["product_id"], m["title"])
        for v in m.get("versions", []):
            claims = tuple(
                Claim(
                    claim["claim_id"],
                    MaterialSlot(claim["slot"]),
                    claim["text"],
                    ClaimCategory(claim["category"]),
                    ClaimTopic(claim["topic"]),
                    tuple(claim.get("evidence_ids", ())),
                )
                for claim in v["claims"]
            )
            service.add_version(
                m["material_id"], _date(v["created_on"]), claims, v.get("note", "")
            )
    for a in data.get("approvals", []):
        service.submit_approval(
            _version_ref(a),
            a["role"],
            Decision(a["decision"]),
            _date(a["decided_on"]),
            tuple(a.get("channels", ())),
            a.get("comment", ""),
        )
    for p in data.get("publications", []):
        service.publish(_version_ref(p), p["channel_id"], _date(p["started_on"]))
    for c in data.get("complaints", []):
        service.file_complaint(
            c["product_id"],
            c["channel_id"],
            _date(c["observed_on"]),
            c["description"],
            tuple(c.get("quotes", ())),
            complaint_id=c.get("complaint_id"),
        )
    return service


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _version_ref(record: dict) -> str:
    return f'{record["material_id"]}@v{record["version"]}'
