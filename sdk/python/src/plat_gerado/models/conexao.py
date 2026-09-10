from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conexao_config import ConexaoConfig
    from ..models.dono import Dono


T = TypeVar("T", bound="Conexao")


@_attrs_define
class Conexao:
    """
    Attributes:
        id (str):
        tipo (str):
        modo (str):
        nome (str):
        url (str):
        saude (str):
        config (ConexaoConfig):
        tem_credencial (bool):
        dono (Dono):
        criado_em (str):
        atualizado_em (str):
        saude_verificada_em (None | str | Unset):
        estado_saude (str | Unset):  Default: 'nunca_testada'.
        disponibilidade_30d_pct (float | None | Unset):
        disponibilidade_30d_total (int | Unset):  Default: 0.
        saude_mensagem (None | str | Unset):
        saude_latencia_ms (int | None | Unset):
    """

    id: str
    tipo: str
    modo: str
    nome: str
    url: str
    saude: str
    config: ConexaoConfig
    tem_credencial: bool
    dono: Dono
    criado_em: str
    atualizado_em: str
    saude_verificada_em: None | str | Unset = UNSET
    estado_saude: str | Unset = "nunca_testada"
    disponibilidade_30d_pct: float | None | Unset = UNSET
    disponibilidade_30d_total: int | Unset = 0
    saude_mensagem: None | str | Unset = UNSET
    saude_latencia_ms: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        tipo = self.tipo

        modo = self.modo

        nome = self.nome

        url = self.url

        saude = self.saude

        config = self.config.to_dict()

        tem_credencial = self.tem_credencial

        dono = self.dono.to_dict()

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        saude_verificada_em: None | str | Unset
        if isinstance(self.saude_verificada_em, Unset):
            saude_verificada_em = UNSET
        else:
            saude_verificada_em = self.saude_verificada_em

        estado_saude = self.estado_saude

        disponibilidade_30d_pct: float | None | Unset
        if isinstance(self.disponibilidade_30d_pct, Unset):
            disponibilidade_30d_pct = UNSET
        else:
            disponibilidade_30d_pct = self.disponibilidade_30d_pct

        disponibilidade_30d_total = self.disponibilidade_30d_total

        saude_mensagem: None | str | Unset
        if isinstance(self.saude_mensagem, Unset):
            saude_mensagem = UNSET
        else:
            saude_mensagem = self.saude_mensagem

        saude_latencia_ms: int | None | Unset
        if isinstance(self.saude_latencia_ms, Unset):
            saude_latencia_ms = UNSET
        else:
            saude_latencia_ms = self.saude_latencia_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "tipo": tipo,
                "modo": modo,
                "nome": nome,
                "url": url,
                "saude": saude,
                "config": config,
                "tem_credencial": tem_credencial,
                "dono": dono,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )
        if saude_verificada_em is not UNSET:
            field_dict["saude_verificada_em"] = saude_verificada_em
        if estado_saude is not UNSET:
            field_dict["estado_saude"] = estado_saude
        if disponibilidade_30d_pct is not UNSET:
            field_dict["disponibilidade_30d_pct"] = disponibilidade_30d_pct
        if disponibilidade_30d_total is not UNSET:
            field_dict["disponibilidade_30d_total"] = disponibilidade_30d_total
        if saude_mensagem is not UNSET:
            field_dict["saude_mensagem"] = saude_mensagem
        if saude_latencia_ms is not UNSET:
            field_dict["saude_latencia_ms"] = saude_latencia_ms

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conexao_config import ConexaoConfig  # noqa: PLC0415
        from ..models.dono import Dono  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        tipo = d.pop("tipo")

        modo = d.pop("modo")

        nome = d.pop("nome")

        url = d.pop("url")

        saude = d.pop("saude")

        config = ConexaoConfig.from_dict(d.pop("config"))

        tem_credencial = d.pop("tem_credencial")

        dono = Dono.from_dict(d.pop("dono"))

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        def _parse_saude_verificada_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        saude_verificada_em = _parse_saude_verificada_em(d.pop("saude_verificada_em", UNSET))

        estado_saude = d.pop("estado_saude", UNSET)

        def _parse_disponibilidade_30d_pct(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        disponibilidade_30d_pct = _parse_disponibilidade_30d_pct(d.pop("disponibilidade_30d_pct", UNSET))

        disponibilidade_30d_total = d.pop("disponibilidade_30d_total", UNSET)

        def _parse_saude_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        saude_mensagem = _parse_saude_mensagem(d.pop("saude_mensagem", UNSET))

        def _parse_saude_latencia_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        saude_latencia_ms = _parse_saude_latencia_ms(d.pop("saude_latencia_ms", UNSET))

        conexao = cls(
            id=id,
            tipo=tipo,
            modo=modo,
            nome=nome,
            url=url,
            saude=saude,
            config=config,
            tem_credencial=tem_credencial,
            dono=dono,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
            saude_verificada_em=saude_verificada_em,
            estado_saude=estado_saude,
            disponibilidade_30d_pct=disponibilidade_30d_pct,
            disponibilidade_30d_total=disponibilidade_30d_total,
            saude_mensagem=saude_mensagem,
            saude_latencia_ms=saude_latencia_ms,
        )

        conexao.additional_properties = d
        return conexao

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
