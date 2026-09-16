from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.importacao_osm_resultado_contagens import ImportacaoOsmResultadoContagens
    from ..models.importacao_osm_resultado_desvios import ImportacaoOsmResultadoDesvios
    from ..models.importacao_osm_resultado_fora_do_limite import ImportacaoOsmResultadoForaDoLimite


T = TypeVar("T", bound="ImportacaoOsmResultado")


@_attrs_define
class ImportacaoOsmResultado:
    """
    Attributes:
        rede_id (str):
        licenca (str):
        aviso (str):
        contagens (ImportacaoOsmResultadoContagens):
        trechos_gerados (int):
        fixacoes (int):
        fora_do_limite (ImportacaoOsmResultadoForaDoLimite):
        desvios (ImportacaoOsmResultadoDesvios):
        duracao_ms (int):
        conferido (bool):
        importacao_id (None | str):
    """

    rede_id: str
    licenca: str
    aviso: str
    contagens: ImportacaoOsmResultadoContagens
    trechos_gerados: int
    fixacoes: int
    fora_do_limite: ImportacaoOsmResultadoForaDoLimite
    desvios: ImportacaoOsmResultadoDesvios
    duracao_ms: int
    conferido: bool
    importacao_id: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        licenca = self.licenca

        aviso = self.aviso

        contagens = self.contagens.to_dict()

        trechos_gerados = self.trechos_gerados

        fixacoes = self.fixacoes

        fora_do_limite = self.fora_do_limite.to_dict()

        desvios = self.desvios.to_dict()

        duracao_ms = self.duracao_ms

        conferido = self.conferido

        importacao_id: None | str
        importacao_id = self.importacao_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "licenca": licenca,
                "aviso": aviso,
                "contagens": contagens,
                "trechos_gerados": trechos_gerados,
                "fixacoes": fixacoes,
                "fora_do_limite": fora_do_limite,
                "desvios": desvios,
                "duracao_ms": duracao_ms,
                "conferido": conferido,
                "importacao_id": importacao_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importacao_osm_resultado_contagens import ImportacaoOsmResultadoContagens  # noqa: PLC0415
        from ..models.importacao_osm_resultado_desvios import ImportacaoOsmResultadoDesvios  # noqa: PLC0415
        from ..models.importacao_osm_resultado_fora_do_limite import ImportacaoOsmResultadoForaDoLimite  # noqa: PLC0415

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        licenca = d.pop("licenca")

        aviso = d.pop("aviso")

        contagens = ImportacaoOsmResultadoContagens.from_dict(d.pop("contagens"))

        trechos_gerados = d.pop("trechos_gerados")

        fixacoes = d.pop("fixacoes")

        fora_do_limite = ImportacaoOsmResultadoForaDoLimite.from_dict(d.pop("fora_do_limite"))

        desvios = ImportacaoOsmResultadoDesvios.from_dict(d.pop("desvios"))

        duracao_ms = d.pop("duracao_ms")

        conferido = d.pop("conferido")

        def _parse_importacao_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        importacao_id = _parse_importacao_id(d.pop("importacao_id"))

        importacao_osm_resultado = cls(
            rede_id=rede_id,
            licenca=licenca,
            aviso=aviso,
            contagens=contagens,
            trechos_gerados=trechos_gerados,
            fixacoes=fixacoes,
            fora_do_limite=fora_do_limite,
            desvios=desvios,
            duracao_ms=duracao_ms,
            conferido=conferido,
            importacao_id=importacao_id,
        )

        importacao_osm_resultado.additional_properties = d
        return importacao_osm_resultado

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
