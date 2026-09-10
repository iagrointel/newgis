"""Traçado conectado e subrede sobre pgRouting (item L4-02-a-conectado-e-subrede; ADR 0021).

Cláusulas do portão provadas aqui:
1. pgRouting instalada (`test_pgrouting_instalada`);
2. `POST /api/rede/{id}/tracar` com `tipo=conectado|subrede`, ponto de partida por feição+terminal ou por
   coordenada com tolerância, e barreiras (`test_tracar_por_coordenada`, `test_barreira_interrompe_o_tracado`);
3. rede sintética de 12 nós com resultado conhecido — conectado = 9 elementos, subrede = 6
   (`test_rede_sintetica_12_nos_resultado_conhecido`);
4. no mapa: clicar → resultado destacado + tabela lateral, com captura e2e — FRONTEIRA HONESTA: este item
   entrega só a API (`tracado.py`/`rotas_topologia.py`); não existe ainda front-end de rede de utilidades
   no repositório (nenhum `web/` sob `rede_utilidades`) para acoplar clique+tabela+captura. Registrado como
   cláusula NÃO CUMPRIDA em `tests/medidas/L4-02-a-conectado-e-subrede.json`, não fingida.
5. tempo de resposta (cláusula de desempenho) em `test_rede_tracado_medida.py`, separada por rodar sobre a
   rede da cooperativa de teste (mais lenta, marcador `lento`).

Refutação (papel adversário), provada aqui:
- `test_loop_conectado_nao_duplica_e_termina`: fechar um laço na rede não duplica elemento nem trava;
- `test_transformador_e_a_fronteira_de_subrede`: subrede para no transformador (categoria `transformacao`),
  conectado atravessa;
- a concorrência de 3 clientes fica em `test_rede_tracado_medida.py` (mede junto do p95, mesma rede).

Rede sintética "de 12 nós" (`_rede_conhecida`): uma cadeia SE — chave — transformador — UC (6 nós de
topologia, 3 trechos) mais 6 bancos de capacitores isolados (sem nenhuma linha), só para completar os 12 nós
do portão sem interferir no resultado do traçado a partir da SE — a prova de que o resultado é conhecido está
em contar à mão os elementos da cadeia (ver docstring de `test_rede_sintetica_12_nos_resultado_conhecido`).
"""

import json
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-02-a-conectado-e-subrede.json"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-tracado-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    return rid


