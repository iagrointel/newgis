"""Erros tipados do SDK. Cada status da API vira uma classe; o corpo da API vem de
`{"erro": "<codigo>", "detalhe": {...}}` e o código viaja na exceção (`.codigo`), com os campos
de `detalhe` expostos por extenso (`.exigido`, `.escopo`) quando presentes — é o que o teste de
permissão compara. `NaoEncontrado` é o caso do adversário: token do inquilino A lendo item do
inquilino B recebe 404 (RLS), nunca 403 que confirmaria a existência do objeto.

Exemplo (os campos do `detalhe` da API ficam expostos na exceção):

    >>> e = ErroPermissao("recusado", status=403, codigo="sem_privilegio",
    ...                   detalhe={"exigido": "conteudo.criar"})
    >>> e.status, e.codigo, e.exigido
    (403, 'sem_privilegio', 'conteudo.criar')
"""

from __future__ import annotations

from typing import Any


class ErroPlataforma(Exception):
    """Base de todos os erros do SDK. Guarda o status HTTP quando o erro veio da rede."""

    def __init__(self, mensagem: str, *, status: int | None = None, codigo: str | None = None,
                 detalhe: dict[str, Any] | None = None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.detalhe = detalhe or {}

    @property
    def exigido(self) -> str | None:
        """Privilégio exigido pela operação (quando a API declara em `detalhe.exigido`)."""
        return self.detalhe.get("exigido")

    @property
    def escopo(self) -> str | None:
        """Escopo de token exigido pela operação (quando a API declara em `detalhe.exigido` da recusa de escopo)."""
        return self.detalhe.get("exigido") or self.detalhe.get("escopo")


class ErroAutenticacao(ErroPlataforma):
    """401: token ausente, revogado ou expirado."""


class ErroPermissao(ErroPlataforma):
    """403: credencial válida, sem o privilégio ou o escopo que a rota exige (a API devolve
    `detalhe.exigido`; `.escopo` traz o escopo faltante quando a recusa é de escopo de token)."""


class NaoEncontrado(ErroPlataforma):
    """404: o objeto não existe ou pertence a outro inquilino (RLS devolve 404 de propósito)."""


class Conflito(ErroPlataforma):
    """409: o estado atual impede a operação (fonte com risco PII sem confirmação, nome repetido)."""


class ErroLimite(ErroPlataforma):
    """413: carga acima da cota do inquilino (ingestão, tamanho de corpo)."""


class ErroValidacao(ErroPlataforma):
    """422: entrada recusada pela validação (parâmetro fora de faixa, tipo de item sem esquema)."""


class ErroServidor(ErroPlataforma):
    """5xx: falha do lado da plataforma; pode valer repetir com recuo (o SDK não repete por você)."""


class FalhaJob(ErroPlataforma):
    """O job chegou a um estado final de falha (`falhou`) — `.codigo` é a mensagem de erro do job,
    `.cancelado` diz se foi cancelamento."""

    def __init__(self, mensagem: str, *, cancelado: bool = False, job: dict | None = None):
        super().__init__(mensagem)
        self.cancelado = cancelado
        self.job = job or {}


POR_STATUS: dict[int, type[ErroPlataforma]] = {
    401: ErroAutenticacao,
    403: ErroPermissao,
    404: NaoEncontrado,
    409: Conflito,
    413: ErroLimite,
    422: ErroValidacao,
}


def por_resposta(status: int, corpo: Any) -> ErroPlataforma:
    """Constrói a exceção do status, com o código e o detalhe que a API devolveu."""
    classe = POR_STATUS.get(status) if status < 500 else ErroServidor
    if classe is None:  # 400, 405, 429 …: erro do cliente sem classe própria
        classe = ErroPlataforma
    codigo = None
    detalhe = None
    if isinstance(corpo, dict):
        codigo = corpo.get("erro")
        d = corpo.get("detalhe")
        detalhe = d if isinstance(d, dict) else None
    mensagem = str(codigo or corpo or f"HTTP {status}")
    return classe(mensagem, status=status, codigo=codigo, detalhe=detalhe)
