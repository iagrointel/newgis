"""Rotas dos widgets externos (item L5-36-widgets-personalizados-sdk).

- POST /api/widgets/externos (admin do inquilino, sessão): instala/atualiza o pacote de um widget; o
  sha256 do módulo é calculado AQUI e volta em toda listagem — o navegador só registra o widget depois de
  reconferir o hash do texto que baixou.
- GET /api/widgets/externos: lista o que o inquilino tem instalado (sem o código).
- GET /api/widgets/externos/{nome}: manifesto + metadados de instalação.
- GET /api/widgets/externos/{nome}/modulo.js: o código, same-origin, com X-Plat-Widget-Sha256 e no-store
  (versão nova precisa valer na próxima carga); passar por aqui é o que fica no log de acesso — a origem
  do widget que corre SEM sandbox é auditável pelo caminho.
- GET /api/widgets/externos/{nome}/i18n.json: as chaves do pacote (já validadas sob o prefixo do widget).
- DELETE /api/widgets/externos/{nome} (admin): desinstala.

Instalação e desinstalação usam o privilégio `org.configurar` (sessão de navegador): instalar código que
roda na página de todo o inquilino é configuração da organização, não conteúdo de editor.
"""

import hashlib

from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.widgets import modelos

router = APIRouter(prefix="/api/widgets/externos", tags=["widgets"])
X = {"x-auth": "S/T", "x-privilegio": "rls:tenant|org.configurar"}


def _linha_json(linha: dict) -> dict:
    return {
        "nome": linha["nome"],
        "versao": linha["versao"],
        "api_widget": linha["api_widget"],
        "sandbox": linha["sandbox"],
        "sha256": linha["sha256"],
        "manifesto": linha["manifesto"],
        "origem": linha["origem"],
        "instalado_em": linha["instalado_em"].strftime("%Y-%m-%dT%H:%M:%SZ") if linha["instalado_em"] else None,
    }


def _instalado_ou_404(cur, nome: str) -> dict:
    cur.execute(
        "SELECT nome, versao, api_widget, sandbox, sha256, manifesto, origem, instalado_em, modulo, i18n "
        "FROM plat.widget_externo WHERE nome = %s",
        (nome,),
    )
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "widget_inexistente", "widget externo inexistente neste inquilino")
    return linha


@router.get("", openapi_extra=X)
def listar(auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT nome, versao, api_widget, sandbox, sha256, manifesto, origem, instalado_em "
            "FROM plat.widget_externo ORDER BY nome"
        )
        itens = [_linha_json(linha) for linha in cur.fetchall()]
        return {"total": len(itens), "itens": itens, "proximo_cursor": None}


@router.post("", status_code=201, openapi_extra=X)
def instalar(corpo: dict, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)):
    manifesto, modulo, i18n, sandbox = modelos.validar_pacote(corpo)
    sha = hashlib.sha256(modulo.encode("utf-8")).hexdigest()
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.widget_externo "
            " (tenant_id, nome, versao, api_widget, sandbox, sha256, manifesto, modulo, i18n, origem, instalado_por)"
            " VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, 'upload', %s)"
            " ON CONFLICT (tenant_id, nome) DO UPDATE SET"
            "   versao = EXCLUDED.versao, api_widget = EXCLUDED.api_widget, sandbox = EXCLUDED.sandbox,"
            "   sha256 = EXCLUDED.sha256, manifesto = EXCLUDED.manifesto, modulo = EXCLUDED.modulo,"
            "   i18n = EXCLUDED.i18n, origem = 'upload', instalado_por = EXCLUDED.instalado_por,"
            "   instalado_em = now()",
            (manifesto["nome"], manifesto["versao"], modelos.API_WIDGET_ATUAL, sandbox, sha,
             modelos.jsonb(manifesto), modulo, modelos.jsonb(i18n), auth.usuario_id),
        )
        registrar_evento(cur, request, "widgets/instalar", "widget", manifesto["nome"],
                         {"versao": manifesto["versao"], "sandbox": sandbox, "sha256": sha})
        linha = _instalado_ou_404(cur, manifesto["nome"])
    return _linha_json(linha)


@router.get("/{nome}", openapi_extra=X)
def obter(nome: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        linha = _instalado_ou_404(cur, nome)
    return _linha_json(linha)


@router.get("/{nome}/modulo.js", response_class=Response, openapi_extra={"x-auth": "S"})
def modulo(nome: str, auth: Auth = autenticado()):
    with db.db(auth.contexto_leitura()) as cur:
        linha = _instalado_ou_404(cur, nome)
    return Response(
        content=linha["modulo"],
        media_type="text/javascript; charset=utf-8",
        headers={"X-Plat-Widget-Sha256": linha["sha256"], "Cache-Control": "no-store"},
    )


@router.get("/{nome}/i18n.json", openapi_extra={"x-auth": "S"})
def i18n(nome: str, auth: Auth = autenticado()):
    with db.db(auth.contexto_leitura()) as cur:
        linha = _instalado_ou_404(cur, nome)
    return linha["i18n"] or {}


@router.delete("/{nome}", status_code=204, openapi_extra=X)
def desinstalar(nome: str, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        _instalado_ou_404(cur, nome)
        cur.execute("DELETE FROM plat.widget_externo WHERE nome = %s", (nome,))
        registrar_evento(cur, request, "widgets/desinstalar", "widget", nome, None)
    return Response(status_code=204)
