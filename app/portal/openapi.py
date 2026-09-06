"""`x-plat-escopo` em TODA operação do OpenAPI, DERIVADO do código (item L7-08-d).

Por que derivado e não declarado à mão: `x-auth` e `x-privilegio` já são escritos um a um em
`openapi_extra` e por isso podem envelhecer em silêncio quando o handler muda. O escopo de token é o que
o adversário varre rota a rota; se a etiqueta do OpenAPI não for a mesma coisa que o servidor confere,
a varredura mede a etiqueta e não o servidor. Aqui a etiqueta é LIDA da dependência `autenticado(...)`
que a própria rota instalou (atributos `plat_escopo_token`/`plat_so_sessao`/`plat_superadmin` postos em
`app/auth/sessao.py`), logo não existe estado a sincronizar.

Vocabulário de `x-plat-escopo` (fechado, `ESCOPO_ROTA_VALORES`):
  `publico`            rota sem credencial nenhuma (`x-auth: -`);
  `sessao`             só cookie de sessão — nenhum token de serviço entra (`so_sessao=True`);
  `superadmin`         só sessão de operador da plataforma;
  `token:qualquer`     qualquer token válido serve; quem filtra é o privilégio do dono;
  `<base>[:<uuid>]`    o escopo de `app/auth/escopos.py` que o token precisa ter.

Rota cuja autenticação acontece DENTRO do handler (o GeocodeServer compatível Esri aceita `?token=`) não
tem a dependência para ser lida: essa declara `x-plat-escopo` em `openapi_extra`, e o valor declarado é
conferido contra o servidor pela varredura de `tests/api/test_portal_chaves.py` como qualquer outro.
"""

from typing import Any

from fastapi import FastAPI
from fastapi import routing as fastapi_routing
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.auth import escopos as esc
from app.versao import versao

CHAVE = "x-plat-escopo"
PUBLICO = "publico"
SESSAO = "sessao"
SUPERADMIN = "superadmin"
QUALQUER = "token:qualquer"
ESPECIAIS = (PUBLICO, SESSAO, SUPERADMIN, QUALQUER)

DESCRICAO_ESPECIAIS = {
    PUBLICO: "rota aberta: não exige credencial",
    SESSAO: "só sob cookie de sessão de usuário; token de serviço recebe 403 so_sessao",
    SUPERADMIN: "só sob sessão de operador da plataforma; qualquer outra credencial recebe 404",
    QUALQUER: "qualquer token de serviço válido serve; o privilégio do dono é o que filtra",
}

DESCRICAO_PORTAL = """Interface de programação da plataforma. Interno, análise / beta privado.

Autenticação: cookie de sessão (navegador, `POST /api/login`) **ou** chave de API no cabeçalho
`Authorization: Bearer plat_...`. As duas juntas na mesma requisição são recusadas com 400
`autenticacao_ambigua`.

Chave de API: criada em `POST /api/tokens` sob sessão, mostrada uma única vez. Toda chave tem prazo
(padrão 90 dias, máximo 365) e um conjunto fechado de escopos; a revogação vale na requisição seguinte.
Cada operação abaixo declara em `x-plat-escopo` o escopo que a chave precisa ter.

Erro: toda resposta de erro segue a RFC 9457 (`application/problem+json`) e traz também os campos da
casa `erro`, `mensagem`, `detalhe` e `req_id` como membros de extensão."""


def _escopo_da_dependencia(rota) -> str | None:
    """Percorre a árvore de dependências da rota e devolve o escopo da primeira `autenticado(...)`."""
    pilha = list(getattr(rota.dependant, "dependencies", ()))
    while pilha:
        d = pilha.pop(0)
        chamada = getattr(d, "call", None)
        if chamada is not None and hasattr(chamada, "plat_escopo_token"):
            if getattr(chamada, "plat_superadmin", False):
                return SUPERADMIN
            if getattr(chamada, "plat_so_sessao", False):
                return SESSAO
            return chamada.plat_escopo_token or QUALQUER
        pilha.extend(getattr(d, "dependencies", ()))
    return None


def escopo_da_rota(rota) -> str:
    """Valor de `x-plat-escopo` da rota: declarado em `openapi_extra` (autenticação no handler) ou derivado."""
    declarado = (rota.openapi_extra or {}).get(CHAVE)
    if declarado:
        return declarado
    derivado = _escopo_da_dependencia(rota)
    if derivado is not None:
        return derivado
    return PUBLICO


def valor_admitido(valor: str) -> bool:
    return valor in ESPECIAIS or esc.valido(valor)


def _rotas_por_operacao(app: FastAPI):
    """(caminho, método minúsculo) -> contexto de rota, casando com as chaves de `paths` do OpenAPI.

    `app.routes` no FastAPI 0.138 guarda `_IncludedRouter` preguiçoso, não as rotas: quem achata é
    `fastapi.routing.iter_route_contexts`, a MESMA função que `get_openapi` usa. A chave é `path_format`
    (com `{id}`), também como em `get_openapi` — usar `route.path` daria caminho que não existe em `paths`.
    """
    saida = {}
    for contexto in fastapi_routing.iter_route_contexts(app.routes):
        if not isinstance(contexto.original_route, APIRoute) or not contexto.include_in_schema:
            continue
        for metodo in contexto.methods:
            saida[(contexto.path_format, metodo.lower())] = contexto
    return saida


def enriquecer(app: FastAPI, esquema: dict[str, Any]) -> dict[str, Any]:
    """Escreve `x-plat-escopo` em toda operação e o dicionário de escopos em `info`/`components`."""
    rotas = _rotas_por_operacao(app)
    for caminho, operacoes in esquema.get("paths", {}).items():
        for metodo, operacao in operacoes.items():
            if not isinstance(operacao, dict):
                continue
            rota = rotas.get((caminho, metodo))
            operacao[CHAVE] = escopo_da_rota(rota) if rota is not None else PUBLICO
    esquema.setdefault("components", {})["securitySchemes"] = {
        "chaveApi": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "plat_<43 caracteres>",
            "description": "chave de API criada em POST /api/tokens; prazo obrigatório, escopos fechados",
        },
        "sessao": {
            "type": "apiKey",
            "in": "cookie",
            "name": "plat_sessao",
            "description": "cookie de sessão do navegador, posto por POST /api/login",
        },
    }
    esquema["x-plat-escopos"] = [
        {"escopo": nome, "descricao": texto} for nome, texto in {**DESCRICAO_ESPECIAIS, **esc.DESCRICAO}.items()
    ]
    esquema["x-plat-perfis-de-chave"] = [
        {"perfil": nome, "escopos": list(escopos), "descricao": texto}
        for nome, (escopos, texto) in esc.PERFIS_DE_CHAVE.items()
    ]
    return esquema


def instalar(app: FastAPI) -> None:
    """Substitui `app.openapi` por uma versão que enriquece e memoriza (mesmo contrato do FastAPI)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        esquema = get_openapi(
            title=app.title,
            version=versao(),
            openapi_version=app.openapi_version,
            description=DESCRICAO_PORTAL,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        app.openapi_schema = enriquecer(app, esquema)
        return app.openapi_schema

    app.openapi = openapi
