from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.inventario_detalhe_por_classificacao import InventarioDetalhePorClassificacao
    from ..models.inventario_detalhe_por_tipo_item import InventarioDetalhePorTipoItem
    from ..models.inventario_detalhe_retomada import InventarioDetalheRetomada
    from ..models.inventario_detalhe_totais import InventarioDetalheTotais


T = TypeVar("T", bound="InventarioDetalhe")


@_attrs_define
class InventarioDetalhe:
    """
    Attributes:
        id (str):
        conexao_id (str):
        estado (str):
        portal_url (str):
        criado_em (str):
        atualizado_em (str):
        portal_nome (None | str | Unset):
        portal_versao (None | str | Unset):
        totais (InventarioDetalheTotais | Unset):
        job_id (None | str | Unset):
        mensagem (None | str | Unset):
        portal_id (None | str | Unset):
        retomada (InventarioDetalheRetomada | Unset):
        por_tipo (list[InventarioDetalhePorTipoItem] | Unset):
        por_classificacao (InventarioDetalhePorClassificacao | Unset):
        grupos (int | Unset):  Default: 0.
        usuarios (int | Unset):  Default: 0.
    """

    id: str
    conexao_id: str
    estado: str
    portal_url: str
    criado_em: str
    atualizado_em: str
    portal_nome: None | str | Unset = UNSET
    portal_versao: None | str | Unset = UNSET
    totais: InventarioDetalheTotais | Unset = UNSET
    job_id: None | str | Unset = UNSET
    mensagem: None | str | Unset = UNSET
    portal_id: None | str | Unset = UNSET
    retomada: InventarioDetalheRetomada | Unset = UNSET
    por_tipo: list[InventarioDetalhePorTipoItem] | Unset = UNSET
    por_classificacao: InventarioDetalhePorClassificacao | Unset = UNSET
    grupos: int | Unset = 0
    usuarios: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        conexao_id = self.conexao_id

        estado = self.estado

        portal_url = self.portal_url

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        portal_nome: None | str | Unset
        if isinstance(self.portal_nome, Unset):
            portal_nome = UNSET
        else:
            portal_nome = self.portal_nome

        portal_versao: None | str | Unset
        if isinstance(self.portal_versao, Unset):
            portal_versao = UNSET
        else:
            portal_versao = self.portal_versao

        totais: dict[str, Any] | Unset = UNSET
        if not isinstance(self.totais, Unset):
            totais = self.totais.to_dict()

        job_id: None | str | Unset
        if isinstance(self.job_id, Unset):
            job_id = UNSET
        else:
            job_id = self.job_id

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        portal_id: None | str | Unset
        if isinstance(self.portal_id, Unset):
            portal_id = UNSET
        else:
            portal_id = self.portal_id

        retomada: dict[str, Any] | Unset = UNSET
        if not isinstance(self.retomada, Unset):
            retomada = self.retomada.to_dict()

        por_tipo: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.por_tipo, Unset):
            por_tipo = []
            for por_tipo_item_data in self.por_tipo:
                por_tipo_item = por_tipo_item_data.to_dict()
                por_tipo.append(por_tipo_item)

        por_classificacao: dict[str, Any] | Unset = UNSET
        if not isinstance(self.por_classificacao, Unset):
            por_classificacao = self.por_classificacao.to_dict()

        grupos = self.grupos

        usuarios = self.usuarios

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "conexao_id": conexao_id,
                "estado": estado,
                "portal_url": portal_url,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )
        if portal_nome is not UNSET:
            field_dict["portal_nome"] = portal_nome
        if portal_versao is not UNSET:
            field_dict["portal_versao"] = portal_versao
        if totais is not UNSET:
            field_dict["totais"] = totais
        if job_id is not UNSET:
            field_dict["job_id"] = job_id
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if portal_id is not UNSET:
            field_dict["portal_id"] = portal_id
        if retomada is not UNSET:
            field_dict["retomada"] = retomada
        if por_tipo is not UNSET:
            field_dict["por_tipo"] = por_tipo
        if por_classificacao is not UNSET:
            field_dict["por_classificacao"] = por_classificacao
        if grupos is not UNSET:
            field_dict["grupos"] = grupos
        if usuarios is not UNSET:
            field_dict["usuarios"] = usuarios

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inventario_detalhe_por_classificacao import InventarioDetalhePorClassificacao  # noqa: PLC0415
        from ..models.inventario_detalhe_por_tipo_item import InventarioDetalhePorTipoItem  # noqa: PLC0415
        from ..models.inventario_detalhe_retomada import InventarioDetalheRetomada  # noqa: PLC0415
        from ..models.inventario_detalhe_totais import InventarioDetalheTotais  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        conexao_id = d.pop("conexao_id")

        estado = d.pop("estado")

        portal_url = d.pop("portal_url")

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        def _parse_portal_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        portal_nome = _parse_portal_nome(d.pop("portal_nome", UNSET))

        def _parse_portal_versao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        portal_versao = _parse_portal_versao(d.pop("portal_versao", UNSET))

        _totais = d.pop("totais", UNSET)
        totais: InventarioDetalheTotais | Unset
        if isinstance(_totais, Unset):
            totais = UNSET
        else:
            totais = InventarioDetalheTotais.from_dict(_totais)

        def _parse_job_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        job_id = _parse_job_id(d.pop("job_id", UNSET))

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        def _parse_portal_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        portal_id = _parse_portal_id(d.pop("portal_id", UNSET))

        _retomada = d.pop("retomada", UNSET)
        retomada: InventarioDetalheRetomada | Unset
        if isinstance(_retomada, Unset):
            retomada = UNSET
        else:
            retomada = InventarioDetalheRetomada.from_dict(_retomada)

        _por_tipo = d.pop("por_tipo", UNSET)
        por_tipo: list[InventarioDetalhePorTipoItem] | Unset = UNSET
        if _por_tipo is not UNSET:
            por_tipo = []
            for por_tipo_item_data in _por_tipo:
                por_tipo_item = InventarioDetalhePorTipoItem.from_dict(por_tipo_item_data)

                por_tipo.append(por_tipo_item)

        _por_classificacao = d.pop("por_classificacao", UNSET)
        por_classificacao: InventarioDetalhePorClassificacao | Unset
        if isinstance(_por_classificacao, Unset):
            por_classificacao = UNSET
        else:
            por_classificacao = InventarioDetalhePorClassificacao.from_dict(_por_classificacao)

        grupos = d.pop("grupos", UNSET)

        usuarios = d.pop("usuarios", UNSET)

        inventario_detalhe = cls(
            id=id,
            conexao_id=conexao_id,
            estado=estado,
            portal_url=portal_url,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
            portal_nome=portal_nome,
            portal_versao=portal_versao,
            totais=totais,
            job_id=job_id,
            mensagem=mensagem,
            portal_id=portal_id,
            retomada=retomada,
            por_tipo=por_tipo,
            por_classificacao=por_classificacao,
            grupos=grupos,
            usuarios=usuarios,
        )

        inventario_detalhe.additional_properties = d
        return inventario_detalhe

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
