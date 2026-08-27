from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RegionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    state_fips: list[str] = Field(min_length=1)
    counties: list[str] = Field(min_length=1)
    layers: list[str] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)

    @field_validator("state_fips")
    @classmethod
    def state_fips_are_two_digits(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) != 2 or not value.isdigit():
                raise ValueError("state_fips values must be two-digit FIPS codes")
        return values

    @field_validator("counties")
    @classmethod
    def counties_are_five_digits(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) != 5 or not value.isdigit():
                raise ValueError("counties values must be five-digit county FIPS codes")
        return values


Grain = Literal["tract", "listing", "both"]
ListingReduction = Literal[
    "point",
    "buffer_100m",
    "buffer_300m",
    "buffer_500m",
    "point_in_polygon",
    "distance_to_nearest",
]
ReductionMethod = Literal[
    "zonal_mean",
    "zonal_share",
    "threshold_share",
    "direct_join",
    "housing_unit_weighted",
    "area_weighted",
    "idw",
    "nearest_distance",
    "source_density",
    "buffer_count",
    "line_density",
    "route_matrix",
]
Direction = Literal["higher_better", "lower_better", "neutral"]


class LayerManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_urls: list[str] = Field(min_length=1)
    vintage: str = Field(min_length=1)
    units: str | None = None
    direction: Direction = "neutral"
    native_resolution: str = Field(min_length=1)
    allowed_range: tuple[float, float]
    reduction_method: ReductionMethod
    coverage_threshold: float = Field(ge=0, le=1)
    grains: list[Grain] = Field(min_length=1)
    listing_reductions: list[ListingReduction] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("allowed_range")
    @classmethod
    def range_is_ordered(cls, value: tuple[float, float]) -> tuple[float, float]:
        if value[0] >= value[1]:
            raise ValueError("allowed_range minimum must be less than maximum")
        return value

    @field_validator("listing_reductions")
    @classmethod
    def listing_reductions_require_listing_grain(
        cls, values: list[ListingReduction], info: Any
    ) -> list[ListingReduction]:
        grains = info.data.get("grains", [])
        if values and "listing" not in grains and "both" not in grains:
            raise ValueError("listing_reductions require listing or both grain")
        return values


ManifestT = TypeVar("ManifestT", bound=BaseModel)


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def load_manifest(path: Path, model: type[ManifestT]) -> ManifestT:
    return model.model_validate(_read_yaml(path))


def load_region_manifest(path: Path) -> RegionManifest:
    return load_manifest(path, RegionManifest)


def load_layer_manifest(path: Path) -> LayerManifest:
    return load_manifest(path, LayerManifest)
