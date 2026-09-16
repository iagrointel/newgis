from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.resultado_feicao_atributos_type_0 import ResultadoFeicaoAtributosType0


T = TypeVar("T", bound="ResultadoFeicao")


@_attrs_define
class ResultadoFeicao:
    """
    Attributes:
        sucesso (bool):
        id (None | str | Unset):
        fid (int | None | Unset):
        versao (int | None | Unset):
        atributos (None | ResultadoFeicaoAtributosType0 | Unset):
        erro (None | str | Unset):
        mensagem (None | str | Unset):
        detalhe (Any | Unset):
    """

    sucesso: bool
    id: None | str | Unset = UNSET
    fid: int | None | Unset = UNSET
    versao: int | None | Unset = UNSET
    atributos: None | ResultadoFeicaoAtributosType0 | Unset = UNSET
    erro: None | str | Unset = UNSET
    mensagem: None | str | Unset = UNSET
    detalhe: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.resultado_feicao_atributos_type_0 import ResultadoFeicaoAtributosType0  # noqa: PLC0415

        sucesso = self.sucesso

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        fid: int | None | Unset
        if isinstance(self.fid, Unset):
            fid = UNSET
        else:
            fid = self.fid

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        atributos: dict[str, Any] | None | Unset
        if isinstance(self.atributos, Unset):
            atributos = UNSET
        elif isinstance(self.atributos, ResultadoFeicaoAtributosType0):
            atributos = self.atributos.to_dict()
        else:
            atributos = self.atributos

        erro: None | str | Unset
        if isinstance(self.erro, Unset):
            erro = UNSET
        else:
            erro = self.erro

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        detalhe = self.detalhe

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sucesso": sucesso,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if fid is not UNSET:
            field_dict["fid"] = fid
        if versao is not UNSET:
            field_dict["versao"] = versao
        if atributos is not UNSET:
            field_dict["atributos"] = atributos
        if erro is not UNSET:
            field_dict["erro"] = erro
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if detalhe is not UNSET:
            field_dict["detalhe"] = detalhe

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resultado_feicao_atributos_type_0 import ResultadoFeicaoAtributosType0  # noqa: PLC0415

        d = dict(src_dict)
        sucesso = d.pop("sucesso")

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_fid(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fid = _parse_fid(d.pop("fid", UNSET))

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        def _parse_atributos(data: object) -> None | ResultadoFeicaoAtributosType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                atributos_type_0 = ResultadoFeicaoAtributosType0.from_dict(data)

                return atributos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ResultadoFeicaoAtributosType0 | Unset, data)

        atributos = _parse_atributos(d.pop("atributos", UNSET))

        def _parse_erro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        erro = _parse_erro(d.pop("erro", UNSET))

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        detalhe = d.pop("detalhe", UNSET)

        resultado_feicao = cls(
            sucesso=sucesso,
            id=id,
            fid=fid,
            versao=versao,
            atributos=atributos,
            erro=erro,
            mensagem=mensagem,
            detalhe=detalhe,
        )

        resultado_feicao.additional_properties = d
        return resultado_feicao

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
