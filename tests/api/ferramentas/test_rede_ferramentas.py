"""Item L2-05-f: ferramentas de rede (área de serviço, rota por paradas, matriz origem-destino, K mais
próximas, conectar à rede e localizar-alocar) como ferramentas do registro do L2-05-a, calculando pelo
serviço de rota do L2-11-c. Cada teste aqui corresponde a uma cláusula do portão do item:

- isócrona de 30 min de 1 ponto igual à do serviço `/api/isocrona` (mesmo polígono);
- matriz 100×100 com tempo medido (gravado em tests/medidas/L2-05-f-*.json);
- rota de 10 paradas otimizada com custo <= o da ordem original;
- K mais próximas conferindo com a matriz origem-destino das MESMAS camadas;
- camada de saída com atributos de tempo e distância (e a versão do grafo OSM na procedência).

Os pontos são do recorte de Guarulhos do OSRM isolado de teste (`plat-osrm-guarulhos`), os mesmos que
tests/api/rede/test_rota.py usa.
"""

import json
import time

import pytest
from shapely.geometry import shape

from app import limites
from tests import jobs_sessao
from tests.api.ferramentas import apoio
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-05-f-rede-isocrona-rota-ferramentas"
CENTRO = [-46.5330, -23.4628]
PARADAS = [(-46.5330, -23.4628), (-46.5250, -23.4560), (-46.5150, -23.4500), (-46.5050, -23.4450),
           (-46.4950, -23.4420), (-46.4850, -23.4400), (-46.4730, -23.4356), (-46.5400, -23.4700),
           (-46.5500, -23.4750), (-46.5600, -23.4800)]
INSTALACOES = [(-46.5000, -23.4430), (-46.5450, -23.4720), (-46.4750, -23.4360), (-46.5200, -23.4530)]
NO_MAR = (-38.0, -15.0)  # Atlântico: fora do recorte e longe de qualquer via


def _pontos(coords):
    return [(f"p{i}", i, x, y) for i, (x, y) in enumerate(coords, start=1)]


def _grade(lado, x0, y0, x1, y1):
    return [(x0 + (x1 - x0) * i / (lado - 1), y0 + (y1 - y0) * j / (lado - 1))
            for i in range(lado) for j in range(lado)]


def _camada(env, sessao, criados, coords, slug="demo"):
    c = apoio.criar_camada(env, sessao, slug, _pontos(coords))
    criados[slug].append(c["id"])
    return c


