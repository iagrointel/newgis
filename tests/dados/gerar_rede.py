"""Gerador de rede SINTÉTICA DETERMINÍSTICA (item L4-01-b-topologia-derivada). A rede REAL de teste (44.268
trechos de MT, 29.244 de BT, 26.581 ramais, 5.481 trafos, 60.549 postes) não está no repositório e não vai
estar (disco apertado, regra do laço) — este gerador produz uma rede FICTÍCIA nas MESMAS ORDENS DE GRANDEZA,
com semente fixa (determinística: a mesma semente sempre produz os mesmos pontos e a mesma contagem). Todo
número citado a partir daqui (contagem de nós, arestas, tempo de construção) é do GERADOR, não da BDGD.

Modelo: uma árvore de MÉDIA TENSÃO cresce por passos aleatórios (semente fixa) a partir de uma subestação;
em `N_TRAFOS` vértices da árvore de MT nasce um TRANSFORMADOR (2 terminais: alta=MT, baixa=BT — a cláusula do
tier faz a topologia religar cada lado no trecho certo, ver `app/rede_utilidades/topologia.py`), de onde cresce
uma sub-árvore de BAIXA TENSÃO; RAMAIS DE LIGAÇÃO saem de vértices de BT existentes até um consumidor (folha
nova). POSTES (`ponto_notavel/poste`, `sem_terminal`) são decorativos — não participam da topologia (prova
em si: 60 mil postes têm de dar ZERO nós) — por isso nascem em qualquer coordenada da caixa, sem precisar
coincidir com vértice nenhum.

Casos de fronteira DELIBERADOS (fora das contagens "de cabeça", somados a elas — nunca escondidos):
  - `N_TRAFOS_ORFAOS` transformadores extras, deslocados 1,0 m de qualquer vértice real (bem além da
    tolerância padrão de 0,05 m): os dois terminais nunca encontram um trecho — prova viva de "nó órfão".
  - `N_TRECHOS_DEGENERADOS` trechos extras com origem == destino (comprimento 0): prova viva de "aresta sem
    nó" (`_EPS_COMPRIMENTO_M` em `topologia.py` os exclui da candidatura de nó de propósito)."""

import math
import random

from app.rede_utilidades.topologia import _inserir_lote

SEMENTE = 20260906
LON0, LAT0 = -47.9292, -15.7801  # referência arbitrária (não é nenhuma subestação real)
_M_POR_GRAU_LAT = 110_540.0

N_TRECHOS_MT = 44_268
N_TRECHOS_BT = 29_244
N_RAMAIS = 26_581
N_TRAFOS = 5_481
N_POSTES = 60_549
N_TRAFOS_ORFAOS = 25
N_TRECHOS_DEGENERADOS = 10


def _m_por_grau_lon(lat0: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat0))


def _para_lonlat(dx: float, dy: float) -> tuple[float, float]:
    return LON0 + dx / _m_por_grau_lon(LAT0), LAT0 + dy / _M_POR_GRAU_LAT


class _Arvore:
    """Árvore de crescimento aleatório: cada passo escolhe um vértice existente (viés para os últimos —
    produz troncos compridos com ramificação lateral ocasional, mais parecido com um alimentador real do que
    um raio puro) e sai dele numa direção/distância aleatórias."""

    def __init__(self, rng: random.Random, origem_dx: float, origem_dy: float):
        self.rng = rng
        self.vertices: list[tuple[float, float]] = [(origem_dx, origem_dy)]
        self.arestas: list[tuple[int, int]] = []

    def crescer(self, n: int, dist_min=20.0, dist_max=80.0) -> None:
        for _ in range(n):
            if len(self.vertices) > 60 and self.rng.random() < 0.7:
                pai = self.rng.randrange(len(self.vertices) - 50, len(self.vertices))
            else:
                pai = self.rng.randrange(len(self.vertices))
            dx0, dy0 = self.vertices[pai]
            d = self.rng.uniform(dist_min, dist_max)
            ang = self.rng.uniform(0, 2 * math.pi)
            novo = (dx0 + d * math.cos(ang), dy0 + d * math.sin(ang))
            filho = len(self.vertices)
            self.vertices.append(novo)
            self.arestas.append((pai, filho))


def _tipos_da_rede(cur, rede_id: str) -> dict:
    cur.execute(
        "SELECT g.codigo AS grupo, tp.codigo AS tipo_codigo, tp.id FROM plat.rede_tipo tp "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id WHERE tp.rede_id = %s::uuid",
        (rede_id,),
    )
    return {(r["grupo"], r["tipo_codigo"]): r["id"] for r in cur.fetchall()}


