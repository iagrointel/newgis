from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.epanet_importacao_contagens_type_0 import EpanetImportacaoContagensType0


T = TypeVar("T", bound="EpanetImportacao")


@_attrs_define
class EpanetImportacao:
    """
    Attributes:
        id (str):
        rede_id (str):
        estado (str):
        nome_arquivo (None | str):
        crs_epsg (int | None):
        arquivo_sha256 (str):
        arquivo_bytes_tamanho (int):
        job_id (None | str):
        contagens (EpanetImportacaoContagensType0 | None):
        avisos (list[Any] | None):
        erro (None | str):
        criado_em (str):
        atualizado_em (str):
    """

    id: str
    rede_id: str
    estado: str
    nome_arquivo: None | str
    crs_epsg: int | None
    arquivo_sha256: str
    arquivo_bytes_tamanho: int
    job_id: None | str
    contagens: EpanetImportacaoContagensType0 | None
    avisos: list[Any] | None
    erro: None | str
    criado_em: str
    atualizado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.epanet_importacao_contagens_type_0 import EpanetImportacaoContagensType0  # noqa: PLC0415

        id = self.id

        rede_id = self.rede_id

        estado = self.estado

        nome_arquivo: None | str
        nome_arquivo = self.nome_arquivo

        crs_epsg: int | None
        crs_epsg = self.crs_epsg

        arquivo_sha256 = self.arquivo_sha256

        arquivo_bytes_tamanho = self.arquivo_bytes_tamanho

        job_id: None | str
        job_id = self.job_id

        contagens: dict[str, Any] | None
        if isinstance(self.contagens, EpanetImportacaoContagensType0):
            contagens = self.contagens.to_dict()
        else:
            contagens = self.contagens

        avisos: list[Any] | None
        if isinstance(self.avisos, list):
            avisos = self.avisos

        else:
            avisos = self.avisos

        erro: None | str
        erro = self.erro

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "rede_id": rede_id,
                "estado": estado,
                "nome_arquivo": nome_arquivo,
                "crs_epsg": crs_epsg,
                "arquivo_sha256": arquivo_sha256,
                "arquivo_bytes_tamanho": arquivo_bytes_tamanho,
                "job_id": job_id,
                "contagens": contagens,
                "avisos": avisos,
                "erro": erro,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.epanet_importacao_contagens_type_0 import EpanetImportacaoContagensType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        rede_id = d.pop("rede_id")

        estado = d.pop("estado")

        def _parse_nome_arquivo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        nome_arquivo = _parse_nome_arquivo(d.pop("nome_arquivo"))

        def _parse_crs_epsg(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        crs_epsg = _parse_crs_epsg(d.pop("crs_epsg"))

        arquivo_sha256 = d.pop("arquivo_sha256")

        arquivo_bytes_tamanho = d.pop("arquivo_bytes_tamanho")

        def _parse_job_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        job_id = _parse_job_id(d.pop("job_id"))

        def _parse_contagens(data: object) -> EpanetImportacaoContagensType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                contagens_type_0 = EpanetImportacaoContagensType0.from_dict(data)

                return contagens_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EpanetImportacaoContagensType0 | None, data)

        contagens = _parse_contagens(d.pop("contagens"))

        def _parse_avisos(data: object) -> list[Any] | None:
            if data is None:
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                avisos_type_0 = cast(list[Any], data)

                return avisos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None, data)

        avisos = _parse_avisos(d.pop("avisos"))

        def _parse_erro(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        erro = _parse_erro(d.pop("erro"))

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        epanet_importacao = cls(
            id=id,
            rede_id=rede_id,
            estado=estado,
            nome_arquivo=nome_arquivo,
            crs_epsg=crs_epsg,
            arquivo_sha256=arquivo_sha256,
            arquivo_bytes_tamanho=arquivo_bytes_tamanho,
            job_id=job_id,
            contagens=contagens,
            avisos=avisos,
            erro=erro,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        epanet_importacao.additional_properties = d
        return epanet_importacao

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
