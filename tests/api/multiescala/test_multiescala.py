"""Motor de grades aninhadas, macro -> micro (item L3-19-multiescala).

Portão, cláusula por cláusula:
  a) "fluxo macro -> micro em 2 execuções ligadas" -> test_fluxo_macro_para_micro_em_duas_execucoes_ligadas
  b) "célula micro fora das regiões macro não é calculada" -> mesmo teste, conferindo celulas < celulas_possiveis
     e celulas == aprovadas_macro * k^2 (aritmético, não filtrado depois de gerar tudo)
  c) "relatório declara a escala de cada fator" -> test_relatorio_declara_escala_grosseira_do_fator (é também
     a refutação exigida do item: fator declarado a 1 km usado numa grade de 100 m sai marcado 'grosseira'
     sem o cliente precisar dizer isso).

Área de estudo: um retângulo de ~1,47 km x 1,35 km perto de São Paulo, construído para dar EXATAMENTE 2x2 = 4
células na grade macro de 1 km (a extensão passa de 1.000 m e não chega a 2.000 m em nenhum eixo)."""

import math
import secrets

import pytest

CENTRO = (-46.60, -23.50)
# 1.900 m x 1.900 m no ponto acima -> grade macro de 1 km dá exatamente 2x2 = 4 células (ceil(1900/1000)=2)
# E o CENTRO de toda célula (inclusive a segunda linha/coluna, a 1.500 m da origem) cai DENTRO da área real
# (achado rodando de verdade: com ~1.35-1.47 km a segunda linha vira uma fatia fina cujo centro nominal de
# célula fica FORA da área de dado, e a amostra nunca alcança o bloco que aquela célula vai procurar).
ALVO_LARGURA_M = 1900.0
ALVO_ALTURA_M = 1900.0
_M_POR_GRAU_LAT = 111_320.0
_M_POR_GRAU_LON = 111_320.0 * math.cos(math.radians(CENTRO[1]))
MEIA_LARGURA_GRAUS = (ALVO_LARGURA_M / 2) / _M_POR_GRAU_LON
MEIA_ALTURA_GRAUS = (ALVO_ALTURA_M / 2) / _M_POR_GRAU_LAT


def _retangulo_estudo() -> dict:
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LARGURA_GRAUS, lon + MEIA_LARGURA_GRAUS
    y0, y1 = lat - MEIA_ALTURA_GRAUS, lat + MEIA_ALTURA_GRAUS
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _amostras_cobrindo_o_retangulo(valor: float, n_por_lado: int = 6) -> list[dict]:
    """Grade fina de pontos cobrindo o retângulo inteiro, valor constante — o suficiente para toda célula
    macro/micro ter pelo menos uma amostra no bloco (favorabilidade 50,0 quando min=max, decisão A da
    migração); a variação de nota não é o que este item mede, é a mecânica de escala e aninhamento."""
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LARGURA_GRAUS * 0.90, lon + MEIA_LARGURA_GRAUS * 0.90
    y0, y1 = lat - MEIA_ALTURA_GRAUS * 0.90, lat + MEIA_ALTURA_GRAUS * 0.90
    pontos = []
    for i in range(n_por_lado):
        for j in range(n_por_lado):
            px = x0 + (x1 - x0) * i / (n_por_lado - 1)
            py = y0 + (y1 - y0) * j / (n_por_lado - 1)
            pontos.append({"lon": px, "lat": py, "valor": valor})
    return pontos


@pytest.fixture
def conjunto(sessao_a):
    r = sessao_a.post("/api/multiescala/conjuntos",
                      json={"nome": f"zt-estudo-{secrets.token_hex(4)}", "area": _retangulo_estudo()})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def fator_fino(sessao_a):
    r = sessao_a.post("/api/multiescala/fatores", json={
        "nome": f"zt-fator-fino-{secrets.token_hex(4)}", "resolucao_fonte_m": 50.0, "papel": "atrai",
        "unidade": "un", "fonte": "amostra sintética de teste",
    })
    assert r.status_code == 201, r.text
    fator = r.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras",
                       json={"amostras": _amostras_cobrindo_o_retangulo(10.0)})
    assert ra.status_code == 201, ra.text
    return fator