def gerar(cur, tenant_id: int, rede_id: str, semente: int = SEMENTE, lote: int = 8000, *,
          n_mt: int = N_TRECHOS_MT, n_bt: int = N_TRECHOS_BT, n_ramais: int = N_RAMAIS,
          n_trafos: int = N_TRAFOS, n_postes: int = N_POSTES, n_trafos_orfaos: int = N_TRAFOS_ORFAOS,
          n_trechos_degenerados: int = N_TRECHOS_DEGENERADOS) -> dict:
    """Insere a rede sintética inteira (feições ponto+linha) na rede `rede_id` (já com o pacote `eletrica-br`
    importado). Devolve a contagem por grupo. Determinística: a mesma `semente` (+ os `n_*`) sempre gera os
    mesmos dados. Os `n_*` têm o tamanho real de teste como padrão; a suíte usa valores menores para os testes
    rápidos e o tamanho padrão só na medição de L4-01-b.json."""
    rng = random.Random(semente)
    tipos = _tipos_da_rede(cur, rede_id)
    t_mt = tipos[("trecho_de_media_tensao", 1)]
    t_bt = tipos[("trecho_de_baixa_tensao", 1)]
    t_ramal = tipos[("ramal_de_ligacao", 1)]
    t_trafo = tipos[("transformador_de_distribuicao", 1)]
    t_poste = tipos[("ponto_notavel", 1)]

    mt = _Arvore(rng, 0.0, 0.0)
    mt.crescer(n_mt)

    # sítios de transformador: amostra regular dos vértices de MT (nunca a raiz, índice 0)
    passo = max(1, (len(mt.vertices) - 1) // n_trafos)
    sitios = [1 + i * passo for i in range(n_trafos)]
    sitios = sitios[:n_trafos]
    while len(sitios) < n_trafos:  # rede pequena demais no teste: repete os últimos com jitter de índice
        sitios.append(sitios[-1])

    base_bt, resto_bt = divmod(n_bt, n_trafos)
    base_ram, resto_ram = divmod(n_ramais, n_trafos)

    linhas_mt = [(mt.vertices[a], mt.vertices[b], t_mt) for a, b in mt.arestas]
    linhas_bt = []
    linhas_ramal = []
    pontos_trafo = []

    for i, no_mt in enumerate(sitios):
        origem_dx, origem_dy = mt.vertices[no_mt]
        pontos_trafo.append((origem_dx, origem_dy))
        bt = _Arvore(rng, origem_dx, origem_dy)
        n_bt_i = base_bt + (1 if i < resto_bt else 0)
        bt.crescer(max(n_bt_i, 1), dist_min=5.0, dist_max=25.0)
        # se o orçamento deste trafo é 0 (rede de teste pequena), a sub-árvore fica só com a raiz — sem trecho.
        usados = bt.arestas[:n_bt_i] if n_bt_i else []
        for a, b in usados:
            linhas_bt.append((bt.vertices[a], bt.vertices[b], t_bt))
        n_ram_i = base_ram + (1 if i < resto_ram else 0)
        for _ in range(n_ram_i):
            v = bt.vertices[rng.randrange(len(bt.vertices))]
            d = rng.uniform(3.0, 15.0)
            ang = rng.uniform(0, 2 * math.pi)
            folha = (v[0] + d * math.cos(ang), v[1] + d * math.sin(ang))
            linhas_ramal.append((v, folha, t_ramal))

    # postes: decorativos, em qualquer lugar da caixa (sem_terminal — 0 nós de topologia, propositalmente)
    largura = max(1.0, max(abs(x) for x, _ in mt.vertices) if mt.vertices else 1.0) + 200.0
    pontos_poste = [
        (rng.uniform(-largura, largura), rng.uniform(-largura, largura)) for _ in range(n_postes)
    ]

    # casos de fronteira: transformador órfão (1,0 m de qualquer vértice real) e trecho degenerado (comprimento 0)
    pontos_trafo_orfaos = [
        (mt.vertices[rng.randrange(len(mt.vertices))][0] + 1.0, mt.vertices[rng.randrange(len(mt.vertices))][1] + 1.0)
        for _ in range(n_trafos_orfaos)
    ]
    linhas_degeneradas = [
        (mt.vertices[rng.randrange(len(mt.vertices))],) * 2 + (t_mt,) for _ in range(n_trechos_degenerados)
    ]

    def inserir_pontos(pontos_xy, tipo_id):
        linhas = []
        for dx, dy in pontos_xy:
            lon, lat = _para_lonlat(dx, dy)
            linhas.append((tenant_id, rede_id, tipo_id, lon, lat))
        for i in range(0, len(linhas), lote):
            _inserir_lote(
                cur,
                "INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom) VALUES ",
                linhas[i:i + lote],
                "(%s,%s::uuid,%s, ST_SetSRID(ST_MakePoint(%s,%s), 4326))",
            )

    def inserir_linhas(trechos):
        linhas = []
        for p0, p1, tipo_id in trechos:
            lon0, lat0 = _para_lonlat(*p0)
            lon1, lat1 = _para_lonlat(*p1)
            wkt = f"LINESTRING({lon0} {lat0}, {lon1} {lat1})"
            linhas.append((tenant_id, rede_id, tipo_id, wkt))
        for i in range(0, len(linhas), lote):
            _inserir_lote(
                cur,
                "INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom) VALUES ",
                linhas[i:i + lote],
                "(%s,%s::uuid,%s, ST_SetSRID(ST_GeomFromText(%s), 4326))",
            )

    inserir_pontos(pontos_trafo, t_trafo)
    inserir_pontos(pontos_trafo_orfaos, t_trafo)
    inserir_pontos(pontos_poste, t_poste)
    inserir_linhas(linhas_mt)
    inserir_linhas(linhas_bt)
    inserir_linhas(linhas_ramal)
    inserir_linhas(linhas_degeneradas)

    return {
        "trechos_mt": len(linhas_mt), "trechos_bt": len(linhas_bt), "ramais": len(linhas_ramal),
        "trafos": len(pontos_trafo), "trafos_orfaos": len(pontos_trafo_orfaos), "postes": len(pontos_poste),
        "trechos_degenerados": len(linhas_degeneradas),
    }
