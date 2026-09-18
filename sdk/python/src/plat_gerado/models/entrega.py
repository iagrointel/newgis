from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.entrega_payload import EntregaPayload


T = TypeVar("T", bound="Entrega")


@_attrs_define
class Entrega:
    """
    Attributes:
        id (str):
        webhook_id (str):
        evento_id (int):
        tipo_evento (str):
        payload (EntregaPayload):
        estado (str):
        tentativas (int):
        reenvios (int):
        criado_em (str):
        ultima_status (int | None | Unset):
        ultima_erro (None | str | Unset):
        entregue_em (None | str | Unset):
    """

    id: str
    webhook_id: str
    evento_id: int
    tipo_evento: str
    payload: EntregaPayload
    estado: str
    tentativas: int
    reenvios: int
    criado_em: str
    ultima_status: int | None | Unset = UNSET
    ultima_erro: None | str | Unset = UNSET
    entregue_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        webhook_id = self.webhook_id

        evento_id = self.evento_id

        tipo_evento = self.tipo_evento

        payload = self.payload.to_dict()

        estado = self.estado

        tentativas = self.tentativas

        reenvios = self.reenvios

        criado_em = self.criado_em

        ultima_status: int | None | Unset
        if isinstance(self.ultima_status, Unset):
            ultima_status = UNSET
        else:
            ultima_status = self.ultima_status

        ultima_erro: None | str | Unset
        if isinstance(self.ultima_erro, Unset):
            ultima_erro = UNSET
        else:
            ultima_erro = self.ultima_erro

        entregue_em: None | str | Unset
        if isinstance(self.entregue_em, Unset):
            entregue_em = UNSET
        else:
            entregue_em = self.entregue_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "webhook_id": webhook_id,
                "evento_id": evento_id,
                "tipo_evento": tipo_evento,
                "payload": payload,
                "estado": estado,
                "tentativas": tentativas,
                "reenvios": reenvios,
                "criado_em": criado_em,
            }
        )
        if ultima_status is not UNSET:
            field_dict["ultima_status"] = ultima_status
        if ultima_erro is not UNSET:
            field_dict["ultima_erro"] = ultima_erro
        if entregue_em is not UNSET:
            field_dict["entregue_em"] = entregue_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.entrega_payload import EntregaPayload  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        webhook_id = d.pop("webhook_id")

        evento_id = d.pop("evento_id")

        tipo_evento = d.pop("tipo_evento")

        payload = EntregaPayload.from_dict(d.pop("payload"))

        estado = d.pop("estado")

        tentativas = d.pop("tentativas")

        reenvios = d.pop("reenvios")

        criado_em = d.pop("criado_em")

        def _parse_ultima_status(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ultima_status = _parse_ultima_status(d.pop("ultima_status", UNSET))

        def _parse_ultima_erro(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ultima_erro = _parse_ultima_erro(d.pop("ultima_erro", UNSET))

        def _parse_entregue_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        entregue_em = _parse_entregue_em(d.pop("entregue_em", UNSET))

        entrega = cls(
            id=id,
            webhook_id=webhook_id,
            evento_id=evento_id,
            tipo_evento=tipo_evento,
            payload=payload,
            estado=estado,
            tentativas=tentativas,
            reenvios=reenvios,
            criado_em=criado_em,
            ultima_status=ultima_status,
            ultima_erro=ultima_erro,
            entregue_em=entregue_em,
        )

        entrega.additional_properties = d
        return entrega

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
