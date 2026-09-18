"""Item L4-23-isolamento-por-inquilino-na-rede: prova, com pedido HTTP e consulta de banco de verdade — nunca
só por inspeção — que a rede de utilidades (catálogo, topologia, feições) é isolada por inquilino em toda rota
e no SQL que o pgRouting/CTE de arestas recebe.

Cláusulas do portão (cada uma vira uma função de teste ou uma medida em
tests/medidas/L4-23-isolamento-por-inquilino-na-rede.json, via a fixture `medida`):

1. teste cruzado A→B em TODAS as rotas de rede que apontam um recurso (id na URL) falha com 403/404
   (`test_toda_rota_de_rede_com_alvo_falha_cruzada`); a lista vem do OpenAPI em processo (`app.main.app`),
   não de um arquivo comitado que pode estar atrasado (achado do L0-02-tenant-auth, bloqueio 06/09).
2. `EXPLAIN` da consulta de arestas que o traçado (`/topologia/alcance`) executa mostra o filtro de tenant
   (`test_explain_do_tracado_mostra_filtro_de_tenant`).
3. traçado com nó de partida de outro inquilino devolve 404, tanto quando a REDE é de B quanto quando a rede
   é de A mas o nó é de B (`test_tracado_com_no_de_outro_inquilino_devolve_404`).
4. escopos de token `rede:ler/editar/validar/analisar` testados (regex + `cobre`/`exigir_escopo` unitário em
   `tests/unit/test_escopos.py`; aqui, na prática HTTP, `test_token_com_escopo_rede_ler_nao_edita` e
   `test_token_sem_escopo_rede_toma_403`).
5. registro em tests/medidas (`test_medidas_registradas`, roda por último e grava o resumo).

Refutação do item (mesmo arquivo):
- `test_forjar_tenant_id_no_corpo_e_ignorado`: adversário manda `tenant_id` de B no corpo de `POST /api/rede`
  — o campo não existe no modelo Pydantic (`RedeEntrada`), é descartado, e a rede nasce no tenant de quem
  autenticou, nunca no forjado.
- `test_ler_arestas_como_app_sem_set_tenant_da_zero_linhas`: a role `plat_app` lendo `plat.rede_topo_aresta`
  sem `SET` de `plat.tenant_id` (ou com o de outro inquilino) nunca vê a linha, mesmo com o id exato na
  cláusula WHERE — é a RLS, não a rota, quem decide.
- traceLocations da fachada Esri (mencionado na hipótese do item): NÃO EXISTE nesta passagem do produto —
  `grep -rn "traceLocations" app/` não acha nada; não há UtilityNetworkServer/trace REST compatível construído
  ainda (procurado em app/rede_utilidades e app/rede). Cláusula sem rota para testar: registrada como
  `nao_aplicavel` em vez de fingida (regra do brief: cláusula que não fechar vira nomeada, nunca inventada).
"""

import json
import uuid

import psycopg2
import pytest

from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rede_topologia import _criar_rede, _habilitar, _importar_eletrica, _linha
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L4-23-isolamento-por-inquilino-na-rede"

# uuid que não existe em inquilino nenhum: serve de recurso-fantasma na prova de que a resposta
# à tentativa cruzada é indistinguível da resposta a um recurso que simplesmente não existe.
UUID_INVENTADO = str(uuid.uuid4())


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


@pytest.fixture(scope="module")
def rede_b_com_topologia(sessao_b):
    """Rede de B com feições e topologia construídas — o alvo fixo de toda tentativa cruzada deste arquivo.
    scope=module: construída uma vez, todas as rotas GET/POST/DELETE deste arquivo apontam para ela; nenhum
    teste aqui grava nada de verdade nela (RLS barra antes) e o DELETE final do módulo a remove."""
    r = sessao_b.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-l423-alvo-b", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    bruto = instalados.bruto("eletrica-br")
    r = sessao_b.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    r = sessao_b.post(f"/api/rede/{rid}/feicoes/linhas",
                       json={"tipo_codigo": 1, "grupo": "trecho_de_media_tensao",
                             "coordenadas": [[-45.0, -15.0], [-45.0, -14.999]]})
    assert r.status_code == 201, r.text
    r = sessao_b.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao_b.get(f"/api/rede/{rid}/topologia/nos")
    assert r.status_code == 200
    no_id = r.json()["itens"][0]["id"]
    yield {"rede_id": rid, "no_id": no_id}
    sessao_b.delete(f"/api/rede/{rid}")


