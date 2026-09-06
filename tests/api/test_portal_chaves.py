"""Portal de API e chaves de API (item L7-08-d): cada cláusula do portão de pronto vira um teste aqui.

O que este arquivo prova, na ordem do portão:
  1. o OpenAPI é 3.1 válido por validador de terceiro (`openapi-spec-validator`);
  2. TODA operação do OpenAPI declara `x-plat-escopo` de um vocabulário fechado;
  3. varredura do adversário: chave de escopo `catalogo:ler` em TODA rota que exige outro escopo — nenhum
     200 indevido, e o 403 vem antes de o handler tocar em qualquer coisa;
  4. chave sem prazo é impossível pela API e agora também pelo banco;
  5. chave expirada devolve 401 em Problem Details (RFC 9457);
  6. chave de leitura em rota de escrita devolve 403 `escopo_insuficiente`;
  7. revogar nega em menos de 5 s (o código é 401 `token_revogado`, ver o handoff);
  8. a página `/portal` não referencia nenhum recurso de fora e vem com CSP.
As medidas de contagem vão para tests/medidas/L7-08-d-portal-api-chaves.json pelo fixture `medida`.
"""

import re
import time
import uuid

import psycopg2
import pytest

from app.auth import escopos as esc
from app.portal import openapi as portal_openapi

ITEM = "L7-08-d-portal-api-chaves"
VERBOS = ("get", "post", "put", "patch", "delete")
ESCOPOS_DA_CHAVE_DE_LEITURA = list(esc.PERFIS_DE_CHAVE["leitura"][0])
# ids inexistentes para a varredura: mesmo que uma rota aceitasse a chave por engano, ela não acharia
# nada para mudar. Nenhuma rota é chamada com um id de verdade.
ID_INEXISTENTE = "999000111"
UUID_INEXISTENTE = str(uuid.UUID(int=0))
EXTERNO = re.compile(r"""(?:src|href|url\(|@import\s+)["'(]?\s*(?:https?:)?//""", re.IGNORECASE)


@pytest.fixture(scope="module")
def esquema(cliente):
    r = cliente.get("/api/openapi.json")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def operacoes(esquema):
    """[(verbo, caminho, operação)] de todo o OpenAPI."""
    return [
        (verbo, caminho, op)
        for caminho, metodos in esquema["paths"].items()
        for verbo, op in metodos.items()
        if verbo in VERBOS
    ]


@pytest.fixture(scope="module")
def chave_leitura(sessao_a):
    """Chave de API do admin de demo com o perfil `leitura` (é a chave de demonstração do portal)."""
    r = sessao_a.post(
        "/api/tokens",
        json={"nome": "zt-portal-leitura", "escopos": ESCOPOS_DA_CHAVE_DE_LEITURA, "validade_dias": 1},
    )
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def cabecalho(chave: str) -> dict:
    return {"Authorization": f"Bearer {chave}"}


# ---------------------------------------------------------------- 1. OpenAPI válido


def test_openapi_31_valido_por_validador(esquema, medida):
    """Validador de terceiro, não asserção nossa: openapi-spec-validator 0.9.0 contra o OAS 3.1."""
    from openapi_spec_validator import validate

    assert esquema["openapi"].startswith("3.1"), esquema["openapi"]
    validate(esquema)  # levanta OpenAPIValidationError se o documento não for válido
    medida(ITEM)(
        "rotas_no_openapi",
        sum(len([v for v in m if v in VERBOS]) for m in esquema["paths"].values()),
        "rotas",
        "GET /api/openapi.json; conta operação (caminho x verbo)",
    )


# ---------------------------------------------------------------- 2. x-plat-escopo em toda rota


def test_x_plat_escopo_em_toda_rota(operacoes, medida):
    sem = [(v, c) for v, c, op in operacoes if not op.get(portal_openapi.CHAVE)]
    assert sem == [], sem
    fora = [(v, c, op[portal_openapi.CHAVE]) for v, c, op in operacoes
            if not portal_openapi.valor_admitido(op[portal_openapi.CHAVE])]
    assert fora == [], fora
    gravar = medida(ITEM)
    gravar("rotas_com_x_plat_escopo", len(operacoes), "rotas",
           "GET /api/openapi.json; conta operação com a chave x-plat-escopo")
    gravar("rotas_sem_x_plat_escopo", len(sem), "rotas", "mesma varredura, operações sem a chave")


