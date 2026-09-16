"""Contrato da interface: TODA rota que se declara autenticada passa por uma porta AUDITADA — o decorador
comum (app.auth.sessao.autenticado) OU, nas rotas de fachada de protocolo (Esri REST/OGC/tiles/svc por
token), a mesma checagem canônica de token chamada por fora do Depends.

Nasce do achado G1-c1 do adversário do turno 3 (laco/handoffs/T3/ataque-g1-ADVERSARIO.md): as 7 rotas
/rest/services/Geocodificador/GeocodeServer* autenticavam num `_autenticar` próprio, que chamava
`sessao.resolver()` direto SEM verificar o resultado antes de seguir. Elas exigiam credencial — logo nenhum
teste de autenticação as pegava —, mas pulavam três guardas do decorador comum de uma vez: pendência de conta
(a tela de configurar 2FA quando o inquilino exige segundo fator), CSRF sob cookie e a checagem de
`X-Plat-Inquilino`. Uma guarda que vive num caminho só não é guarda: é hábito. Foram migradas para
`Depends(autenticado(token_por_querystring=True))` (ver app/geocodificador/rotas_esri.py).

Decisão G1 do gerente (laco/handoffs/T9/FASE1.md, "Decisões do gerente"): as ~174 rotas de fachada Esri REST/
OGC/WFS/WMS/WMTS/tiles/`/svc/<token>/...` NÃO migram para Depends — é desenho deliberado (clientes SIG como
ArcGIS Pro/QGIS não mandam cabeçalho `Authorization`, só token na URL). Migrar os ~15 módulos custaria mais
que o achado vale, e as três guardas que o Depends soma além da checagem de token (CSRF sob cookie,
X-Plat-Inquilino, pendência) são todas SÓ DE SESSÃO — `autenticado()` só as aplica quando `auth.modo ==
"sessao"` — então elas não fazem falta nenhuma num pedido autenticado por token: pendência já é checada
DENTRO de `_auth_de_token` (levanta 401 `pendencia_do_usuario` antes de devolver o Auth), e CSRF/
X-Plat-Inquilino são conceitos de cookie de navegador que um cliente SIG nunca manda. O que o teste abaixo
verifica, então, é que a rota REALMENTE chama essa porta — não que ela existe em algum lugar do módulo.

O teste é ESTRUTURAL e roda sem banco — varre o app vivo (nunca docs/openapi.json, que é retrato parado, achado
G1-T1) e cruza duas leituras da mesma rota:
  1. o que ela DECLARA no OpenAPI (`x-auth`: "-" público, "S" sessão, "T" token, "S/T" os dois);
  2. o que ela FAZ:
     a. existe alguma dependência do FastAPI criada por `sessao.autenticado(...)`? (`_tem_guarda`)
     b. SENÃO, e só para as famílias de caminho abaixo (`_rota_de_fachada_token`): o handler alcança,
        estaticamente (bytecode, sem executar nada — `_alcanca_guarda_de_token`), uma chamada à mesma porta
        canônica de token que o resto da casa usa (`app.auth.sessao._auth_de_token`), direta ou por um
        wrapper de 1-2 níveis (`rotas_query._autenticar`, `imagens/rotas_stac._auth`,
        `tiles/autorizacao.autorizar` etc. — todos importam e chamam `_auth_de_token`, nunca reinventam)?
Divergência nos dois sentidos reprova: declara credencial e não tem NENHUMA das duas guardas (o buraco do
G1-c1, ou um novo — acontece de verdade, ver `test_toda_rota_declarada_autenticada_passa_pelo_guarda_comum`
e o achado registrado no relatório do turno), ou tem guarda e se declara pública (a declaração mente para
quem lê o catálogo).
"""

import dis
import inspect

import pytest
from fastapi.routing import APIRoute

from app.auth import sessao as auth_sessao
from app.main import app

# rota pública que USA a sessão quando ela existe (sessao.opcional) e nunca a exige: declara "-" e não tem a
# dependência; está aqui só para o teste dizer, por nome, o que aceita como exceção — a lista não cresce sem
# alguém escrever por quê.
EXCECOES: dict[tuple[str, str], str] = {
    ("POST", "/api/logout"): (
        "logout precisa aceitar cookie EXPIRADO ou já inválido — se exigisse sessão viva, quem tem a sessão "
        "vencida ficaria sem como apagar o cookie e receberia 401 ao tentar sair. Declara `x-auth: S` porque é "
        "o cookie que ela consome; resolve a sessão à mão e nunca levanta por ausência de credencial."
    ),
    ("GET", "/api/sso/oidc/logout"): (
        "mesma razão de /api/logout (encerra a sessão local mesmo com cookie expirado/inválido/ausente — "
        "app/auth/oidc.py::sso_oidc_logout resolve a sessão à mão dentro de `if cookie:` e nunca levanta por "
        "ausência de credencial), mais o passo de RP-Initiated Logout que só faz sentido sem exigir sessão viva."
    ),
    ("GET", "/api/sso/saml/logout"): (
        "mesma razão de /api/logout (app/auth/saml.py::sso_saml_logout resolve a sessão à mão dentro de "
        "`if cookie:` e devolve 204 mesmo sem cookie, para o SLO do IdP funcionar mesmo com sessão local já "
        "morta)."
    ),
}

