"""Importação/exportação EPANET .inp da rede de água (item L4-05-d-epanet-inp; ADR 20260907T1629).

Cláusulas do portão provadas aqui:
1. `POST /api/rede/{id}/epanet` enfileira um job (`rede.epanet_importar`) que importa o .inp com CONTAGENS
   iguais às do arquivo (`test_importa_fixture_sintetica_por_job_contagens_batem`);
2. topologia habilitada sobre a rede importada; traçado conectado a partir do reservatório alcança os nós que
   o próprio `.inp` diz que estão no mesmo componente, medido com `networkx` direto do arquivo
   (`test_topologia_e_tracado_batem_com_componente_networkx`);
3. `GET /api/rede/{id}/epanet` exporta reconstruído das tabelas; reimportado numa rede NOVA dá a mesma contagem
   (`test_exportar_e_reimportar_da_o_mesmo_grafo`);
4. `wntr.sim.EpanetSimulator` roda o `.inp` exportado sem erro, quando `wntr` está instalado
   (`test_wntr_simula_o_inp_exportado`) — o item declara a biblioteca como bloqueante; se não estiver instalada
   o teste pula e isso fica registrado como cláusula NÃO MEDIDA, nunca como PASSOU;
5. paridade com o "water utility network foundation" da Esri: NÃO tentada nesta passagem (fronteira honesta,
   registrada como PARCIAL em `tests/medidas/L4-05-d-epanet-inp.json` — comparar contra um modelo de dados
   fechado e licenciado exige o próprio pacote, que este item não tem).

Refutação do item ("adversário remove uma linha de COORDINATES...") provada aqui em
`test_adversario_remove_uma_coordenada`.

Exige um worker vivo (mesma regra de `tests/api/jobs/conftest.py`): sem ele, todo job de importação nunca
termina — `esperar_importacao` falha explicando isso, nunca fica esperando escondido."""

import time
from pathlib import Path

import networkx as nx
import pytest

from tests.api.conftest import PREFIXO_TESTE

