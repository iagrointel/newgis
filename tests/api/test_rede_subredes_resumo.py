"""Sumário por subrede (item L4-04-c-sumarios-por-subrede).

Cláusulas do portão provadas aqui, sobre uma rede pequena no formato da BDGD Módulo 10, com números
conferíveis à mão:

1. a tabela `plat.rede_subrede_resumo` tem as colunas da hipótese e é preenchida pelo cálculo —
   `test_sumario_do_alimentador_tem_as_colunas_da_hipotese`;
2. o sumário do tier de BAIXA tensão é filiado por outro atributo (`uni_tr_mt`, o transformador) e não
   herda os trechos de média tensão — `test_sumario_da_baixa_tensao_conta_o_que_sai_do_transformador`;
3. a tabela serve a um painel: vem com a descrição das colunas ao lado das linhas, e toda coluna
   declarada aparece em toda linha — `test_tabela_descreve_as_colunas_para_o_painel`;
4. exportação CSV com o mesmo conteúdo — `test_csv_tem_cabecalho_e_uma_linha_por_subrede`;
5. o tronco é medido pela topologia quando há topologia e controlador, e fica NULO (com a razão escrita)
   quando não há — `test_tronco_medido_pela_topologia`, `test_tronco_nulo_sem_topologia`;
6. o painel (L2-06) LIGA na tabela: uma camada do catálogo apontando para a tabela física do sumário e
   uma fonte de painel sobre ela respondem os pedidos oficiais (indicadores e tabela) pela rota de dados
   do painel, conferidos contra SQL direto — `test_painel_liga_na_tabela_do_sumario`.

A conferência contra o arquivo real da cooperativa de teste (20 alimentadores, km de MT e contagem de
unidades consumidoras por CTMT) está em `test_rede_subredes_resumo_medida.py`, marcada `lento`."""

import json
import os
import uuid

import psycopg2.extras
import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L4-04-c-sumarios-por-subrede"

CTMT_A = "1_TST_1"
CTMT_B = "2_TST_1"
SUB = "TST"
TRAFO_A = "TR1"
DISJUNTOR = 4  # tipo `disjuntor` dentro do grupo chave_de_media_tensao (pacote eletrica-br)
UC_BT = 1      # tipo `consumidor_de_baixa_tensao` no grupo unidade_consumidora
GD_BT = 1      # tipo `geracao_em_baixa_tensao` no grupo geracao_distribuida


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-resumo-{sufixo}", "disciplina": "eletrica"})
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


def _rede_bdgd(sessao, rid, com_topologia=True, lon0=30.0, lat0=10.0):
    """Dois alimentadores no vocabulário da BDGD, com número redondo em cada atributo:

      * `1_TST_1`: dois trechos de MT (100 m + 200 m declarados), um transformador de 75 kVA, um trecho de
        BT de 50 m, três unidades consumidoras (duas RE1 de 1.200 kWh, uma RU1 de 600 kWh) e uma geração
        distribuída de 5,5 kW. O disjuntor de saída carrega o `ctmt`, e é dele que sai o controlador.
      * `2_TST_1`: um trecho de MT de 300 m e nada mais — serve para provar que o sumário separa os dois.
    """
    d = 0.001
    a, b, c = (lon0, lat0), (lon0 + d, lat0), (lon0 + 2 * d, lat0)
    bt = (lon0 + 2 * d, lat0 + d)
    a2, b2 = (lon0, lat0 + 10 * d), (lon0 + d, lat0 + 10 * d)
    at_a = {"ctmt": CTMT_A, "sub": SUB}
    at_b = {"ctmt": CTMT_B, "sub": SUB}
    disjuntor = _ponto(sessao, rid, *a, "chave_de_media_tensao", DISJUNTOR, atributos=at_a)
    _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
           atributos={**at_a, "cod_id": "MT1", "comp": 100})
    _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao",
           atributos={**at_a, "cod_id": "MT2", "comp": 200})
    trafo = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1,
                   atributos={"cod_id": TRAFO_A, "ctmt": CTMT_A, "pot_nom": 75})
    _linha(sessao, rid, [list(c), list(bt)], "trecho_de_baixa_tensao",
           atributos={"cod_id": "BT1", "ctmt": CTMT_A, "uni_tr_mt": TRAFO_A, "comp": 50})
    for i, (classe, energia) in enumerate((("RE1", 1200), ("RE1", 1200), ("RU1", 600))):
        _ponto(sessao, rid, bt[0] + i * 1e-5, bt[1], "unidade_consumidora", UC_BT,
               atributos={"cod_id": f"UC{i}", "ctmt": CTMT_A, "uni_tr_mt": TRAFO_A,
                          "clas_sub": classe, "ene": energia})
    _ponto(sessao, rid, bt[0], bt[1] + 1e-5, "geracao_distribuida", GD_BT,
           atributos={"cod_id": "GD1", "ctmt": CTMT_A, "uni_tr_mt": TRAFO_A, "pot": 5.5})
    _linha(sessao, rid, [list(a2), list(b2)], "trecho_de_media_tensao",
           atributos={**at_b, "cod_id": "MT3", "comp": 300})
    if com_topologia:
        r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
        assert r.status_code == 201, r.text
        r = sessao.post(f"/api/rede/{rid}/controladores/importar")
        assert r.status_code == 200, r.text
    return {"disjuntor": disjuntor, "trafo": trafo}


