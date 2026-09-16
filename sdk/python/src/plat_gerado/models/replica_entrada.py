from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.camada_entrada import CamadaEntrada
    from ..models.replica_entrada_extensao_type_0 import ReplicaEntradaExtensaoType0


T = TypeVar("T", bound="ReplicaEntrada")


@_attrs_define
class ReplicaEntrada:
    """
    Attributes:
        nome (str):
        camadas (list[CamadaEntrada]):
        dispositivo (None | str | Unset):
        politica_conflito (str | Unset):  Default: 'servidor_vence'.
        extensao (None | ReplicaEntradaExtensaoType0 | Unset):
        anexos (bool | Unset):  Default: False.
    """

    nome: str
    camadas: list[CamadaEntrada]
    dispositivo: None | str | Unset = UNSET
    politica_conflito: str | Unset = "servidor_vence"
    extensao: None | ReplicaEntradaExtensaoType0 | Unset = UNSET
    anexos: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.replica_entrada_extensao_type_0 import ReplicaEntradaExtensaoType0  # noqa: PLC0415

        nome = self.nome

        camadas = []
        for camadas_item_data in self.camadas:
            camadas_item = camadas_item_data.to_dict()
            camadas.append(camadas_item)

        dispositivo: None | str | Unset
        if isinstance(self.dispositivo, Unset):
            dispositivo = UNSET
        else:
            dispositivo = self.dispositivo

        politica_conflito = self.politica_conflito

        extensao: dict[str, Any] | None | Unset
        if isinstance(self.extensao, Unset):
            extensao = UNSET
        elif isinstance(self.extensao, ReplicaEntradaExtensaoType0):
            extensao = self.extensao.to_dict()
        else:
            extensao = self.extensao

        anexos = self.anexos

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "camadas": camadas,
            }
        )
        if dispositivo is not UNSET:
            field_dict["dispositivo"] = dispositivo
        if politica_conflito is not UNSET:
            field_dict["politica_conflito"] = politica_conflito
        if extensao is not UNSET:
            field_dict["extensao"] = extensao
        if anexos is not UNSET:
            field_dict["anexos"] = anexos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.camada_entrada import CamadaEntrada  # noqa: PLC0415
        from ..models.replica_entrada_extensao_type_0 import ReplicaEntradaExtensaoType0  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        camadas = []
        _camadas = d.pop("camadas")
        for camadas_item_data in _camadas:
            camadas_item = CamadaEntrada.from_dict(camadas_item_data)

            camadas.append(camadas_item)

        def _parse_dispositivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dispositivo = _parse_dispositivo(d.pop("dispositivo", UNSET))

        politica_conflito = d.pop("politica_conflito", UNSET)

        def _parse_extensao(data: object) -> None | ReplicaEntradaExtensaoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extensao_type_0 = ReplicaEntradaExtensaoType0.from_dict(data)

                return extensao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ReplicaEntradaExtensaoType0 | Unset, data)

        extensao = _parse_extensao(d.pop("extensao", UNSET))

        anexos = d.pop("anexos", UNSET)

        replica_entrada = cls(
            nome=nome,
            camadas=camadas,
            dispositivo=dispositivo,
            politica_conflito=politica_conflito,
            extensao=extensao,
            anexos=anexos,
        )

        return replica_entrada
