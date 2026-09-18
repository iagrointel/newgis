"""Portão do item L4-05-d-epanet-inp na ESCALA declarada, com rede SINTÉTICA determinística (marcador
`lento`) — complemento de `tests/api/test_rede_epanet.py`.

O arquivo REAL da casa (11.119 junções + 7 reservatórios, 14.756 trechos, 941.294 m, SIRGAS 2000/UTM 23S)
não está neste servidor remoto (é ativo interno da casa, fora do repositório); o teste que o consome pula
sem ele. Este aqui prova o MESMO caminho, no MESMO código, nas MESMAS contagens, com o `.inp` fictício de
`tests/dados/gerar_epanet.py` (semente fixa, grafo comprovadamente conexo, coordenadas em faixa UTM 23S —
o que obriga o caminho `crs_epsg=31983`, igual ao do arquivo real). Nasceu na trilha remota l405depc724
(18/09/2026), mesma solução do item irmão L4-01-b (`test_rede_topologia_sintetica_medida.py`): sem esta
prova, a cláusula de escala ficaria apoiada só no pulo do teste do arquivo real.

Prova, em sequência, num único teste (cada passo depende do anterior):
1. importação por JOB (`rede.epanet_importar`) com contagens iguais às do arquivo: 11.119 junções + 7
   reservatórios = 11.126 pontos, 14.756 trechos, zero feição sem geometria;
2. topologia habilitada: 14.756 arestas e 11.126 nós;
3. traçado conectado a partir do reservatório R1 alcança exatamente os nós da componente conexa calculada
   por networkx no PRÓPRIO .inp (a cláusula é a igualdade; o gerador garante grafo conexo, então o número
   esperado é 11.126 — a comparação é contra o networkx, não contra a constante);
4. `GET .../epanet` exporta e a reimportação numa rede NOVA dá o mesmo grafo (mesmas contagens de pontos e
   de linhas) e a mesma soma de comprimentos — em escala, não só na fixture de 6 nós;
5. a soma de comprimentos lida do arquivo (Σ Length de [PIPES]) é a mesma antes e depois da ida e volta —
   a comparação que a refutação do item pede.

Grava `tests/medidas/L4-05-d-epanet-inp-sintetica.json` (arquivo PRÓPRIO — nunca toca o JSON da medição do
arquivo real, que é o registro vivo daquela cláusula). Tempos vão gravados com a carga da máquina ao lado
(regra da casa, 07/09)."""

import json
import os
import subprocess
import time
from pathlib import Path

import networkx as nx
import pytest

from app.rede_utilidades import epanet_inp
from tests.api.test_rede_epanet import _criar_rede_agua, _importar
from tests.dados import gerar_epanet

MEDIDAS = Path(__file__).resolve().parent.parent / "medidas" / "L4-05-d-epanet-inp-sintetica.json"


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}", timeout=900)


