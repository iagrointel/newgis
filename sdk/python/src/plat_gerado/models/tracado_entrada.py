from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ponto_tracado import PontoTracado


T = TypeVar("T", bound="TracadoEntrada")


@_attrs_define
class TracadoEntrada:
    """`tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda pela direção de fluxo declarada em
    atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`; `tipo=caminho_curto` (item L4-02-d)
    exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e `tipo=isolados` não
    exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na rota, não aqui,
    porque cada tipo tem uma exigência diferente sobre a MESMA lista.

        Attributes:
            tipo (None | str | Unset):
            config_id (None | str | Unset):
            pontos_partida (list[PontoTracado] | Unset):
            destino (None | PontoTracado | Unset):
            barreiras (list[PontoTracado] | Unset):
            atributo_custo (None | str | Unset):
            k (int | Unset):  Default: 1.
            categoria_controlador (str | Unset):  Default: 'fonte'.
            origem_direcao (str | Unset):  Default: 'auto'.
    """

    tipo: None | str | Unset = UNSET
    config_id: None | str | Unset = UNSET
    pontos_partida: list[PontoTracado] | Unset = UNSET
    destino: None | PontoTracado | Unset = UNSET
    barreiras: list[PontoTracado] | Unset = UNSET
    atributo_custo: None | str | Unset = UNSET
    k: int | Unset = 1
    categoria_controlador: str | Unset = "fonte"
    origem_direcao: str | Unset = "auto"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.ponto_tracado import PontoTracado  # noqa: PLC0415

        tipo: None | str | Unset
        if isinstance(self.tipo, Unset):
            tipo = UNSET
        else:
            tipo = self.tipo

        config_id: None | str | Unset
        if isinstance(self.config_id, Unset):
            config_id = UNSET
        else:
            config_id = self.config_id

        pontos_partida: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.pontos_partida, Unset):
            pontos_partida = []
            for pontos_partida_item_data in self.pontos_partida:
                pontos_partida_item = pontos_partida_item_data.to_dict()
                pontos_partida.append(pontos_partida_item)

        destino: dict[str, Any] | None | Unset
        if isinstance(self.destino, Unset):
            destino = UNSET
        elif isinstance(self.destino, PontoTracado):
            destino = self.destino.to_dict()
        else:
            destino = self.destino

        barreiras: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.barreiras, Unset):
            barreiras = []
            for barreiras_item_data in self.barreiras:
                barreiras_item = barreiras_item_data.to_dict()
                barreiras.append(barreiras_item)

        atributo_custo: None | str | Unset
        if isinstance(self.atributo_custo, Unset):
            atributo_custo = UNSET
        else:
            atributo_custo = self.atributo_custo

        k = self.k

        categoria_controlador = self.categoria_controlador

        origem_direcao = self.origem_direcao

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if config_id is not UNSET:
            field_dict["config_id"] = config_id
        if pontos_partida is not UNSET:
            field_dict["pontos_partida"] = pontos_partida
        if destino is not UNSET:
            field_dict["destino"] = destino
        if barreiras is not UNSET:
            field_dict["barreiras"] = barreiras
        if atributo_custo is not UNSET:
            field_dict["atributo_custo"] = atributo_custo
        if k is not UNSET:
            field_dict["k"] = k
        if categoria_controlador is not UNSET:
            field_dict["categoria_controlador"] = categoria_controlador
        if origem_direcao is not UNSET:
            field_dict["origem_direcao"] = origem_direcao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ponto_tracado import PontoTracado  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tipo = _parse_tipo(d.pop("tipo", UNSET))

        def _parse_config_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        config_id = _parse_config_id(d.pop("config_id", UNSET))

        _pontos_partida = d.pop("pontos_partida", UNSET)
        pontos_partida: list[PontoTracado] | Unset = UNSET
        if _pontos_partida is not UNSET:
            pontos_partida = []
            for pontos_partida_item_data in _pontos_partida:
                pontos_partida_item = PontoTracado.from_dict(pontos_partida_item_data)

                pontos_partida.append(pontos_partida_item)

        def _parse_destino(data: object) -> None | PontoTracado | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                destino_type_0 = PontoTracado.from_dict(data)

                return destino_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PontoTracado | Unset, data)

        destino = _parse_destino(d.pop("destino", UNSET))

        _barreiras = d.pop("barreiras", UNSET)
        barreiras: list[PontoTracado] | Unset = UNSET
        if _barreiras is not UNSET:
            barreiras = []
            for barreiras_item_data in _barreiras:
                barreiras_item = PontoTracado.from_dict(barreiras_item_data)

                barreiras.append(barreiras_item)

        def _parse_atributo_custo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atributo_custo = _parse_atributo_custo(d.pop("atributo_custo", UNSET))

        k = d.pop("k", UNSET)

        categoria_controlador = d.pop("categoria_controlador", UNSET)

        origem_direcao = d.pop("origem_direcao", UNSET)

        tracado_entrada = cls(
            tipo=tipo,
            config_id=config_id,
            pontos_partida=pontos_partida,
            destino=destino,
            barreiras=barreiras,
            atributo_custo=atributo_custo,
            k=k,
            categoria_controlador=categoria_controlador,
            origem_direcao=origem_direcao,
        )

        tracado_entrada.additional_properties = d
        return tracado_entrada

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
