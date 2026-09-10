"""Diagrama de rede pela API (item L4-04-d-diagrama-esquematico).

Cláusulas do portão provadas aqui (a de TEMPO, num alimentador da cooperativa de teste, está em
`test_rede_diagrama_medida.py`, marcador `lento`; a seleção bidirecional na tela está em
`tests/e2e/test_rede_diagrama.py`):

* gerar a partir do traçado de subrede grava nós e arestas e devolve o resumo com o grafo bruto ao lado do
  reduzido — `test_gerar_de_subrede_grava_o_grafo`;
* quatro layouts (árvore inteligente, radial, linha principal e geográfico) reaplicados pela API terminam com
  ZERO par de nós a menos de 1 unidade — `test_quatro_layouts_sem_sobreposicao`;
* a regra `reduzir_juncao_de_passagem` reduz o número de nós SEM mudar a conectividade, medido sobre a rede
  do banco — `test_reduzir_juncao_reduz_sem_partir_a_rede`;
* a seleção casa nos dois sentidos porque cada nó carrega a feição e o terminal de onde veio, e cada aresta a
  lista de feições que representa — `test_no_e_aresta_carregam_a_ancora_do_mapa`;
* exportação em SVG e PNG do mesmo grafo gravado — `test_exportar_svg_e_png`.

Refutação (papel adversário), provada aqui:
* `test_diagrama_de_subrede_com_laco_mantem_a_aresta_do_laco`: alimentador em ANEL, layout de árvore — o
  desenho continua com aresta suficiente para fechar o laço;
* `test_editar_a_rede_deixa_o_diagrama_inconsistente`: editar a rede marca o diagrama `inconsistente`, e ele
  só volta a `consistente` quando é gerado de novo;
* `test_diagrama_de_subrede_nunca_atualizada_e_recusado`: não sai desenho vazio fingindo rede;
* `test_modelo_embutido_nao_pode_ser_redefinido` e `test_regra_desconhecida_no_modelo_e_recusada`."""

import pytest

from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-04-d-diagrama-esquematico"

CTMT = "1_DIA_1"
CTMT_ANEL = "2_DIA_1"
SUB = "DIA"
DISJUNTOR = 4  # tipo `disjuntor` do grupo chave_de_media_tensao (pacote eletrica-br)
LAYOUTS_DO_PORTAO = ("arvore_inteligente", "radial", "linha_principal", "geografico")


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-diag-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _preparar(sessao, rid, nome_subrede, segmentos, lon0, lat0):
    """Um alimentador com o disjuntor de saída em (lon0, lat0) e um trecho de média tensão por par de
    coordenadas de `segmentos`. Recebe SEGMENTOS, e não um caminho, porque o alimentador em anel não é um
    caminho: ele tem um trecho de entrada e um circuito fechado depois dele."""
    atributos = {"ctmt": nome_subrede, "sub": SUB}
    feicoes = {"disjuntor": _ponto(sessao, rid, lon0, lat0, "chave_de_media_tensao", DISJUNTOR,
                                   atributos={**atributos, "unsemt_fas_con": "ABC"})}
    trechos = []
    for i, (a, b) in enumerate(segmentos):
        trechos.append(_linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
                              atributos={**atributos, "cod_id": f"MT{i}-{nome_subrede}"}))
    feicoes["trechos"] = trechos
    return feicoes


def _consecutivos(pontos):
    return [(pontos[i], pontos[i + 1]) for i in range(len(pontos) - 1)]


def _habilitar_e_atualizar(sessao, rid, nome_subrede):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    r = sessao.get(f"/api/rede/{rid}/subredes?limite=500")
    assert r.status_code == 200, r.text
    alvo = {s["nome"]: s for s in r.json()["itens"]}[nome_subrede]
    r = sessao.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar")
    assert r.status_code == 200, r.text
    return alvo


def _alimentador_reto(sessao, rid, nome=CTMT, lon0=37.0, lat0=18.0, trechos=8):
    d = 0.001
    pontos = [(lon0 + i * d, lat0) for i in range(trechos + 1)]
    feicoes = _preparar(sessao, rid, nome, _consecutivos(pontos), lon0, lat0)
    _habilitar_e_atualizar(sessao, rid, nome)
    return feicoes, pontos


