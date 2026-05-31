from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatalogRef(BaseModel):
    kind: str
    name: str
    source: str | None = None


class AppInstallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    catalog_ref: CatalogRef = Field(alias="catalogRef")
    instance_name: str | None = Field(default=None, alias="instanceName")
    config: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, Any] = Field(default_factory=dict)


class ServiceInstallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    catalog_ref: CatalogRef = Field(alias="catalogRef")
    instance_name: str | None = Field(default=None, alias="instanceName")
    config: dict[str, Any] = Field(default_factory=dict)


class LifecycleActionRequest(BaseModel):
    force: bool = False
    confirm: str | None = None


class PlatformDomainCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    domain: str
    is_default: bool = Field(default=False, alias="default")


class PlatformDomainRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    domain: str
    is_default: bool = Field(alias="default")
    generation: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class ReconciliationRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    target_type: str = Field(alias="targetType")
    target_id: str = Field(alias="targetId")
    target_generation: int | None = Field(alias="targetGeneration")
    action: str
    state: str
    error: str | None = None
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class StatusRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    resource_type: str = Field(alias="resourceType")
    resource_id: str = Field(alias="resourceId")
    level: str
    lifecycle: str
    reconciliation: str
    reason: str
    message: str
    evidence: list[dict[str, Any]]
    observed_generation: int | None = Field(alias="observedGeneration")
    observed_at: str = Field(alias="observedAt")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class MutationEnvelope(BaseModel):
    resource: dict[str, Any]
    reconciliation: dict[str, Any]
    status: dict[str, Any] | None = None
