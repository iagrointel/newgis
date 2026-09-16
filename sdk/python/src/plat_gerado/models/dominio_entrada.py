from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.intervalo import Intervalo
    from ..models.valor_codificado import ValorCodificado


T = TypeVar("T", bound="DominioEntrada")


@_attrs_define
class DominioEntrada:
    """
    Attributes:
        nome (str):
        tipo (str):
        tipo_campo (str):
        valores (Intervalo | list[ValorCodificado]):
        descricao (None | str | Unset):
    """

    nome: str
    tipo: str
    tipo_campo: str
    valores: Intervalo | list[ValorCodificado]
    descricao: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        tipo = self.tipo

        tipo_campo = self.tipo_campo

        valores: dict[str, Any] | list[dict[str, Any]]
        if isinstance(self.valores, list):
            valores = []
            for valores_type_0_item_data in self.valores:
                valores_type_0_item = valores_type_0_item_data.to_dict()
                valores.append(valores_type_0_item)

        else:
            valores = self.valores.to_dict()

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "tipo": tipo,
                "tipo_campo": tipo_campo,
                "valores": valores,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.intervalo import Intervalo  # noqa: PLC0415
        from ..models.valor_codificado import ValorCodificado  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        tipo = d.pop("tipo")

        tipo_campo = d.pop("tipo_campo")

        def _parse_valores(data: object) -> Intervalo | list[ValorCodificado]:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                valores_type_0 = []
                _valores_type_0 = data
                for valores_type_0_item_data in _valores_type_0:
                    valores_type_0_item = ValorCodificado.from_dict(valores_type_0_item_data)

                    valores_type_0.append(valores_type_0_item)

                return valores_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            valores_type_1 = Intervalo.from_dict(data)

            return valores_type_1

        valores = _parse_valores(d.pop("valores"))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        dominio_entrada = cls(
            nome=nome,
            tipo=tipo,
            tipo_campo=tipo_campo,
            valores=valores,
            descricao=descricao,
        )

        return dominio_entrada