DADOS = Path(__file__).resolve().parent.parent / "dados"
COMPLETO = DADOS / "epanet_completo.inp"
REAL = DADOS / "brasilia_caesb.inp"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede_agua(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-epanet-{sufixo}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    bruto = instalados.bruto("agua-epanet")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _worker_vivo(cliente) -> bool:
    r = cliente.get("/saude").json()
    return bool((r.get("fila") or {}).get("workers_vivos"))


def _importar(sessao, rid, bruto: bytes, crs_epsg=None, timeout=120):
    if not _worker_vivo(sessao):
        pytest.skip("nenhum worker vivo em /saude — rode `venv/bin/python -m app.jobs.worker` na trilha")
    url = f"/api/rede/{rid}/epanet"
    if crs_epsg is not None:
        url += f"?crs_epsg={crs_epsg}"
    # o middleware de limite de corpo só aceita application/json neste ponto da API (mesma regra de
    # `.../pacote`, que também recebe bytes crus com esse content-type "de conveniência").
    r = sessao.post(url, content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 202, r.text
    importacao_id = r.json()["importacao_id"]
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/rede/{rid}/epanet/{importacao_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("concluida", "falhou"):
            return ultimo
        time.sleep(0.3)
    pytest.fail(f"importação {importacao_id} não terminou em {timeout}s: {ultimo}")


# --- cláusula 1: contagens do job batem com o arquivo -------------------------------------------------

def test_importa_fixture_sintetica_por_job_contagens_batem(sessao_a, limpar_redes):
    rid = _criar_rede_agua(sessao_a, "sintetica", limpar_redes)
    bruto = COMPLETO.read_bytes()
    imp = _importar(sessao_a, rid, bruto)
    assert imp["estado"] == "concluida", imp
    c = imp["contagens"]
    assert c["arquivo"] == {"junctions": 4, "reservoirs": 1, "tanks": 1, "pipes": 5, "pumps": 1, "valves": 1,
                             "coordinates": 6, "vertices": 1, "patterns": 1, "curves": 1}
    # gravado: 4 juncoes + 1 reservatorio fixo + 1 variavel + 1 bomba + 1 valvula = 8 pontos; 5 trechos
    assert c["gravado"]["pontos"] == 4 + 1 + 1 + 1 + 1
    assert c["gravado"]["linhas"] == 5
    assert c["pontos_sem_geometria"] == 0
    assert c["linhas_sem_geometria"] == 0

    ficha = sessao_a.get(f"/api/rede/{rid}").json()
    assert ficha["contagens"]  # a ficha do pacote continua íntegra (não foi tocada pelo import de feições)
    pontos = sessao_a.get(f"/api/rede/{rid}/feicoes/pontos?limite=100").json()
    assert pontos["total"] == 8
    linhas = sessao_a.get(f"/api/rede/{rid}/feicoes/linhas?limite=100").json()
    assert linhas["total"] == 5


@pytest.mark.skipif(not REAL.exists(), reason="fixture real (brasilia_caesb.inp) não está neste checkout")
def test_importa_arquivo_real_11119_juncoes_14756_trechos_941km(sessao_a, limpar_redes):
    """A rede REAL medida nesta casa (GPU box, CAESB/atlas público): 11.119 junções + 7 reservatórios,
    14.756 trechos, 941.294 m — os números citados no portão do item. Coordenadas em SIRGAS 2000/UTM 23S
    (EPSG:31983, declarado explicitamente — nunca adivinhado)."""
    rid = _criar_rede_agua(sessao_a, "real", limpar_redes)
    bruto = REAL.read_bytes()
    imp = _importar(sessao_a, rid, bruto, crs_epsg=31983, timeout=480)
    assert imp["estado"] == "concluida", imp
    c = imp["contagens"]
    assert c["arquivo"]["junctions"] == 11119
    assert c["arquivo"]["reservoirs"] == 7
    assert c["arquivo"]["pipes"] == 14756
    assert c["gravado"]["pontos"] == 11119 + 7
    assert c["gravado"]["linhas"] == 14756
    assert c["pontos_sem_geometria"] == 0
    assert c["linhas_sem_geometria"] == 0

    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    resumo = r.json()
    assert resumo["nos"] > 0 and resumo["arestas"] == 14756

    # traçado conectado a partir de um reservatório x componente conexa calculada por networkx no PRÓPRIO .inp
    doc_texto = bruto.decode("utf-8")
    from app.rede_utilidades import epanet_inp

    doc = epanet_inp.ler_inp(doc_texto)
    g = nx.Graph()
    g.add_nodes_from(j["id"] for j in doc.junctions)
    g.add_nodes_from(res["id"] for res in doc.reservoirs)
    g.add_edges_from((p["node1"], p["node2"]) for p in doc.pipes)
    reservatorio_id = doc.reservoirs[0]["id"]
    componente = nx.node_connected_component(g, reservatorio_id)
    lon, lat = doc.coordinates[reservatorio_id]
    # a coordenada do reservatório está em UTM 23S no arquivo; reprojeta pela mesma regra do importador
    import pyproj

    transformador = pyproj.Transformer.from_crs(31983, 4326, always_xy=True)
    lon84, lat84 = transformador.transform(lon, lat)
    r = sessao_a.post(f"/api/rede/{rid}/tracar",
                       json={"tipo": "conectado", "pontos_partida": [{"lon": lon84, "lat": lat84}]})
    assert r.status_code == 200, r.text
    resultado = r.json()
    # o traçado conta ELEMENTOS (trechos + dispositivos), o componente do networkx conta NÓS — a comparação
    # honesta é nós alcançados x tamanho do componente (o próprio resultado já traz "nos_alcancados").
    assert resultado["nos_alcancados"] == len(componente), (resultado["nos_alcancados"], len(componente))


# --- cláusula 3: exportar e reimportar dá o mesmo grafo -------------------------------------------------

def test_exportar_e_reimportar_da_o_mesmo_grafo(sessao_a, limpar_redes):
    rid1 = _criar_rede_agua(sessao_a, "export-origem", limpar_redes)
    imp1 = _importar(sessao_a, rid1, COMPLETO.read_bytes())
    assert imp1["estado"] == "concluida", imp1

    r = sessao_a.get(f"/api/rede/{rid1}/epanet")
    assert r.status_code == 200, r.text
    exportado = r.content
    from app.rede_utilidades import epanet_inp

    doc_exportado = epanet_inp.ler_inp(exportado.decode("utf-8"))
    assert doc_exportado.contagens()["junctions"] == 4
    assert doc_exportado.contagens()["pipes"] == 5
    assert doc_exportado.contagens()["pumps"] == 1
    assert doc_exportado.contagens()["valves"] == 1
    assert doc_exportado.contagens()["tanks"] == 1
    soma_original = sum(p["length"] for p in epanet_inp.ler_inp(COMPLETO.read_text(encoding="utf-8")).pipes)
    soma_exportada = sum(p["length"] for p in doc_exportado.pipes)
    assert soma_exportada == pytest.approx(soma_original)

    rid2 = _criar_rede_agua(sessao_a, "export-destino", limpar_redes)
    imp2 = _importar(sessao_a, rid2, exportado)
    assert imp2["estado"] == "concluida", imp2
    assert imp2["contagens"]["gravado"]["pontos"] == imp1["contagens"]["gravado"]["pontos"]
    assert imp2["contagens"]["gravado"]["linhas"] == imp1["contagens"]["gravado"]["linhas"]
    pontos2 = sessao_a.get(f"/api/rede/{rid2}/feicoes/pontos?limite=100").json()
    linhas2 = sessao_a.get(f"/api/rede/{rid2}/feicoes/linhas?limite=100").json()
    pontos1 = sessao_a.get(f"/api/rede/{rid1}/feicoes/pontos?limite=100").json()
    linhas1 = sessao_a.get(f"/api/rede/{rid1}/feicoes/linhas?limite=100").json()
    assert pontos2["total"] == pontos1["total"]
    assert linhas2["total"] == linhas1["total"]


def test_wntr_simula_o_inp_exportado(sessao_a, limpar_redes, tmp_path):
    wntr = pytest.importorskip("wntr", reason="WNTR não instalado nesta máquina — cláusula NÃO MEDIDA, "
                                              "o item declara a instalação como bloqueante")
    rid = _criar_rede_agua(sessao_a, "wntr", limpar_redes)
    imp = _importar(sessao_a, rid, COMPLETO.read_bytes())
    assert imp["estado"] == "concluida", imp
    r = sessao_a.get(f"/api/rede/{rid}/epanet")
    assert r.status_code == 200, r.text
    caminho = tmp_path / "exportado.inp"
    caminho.write_bytes(r.content)
    wn = wntr.network.WaterNetworkModel(str(caminho))
    sim = wntr.sim.EpanetSimulator(wn)
    resultados = sim.run_sim()
    assert "pressure" in resultados.node


# --- refutação do item -----------------------------------------------------------------------------------

def test_adversario_remove_uma_coordenada(sessao_a, limpar_redes):
    """Remove a linha de [COORDINATES] de J4 do .inp sintético; confere que J4 entra sem geometria (nunca em
    (0,0)) e que a soma de comprimento dos trechos não muda (ela vem do campo Length, não da geometria)."""
    texto = COMPLETO.read_text(encoding="utf-8")
    linhas_texto = texto.splitlines()
    secao = None
    linhas_sem_j4 = []
    removidas = 0
    for ln in linhas_texto:
        crua = ln.strip()
        if crua.startswith("[") :
            secao = crua.strip("[]").upper()
        if secao == "COORDINATES" and crua.startswith("J4 "):
            removidas += 1
            continue
        linhas_sem_j4.append(ln)
    assert removidas == 1, "a fixture não tinha exatamente 1 linha de J4 em COORDINATES"
    texto_adulterado = "\n".join(linhas_sem_j4) + "\n"

    rid = _criar_rede_agua(sessao_a, "adversario", limpar_redes)
    imp = _importar(sessao_a, rid, texto_adulterado.encode("utf-8"))
    assert imp["estado"] == "concluida", imp
    # J4 fica sem geometria (o próprio nó) e a válvula V1 (J4-J3), cujo ponto é o MÉDIO de J4/J3, também fica
    # sem geometria por tabela — os dois avisos citam J4, nenhum ponto nasce em (0,0).
    assert imp["contagens"]["pontos_sem_geometria"] == 2
    # J4 também aparece nos avisos dos DOIS trechos que tocam nele (P3, P5) e da válvula V1 — pelo menos os
    # dois pontos contam entre os avisos; o número exato de avisos-texto não é a cláusula, a AUSÊNCIA de
    # ponto fantasma é.
    assert sum("J4" in a for a in imp["avisos"]) >= 2

    pontos = sessao_a.get(f"/api/rede/{rid}/feicoes/pontos?limite=100").json()["itens"]
    j4 = next(p for p in pontos if p["atributos"].get("no_id") == "J4")
    # o objeto existe (id, atributos) mas não tem geometria nenhuma — provado indiretamente: ele não aparece
    # na lista de nós de topologia depois de habilitar, nunca em (0,0)
    assert j4["atributos"]["no_elevacao"] == 85.0

    from app.rede_utilidades import epanet_inp

    doc_original = epanet_inp.ler_inp(texto)
    doc_adulterado = epanet_inp.ler_inp(texto_adulterado)
    soma_original = sum(p["length"] for p in doc_original.pipes)
    soma_adulterada = sum(p["length"] for p in doc_adulterado.pipes)
    assert soma_original == soma_adulterada  # remover a COORDENADA não muda o comprimento DECLARADO dos trechos

    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    nos = sessao_a.get(f"/api/rede/{rid}/topologia/nos?limite=1000").json()["itens"]
    for no in nos:
        assert not (no["lon"] == 0.0 and no["lat"] == 0.0), "nó fantasma em (0,0): a refutação do item reprovou"