# --------------------------------------------------------------------------------------------------------
# cláusula 1: rotas de rede com alvo — geradas do OpenAPI em processo (nunca docs/openapi.json comitado,
# que pode estar atrasado; achado do L0-02-tenant-auth, bloqueio de 06/09).
# --------------------------------------------------------------------------------------------------------

def _rotas_de_rede_utilidades() -> list[tuple[str, str]]:
    """Todas as (método, caminho) de `/api/rede...` no OpenAPI que a aplicação serve agora — inclui o que
    ainda não foi commitado em docs/openapi.json."""
    from app.main import app

    esquema = app.openapi()
    return sorted(
        (m.upper(), c) for c, ops in esquema["paths"].items() if c.startswith("/api/rede") for m in ops
    )


# rotas SEM alvo cruzável (não têm {rede_id}/id de recurso de outro inquilino na URL: catálogo instalado ou
# criação nova) — não entram na varredura cruzada porque não há "recurso de B" para apontar.
SEM_ALVO = {
    ("GET", "/api/rede"), ("POST", "/api/rede"),
    ("GET", "/api/rede/pacotes"), ("GET", "/api/rede/pacotes/{codigo}"),
    ("POST", "/api/rede/simples"),                      # cria rede nova; o id sai da resposta, não entra na URL
    ("GET", "/api/rede/medicao/grandezas"),             # catálogo instalado, igual para todo inquilino
    ("GET", "/api/rede/consumidores/enderecos-sem-rede"),   # lista do próprio inquilino (filtro `tenant_atual()`)
    ("POST", "/api/rede/consumidores/enderecos-sem-rede"),  # gera para o próprio inquilino
    ("POST", "/api/rede/consumidores/jusante/calcular"),    # calcula sobre o próprio inquilino
    ("POST", "/api/rede/medicao/leituras"),                 # publica no próprio inquilino
}

# Rotas de /api/rede que apontam um recurso de OUTRA família (unidade consumidora, trecho, ativo de medição)
# e não a rede: não têm `{rede_id}` para trocar, então a varredura acima não as alcança. Não são "sem alvo" —
# são alvo de outro tipo, e ficam com prova própria em `test_rotas_irmas_com_alvo_proprio_tambem_isolam`.
# 18/09: estavam fora de toda medição — nem na varredura, nem em teste próprio.
IRMAS_COM_ALVO_PROPRIO = {
    ("GET", "/api/rede/consumidores/uc/{id}"),
    ("GET", "/api/rede/consumidores/trecho/{id}"),
    ("GET", "/api/rede/medicao/ativos/{ativo}"),
    ("GET", "/api/rede/medicao/ativos/{ativo}/serie"),
    ("GET", "/api/rede/medicao/ativos/{ativo}/ultimas"),
    ("PUT", "/api/rede/medicao/ativos/{ativo}"),
}


def _corpo_para(metodo: str, caminho: str):
    """Corpo válido (passa o pydantic) para cada rota de escrita, para que a única coisa em jogo na
    varredura cruzada seja RLS/dono — nunca um 422 de esquema escondendo o 403/404 esperado.

    18/09: esta tabela estava incompleta e era o buraco de cobertura do item. Trinta rotas de escrita
    respondiam 422 (esquema) à tentativa cruzada e NUNCA chegavam ao ponto em que a rota decide sobre o
    recurso de outro inquilino — o teste as dava por testadas sem nunca ter exercido a autorização delas.
    Cada corpo abaixo foi conferido contra o esquema que a própria aplicação publica (padrões de `tipo`,
    `modo` e `codigo` não aceitam texto genérico) e medido: a rota passa a responder 404, não 422."""
    if caminho == "/api/rede/{rede_id}/pacote" and metodo == "POST":
        return {"__bruto__": instalados.bruto("eletrica-br")}
    if caminho.endswith("/feicoes/pontos") and metodo == "POST":
        return {"tipo_codigo": 1, "grupo": "transformador_de_distribuicao", "lon": -46.0, "lat": -16.0}
    if caminho.endswith("/feicoes/linhas") and metodo == "POST":
        return {"tipo_codigo": 1, "grupo": "trecho_de_media_tensao",
                "coordenadas": [[-46.0, -16.0], [-46.0, -15.999]]}
    if caminho.endswith("/applyEdits") and metodo == "POST":
        return {"adicionar": [], "atualizar": [], "apagar": []}
    if caminho.endswith("/tracar") and metodo == "POST":
        return {"tipo": "conectado"}
    if caminho.endswith("/config_tracado") or caminho.endswith("/config_tracado/{config_id}"):
        if metodo in ("POST", "PUT"):
            return {"codigo": "zt-l423", "nome": f"{PREFIXO_TESTE}-l423", "tipo": "conectado"}
    if caminho.endswith("/area_sujas/modo") and metodo == "PUT":
        return {"modo": "avisar"}
    # corpo bruto (não-JSON): a rota lê `await request.body()` e só depois resolve a rede
    if caminho.endswith("/epanet") and metodo == "POST":
        return {"__bruto__": b"[TITLE]\nzt-l423\n[END]\n"}
    if caminho.endswith("/teksi") and metodo == "POST":
        return {"__bruto__": b"SQLite format 3\x00"}
    return None


