"""Modelos pydantic da ficha do acervo (item L6-01-a-procedencia-acervo). Saída lê `plat.acervo_ficha`
(migração 021), view SECURITY INVOKER sobre `acervo.fonte`/`acervo.v_completude` que já filtra por
`licenca IS NOT NULL` (regra D17) — o modelo só espelha o que a view devolve, não filtra de novo."""

from pydantic import BaseModel, ConfigDict


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class AcervoCartao(Saida):
    fonte_id: str
    nome: str
    orgao: str | None = None
    dominio: str
    licenca: str
    frescor: str | None = None
    numero_tabelas: int
    registros_estimados: int
    procedencia_pontuacao: float | None = None
    proxima_verificacao: str | None = None


class AcervoFicha(AcervoCartao):
    url: str | None = None
    url_http: str | None = None
    url_conferida_em: str | None = None
    data_dado: str | None = None
    data_acesso: str | None = None
    script_gerador: str | None = None
    sha256: str | None = None
    comando_reexecucao: str | None = None
    metodo: str | None = None
    confianca: str | None = None
    limites: str | None = None
    bytes: int | None = None
    procedencia_campos: int | None = None
    procedencia_campos_possiveis: int | None = None
    atualizado_em: str | None = None


class AcervoPagina(Saida):
    total: int
    itens: list[AcervoCartao]


class AcervoDominio(Saida):
    dominio: str
    fontes: int
