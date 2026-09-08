"""Topologia derivada da rede de utilidades (item L4-01-b-topologia-derivada; ADR 0020).

Cláusulas do portão provadas aqui:
1. tolerância é parâmetro da rede e aparece na ficha (`test_tolerancia_e_parametro_da_rede`);
2. 0,04 m conecta e 0,06 m não conecta, com a mesma tolerância padrão (`test_ponto_a_004m_conecta_a_006m_nao`);
3. cruzamento sem nó compartilhado nunca conecta (`test_cruzamento_sem_no_nao_conecta`);
4. GIST + RLS em `rede_topo_no`/`rede_topo_aresta` (`test_rls.py::test_topologia_rls_e_gist`, junto dos outros);
5. resumo com nós/arestas/órfãos/sem-nó corretos (`test_resumo_conta_orfaos_e_arestas_sem_no`);
7. isolamento entre inquilinos — CLÁUSULA INEGOCIÁVEL (`test_inquilino_b_nunca_le_topologia_de_a`).

A cláusula 6 (tempo de construção na escala real) está em `test_rede_topologia_medida.py`, separada porque
usa o gerador sintético completo (dezenas de segundos) — não deve rodar em todo `pytest -q` do dia a dia."""

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar, tolerancia_m=None, disciplina="eletrica"):
    corpo = {"nome": f"{PREFIXO_TESTE}-topo-{sufixo}", "disciplina": disciplina}
    if tolerancia_m is not None:
        corpo["tolerancia_m"] = tolerancia_m
    r = sessao.post("/api/rede", json=corpo)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append((sessao, rid))
    return rid


def _importar_eletrica(sessao, rid):
    from app.rede_utilidades import instalados

    bruto = instalados.bruto("eletrica-br")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text