# Famílias de caminho onde o protocolo do CLIENTE (ArcGIS Pro, QGIS, GDAL, um navegador batendo em /svc)
# proíbe cabeçalho Authorization — a credencial vai por querystring `?token=` ou embutida no próprio caminho
# (`/svc/{token}/...`). Fora destes prefixos, uma rota autenticada por fora do Depends(autenticado(...)) É o
# achado G1-c1 de novo, não desenho: nunca ampliar esta lista para calar um caso novo sem essa mesma análise.
_PREFIXOS_FACHADA_TOKEN = ("/svc/", "/rest/services/", "/ogc/", "/wfs/", "/wms/", "/wmts/", "/tiles/")

# Porta canônica ÚNICA de autenticação por token (app/auth/sessao.py): valida hash, revogação, expiração,
# pendência do dono e restrição de IP/referer contra `plat.auth_token`. Toda rota de fachada chama ESTA
# função — direto (`from app.auth.sessao import _auth_de_token`, ex.: app/imagens/rotas_stac.py) ou por um
# wrapper do próprio módulo (`_autenticar`/`_auth`/`autorizar` em rotas_query.py, rotas_geometria.py,
# rotas_esri_un.py, rotas_gp.py, tiles/autorizacao.py) — nunca por uma checagem paralela reinventada.
_GUARDAS_TOKEN_RAIZ = {auth_sessao._auth_de_token}


def _rota_de_fachada_token(caminho: str) -> bool:
    return caminho.startswith(_PREFIXOS_FACHADA_TOKEN)


def _chamadas_por_atributo(fn):
    """[(nome_base, atributo), ...] para cada `base.atributo(...)` estático no bytecode de `fn` — o
    suficiente para reconhecer `auth_sessao._auth_de_token(...)` ou `autorizacao.autorizar(...)` sem
    executar nada (só `dis`, não roda a função)."""
    pares = []
    pendente = None
    for instr in dis.get_instructions(fn.__code__):
        if instr.opname in ("LOAD_GLOBAL", "LOAD_DEREF", "LOAD_FAST", "LOAD_NAME"):
            pendente = instr.argval
        elif instr.opname in ("LOAD_ATTR", "LOAD_METHOD") and pendente is not None:
            pares.append((pendente, instr.argval))
            pendente = instr.argval  # permite cadeia a.b.c
        else:
            pendente = None
    return pares


def _alcanca_guarda_de_token(fn, profundidade: int = 5, vistas: set | None = None) -> bool:
    """Sobe estaticamente, sem executar nada, até achar uma chamada à porta canônica de token
    (`app.auth.sessao._auth_de_token`) por IDENTIDADE do objeto — nunca por nome solto (nomes como
    `autorizar`/`resolver` se repetem no código por razões nada a ver com autenticação). Cobre a chamada
    direta e o wrapper de 1-2 níveis dos módulos de fachada; teto de profundidade evita recursão infinita
    num ciclo de import esquisito."""
    if fn is None:
        return False
    if vistas is None:
        vistas = set()
    if fn in vistas or profundidade < 0:
        return False
    vistas.add(fn)
    if fn in _GUARDAS_TOKEN_RAIZ:
        return True
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    globais = getattr(fn, "__globals__", {})
    candidatos: set = set()
    for nome in code.co_names:  # chamada direta: `_autenticar(...)`, nome importado para o módulo
        alvo = globais.get(nome)
        if inspect.isfunction(alvo):
            candidatos.add(alvo)
    for base_nome, atributo in _chamadas_por_atributo(fn):  # `auth_sessao._auth_de_token(...)` etc.
        base = globais.get(base_nome)
        if base is None and fn.__closure__:
            try:
                idx = fn.__code__.co_freevars.index(base_nome)
                base = fn.__closure__[idx].cell_contents
            except ValueError:
                base = None
        alvo = getattr(base, atributo, None)
        if inspect.isfunction(alvo):
            candidatos.add(alvo)
    return any(_alcanca_guarda_de_token(c, profundidade - 1, vistas) for c in candidatos)


def _guardada_por_token_no_caminho(caminho: str, dependente) -> bool:
    if not _rota_de_fachada_token(caminho):
        return False
    return _alcanca_guarda_de_token(getattr(dependente, "call", None))