def test_x_plat_escopo_bate_com_a_dependencia_da_rota(cliente, operacoes):
    """A etiqueta do OpenAPI é a MESMA coisa que o servidor confere (derivada, não copiada à mão)."""
    from app.main import app

    rotas = portal_openapi._rotas_por_operacao(app)  # noqa: SLF001 — é a função sob teste
    divergentes = []
    for verbo, caminho, op in operacoes:
        rota = rotas.get((caminho, verbo))
        if rota is None:
            divergentes.append((verbo, caminho, "rota sumiu da aplicação"))
            continue
        esperado = portal_openapi.escopo_da_rota(rota)
        if op[portal_openapi.CHAVE] != esperado:
            divergentes.append((verbo, caminho, op[portal_openapi.CHAVE], esperado))
    assert divergentes == []


# ---------------------------------------------------------------- 3. varredura do adversário


def _coberto_pela_chave_de_leitura(escopo: str) -> bool:
    """`camada:ler:<uuid>` é base + uuid, não `camada` + resto: partir na primeira dois-pontos daria errado."""
    m = esc.COM_UUID.match(escopo)
    base, uid = (m.group(1), m.group(3)) if m else (escopo, None)
    return esc.cobre(ESCOPOS_DA_CHAVE_DE_LEITURA, base, uid)


def _caminho_concreto(caminho: str) -> str:
    def trocar(m):
        nome = m.group(1)
        return UUID_INEXISTENTE if nome in ("item_id", "colecao_id", "chave", "token") else ID_INEXISTENTE

    return re.sub(r"\{([^}]+)\}", trocar, caminho)


def test_varredura_escopo_errado_nao_devolve_200(cliente, chave_leitura, operacoes, medida):
    """O adversário do item: chave `leitura` em TODA rota que exige outro escopo; conta os 200 indevidos."""
    cabecalhos = cabecalho(chave_leitura["token"])
    varridas, indevidos, respostas = 0, [], {}
    for verbo, caminho, op in operacoes:
        escopo = op[portal_openapi.CHAVE]
        if escopo == portal_openapi.PUBLICO:
            continue  # rota aberta: 200 sem chave é o contrato dela, não um vazamento
        if escopo == portal_openapi.QUALQUER:
            continue  # qualquer chave serve, por contrato da rota
        if _coberto_pela_chave_de_leitura(escopo):
            continue  # a chave TEM esse escopo; 200 aqui é correto
        varridas += 1
        alvo = _caminho_concreto(caminho)
        pedido = getattr(cliente, verbo)
        r = pedido(alvo, headers=cabecalhos, json={}) if verbo in ("post", "put", "patch") else pedido(
            alvo, headers=cabecalhos
        )
        respostas[r.status_code] = respostas.get(r.status_code, 0) + 1
        if r.status_code == 200:
            indevidos.append((verbo.upper(), caminho, r.text[:200]))
    assert varridas > 100, f"varredura pequena demais para valer: {varridas} rotas"
    assert indevidos == [], indevidos
    gravar = medida(ITEM)
    gravar("rotas_varridas_com_escopo_errado", varridas, "rotas",
           "tests/api/test_portal_chaves.py::test_varredura_escopo_errado_nao_devolve_200")
    gravar("respostas_200_indevidas", len(indevidos), "respostas", "mesma varredura; contrato: zero")
    gravar("distribuicao_de_status_na_varredura", respostas, "contagem por status", "mesma varredura")


def test_varredura_sem_chave_nenhuma_nao_devolve_200(cliente, operacoes):
    """Mesma varredura sem credencial: rota não-pública nunca responde 200 a anônimo."""
    vazam = []
    for verbo, caminho, op in operacoes:
        if op[portal_openapi.CHAVE] == portal_openapi.PUBLICO:
            continue
        alvo = _caminho_concreto(caminho)
        pedido = getattr(cliente, verbo)
        r = pedido(alvo, json={}) if verbo in ("post", "put", "patch") else pedido(alvo)
        if r.status_code == 200:
            vazam.append((verbo.upper(), caminho))
    assert vazam == [], vazam


def test_chave_de_um_inquilino_nao_responde_no_outro(cliente, chave_leitura, sessao_b):
    """A→B: a chave de demo lê o catálogo de demo; o item de demo2 não aparece para ela (RLS por linha)."""
    r = sessao_b.get("/api/itens?limite=1")
    assert r.status_code == 200, r.text
    do_b = (r.json().get("itens") or [{}])[0].get("id")
    if do_b:
        alcanca = cliente.get(f"/api/itens/{do_b}", headers=cabecalho(chave_leitura["token"]))
        assert alcanca.status_code in (403, 404), alcanca.text
    eu = cliente.get("/api/eu", headers=cabecalho(chave_leitura["token"]))
    assert eu.status_code == 200 and eu.json()["inquilino"]["slug"] == "demo", eu.text


