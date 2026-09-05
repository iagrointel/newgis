"""Ponte entre a identidade (trilha A: `app.auth.sessao.autenticado`, privilégios `jobs.executar` e
`jobs.gerir_todos`, contrato de erro `app.erros.ErroAPI`) e o serviço da fila. O serviço fala em `Sessao`
(contexto de banco + perfil + admin); a rota obtém o `Auth` pela dependência da trilha A e o converte aqui.
`ErroServico` é um `ErroAPI` com a assinatura (status, codigo, mensagem, detalhe): o tratador global responde
no formato D18 `{erro, mensagem, detalhe?, req_id}`."""

from dataclasses import dataclass

from app import db as banco
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

COOKIE_SESSAO = "plat_sessao"
PRIVILEGIO_JOBS = "jobs.executar"        # ver, criar e cancelar os próprios jobs (campo, editor, admin)
PRIVILEGIO_GERIR = "jobs.gerir_todos"    # ver e cancelar jobs de qualquer membro (admin)


class ErroServico(ErroAPI):
    def __init__(self, status: int, codigo: str, mensagem: str, detalhe=None):
        super().__init__(status, codigo, mensagem, detalhe)
        self.codigo = codigo


@dataclass(frozen=True)
class Sessao:
    ctx: banco.Contexto
    perfil: str
    superadmin: bool
    tenant_slug: str
    nome: str
    admin: bool

    @property
    def tenant_id(self) -> int:
        return self.ctx.tenant_id

    @property
    def usuario_id(self) -> int:
        return self.ctx.usuario_id


def sessao_de(auth: Auth) -> Sessao:
    return Sessao(ctx=auth.contexto(), perfil=auth.perfil, superadmin=auth.superadmin, tenant_slug=auth.tenant_slug,
                  nome=auth.nome, admin=auth.superadmin or auth.tem(PRIVILEGIO_GERIR))


def dependencia_jobs():
    """Dependência FastAPI das rotas da fila: sessão, ou token com escopo jobs:executar (admin:inquilino cobre),
    sempre com o privilégio jobs.executar no dono."""
    return autenticado(PRIVILEGIO_JOBS, escopo_token="jobs:executar")
