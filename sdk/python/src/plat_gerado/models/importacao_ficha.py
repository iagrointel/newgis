from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.importacao_ficha_contagens_type_0 import ImportacaoFichaContagensType0
    from ..models.importacao_ficha_desvios_type_0 import ImportacaoFichaDesviosType0


T = TypeVar("T", bound="ImportacaoFicha")


@_attrs_define
class ImportacaoFicha:
    """
    Attributes:
        id (str):
        fonte (str):
        caminho (str):
        distribuidora (None | str):
        municipio (None | str):
        sha256 (str):
        licenca (None | str):
        aviso (None | str):
        estado (str):
        contagens (ImportacaoFichaContagensType0 | None):
        desvios (ImportacaoFichaDesviosType0 | None):
        erro (None | str):
        criado_em (str):
        concluido_em (None | str):
    """

    id: str
    fonte: str
    caminho: str
    distribuidora: None | str
    municipio: None | str
    sha256: str
    licenca: None | str
    aviso: None | str
    estado: str
    contagens: ImportacaoFichaContagensType0 | None
    desvios: ImportacaoFichaDesviosType0 | None
    erro: None | str
    criado_em: str
    concluido_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.importacao_ficha_contagens_type_0 import ImportacaoFichaContagensType0  # noqa: PLC0415
        from ..models.importacao_ficha_desvios_type_0 import ImportacaoFichaDesviosType0  # noqa: PLC0415

        id = self.id

        fonte = self.fonte

        caminho = self.caminho

        distribuidora: None | str
        distribuidora = self.distribuidora

        municipio: None | str
        municipio = self.municipio

        sha256 = self.sha256

        licenca: None | str
        licenca = self.licenca

        aviso: None | str
        aviso = self.aviso

        estado = self.estado

        contagens: dict[str, Any] | None
        if isinstance(self.contagens, ImportacaoFichaContagensType0):
            contagens = self.contagens.to_dict()
        else:
            contagens = self.contagens

        desvios: dict[str, Any] | None
        if isinstance(self.desvios, ImportacaoFichaDesviosType0):
            desvios = self.desvios.to_dict()
        else:
            desvios = self.desvios

        erro: None | str
        erro = self.erro

        criado_em = self.criado_em

        concluido_em: None | str
        concluido_em = self.concluido_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "fonte": fonte,
                "caminho": caminho,
                "distribuidora": distribuidora,
                "municipio": municipio,
                "sha256": sha256,
                "licenca": licenca,
                "aviso": aviso,
                "estado": estado,
                "contagens": contagens,
                "desvios": desvios,
                "erro": erro,
                "criado_em": criado_em,
                "concluido_em": concluido_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importacao_ficha_contagens_type_0 import ImportacaoFichaContagensType0  # noqa: PLC0415
        from ..models.importacao_ficha_desvios_type_0 import ImportacaoFichaDesviosType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        fonte = d.pop("fonte")

        caminho = d.pop("caminho")

        def _parse_distribuidora(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        distribuidora = _parse_distribuidora(d.pop("distribuidora"))

        def _parse_municipio(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        municipio = _parse_municipio(d.pop("municipio"))

        sha256 = d.pop("sha256")

        def _parse_licenca(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        licenca = _parse_licenca(d.pop("licenca"))

        def _parse_aviso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        aviso = _parse_aviso(d.pop("aviso"))

        estado = d.pop("estado")

        def _parse_contagens(data: object) -> ImportacaoFichaContagensType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                contagens_type_0 = ImportacaoFichaContagensType0.from_dict(data)

                return contagens_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ImportacaoFichaContagensType0 | None, data)

        contagens = _parse_contagens(d.pop("contagens"))

        def _parse_desvios(data: object) -> ImportacaoFichaDesviosType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                desvios_type_0 = ImportacaoFichaDesviosType0.from_dict(data)

                return desvios_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ImportacaoFichaDesviosType0 | None, data)

        desvios = _parse_desvios(d.pop("desvios"))

        def _parse_erro(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        erro = _parse_erro(d.pop("erro"))

        criado_em = d.pop("criado_em")

        def _parse_concluido_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        concluido_em = _parse_concluido_em(d.pop("concluido_em"))

        importacao_ficha = cls(
            id=id,
            fonte=fonte,
            caminho=caminho,
            distribuidora=distribuidora,
            municipio=municipio,
            sha256=sha256,
            licenca=licenca,
            aviso=aviso,
            estado=estado,
            contagens=contagens,
            desvios=desvios,
            erro=erro,
            criado_em=criado_em,
            concluido_em=concluido_em,
        )

        importacao_ficha.additional_properties = d
        return importacao_ficha

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