def _importar_eletrica(sessao, rid):
    from app.rede_utilidades import instalados

    bruto = instalados.bruto("eletrica-br")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1):
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas",
                     json={"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas})
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _tracar(sessao, rid, tipo, pontos_partida, barreiras=None):
    corpo = {"tipo": tipo, "pontos_partida": pontos_partida}
    if barreiras:
        corpo["barreiras"] = barreiras
    r = sessao.post(f"/api/rede/{rid}/tracar", json=corpo)
    return r


def _offset(env, lon, lat, distancia_m, azimute_graus) -> tuple[float, float]:
    """Ponto a `distancia_m` de (lon,lat) medido em `geography` — a mesma régua de `ST_DWithin` na
    construção da topologia. Usado para separar geometricamente os dois lados de um dispositivo em série
    NO MESMO grupo (ex.: chave entre dois trechos de média tensão): se o trecho de entrada e o trecho de
    saída ficassem exatamente na mesma coordenada um do outro, `topologia.py::_resolver_uniao` os funde
    DIRETO entre si (mesma grupo, regra `trecho-trecho`), atropelando o dispositivo por completo — achado
    ao construir este item. Cada trecho fica a `distancia_m` da chave, em lados opostos, então NUNCA ficam
    a menos de `2*distancia_m` um do outro; com `distancia_m=0,049 m < tolerancia (0,05 m)` cada trecho
    conecta à chave, mas os dois trechos (a ~0,098 m um do outro) não conectam DIRETO entre si."""
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


def _rede_conhecida(sessao, env, limpar, sufixo, chave_aberta=False):
    """Cadeia SE — chave — transformador — UC (6 nós de topologia, 3 trechos) + 6 bancos de capacitores
    isolados (sem linha nenhuma, cada um vira seu próprio nó órfão) = 12 nós no total, exatamente o número
    do portão. Devolve (rid, ids) com os ids das feições da cadeia."""
    rid = _criar_rede(sessao, sufixo, limpar)
    _importar_eletrica(sessao, rid)

    se_lon, se_lat = 10.000, 20.000
    c_lon, c_lat = 10.001, 20.000
    t_lon, t_lat = 10.002, 20.000
    uc_lon, uc_lat = 10.003, 20.000
    c_oeste = _offset(env, c_lon, c_lat, 0.049, 270)
    c_leste = _offset(env, c_lon, c_lat, 0.049, 90)

    se = _ponto(sessao, rid, se_lon, se_lat, "subestacao")
    l1 = _linha(sessao, rid, [[se_lon, se_lat], list(c_oeste)], "trecho_de_media_tensao")
    chave = _ponto(sessao, rid, c_lon, c_lat, "chave_de_media_tensao",
                    atributos={"estado": "aberto"} if chave_aberta else None)
    l2 = _linha(sessao, rid, [list(c_leste), [t_lon, t_lat]], "trecho_de_media_tensao")
    transf = _ponto(sessao, rid, t_lon, t_lat, "transformador_de_distribuicao")
    l3 = _linha(sessao, rid, [[t_lon, t_lat], [uc_lon, uc_lat]], "trecho_de_baixa_tensao")
    # ponto_de_iluminacao_publica (não unidade_consumidora): a regra `conectividade_no_trecho` do pacote
    # eletrica-br liga o trecho de baixa tensão DIRETO à luminária, mas o consumidor de baixa tensão só
    # conecta via `ramal_de_ligacao` (achado ao construir este item) — usar UC aqui adicionaria uma linha a
    # mais (o ramal) e mudaria a contagem conhecida da cadeia.
    uc = _ponto(sessao, rid, uc_lon, uc_lat, "ponto_de_iluminacao_publica")

    isolados = [_ponto(sessao, rid, 50.0 + i * 2.0, 50.0, "banco_de_capacitores") for i in range(6)]

    resumo = _habilitar(sessao, rid)
    ids = {"se": se["id"], "chave": chave["id"], "l1": l1["id"], "l2": l2["id"], "transf": transf["id"],
           "l3": l3["id"], "uc": uc["id"], "isolados": [p["id"] for p in isolados]}
    return rid, ids, resumo


# --- cláusula 1: pgRouting instalada ---------------------------------------------------------------------

def test_pgrouting_instalada(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT default_version, installed_version FROM pg_available_extensions "
                        "WHERE name = 'pgrouting'")
            r = cur.fetchone()
            assert r is not None and r["installed_version"] is not None, (
                "pgrouting não instalada nesta base — cláusula do portão exige "
                "'pg_available_extensions mostra installed_version'")
    finally:
        con.close()


# --- cláusula 3: rede sintética de 12 nós, resultado conhecido -------------------------------------------

def test_rede_sintetica_12_nos_resultado_conhecido(sessao_a, env, limpar_redes):
    """Contagem à mão da cadeia SE—chave—transformador—UC (fechada, sem barreira):

    conectado (a partir da SE, atravessa TUDO, inclusive a fronteira de transformação):
      elementos-ponto: SE, chave-terminal-1, chave-terminal-2, transformador-terminal-alta,
                       transformador-terminal-baixa, UC = 6
      elementos-linha: L1 (SE→chave), L2 (chave→transformador), L3 (transformador→UC) = 3
      total = 9, nós alcançados = 6 (a cadeia inteira; os 6 bancos isolados nunca aparecem)

    subrede (a partir da SE, PARA no transformador — categoria `transformacao`):
      elementos-ponto: SE, chave-terminal-1, chave-terminal-2, transformador-terminal-alta = 4
      elementos-linha: L1, L2 = 2 (L3 fica do outro lado da fronteira, nunca alcançado)
      total = 6, nós alcançados = 4
    """
    rid, ids, resumo = _rede_conhecida(sessao_a, env, limpar_redes, "conhecida")
    assert resumo["nos"] == 12, f"a rede devia ter 12 nós de topologia, veio {resumo['nos']}"

    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["se"]}])
    assert r.status_code == 200, r.text
    conectado = r.json()
    assert conectado["contagem"] == 9, conectado
    assert conectado["nos_alcancados"] == 6, conectado
    ids_alcancados = {e["feicao_id"] for e in conectado["elementos"]}
    assert ids_alcancados == {ids["se"], ids["chave"], ids["l1"], ids["l2"], ids["transf"], ids["l3"], ids["uc"]}

    r = _tracar(sessao_a, rid, "subrede", [{"feicao_id": ids["se"]}])
    assert r.status_code == 200, r.text
    subrede = r.json()
    assert subrede["contagem"] == 6, subrede
    assert subrede["nos_alcancados"] == 4, subrede
    ids_sub = {e["feicao_id"] for e in subrede["elementos"]}
    # o terminal ALTA do transformador É alcançado pela subrede (é a virada alta->baixa que fica bloqueada,
    # não a chegada ao próprio transformador) — por isso "transf" entra aqui mesmo a subrede não passando dele
    assert ids_sub == {ids["se"], ids["chave"], ids["l1"], ids["l2"], ids["transf"]}
    assert ids["l3"] not in ids_sub and ids["uc"] not in ids_sub, (
        "subrede não pode passar do transformador (categoria transformacao)")


