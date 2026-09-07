"""PWA de campo (item L2-07-a-pwa-instalavel-cache): aplicação instalável em `/campo/` para coleta em área sem
rede. Reusa o token de serviço genérico do L0-02-d (`plat.token_servico`) com o escopo `campo:usar` já reservado
no vocabulário (`app/auth/escopos.py`) — este arquivo só acrescenta o emissor de conveniência (`POST
/api/campo/sessao`, sessão → token de 30 dias, sem escolha de escopo/validade) e a listagem mínima de mapas
(`GET /api/campo/mapas`, reaproveitando `plat.item`/RLS do L0-03: nenhuma tabela nova). Todo o resto do item —
manifest, ícone, service worker, shell — é servido por rotas próprias em vez de `/static/` porque a trilha de
teste roda só `uvicorn` sem nginx na frente (ADR 0001 seção 4.3 vale para produção; aqui a app se basta).

Cache do shell: o nome do cache no service worker inclui `versao_shell()` (arquivo `web/campo/VERSAO_SHELL`,
não o git sha do repo inteiro — trocar só essa linha já é "nova versão do app" sem exigir commit; o campo lê o
arquivo a cada resposta, então o teste de invalidação de cache troca o conteúdo e recarrega, sem reiniciar o
servidor)."""

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app import db, limites
from app.auth.comum import registrar_evento
from app.auth.escopos import cobre
from app.auth.sessao import Auth, autenticado, iso, opcional, sha256_hex
from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[2]
WEB_CAMPO = ROOT / "web" / "campo"
VERSAO_SHELL_ARQUIVO = WEB_CAMPO / "VERSAO_SHELL"

router = APIRouter(tags=["campo"])

CAMPO_TOKEN_DIAS = 30
CAMPO_TOKEN_NOME = "PWA de campo"


def versao_shell() -> str:
    try:
        return VERSAO_SHELL_ARQUIVO.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def _sem_cache_json(corpo: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(corpo, status_code=status, headers={"Cache-Control": "no-store"})


def _inserir_token(cur, auth: Auth, nome: str, escopos: list[str], dias: int) -> tuple[dict, str]:
    """Cópia mínima de `app.auth.rotas_tokens._inserir` (mesma tabela, mesmo formato de valor `plat_<url-safe>`):
    campo é o único chamador com escopo fixo, e importar uma função privada de outro pacote acoplaria dois
    módulos que hoje mudam por trilhas diferentes — a redundância é 8 linhas, o acoplamento seria pior."""
    valor = "plat_" + secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, restricao, "
        "expira_em) VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, now() + make_interval(days => %s)) "
        "RETURNING id, prefixo, escopos, expira_em",
        (auth.tenant_id, auth.usuario_id, nome, sha256_hex(valor), valor[:12], escopos, dias),
    )
    return cur.fetchone(), valor


def _arquivo(nome: str, media_type: str, cabecalhos: dict | None = None) -> FileResponse:
    caminho = WEB_CAMPO / nome
    if not caminho.is_file():
        raise ErroAPI(404, "arquivo_inexistente", "arquivo do PWA de campo inexistente")
    return FileResponse(caminho, media_type=media_type, headers=cabecalhos or {})


