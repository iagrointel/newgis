from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.visita_criar_dados import VisitaCriarDados


T = TypeVar("T", bound="VisitaCriar")


@_attrs_define
class VisitaCriar:
    """
    Attributes:
        cliente_uuid (str):
        camada_id (str):
        globalid (str):
        status (str):
        capturado_em (str):
        alvo_id (None | str | Unset):
        fila_id (None | str | Unset):
        roteiro_id (None | str | Unset):
        texto (None | str | Unset):
        lat (float | None | Unset):
        lon (float | None | Unset):
        gps_acc_m (float | None | Unset):
        dados (VisitaCriarDados | Unset):
    """

    cliente_uuid: str
    camada_id: str
    globalid: str
    status: str
    capturado_em: str
    alvo_id: None | str | Unset = UNSET
    fila_id: None | str | Unset = UNSET
    roteiro_id: None | str | Unset = UNSET
    texto: None | str | Unset = UNSET
    lat: float | None | Unset = UNSET
    lon: float | None | Unset = UNSET
    gps_acc_m: float | None | Unset = UNSET
    dados: VisitaCriarDados | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        cliente_uuid = self.cliente_uuid

        camada_id = self.camada_id

        globalid = self.globalid

        status = self.status

        capturado_em = self.capturado_em

        alvo_id: None | str | Unset
        if isinstance(self.alvo_id, Unset):
            alvo_id = UNSET
        else:
            alvo_id = self.alvo_id

        fila_id: None | str | Unset
        if isinstance(self.fila_id, Unset):
            fila_id = UNSET
        else:
            fila_id = self.fila_id

        roteiro_id: None | str | Unset
        if isinstance(self.roteiro_id, Unset):
            roteiro_id = UNSET
        else:
            roteiro_id = self.roteiro_id

        texto: None | str | Unset
        if isinstance(self.texto, Unset):
            texto = UNSET
        else:
            texto = self.texto

        lat: float | None | Unset
        if isinstance(self.lat, Unset):
            lat = UNSET
        else:
            lat = self.lat

        lon: float | None | Unset
        if isinstance(self.lon, Unset):
            lon = UNSET
        else:
            lon = self.lon

        gps_acc_m: float | None | Unset
        if isinstance(self.gps_acc_m, Unset):
            gps_acc_m = UNSET
        else:
            gps_acc_m = self.gps_acc_m

        dados: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dados, Unset):
            dados = self.dados.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "cliente_uuid": cliente_uuid,
                "camada_id": camada_id,
                "globalid": globalid,
                "status": status,
                "capturado_em": capturado_em,
            }
        )
        if alvo_id is not UNSET:
            field_dict["alvo_id"] = alvo_id
        if fila_id is not UNSET:
            field_dict["fila_id"] = fila_id
        if roteiro_id is not UNSET:
            field_dict["roteiro_id"] = roteiro_id
        if texto is not UNSET:
            field_dict["texto"] = texto
        if lat is not UNSET:
            field_dict["lat"] = lat
        if lon is not UNSET:
            field_dict["lon"] = lon
        if gps_acc_m is not UNSET:
            field_dict["gps_acc_m"] = gps_acc_m
        if dados is not UNSET:
            field_dict["dados"] = dados

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.visita_criar_dados import VisitaCriarDados  # noqa: PLC0415

        d = dict(src_dict)
        cliente_uuid = d.pop("cliente_uuid")

        camada_id = d.pop("camada_id")

        globalid = d.pop("globalid")

        status = d.pop("status")

        capturado_em = d.pop("capturado_em")

        def _parse_alvo_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        alvo_id = _parse_alvo_id(d.pop("alvo_id", UNSET))

        def _parse_fila_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fila_id = _parse_fila_id(d.pop("fila_id", UNSET))

        def _parse_roteiro_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        roteiro_id = _parse_roteiro_id(d.pop("roteiro_id", UNSET))

        def _parse_texto(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        texto = _parse_texto(d.pop("texto", UNSET))

        def _parse_lat(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        lat = _parse_lat(d.pop("lat", UNSET))

        def _parse_lon(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        lon = _parse_lon(d.pop("lon", UNSET))

        def _parse_gps_acc_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        gps_acc_m = _parse_gps_acc_m(d.pop("gps_acc_m", UNSET))

        _dados = d.pop("dados", UNSET)
        dados: VisitaCriarDados | Unset
        if isinstance(_dados, Unset):
            dados = UNSET
        else:
            dados = VisitaCriarDados.from_dict(_dados)

        visita_criar = cls(
            cliente_uuid=cliente_uuid,
            camada_id=camada_id,
            globalid=globalid,
            status=status,
            capturado_em=capturado_em,
            alvo_id=alvo_id,
            fila_id=fila_id,
            roteiro_id=roteiro_id,
            texto=texto,
            lat=lat,
            lon=lon,
            gps_acc_m=gps_acc_m,
            dados=dados,
        )

        return visita_criar
