"""营销合规审校后台的核心服务。

职责：
- 登记产品、渠道、证据版本、法规版本与审核权限；
- 校验每条表达绑定的证据版本在发布日是否适用（当时适用原则）；
- 校验普通食品与药品功效表达的边界；
- 管理并行审批（按角色、按渠道范围），识别审核依据事后变化；
- 发布素材并按“渠道 + 日期”复原消费者当时看到的页面；
- 下架、澄清、修改只追加处置记录，不抹去历史页面。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .models import (
    Approval,
    Channel,
    Claim,
    ClaimCategory,
    Complaint,
    Decision,
    Disposition,
    DispositionKind,
    Evidence,
    EvidenceKind,
    Material,
    MaterialSlot,
    MaterialVersion,
    Product,
    ProductType,
    Publication,
    PublicationEnd,
    Regulation,
    RegulationRule,
)
from .policy import ReviewPolicy
from .store import ComplianceStore


class IssueCode:
    UNKNOWN_EVIDENCE = "unknown_evidence"
    CLAIM_UNBOUND = "claim_unbound"
    CLAIM_EVIDENCE_EXPIRED = "claim_evidence_expired"
    CLAIM_EVIDENCE_SUPERSEDED = "claim_evidence_superseded"
    CLAIM_EVIDENCE_KIND_MISMATCH = "claim_evidence_kind_mismatch"
    CLAIM_PROHIBITED = "claim_prohibited"
    MISSING_APPROVAL = "missing_approval"
    REJECTED_APPROVAL = "rejected_approval"
    APPROVAL_CHANNEL_MISMATCH = "approval_channel_mismatch"
    STALE_APPROVAL = "stale_approval"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    claim_id: str | None = None
    role: str | None = None


class ComplianceError(Exception):
    """发布等操作未通过合规校验。"""

    def __init__(self, issues):
        self.issues = tuple(issues)
        summary = "；".join(i.message for i in self.issues)
        super().__init__(f"合规校验未通过：{summary}")


@dataclass(frozen=True)
class RegulationHit:
    regulation: Regulation
    rule: RegulationRule


@dataclass(frozen=True)
class EvidenceStatus:
    """某条表达绑定的证据在指定日期的状态。"""

    evidence: Evidence
    status: str  # current / superseded / expired / not_yet_valid
    superseded: bool  # 是否已被同系列更新版本取代（可与过期并存）
    current_evidence_id: str | None


@dataclass(frozen=True)
class ClaimAssessment:
    claim: Claim
    evidence: tuple[EvidenceStatus, ...]
    prohibitions: tuple[RegulationHit, ...]
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class RoleApprovalView:
    """某角色对某版本的并行审批视图。"""

    role: str
    required: bool
    records: tuple[Approval, ...]
    latest: Approval | None
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class Evaluation:
    """对“某版本拟在某渠道某日发布”的完整合规评估。"""

    version_id: str
    channel_id: str
    on: date
    issues: tuple[Issue, ...]
    claims: tuple[ClaimAssessment, ...]
    approvals: tuple[RoleApprovalView, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class PageSnapshot:
    """消费者在某渠道某日实际看到的页面及其当时的合规状态。"""

    publication: Publication
    material: Material
    product: Product
    version: MaterialVersion
    evaluation: Evaluation

    def claims_in(self, slot: MaterialSlot) -> tuple[Claim, ...]:
        return tuple(c for c in self.version.claims if c.slot is slot)


class ComplianceService:
    def __init__(self, policy: ReviewPolicy, store: ComplianceStore | None = None):
        self.policy = policy
        self.store = store or ComplianceStore()
        self._counters: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # 基础资料登记
    # ------------------------------------------------------------------
    def add_product(
        self, product_id: str, name: str, product_type, note: str = ""
    ) -> Product:
        record = Product(product_id, name, ProductType(product_type), note)
        self.store.add_product(record)
        return record

    def add_channel(self, channel_id: str, name: str, kind: str) -> Channel:
        record = Channel(channel_id, name, kind)
        self.store.add_channel(record)
        return record

    def add_evidence(
        self,
        evidence_id: str,
        series_id: str,
        kind,
        version: int,
        title: str,
        summary: str,
        valid_from: date,
        valid_to: date | None = None,
    ) -> Evidence:
        if valid_to is not None and valid_to < valid_from:
            raise ValueError("证据有效期止日早于起日")
        record = Evidence(
            evidence_id,
            series_id,
            EvidenceKind(kind),
            version,
            title,
            summary,
            valid_from,
            valid_to,
        )
        self.store.add_evidence(record)
        return record

    def add_regulation(
        self,
        regulation_id: str,
        series_id: str,
        name: str,
        version: int,
        effective_from: date,
        rules,
        effective_to: date | None = None,
    ) -> Regulation:
        record = Regulation(
            regulation_id,
            series_id,
            name,
            version,
            effective_from,
            tuple(rules),
            effective_to,
        )
        self.store.add_regulation(record)
        return record

    # ------------------------------------------------------------------
    # 素材与表达
    # ------------------------------------------------------------------
    def create_material(self, material_id: str, product_id: str, title: str) -> Material:
        if product_id not in self.store.products:
            raise KeyError(f"未知产品：{product_id}")
        record = Material(material_id, product_id, title)
        self.store.add_material(record)
        return record

    def add_version(
        self, material_id: str, created_on: date, claims, note: str = ""
    ) -> MaterialVersion:
        self._material(material_id)
        number = 1 + sum(
            1 for v in self.store.versions.values() if v.material_id == material_id
        )
        record = MaterialVersion(
            f"{material_id}@v{number}", material_id, number, created_on, tuple(claims), note
        )
        self.store.add_version(record)
        return record

    # ------------------------------------------------------------------
    # 审核（并行审批，按角色与渠道范围）
    # ------------------------------------------------------------------
    def submit_approval(
        self,
        version_id: str,
        role: str,
        decision,
        decided_on: date,
        channels=(),
        comment: str = "",
    ) -> Approval:
        version = self._version(version_id)
        if role not in self.policy.roles:
            raise ValueError(f"未知审核角色：{role}")
        if decided_on < version.created_on:
            raise ValueError("审核日期早于版本创建日期")
        unknown = [c for c in channels if c not in self.store.channels]
        if unknown:
            raise ValueError(f"未知渠道：{unknown}")
        record = Approval(
            self._next_id("appr"),
            version_id,
            role,
            Decision(decision),
            decided_on,
            tuple(channels),
            comment,
        )
        self.store.add_approval(record)
        return record

    # ------------------------------------------------------------------
    # 发布与复原
    # ------------------------------------------------------------------
    def publish(self, version_id: str, channel_id: str, on: date) -> Publication:
        if channel_id not in self.store.channels:
            raise KeyError(f"未知渠道：{channel_id}")
        evaluation = self.evaluate(version_id, channel_id, on)
        if not evaluation.ok:
            raise ComplianceError(evaluation.issues)
        record = Publication(self._next_id("pub"), version_id, channel_id, on)
        self.store.add_publication(record)
        # 同素材同渠道的旧页面同日替换下线（追加下线记录，不删历史）。
        version = self._version(version_id)
        for other in list(self.store.publications):
            if other.publication_id == record.publication_id:
                continue
            other_version = self.store.versions[other.version_id]
            if (
                other_version.material_id == version.material_id
                and other.channel_id == channel_id
                and self.store.publication_live_at(other, on)
            ):
                self.store.add_publication_end(
                    PublicationEnd(other.publication_id, on, None)
                )
        return record

    def snapshot(self, channel_id: str, on: date) -> list[PageSnapshot]:
        """复原某渠道某日实际可见的页面（含当时的合规状态）。"""
        if channel_id not in self.store.channels:
            raise KeyError(f"未知渠道：{channel_id}")
        pages = []
        for pub in self.store.publications:
            if pub.channel_id != channel_id:
                continue
            if not self.store.publication_live_at(pub, on):
                continue
            version = self.store.versions[pub.version_id]
            material = self.store.materials[version.material_id]
            product = self.store.products[material.product_id]
            pages.append(
                PageSnapshot(
                    pub,
                    material,
                    product,
                    version,
                    self.evaluate(pub.version_id, channel_id, on),
                )
            )
        return sorted(
            pages, key=lambda s: (s.publication.started_on, s.publication.publication_id)
        )

    # ------------------------------------------------------------------
    # 处置：只追加记录
    # ------------------------------------------------------------------
    def record_disposition(
        self,
        material_id: str,
        kind,
        on: date,
        actor: str,
        reason: str,
        channel_id: str | None = None,
        linked_version_id: str | None = None,
    ) -> Disposition:
        self._material(material_id)
        kind = DispositionKind(kind)
        record = Disposition(
            self._next_id("disp"),
            material_id,
            kind,
            on,
            actor,
            reason,
            channel_id,
            linked_version_id,
        )
        self.store.add_disposition(record)
        if kind is DispositionKind.TAKEDOWN:
            for pub in list(self.store.publications):
                version = self.store.versions[pub.version_id]
                if version.material_id != material_id:
                    continue
                if channel_id is not None and pub.channel_id != channel_id:
                    continue
                if self.store.publication_live_at(pub, on):
                    self.store.add_publication_end(
                        PublicationEnd(pub.publication_id, on, record.disposition_id)
                    )
        return record

    def correct_material(
        self, material_id: str, on: date, claims, actor: str, reason: str, note: str = ""
    ) -> tuple[MaterialVersion, Disposition]:
        """修改素材：产生新版本并追加修改处置，旧版本保留可查。"""
        version = self.add_version(material_id, on, claims, note)
        disposition = self.record_disposition(
            material_id,
            DispositionKind.CORRECTION,
            on,
            actor,
            reason,
            linked_version_id=version.version_id,
        )
        return version, disposition

    # ------------------------------------------------------------------
    # 投诉登记
    # ------------------------------------------------------------------
    def file_complaint(
        self,
        product_id: str,
        channel_id: str,
        observed_on: date,
        description: str,
        quotes=(),
        complaint_id: str | None = None,
    ) -> Complaint:
        if product_id not in self.store.products:
            raise KeyError(f"未知产品：{product_id}")
        if channel_id not in self.store.channels:
            raise KeyError(f"未知渠道：{channel_id}")
        record = Complaint(
            complaint_id or self._next_id("cmp"),
            product_id,
            channel_id,
            observed_on,
            description,
            tuple(quotes),
        )
        self.store.add_complaint(record)
        return record

    # ------------------------------------------------------------------
    # 评估
    # ------------------------------------------------------------------
    def evaluate(self, version_id: str, channel_id: str, on: date) -> Evaluation:
        version = self._version(version_id)
        material = self.store.materials[version.material_id]
        product = self.store.products[material.product_id]
        assessments = tuple(
            self._assess_claim(product, claim, on) for claim in version.claims
        )
        required: set[str] = set()
        for claim in version.claims:
            required |= self.policy.required_roles.get(claim.category, frozenset())
        views = tuple(
            self._role_view(version, product, role, channel_id, on)
            for role in sorted(required)
        )
        issues = tuple(i for a in assessments for i in a.issues) + tuple(
            i for v in views for i in v.issues
        )
        return Evaluation(version_id, channel_id, on, issues, assessments, views)

    def prohibitions(
        self, product_type, claim: Claim, on: date
    ) -> tuple[RegulationHit, ...]:
        """指定日期适用于该表达的禁用规则（核对“当时适用”的法规）。"""
        hits = []
        series_ids = sorted({r.series_id for r in self.store.regulations.values()})
        for series_id in series_ids:
            regulation = self.store.current_regulation(series_id, on)
            if regulation is None:
                continue
            for rule in regulation.rules:
                if rule.product_type is not product_type:
                    continue
                if rule.category is not claim.category:
                    continue
                if rule.topic is not None and rule.topic is not claim.topic:
                    continue
                hits.append(RegulationHit(regulation, rule))
        return tuple(hits)

    def current_evidence(self, series_id: str, on: date) -> Evidence | None:
        return self.store.current_evidence(series_id, on)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _assess_claim(self, product: Product, claim: Claim, on: date) -> ClaimAssessment:
        issues: list[Issue] = []
        statuses: list[EvidenceStatus] = []
        for evidence_id in claim.evidence_ids:
            evidence = self.store.evidence.get(evidence_id)
            if evidence is None:
                issues.append(
                    Issue(
                        IssueCode.UNKNOWN_EVIDENCE,
                        f"表达「{claim.text}」绑定了不存在的证据 {evidence_id}",
                        claim.claim_id,
                    )
                )
                continue
            current = self.store.current_evidence(evidence.series_id, on)
            current_id = current.evidence_id if current else None
            superseded = current_id is not None and current_id != evidence.evidence_id
            if not evidence.covers(on):
                when = "尚未生效" if on < evidence.valid_from else "已过有效期"
                status = "not_yet_valid" if on < evidence.valid_from else "expired"
                issues.append(
                    Issue(
                        IssueCode.CLAIM_EVIDENCE_EXPIRED,
                        f"表达「{claim.text}」绑定的证据 {evidence.evidence_id}"
                        f"（{evidence.title}）在 {on} {when}",
                        claim.claim_id,
                    )
                )
            elif superseded:
                status = "superseded"
            else:
                status = "current"
            if superseded:
                issues.append(
                    Issue(
                        IssueCode.CLAIM_EVIDENCE_SUPERSEDED,
                        f"表达「{claim.text}」绑定的证据 {evidence.evidence_id}"
                        f"（{evidence.title}）在 {on} 已被 {current_id} 取代",
                        claim.claim_id,
                    )
                )
            statuses.append(EvidenceStatus(evidence, status, superseded, current_id))
        if not claim.evidence_ids:
            issues.append(
                Issue(
                    IssueCode.CLAIM_UNBOUND,
                    f"表达「{claim.text}」未绑定任何证据版本",
                    claim.claim_id,
                )
            )
        kinds = {s.evidence.kind for s in statuses}
        allowed = self.policy.topic_evidence.get(claim.topic, frozenset())
        if statuses and allowed and not (kinds & allowed):
            allowed_names = "、".join(sorted(k.value for k in allowed))
            issues.append(
                Issue(
                    IssueCode.CLAIM_EVIDENCE_KIND_MISMATCH,
                    f"表达「{claim.text}」（{claim.topic.value} 类）需要 {allowed_names}"
                    " 类证据之一支撑；注册商标或抽检合格不能单独放行该表达",
                    claim.claim_id,
                )
            )
        hits = self.prohibitions(product.product_type, claim, on)
        for hit in hits:
            issues.append(
                Issue(
                    IssueCode.CLAIM_PROHIBITED,
                    f"表达「{claim.text}」违反 {hit.regulation.name}"
                    f"（{hit.regulation.regulation_id}，{hit.rule.note}）",
                    claim.claim_id,
                )
            )
        return ClaimAssessment(claim, tuple(statuses), hits, tuple(issues))

    def _role_view(
        self,
        version: MaterialVersion,
        product: Product,
        role: str,
        channel_id: str,
        on: date,
    ) -> RoleApprovalView:
        records = tuple(
            a
            for a in self.store.approvals
            if a.version_id == version.version_id
            and a.role == role
            and a.decided_on >= version.created_on
        )
        latest = (
            max(records, key=lambda a: (a.decided_on, a.approval_id)) if records else None
        )
        issues: list[Issue] = []
        if latest is None:
            issues.append(
                Issue(
                    IssueCode.MISSING_APPROVAL,
                    f"版本 {version.version_id} 缺少 {role} 角色的审核",
                    role=role,
                )
            )
        elif latest.decision is Decision.REJECTED:
            issues.append(
                Issue(
                    IssueCode.REJECTED_APPROVAL,
                    f"{role} 角色于 {latest.decided_on} 驳回了版本 {version.version_id}",
                    role=role,
                )
            )
        else:
            if latest.channels and channel_id not in latest.channels:
                issues.append(
                    Issue(
                        IssueCode.APPROVAL_CHANNEL_MISMATCH,
                        f"{role} 角色的审核范围 {sorted(latest.channels)}"
                        f" 不含渠道 {channel_id}，跨渠道复用需重新审核",
                        role=role,
                    )
                )
            if self._approval_stale(latest, version, product, on):
                issues.append(
                    Issue(
                        IssueCode.STALE_APPROVAL,
                        f"{role} 角色于 {latest.decided_on} 的审核依据（证据或法规）"
                        f"在 {on} 前已发生变化，需复核",
                        role=role,
                    )
                )
        return RoleApprovalView(role, True, records, latest, tuple(issues))

    def _approval_stale(
        self,
        approval: Approval,
        version: MaterialVersion,
        product: Product,
        on: date,
    ) -> bool:
        """审核之后证据版本更替或法规边界变化，则该审核在 on 日失效。"""
        for claim in version.claims:
            for evidence_id in claim.evidence_ids:
                evidence = self.store.evidence.get(evidence_id)
                if evidence is None:
                    continue
                current = self.store.current_evidence(evidence.series_id, on)
                if (
                    current is not None
                    and current.evidence_id != evidence.evidence_id
                    and current.valid_from > approval.decided_on
                ):
                    return True
            now = bool(self.prohibitions(product.product_type, claim, on))
            then = bool(
                self.prohibitions(product.product_type, claim, approval.decided_on)
            )
            if now != then:
                return True
        return False

    def _version(self, version_id: str) -> MaterialVersion:
        try:
            return self.store.versions[version_id]
        except KeyError:
            raise KeyError(f"未知素材版本：{version_id}") from None

    def _material(self, material_id: str) -> Material:
        try:
            return self.store.materials[material_id]
        except KeyError:
            raise KeyError(f"未知素材：{material_id}") from None

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]}"
