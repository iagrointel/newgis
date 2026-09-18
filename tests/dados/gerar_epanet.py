"""Gerador do .inp SINTÉTICO DETERMINÍSTICO na escala do portão do item L4-05-d-epanet-inp.

O arquivo REAL da casa (rede de água de operadora, dado público: 11.119 junções + 7 reservatórios, 14.756
trechos, 941.294 m, SIRGAS 2000 / UTM 23S) não está no repositório nem neste servidor remoto — o teste que o
consome (`tests/api/test_rede_epanet.py::test_importa_arquivo_real_11119_juncoes_14756_trechos_941km`) pula
sem ele. Este gerador produz um `.inp` FICTÍCIO com as MESMAS CONTAGENS e a mesma ordem de grandeza de
comprimento, com semente fixa (a mesma chamada produz sempre o mesmo texto — todo número citado a partir
daqui é do GERADOR, nunca do arquivo da operadora).

Modelo: malha retangular de 106 x 105 células (11.130 posições; as 4 últimas são cortadas para fechar em
11.126 nós = 11.119 junções + 7 reservatórios), passo ~63,79 m com jitter determinístico de ±2,5 m (a média
de comprimento do portão é 941.294 / 14.756 = 63,79 m). A malha tem 22.049 arestas candidatas; uma floresta
geradora aleatória (Kruskal com a semente fixa) garante UM componente conexo com 11.125 trechos, e as
3.631 arestas seguintes do embaralhamento completam os 14.756. Coordenadas na faixa de SIRGAS 2000 / UTM 23S
(EPSG:31983) de propósito — o caminho `crs_epsg=31983` do importador é o mesmo do arquivo real.

Sem bombas, válvulas, padrões ou curvas: essas seções são exercidas na escala pequena pela fixture
`tests/dados/epanet_completo.inp` (a cláusula de ida e volta delas mora em `tests/unit/test_epanet_inp.py` e
em `tests/api/test_rede_epanet.py`); aqui o que se prova é o FUNDO DE ESCALA do portão (contagens, topologia,
traçado contra networkx, exportar e reimportar)."""

import math
import random

SEMENTE = 20260918
N_JUNCOES = 11_119
N_RESERVATORIOS = 7
N_NOS = N_JUNCOES + N_RESERVATORIOS  # 11.126
N_TUBOS = 14_756
SOMA_ALVO_M = 941_294.02  # a referência de magnitude do portão (arquivo real da casa)

_COLS = 106
_ROWS = 105  # 106*105 = 11.130; cortadas as 4 últimas posições -> 11.126 nós
_X0, _Y0 = 187_000.0, 8_252_000.0  # faixa UTM 23S (EPSG:31983); ponto arbitrário, não é dado de operadora
_PASSO = SOMA_ALVO_M / N_TUBOS  # ~63,79 m
_JITTER = 2.5

# posições (índice na malha) que viram reservatório: espalhadas, nunca na última linha cortada
_RESERVATORIO_IDX = (0, 1855, 3710, 5565, 7420, 9275, 11125)


def _nos(rng: random.Random) -> tuple[list[str], dict[str, tuple[float, float]]]:
    """ids e coordenadas UTM dos 11.126 nós; os 7 reservatórios recebem ids R1..R7, o resto J1..J11119."""
    ids: list[str] = []
    coords: dict[str, tuple[float, float]] = {}
    n_res = 0
    n_jun = 0
    for idx in range(N_NOS):
        if idx in _RESERVATORIO_IDX:
            n_res += 1
            nid = f"R{n_res}"
        else:
            n_jun += 1
            nid = f"J{n_jun}"
        linha, col = divmod(idx, _COLS)
        x = _X0 + col * _PASSO + rng.uniform(-_JITTER, _JITTER)
        y = _Y0 + linha * _PASSO + rng.uniform(-_JITTER, _JITTER)
        ids.append(nid)
        coords[nid] = (round(x, 2), round(y, 2))
    assert n_res == N_RESERVATORIOS and n_jun == N_JUNCOES
    return ids, coords


