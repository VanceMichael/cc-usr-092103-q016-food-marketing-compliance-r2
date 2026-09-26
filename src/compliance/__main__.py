"""演示入口：装载样例资料，输出投诉溯源报告与影响面分析。

用法：python -m src.compliance [fixtures 目录]
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from .impact import (
    impacts_from_channel_reuse,
    impacts_from_regulation,
    impacts_from_resurface,
    parallel_review_conflicts,
)
from .loader import load_store
from .trace import render_trace, trace_complaint


def main() -> None:
    fixtures_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures")
    store = load_store(fixtures_dir)

    print("=" * 30, "投诉溯源", "=" * 30)
    for complaint_id in store.complaints:
        print(render_trace(trace_complaint(store, complaint_id)))
        print()

    print("=" * 30, "影响面分析", "=" * 30)
    impacts = []
    impacts += impacts_from_regulation(store, "REG-02")
    impacts += impacts_from_resurface(store, "img-back-v1", date(2025, 9, 15))
    impacts += impacts_from_channel_reuse(store, "M-POSTER", 1, "CH-LIVE", date(2025, 9, 10))
    impacts += parallel_review_conflicts(store)
    for impact in impacts:
        pub = f" 发布{impact.publication_id}" if impact.publication_id else ""
        status = f"（{impact.status}）" if impact.status else ""
        print(f"[{impact.kind}] {impact.material_id} v{impact.material_version}{pub}{status}：{impact.detail}")


if __name__ == "__main__":
    main()
