"""测试用辅助函数。"""

from src.compliance import (
    Claim,
    ClaimCategory,
    ClaimTopic,
    Decision,
    MaterialSlot,
)


def make_claim(
    claim_id="c-1",
    text="示例表达",
    topic=ClaimTopic.GENERAL,
    category=ClaimCategory.ORDINARY_FOOD,
    evidence=(),
    slot=MaterialSlot.AD_COPY,
):
    return Claim(claim_id, slot, text, category, topic, tuple(evidence))


def approve(service, version_id, roles, on, channels=("ch-a",)):
    for role in roles:
        service.submit_approval(
            version_id, role, Decision.APPROVED, on, tuple(channels)
        )


def issue_codes(evaluation):
    return {issue.code for issue in evaluation.issues}
