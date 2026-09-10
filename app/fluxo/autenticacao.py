"""Autenticação do RECEPTOR de eventos (item L2-14-a-ingestao-de-fluxos).

O receptor vive no processo `plat-fluxo`, fora da aplicação: não tem sessão, não tem cookie, não tem o
middleware de registro de acesso (uma linha de registro por evento seria mais cara que o evento). O que ele
aceita é o token de SERVIÇO do item L0-02-d, pelo mesmo `Authorization: Bearer plat_...`, verificado pela
MESMA função de banco `plat.auth_token` que a API usa — nenhuma segunda implementação de token, nenhuma
tabela paralela, nenhuma chave própria deste processo.

Regras, todas exercidas por teste:
  - token revogado, expirado ou de dono com pendência de conta → 401 (a função de banco devolve os campos);
  - token sem o escopo `fluxo:escrever` → 403;
  - token de um inquilino não escreve em fonte de OUTRO: a fonte é procurada pelo inquilino DO TOKEN, então
    o id de fonte alheia devolve 404 (existência de objeto de outro inquilino não vaza, é a regra da casa);
  - restrição de IP e de origem do token é aplicada (mesma checagem da API, reusada de `app.auth.sessao`).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from app import db
from app.auth import escopos as mod_escopos
from app.auth import sessao
from app.auth.politica import politica_de


class ErroAutenticacao(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem = status, codigo, mensagem


@dataclass(frozen=True)
class Portador:
    token_id: int
    tenant_id: int
    usuario_id: int
    login: str
    escopos: tuple[str, ...]

    def tem_escopo(self, base: str, uuid: str | None = None) -> bool:
        return mod_escopos.cobre(list(self.escopos), base, uuid)


def autenticar(cabecalho_autorizacao: str | None, *, ip: str | None = None) -> Portador:
    valor = ""
    if cabecalho_autorizacao and cabecalho_autorizacao.lower().startswith("bearer "):
        valor = cabecalho_autorizacao[7:].strip()
    if not valor.startswith(sessao.TOKEN_PREFIXO) or len(valor) != sessao.TOKEN_TAMANHO:
        raise ErroAutenticacao(401, "token_invalido", "token de serviço inválido")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_token(%s, %s)", (sessao.sha256_hex(valor), ip))
        r = cur.fetchone()
    if r is None:
        raise ErroAutenticacao(401, "token_invalido", "token de serviço inválido")
    if r["revogado_em"] is not None:
        raise ErroAutenticacao(401, "token_revogado", "token revogado")
    if r["expira_em"] is not None and r["expira_em"] <= datetime.datetime.now(datetime.UTC):
        raise ErroAutenticacao(401, "token_expirado", "token expirado")
    politica = politica_de(r["config"], r["tenant_slug"])
    if sessao.pendencias_de(r["trocar_senha"], r["totp_ativo"], r["origem"], politica):
        raise ErroAutenticacao(401, "pendencia_do_usuario", "o dono do token tem pendência de conta")
    return Portador(token_id=r["token_id"], tenant_id=r["tenant_id"], usuario_id=r["usuario_id"],
                    login=r["login"], escopos=tuple(r["escopos"] or []))


def exigir_escrita(portador: Portador, fonte_id: str) -> None:
    if not portador.tem_escopo("fluxo:escrever", fonte_id):
        raise ErroAutenticacao(403, "escopo_insuficiente", "o token não tem o escopo fluxo:escrever")
