"""Montante e jusante numa bacia real, conferidos contra networkx (cláusula 3 do portão do item
L4-18-rede-simples-trace-network).

O dado é um recorte da Base Cartográfica Contínua 1:250.000 do IBGE (BC250, trecho de drenagem, dado aberto),
já no acervo da casa: `tests/dados/bacia_bc250.json` guarda UMA bacia — o maior componente conexo de um
retângulo do alto rio Grande (MG) — extraída por `tests/dados/gerar_bacia_bc250.py`, com a procedência dentro
do próprio arquivo. O recorte vira uma camada do inquilino, a camada vira rede simples e a rede é traçada.

A direção de fluxo é ATRIBUÍDA PELO TESTE por uma regra determinística sobre o `ogc_fid` (a maioria
digitalizada, uma fatia contra e uma fatia indeterminada). Isso é de propósito e não é uma afirmação sobre o
sentido real dos rios: o BC250 não traz coluna de direção, e o que a cláusula exige é que o traçado do
produto e um cálculo independente concordem SOBRE A MESMA declaração de direção. Uma bacia toda digitalizada
no mesmo sentido não exercitaria nem 'contra' nem 'indeterminada'.

A conferência independente é `networkx`: o teste remonta o grafo dirigido a partir do que a API publica
(as arestas da topologia e os atributos das feições), calcula alcançabilidade com `networkx.descendants` /
`ancestors` e compara conjunto a conjunto com o resultado do traçado."""

import json
import time
from pathlib import Path

import networkx
import pytest

from tests.api.apoio_camada_teste import conexao, criar_tabela_linhas, registrar_item
from tests.api.conftest import PREFIXO_TESTE

ARQUIVO = Path(__file__).resolve().parents[1] / "dados" / "bacia_bc250.json"
SCHEMA_DADO = "d_demo"
TAB_BACIA = "zt_l418_bacia"
CAMPOS = ["nome", "tipotrecho", "regime", "sentido"]
MAPA = {"jusante": "digitalizada", "invertido": "contra", "desconhecido": "indeterminada"}
ITEM = "L4-18-rede-simples-trace-network"


def _sentido(ogc_fid: int) -> str:
    """Regra determinística do teste (ver o cabeçalho): 1 em 7 contra, 1 em 11 indeterminada, o resto
    digitalizada. A ordem das condições faz de 77 em 77 uma 'contra', não uma 'indeterminada'."""
    if ogc_fid % 7 == 0:
        return "invertido"
    if ogc_fid % 11 == 0:
        return "desconhecido"
    return "jusante"


@pytest.fixture(scope="module")
def bacia():
    if not ARQUIVO.exists():
        pytest.skip(f"sem {ARQUIVO} (rode tests/dados/gerar_bacia_bc250.py como postgres)")
    doc = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    trechos = [{"nome": t["nome"], "tipotrecho": t["tipotrecho"], "regime": t["regime"],
                "sentido": _sentido(t["ogc_fid"]), "coordenadas": t["coordenadas"]}
               for t in doc["trechos"]]
    con = conexao()
    try:
        criar_tabela_linhas(con, SCHEMA_DADO, TAB_BACIA, trechos, CAMPOS)
    finally:
        con.close()
    return {"doc": doc, "trechos": trechos}


@pytest.fixture(scope="module")
def rede_bacia(sessao_a, bacia):
    item = registrar_item(sessao_a, f"{PREFIXO_TESTE}-l418-bacia-bc250", SCHEMA_DADO, TAB_BACIA,
                          "MultiLineString", CAMPOS)
    inicio = time.perf_counter()
    r = sessao_a.post("/api/rede/simples", json={
        "nome": f"{PREFIXO_TESTE}-simples-bacia-bc250", "disciplina": "agua",
        "camada_linha_id": item, "campo_direcao": "sentido", "mapa_direcao": MAPA,
        "atributos_rede": [{"nome": "regime", "tipo_dado": "texto", "de": "linha"}],
    })
    assert r.status_code == 201, r.text
    saida = r.json()
    saida["criar_ms"] = int((time.perf_counter() - inicio) * 1000)
    yield saida
    sessao_a.delete(f"/api/rede/{saida['rede_id']}")


def _grafo(sessao, rid) -> tuple[networkx.DiGraph, dict, set]:
    """Remonta o grafo dirigido do que a API publica: as arestas da topologia (com os nós de cada ponta) e a
    direção que está no ATRIBUTO de cada feição de trecho. Nada aqui usa o código do traçado."""
    arestas = sessao.get(f"/api/rede/{rid}/topologia/arestas?limite=2000").json()["itens"]
    feicoes = sessao.get(f"/api/rede/{rid}/feicoes/linhas?limite=2000").json()["itens"]
    direcao = {f["id"]: f["atributos"].get("direcao_fluxo") for f in feicoes}
    g = networkx.DiGraph()
    indeterminadas = set()
    por_par: dict = {}
    for a in arestas:
        origem, destino = a["no_origem_id"], a["no_destino_id"]
        if origem is None or destino is None:
            continue
        g.add_node(origem)
        g.add_node(destino)
        d = direcao[a["origem_id"]]
        if d == "indeterminada":
            indeterminadas.add(a["id"])
            continue
        de, para = (destino, origem) if d == "contra" else (origem, destino)
        g.add_edge(de, para)
        por_par.setdefault((origem, destino), []).append(a)
    return g, {a["id"]: a for a in arestas}, indeterminadas