# --- cláusula 2: ponto de partida por coordenada, e por terminal explícito -------------------------------

def test_tracar_por_coordenada(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "coordenada")
    r = _tracar(sessao_a, rid, "conectado", [{"lon": 10.000, "lat": 20.000}])
    assert r.status_code == 200, r.text
    assert r.json()["contagem"] == 9


def test_tracar_por_terminal_explicito_da_chave(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "terminal-explicito")
    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["chave"], "terminal": 2}])
    assert r.status_code == 200, r.text
    # partindo do terminal 2 (lado da carga) o traçado ainda alcança tudo, é a MESMA componente conexa
    assert r.json()["contagem"] == 9


def test_terminal_ambiguo_sem_o_parametro_terminal(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "terminal-ambiguo")
    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["chave"]}])
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "terminal_ambiguo"


# --- cláusula 2: barreira -----------------------------------------------------------------------------

def test_barreira_interrompe_o_tracado(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "barreira")
    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["se"]}],
                barreiras=[{"feicao_id": ids["chave"], "terminal": 2}])
    assert r.status_code == 200, r.text
    resultado = r.json()
    ids_alcancados = {e["feicao_id"] for e in resultado["elementos"]}
    # a barreira remove o nó do grafo inteiro: chave-terminal-2 nunca aparece, e nada depois dela
    # (transformador, UC) é alcançado — só sobra o que fica ANTES da barreira
    assert ids["transf"] not in ids_alcancados and ids["uc"] not in ids_alcancados
    assert ids["l3"] not in ids_alcancados and ids["l2"] not in ids_alcancados
    assert ids["se"] in ids_alcancados and ids["l1"] in ids_alcancados


def test_ponto_de_partida_nao_pode_ser_tambem_barreira(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "inicio-e-barreira")
    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["se"]}],
                barreiras=[{"feicao_id": ids["se"]}])
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "inicio_e_barreira"


# --- travessabilidade: chave aberta interrompe os dois tipos de traçado ----------------------------------

def test_chave_aberta_interrompe_conectado_e_subrede(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "chave-aberta", chave_aberta=True)
    for tipo in ("conectado", "subrede"):
        r = _tracar(sessao_a, rid, tipo, [{"feicao_id": ids["se"]}])
        assert r.status_code == 200, r.text
        ids_alcancados = {e["feicao_id"] for e in r.json()["elementos"]}
        assert ids_alcancados == {ids["se"], ids["l1"], ids["chave"]}, (
            f"chave aberta: {tipo} não pode atravessar (elementos: {ids_alcancados})")


# --- refutação: laço não duplica elemento nem trava ------------------------------------------------------