@pytest.mark.lento
def test_portao_na_escala_com_rede_sintetica(sessao_a, limpar_redes):
    t0_gerar = time.perf_counter()
    texto = gerar_epanet.gerar_inp()
    bruto = texto.encode("utf-8")
    doc = epanet_inp.ler_inp(texto)
    assert doc.contagens() == gerar_epanet.CONTAGENS_ESPERADAS, doc.contagens()
    soma_arquivo = round(sum(p["length"] for p in doc.pipes), 2)
    assert soma_arquivo > 900_000, "o sintético tem de ficar na ordem dos 941 km do portão"
    medida = {"bytes_inp": len(bruto), "soma_comprimento_arquivo_m": soma_arquivo}

    # 1. importação por job, contagens iguais às do arquivo
    rid = _criar_rede_agua(sessao_a, "escala-origem", limpar_redes)
    t0 = time.monotonic()
    imp = _importar(sessao_a, rid, bruto, crs_epsg=31983, timeout=1200)
    medida["importacao_s"] = round(time.monotonic() - t0, 1)
    assert imp["estado"] == "concluida", imp.get("erro") or imp
    c = imp["contagens"]
    assert c["arquivo"] == gerar_epanet.CONTAGENS_ESPERADAS, c["arquivo"]
    assert c["gravado"]["pontos"] == 11119 + 7
    assert c["gravado"]["linhas"] == 14756
    assert c["pontos_sem_geometria"] == 0
    assert c["linhas_sem_geometria"] == 0
    medida["gravado_pontos"] = c["gravado"]["pontos"]
    medida["gravado_linhas"] = c["gravado"]["linhas"]

    # 2. topologia habilitada
    t0 = time.monotonic()
    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar", timeout=1200)
    medida["topologia_s"] = round(time.monotonic() - t0, 1)
    assert r.status_code == 201, r.text[:2000]
    resumo = r.json()
    assert resumo["arestas"] == 14756, resumo
    assert resumo["nos"] == 11126, resumo
    medida["topologia_nos"] = resumo["nos"]
    medida["topologia_arestas"] = resumo["arestas"]

    # 3. traçado x componente conexa do networkx no próprio .inp
    g = nx.Graph()
    g.add_nodes_from(j["id"] for j in doc.junctions)
    g.add_nodes_from(res["id"] for res in doc.reservoirs)
    g.add_edges_from((p["node1"], p["node2"]) for p in doc.pipes)
    reservatorio_id = doc.reservoirs[0]["id"]
    componente = nx.node_connected_component(g, reservatorio_id)
    import pyproj

    lon84, lat84 = pyproj.Transformer.from_crs(31983, 4326, always_xy=True).transform(
        *doc.coordinates[reservatorio_id])
    t0 = time.monotonic()
    r = sessao_a.post(f"/api/rede/{rid}/tracar", timeout=600,
                      json={"tipo": "conectado", "pontos_partida": [{"lon": lon84, "lat": lat84}]})
    medida["tracado_s"] = round(time.monotonic() - t0, 1)
    assert r.status_code == 200, r.text[:2000]
    alcancados = r.json()["nos_alcancados"]
    assert alcancados == len(componente), (alcancados, len(componente))
    medida["tracado_nos_alcancados"] = alcancados
    medida["componente_conexa_networkx"] = len(componente)

    # 4./5. exportar e reimportar dá o mesmo grafo, com a mesma soma de comprimentos
    t0 = time.monotonic()
    r = sessao_a.get(f"/api/rede/{rid}/epanet", timeout=600)
    medida["exportacao_s"] = round(time.monotonic() - t0, 1)
    assert r.status_code == 200, r.text[:500]
    exportado = r.content
    doc2 = epanet_inp.ler_inp(exportado.decode("utf-8"))
    assert doc2.contagens() == doc.contagens(), (doc2.contagens(), doc.contagens())
    soma_exportada = round(sum(p["length"] for p in doc2.pipes), 2)
    assert soma_exportada == pytest.approx(soma_arquivo, abs=0.01), (soma_exportada, soma_arquivo)

    rid2 = _criar_rede_agua(sessao_a, "escala-destino", limpar_redes)
    t0 = time.monotonic()
    imp2 = _importar(sessao_a, rid2, exportado, crs_epsg=31983, timeout=1200)
    medida["reimportacao_s"] = round(time.monotonic() - t0, 1)
    assert imp2["estado"] == "concluida", imp2.get("erro") or imp2
    assert imp2["contagens"]["gravado"]["pontos"] == imp["contagens"]["gravado"]["pontos"]
    assert imp2["contagens"]["gravado"]["linhas"] == imp["contagens"]["gravado"]["linhas"]
    medida["ida_e_volta_mesmo_grafo"] = True

    medida["geracao_inp_s"] = round(time.perf_counter() - t0_gerar, 3)
    medida["carga_1min"] = round(os.getloadavg()[0], 2)
    medida["ram_livre_gb"] = round(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3, 1)

    anteriores = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    anteriores.update({
        "item": "L4-05-d-epanet-inp",
        "git_sha": sha,
        "tipo": "rede SINTÉTICA determinística (tests/dados/gerar_epanet.py, semente fixa) nas contagens "
                "exatas do portão — complemento da medição contra o arquivo real da casa, que não existe "
                "neste servidor remoto",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "comando": "venv/bin/pytest tests/api/test_rede_epanet_escala.py -m lento -q",
        "rede_sintetica_escala_portao": medida,
    })
    MEDIDAS.write_text(json.dumps(anteriores, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