def _elementos_esperados(arestas_por_id: dict, alcancados: set) -> set:
    """A mesma definição de elemento do produto: trecho cujas DUAS pontas foram alcançadas."""
    return {a["origem_id"] for a in arestas_por_id.values()
            if a["no_origem_id"] in alcancados and a["no_destino_id"] in alcancados}


def _tracar(sessao, rid, tipo, no) -> dict:
    r = sessao.post(f"/api/rede/{rid}/tracar", json={
        "tipo": tipo, "pontos_partida": [{"lon": no["lon"], "lat": no["lat"], "tolerancia_m": 0.05}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_bacia_bc250_carregou_inteira(sessao_a, bacia, rede_bacia):
    assert rede_bacia["feicoes"]["trechos"] == len(bacia["trechos"])
    assert rede_bacia["topologia"]["arestas"] == len(bacia["trechos"])
    assert rede_bacia["topologia"]["arestas_sem_no"] == 0
    # uma bacia é um componente conexo só: o traçado conectado de qualquer trecho alcança a bacia inteira
    nos = sessao_a.get(f"/api/rede/{rede_bacia['rede_id']}/topologia/nos?limite=2000").json()["itens"]
    con = _tracar(sessao_a, rede_bacia["rede_id"], "conectado", nos[0])
    assert con["nos_alcancados"] == len(nos), "a bacia extraída tem de ser um único componente conexo"


def test_montante_e_jusante_batem_com_networkx(sessao_a, bacia, rede_bacia, medida):
    rid = rede_bacia["rede_id"]
    nos = sessao_a.get(f"/api/rede/{rid}/topologia/nos?limite=2000").json()["itens"]
    g, arestas_por_id, indeterminadas = _grafo(sessao_a, rid)
    assert indeterminadas, "a regra de direção do teste tem de produzir trechos indeterminados"

    # nós de partida: os 12 com mais descendentes (traçados grandes) e os 12 com mais ancestrais, para que a
    # comparação não caia toda em folha de rio (traçado de 1 aresta acerta por acaso).
    por_id = {n["id"]: n for n in nos if n["id"] in g}
    escolhidos = sorted(por_id, key=lambda n: -len(networkx.descendants(g, n)))[:12]
    escolhidos += sorted(por_id, key=lambda n: -len(networkx.ancestors(g, n)))[:12]

    comparacoes = 0
    for no_id in dict.fromkeys(escolhidos):
        no = por_id[no_id]
        for tipo, alcance in (("jusante", networkx.descendants), ("montante", networkx.ancestors)):
            esperado_nos = alcance(g, no_id) | {no_id}
            resultado = _tracar(sessao_a, rid, tipo, no)
            assert resultado["nos_alcancados"] == len(esperado_nos), (tipo, no_id)
            obtidos = {e["feicao_id"] for e in resultado["elementos"] if e["terminal"] is None}
            assert obtidos == _elementos_esperados(arestas_por_id, esperado_nos), (tipo, no_id)
            comparacoes += 1
    assert comparacoes == 2 * len(dict.fromkeys(escolhidos))

    gravar = medida(ITEM)
    comando = ("bash laco/roda_teste.sh tests/api/test_rede_simples_bacia_bc250.py"
               "::test_montante_e_jusante_batem_com_networkx")
    gravar("bacia_bc250_trechos", len(bacia["trechos"]), "trechos", comando)
    gravar("bacia_bc250_nos", len(nos), "nós", comando)
    gravar("bacia_bc250_arestas_indeterminadas", len(indeterminadas), "arestas", comando)
    gravar("bacia_bc250_tracados_conferidos_contra_networkx", comparacoes, "traçados", comando)
    gravar("bacia_bc250_criar_rede_ms", rede_bacia["criar_ms"], "ms",
           comando + " (POST /api/rede/simples, camada -> feições -> topologia)")


def test_aviso_de_indeterminada_cita_trecho_encostado_no_resultado(sessao_a, rede_bacia):
    """Todo aviso nomeia uma aresta indeterminada que encosta no resultado — e nenhuma aresta indeterminada
    encostada fica sem aviso. É a refutação do item medida na bacia real, não só na rede sintética."""
    rid = rede_bacia["rede_id"]
    nos = sessao_a.get(f"/api/rede/{rid}/topologia/nos?limite=2000").json()["itens"]
    g, arestas_por_id, indeterminadas = _grafo(sessao_a, rid)
    por_id = {n["id"]: n for n in nos if n["id"] in g}
    no_id = max(por_id, key=lambda n: len(networkx.descendants(g, n)))
    resultado = _tracar(sessao_a, rid, "jusante", por_id[no_id])
    alcancados = networkx.descendants(g, no_id) | {no_id}
    esperado = {arestas_por_id[a]["origem_id"] for a in indeterminadas
                if arestas_por_id[a]["no_origem_id"] in alcancados
                or arestas_por_id[a]["no_destino_id"] in alcancados}
    assert {a["feicao_id"] for a in resultado["avisos"]} == esperado
    assert resultado["parou_em_indeterminada"] is bool(esperado)