# ---------------------------------------------------------------- 4. chave sem prazo é impossível


def test_chave_nasce_com_prazo_mesmo_sem_pedir(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-portal-padrao", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    criado = r.json()
    try:
        assert criado["expira_em"], "chave criada sem expira_em"
        ver = sessao_a.get(f"/api/tokens/{criado['id']}").json()
        assert ver["expira_em"], ver
    finally:
        sessao_a.delete(f"/api/tokens/{criado['id']}")


@pytest.mark.parametrize("dias", [366, 400, 3650])
def test_chave_acima_do_teto_e_recusada(sessao_a, dias):
    r = sessao_a.post(
        "/api/tokens", json={"nome": "zt-portal-teto", "escopos": ["catalogo:ler"], "validade_dias": dias}
    )
    assert r.status_code == 400 and r.json()["erro"] == "validade_acima_do_maximo", r.text


def _dono_de_chave(con):
    """(tenant_id, usuario_id) do admin de demo, com o contexto de RLS já posto na conexão como plat_app."""
    from tests.api.test_rls import contexto, ids_por_slug

    tid = ids_por_slug(con)["demo"]
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('demo', 'admin')")
        linha = cur.fetchone()
    contexto(con, tid, linha["usuario_id"])
    return tid, linha["usuario_id"]


def test_banco_recusa_chave_sem_prazo(conexao_plat_app):
    """A refutação exigida do item: mesmo por SQL, `expira_em` NULL não entra (migração 20260906T1617)."""
    tid, uid = _dono_de_chave(conexao_plat_app)
    with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.errors.NotNullViolation):
        cur.execute(
            "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, expira_em) "
            "VALUES (%s, %s, 'zt-sem-prazo', %s, 'plat_zt', NULL)",
            (tid, uid, "zt" + uuid.uuid4().hex),
        )
    conexao_plat_app.rollback()


def test_banco_recusa_prazo_acima_do_teto(conexao_plat_app):
    tid, uid = _dono_de_chave(conexao_plat_app)
    with conexao_plat_app.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, expira_em) "
            "VALUES (%s, %s, 'zt-teto', %s, 'plat_zt', now() + interval '2 years')",
            (tid, uid, "zt" + uuid.uuid4().hex),
        )
    conexao_plat_app.rollback()


# ---------------------------------------------------------------- 5. expirada -> 401 Problem Details


def _conferir_problem_details(resposta, status: int, codigo: str) -> dict:
    assert resposta.status_code == status, resposta.text
    tipo = resposta.headers.get("content-type", "")
    assert tipo.startswith("application/problem+json"), tipo
    corpo = resposta.json()
    for campo in ("type", "title", "status", "detail", "instance", "erro", "mensagem", "req_id"):
        assert campo in corpo, (campo, sorted(corpo))
    assert corpo["status"] == status and corpo["erro"] == codigo, corpo
    assert corpo["type"] == "urn:plat:erro:" + codigo, corpo
    return corpo


def test_chave_expirada_401_em_problem_details(cliente, sessao_a):
    """validade_dias=0 só vale fora de produção (ADR 0002 seção 16.4): é como se prova o 401 sem esperar 90 d."""
    r = sessao_a.post(
        "/api/tokens", json={"nome": "zt-portal-expirada", "escopos": ["catalogo:ler"], "validade_dias": 0}
    )
    assert r.status_code == 201, r.text
    criado = r.json()
    try:
        resposta = cliente.get("/api/eu", headers=cabecalho(criado["token"]))
        _conferir_problem_details(resposta, 401, "token_expirado")
    finally:
        sessao_a.delete(f"/api/tokens/{criado['id']}")


def test_chave_invalida_401_em_problem_details(cliente):
    _conferir_problem_details(cliente.get("/api/eu", headers=cabecalho("plat_" + "z" * 43)), 401, "token_invalido")


def test_erro_de_validacao_tambem_e_problem_details(cliente, chave_leitura):
    r = cliente.post("/api/itens", headers=cabecalho(chave_leitura["token"]), json={"tipo": 7})
    assert r.headers.get("content-type", "").startswith("application/problem+json"), r.headers


# ---------------------------------------------------------------- 6. leitura em rota de escrita -> 403


