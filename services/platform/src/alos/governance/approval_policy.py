import json
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from alos.genesis.source import SourceRegistry, SourceUse


class ApprovalPolicyError(ValueError):
    """Raised when a deterministic approval policy is invalid or incomplete."""


class ApprovalPolicyStatus(StrEnum):
    PILOT = "PILOT"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"


class ApprovalTier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    required_role: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    maximum_amount: Decimal | None = Field(default=None, gt=0)
    sla_hours: int = Field(ge=1, le=720)


class PaymentApprovalPolicy(BaseModel):
    """Versioned single source of truth for deterministic payment routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    policy_id: str = Field(pattern=r"^ALOS-POL-[A-Z0-9-]{3,80}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: ApprovalPolicyStatus
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    business_owner: str = Field(pattern=r"^[A-Z][A-Z0-9_& -]{1,79}$")
    source_references: tuple[str, ...] = Field(min_length=1)
    production_effect: bool
    tiers: tuple[ApprovalTier, ...] = Field(min_length=1)

    @field_validator("source_references")
    @classmethod
    def validate_source_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("Referensi sumber approval policy tidak boleh kosong")
        if len(values) != len(set(values)):
            raise ValueError("Referensi sumber approval policy tidak boleh duplikat")
        return values

    @model_validator(mode="after")
    def validate_tiers(self) -> "PaymentApprovalPolicy":
        routes = [tier.route for tier in self.tiers]
        if len(routes) != len(set(routes)):
            raise ValueError("Route approval wajib unik")
        open_ended = [index for index, tier in enumerate(self.tiers) if tier.maximum_amount is None]
        if open_ended != [len(self.tiers) - 1]:
            raise ValueError("Hanya tier terakhir yang boleh tanpa maximum_amount")
        finite_limits = [
            tier.maximum_amount for tier in self.tiers if tier.maximum_amount is not None
        ]
        if finite_limits != sorted(finite_limits) or len(finite_limits) != len(set(finite_limits)):
            raise ValueError("maximum_amount wajib meningkat dan tidak duplikat")
        if self.status == ApprovalPolicyStatus.APPROVED and not self.production_effect:
            raise ValueError("Approval policy APPROVED wajib menyatakan production_effect")
        if self.status != ApprovalPolicyStatus.APPROVED and self.production_effect:
            raise ValueError("Hanya approval policy APPROVED yang boleh berefek production")
        return self

    def route_for(self, amount: Decimal) -> ApprovalTier:
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Nominal pembayaran wajib lebih besar dari nol")
        for tier in self.tiers:
            if tier.maximum_amount is None or amount <= tier.maximum_amount:
                return tier
        raise ApprovalPolicyError("Approval policy tidak memiliki tier penutup")


class PaymentApprovalPolicyRegistry:
    def __init__(self, definitions_root: Path) -> None:
        self._path = definitions_root / "policies" / "approval-levels" / "payment-request.json"
        self._sources = SourceRegistry(definitions_root)
        self._cache: PaymentApprovalPolicy | None = None

    def load(self, *, force_reload: bool = False) -> PaymentApprovalPolicy:
        if self._cache is not None and not force_reload:
            return self._cache
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            policy = PaymentApprovalPolicy.model_validate(payload)
            for reference in policy.source_references:
                self._sources.validate_references((reference,), SourceUse.TEST)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            if isinstance(exc, ApprovalPolicyError):
                raise
            raise ApprovalPolicyError(f"Payment approval policy tidak valid: {exc}") from exc
        self._cache = policy
        return policy