def _linha(sessao, rid, coordenadas, grupo="trecho_de_media_tensao", tipo_codigo=1):
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas",
                     json={"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas})
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo):
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos",
                     json={"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat})
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _projetar(env, lon, lat, distancia_m, azimute_graus) -> tuple[float, float]:
    """Ponto exatamente a `distancia_m` de (lon,lat), medido em `geography` (o mesmo tipo que
    `ST_DWithin` usa na construção) — para o teste da cláusula 2 não depender de nenhuma aproximação
    própria: quem diz "0,04 m" e "0,06 m" é o PostGIS, a mesma régua do item."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT ST_X(p::geometry) AS lon, ST_Y(p::geometry) AS lat FROM (SELECT "
                "ST_Project(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, radians(%s)) AS p) s",
                (lon, lat, distancia_m, azimute_graus),
            )
            r = cur.fetchone()
            return r["lon"], r["lat"]
    finally:
        con.close()


# --- cláusula 1: tolerância é parâmetro da rede -------------------------------------------------------

def test_tolerancia_e_parametro_da_rede_e_aparece_na_ficha(sessao_a, limpar_redes):
    rid_padrao = _criar_rede(sessao_a, "tol-padrao", limpar_redes)
    assert sessao_a.get(f"/api/rede/{rid_padrao}").json()["tolerancia_m"] == 0.05

    rid_larga = _criar_rede(sessao_a, "tol-larga", limpar_redes, tolerancia_m=0.2)
    assert sessao_a.get(f"/api/rede/{rid_larga}").json()["tolerancia_m"] == 0.2

    r = sessao_a.get("/api/rede")  # sanity: a lista também carrega o campo, não só a ficha
    achou = next(i for i in r.json()["itens"] if i["id"] == rid_larga)
    assert achou["tolerancia_m"] == 0.2


# --- cláusula 2: 0,04 m conecta, 0,06 m não conecta (mesma tolerância padrão, 0,05 m) -----------------

@pytest.mark.parametrize("distancia_m,deve_conectar", [(0.04, True), (0.06, False)])
def test_ponto_a_004m_conecta_a_006m_nao(sessao_a, limpar_redes, env, distancia_m, deve_conectar):
    rid = _criar_rede(sessao_a, f"dist-{distancia_m}", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    p_lon, p_lat = -47.5, -16.0
    deslocado_lon, deslocado_lat = _projetar(env, p_lon, p_lat, distancia_m, 90)

    _linha(sessao_a, rid, [[-47.501, -16.0], [p_lon, p_lat]])  # trecho A termina em P
    _linha(sessao_a, rid, [[deslocado_lon, deslocado_lat], [-47.499, -16.0]])  # trecho B começa a `distancia_m` de P

    resumo = _habilitar(sessao_a, rid)
    esperado = 3 if deve_conectar else 4
    assert resumo["nos"] == esperado, (
        f"a {distancia_m} m do vértice: esperava {esperado} nós ({'conecta' if deve_conectar else 'não conecta'}), "
        f"veio {resumo['nos']}"
    )
    assert resumo["arestas"] == 2 and resumo["arestas_sem_no"] == 0


def test_tolerancia_maior_na_rede_conecta_o_que_a_padrao_recusaria(sessao_a, limpar_redes, env):
    """Prova que a tolerância É de fato lida da REDE (cláusula 1) e não uma constante global: os MESMOS
    0,06 m que não conectam no teste acima conectam aqui, numa rede com tolerância declarada de 0,1 m."""
    rid = _criar_rede(sessao_a, "tol-conecta-006", limpar_redes, tolerancia_m=0.1)
    _importar_eletrica(sessao_a, rid)
    p_lon, p_lat = -47.5, -16.0
    deslocado_lon, deslocado_lat = _projetar(env, p_lon, p_lat, 0.06, 90)
    _linha(sessao_a, rid, [[-47.501, -16.0], [p_lon, p_lat]])
    _linha(sessao_a, rid, [[deslocado_lon, deslocado_lat], [-47.499, -16.0]])
    resumo = _habilitar(sessao_a, rid)
    assert resumo["nos"] == 3, "0,06 m deveria conectar numa rede com tolerância 0,1 m"


# --- cláusula 3: cruzar não é conectar ------------------------------------------------------------------

def test_cruzamento_sem_no_nao_conecta(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "cruzamento", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    a = _linha(sessao_a, rid, [[-47.60, -16.10], [-47.58, -16.08]])  # cruza no meio, sem vértice compartilhado
    b = _linha(sessao_a, rid, [[-47.60, -16.08], [-47.58, -16.10]])

    resumo = _habilitar(sessao_a, rid)
    assert resumo["nos"] == 4, "os 4 extremos são distintos: o cruzamento no meio não é um vértice declarado"
    assert resumo["arestas"] == 2

    arestas = {e["origem_id"]: e for e in sessao_a.get(f"/api/rede/{rid}/topologia/arestas").json()["itens"]}
    nos_de_a = {arestas[a["id"]]["no_origem_id"], arestas[a["id"]]["no_destino_id"]}
    nos_de_b = {arestas[b["id"]]["no_origem_id"], arestas[b["id"]]["no_destino_id"]}
    assert nos_de_a.isdisjoint(nos_de_b), "as duas linhas não podem compartilhar nó nenhum"


# --- cláusula 5: resumo conta nós, arestas, órfãos e arestas sem nó ------------------------------------

def test_resumo_conta_orfaos_e_arestas_sem_no(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "resumo", limpar_redes)
    _importar_eletrica(sessao_a, rid)

    # 1 trecho de MT contínuo em 2 segmentos (3 nós de conexão, 2 arestas)
    _linha(sessao_a, rid, [[-48.0, -17.0], [-48.0, -16.999]])
    _linha(sessao_a, rid, [[-48.0, -16.999], [-48.0, -16.998]])
    # 1 trecho de BT que sai do MESMO ponto final (funde com o nó acima: MT e BT são grupos diferentes,
    # mas aqui a fusão é direta grupo-a-grupo só quando há regra — usa-se o transformador para religar)
    trafo = _ponto(sessao_a, rid, -48.0, -16.998, "transformador_de_distribuicao", 1)
    _linha(sessao_a, rid, [[-48.0, -16.998], [-48.0, -16.997]], grupo="trecho_de_baixa_tensao")
    # 1 transformador ÓRFÃO: longe de qualquer trecho — os 2 terminais (alta/baixa) nunca encontram nada
    _ponto(sessao_a, rid, -49.0, -18.0, "transformador_de_distribuicao", 1)
    # 1 trecho degenerado (origem == destino): "aresta sem nó"
    _linha(sessao_a, rid, [[-48.5, -17.5], [-48.5, -17.5]])

    resumo = _habilitar(sessao_a, rid)
    # nós: A (origem do 1º trecho MT) + B (junção dos 2 trechos MT) + C (fim do MT, fundido com o terminal
    # ALTA do trafo) + D (início do BT, fundido com o terminal BAIXA do trafo) + E (fim do BT) = 5, mais os
    # 2 terminais do transformador ÓRFÃO (sem ninguém para fundir) = 7. A fusão em C/D é o ponto: o terminal
    # do trafo não soma nó novo quando encontra o trecho do seu lado (tier), só quando não encontra nada.
    assert resumo["nos"] == 7, resumo
    assert resumo["arestas"] == 4  # 2 MT + 1 BT + 1 degenerado
    assert resumo["nos_orfaos"] == 2, "os 2 terminais do transformador longe de tudo"
    assert resumo["arestas_sem_no"] == 1, "o trecho degenerado"

    nos = sessao_a.get(f"/api/rede/{rid}/topologia/nos").json()["itens"]
    terminais_do_trafo_ligado = [n for n in nos if n["origem_id"] == trafo["id"]]
    assert len(terminais_do_trafo_ligado) == 2  # os 2 terminais existem como NÓS mesmo fundidos com trechos
    graus = sorted(n["grau"] for n in terminais_do_trafo_ligado)
    assert graus == [1, 1], "cada terminal (alta/baixa) fundiu com o trecho do SEU lado, 1 aresta cada"


# --- cláusula 7 (inegociável): inquilino B nunca lê nó/aresta/resumo de A -------------------------------

def test_inquilino_b_nunca_le_topologia_de_a(sessao_a, sessao_b, limpar_redes, env):
    rid = _criar_rede(sessao_a, "isolamento", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _linha(sessao_a, rid, [[-48.2, -17.2], [-48.2, -17.199]])
    _linha(sessao_a, rid, [[-48.2, -17.199], [-48.2, -17.198]])
    resumo = _habilitar(sessao_a, rid)
    assert resumo["nos"] > 0 and resumo["arestas"] > 0

    # nível API: B nem enxerga a rede (RLS em plat.rede já barra antes de chegar nas tabelas de topologia)
    assert sessao_b.get(f"/api/rede/{rid}").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/topologia").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/topologia/nos").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/topologia/arestas").status_code == 404

    # nível banco: mesmo com o id exato de A na cláusula WHERE, plat_app como B lê ZERO linhas — é a
    # RLS, não a rota, que garante o isolamento (a rota poderia ter um bug e a RLS ainda seguraria).
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        contexto(con, ids["demo2"])
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rid,))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid", (rid,))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rid,))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT count(*) AS n FROM plat.rede_feicao_linha WHERE rede_id = %s::uuid", (rid,))
            assert cur.fetchone()["n"] == 0
        con.rollback()

        # e o contrário: A não vazou nada nas tabelas globais de B por engano (contagem total é só de A)
        contexto(con, ids["demo"])
        with con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rid,))
            assert cur.fetchone()["n"] == resumo["nos"]
        con.rollback()
    finally:
        con.close()