def _tem_guarda(dependente) -> bool:
    """A dependência criada por `autenticado()` é a função interna `dependencia` daquela fábrica."""
    for sub in dependente.dependencies:
        alvo = getattr(sub, "call", None)
        nome = getattr(alvo, "__qualname__", "")
        if nome.startswith("autenticado.<locals>."):
            return True
        if _tem_guarda(sub):
            return True
    return False


def _todas(no):
    """Desce a árvore de rotas do app vivo. Nesta versão do FastAPI `app.routes` guarda um `_IncludedRouter`
    por `include_router`, e as rotas de verdade ficam no `original_router` dele — por isso os dois caminhos."""
    for r in getattr(no, "routes", []):
        if isinstance(r, APIRoute):
            yield r
        else:
            yield from _todas(r)
    incluido = getattr(no, "original_router", None)
    if incluido is not None:
        yield from _todas(incluido)


def test_a_varredura_enxerga_o_app_inteiro():
    """Guarda da guarda: se o jeito de descer a árvore de rotas parar de funcionar (mudança de FastAPI), esta
    varredura passaria a aprovar tudo por não ver nada. Reprova antes disso."""
    vistas = {(m, caminho) for m, caminho, _a, _d in _rotas()}
    assert len(vistas) > 150, f"a varredura de rotas parou de enxergar o app ({len(vistas)}); conserte _todas()"


def _rotas():
    for r in _todas(app):
        if not r.include_in_schema:  # /api/docs, /redoc e afins: não fazem parte do contrato publicado
            continue
        extra = getattr(r, "openapi_extra", None) or {}
        for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
            yield metodo, r.path, str(extra.get("x-auth", "")).strip(), r.dependant


def test_toda_rota_declarada_autenticada_passa_pelo_guarda_comum():
    fugitivas = [
        f"{m} {caminho} (x-auth={auth!r})"
        for m, caminho, auth, dep in _rotas()
        if auth not in ("", "-")
        and not _tem_guarda(dep)
        and not _guardada_por_token_no_caminho(caminho, dep)
        and (m, caminho) not in EXCECOES
    ]
    assert fugitivas == [], (
        "rotas que declaram credencial mas não passam por app.auth.sessao.autenticado() NEM chamam "
        "_auth_de_token (direto ou por wrapper) numa família de fachada por token conhecida: elas escapam "
        "da pendência de conta (2FA obrigatório), do CSRF sob cookie e da checagem de X-Plat-Inquilino"
    )


def test_rota_de_fachada_token_sem_guarda_nenhuma_ainda_reprova():
    """Guarda da exceção G1: uma rota em `/svc/...` (ou irmã) que não chame `_auth_de_token` nem por wrapper
    tem de continuar reprovando — a exceção de G1 é para o DESENHO (token fora do Depends), nunca para
    ausência de autenticação. Usa uma função qualquer do próprio módulo de teste, que nunca chama
    `_auth_de_token`, como dublê de handler desguarnecido."""
    assert not _guardada_por_token_no_caminho("/svc/{token}/exemplo", _tem_guarda)


def test_nenhuma_rota_com_guarda_se_declara_publica():
    mentirosas = [
        f"{m} {caminho} (x-auth={auth!r})"
        for m, caminho, auth, dep in _rotas()
        if auth in ("", "-") and _tem_guarda(dep) and (m, caminho) not in EXCECOES
    ]
    assert mentirosas == [], "rotas com guarda de autenticação declarando x-auth público"


@pytest.mark.parametrize("caminho", ["/rest/services/Geocodificador/GeocodeServer/suggest",
                                     "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates",
                                     "/rest/services/Geocodificador/GeocodeServer/reverseGeocode",
                                     "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"])
def test_geocodeserver_esta_sob_o_guarda_comum(caminho):
    """O caso nomeado do achado, para que a regressão apareça pelo nome e não só na varredura."""
    achadas = [dep for m, c, auth, dep in _rotas() if c == caminho]
    assert achadas, f"rota sumiu do app: {caminho}"
    assert all(_tem_guarda(d) for d in achadas), caminho


def test_toda_rota_viva_declara_x_auth():
    """Sem a declaração, a varredura acima fica cega: rota nova sem `x-auth` no openapi_extra reprova aqui."""
    sem = sorted({f"{m} {c}" for m, c, auth, _ in _rotas() if auth == ""} - {f"{m} {c}" for m, c in EXCECOES})
    permitidas = {"GET /saude", "GET /api/versao", "GET /openapi.json", "GET /docs", "GET /redoc"}
    assert set(sem) - permitidas == set(), "rotas vivas sem x-auth declarado no openapi_extra"
