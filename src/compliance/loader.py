"""从 fixtures 目录装载领域资料样例。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

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
from .store import Store


def _d(value) -> date | None:
    return date.fromisoformat(value) if value else None


def _refs(items) -> tuple[EvidenceRef, ...]:
    return tuple(EvidenceRef(evidence_id=i["evidence_id"], version=i["version"]) for i in items)


def _read(fixtures_dir: Path, name: str) -> list | dict:
    path = fixtures_dir / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_store(fixtures_dir: Path) -> Store:
    """按依赖顺序装载全部样例资料，装载过程即做引用完整性校验。"""
    store = Store()

    for p in _read(fixtures_dir, "products.json"):
        store.add_product(
            Product(
                product_id=p["product_id"],
                name=p["name"],
                category=ProductCategory(p["category"]),
                ingredients=tuple(p["ingredients"]),
            )
        )

    for e in _read(fixtures_dir, "evidence.json"):
        store.add_evidence(
            Evidence(
                evidence_id=e["evidence_id"],
                version=e["version"],
                kind=EvidenceKind(e["kind"]),
                title=e["title"],
                issuer=e["issuer"],
                valid_from=_d(e["valid_from"]),
                valid_to=_d(e["valid_to"]),
                summary=e.get("summary", ""),
            )
        )

    for c in _read(fixtures_dir, "claims.json"):
        store.add_claim(
            Claim(
                claim_id=c["claim_id"],
                product_id=c["product_id"],
                claim_type=ClaimType(c["claim_type"]),
                text=c["text"],
                evidence=_refs(c.get("evidence", [])),
            )
        )

    for m in _read(fixtures_dir, "materials.json"):
        store.add_material(
            Material(
                material_id=m["material_id"],
                version=m["version"],
                product_id=m["product_id"],
                kind=m["kind"],
                content_hash=m["content_hash"],
                claim_ids=tuple(m["claim_ids"]),
                created_at=_d(m["created_at"]),
            )
        )

    for ch in _read(fixtures_dir, "channels.json"):
        store.add_channel(
            Channel(
                channel_id=ch["channel_id"],
                name=ch["name"],
                channel_type=ch["channel_type"],
                restricted_claim_types=tuple(ClaimType(t) for t in ch.get("restricted_claim_types", [])),
            )
        )

    for p in _read(fixtures_dir, "publications.json"):
        store.add_publication(
            Publication(
                publication_id=p["publication_id"],
                material_id=p["material_id"],
                material_version=p["material_version"],
                channel_id=p["channel_id"],
                start=_d(p["start"]),
                end=_d(p["end"]),
            )
        )

    for r in _read(fixtures_dir, "reviews.json"):
        store.add_review(
            Review(
                review_id=r["review_id"],
                material_id=r["material_id"],
                material_version=r["material_version"],
                reviewer=r["reviewer"],
                role=r["role"],
                decision=r["decision"],
                cited_evidence=_refs(r.get("cited_evidence", [])),
                created_at=_d(r["created_at"]),
                note=r.get("note", ""),
            )
        )

    for d in _read(fixtures_dir, "dispositions.json"):
        store.add_disposition(
            Disposition(
                seq=0,
                disposition_id=d["disposition_id"],
                dtype=DispositionType(d["dtype"]),
                material_id=d["material_id"],
                publication_id=d.get("publication_id"),
                reason=d["reason"],
                actor=d["actor"],
                created_at=_d(d["created_at"]),
                note=d.get("note", ""),
            )
        )

    for c in _read(fixtures_dir, "complaints.json"):
        store.add_complaint(
            Complaint(
                complaint_id=c["complaint_id"],
                product_id=c["product_id"],
                channel_id=c["channel_id"],
                observed_at=_d(c["observed_at"]),
                description=c["description"],
            )
        )

    for r in _read(fixtures_dir, "regulations.json"):
        store.add_regulation(
            Regulation(
                regulation_id=r["regulation_id"],
                name=r["name"],
                effective_from=_d(r["effective_from"]),
                prohibited_terms=tuple(r["prohibited_terms"]),
                note=r.get("note", ""),
            )
        )

    permissions = _read(fixtures_dir, "permissions.json")
    if permissions:
        store.set_permissions(
            {role: frozenset(ClaimType(t) for t in types) for role, types in permissions["roles"].items()}
        )

    return store