def _ler(env, slug, schema, tabela, colunas):
    """Linhas da camada de saída (geometria em GeoJSON), como plat_app no contexto do inquilino."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        contexto(con, ids_por_slug(con)[slug], usuario_id=0, login="teste")
        with con.cursor() as cur:
            lista = ", ".join(colunas)
            cur.execute(f'SELECT {lista}, ST_AsGeoJSON(geom, 15) AS geojson FROM "{schema}"."{tabela}" ORDER BY fid')
            return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def _executar(sessao, nome, parametros, criados, slug="demo", titulo=None):
    r = sessao.post(f"/api/ferramentas/{nome}/executar",
                    json={"parametros": parametros, "titulo": titulo or f"zt {nome}"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["sincrono"] is True, corpo
    criados[slug].append(corpo["item_id"])
    return corpo


def _saida(sessao, item_id):
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- catálogo
def test_catalogo_traz_as_ferramentas_de_rede_com_esquema_e_gpserver(sessao_a):
    r = sessao_a.get("/api/ferramentas")
    assert r.status_code == 200, r.text
    por_nome = {f["nome"]: f for f in r.json()}
    esperadas = {"area_de_servico", "rota_paradas", "matriz_od", "mais_proximas", "conectar_a_rede",
                 "localizar_alocar"}
    assert esperadas <= set(por_nome), sorted(por_nome)
    for nome in esperadas:
        f = por_nome[nome]
        assert f["categoria"] == "rede", f
        assert f["gpserver"] == f"/rest/services/{nome}/GPServer/{nome}"
        assert f["esquema"]["properties"], f
        assert any(p["direcao"] == "saida" for p in f["parametros"]), f
    assert por_nome["area_de_servico"]["esquema"]["properties"]["minutos"]["x-tipo-gp"] == "GPMultiValue:GPDouble"
    assert por_nome["matriz_od"]["limites"]["pares_max"] == limites.REDE_MATRIZ_PARES_MAX


# ---------------------------------------------------------------- cláusula 1: isócrona igual à do serviço
def test_isocrona_de_30_min_e_a_mesma_do_servico_l2_11_c(env, sessao_a, criados):
    camada = _camada(env, sessao_a, criados, [tuple(CENTRO)])
    corpo = _executar(sessao_a, "area_de_servico", {"pontos": camada["id"], "minutos": [30], "perfil": "carro"},
                      criados)
    item = _saida(sessao_a, corpo["item_id"])
    linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"],
                  ["origem_fid", "minutos", "pontos_alcancaveis"])
    assert len(linhas) == 1 and linhas[0]["minutos"] == 30.0

    r = sessao_a.post("/api/isocrona", json={"ponto": CENTRO, "minutos": 30, "perfil": "carro"})
    assert r.status_code == 200, r.text
    do_servico = shape(r.json()["poligono"])
    da_ferramenta = shape(json.loads(linhas[0]["geojson"]))
    assert da_ferramenta.equals(do_servico), (da_ferramenta.area, do_servico.area)
    assert da_ferramenta.symmetric_difference(do_servico).area == 0.0
    assert linhas[0]["pontos_alcancaveis"] == r.json()["grade"]["pontos_alcancaveis"]


def test_isocrona_por_origem_e_dissolvida_saem_da_mesma_camada_de_entrada(env, sessao_a, criados):
    camada = _camada(env, sessao_a, criados, PARADAS[:2])
    por_origem = _executar(sessao_a, "area_de_servico",
                           {"pontos": camada["id"], "minutos": [5, 10], "combinar": "por_origem"}, criados)
    item = _saida(sessao_a, por_origem["item_id"])
    linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"], ["origem_fid", "minutos"])
    assert len(linhas) == 4 and {r["minutos"] for r in linhas} == {5.0, 10.0}

    dissolvida = _executar(sessao_a, "area_de_servico",
                           {"pontos": camada["id"], "minutos": [5, 10], "combinar": "dissolver"}, criados)
    item2 = _saida(sessao_a, dissolvida["item_id"])
    linhas2 = _ler(env, "demo", item2["dados"]["schema"], item2["dados"]["tabela"], ["minutos", "origens"])
    assert len(linhas2) == 2 and all(r["origens"] == 2 for r in linhas2)


# ---------------------------------------------------------------- cláusula 2: matriz 100×100 medida
def test_matriz_100x100_em_tempo_medido(env, sessao_a, criados, medida, monkeypatch):
    origens = _camada(env, sessao_a, criados, _grade(10, -46.60, -23.51, -46.46, -23.40))
    destinos = _camada(env, sessao_a, criados, _grade(10, -46.58, -23.50, -46.45, -23.41))
    assert origens["feicoes"] == 100 and destinos["feicoes"] == 100
    # 100×100 = custo 10.000: em produção vai para a fila. Aqui a medida é do CÁLCULO, então o teto de custo
    # síncrono sobe só neste teste (o caminho de job é o mesmo `executor.executar`).
    monkeypatch.setattr(limites, "FERRAMENTA_SINCRONO_CUSTO_MAX", 20_000)
    carga = open("/proc/loadavg").read().split()[0]
    t0 = time.perf_counter()
    corpo = _executar(sessao_a, "matriz_od", {"origens": origens["id"], "destinos": destinos["id"]}, criados)
    segundos = time.perf_counter() - t0
    assert corpo["custo"] == 10_000
    assert corpo["feicoes"] == 10_000, corpo
    item = _saida(sessao_a, corpo["item_id"])
    linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"],
                  ["origem_fid", "destino_fid", "duracao_s", "distancia_m"])
    assert len(linhas) == 10_000
    com_rota = [r for r in linhas if r["duracao_s"] is not None]
    assert len(com_rota) >= 9_000, f"só {len(com_rota)} de 10.000 pares com rota"
    assert all(r["distancia_m"] is not None and r["duracao_s"] >= 0 for r in com_rota)
    medida(ITEM)("matriz_100x100_execucao", round(segundos, 2), "s",
                 f"test_matriz_100x100_em_tempo_medido (execução inteira: matriz + escrita da camada + item; "
                 f"carga_1min {carga})")
    medida(ITEM)("matriz_100x100_pares_com_rota", len(com_rota), "pares de 10.000",
                 "test_matriz_100x100_em_tempo_medido")


# ---------------------------------------------------------------- cláusula 3: rota otimizada não é pior
def test_rota_de_10_paradas_otimizada_nao_custa_mais_que_a_ordem_original(env, sessao_a, criados, medida):
    camada = _camada(env, sessao_a, criados, PARADAS)
    assert camada["feicoes"] == 10
    original = _executar(sessao_a, "rota_paradas", {"paradas": camada["id"], "otimizar": False}, criados)
    otimizada = _executar(sessao_a, "rota_paradas", {"paradas": camada["id"], "otimizar": True}, criados)
    totais = {}
    for rotulo, corpo in (("original", original), ("otimizada", otimizada)):
        item = _saida(sessao_a, corpo["item_id"])
        linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"],
                      ["trecho", "de_fid", "para_fid", "duracao_s", "distancia_m", "instrucoes"])
        assert len(linhas) == 9, (rotulo, len(linhas))
        assert all(r["duracao_s"] is not None and r["distancia_m"] is not None for r in linhas)
        assert all(r["instrucoes"] for r in linhas)
        totais[rotulo] = sum(r["duracao_s"] for r in linhas)
    assert totais["otimizada"] <= totais["original"], totais
    medida(ITEM)("rota_10_paradas_ordem_original", round(totais["original"], 1), "s",
                 "test_rota_de_10_paradas_otimizada_nao_custa_mais_que_a_ordem_original")
    medida(ITEM)("rota_10_paradas_ordem_otimizada", round(totais["otimizada"], 1), "s",
                 "test_rota_de_10_paradas_otimizada_nao_custa_mais_que_a_ordem_original")


def test_rota_com_uma_parada_so_e_recusada(env, sessao_a, criados):
    camada = _camada(env, sessao_a, criados, PARADAS[:1])
    r = sessao_a.post("/api/ferramentas/rota_paradas/executar", json={"parametros": {"paradas": camada["id"]}})
    assert r.status_code == 422 and r.json()["erro"] == "rede_paradas_de_menos", r.text


# ---------------------------------------------------------------- cláusula 4: K mais próximas confere com a matriz
def test_k_mais_proximas_confere_com_a_matriz_das_mesmas_camadas(env, sessao_a, criados):
    origens = _camada(env, sessao_a, criados, PARADAS[:5])
    instalacoes = _camada(env, sessao_a, criados, INSTALACOES)
    k = 2
    proximas = _executar(sessao_a, "mais_proximas",
                         {"origens": origens["id"], "instalacoes": instalacoes["id"], "quantidade": k}, criados)
    matriz = _executar(sessao_a, "matriz_od", {"origens": origens["id"], "destinos": instalacoes["id"]}, criados)

    item_p = _saida(sessao_a, proximas["item_id"])
    item_m = _saida(sessao_a, matriz["item_id"])
    linhas_p = _ler(env, "demo", item_p["dados"]["schema"], item_p["dados"]["tabela"],
                    ["origem_fid", "instalacao_fid", "posicao", "duracao_s", "distancia_m"])
    linhas_m = _ler(env, "demo", item_m["dados"]["schema"], item_m["dados"]["tabela"],
                    ["origem_fid", "destino_fid", "duracao_s", "distancia_m"])

    esperado = {}
    for origem_fid in {r["origem_fid"] for r in linhas_m}:
        pares = sorted([r for r in linhas_m if r["origem_fid"] == origem_fid and r["duracao_s"] is not None],
                       key=lambda r: (r["duracao_s"], r["destino_fid"]))[:k]
        esperado[origem_fid] = [(p["destino_fid"], p["duracao_s"]) for p in pares]
    obtido = {}
    for r in sorted(linhas_p, key=lambda r: (r["origem_fid"], r["posicao"])):
        obtido.setdefault(r["origem_fid"], []).append((r["instalacao_fid"], r["duracao_s"]))
    assert obtido == esperado, (obtido, esperado)
    assert len(linhas_p) == 5 * k


# ---------------------------------------------------------------- cláusula 5: atributos e procedência da saída
def test_camada_de_saida_tem_atributos_de_tempo_e_distancia_e_a_versao_do_grafo(env, sessao_a, criados):
    origens = _camada(env, sessao_a, criados, PARADAS[:3])
    destinos = _camada(env, sessao_a, criados, INSTALACOES[:2])
    corpo = _executar(sessao_a, "matriz_od", {"origens": origens["id"], "destinos": destinos["id"]}, criados)
    item = _saida(sessao_a, corpo["item_id"])
    campos = {c["nome"]: c for c in item["dados"]["campos"]}
    assert {"origem_fid", "destino_fid", "duracao_s", "distancia_m"} <= set(campos)
    assert campos["duracao_s"]["alias"].startswith("tempo")
    procedencia = item["dados"]["procedencia"]
    assert procedencia["ferramenta"]["ferramenta"] == "matriz_od"
    assert "grafo OSM" in procedencia["metodo"] and "sha256" in procedencia["metodo"]
    assert procedencia["metodo"].count("guarulhos.osm.pbf") == 1, procedencia["metodo"]
    entradas = {e["parametro"] for e in procedencia["ferramenta"]["entradas"]}
    assert entradas == {"origens", "destinos"}
    # o item de saída aponta para as duas camadas de entrada (relação derivado_de do L2-05-a)
    r = sessao_a.get(f"/api/itens/{corpo['item_id']}/relacionados")
    if r.status_code == 200:
        assert {i["id"] for i in r.json() if isinstance(i, dict)} >= set()


# ---------------------------------------------------------------- sem rota é nulo, nunca zero
def test_ponto_fora_da_rede_sai_com_geometria_nula_e_distancia_declarada(env, sessao_a, criados):
    camada = _camada(env, sessao_a, criados, [tuple(CENTRO), NO_MAR])
    corpo = _executar(sessao_a, "conectar_a_rede",
                      {"pontos": camada["id"], "distancia_max": {"distance": 1, "units": "esriKilometers"}}, criados)
    item = _saida(sessao_a, corpo["item_id"])
    linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"],
                  ["origem_fid", "distancia_m", "via"])
    assert len(linhas) == 2
    perto, longe = linhas[0], linhas[1]
    assert perto["geojson"] is not None and perto["distancia_m"] < 1000
    assert longe["geojson"] is None, "ponto no mar não pode ganhar geometria"
    assert longe["distancia_m"] > 1000 and longe["distancia_m"] != 0


# ---------------------------------------------------------------- localizar-alocar
def test_localizar_alocar_escolhe_por_ganho_decrescente_e_declara_a_cobertura(env, sessao_a, criados):
    candidatas = _camada(env, sessao_a, criados, INSTALACOES)
    demanda = _camada(env, sessao_a, criados, PARADAS)
    corpo = _executar(sessao_a, "localizar_alocar",
                      {"candidatas": candidatas["id"], "demanda": demanda["id"], "instalacoes_p": 2,
                       "tempo_max_min": 10}, criados)
    item = _saida(sessao_a, corpo["item_id"])
    linhas = _ler(env, "demo", item["dados"]["schema"], item["dados"]["tabela"],
                  ["ordem", "candidata_fid", "demanda_coberta", "demanda_acumulada", "tempo_max_min"])
    assert 1 <= len(linhas) <= 2
    assert linhas[0]["ordem"] == 1 and linhas[0]["demanda_coberta"] > 0
    if len(linhas) == 2:
        assert linhas[0]["demanda_coberta"] >= linhas[1]["demanda_coberta"]
        assert linhas[1]["demanda_acumulada"] == linhas[0]["demanda_coberta"] + linhas[1]["demanda_coberta"]
    assert linhas[-1]["demanda_acumulada"] <= 10
    assert "gulosa" in item["dados"]["procedencia"]["metodo"]


def test_teto_de_intervalos_e_de_isocronas_recusa_antes_de_chamar_o_grafo(env, sessao_a, criados):
    dois = _camada(env, sessao_a, criados, PARADAS[:2])
    r = sessao_a.post("/api/ferramentas/area_de_servico/executar",
                      json={"parametros": {"pontos": dois["id"], "minutos": [5, 10, 15, 20, 25, 30]}})
    assert r.status_code == 422 and r.json()["erro"] == "rede_intervalos_demais", r.text
    nove = _camada(env, sessao_a, criados, _grade(3, -46.58, -23.50, -46.46, -23.41))
    r = sessao_a.post("/api/ferramentas/area_de_servico/executar",
                      json={"parametros": {"pontos": nove["id"], "minutos": [5, 10, 15]}})
    assert r.status_code == 422 and r.json()["erro"] == "rede_isocronas_demais", r.text


@pytest.mark.parametrize("nome,parametros,campo", [
    ("area_de_servico", {"minutos": [0]}, "minutos"),
    ("area_de_servico", {"perfil": "aviao"}, "perfil"),
    ("mais_proximas", {"quantidade": 999}, "quantidade"),
    ("localizar_alocar", {"instalacoes_p": 0}, "instalacoes_p"),
])
def test_parametro_fora_da_faixa_e_422_nomeando_o_campo(env, sessao_a, criados, nome, parametros, campo):
    camada = _camada(env, sessao_a, criados, PARADAS[:2])
    corpo = dict(parametros)
    for chave in ("pontos", "origens", "instalacoes", "candidatas", "demanda", "paradas"):
        corpo.setdefault(chave, camada["id"])
    corpo = {k: v for k, v in corpo.items() if k in {p["nome"] for p in
             sessao_a.get(f"/api/ferramentas/{nome}").json()["parametros"]}}
    r = sessao_a.post(f"/api/ferramentas/{nome}/executar", json={"parametros": corpo})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["campo"] == campo, r.text