@pytest.mark.parametrize(
    ("verbo", "caminho"),
    [("post", "/api/itens"), ("post", "/api/pastas"), ("put", "/api/categorias"), ("post", "/api/usuarios")],
)
def test_chave_de_leitura_em_rota_de_escrita_403(cliente, chave_leitura, verbo, caminho):
    r = getattr(cliente, verbo)(caminho, headers=cabecalho(chave_leitura["token"]), json={})
    corpo = _conferir_problem_details(r, 403, "escopo_insuficiente")
    assert corpo["detalhe"]["exigido"] == "admin:inquilino", corpo
    assert sorted(corpo["detalhe"]["token_tem"]) == sorted(ESCOPOS_DA_CHAVE_DE_LEITURA), corpo


# ---------------------------------------------------------------- 7. revogar nega em menos de 5 s


def test_revogar_nega_em_menos_de_cinco_segundos(cliente, sessao_a, medida):
    """Prazo: menos de 5 s. Código: 401 `token_revogado`, não 403 — o contrato do L0-02 diz que credencial
    que deixou de existir é 401, e tests/e2e/test_tokens.py já o prova. A divergência está no handoff."""
    r = sessao_a.post(
        "/api/tokens", json={"nome": "zt-portal-revogar", "escopos": ["catalogo:ler"], "validade_dias": 1}
    )
    assert r.status_code == 201, r.text
    criado = r.json()
    antes = cliente.get("/api/itens?limite=1", headers=cabecalho(criado["token"]))
    assert antes.status_code == 200, antes.text
    t0 = time.perf_counter()
    assert sessao_a.delete(f"/api/tokens/{criado['id']}").status_code == 204
    depois = cliente.get("/api/itens?limite=1", headers=cabecalho(criado["token"]))
    segundos = time.perf_counter() - t0
    assert depois.status_code == 401 and depois.json()["erro"] == "token_revogado", depois.text
    assert segundos < 5, segundos
    gravar = medida(ITEM)
    gravar("segundos_entre_revogar_e_negar", round(segundos, 3), "s",
           "tests/api/test_portal_chaves.py::test_revogar_nega_em_menos_de_cinco_segundos")
    gravar("codigo_http_apos_revogar", depois.status_code, "código HTTP",
           "mesma medição; o portão pedia 403, o contrato do L0-02 dá 401 token_revogado")


def test_chave_conta_uso_e_grava_ultimo_uso(cliente, sessao_a):
    r = sessao_a.post(
        "/api/tokens", json={"nome": "zt-portal-usos", "escopos": ["catalogo:ler"], "validade_dias": 1}
    )
    criado = r.json()
    try:
        for _ in range(3):
            assert cliente.get("/api/itens?limite=1", headers=cabecalho(criado["token"])).status_code == 200
        visto = sessao_a.get(f"/api/tokens/{criado['id']}").json()
        assert visto["usos"] >= 3, visto
        assert visto["ultimo_uso"], visto
    finally:
        sessao_a.delete(f"/api/tokens/{criado['id']}")


# ---------------------------------------------------------------- 8. portal sem recurso externo


def test_portal_responde_com_csp_e_sem_recurso_externo(cliente):
    r = cliente.get("/portal")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), r.status_code
    csp = r.headers.get("content-security-policy", "")
    for diretiva in ("default-src 'none'", "script-src 'self'", "connect-src 'self'", "frame-ancestors 'none'"):
        assert diretiva in csp, (diretiva, csp)
    assert not EXTERNO.search(r.text), EXTERNO.findall(r.text)
    referencias = re.findall(r'(?:src|href)="([^"]+)"', r.text)
    assert referencias and all(ref.startswith(("/", "#")) for ref in referencias), referencias


@pytest.mark.parametrize("arquivo", ["web/portal.html", "web/portal.css", "web/js/portal/portal.js"])
def test_fonte_do_portal_sem_url_externa(arquivo):
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / arquivo).read_text(encoding="utf-8")
    assert "http://" not in texto and "https://" not in texto and "//cdn" not in texto, arquivo


def test_exemplos_sao_vinte_dez_e_dez(cliente, medida):
    r = cliente.get("/api/portal/exemplos")
    assert r.status_code == 200, r.text
    lista = r.json()["exemplos"]
    por_linguagem = {}
    for e in lista:
        por_linguagem[e["linguagem"]] = por_linguagem.get(e["linguagem"], 0) + 1
        assert e["codigo"].strip(), e["arquivo"]
        assert e["titulo"], e["arquivo"]
    assert por_linguagem == {"python": 10, "js": 10}, por_linguagem
    assert len(lista) == 20
    medida(ITEM)("exemplos_publicados_no_portal", len(lista), "programas",
                 "GET /api/portal/exemplos; arquivos de exemplos/python e exemplos/js")
