"""Modelos pydantic dos domínios e subtipos (item L2-10-a). Entradas com extra=forbid; a validação de forma
que o banco também faz (código duplicado, teto de códigos, intervalo invertido) está repetida aqui de
propósito: a API responde 422 com o campo errado antes de gastar transação, e o banco continua sendo a
última palavra para quem escreve por fora."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from app.catalogo.modelos import UUID_PADRAO, Modelo, Saida

# teto de códigos de um domínio codificado: igual ao do gatilho plat.dominio_sincronizar (2.000). Domínio é
# lista de escolha de formulário, não tabela de dados — acima disso o certo é uma camada de referência.
CODIGOS_MAX = 2000
NOME_PADRAO = r"^[A-Za-z_][A-Za-z0-9_ .\-]{0,119}$"
CAMPO_PADRAO = r"^[a-z_][a-z0-9_]{0,62}$"
TIPOS_CAMPO = ("text", "smallint", "integer", "bigint", "double precision", "real", "numeric", "date")
TIPOS_CAMPO_NUMERICOS = ("smallint", "integer", "bigint", "double precision", "real", "numeric")


class ValorCodificado(Modelo):
    codigo: str = Field(min_length=1, max_length=120)
    descricao: str = Field(min_length=1, max_length=250)
    ordem: int | None = Field(default=None, ge=0, le=100000)
    ativo: bool = True


class Intervalo(Modelo):
    min: float
    max: float


class DominioEntrada(Modelo):
    nome: str = Field(pattern=NOME_PADRAO)
    tipo: str = Field(pattern="^(codificado|intervalo)$")
    tipo_campo: str
    descricao: str | None = Field(default=None, max_length=2000)
    valores: list[ValorCodificado] | Intervalo

    @field_validator("tipo_campo")
    @classmethod
    def _tipo_campo(cls, v: str) -> str:
        if v not in TIPOS_CAMPO:
            raise ValueError(f"tipo de campo precisa ser um de {list(TIPOS_CAMPO)}")
        return v

    @model_validator(mode="after")
    def _coerente(self):
        if self.tipo == "codificado":
            if not isinstance(self.valores, list):
                raise ValueError("domínio codificado espera uma lista de valores")
            if not self.valores:
                raise ValueError("domínio codificado precisa de pelo menos um valor")
            if len(self.valores) > CODIGOS_MAX:
                raise ValueError(f"domínio codificado aceita no máximo {CODIGOS_MAX} códigos")
            vistos = set()
            for v in self.valores:
                if v.codigo in vistos:
                    raise ValueError(f"código repetido na lista: {v.codigo}")
                vistos.add(v.codigo)
        else:
            if not isinstance(self.valores, Intervalo):
                raise ValueError('domínio de intervalo espera {"min": número, "max": número}')
            if self.tipo_campo not in TIPOS_CAMPO_NUMERICOS:
                raise ValueError(f"domínio de intervalo só sobre tipo numérico {list(TIPOS_CAMPO_NUMERICOS)}")
            if self.valores.min > self.valores.max:
                raise ValueError("o mínimo é maior que o máximo")
        return self


class DominioSaida(Saida):
    id: str
    nome: str
    tipo: str
    tipo_campo: str
    descricao: str | None = None
    valores: list[dict] | dict
    criado_em: str | None = None
    atualizado_em: str | None = None


class DominioPagina(Saida):
    total: int
    itens: list[DominioSaida]


class LigacaoEntrada(Modelo):
    campo: str = Field(pattern=CAMPO_PADRAO)
    dominio_id: str = Field(pattern=UUID_PADRAO)
    subtipo_codigo: int | None = None


class LigacaoSaida(Saida):
    id: str
    item_id: str
    campo: str
    subtipo_codigo: int | None = None
    dominio_id: str
    dominio_nome: str


class SubtipoValor(Modelo):
    codigo: int
    nome: str = Field(min_length=1, max_length=250)
    padroes: dict[str, object] = Field(default_factory=dict)


class SubtipoEntrada(Modelo):
    campo: str = Field(pattern=CAMPO_PADRAO)
    valores: list[SubtipoValor] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _sem_repetido(self):
        vistos = set()
        for v in self.valores:
            if v.codigo in vistos:
                raise ValueError(f"código de subtipo repetido: {v.codigo}")
            vistos.add(v.codigo)
        return self


class SubtipoSaida(Saida):
    item_id: str
    campo: str
    valores: list[dict]


class UsoSaida(Saida):
    dominio_id: str
    camadas: list[dict]
    valores: list[dict]


class CsvEntrada(Modelo):
    """O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só aceita application/json."""

    csv: str = Field(min_length=1, max_length=4 * 1024 * 1024)


class ImportarEntrada(Modelo):
    """Recorte do JSON de uma camada de FeatureServer/FGDB: `fields` com `domain`, e `types` com
    `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`."""

    fields: list[dict] = Field(default_factory=list, max_length=500)
    types: list[dict] = Field(default_factory=list, max_length=500)
    prefixo: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_ .\-]{0,40}$")
    item_id: str | None = Field(default=None, pattern=UUID_PADRAO)


class ImportarSaida(Saida):
    criados: list[dict]
    reaproveitados: list[dict]
    ligados: list[dict]
    subtipos: dict | None = None
    ignorados: list[dict]