def _alimentador_em_anel(sessao, rid, nome=CTMT_ANEL, lon0=38.0, lat0=19.0, lados=6):
    """Alimentador em ANEL: um trecho de entrada, saindo do disjuntor, e depois um circuito fechado. É o
    grafo da refutação do item — nenhuma regra e nenhum layout pode fazer a aresta que fecha o anel sumir.

    O disjuntor fica FORA do anel, na ponta do trecho de entrada, porque um anel perfeitamente fechado não
    tem cabeça: a marcação automática de controlador não acharia onde ancorar o alimentador."""
    import math

    raio = 0.004
    anel = [(lon0 + raio * math.cos(2 * math.pi * i / lados),
             lat0 + raio * math.sin(2 * math.pi * i / lados)) for i in range(lados)]
    anel.append(anel[0])
    cabeca = (lon0 - raio * 2, lat0)
    segmentos = [(cabeca, anel[0])] + _consecutivos(anel)
    feicoes = _preparar(sessao, rid, nome, segmentos, cabeca[0], cabeca[1])
    _habilitar_e_atualizar(sessao, rid, nome)
    return feicoes, anel


def _gerar(sessao, rid, nome, origem, modelo="basico", layout=None, espera=201):
    corpo = {"nome": nome, "origem": origem, "modelo": modelo}
    if layout:
        corpo["layout"] = layout
    r = sessao.post(f"/api/rede/{rid}/diagrama", json=corpo)
    assert r.status_code == espera, r.text
    return r.json()


# --- cláusula: gerar de subrede grava o grafo -----------------------------------------------------------

def test_gerar_de_subrede_grava_o_grafo(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "gerar", limpar_redes)
    _alimentador_reto(sessao_a, rid)

    saida = _gerar(sessao_a, rid, "alimentador reto", {"tipo": "subrede", "subrede": CTMT,
                                                       "tier": "media_tensao"})
    resumo = saida["resumo"]
    assert saida["estado"] == "consistente"
    assert saida["modelo"] == "basico" and saida["layout"] == "arvore_inteligente"
    assert resumo["nos"] >= 2 and resumo["arestas"] >= 1
    assert resumo["bruto"]["nos"] == resumo["nos"], "o modelo básico não tem regra: bruto == desenhado"
    assert resumo["componentes"] == 1
    assert resumo["pares_sobrepostos"] == 0

    r = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert len(doc["nos"]) == resumo["nos"] and len(doc["arestas"]) == resumo["arestas"]
    assert doc["origem"]["tipo"] == "subrede" and doc["origem"]["subrede"] == CTMT
    assert all(n["x"] is not None and n["y"] is not None for n in doc["nos"])

    r = sessao_a.get(f"/api/rede/{rid}/diagramas")
    assert r.status_code == 200, r.text
    assert [i["nome"] for i in r.json()["itens"]] == ["alimentador reto"]
    assert r.json()["itens"][0]["estado"] == "consistente"


def test_gerar_de_tracado_e_de_selecao(sessao_a, limpar_redes):
    """As outras duas origens da hipótese: um traçado com ponto de partida e uma seleção de feições."""
    rid = _criar_rede(sessao_a, "origens", limpar_redes)
    feicoes, _pontos = _alimentador_reto(sessao_a, rid)

    do_tracado = _gerar(sessao_a, rid, "por traçado", {
        "tipo": "tracado", "tracado": "subrede",
        "pontos_partida": [{"feicao_id": feicoes["disjuntor"]["id"], "terminal": 1}]})
    assert do_tracado["origem"]["tipo"] == "tracado"
    assert do_tracado["resumo"]["nos"] >= 2

    escolhidas = [t["id"] for t in feicoes["trechos"][:3]]
    da_selecao = _gerar(sessao_a, rid, "por seleção", {"tipo": "selecao", "feicoes": escolhidas})
    assert da_selecao["origem"]["tipo"] == "selecao"
    r = sessao_a.get(f"/api/rede/{rid}/diagrama/{da_selecao['id']}")
    feicoes_desenhadas = {f for a in r.json()["arestas"] for f in a["feicoes"]}
    assert feicoes_desenhadas == set(escolhidas), "a seleção desenha o que foi selecionado, nada mais"


