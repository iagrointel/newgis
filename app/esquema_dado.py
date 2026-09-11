"""Nome do schema de dado de um inquilino, derivado do MESMO lugar que o SQL usa.

Por que este módulo existe: a migração `20260907T0245_isolamento_schema_de_dado.sql` criou
`plat.camada_schema_prefixo()`, que devolve `d_` em produção e `d_plat_t<trilha>_` numa instalação
derivada — é o que impede uma trilha de escrever no `d_demo` de outra instalação (o defeito de raiz,
achado em 06/09: 668 tabelas num schema partilhado por todo mundo).

O lado SQL passou a respeitar o prefixo. O lado Python NÃO: dez lugares montavam o nome como
`f"d_{slug}"`, à mão. Em produção os dois coincidem e ninguém percebe; numa trilha isolada, a função
cria `d_plat_tuniao_demo` e o Python escreve em `d_demo` — que está corretamente REVOGADO, e por isso
falha com `permission denied for schema d_demo` em vez de corromper o dado de outra instalação.
Medido em 11/09/2026 ao semear a união.

O prefixo é imutável por instalação, então uma consulta por processo basta.
"""
from __future__ import annotations

_prefixo: str | None = None


def prefixo(cur) -> str:
    """`d_` em produção, `d_plat_t<trilha>_` numa trilha. Lê do banco uma vez por processo."""
    global _prefixo
    if _prefixo is None:
        cur.execute("SELECT plat.camada_schema_prefixo() AS p")
        _prefixo = cur.fetchone()["p"]
    return _prefixo


def esquema(cur, slug: str) -> str:
    """Nome completo do schema de dado do inquilino `slug`, com o prefixo da instalação."""
    return f"{prefixo(cur)}{slug}"


def esquecer() -> None:
    """Só para teste: força a próxima chamada a reler do banco."""
    global _prefixo
    _prefixo = None