def _subredes_com_controlador(sessao, rid):
    """Sem topologia não há como marcar controlador pela importação; as subredes são criadas uma a uma
    pelo caminho normal (definir controlador no disjuntor e no transformador)."""
    r = sessao.get(f"/api/rede/{rid}/subredes")
    assert r.status_code == 200, r.text
    return {s["nome"]: s for s in r.json()["itens"]}


def _calcular(sessao, rid, **params):
    r = sessao.post(f"/api/rede/{rid}/subredes/resumos/calcular", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _tabela(sessao, rid, **params):
    r = sessao.get(f"/api/rede/{rid}/subredes/resumos", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _por_subrede(tabela):
    return {i["subrede"]: i for i in tabela["itens"]}


# --- cláusula 1: as colunas da hipótese, calculadas ------------------------------------------------------

def test_sumario_do_alimentador_tem_as_colunas_da_hipotese(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "colunas", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    contagem = _calcular(sessao_a, rid)
    assert contagem["calculadas"] == contagem["subredes"] and contagem["subredes"] >= 3, contagem

    linhas = _por_subrede(_tabela(sessao_a, rid, tier="media_tensao"))
    assert set(linhas) == {CTMT_A, CTMT_B}, sorted(linhas)
    alimentador = linhas[CTMT_A]

    # km por nível de tensão: 100 m + 200 m de média, 50 m de baixa (o que o cadastro declara)
    assert alimentador["km_por_nivel"]["trecho_de_media_tensao"] == pytest.approx(0.300), alimentador
    assert alimentador["km_por_nivel"]["trecho_de_baixa_tensao"] == pytest.approx(0.050), alimentador
    assert alimentador["km_declarado"] == pytest.approx(0.350), alimentador
    # comprimento pela geometria: três passos de 0,001 grau nesta latitude dão ~110 m cada, contra os
    # 350 m que o cadastro declara — a diferença é medida e guardada, não escondida
    assert alimentador["km_geometria"] == pytest.approx(0.330, abs=0.005), alimentador
    assert -10.0 < alimentador["divergencia_pct"] < 0.0, alimentador

    assert alimentador["trafos"] == 1 and alimentador["kva_instalado"] == pytest.approx(75.0)
    assert alimentador["ucs"] == 3, alimentador
    assert alimentador["ucs_por_classe"] == {"RE1": 2, "RU1": 1}, alimentador
    assert alimentador["energia_anual_kwh"] == pytest.approx(3000.0), alimentador
    assert alimentador["gd_unidades"] == 1 and alimentador["gd_potencia_kw"] == pytest.approx(5.5)
    # dispositivos por categoria: o vocabulário do pacote, não uma lista escrita à mão
    categorias = alimentador["dispositivos_por_categoria"]
    assert categorias.get("consumo") == 3, categorias    # as três unidades consumidoras
    assert categorias.get("geracao") == 1, categorias     # a geração distribuída
    assert categorias.get("medicao") == 4, categorias     # medição: as três unidades mais a geração
    assert categorias.get("transformacao", 0) >= 1, categorias  # o transformador
    assert alimentador["atributo_de_subrede"] == "ctmt", alimentador

    # o outro alimentador tem só o trecho dele: a filiação separa os dois
    outro = linhas[CTMT_B]
    assert outro["km_declarado"] == pytest.approx(0.300) and outro["ucs"] == 0, outro
    assert outro["trafos"] == 0 and outro["gd_unidades"] == 0, outro


# --- cláusula 2: o tier de baixa tensão filia por outro atributo -----------------------------------------

def test_sumario_da_baixa_tensao_conta_o_que_sai_do_transformador(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "bt", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)
    linhas = _por_subrede(_tabela(sessao_a, rid, tier="baixa_tensao"))
    assert TRAFO_A in linhas, sorted(linhas)
    bt = linhas[TRAFO_A]
    assert bt["atributo_de_subrede"] == "uni_tr_mt", bt
    # o trecho de BT e as unidades consumidoras entram; os trechos de MT NÃO (não têm uni_tr_mt)
    assert bt["km_por_nivel"] == {"trecho_de_baixa_tensao": pytest.approx(0.050)}, bt
    assert bt["ucs"] == 3 and bt["gd_unidades"] == 1, bt
    assert bt["energia_anual_kwh"] == pytest.approx(3000.0), bt


# --- cláusula 3: a tabela se descreve para o painel ------------------------------------------------------

def test_tabela_descreve_as_colunas_para_o_painel(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "painel", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)
    tabela = _tabela(sessao_a, rid)
    assert tabela["total"] == len(tabela["itens"]) and tabela["itens"], tabela["total"]
    codigos = [c["codigo"] for c in tabela["colunas"]]
    # o que um elemento de painel precisa para se ligar sozinho: código, rótulo, tipo e unidade
    for coluna in tabela["colunas"]:
        assert set(coluna) == {"codigo", "nome", "tipo", "unidade"}, coluna
        assert coluna["nome"] and coluna["tipo"] in ("texto", "inteiro", "real", "mapa", "data"), coluna
    # toda coluna declarada existe em toda linha (chave presente, ainda que nula)
    for item in tabela["itens"]:
        faltando = [c for c in codigos if c not in item]
        assert not faltando, (faltando, item)
    # e o número que um indicador somaria é número, não texto
    for item in tabela["itens"]:
        for coluna in tabela["colunas"]:
            valor = item[coluna["codigo"]]
            if coluna["tipo"] in ("inteiro", "real") and valor is not None:
                assert isinstance(valor, (int, float)), (coluna, valor)
            if coluna["tipo"] == "mapa":
                assert isinstance(valor, dict), (coluna, valor)


# --- cláusula 4: exportação CSV ---------------------------------------------------------------------------

def test_csv_tem_cabecalho_e_uma_linha_por_subrede(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "csv", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)
    tabela = _tabela(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/subredes/resumos", params={"formato": "csv"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv"), r.headers["content-type"]
    linhas = [linha for linha in r.text.split("\n") if linha]
    assert len(linhas) == 1 + len(tabela["itens"]), r.text[:500]
    cabecalho = linhas[0].split(",")
    assert cabecalho[0] == "subrede" and "km_declarado_km" in cabecalho, cabecalho
    # a coluna de mapa sai como JSON legível numa célula
    import csv as csv_mod

    lidas = list(csv_mod.DictReader(r.text.splitlines()))
    do_alimentador = [linha for linha in lidas if linha["subrede"] == CTMT_A][0]
    assert json.loads(do_alimentador["ucs_por_classe"]) == {"RE1": 2, "RU1": 1}, do_alimentador
    assert float(do_alimentador["km_declarado_km"]) == pytest.approx(0.350)


def test_formato_desconhecido_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "formato", limpar_redes)
    r = sessao_a.get(f"/api/rede/{rid}/subredes/resumos", params={"formato": "xlsx"})
    assert r.status_code == 422, r.text


# --- cláusula 5: tronco ------------------------------------------------------------------------------------

def test_tronco_medido_pela_topologia(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "tronco", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)
    alimentador = _por_subrede(_tabela(sessao_a, rid, tier="media_tensao"))[CTMT_A]
    assert alimentador["tronco_origem"] == "topologia", alimentador
    # do disjuntor até o fim da baixa tensão são três passos de 0,001 grau (~110 m cada) pela geometria
    assert 320.0 < alimentador["tronco_max_m"] < 340.0, alimentador


def test_tronco_nulo_sem_topologia(sessao_a, limpar_redes):
    """Sem topologia construída não há controlador com nó: a coluna fica NULA e a razão fica escrita, em
    vez de gravar zero e parecer medida."""
    rid = _criar_rede(sessao_a, "sem-topo", limpar_redes)
    _rede_bdgd(sessao_a, rid, com_topologia=False)
    # a subrede existe assim que um controlador é definido; sem topologia, a importação recusa
    r = sessao_a.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 409, r.text
    r = sessao_a.get(f"/api/rede/{rid}/subredes")
    assert r.status_code == 200 and r.json()["total"] == 0, r.text
    contagem = _calcular(sessao_a, rid)
    assert contagem == {"subredes": 0, "calculadas": 0, "sem_atributo": [], "duracao_ms": 0}, contagem
    assert _tabela(sessao_a, rid)["total"] == 0


# --- recálculo é idempotente e por subrede ----------------------------------------------------------------

def test_recalcular_nao_duplica_linha_e_aceita_uma_subrede(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "recalcular", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)
    antes = _tabela(sessao_a, rid)
    _calcular(sessao_a, rid)
    depois = _tabela(sessao_a, rid)
    assert antes["total"] == depois["total"], (antes["total"], depois["total"])

    subrede = _subredes_com_controlador(sessao_a, rid)[CTMT_A]
    contagem = _calcular(sessao_a, rid, subrede_id=subrede["id"])
    assert contagem["subredes"] == 1 and contagem["calculadas"] == 1, contagem
    assert _tabela(sessao_a, rid)["total"] == depois["total"]


def test_subrede_inexistente_nao_cria_linha(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "inexistente", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    contagem = _calcular(sessao_a, rid, subrede_id="00000000-0000-4000-8000-000000000001")
    assert contagem["subredes"] == 0 and contagem["calculadas"] == 0, contagem


# --- cláusula 6: o painel (L2-06) liga na tabela ------------------------------------------------------------

FONTE_RESUMO = "01JPA1NEKEXEMPK0F0NTE0000C"
ELEM_INDICADOR = "01JPA1NEKEXEMPK0F0NTE000E1"
ELEM_TABELA = "01JPA1NEKEXEMPK0F0NTE000E2"

# as colunas do sumário que a fonte expõe (lista branca do painel — nunca SELECT *)
CAMPOS_FONTE_RESUMO = ["subrede_nome", "rede_id", "km_declarado", "trafos", "kva_instalado",
                       "ucs", "energia_anual_kwh", "gd_unidades", "gd_potencia_kw"]


def test_painel_liga_na_tabela_do_sumario(sessao_a, limpar_redes, conexao_plat_app):
    """O portão exige que o painel (L2-06) consiga LIGAR a esta tabela. A ligação de um painel é uma
    FONTE: camada do catálogo (schema+tabela) + campos + filtro, lida pela rota oficial de dados
    (`POST /api/itens/{id}/paineis/fontes/{fonte}/dados`, motor do L2-06-b). A prova monta a camada
    apontando para a tabela física do sumário e pede indicadores e linhas — cada número conferido
    contra SQL direto na tabela, por caminho independente.

    A camada é registrada por SQL (mesma via da semente `plat.painel_exemplo_semear`): não existe rota
    de catálogo para apontar uma camada a uma tabela do próprio schema plat — camadas de catálogo vivem
    em `d_<slug>`. Sem função de tile de propósito: a tabela do sumário não tem geometria."""
    rid = _criar_rede(sessao_a, "painel-liga", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    _calcular(sessao_a, rid)

    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")

    camada_id = str(uuid.uuid4())
    painel_id = None
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, "
                "modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'inquilino', %s, %s)",
                (camada_id, ids["demo"], f"{PREFIXO_TESTE}-camada-resumo", adm,
                 psycopg2.extras.Json({
                     "schema": os.environ["PLAT_SCHEMA"], "tabela": "rede_subrede_resumo",
                     "fonte": "hospedada",
                     "campos": [{"nome": c, "tipo": "text" if c in ("subrede_nome", "rede_id") else "numeric"}
                                for c in CAMPOS_FONTE_RESUMO]}),
                 adm, adm),
            )
            # o esperado por caminho INDEPENDENTE: SQL direto na tabela, antes de chamar a rota do painel
            cur.execute(
                "SELECT count(*) AS n, sum(kva_instalado) AS kva, sum(ucs) AS ucs, "
                "sum(energia_anual_kwh) AS ene FROM plat.rede_subrede_resumo WHERE rede_id = %s::uuid",
                (rid,),
            )
            esperado = dict(cur.fetchone())
        conexao_plat_app.commit()
        assert esperado["n"] == 3 and float(esperado["kva"]) == 75.0, esperado

        corpo = {
            "grade": {"colunas": 12, "linha_px": 36},
            "fontes": [{"id": FONTE_RESUMO, "nome": "sumário por subrede",
                        "camada": {"ref": camada_id}, "campos": CAMPOS_FONTE_RESUMO,
                        "filtro": {"op": "=", "args": [{"property": "rede_id"}, rid]}}],
            "elementos": [
                {"id": ELEM_INDICADOR, "tipo": "indicador", "titulo": "kVA instalado", "fonte": FONTE_RESUMO,
                 "x": 0, "y": 0, "largura": 3, "altura": 3,
                 "opcoes": {"agregacao": "soma", "campo": "kva_instalado"}},
                {"id": ELEM_TABELA, "tipo": "tabela", "titulo": "subredes", "fonte": FONTE_RESUMO,
                 "x": 0, "y": 3, "largura": 8, "altura": 6,
                 "opcoes": {"campos": ["subrede_nome", "ucs", "kva_instalado"], "max_linhas": 10}},
            ],
        }
        r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": f"{PREFIXO_TESTE}-painel-resumo",
                                              "dados": {"tipo": "painel", "esquema_versao": 3,
                                                        "corpo": corpo}})
        assert r.status_code == 201, r.text
        painel_id = r.json()["id"]

        r = sessao_a.post(
            f"/api/itens/{painel_id}/paineis/fontes/{FONTE_RESUMO}/dados",
            json={"pedidos": {
                "subredes": {"agregacao": "indicador", "estatistica": "contagem"},
                "kva": {"agregacao": "indicador", "estatistica": "soma", "campo": "kva_instalado"},
                "ucs": {"agregacao": "indicador", "estatistica": "soma", "campo": "ucs"},
                "energia": {"agregacao": "indicador", "estatistica": "soma", "campo": "energia_anual_kwh"},
                "linhas": {"agregacao": "linhas",
                           "campos": ["subrede_nome", "ucs", "kva_instalado", "km_declarado"],
                           "ordenacao": {"campo": "subrede_nome", "direcao": "asc"},
                           "limite": 10, "total": True},
            }, "filtro_execucao": {}})
        assert r.status_code == 200, r.text
        res = r.json()["resultados"]
        # cada número do painel bate com o SQL direto na tabela
        assert res["subredes"]["valor"] == esperado["n"] == 3, res
        assert res["kva"]["valor"] == pytest.approx(float(esperado["kva"])), res
        assert res["ucs"]["valor"] == esperado["ucs"] == 6, res          # 3 UCs do alimentador + 3 da BT
        assert res["energia"]["valor"] == pytest.approx(float(esperado["ene"])), res
        # a tabela do painel lê as linhas da tabela do sumário, uma por subrede, na ordem pedida
        assert res["linhas"]["total"] == 3, res
        assert [linha["subrede_nome"] for linha in res["linhas"]["linhas"]] == [CTMT_A, CTMT_B, TRAFO_A], res
        primeiro = res["linhas"]["linhas"][0]
        assert primeiro["ucs"] == 3 and primeiro["kva_instalado"] == pytest.approx(75.0), primeiro
        assert primeiro["km_declarado"] == pytest.approx(0.350), primeiro
    finally:
        if painel_id:
            sessao_a.delete(f"/api/itens/{painel_id}")
        # plat.item não aceita DELETE nem UPDATE direto (p_item_apagar é false de propósito): a casa
        # apaga pela lixeira, SECURITY DEFINER — mesmo padrão da fixture de fronteira do L2-06-b.
        # `contexto` é transaction-local: o commit acima o limpou, então é posto de novo aqui.
        contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT plat.item_lixeira(%s::uuid, true) AS ok", (camada_id,))
            assert cur.fetchone()["ok"] is True, "lixeira recusou a camada do sumário"
        conexao_plat_app.commit()