@pytest.fixture
def fator_grosso_1km(sessao_a):
    """Escala nativa DECLARADA de 1.000 m (1 km) — mesma ordem de grandeza da hipótese do item."""
    r = sessao_a.post("/api/multiescala/fatores", json={
        "nome": f"zt-fator-grosso-{secrets.token_hex(4)}", "resolucao_fonte_m": 1000.0, "papel": "atrai",
        "unidade": "un", "fonte": "amostra sintética de teste, escala quilométrica",
    })
    assert r.status_code == 201, r.text
    fator = r.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras",
                       json={"amostras": _amostras_cobrindo_o_retangulo(20.0)})
    assert ra.status_code == 201, ra.text
    return fator


# ---------------------------------------------------------------- a) + b) fluxo e recorte aritmético
def test_fluxo_macro_para_micro_em_duas_execucoes_ligadas(sessao_a, conjunto, fator_fino, fator_grosso_1km, medida):
    fatores = [{"fator_id": fator_fino["id"], "peso": 1.0}, {"fator_id": fator_grosso_1km["id"], "peso": 1.0}]

    r_macro = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r_macro.status_code == 201, r_macro.text
    macro = r_macro.json()
    assert macro["nivel"] == "macro"
    assert macro["execucao_pai_id"] is None
    assert macro["grade"]["colunas"] == 2 and macro["grade"]["linhas"] == 2
    assert macro["celulas"] == 4, macro          # o retângulo foi desenhado para caber em exatamente 2x2
    assert macro["celulas_com_nota"] == 4, "as duas fontes cobrem o retângulo inteiro; nenhuma célula sem nota"
    assert macro["celulas_aprovadas"] == 2, "top_pct 50% de 4 células = 2"

    r_micro = sessao_a.post(f"/api/multiescala/execucoes/{macro['id']}/micro", json={
        "resolucao_m": 100.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r_micro.status_code == 201, r_micro.text
    micro = r_micro.json()
    assert micro["nivel"] == "micro"
    assert micro["execucao_pai_id"] == macro["id"]
    assert micro["grade"]["fator_aninhamento"] == 10, "k = 1.000 m / 100 m"

    # cláusula central do portão: célula micro fora das regiões macro aprovadas NUNCA é gerada — não é um
    # filtro aplicado depois, é aritmético (só as aprovadas entram no produto cartesiano de sub-células)
    k = micro["grade"]["fator_aninhamento"]
    assert micro["celulas"] == macro["celulas_aprovadas"] * k * k, micro
    assert micro["grade"]["celulas_possiveis"] == macro["celulas"] * k * k, micro
    assert micro["celulas"] < micro["grade"]["celulas_possiveis"], (
        "com só metade do macro aprovado, o micro tem de cobrir menos do que o total possível"
    )
    economia_pct = 100.0 * (1.0 - micro["celulas"] / micro["grade"]["celulas_possiveis"])
    assert economia_pct == pytest.approx(50.0), "2 de 4 macro aprovadas -> metade das micro possíveis"

    # a execução volta a aparecer pela leitura (GET), não só na resposta do POST
    r_ver = sessao_a.get(f"/api/multiescala/execucoes/{micro['id']}")
    assert r_ver.status_code == 200, r_ver.text
    assert r_ver.json()["celulas"] == micro["celulas"]

    r_lista = sessao_a.get(f"/api/multiescala/execucoes?conjunto_id={conjunto['id']}")
    assert r_lista.status_code == 200
    ids_na_lista = {e["id"] for e in r_lista.json()["itens"]}
    assert {macro["id"], micro["id"]} <= ids_na_lista

    gravar = medida("L3-19-multiescala")
    gravar("macro_celulas", macro["celulas"], "células",
           "POST /api/multiescala/conjuntos/{id}/macro, resolucao_m=1000 sobre estudo de 1.900x1.900 m")
    gravar("macro_celulas_aprovadas", macro["celulas_aprovadas"], "células", "aprovacao_tipo=top_pct, valor=50")
    gravar("micro_fator_aninhamento", k, "×", "k = resolucao macro / resolucao micro = 1.000 m / 100 m")
    gravar("micro_celulas_geradas", micro["celulas"], "células",
           "POST /api/multiescala/execucoes/{id}/micro, resolucao_m=100 (só dentro das macro aprovadas)")
    gravar("micro_celulas_possiveis", micro["grade"]["celulas_possiveis"], "células",
           "macro.celulas × k² — se TODA macro tivesse sido aprovada")
    gravar("micro_economia_pct", round(economia_pct, 1), "%",
           "100 × (1 − celulas_geradas / celulas_possiveis): custo evitado por não calcular fora do aprovado")


def test_micro_sem_macro_aprovada_e_recusado(sessao_a, conjunto, fator_fino):
    """Sem execução macro (ou sem nenhuma região aprovada) não há onde refinar — 422, nunca uma grade vazia."""
    fatores = [{"fator_id": fator_fino["id"], "peso": 1.0}]
    r_macro = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": fatores, "aprovacao_tipo": "limiar", "aprovacao_valor": 100.0,
    })
    assert r_macro.status_code == 201, r_macro.text
    macro = r_macro.json()
    # amostra de valor constante -> favorabilidade 50,0 em toda célula (min=max); limiar 100 não aprova nenhuma
    assert macro["celulas_aprovadas"] == 0, macro

    r_micro = sessao_a.post(f"/api/multiescala/execucoes/{macro['id']}/micro", json={
        "resolucao_m": 100.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r_micro.status_code == 422, r_micro.text
    assert r_micro.json()["erro"] == "macro_sem_regiao_aprovada"


def test_micro_ligado_a_micro_e_recusado(sessao_a, conjunto, fator_fino):
    """`execucao_pai_id` só pode ser uma execução macro — encadear micro em micro não é o portão do item."""
    fatores = [{"fator_id": fator_fino["id"], "peso": 1.0}]
    macro = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 100.0,
    }).json()
    micro = sessao_a.post(f"/api/multiescala/execucoes/{macro['id']}/micro", json={
        "resolucao_m": 100.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 100.0,
    }).json()
    r = sessao_a.post(f"/api/multiescala/execucoes/{micro['id']}/micro", json={
        "resolucao_m": 10.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 100.0,
    })
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "nivel_invalido"


