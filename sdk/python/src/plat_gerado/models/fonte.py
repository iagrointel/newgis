from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dono import Dono
    from ..models.fonte_config import FonteConfig
    from ..models.fonte_esquema_destino_item import FonteEsquemaDestinoItem
    from ..models.fonte_mapeamento import FonteMapeamento
    from ..models.metrica import Metrica


T = TypeVar("T", bound="Fonte")


@_attrs_define
class Fonte:
    """
    Attributes:
        id (str):
        tipo (str):
        nome (str):
        estado (str):
        config (FonteConfig):
        mapeamento (FonteMapeamento):
        esquema_destino (list[FonteEsquemaDestinoItem]):
        limite_eventos_s (int):
        dono (Dono):
        metrica (Metrica):
        filtro (None | str | Unset):
        tem_credencial (bool | Unset):  Default: False.
        endereco_receptor (None | str | Unset):
        criado_em (None | str | Unset):
        atualizado_em (None | str | Unset):
    """

    id: str
    tipo: str
    nome: str
    estado: str
    config: FonteConfig
    mapeamento: FonteMapeamento
    esquema_destino: list[FonteEsquemaDestinoItem]
    limite_eventos_s: int
    dono: Dono
    metrica: Metrica
    filtro: None | str | Unset = UNSET
    tem_credencial: bool | Unset = False
    endereco_receptor: None | str | Unset = UNSET
    criado_em: None | str | Unset = UNSET
    atualizado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo = self.tipo

        nome = self.nome

        estado = self.estado

        config = self.config.to_dict()

        mapeamento = self.mapeamento.to_dict()

        esquema_destino = []
        for esquema_destino_item_data in self.esquema_destino:
            esquema_destino_item = esquema_destino_item_data.to_dict()
            esquema_destino.append(esquema_destino_item)

        limite_eventos_s = self.limite_eventos_s

        dono = self.dono.to_dict()

        metrica = self.metrica.to_dict()

        filtro: None | str | Unset
        if isinstance(self.filtro, Unset):
            filtro = UNSET
        else:
            filtro = self.filtro

        tem_credencial = self.tem_credencial

        endereco_receptor: None | str | Unset
        if isinstance(self.endereco_receptor, Unset):
            endereco_receptor = UNSET
        else:
            endereco_receptor = self.endereco_receptor

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        atualizado_em: None | str | Unset
        if isinstance(self.atualizado_em, Unset):
            atualizado_em = UNSET
        else:
            atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "nome": nome,
                "estado": estado,
                "config": config,
                "mapeamento": mapeamento,
                "esquema_destino": esquema_destino,
                "limite_eventos_s": limite_eventos_s,
                "dono": dono,
                "metrica": metrica,
            }
        )
        if filtro is not UNSET:
            field_dict["filtro"] = filtro
        if tem_credencial is not UNSET:
            field_dict["tem_credencial"] = tem_credencial
        if endereco_receptor is not UNSET:
            field_dict["endereco_receptor"] = endereco_receptor
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em
        if atualizado_em is not UNSET:
            field_dict["atualizado_em"] = atualizado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dono import Dono  # noqa: PLC0415
        from ..models.fonte_config import FonteConfig  # noqa: PLC0415
        from ..models.fonte_esquema_destino_item import FonteEsquemaDestinoItem  # noqa: PLC0415
        from ..models.fonte_mapeamento import FonteMapeamento  # noqa: PLC0415
        from ..models.metrica import Metrica  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        tipo = d.pop("tipo")

        nome = d.pop("nome")

        estado = d.pop("estado")

        config = FonteConfig.from_dict(d.pop("config"))

        mapeamento = FonteMapeamento.from_dict(d.pop("mapeamento"))

        esquema_destino = []
        _esquema_destino = d.pop("esquema_destino")
        for esquema_destino_item_data in _esquema_destino:
            esquema_destino_item = FonteEsquemaDestinoItem.from_dict(esquema_destino_item_data)

            esquema_destino.append(esquema_destino_item)

        limite_eventos_s = d.pop("limite_eventos_s")

        dono = Dono.from_dict(d.pop("dono"))

        metrica = Metrica.from_dict(d.pop("metrica"))

        def _parse_filtro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        filtro = _parse_filtro(d.pop("filtro", UNSET))

        tem_credencial = d.pop("tem_credencial", UNSET)

        def _parse_endereco_receptor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        endereco_receptor = _parse_endereco_receptor(d.pop("endereco_receptor", UNSET))

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        def _parse_atualizado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em", UNSET))

        fonte = cls(
            id=id,
            tipo=tipo,
            nome=nome,
            estado=estado,
            config=config,
            mapeamento=mapeamento,
            esquema_destino=esquema_destino,
            limite_eventos_s=limite_eventos_s,
            dono=dono,
            metrica=metrica,
            filtro=filtro,
            tem_credencial=tem_credencial,
            endereco_receptor=endereco_receptor,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        fonte.additional_properties = d
        return fonte

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
