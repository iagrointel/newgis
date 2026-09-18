from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.rede_contagens import RedeContagens
    from ..models.rede_dono import RedeDono
    from ..models.rede_pacote_type_0 import RedePacoteType0


T = TypeVar("T", bound="Rede")


@_attrs_define
class Rede:
    """
    Attributes:
        id (str):
        nome (str):
        disciplina (str):
        descricao (None | str):
        tolerancia_m (float):
        pacote (None | RedePacoteType0):
        regras_ativas (bool):
        contagens (RedeContagens):
        dono (RedeDono):
        criado_em (str):
        atualizado_em (str):
    """

    id: str
    nome: str
    disciplina: str
    descricao: None | str
    tolerancia_m: float
    pacote: None | RedePacoteType0
    regras_ativas: bool
    contagens: RedeContagens
    dono: RedeDono
    criado_em: str
    atualizado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.rede_pacote_type_0 import RedePacoteType0  # noqa: PLC0415

        id = self.id

        nome = self.nome

        disciplina = self.disciplina

        descricao: None | str
        descricao = self.descricao

        tolerancia_m = self.tolerancia_m

        pacote: dict[str, Any] | None
        if isinstance(self.pacote, RedePacoteType0):
            pacote = self.pacote.to_dict()
        else:
            pacote = self.pacote

        regras_ativas = self.regras_ativas

        contagens = self.contagens.to_dict()

        dono = self.dono.to_dict()

        criado_em = self.criado_em

        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "disciplina": disciplina,
                "descricao": descricao,
                "tolerancia_m": tolerancia_m,
                "pacote": pacote,
                "regras_ativas": regras_ativas,
                "contagens": contagens,
                "dono": dono,
                "criado_em": criado_em,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rede_contagens import RedeContagens  # noqa: PLC0415
        from ..models.rede_dono import RedeDono  # noqa: PLC0415
        from ..models.rede_pacote_type_0 import RedePacoteType0  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        disciplina = d.pop("disciplina")

        def _parse_descricao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        descricao = _parse_descricao(d.pop("descricao"))

        tolerancia_m = d.pop("tolerancia_m")

        def _parse_pacote(data: object) -> None | RedePacoteType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                pacote_type_0 = RedePacoteType0.from_dict(data)

                return pacote_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RedePacoteType0, data)

        pacote = _parse_pacote(d.pop("pacote"))

        regras_ativas = d.pop("regras_ativas")

        contagens = RedeContagens.from_dict(d.pop("contagens"))

        dono = RedeDono.from_dict(d.pop("dono"))

        criado_em = d.pop("criado_em")

        atualizado_em = d.pop("atualizado_em")

        rede = cls(
            id=id,
            nome=nome,
            disciplina=disciplina,
            descricao=descricao,
            tolerancia_m=tolerancia_m,
            pacote=pacote,
            regras_ativas=regras_ativas,
            contagens=contagens,
            dono=dono,
            criado_em=criado_em,
            atualizado_em=atualizado_em,
        )

        rede.additional_properties = d
        return rede

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
