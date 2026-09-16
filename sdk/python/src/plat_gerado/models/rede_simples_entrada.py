from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.atributo_rede import AtributoRede
    from ..models.rede_simples_entrada_mapa_direcao import RedeSimplesEntradaMapaDirecao


T = TypeVar("T", bound="RedeSimplesEntrada")


@_attrs_define
class RedeSimplesEntrada:
    """Criação de uma rede simples a partir de duas camadas do inquilino. `camada_ponto_id` é opcional: uma
    rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo). `campo_direcao` é o
    NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz os valores
    desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
    digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como digitalizada.

        Attributes:
            nome (str):
            disciplina (str):
            camada_linha_id (str):
            descricao (None | str | Unset):
            tolerancia_m (float | Unset):  Default: 0.05.
            camada_ponto_id (None | str | Unset):
            campo_direcao (None | str | Unset):
            mapa_direcao (RedeSimplesEntradaMapaDirecao | Unset):
            atributos_rede (list[AtributoRede] | Unset):
    """

    nome: str
    disciplina: str
    camada_linha_id: str
    descricao: None | str | Unset = UNSET
    tolerancia_m: float | Unset = 0.05
    camada_ponto_id: None | str | Unset = UNSET
    campo_direcao: None | str | Unset = UNSET
    mapa_direcao: RedeSimplesEntradaMapaDirecao | Unset = UNSET
    atributos_rede: list[AtributoRede] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        disciplina = self.disciplina

        camada_linha_id = self.camada_linha_id

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        tolerancia_m = self.tolerancia_m

        camada_ponto_id: None | str | Unset
        if isinstance(self.camada_ponto_id, Unset):
            camada_ponto_id = UNSET
        else:
            camada_ponto_id = self.camada_ponto_id

        campo_direcao: None | str | Unset
        if isinstance(self.campo_direcao, Unset):
            campo_direcao = UNSET
        else:
            campo_direcao = self.campo_direcao

        mapa_direcao: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapa_direcao, Unset):
            mapa_direcao = self.mapa_direcao.to_dict()

        atributos_rede: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.atributos_rede, Unset):
            atributos_rede = []
            for atributos_rede_item_data in self.atributos_rede:
                atributos_rede_item = atributos_rede_item_data.to_dict()
                atributos_rede.append(atributos_rede_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "disciplina": disciplina,
                "camada_linha_id": camada_linha_id,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if tolerancia_m is not UNSET:
            field_dict["tolerancia_m"] = tolerancia_m
        if camada_ponto_id is not UNSET:
            field_dict["camada_ponto_id"] = camada_ponto_id
        if campo_direcao is not UNSET:
            field_dict["campo_direcao"] = campo_direcao
        if mapa_direcao is not UNSET:
            field_dict["mapa_direcao"] = mapa_direcao
        if atributos_rede is not UNSET:
            field_dict["atributos_rede"] = atributos_rede

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.atributo_rede import AtributoRede  # noqa: PLC0415
        from ..models.rede_simples_entrada_mapa_direcao import RedeSimplesEntradaMapaDirecao  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        disciplina = d.pop("disciplina")

        camada_linha_id = d.pop("camada_linha_id")

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        tolerancia_m = d.pop("tolerancia_m", UNSET)

        def _parse_camada_ponto_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        camada_ponto_id = _parse_camada_ponto_id(d.pop("camada_ponto_id", UNSET))

        def _parse_campo_direcao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        campo_direcao = _parse_campo_direcao(d.pop("campo_direcao", UNSET))

        _mapa_direcao = d.pop("mapa_direcao", UNSET)
        mapa_direcao: RedeSimplesEntradaMapaDirecao | Unset
        if isinstance(_mapa_direcao, Unset):
            mapa_direcao = UNSET
        else:
            mapa_direcao = RedeSimplesEntradaMapaDirecao.from_dict(_mapa_direcao)

        _atributos_rede = d.pop("atributos_rede", UNSET)
        atributos_rede: list[AtributoRede] | Unset = UNSET
        if _atributos_rede is not UNSET:
            atributos_rede = []
            for atributos_rede_item_data in _atributos_rede:
                atributos_rede_item = AtributoRede.from_dict(atributos_rede_item_data)

                atributos_rede.append(atributos_rede_item)

        rede_simples_entrada = cls(
            nome=nome,
            disciplina=disciplina,
            camada_linha_id=camada_linha_id,
            descricao=descricao,
            tolerancia_m=tolerancia_m,
            camada_ponto_id=camada_ponto_id,
            campo_direcao=campo_direcao,
            mapa_direcao=mapa_direcao,
            atributos_rede=atributos_rede,
        )

        rede_simples_entrada.additional_properties = d
        return rede_simples_entrada

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
