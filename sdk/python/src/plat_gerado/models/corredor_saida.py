from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.corredor_saida_corredor_type_0 import CorredorSaidaCorredorType0
    from ..models.corredor_saida_linha import CorredorSaidaLinha
    from ..models.manifesto import Manifesto


T = TypeVar("T", bound="CorredorSaida")


@_attrs_define
class CorredorSaida:
    """
    Attributes:
        execucao_id (str):
        linha (CorredorSaidaLinha): LineString GeoJSON em EPSG:4326 pelo centro das células
        corredor_celulas (int):
        manifesto (Manifesto):
        duracao_ms (int):
        corredor (CorredorSaidaCorredorType0 | None | Unset): MultiPolygon GeoJSON do corredor-epsilon, quando cabe
        corredor_geometria_omitida (bool | Unset): corredor acima de 20000 células: só a contagem Default: False.
    """

    execucao_id: str
    linha: CorredorSaidaLinha
    corredor_celulas: int
    manifesto: Manifesto
    duracao_ms: int
    corredor: CorredorSaidaCorredorType0 | None | Unset = UNSET
    corredor_geometria_omitida: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.corredor_saida_corredor_type_0 import CorredorSaidaCorredorType0  # noqa: PLC0415

        execucao_id = self.execucao_id

        linha = self.linha.to_dict()

        corredor_celulas = self.corredor_celulas

        manifesto = self.manifesto.to_dict()

        duracao_ms = self.duracao_ms

        corredor: dict[str, Any] | None | Unset
        if isinstance(self.corredor, Unset):
            corredor = UNSET
        elif isinstance(self.corredor, CorredorSaidaCorredorType0):
            corredor = self.corredor.to_dict()
        else:
            corredor = self.corredor

        corredor_geometria_omitida = self.corredor_geometria_omitida

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "execucao_id": execucao_id,
                "linha": linha,
                "corredor_celulas": corredor_celulas,
                "manifesto": manifesto,
                "duracao_ms": duracao_ms,
            }
        )
        if corredor is not UNSET:
            field_dict["corredor"] = corredor
        if corredor_geometria_omitida is not UNSET:
            field_dict["corredor_geometria_omitida"] = corredor_geometria_omitida

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.corredor_saida_corredor_type_0 import CorredorSaidaCorredorType0  # noqa: PLC0415
        from ..models.corredor_saida_linha import CorredorSaidaLinha  # noqa: PLC0415
        from ..models.manifesto import Manifesto  # noqa: PLC0415

        d = dict(src_dict)
        execucao_id = d.pop("execucao_id")

        linha = CorredorSaidaLinha.from_dict(d.pop("linha"))

        corredor_celulas = d.pop("corredor_celulas")

        manifesto = Manifesto.from_dict(d.pop("manifesto"))

        duracao_ms = d.pop("duracao_ms")

        def _parse_corredor(data: object) -> CorredorSaidaCorredorType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                corredor_type_0 = CorredorSaidaCorredorType0.from_dict(data)

                return corredor_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CorredorSaidaCorredorType0 | None | Unset, data)

        corredor = _parse_corredor(d.pop("corredor", UNSET))

        corredor_geometria_omitida = d.pop("corredor_geometria_omitida", UNSET)

        corredor_saida = cls(
            execucao_id=execucao_id,
            linha=linha,
            corredor_celulas=corredor_celulas,
            manifesto=manifesto,
            duracao_ms=duracao_ms,
            corredor=corredor,
            corredor_geometria_omitida=corredor_geometria_omitida,
        )

        return corredor_saida
