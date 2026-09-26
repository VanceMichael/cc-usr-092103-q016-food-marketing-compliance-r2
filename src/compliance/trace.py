"""投诉溯源：从投诉一路核对到实际素材、审核依据和后续行动。

法务收到投诉后，按"渠道 + 目击日期"复原当时展示的素材版本，
逐条表达核对其绑定的证据版本当日是否有效，再列出该素材版本的
全部审核记录与投诉后的处置记录。
"""

from __future__ import annotations

from .rules import claim_findings, review_findings
from .store import Store


def trace_complaint(store: Store, complaint_id: str) -> dict:
    complaint = store.complaints[complaint_id]
    product = store.products[complaint.product_id]
    channel = store.channels[complaint.channel_id]
    on = complaint.observed_at

    items = []
    for pub in store.publications_on(complaint.channel_id, on):
        material = store.materials[(pub.material_id, pub.material_version)]
        if material.product_id != complaint.product_id:
            continue

        claims = []
        for claim in store.material_claims(pub.material_id, pub.material_version):
            bindings = []
            for ref in claim.evidence:
                evidence = store.evidence.get((ref.evidence_id, ref.version))
                bindings.append(
                    {
                        "evidence_id": ref.evidence_id,
                        "version": ref.version,
                        "kind": evidence.kind.value if evidence else None,
                        "title": evidence.title if evidence else None,
                        "valid_on_observed": bool(evidence and evidence.covers(on)),
                    }
                )
            claims.append(
                {
                    "claim_id": claim.claim_id,
                    "claim_type": claim.claim_type.value,
                    "text": claim.text,
                    "evidence": bindings,
                    "findings": [
                        {"level": f.level, "message": f.message}
                        for f in claim_findings(store, claim, on)
                    ],
                }
            )

        reviews = [
            {
                "review_id": r.review_id,
                "reviewer": r.reviewer,
                "role": r.role,
                "decision": r.decision,
                "created_at": r.created_at.isoformat(),
                "findings": [
                    {"level": f.level, "message": f.message} for f in review_findings(store, r)
                ],
            }
            for r in store.reviews_for(pub.material_id, pub.material_version)
        ]

        dispositions = [
            {
                "seq": d.seq,
                "dtype": d.dtype.value,
                "reason": d.reason,
                "actor": d.actor,
                "created_at": d.created_at.isoformat(),
                "note": d.note,
            }
            for d in store.dispositions_for(material_id=pub.material_id)
        ]

        items.append(
            {
                "publication_id": pub.publication_id,
                "material_id": material.material_id,
                "material_version": material.version,
                "material_kind": material.kind,
                "status_on_observed": store.publication_status(pub.publication_id, on),
                "claims": claims,
                "reviews": reviews,
                "dispositions": dispositions,
            }
        )

    return {
        "complaint": {
            "complaint_id": complaint.complaint_id,
            "description": complaint.description,
            "observed_at": on.isoformat(),
            "channel_id": channel.channel_id,
            "channel_name": channel.name,
        },
        "product": product.name,
        "category": product.category.value,
        "items": items,
    }


def render_trace(trace: dict) -> str:
    """渲染为管理层可逐行核对的文本报告。"""
    c = trace["complaint"]
    lines = [
        f"投诉 {c['complaint_id']}：{c['description']}",
        f"产品：{trace['product']}（{trace['category']}） 渠道：{c['channel_name']} 目击日期：{c['observed_at']}",
    ]
    for item in trace["items"]:
        lines.append(
            f"素材 {item['material_id']} v{item['material_version']}（{item['material_kind']}）"
            f" 发布 {item['publication_id']} 当日状态：{item['status_on_observed']}"
        )
        for claim in item["claims"]:
            lines.append(f"  表达 {claim['claim_id']}〔{claim['claim_type']}〕{claim['text']}")
            for b in claim["evidence"]:
                mark = "有效" if b["valid_on_observed"] else "失效或缺失"
                lines.append(f"    证据 {b['evidence_id']} v{b['version']}（{b['kind']}）{b['title']}——当日{mark}")
            for f in claim["findings"]:
                lines.append(f"    [{f['level']}] {f['message']}")
        for r in item["reviews"]:
            lines.append(f"  审核 {r['review_id']}：{r['reviewer']}（{r['role']}）{r['decision']} @ {r['created_at']}")
            for f in r["findings"]:
                lines.append(f"    [{f['level']}] {f['message']}")
        for d in item["dispositions"]:
            lines.append(f"  处置 #{d['seq']} {d['dtype']} @ {d['created_at']}：{d['reason']}（{d['actor']}）")
    return "\n".join(lines)
