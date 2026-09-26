"""审核权限与表达-证据匹配策略。

- ``required_roles``：每类表达需要哪些角色并行审批，全部通过才算审结。
- ``topic_evidence``：每类话题至少需要的证据种类之一。注册商标、抽检合格
  等单一证据无法覆盖所有话题，因此不能单独替所有宣传放行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import ClaimCategory, ClaimTopic, EvidenceKind


@dataclass(frozen=True)
class ReviewPolicy:
    roles: frozenset[str]
    required_roles: Mapping[ClaimCategory, frozenset[str]]
    topic_evidence: Mapping[ClaimTopic, frozenset[EvidenceKind]]

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewPolicy":
        return cls(
            roles=frozenset(data["roles"]),
            required_roles={
                ClaimCategory(k): frozenset(v)
                for k, v in data["required_roles"].items()
            },
            topic_evidence={
                ClaimTopic(k): frozenset(EvidenceKind(x) for x in v)
                for k, v in data["topic_evidence"].items()
            },
        )