# --- cláusula: quatro layouts, zero sobreposição ---------------------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS_DO_PORTAO)
def test_quatro_layouts_sem_sobreposicao(sessao_a, limpar_redes, layout):
    rid = _criar_rede(sessao_a, f"layout-{layout}", limpar_redes)
    _alimentador_reto(sessao_a, rid)
    saida = _gerar(sessao_a, rid, f"desenho {layout}",
                   {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"}, layout=layout)
    assert saida["layout"] == layout
    assert saida["resumo"]["pares_sobrepostos"] == 0, saida["resumo"]
    menor = saida["resumo"]["menor_distancia_proxima"]
    assert menor is None or menor >= 1.0, saida["resumo"]

    r = sessao_a.post(f"/api/rede/{rid}/diagrama/{saida['id']}/layout", json={"layout": "grade"})
    assert r.status_code == 200, r.text
    assert r.json()["layout"] == "grade" and r.json()["resumo"]["pares_sobrepostos"] == 0

    doc = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}").json()
    assert len(doc["nos"]) == saida["resumo"]["nos"], "reaplicar layout não cria nem apaga nó"
    assert len(doc["arestas"]) == saida["resumo"]["arestas"]


def test_layout_desconhecido_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "layout-ruim", limpar_redes)
    _alimentador_reto(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/diagrama", json={
        "nome": "x", "origem": {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"},
        "layout": "espiral"})
    assert r.status_code == 422 and r.json()["erro"] == "layout_desconhecido", r.text


# --- cláusula: reduzir junção de passagem ----------------------------------------------------------------

