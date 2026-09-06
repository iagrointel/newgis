"""Contrato da interface: TODA rota que se declara autenticada passa pela MESMA porta (app.auth.sessao.autenticado).

Nasce do achado G1-c1 do adversário do turno 3 (laco/handoffs/T3/ataque-g1-ADVERSARIO.md): as 7 rotas
/rest/services/Geocodificador/GeocodeServer* autenticavam num `_autenticar` próprio, que chamava
`sessao.resolver()` direto. Elas exigiam credencial — logo nenhum teste de autenticação as pegava —, mas
pulavam três guardas do decorador comum de uma vez: pendência de conta (a tela de configurar 2FA quando o
inquilino exige segundo fator), CSRF sob cookie e a checagem de `X-Plat-Inquilino`. Uma guarda que vive num
caminho só não é guarda: é hábito.

O teste é ESTRUTURAL e roda sem banco — varre o app vivo (nunca docs/openapi.json, que é retrato parado, achado
G1-T1) e cruza duas leituras da mesma rota:
  1. o que ela DECLARA no OpenAPI (`x-auth`: "-" público, "S" sessão, "T" token, "S/T" os dois);
  2. o que ela FAZ, lido da árvore de dependências do FastAPI: existe alguma dependência criada por
     `sessao.autenticado(...)`?
Divergência nos dois sentidos reprova: declara credencial e não tem guarda (o buraco do G1-c1), ou tem guarda
e se declara pública (a declaração mente para quem lê o catálogo).
"""

import pytest
from fastapi.routing import APIRoute

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
}


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
        if auth not in ("", "-") and not _tem_guarda(dep) and (m, caminho) not in EXCECOES
    ]
    assert fugitivas == [], (
        "rotas que declaram credencial mas não passam por app.auth.sessao.autenticado(): elas escapam da "
        "pendência de conta (2FA obrigatório), do CSRF sob cookie e da checagem de X-Plat-Inquilino"
    )


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