# ---------------------------------------------------------------- c) relatório de escala + refutação
def test_relatorio_declara_escala_grosseira_do_fator(sessao_a, conjunto, fator_fino, fator_grosso_1km, medida):
    """Refutação do item: o fator de 1 km (declarado, `fator_grosso_1km`) usado sem qualquer flag especial
    do cliente tem de sair marcado 'grosseira' quando a grade é mais fina que 1 km — e 'própria' quando a
    grade é igual ou mais grossa que a escala nativa dele. O motor decide isso sozinho pela comparação de
    `resolucao_fonte_m` x `resolucao_grade_m`; o cliente nunca envia `escala_grosseira`."""
    fatores = [{"fator_id": fator_fino["id"], "peso": 2.0}, {"fator_id": fator_grosso_1km["id"], "peso": 1.0}]

    macro = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 100.0,
    }).json()
    por_fator_macro = {f["fator_id"]: f for f in macro["fatores"]}
    # na grade de 1 km, o fator de 1 km bate a própria escala (1000 > 1000 é falso) -> própria, não grosseira
    assert por_fator_macro[fator_grosso_1km["id"]]["escala"] == "propria"
    assert por_fator_macro[fator_grosso_1km["id"]]["escala_grosseira"] is False
    assert por_fator_macro[fator_grosso_1km["id"]]["resolucao_fonte_m"] == 1000.0
    assert por_fator_macro[fator_grosso_1km["id"]]["resolucao_grade_m"] == 1000.0
    assert por_fator_macro[fator_grosso_1km["id"]]["peso"] == 1.0
    # o fator fino (50 m) numa grade de 1 km também é 'própria': fonte mais fina que a grade nunca é grosseira
    assert por_fator_macro[fator_fino["id"]]["escala"] == "propria"
    assert por_fator_macro[fator_fino["id"]]["escala_grosseira"] is False

    micro = sessao_a.post(f"/api/multiescala/execucoes/{macro['id']}/micro", json={
        "resolucao_m": 100.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 100.0,
    }).json()
    por_fator_micro = {f["fator_id"]: f for f in micro["fatores"]}
    # MESMO fator, MESMA chamada (o cliente não mudou nada) — na grade de 100 m ele vira grosseiro sozinho
    alvo = por_fator_micro[fator_grosso_1km["id"]]
    assert alvo["escala"] == "grosseira", alvo
    assert alvo["escala_grosseira"] is True, alvo
    assert alvo["resolucao_fonte_m"] == 1000.0
    assert alvo["resolucao_grade_m"] == 100.0
    assert alvo["razao_escala"] == pytest.approx(10.0)
    # o fator de 50 m continua 'própria' na grade de 100 m (fonte ainda mais fina que a grade)
    assert por_fator_micro[fator_fino["id"]]["escala"] == "propria"
    assert por_fator_micro[fator_fino["id"]]["escala_grosseira"] is False

    # o relatório é o que volta também por GET, não um artefato só da resposta do POST
    r = sessao_a.get(f"/api/multiescala/execucoes/{micro['id']}")
    assert r.status_code == 200
    assert {f["fator_id"]: f["escala_grosseira"] for f in r.json()["fatores"]}[fator_grosso_1km["id"]] is True

    gravar = medida("L3-19-multiescala")
    gravar("fator_1km_escala_na_grade_1km", por_fator_macro[fator_grosso_1km["id"]]["escala"], "rótulo",
           "GET/POST /api/multiescala/.../macro: fator de 1.000 m numa grade de 1.000 m")
    gravar("fator_1km_escala_na_grade_100m", alvo["escala"], "rótulo",
           "mesma chamada, execução micro (resolucao_m=100) ligada à mesma macro — refutação do item")