def _arestas_candidatas() -> list[tuple[int, int]]:
    """Vizinhança da malha (direita e baixo), em ordem determinística, já sem as 4 posições cortadas."""
    arestas = []
    for idx in range(N_NOS):
        linha, col = divmod(idx, _COLS)
        if col + 1 < _COLS and idx + 1 < N_NOS:
            arestas.append((idx, idx + 1))
        if linha + 1 < _ROWS and idx + _COLS < N_NOS:
            arestas.append((idx, idx + _COLS))
    return arestas


def _escolher_tubos(rng: random.Random) -> list[tuple[int, int]]:
    """Kruskal com a semente fixa: primeiro uma floresta geradora (grafo conexo), depois arestas extras até
    fechar N_TUBOS. Determinístico: o embaralhamento é o único sorteio."""
    candidatas = _arestas_candidatas()
    rng.shuffle(candidatas)
    pai = list(range(N_NOS))

    def raiz(a: int) -> int:
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a

    escolhidas: list[tuple[int, int]] = []
    for a, b in candidatas:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[ra] = rb
            escolhidas.append((a, b))
            if len(escolhidas) == N_NOS - 1:
                break
    assert len(escolhidas) == N_NOS - 1, "a malha cortada deixou de ser conexa (não deveria)"
    em_arvore = set(escolhidas)
    for par in candidatas:
        if len(escolhidas) == N_TUBOS:
            break
        if par not in em_arvore:
            escolhidas.append(par)
    assert len(escolhidas) == N_TUBOS
    return escolhidas


def gerar_doc() -> dict:
    """Monta a rede em memória (sem texto): devolve ids, coords, tubos [(id, no1, no2, comprimento)] e a soma
    de comprimentos — tudo já arredondado no formato que vai para o arquivo (2 casas)."""
    rng = random.Random(SEMENTE)
    ids, coords = _nos(rng)
    tubos = []
    for n, (a, b) in enumerate(_escolher_tubos(rng), start=1):
        xa, ya = coords[ids[a]]
        xb, yb = coords[ids[b]]
        comp = round(math.hypot(xb - xa, yb - ya), 2)
        tubos.append((f"P{n}", ids[a], ids[b], comp))
    return {"ids": ids, "coords": coords, "tubos": tubos,
            "soma_m": round(sum(t[3] for t in tubos), 2)}


def gerar_inp() -> str:
    """O texto `.inp` (seções JUNCTIONS, RESERVOIRS, PIPES, COORDINATES, OPTIONS)."""
    doc = gerar_doc()
    ids, coords, tubos = doc["ids"], doc["coords"], doc["tubos"]
    linhas = ["[TITLE]", "rede sintetica na escala do portao do item L4-05-d (gerar_epanet.py; NAO e dado "
              "de operadora)", ""]
    linhas.append("[JUNCTIONS]")
    n_jun = 0
    for nid in ids:
        if nid.startswith("J"):
            n_jun += 1
            elev = 900.0 + (n_jun * 7919) % 140  # espalhamento determinístico, sem sorteio
            linhas.append(f" {nid:<10} {elev:.2f} 0.0")
    linhas.append("")
    linhas.append("[RESERVOIRS]")
    n_res = 0
    for nid in ids:
        if nid.startswith("R"):
            n_res += 1
            linhas.append(f" {nid:<10} {1000.0 + (n_res * 37) % 60:.2f}")
    linhas.append("")
    linhas.append("[PIPES]")
    for pid, a, b, comp in tubos:
        linhas.append(f" {pid:<10} {a:<10} {b:<10} {comp:.2f} 100 130 0 Open")
    linhas.append("")
    linhas.append("[COORDINATES]")
    for nid in ids:
        x, y = coords[nid]
        linhas.append(f" {nid:<10} {x:.2f} {y:.2f}")
    linhas.append("")
    linhas += ["[OPTIONS]", " UNITS LPS", " HEADLOSS H-W", "", "[END]", ""]
    return "\n".join(linhas)


CONTAGENS_ESPERADAS = {"junctions": N_JUNCOES, "reservoirs": N_RESERVATORIOS, "tanks": 0,
                       "pipes": N_TUBOS, "pumps": 0, "valves": 0, "coordinates": N_NOS,
                       "vertices": 0, "patterns": 0, "curves": 0}
