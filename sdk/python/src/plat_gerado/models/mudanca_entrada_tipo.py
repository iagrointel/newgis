from enum import StrEnum


class MudancaEntradaTipo(StrEnum):
    ADICIONAR_CAMPO = "adicionar_campo"
    MUDAR_TAMANHO = "mudar_tamanho"
    MUDAR_TIPO = "mudar_tipo"
    RENOMEAR_ALIAS = "renomear_alias"

    def __str__(self) -> str:
        return str(self.value)
