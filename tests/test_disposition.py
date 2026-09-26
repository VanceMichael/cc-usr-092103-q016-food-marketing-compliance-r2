"""下架、澄清、修改只追加处置记录，历史页面不抹去。"""

from datetime import date

from src.compliance import (
    Claim,
    ClaimCategory,
    ClaimTopic,
    DispositionKind,
    MaterialSlot,
)


def test_takedown_appends_record_and_preserves_history(seeded):
    before = seeded.snapshot("short-video", date(2026, 5, 10))
    assert len(before) == 1
    publication_ids = [p.publication_id for p in seeded.store.publications]

    disposition = seeded.record_disposition(
        "lozenge-page",
        DispositionKind.TAKEDOWN,
        date(2026, 5, 12),
        "法务-林某",
        "消费者投诉涉嫌混淆药品功效，先予下架",
        channel_id="short-video",
    )

    # 下架当日起页面不再可见
    assert seeded.snapshot("short-video", date(2026, 5, 12)) == []
    # 但投诉当日看到的历史页面仍可完整复原
    after = seeded.snapshot("short-video", date(2026, 5, 10))
    assert [p.version.version_id for p in after] == ["lozenge-page@v1"]
    # 发布记录未被删除或改写，只追加了下线事件
    assert [p.publication_id for p in seeded.store.publications] == publication_ids
    ends = [
        e
        for e in seeded.store.publication_ends
        if e.disposition_id == disposition.disposition_id
    ]
    assert len(ends) == 1 and ends[0].ended_on == date(2026, 5, 12)


def test_takedown_without_channel_covers_all_channels(seeded):
    seeded.record_disposition(
        "lozenge-page",
        DispositionKind.TAKEDOWN,
        date(2026, 5, 12),
        "法务-林某",
        "全渠道下架",
    )
    assert seeded.snapshot("short-video", date(2026, 5, 12)) == []
    assert seeded.snapshot("tmall-flagship", date(2026, 5, 12)) == []


def test_clarification_is_append_only(seeded):
    seeded.record_disposition(
        "lozenge-page",
        DispositionKind.CLARIFICATION,
        date(2026, 5, 13),
        "公关-赵某",
        "发布澄清声明：喉糖为普通食品，与同名药品配方不同",
        channel_id="short-video",
    )
    dispositions = seeded.store.dispositions
    assert dispositions[-1].kind is DispositionKind.CLARIFICATION
    # 澄清不影响页面可见性，只追加记录
    assert len(seeded.snapshot("short-video", date(2026, 5, 13))) == 1


def test_correction_creates_new_version_and_keeps_old_ones(seeded):
    claims = (
        Claim(
            "c-brand-front",
            MaterialSlot.PACKAGE_FRONT,
            "蓝芩喉糖",
            ClaimCategory.ORDINARY_FOOD,
            ClaimTopic.BRAND,
            ("ev-trademark",),
        ),
        Claim(
            "c-ingredients-back-2",
            MaterialSlot.PACKAGE_BACK,
            "配料：白砂糖、桔梗提取物、甘草提取物",
            ClaimCategory.ORDINARY_FOOD,
            ClaimTopic.INGREDIENT,
            ("ev-formula-v2",),
        ),
    )
    version, disposition = seeded.correct_material(
        "lozenge-page",
        date(2026, 5, 14),
        claims,
        "法务-林某",
        "投诉后修改：删除功效与代言话术",
        note="v3 合规改版",
    )
    assert version.version == 3
    assert version.version_id == "lozenge-page@v3"
    assert disposition.kind is DispositionKind.CORRECTION
    assert disposition.linked_version_id == "lozenge-page@v3"
    # 旧版本依然可查
    assert "lozenge-page@v1" in seeded.store.versions
    assert "lozenge-page@v2" in seeded.store.versions