def _url_para(caminho: str, alvo: dict) -> str:
    url = caminho.replace("{rede_id}", alvo["rede_id"])
    if "/topologia/alcance" in url:
        url = url.replace("/topologia/alcance", f"/topologia/alcance?no={alvo['no_id']}")
    if caminho == "/api/rede/medicao/jusante":
        # esta rota leva o rede_id na QUERY, não no caminho: sem tratá-la aqui ela não seria alcançada pela
        # troca de `{rede_id}` e sairia da varredura sem ninguém notar.
        url = f"{caminho}?rede_id={alvo['rede_id']}&ativo={alvo['no_id']}"
    if url.endswith("/tracar"):
        # GET /{rede_id}/tracar recusa com 422 "entrada_vazia" antes de olhar a rede: sem um dos dois
        # parâmetros a rota nunca chegaria à decisão de dono, e a varredura mediria o esquema, não o
        # isolamento. O uuid é inventado aqui — nunca uma feição real de B.
        url += f"?feicao_id={UUID_INVENTADO}"
    return url


def _pedir_cruzado(sessao, metodo: str, caminho: str, alvo: dict):
    """Um pedido da varredura cruzada: `sessao` autenticada como um inquilino, a URL apontando o recurso de
    OUTRO."""
    url = _url_para(caminho, alvo)
    corpo = _corpo_para(metodo, caminho)
    if corpo and "__bruto__" in corpo:
        return sessao.request(metodo, url, content=corpo["__bruto__"],
                              headers={"Content-Type": "application/json"})
    return sessao.request(metodo, url, json=corpo)


