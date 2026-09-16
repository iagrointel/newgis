from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.extent_spatial_reference_type_0 import ExtentSpatialReferenceType0


T = TypeVar("T", bound="Extent")


@_attrs_define
class Extent:
    """Envelope da doc (buildExtent/extent). spatialReference é aceito e ignorado (SRID fixo).

    Attributes:
        xmin (float):
        ymin (float):
        xmax (float):
        ymax (float):
        spatial_reference (ExtentSpatialReferenceType0 | None | Unset):
    """

    xmin: float
    ymin: float
    xmax: float
    ymax: float
    spatial_reference: ExtentSpatialReferenceType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.extent_spatial_reference_type_0 import ExtentSpatialReferenceType0  # noqa: PLC0415

        xmin = self.xmin

        ymin = self.ymin

        xmax = self.xmax

        ymax = self.ymax

        spatial_reference: dict[str, Any] | None | Unset
        if isinstance(self.spatial_reference, Unset):
            spatial_reference = UNSET
        elif isinstance(self.spatial_reference, ExtentSpatialReferenceType0):
            spatial_reference = self.spatial_reference.to_dict()
        else:
            spatial_reference = self.spatial_reference

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
            }
        )
        if spatial_reference is not UNSET:
            field_dict["spatialReference"] = spatial_reference

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.extent_spatial_reference_type_0 import ExtentSpatialReferenceType0  # noqa: PLC0415

        d = dict(src_dict)
        xmin = d.pop("xmin")

        ymin = d.pop("ymin")

        xmax = d.pop("xmax")

        ymax = d.pop("ymax")

        def _parse_spatial_reference(data: object) -> ExtentSpatialReferenceType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                spatial_reference_type_0 = ExtentSpatialReferenceType0.from_dict(data)

                return spatial_reference_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ExtentSpatialReferenceType0 | None | Unset, data)

        spatial_reference = _parse_spatial_reference(d.pop("spatialReference", UNSET))

        extent = cls(
            xmin=xmin,
            ymin=ymin,
            xmax=xmax,
            ymax=ymax,
            spatial_reference=spatial_reference,
        )

        extent.additional_properties = d
        return extent

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