# ---------------------------------------------------------------- CRS e limites
def test_crs_de_trabalho_e_utm_sirgas_da_zona_do_centroide(sessao_a, conjunto):
    assert conjunto["srid_trabalho"] == 31983, conjunto        # zona 23S cobre -46,60/-23,50
    assert "23S" in conjunto["srid_nome"], conjunto
    assert conjunto["largura_m"] == pytest.approx(ALVO_LARGURA_M, rel=0.05)
    assert conjunto["altura_m"] == pytest.approx(ALVO_ALTURA_M, rel=0.05)


def test_fora_da_cobertura_sirgas_e_422(sessao_a):
    # longitude bem a leste do Brasil, fora das zonas 11N-22N/17S-25S do SIRGAS 2000 UTM
    area = {"type": "Polygon", "coordinates": [[[10.0, 5.0], [10.01, 5.0], [10.01, 5.01], [10.0, 5.01], [10.0, 5.0]]]}
    r = sessao_a.post("/api/multiescala/conjuntos", json={"nome": "zt-fora-de-cobertura", "area": area})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "fora_da_cobertura_sirgas"


def test_grade_grande_demais_e_422(sessao_a, conjunto, fator_fino):
    r = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1.0, "fatores": [{"fator_id": fator_fino["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "grade_grande_demais"


def test_nao_cria_conjunto_com_mais_de_um_polo_igual_nome(sessao_a):
    nome = f"zt-duplicado-{secrets.token_hex(4)}"
    area = _retangulo_estudo()
    r1 = sessao_a.post("/api/multiescala/conjuntos", json={"nome": nome, "area": area})
    assert r1.status_code == 201, r1.text
    r2 = sessao_a.post("/api/multiescala/conjuntos", json={"nome": nome, "area": area})
    assert r2.status_code == 409, r2.text
    assert r2.json()["erro"] == "nome_existente"


# ---------------------------------------------------------------- apagar (cascata)
def test_apagar_conjunto_em_cascata(sessao_a, conjunto, fator_fino):
    fatores = [{"fator_id": fator_fino["id"], "peso": 1.0}]
    macro = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    }).json()

    r = sessao_a.delete(f"/api/multiescala/conjuntos/{conjunto['id']}")
    assert r.status_code == 204, r.text

    assert sessao_a.get(f"/api/multiescala/conjuntos/{conjunto['id']}").status_code == 404
    # a cascata da FK apagou a execução junto (não sobra órfã apontando para um conjunto inexistente)
    assert sessao_a.get(f"/api/multiescala/execucoes/{macro['id']}").status_code == 404
    # apagar de novo é 404, não 500 (idempotência do lado do cliente)
    assert sessao_a.delete(f"/api/multiescala/conjuntos/{conjunto['id']}").status_code == 404
    # o fator (recurso do inquilino, reusável) continua existindo — só o conjunto e o que dependia dele sumiu
    assert sessao_a.get(f"/api/multiescala/fatores/{fator_fino['id']}").status_code == 200


def test_apagar_fator_em_cascata(sessao_a, fator_fino):
    r = sessao_a.delete(f"/api/multiescala/fatores/{fator_fino['id']}")
    assert r.status_code == 204, r.text
    assert sessao_a.get(f"/api/multiescala/fatores/{fator_fino['id']}").status_code == 404
    assert sessao_a.delete(f"/api/multiescala/fatores/{fator_fino['id']}").status_code == 404