# ---------------------------------------------------------------- shell (HTML/CSS/JS/ícone), sem /static/
@router.api_route("/campo", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/campo/", methods=["GET", "HEAD"], include_in_schema=False)
def campo_shell():
    """`Cache-Control: no-store` na resposta HTTP não impede o service worker de guardar o corpo no Cache
    Storage (são mecanismos diferentes: `cache.put()` grava o que o `fetch()` devolveu, sem olhar o cabeçalho
    de cache do navegador) — por isso o shell pode ficar `no-store` (a versão de rede é sempre a mais nova) E
    aberto offline pelo service worker (a versão cacheada é sempre a que o `install` gravou). O atributo
    `data-versao-shell` deixa a versão visível no DOM para o teste de invalidação conferir sem ler o cache
    diretamente."""
    caminho = WEB_CAMPO / "index.html"
    if not caminho.is_file():
        raise ErroAPI(404, "arquivo_inexistente", "shell do PWA de campo inexistente")
    corpo = caminho.read_text(encoding="utf-8").replace("__VERSAO_SHELL__", versao_shell())
    return Response(corpo, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@router.get("/campo/campo.css", include_in_schema=False)
def campo_css():
    return _arquivo("campo.css", "text/css; charset=utf-8")


@router.get("/campo/app.js", include_in_schema=False)
def campo_app_js():
    return _arquivo("app.js", "text/javascript; charset=utf-8", {"Cache-Control": "no-store"})


@router.get("/campo/idb.js", include_in_schema=False)
def campo_idb_js():
    return _arquivo("idb.js", "text/javascript; charset=utf-8", {"Cache-Control": "no-store"})


@router.get("/campo/icone-192.png", include_in_schema=False)
def campo_icone_192():
    return _arquivo("icone-192.png", "image/png", {"Cache-Control": "public, max-age=86400"})


@router.get("/campo/icone-512.png", include_in_schema=False)
def campo_icone_512():
    return _arquivo("icone-512.png", "image/png", {"Cache-Control": "public, max-age=86400"})


@router.get("/campo/manifest.webmanifest", include_in_schema=False)
def campo_manifest(request: Request):
    """Manifest dinâmico: nome do inquilino e cor quando há sessão (o usuário chega aqui já logado na app
    principal); sem sessão (primeira visita direta, ou revisita do manifest pelo SO com cookie ausente) cai no
    nome/cor genéricos do produto — nunca falha, o manifest tem de existir para o navegador oferecer instalar."""
    nome = "plat · campo"
    cor = "#1f3a5f"
    auth = opcional(request)
    if auth is not None:
        nome = f"{auth.tenant_nome} · campo"
        cor = (auth.config or {}).get("cor") or cor
    corpo = {
        "id": "/campo/",
        "name": nome[: limites.ORG_NOME_MAX + 9],  # + " · campo"
        "short_name": "Campo",
        "description": "PWA de campo para coleta sem rede (análise / beta privado).",
        "start_url": "/campo/",
        "scope": "/campo/",
        "display": "standalone",
        "background_color": "#0b1622",
        "theme_color": cor,
        "lang": "pt-BR",
        "dir": "ltr",
        "icons": [
            {"src": "/campo/icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/campo/icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/campo/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/campo/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JSONResponse(
        corpo,
        media_type="application/manifest+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


_SW_MODELO = """// plat — service worker do PWA de campo (item L2-07-a-pwa-instalavel-cache). Gerado pela API
// (app/campo/rotas.py::campo_sw) para embutir a versão do shell; sem workbox, sem CDN. Escopo /campo/ pelo
// caminho do próprio script (registrado com scope explícito) e por Service-Worker-Allowed no cabeçalho HTTP.
const VERSAO = {versao!r};
const CACHE = `campo-shell-${{VERSAO}}`;
const SHELL = [
  '/campo/',
  '/campo/campo.css',
  '/campo/app.js',
  '/campo/idb.js',
  '/campo/manifest.webmanifest',
  '/campo/icone-192.png',
  '/campo/icone-512.png',
];

self.addEventListener('install', (evento) => {{
  evento.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
}});

self.addEventListener('activate', (evento) => {{
  evento.waitUntil(
    caches.keys()
      .then((nomes) => nomes.filter((n) => n.startsWith('campo-shell-') && n !== CACHE))
      .then((velhos) => Promise.all(velhos.map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
}});

// cache-first só para o shell (mesma origem, GET, sem /api/): dado de negócio nunca passa pelo Cache Storage
// do service worker — o app.js guarda mapas e fila no IndexedDB (idb.js), que é a fonte offline de verdade.
self.addEventListener('fetch', (evento) => {{
  const req = evento.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  if (!SHELL.includes(url.pathname)) return;
  evento.respondWith(
    caches.match(req).then((resposta) => resposta || fetch(req))
  );
}});
"""


@router.get("/campo/sw.js", include_in_schema=False)
def campo_sw():
    corpo = _SW_MODELO.format(versao=versao_shell())
    return Response(
        corpo,
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/campo/"},
    )


# ---------------------------------------------------------------- API: sessão de campo e mapas
@router.post("/api/campo/sessao", status_code=201, openapi_extra={"x-auth": "S", "x-privilegio": "proprio"})
def campo_sessao(request: Request, auth: Auth = autenticado(escopo_token=None, so_sessao=True)):
    """Token de campo (L0-02-d): sempre escopo `campo:usar`, sempre `CAMPO_TOKEN_DIAS` dias, sem escolha —
    é a única forma de emitir esse escopo (a rota genérica `/api/tokens` também aceitaria, mas o PWA sempre
    chama esta para não expor o formulário completo de tokens a quem só quer entrar em campo). Revogável como
    qualquer token de serviço, por `DELETE /api/tokens/{id}` (mesma tabela, sem rota própria de revogar)."""
    dias = min(CAMPO_TOKEN_DIAS, auth.politica.token_max_dias)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.token_servico WHERE usuario_id = %s AND revogado_em IS NULL "
            "AND (expira_em IS NULL OR expira_em > now())",
            (auth.usuario_id,),
        )
        if cur.fetchone()["n"] >= limites.TOKENS_POR_USUARIO:
            raise ErroAPI(422, "limite_tokens", f"no máximo {limites.TOKENS_POR_USUARIO} tokens ativos por usuário")
        r, valor = _inserir_token(cur, auth, CAMPO_TOKEN_NOME, ["campo:usar"], dias)
        # nunca gravar `valor` (o token em claro) no evento — só metadado, mesmo padrão de tokens/criar
        registrar_evento(cur, request, "campo/sessao", "token", r["id"], {"validade_dias": dias})
    return {
        "token": valor,
        "id": r["id"],
        "escopos": list(r["escopos"]),
        "expira_em": iso(r["expira_em"]),
        "tenant_slug": auth.tenant_slug,
    }


@router.get("/api/campo/mapas", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def campo_mapas(auth: Auth = autenticado(escopo_token="campo:usar")):
    """Mapas de campo (tipo `mapa`, item L2-01-a) legíveis pelo dono do token/sessão — RLS de `plat.item`
    (`plat.pode_ler`) já resolve a visibilidade; aqui só filtra o tipo e projeta o mínimo para caber no
    orçamento do shell offline (o documento inteiro fica pesado; a área/tiles por mapa é o L2-07-d, não este
    item — aqui cacheamos só o que identifica e localiza o mapa, não a base cartográfica)."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, titulo, resumo, dados, ST_AsGeoJSON(extent) AS extent, tamanho_bytes, "
            "modificado_em FROM plat.item WHERE tipo = 'mapa' AND apagado_em IS NULL "
            "ORDER BY modificado_em DESC LIMIT %s",
            (limites.CAMPO_MAPAS_MAX,),
        )
        linhas = cur.fetchall()
    return {
        "mapas": [
            {
                "id": str(r["id"]),
                "titulo": r["titulo"],
                "resumo": r["resumo"],
                # `dados` do tipo `mapa` (migração 011) é {"esquema_versao": int, "corpo": object livre} — o
                # conteúdo de `corpo` (camadas por uuid) é de um item de EDIÇÃO de mapa ainda não construído
                # (L2-03/L2-01 seguintes); aqui só projeta o que já existe hoje, sem inventar uma forma.
                "camadas": ((r["dados"] or {}).get("corpo") or {}).get("camadas", []),
                "extent": json.loads(r["extent"]) if r["extent"] else None,
                "tamanho_bytes": r["tamanho_bytes"],
                "modificado_em": iso(r["modificado_em"]),
            }
            for r in linhas
        ],
        "cobre": cobre(auth.escopos, "admin:inquilino") if auth.modo == "token" else True,
    }
