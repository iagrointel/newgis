from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.versao_completa_autor_type_0 import VersaoCompletaAutorType0
    from ..models.versao_completa_corpo import VersaoCompletaCorpo
    from ..models.versao_completa_diff_type_0_item import VersaoCompletaDiffType0Item


T = TypeVar("T", bound="VersaoCompleta")


@_attrs_define
class VersaoCompleta:
    """
    Attributes:
        versao (int):
        sha256 (str):
        autor (None | VersaoCompletaAutorType0):
        rotulo (None | str):
        comentario (None | str):
        compactou (int):
        criado_em (None | str):
        corpo (VersaoCompletaCorpo):
        diff (list[VersaoCompletaDiffType0Item] | None | Unset):
    """

    versao: int
    sha256: str
    autor: None | VersaoCompletaAutorType0
    rotulo: None | str
    comentario: None | str
    compactou: int
    criado_em: None | str
    corpo: VersaoCompletaCorpo
    diff: list[VersaoCompletaDiffType0Item] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.versao_completa_autor_type_0 import VersaoCompletaAutorType0  # noqa: PLC0415

        versao = self.versao

        sha256 = self.sha256

        autor: dict[str, Any] | None
        if isinstance(self.autor, VersaoCompletaAutorType0):
            autor = self.autor.to_dict()
        else:
            autor = self.autor

        rotulo: None | str
        rotulo = self.rotulo

        comentario: None | str
        comentario = self.comentario

        compactou = self.compactou

        criado_em: None | str
        criado_em = self.criado_em

        corpo = self.corpo.to_dict()

        diff: list[dict[str, Any]] | None | Unset
        if isinstance(self.diff, Unset):
            diff = UNSET
        elif isinstance(self.diff, list):
            diff = []
            for diff_type_0_item_data in self.diff:
                diff_type_0_item = diff_type_0_item_data.to_dict()
                diff.append(diff_type_0_item)

        else:
            diff = self.diff

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "versao": versao,
                "sha256": sha256,
                "autor": autor,
                "rotulo": rotulo,
                "comentario": comentario,
                "compactou": compactou,
                "criado_em": criado_em,
                "corpo": corpo,
            }
        )
        if diff is not UNSET:
            field_dict["diff"] = diff

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.versao_completa_autor_type_0 import VersaoCompletaAutorType0  # noqa: PLC0415
        from ..models.versao_completa_corpo import VersaoCompletaCorpo  # noqa: PLC0415
        from ..models.versao_completa_diff_type_0_item import VersaoCompletaDiffType0Item  # noqa: PLC0415

        d = dict(src_dict)
        versao = d.pop("versao")

        sha256 = d.pop("sha256")

        def _parse_autor(data: object) -> None | VersaoCompletaAutorType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                autor_type_0 = VersaoCompletaAutorType0.from_dict(data)

                return autor_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | VersaoCompletaAutorType0, data)

        autor = _parse_autor(d.pop("autor"))

        def _parse_rotulo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        rotulo = _parse_rotulo(d.pop("rotulo"))

        def _parse_comentario(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        comentario = _parse_comentario(d.pop("comentario"))

        compactou = d.pop("compactou")

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        corpo = VersaoCompletaCorpo.from_dict(d.pop("corpo"))

        def _parse_diff(data: object) -> list[VersaoCompletaDiffType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                diff_type_0 = []
                _diff_type_0 = data
                for diff_type_0_item_data in _diff_type_0:
                    diff_type_0_item = VersaoCompletaDiffType0Item.from_dict(diff_type_0_item_data)

                    diff_type_0.append(diff_type_0_item)

                return diff_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[VersaoCompletaDiffType0Item] | None | Unset, data)

        diff = _parse_diff(d.pop("diff", UNSET))

        versao_completa = cls(
            versao=versao,
            sha256=sha256,
            autor=autor,
            rotulo=rotulo,
            comentario=comentario,
            compactou=compactou,
            criado_em=criado_em,
            corpo=corpo,
            diff=diff,
        )

        versao_completa.additional_properties = d
        return versao_completa

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