def _sem_eco(texto: str) -> str:
    """A resposta sem os dois campos que não falam do recurso: `instance` (membro da RFC 9457 que devolve
    verbatim o caminho que o PRÓPRIO cliente acabou de pedir — ver `app/erros.py:corpo_erro`) e `req_id`
    (identificador do pedido, sorteado). O que sobra é tudo o que a resposta conta sobre o recurso; é aí
    que um vazamento apareceria."""
    try:
        d = json.loads(texto)
    except ValueError:
        return texto
    if isinstance(d, dict):
        d.pop("instance", None)
        d.pop("req_id", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def test_toda_rota_de_rede_com_alvo_falha_cruzada(sessao_a, rede_b_com_topologia, medida):
    """Cláusula 1 do portão: A tentando qualquer rota de rede de utilidades com o id de B (rede ou nó)
    recebe 403/404, nunca 2xx nem dado de B."""
    rotas = _rotas_de_rede_utilidades()
    alvo = rede_b_com_topologia
    testadas = []
    for metodo, caminho in rotas:
        if (metodo, caminho) in SEM_ALVO or (metodo, caminho) in IRMAS_COM_ALVO_PROPRIO:
            continue
        url = _url_para(caminho, alvo)
        r = _pedir_cruzado(sessao_a, metodo, caminho, alvo)
        assert r.status_code in (403, 404), f"{metodo} {url} → {r.status_code}: {r.text[:300]}"
        # o corpo, tirado o eco do pedido do próprio cliente, não pode conter NADA de B: nem o id da rede,
        # nem o id do nó, nem o nome. Antes daqui a comparação era sobre o texto inteiro e batia no membro
        # `instance` — o caminho que A acabou de digitar, devolvido verbatim — e parava a varredura na
        # primeira rota, deixando as outras cem sem nunca serem medidas.
        corpo = _sem_eco(r.text)
        for rotulo, agulha in (("id da rede", alvo["rede_id"]), ("id do nó", alvo["no_id"]),
                               ("nome", "l423-alvo-b")):
            assert agulha not in corpo, f"{metodo} {url} devolveu o {rotulo} de B: {corpo[:300]}"
        # e o eco, quando existe, é exatamente o caminho pedido — nada mais. Um id de B que apareça em
        # `instance` sem estar na URL seria vazamento de verdade.
        if alvo["rede_id"] in r.text:
            eco = json.loads(r.text).get("instance")
            assert eco == url.split("?")[0], f"{metodo} {url}: instance={eco!r} não é o caminho pedido"
        testadas.append(f"{metodo} {caminho}")

    medida(ITEM)("rotas_de_rede_no_openapi", len(rotas), "rotas",
                 "app.main.app.openapi() filtrado por caminho iniciando em /api/rede, em processo")
    medida(ITEM)("rotas_com_alvo_testadas_cruzadas", len(testadas), "rotas",
                 "subconjunto de rotas_de_rede_no_openapi com {rede_id}/recurso de outro inquilino na URL, "
                 "cada uma chamada com o alvo de B e A autenticado, exigindo 403/404")
    # honestidade: o portão pede ">= 40 rotas"; a superfície real de rede de utilidades hoje é menor (achado
    # deste item) — ver nota "rotas_40_nao_alcancado" em CHANGELOG/handoff. Não se infla a lista com rota
    # que não existe para bater o número.
    assert len(rotas) >= 20, rotas  # trava de regressão: a suíte falha se a superfície REGREDIR, não se crescer
    assert testadas, "nenhuma rota com alvo cruzável encontrada — a varredura ficaria vazia"


def test_resposta_cruzada_nao_distingue_alheia_de_inexistente(sessao_a, rede_b_com_topologia, medida):
    """Canal lateral também é vazamento: se a resposta a "a rede de B" fosse diferente da resposta a "uma
    rede que não existe em lugar nenhum", A poderia enumerar os ids de B sem nunca ler um byte do conteúdo.
    Toda rota com alvo é chamada duas vezes — uma com o id real de B, outra com um uuid inventado — e as
    duas respostas têm de ter o mesmo status e o mesmo corpo, tirado o eco do caminho pedido."""
    alvo = rede_b_com_topologia
    fantasma = {"rede_id": UUID_INVENTADO, "no_id": str(uuid.uuid4())}
    comparadas = []
    for metodo, caminho in _rotas_de_rede_utilidades():
        if (metodo, caminho) in SEM_ALVO or (metodo, caminho) in IRMAS_COM_ALVO_PROPRIO:
            continue
        real = _pedir_cruzado(sessao_a, metodo, caminho, alvo)
        inexistente = _pedir_cruzado(sessao_a, metodo, caminho, fantasma)
        assert real.status_code == inexistente.status_code, (
            f"{metodo} {caminho}: rede de outro inquilino → {real.status_code}, rede inexistente → "
            f"{inexistente.status_code}; a diferença enumera os ids do vizinho")
        assert _sem_eco(real.text) == _sem_eco(inexistente.text), (
            f"{metodo} {caminho}: corpos diferentes para rede alheia e rede inexistente\n"
            f"  alheia:      {_sem_eco(real.text)[:200]}\n"
            f"  inexistente: {_sem_eco(inexistente.text)[:200]}")
        comparadas.append(f"{metodo} {caminho}")
    medida(ITEM)("rotas_sem_oraculo_de_existencia", len(comparadas), "rotas",
                 "cada rota com alvo chamada com o id real de outro inquilino e com um uuid inventado; "
                 "mesmo status e mesmo corpo (sem o membro `instance`, que é o eco do caminho pedido)")
    assert comparadas


def test_rotas_sem_alvo_nao_vazam_lista_de_b(sessao_a, sessao_b, rede_b_com_topologia):
    """As rotas sem {rede_id} (listar/criar) não devolvem os itens do outro inquilino."""
    r = sessao_a.get("/api/rede")
    assert r.status_code == 200
    assert all(item["id"] != rede_b_com_topologia["rede_id"] for item in r.json()["itens"])


# --------------------------------------------------------------------------------------------------------
# cláusula 2: EXPLAIN do traçado mostra o filtro de tenant na SQL de arestas
# --------------------------------------------------------------------------------------------------------

SQL_ARESTAS_DO_TRACADO = (
    "SELECT a.id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
    "WHERE a.rede_id = %s::uuid AND %s::uuid IN (a.no_origem_id, a.no_destino_id)"
)


def test_explain_do_tracado_mostra_filtro_de_tenant(env, rede_b_com_topologia, medida):
    """A consulta-base do traçado (`_alcance_sincrono`, a âncora da CTE recursiva de `topologia/alcance`)
    roda sob a role `plat_app` com o inquilino de B setado; o plano tem de conter um Filter com
    `tenant_atual()` sobre `rede_topo_aresta` — é a RLS que entra na SQL de arestas, não um WHERE manual da
    rota (a rota nem filtra por tenant_id explicitamente: quem faz isso é a política)."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo2"])  # B — dono da rede/nó usados
        with con.cursor() as cur:
            cur.execute(
                "EXPLAIN (COSTS OFF) " + SQL_ARESTAS_DO_TRACADO,
                (rede_b_com_topologia["rede_id"], rede_b_com_topologia["no_id"]),
            )
            plano = "\n".join(r["QUERY PLAN"] for r in cur.fetchall())
        con.rollback()
        assert "tenant_atual" in plano or "tenant_id" in plano, plano
        medida(ITEM)("explain_mostra_filtro_de_tenant", "tenant_atual" in plano or "tenant_id" in plano,
                     "bool", "EXPLAIN (COSTS OFF) da consulta-base de arestas do traçado, contexto de B")
        medida(ITEM)("explain_plano_bruto", plano, "texto", "plano completo, para auditoria")
    finally:
        con.close()


# --------------------------------------------------------------------------------------------------------
# cláusula 3: traçado com ponto de partida de outro inquilino devolve vazio com 404
# --------------------------------------------------------------------------------------------------------

def test_tracado_com_no_de_outro_inquilino_devolve_404(sessao_a, sessao_b, rede_b_com_topologia, limpar_redes):
    alvo = rede_b_com_topologia

    # caso 1: a REDE inteira é de B — A nem enxerga a rede (404 rede_inexistente antes do nó)
    r = sessao_a.get(f"/api/rede/{alvo['rede_id']}/topologia/alcance?no={alvo['no_id']}")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "rede_inexistente"

    # caso 2: a rede é de A, mas o NÓ de partida pedido é o de B (existe no banco, mas não nesta rede/tenant)
    rid_a = _criar_rede(sessao_a, "l423-tracado-no-estranho", limpar_redes)
    _importar_eletrica(sessao_a, rid_a)
    _linha(sessao_a, rid_a, [[-44.0, -13.0], [-44.0, -12.999]])
    _habilitar(sessao_a, rid_a)
    r = sessao_a.get(f"/api/rede/{rid_a}/topologia/alcance?no={alvo['no_id']}")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "no_inexistente"
    assert alvo["no_id"] not in r.text


# --------------------------------------------------------------------------------------------------------
# cláusula 4: escopos de token rede:ler/editar/validar/analisar, na prática HTTP (o unitário fica em
# tests/unit/test_escopos.py — aqui é o token de verdade batendo na rota de verdade)
# --------------------------------------------------------------------------------------------------------

@pytest.fixture
def token_a_com_escopos():
    _tokens_criados = []

    def _criar(sessao, escopos):
        r = sessao.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-l423-{'-'.join(escopos)}",
                                              "escopos": escopos})
        assert r.status_code == 201, r.text
        tok = r.json()
        _tokens_criados.append((sessao, tok["id"]))
        return tok

    yield _criar
    for sessao, tid in _tokens_criados:
        sessao.delete(f"/api/tokens/{tid}")


def test_token_com_escopo_rede_ler_nao_edita(sessao_a, cliente, token_a_com_escopos, limpar_redes):
    rid = _criar_rede(sessao_a, "l423-escopo-ler", limpar_redes)
    tok = token_a_com_escopos(sessao_a, ["rede:ler"])
    cab = {"Authorization": f"Bearer {tok['token']}"}
    assert cliente.get(f"/api/rede/{rid}", headers=cab).status_code == 200
    r = cliente.post(f"/api/rede/{rid}/feicoes/pontos", headers=cab,
                      json={"tipo_codigo": 1, "grupo": "transformador_de_distribuicao", "lon": -46, "lat": -16})
    assert r.status_code == 403
    assert r.json()["erro"] == "escopo_insuficiente"
    assert r.json()["detalhe"]["exigido"] == "rede:editar"


def test_token_sem_escopo_rede_toma_403(sessao_a, cliente, token_a_com_escopos, limpar_redes):
    rid = _criar_rede(sessao_a, "l423-escopo-nenhum", limpar_redes)
    tok = token_a_com_escopos(sessao_a, ["catalogo:ler"])  # escopo de OUTRA família, não cobre rede:*
    cab = {"Authorization": f"Bearer {tok['token']}"}
    r = cliente.get(f"/api/rede/{rid}", headers=cab)
    assert r.status_code == 403
    assert r.json()["detalhe"]["exigido"] == "rede:ler"


def test_token_rede_analisar_traca_mas_nao_edita(sessao_a, cliente, token_a_com_escopos, limpar_redes):
    rid = _criar_rede(sessao_a, "l423-escopo-analisar", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _linha(sessao_a, rid, [[-43.0, -12.0], [-43.0, -11.999]])
    resumo = _habilitar(sessao_a, rid)
    assert resumo["nos"] > 0
    no_id = sessao_a.get(f"/api/rede/{rid}/topologia/nos").json()["itens"][0]["id"]

    tok = token_a_com_escopos(sessao_a, ["rede:analisar"])
    cab = {"Authorization": f"Bearer {tok['token']}"}
    r = cliente.get(f"/api/rede/{rid}/topologia/alcance?no={no_id}", headers=cab)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/api/rede/{rid}/topologia/habilitar", headers=cab)
    assert r.status_code == 403 and r.json()["detalhe"]["exigido"] == "rede:editar"


# --------------------------------------------------------------------------------------------------------
# refutação 1: adversário forja tenant_id no corpo de POST /api/rede
# --------------------------------------------------------------------------------------------------------

def test_forjar_tenant_id_no_corpo_e_ignorado(sessao_a, sessao_b, limpar_redes, env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
    finally:
        con.close()
    r = sessao_a.post("/api/rede", json={
        "nome": f"{PREFIXO_TESTE}-l423-forjada", "disciplina": "agua",
        "tenant_id": ids["demo2"],  # campo que RedeEntrada não declara — pydantic descarta
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append((sessao_a, rid))
    # a rede nasceu no tenant de A (RLS deixa A ler), nunca no forjado (B não a enxerga)
    assert sessao_a.get(f"/api/rede/{rid}").status_code == 200
    assert sessao_b.get(f"/api/rede/{rid}").status_code == 404
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute("SELECT tenant_id FROM plat.rede WHERE id = %s::uuid", (rid,))
            assert cur.fetchone()["tenant_id"] == ids["demo"]
        con.rollback()
    finally:
        con.close()


# --------------------------------------------------------------------------------------------------------
# refutação 2: ler plat.rede_topo_aresta como plat_app sem SET do tenant (ou com o de outro) dá zero linhas
# --------------------------------------------------------------------------------------------------------

def test_ler_arestas_como_app_sem_set_tenant_da_zero_linhas(env, rede_b_com_topologia):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            # nenhum SET de plat.tenant_id nesta conexão nova: tenant_atual() é NULL
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid",
                        (rede_b_com_topologia["rede_id"],))
            assert cur.fetchone()["n"] == 0
        con.rollback()

        ids = ids_por_slug(con)
        contexto(con, ids["demo"])  # A — não é o dono da rede de B
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid",
                        (rede_b_com_topologia["rede_id"],))
            assert cur.fetchone()["n"] == 0
        con.rollback()
    finally:
        con.close()


def test_traclocations_fachada_esri_nao_existe_ainda(medida):
    """Refutação declarada no item: 'adversário forja tenant_id ... no traceLocations da fachada Esri'.
    Não há fachada de trace Esri (UtilityNetworkServer/traceLocations) nesta passagem do produto — só o
    traçado mínimo por conectividade (`/topologia/alcance`), coberto pelos testes acima. Cláusula sem alvo:
    registrada como não aplicável, nunca fingida."""
    import subprocess

    achou = subprocess.run(
        ["grep", "-rn", "traceLocations", "app"], cwd=__file__.rsplit("/tests/", 1)[0],
        capture_output=True, text=True,
    )
    assert achou.stdout == "", "traceLocations apareceu no código — atualizar este teste e testar de verdade"
    medida("L4-23-isolamento-por-inquilino-na-rede")(
        "traceLocations_fachada_esri", "nao_aplicavel", "texto",
        "grep -rn traceLocations app/ — sem resultado; feature não construída nesta passagem",
    )
