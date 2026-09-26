#!/usr/bin/env python
"""演示：从消费者投诉一路核对到实际素材、审核依据与后续行动。

运行：python scripts/trace_complaint_demo.py
（数据全部来自 fixtures/compliance_seed.json，均为虚构。）
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.compliance import DispositionKind, MaterialSlot  # noqa: E402
from src.compliance.reports import (  # noqa: E402
    impacts_for_evidence,
    impacts_for_regulation,
    resurface_check,
    trace_complaint,
)
from src.compliance.seed import load_seed  # noqa: E402


def main() -> None:
    service = load_seed(Path("fixtures/compliance_seed.json"))
    observed = date(2026, 5, 10)

    print("== 1. 复原消费者 2026-05-10 在短视频平台看到的页面 ==")
    for page in service.snapshot("short-video", observed):
        print(f"素材 {page.version.version_id}（{page.material.title}）")
        for slot in MaterialSlot:
            for claim in page.claims_in(slot):
                print(f"  [{slot.value}] {claim.text}")
        print("  当日问题：")
        for issue in page.evaluation.issues:
            print(f"   - {issue.code}: {issue.message}")

    print("\n== 2. 影响分析：法规生效日与证据版本变化 ==")
    for item in impacts_for_regulation(service, "reg-ad-2026"):
        print(f"新规影响 {item.version_id} @ {item.channel_id}: {item.reasons[0]}")
    for item in impacts_for_evidence(service, "inspection-lozenge", date(2026, 1, 15)):
        print(f"抽检报告过期影响 {item.version_id} @ {item.channel_id}")

    print("\n== 3. 旧图回流复核：v1 若 2026-06-01 复投连锁药店 ==")
    report = resurface_check(service, "lozenge-page@v1", "retail-pharmacy", date(2026, 6, 1))
    print(f"  缺失/未授权渠道的角色: {list(report.missing_channel_roles)}")
    print(f"  新生效法规: {[r.name for r in report.new_regulations]}")

    print("\n== 4. 追加处置（下架 + 澄清），历史页面保留 ==")
    service.record_disposition(
        "lozenge-page", DispositionKind.TAKEDOWN, date(2026, 5, 12),
        "法务-林某", "投诉成立，短视频渠道下架", channel_id="short-video",
    )
    service.record_disposition(
        "lozenge-page", DispositionKind.CLARIFICATION, date(2026, 5, 13),
        "公关-赵某", "发布澄清声明：喉糖为普通食品，与同名药品配方不同",
    )

    print("\n== 5. 投诉追踪报告（JSON） ==")
    print(json.dumps(trace_complaint(service, "cmp-001"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