def test_reduzir_juncao_reduz_sem_partir_a_rede(sessao_a, limpar_redes):
    """Cláusula do portão, medida sobre a rede do banco: o desenho com a regra tem MENOS nós que o desenho
    sem ela, e os dois têm o mesmo número de componentes conexos."""
    rid = _criar_rede(sessao_a, "reduzir", limpar_redes)
    _alimentador_reto(sessao_a, rid, trechos=12)
    origem = {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"}

    sem_regra = _gerar(sessao_a, rid, "sem regra", origem, modelo="basico")
    r = sessao_a.put(f"/api/rede/{rid}/diagrama-modelo/so-reduz", json={
        "nome": "só reduzir junção", "regras": [{"regra": "reduzir_juncao_de_passagem"}],
        "layout": "linha_principal"})
    assert r.status_code == 200, r.text
    com_regra = _gerar(sessao_a, rid, "com regra", origem, modelo="so-reduz")

    assert com_regra["resumo"]["bruto"]["nos"] == sem_regra["resumo"]["nos"], "mesmo recorte, mesmo bruto"
    assert com_regra["resumo"]["nos"] < sem_regra["resumo"]["nos"], (com_regra["resumo"],
                                                                    sem_regra["resumo"])
    assert com_regra["resumo"]["componentes"] == com_regra["resumo"]["bruto"]["componentes"] == 1
    relatorio = com_regra["resumo"]["regras"][0]
    assert relatorio["regra"] == "reduzir_juncao_de_passagem" and relatorio["nos_removidos"] > 0
    soma = sum(a["agregadas"] for a in
               sessao_a.get(f"/api/rede/{rid}/diagrama/{com_regra['id']}").json()["arestas"])
    assert soma == sem_regra["resumo"]["arestas"], "nenhuma aresta some: elas são agregadas e contadas"


def test_modelo_esquematico_colapsa_e_reduz(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "esquematico", limpar_redes)
    _alimentador_reto(sessao_a, rid, trechos=10)
    saida = _gerar(sessao_a, rid, "esquema", {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"},
                   modelo="esquematico")
    nomes = [r["regra"] for r in saida["resumo"]["regras"]]
    assert nomes == ["colapsar_conteiner", "reduzir_juncao_de_passagem"]
    assert saida["resumo"]["nos"] < saida["resumo"]["bruto"]["nos"]
    assert saida["layout"] == "linha_principal"


# --- cláusula: seleção bidirecional (a âncora que a tela usa) --------------------------------------------

def test_no_e_aresta_carregam_a_ancora_do_mapa(sessao_a, limpar_redes):
    """A seleção nos dois sentidos é possível porque a resposta traz, em cada nó, a feição e o terminal de
    onde ele veio (e a coordenada geográfica dele), e em cada aresta a lista de feições que ela representa.
    Quem clica no diagrama sabe o que acender no mapa, e quem clica no mapa sabe que nó acender."""
    rid = _criar_rede(sessao_a, "ancora", limpar_redes)
    feicoes, _pontos = _alimentador_reto(sessao_a, rid)
    saida = _gerar(sessao_a, rid, "âncora", {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"})
    doc = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}").json()

    do_disjuntor = [n for n in doc["nos"] if n["feicao_id"] == feicoes["disjuntor"]["id"]]
    assert do_disjuntor, "o disjuntor da cabeça está no desenho"
    assert all(n["terminal"] is not None for n in do_disjuntor)
    assert all(n["lon"] is not None and n["lat"] is not None for n in doc["nos"])

    ids_dos_trechos = {t["id"] for t in feicoes["trechos"]}
    desenhados = {f for a in doc["arestas"] for f in a["feicoes"]}
    assert ids_dos_trechos <= desenhados, "todo trecho da subrede tem aresta que o representa"
    for a in doc["arestas"]:
        assert a["de"] and a["para"] and a["de"] != a["para"]


# --- cláusula: exportação -------------------------------------------------------------------------------

def test_exportar_svg_e_png(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "exportar", limpar_redes)
    _alimentador_reto(sessao_a, rid)
    saida = _gerar(sessao_a, rid, "para exportar",
                   {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"})

    svg = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}/exportar?formato=svg")
    assert svg.status_code == 200, svg.text
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert svg.text.startswith("<svg ") and svg.text.count("<line ") == saida["resumo"]["arestas"]
    assert svg.text.count("<circle ") == saida["resumo"]["nos"]

    png = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}/exportar?formato=png")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"

    como_json = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}/exportar")
    assert como_json.status_code == 200 and len(como_json.json()["nos"]) == saida["resumo"]["nos"]

    ruim = sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}/exportar?formato=dwg")
    assert ruim.status_code == 422 and ruim.json()["erro"] == "formato_invalido"


# --- refutação ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("layout", ("arvore_inteligente", "linha_principal"))
def test_diagrama_de_subrede_com_laco_mantem_a_aresta_do_laco(sessao_a, limpar_redes, layout):
    """Refutação declarada do item: alimentador em ANEL, desenhado em árvore. A árvore geradora guia só a
    posição; a aresta que fecha o laço continua no desenho, com e sem a regra de redução."""
    rid = _criar_rede(sessao_a, f"anel-{layout}", limpar_redes)
    _alimentador_em_anel(sessao_a, rid)
    origem = {"tipo": "subrede", "subrede": CTMT_ANEL, "tier": "media_tensao"}

    sem_regra = _gerar(sessao_a, rid, f"anel {layout}", origem, layout=layout)
    assert sem_regra["resumo"]["componentes"] == 1
    assert sem_regra["resumo"]["arestas"] >= sem_regra["resumo"]["nos"], (
        "num anel há pelo menos tantas arestas quanto nós; menos que isso é laço perdido")

    r = sessao_a.put(f"/api/rede/{rid}/diagrama-modelo/anel-reduz", json={
        "nome": "anel reduzido", "regras": [{"regra": "reduzir_juncao_de_passagem"}], "layout": layout})
    assert r.status_code == 200, r.text
    com_regra = _gerar(sessao_a, rid, f"anel reduzido {layout}", origem, modelo="anel-reduz", layout=layout)
    assert com_regra["resumo"]["componentes"] == 1
    assert com_regra["resumo"]["arestas"] >= com_regra["resumo"]["nos"], com_regra["resumo"]
    assert com_regra["resumo"]["nos"] >= 2


def test_editar_a_rede_deixa_o_diagrama_inconsistente(sessao_a, limpar_redes):
    """Refutação declarada do item: depois de editar a rede o diagrama fica marcado `inconsistente` e SÓ
    volta a `consistente` quando é gerado de novo. Ele não se conserta sozinho e não mente o estado."""
    rid = _criar_rede(sessao_a, "consistencia", limpar_redes)
    _feicoes, pontos = _alimentador_reto(sessao_a, rid)
    origem = {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"}
    saida = _gerar(sessao_a, rid, "consistência", origem)
    assert saida["estado"] == "consistente"

    meio = pontos[len(pontos) // 2]
    chave = _ponto(sessao_a, rid, meio[0], meio[1], "chave_de_media_tensao", 1,
                   atributos={"ctmt": CTMT, "cod_id": "CH-DIA"})
    r = sessao_a.post(f"/api/rede/{rid}/feicoes/pontos/applyEdits", json={"updates": [
        {"attributes": {"id": chave["id"]}, "geometry": {"x": meio[0] + 0.0001, "y": meio[1]}}]})
    assert r.status_code == 200, r.text
    assert r.json()["updateResults"][0]["success"] is True, r.text

    lista = sessao_a.get(f"/api/rede/{rid}/diagramas").json()["itens"]
    assert lista[0]["estado"] == "inconsistente", lista

    # trocar o layout NÃO conserta: só muda o desenho
    r = sessao_a.post(f"/api/rede/{rid}/diagrama/{saida['id']}/layout", json={"layout": "radial"})
    assert r.status_code == 200 and r.json()["estado"] == "inconsistente", r.text

    r = sessao_a.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao_a.get(f"/api/rede/{rid}/subredes?limite=500")
    alvo = {s["nome"]: s for s in r.json()["itens"]}[CTMT]
    assert sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status_code == 200
    de_novo = _gerar(sessao_a, rid, "consistência", origem)
    assert de_novo["id"] == saida["id"], "gerar pelo mesmo nome mantém o identificador"
    assert de_novo["estado"] == "consistente"


def test_diagrama_de_subrede_nunca_atualizada_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "nunca-atualizada", limpar_redes)
    d = 0.001
    lon0, lat0 = 39.0, 20.0
    pontos = [(lon0 + i * d, lat0) for i in range(4)]
    _preparar(sessao_a, rid, CTMT, _consecutivos(pontos), lon0, lat0)
    assert sessao_a.post(f"/api/rede/{rid}/topologia/habilitar").status_code == 201
    assert sessao_a.post(f"/api/rede/{rid}/controladores/importar").status_code == 200

    r = sessao_a.post(f"/api/rede/{rid}/diagrama", json={
        "nome": "vazio", "origem": {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"}})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "subrede_nunca_atualizada", r.text


def test_selecao_de_feicao_que_nao_e_desta_rede_e_recusada(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "selecao-vazia", limpar_redes)
    _alimentador_reto(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/diagrama", json={
        "nome": "nada", "origem": {"tipo": "selecao",
                                   "feicoes": ["00000000-0000-4000-8000-000000000001"]}})
    assert r.status_code == 409 and r.json()["erro"] == "selecao_vazia", r.text


def test_modelo_embutido_nao_pode_ser_redefinido(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "modelo-reservado", limpar_redes)
    r = sessao_a.put(f"/api/rede/{rid}/diagrama-modelo/basico",
                     json={"nome": "outro básico", "regras": [], "layout": "grade"})
    assert r.status_code == 422 and r.json()["erro"] == "modelo_reservado", r.text


def test_regra_desconhecida_no_modelo_e_recusada(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "regra-ruim", limpar_redes)
    r = sessao_a.put(f"/api/rede/{rid}/diagrama-modelo/inventado",
                     json={"nome": "inventado", "regras": [{"regra": "apagar_tudo"}], "layout": "grade"})
    assert r.status_code == 422 and r.json()["erro"] == "regra_desconhecida", r.text


def test_modelos_listam_embutidos_e_do_inquilino(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "modelos", limpar_redes)
    r = sessao_a.get(f"/api/rede/{rid}/diagrama-modelos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    embutidos = {i["codigo"] for i in corpo["itens"] if i["embutido"]}
    assert embutidos == {"basico", "esquematico", "geografico"}
    assert set(corpo["layouts"]) >= set(LAYOUTS_DO_PORTAO)
    assert "reduzir_juncao_de_passagem" in corpo["regras"]

    assert sessao_a.put(f"/api/rede/{rid}/diagrama-modelo/meu", json={
        "nome": "meu modelo", "regras": [{"regra": "remover_tipos", "tipos": ["ponto_notavel"]}],
        "layout": "radial"}).status_code == 200
    itens = sessao_a.get(f"/api/rede/{rid}/diagrama-modelos").json()["itens"]
    meu = [i for i in itens if i["codigo"] == "meu"]
    assert meu and meu[0]["embutido"] is False and meu[0]["layout"] == "radial"


def test_apagar_diagrama_nao_toca_na_rede(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "apagar", limpar_redes)
    _alimentador_reto(sessao_a, rid)
    saida = _gerar(sessao_a, rid, "some", {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"})
    assert sessao_a.delete(f"/api/rede/{rid}/diagrama/{saida['id']}").status_code == 204
    assert sessao_a.get(f"/api/rede/{rid}/diagrama/{saida['id']}").status_code == 404
    assert sessao_a.get(f"/api/rede/{rid}/diagramas").json()["total"] == 0
    subredes = sessao_a.get(f"/api/rede/{rid}/subredes?limite=500").json()["itens"]
    assert any(s["nome"] == CTMT and s["estado"] == "limpa" for s in subredes), subredes
