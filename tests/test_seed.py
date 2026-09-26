"""种子资料可加载，且与既有领域资料约定一致。"""

from datetime import date
from pathlib import Path

from src.compliance.seed import load_seed


def test_seed_loads_complete_world(seeded):
    assert set(seeded.store.products) == {"lanqin-lozenge", "lanqin-oral-liquid"}
    assert set(seeded.store.channels) == {
        "tmall-flagship",
        "retail-pharmacy",
        "short-video",
    }
    assert len(seeded.store.publications) == 3
    assert "cmp-001" in seeded.store.complaints


def test_seed_timeline_is_internally_consistent(seeded):
    # 种子里的每次发布在发布当日均通过了完整合规校验
    for pub in seeded.store.publications:
        evaluation = seeded.evaluate(pub.version_id, pub.channel_id, pub.started_on)
        assert evaluation.ok, (pub.publication_id, evaluation.issues)


def test_seed_file_path_loading():
    service = load_seed(Path("fixtures/compliance_seed.json"))
    assert service.snapshot("short-video", date(2026, 5, 10))
