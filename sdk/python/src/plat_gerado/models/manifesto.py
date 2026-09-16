from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.manifesto_medidas import ManifestoMedidas
    from ..models.manifesto_parametros import ManifestoParametros
    from ..models.manifesto_superficie import ManifestoSuperficie


T = TypeVar("T", bound="Manifesto")


@_attrs_define
class Manifesto:
    """
    Attributes:
        superficie (ManifestoSuperficie):
        parametros (ManifestoParametros):
        medidas (ManifestoMedidas):
    """

    superficie: ManifestoSuperficie
    parametros: ManifestoParametros
    medidas: ManifestoMedidas

    def to_dict(self) -> dict[str, Any]:
        superficie = self.superficie.to_dict()

        parametros = self.parametros.to_dict()

        medidas = self.medidas.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "superficie": superficie,
                "parametros": parametros,
                "medidas": medidas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.manifesto_medidas import ManifestoMedidas  # noqa: PLC0415
        from ..models.manifesto_parametros import ManifestoParametros  # noqa: PLC0415
        from ..models.manifesto_superficie import ManifestoSuperficie  # noqa: PLC0415

        d = dict(src_dict)
        superficie = ManifestoSuperficie.from_dict(d.pop("superficie"))

        parametros = ManifestoParametros.from_dict(d.pop("parametros"))

        medidas = ManifestoMedidas.from_dict(d.pop("medidas"))

        manifesto = cls(
            superficie=superficie,
            parametros=parametros,
            medidas=medidas,
        )

        return manifesto
