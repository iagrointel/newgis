"""Contexto de requisição da trilha de auditoria (item L7-20).

Quem grava a linha é o banco (`plat.auditoria_registrar`, trigger sobre `plat.evento` e
`plat.auditoria_cobrir`); aqui só se carrega, por requisição, o que o banco não tem como descobrir sozinho:
o identificador da requisição, o método, a rota redigida, o IP e o token de serviço.

O transporte é um `ContextVar`, não `request.state`, porque `app/db.py` prepara o cursor longe da rota e não
recebe o `Request`. O valor entra em GUC de transação (`plat.req_id`, `plat.ip`, `plat.token_id`,
`plat.metodo`, `plat.rota`) na MESMA instrução em que já entravam `plat.tenant_id`/`plat.usuario_id`, e sai
sozinho no fim da transação — nada vaza de uma requisição para a seguinte pela conexão do pool.

⚠ o nome das chaves GUC é literal `plat.*` em todo ambiente, como `plat.tenant_id`: é nome de configuração de
sessão do Postgres, não objeto de schema (ver o cabeçalho de app/schema_ambiente.py).
"""

from contextvars import ContextVar
from dataclasses import dataclass

METODOS_DE_ESCRITA = ("POST", "PUT", "PATCH", "DELETE")


@dataclass(frozen=True)
class Requisicao:
    req_id: str = ""
    metodo: str = ""
    rota: str = ""
    ip: str = ""
    token_id: str = ""


_VAZIA = Requisicao()
_ATUAL: ContextVar[Requisicao] = ContextVar("plat_auditoria_requisicao", default=_VAZIA)


def definir(req_id: str, metodo: str, rota: str, ip: str | None) -> None:
    """Chamada uma vez por requisição pelo middleware, antes de a rota rodar."""
    _ATUAL.set(Requisicao(req_id=req_id or "", metodo=(metodo or "").upper(), rota=rota or "", ip=ip or ""))


def definir_token(token_id: int | None) -> None:
    """O token de serviço só se conhece depois da autenticação; acrescenta sem perder o resto."""
    atual = _ATUAL.get()
    _ATUAL.set(Requisicao(atual.req_id, atual.metodo, atual.rota, atual.ip, "" if token_id is None else str(token_id)))


def limpar() -> None:
    _ATUAL.set(_VAZIA)


def atual() -> Requisicao:
    return _ATUAL.get()


def de_escrita() -> bool:
    return _ATUAL.get().metodo in METODOS_DE_ESCRITA


def cobrir(cur) -> None:
    """Fim de transação de requisição de ESCRITA: garante que aquele req_id deixou pelo menos uma linha.

    Não faz nada em leitura, fora de requisição (worker, script) ou sem contexto de inquilino — a própria
    função do banco confere de novo, esta guarda só evita a ida ao servidor no caminho comum.
    """
    if not de_escrita():
        return
    cur.execute("SELECT plat.auditoria_cobrir() AS id")