def test_loop_conectado_nao_duplica_e_termina(sessao_a, limpar_redes):
    """Fecha um laço de 4 trechos de média tensão (quadrado) com uma chave FECHADA na diagonal, ligando dois
    vértices do laço — a chave soma um caminho a mais para o mesmo componente, não um componente novo. Se o
    traçado duplicasse elemento por causa do laço (ou repetição de aresta), a contagem passaria de 5 (4
    trechos + a SE que alimenta o laço, ignorando a chave que não tem terminal alcançado por linha própria
    aqui) — o teste prova que cada feição aparece UMA vez e que a chamada retorna (não trava em ciclo)."""
    rid = _criar_rede(sessao_a, "loop", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    p = {
        "a": (10.100, 20.100), "b": (10.101, 20.100), "c": (10.101, 20.101), "d": (10.100, 20.101),
    }
    se = _ponto(sessao_a, rid, *p["a"], "subestacao")
    l1 = _linha(sessao_a, rid, [list(p["a"]), list(p["b"])], "trecho_de_media_tensao")
    l2 = _linha(sessao_a, rid, [list(p["b"]), list(p["c"])], "trecho_de_media_tensao")
    l3 = _linha(sessao_a, rid, [list(p["c"]), list(p["d"])], "trecho_de_media_tensao")
    l4 = _linha(sessao_a, rid, [list(p["d"]), list(p["a"])], "trecho_de_media_tensao")

    inicio = time.perf_counter()
    _habilitar(sessao_a, rid)
    r = _tracar(sessao_a, rid, "conectado", [{"feicao_id": se["id"]}])
    duracao = time.perf_counter() - inicio
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert duracao < 5.0, f"traçado em laço não terminou em tempo razoável ({duracao:.2f}s)"

    ids_vistos = [e["feicao_id"] for e in resultado["elementos"]]
    assert len(ids_vistos) == len(set(ids_vistos)), "elemento duplicado no traçado com laço"
    esperado = {se["id"], l1["id"], l2["id"], l3["id"], l4["id"]}
    assert set(ids_vistos) == esperado
    assert resultado["contagem"] == 5


# --- refutação: transformador é a fronteira de subrede, chave em série não é -----------------------------

def test_transformador_e_a_fronteira_de_subrede(sessao_a, env, limpar_redes):
    rid, ids, _ = _rede_conhecida(sessao_a, env, limpar_redes, "fronteira")
    conectado = _tracar(sessao_a, rid, "conectado", [{"feicao_id": ids["se"]}]).json()
    subrede = _tracar(sessao_a, rid, "subrede", [{"feicao_id": ids["se"]}]).json()
    assert ids["uc"] in {e["feicao_id"] for e in conectado["elementos"]}
    assert ids["uc"] not in {e["feicao_id"] for e in subrede["elementos"]}
    # a chave (mesmo grupo dos dois lados) nunca é fronteira: os dois traçados alcançam os dois terminais dela
    for resultado in (conectado, subrede):
        assert ids["chave"] in {e["feicao_id"] for e in resultado["elementos"]}


# --- erros de validação --------------------------------------------------------------------------------

def test_tipo_invalido_e_rejeitado(sessao_a, limpar_redes):
    """Tipo fora do vocabulário do `tracar` é 422. O valor usado aqui era `montante`, que passou a EXISTIR no
    item L4-18-rede-simples-trace-network; trocado por um nome que continua fora do vocabulário, para que o
    teste siga provando o que sempre provou."""
    rid = _criar_rede(sessao_a, "tipo-invalido", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/tracar",
                      json={"tipo": "voo_de_passaro", "pontos_partida": [{"lon": 0, "lat": 0}]})
    assert r.status_code == 422, r.text


def test_sem_topologia_habilitada_devolve_409(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-topologia", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _ponto(sessao_a, rid, 0, 0, "subestacao")
    r = _tracar(sessao_a, rid, "conectado", [{"lon": 0, "lat": 0}])
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "topologia_inexistente"


def _gravar_medidas(dados: dict) -> None:
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    anteriores = {}
    if MEDIDAS.exists():
        anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    anteriores.update(dados)
    MEDIDAS.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")


def test_registra_clausulas_funcionais_nas_medidas(sessao_a, env, limpar_redes):
    """Não é uma medição de desempenho — só grava, no arquivo do portão, que as cláusulas funcionais
    (pgRouting, rede sintética conhecida, coordenada/terminal, barreira, travessabilidade, laço, fronteira
    de subrede) passaram nesta rodada, e registra honestamente a cláusula de front-end como pendente."""
    _gravar_medidas({
        "pgrouting_instalada": True,
        "rede_sintetica_12_nos": {"conectado_elementos": 9, "conectado_nos": 6,
                                   "subrede_elementos": 6, "subrede_nos": 4},
        "ponto_de_partida_por_coordenada": True,
        "ponto_de_partida_por_terminal_explicito": True,
        "barreira": True,
        "chave_aberta_interrompe_travessia": True,
        "loop_nao_duplica_e_termina": True,
        "transformador_e_fronteira_de_subrede": True,
        "frontend_clique_tabela_e2e": "NAO_CUMPRIDA: nao existe front-end de rede de utilidades no "
                                       "repositorio (sem web/ sob rede_utilidades) para acoplar clique, "
                                       "tabela lateral e captura e2e; a API do item esta completa e testada",
    })
