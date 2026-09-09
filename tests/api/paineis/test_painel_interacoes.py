"""Portão do item L2-06-c-acoes-seletores-filtros-cruzados, camada de API: as regras do `corpo.mensagens`
e do elemento `seletor` recusam documento inválido com 422 `grafo_invalido` (cláusula 4 — ação de dado
entre fontes DIFERENTES sem relação declarada nomeia as duas fontes), e o filtro que as ações entregam
(`pedido.filtro` CQL2 e `filtro_execucao.__extensao`) bate com SQL direto na tabela da camada (cláusulas 1
e 3 do portão conferidas no servidor, não só na tela).

Camada de exemplo (`plat.painel_exemplo_semear`): 120 ocorrências determinísticas (30 por categoria),
pontos em EPSG:4326."""

import pytest

from tests.api.paineis.conftest import FONTE_AGUA, FONTE_OCORRENCIAS
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-06-c-acoes-seletores-filtros-cruzados"

F1 = FONTE_OCORRENCIAS
F2 = FONTE_AGUA
E_A = "01JPA1NEKEXEMPK0EKEM000WBA"  # indicador na fonte f1 (26 caracteres, sem I/L/O/U)
E_B = "01JPA1NEKEXEMPK0EKEM000WBB"  # indicador na fonte f2
E_SEL = "01JPA1NEKEXEMPK0EKEM000WBC"  # seletor na fonte f1
M_UM = "01JPA1NEKEXEMPK0EKEM000MDD"


def _admin(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    return ids["demo"], adm


def _tabela_exemplo(conexao_plat_app):
    _admin(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
            "WHERE tipo = 'camada_vetorial' AND dados->>'semente' = 'painel_exemplo' LIMIT 1"
        )
        r = cur.fetchone()
    return r["schema"], r["tabela"]


def _sql(conexao_plat_app, consulta, params=None):
    """A verdade fora da API: a consulta roda direto na tabela física."""
    schema, tabela = _tabela_exemplo(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(consulta.format(t=f'"{schema}"."{tabela}"'), params or ())
        linhas = [dict(x) for x in cur.fetchall()]
    conexao_plat_app.rollback()
    return linhas


def _pedir(sessao, painel_id, pedidos, filtro=None, fonte=F1):
    return sessao.post(f"/api/itens/{painel_id}/paineis/fontes/{fonte}/dados",
                       json={"pedidos": pedidos, "filtro_execucao": filtro or {}})


def _corpo_base(camada_id: str) -> dict:
    camada = {"ref": camada_id}
    return {
        "grade": {"colunas": 12, "linha_px": 36},
        "tema": {"modo": "claro"},
        "fontes": [
            {"id": F1, "nome": "ocorrências", "camada": camada, "campos": ["categoria", "valor"], "limite": 50},
            {"id": F2, "nome": "ocorrências de água", "camada": camada,
             "campos": ["categoria", "valor"],
             "filtro": {"op": "=", "args": [{"property": "categoria"}, "agua"]}, "limite": 50},
        ],
        "filtros": [],
        "parametros_url": [],
        "elementos": [
            {"id": E_A, "tipo": "indicador", "titulo": "todas", "fonte": F1,
             "x": 0, "y": 0, "largura": 3, "altura": 3, "opcoes": {"agregacao": "contagem"}},
            {"id": E_B, "tipo": "indicador", "titulo": "água", "fonte": F2,
             "x": 3, "y": 0, "largura": 3, "altura": 3, "opcoes": {"agregacao": "contagem"}},
            {"id": E_SEL, "tipo": "seletor", "titulo": "categoria", "fonte": F1,
             "x": 6, "y": 0, "largura": 3, "altura": 2,
             "opcoes": {"modo": "categoria", "campo": "categoria"}},
        ],
        "mensagens": [],
    }


# ---------------------------------------------------------------- cláusula 4: relação é obrigatória
def test_acao_entre_fontes_diferentes_sem_relacao_e_recusada_nomeando_as_fontes(
    sessao_a, painel_exemplo_demo,
):
    corpo = _corpo_base(painel_exemplo_demo["camada_id"])
    corpo["mensagens"] = [{
        "id": M_UM,
        "gatilho": {"origem": E_SEL, "evento": "filtro_mudou"},
        "acoes": [{"alvo": E_B, "acao": "filtrar"}],  # f1 -> f2 sem relacao
    }]
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-c sem relação",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}})
    assert r.status_code == 422, r.text
    erro = r.json()
    assert erro["erro"] == "grafo_invalido"
    detalhe = erro.get("detalhe") or []
    regras = [d for d in detalhe if d.get("regra") == "relacao_ausente"]
    assert len(regras) == 1, detalhe
    mensagem = regras[0]["erro"]
    # a mensagem NOMEIA as duas fontes, para quem edita saber o par que falta ligar
    assert "ocorrências" in mensagem and "água" in mensagem, mensagem


def test_acao_de_selecao_na_mesma_fonte_sem_relacao_e_recusada(sessao_a, painel_exemplo_demo):
    """Regra do painel: seleção não vira `mesma_fonte` (linha de painel não tem coluna de id estável) —
    o filtro da seleção tem de ir por atributo ou espacial, mesmo entre elementos da mesma fonte."""
    corpo = _corpo_base(painel_exemplo_demo["camada_id"])
    corpo["mensagens"] = [{
        "id": M_UM,
        "gatilho": {"origem": E_A, "evento": "selecao_mudou"},
        "acoes": [{"alvo": E_SEL, "acao": "filtrar"}],  # mesma fonte, mas gatilho de seleção
    }]
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-c seleção sem relação",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}})
    assert r.status_code == 422, r.text
    assert any(d.get("regra") == "relacao_ausente" for d in (r.json().get("detalhe") or [])), r.text


def test_mensagens_validas_da_semente_salvam_e_o_seletor_sem_campo_e_recusado(
    sessao_a, painel_exemplo_demo,
):
    # (a) o mesmo corpo COM relações declaradas salva (201) — o caminho feliz do editor
    corpo = _corpo_base(painel_exemplo_demo["camada_id"])
    corpo["mensagens"] = [{
        "id": M_UM,
        "gatilho": {"origem": E_SEL, "evento": "filtro_mudou"},
        "acoes": [
            {"alvo": E_A, "acao": "filtrar"},  # mesma fonte, gatilho de filtro: relação opcional
            {"alvo": E_B, "acao": "filtrar",
             "relacao": {"tipo": "atributo", "campo_origem": "categoria", "campo_alvo": "categoria",
                         "operador": "in"}},
        ],
    }]
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-c com relações",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}})
    assert r.status_code == 201, r.text
    painel_id = r.json()["id"]
    try:
        r = sessao_a.get(f"/api/itens/{painel_id}")
        assert r.status_code == 200
        mensagens = r.json()["dados"]["corpo"]["mensagens"]
        assert len(mensagens) == 1 and mensagens[0]["id"] == M_UM
    finally:
        sessao_a.delete(f"/api/itens/{painel_id}")

    # (b) seletor apontando para campo que a fonte não expõe: 422 campo_inexistente
    corpo2 = _corpo_base(painel_exemplo_demo["camada_id"])
    corpo2["elementos"][2]["opcoes"] = {"modo": "categoria", "campo": "nao_existe"}
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-c campo errado",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo2}})
    assert r.status_code == 422, r.text
    assert any(d.get("regra") == "campo_inexistente" for d in (r.json().get("detalhe") or [])), r.text


# ---------------------------------------------------------------- cláusula 1: contagens do filtro cruzado
@pytest.mark.parametrize(
    ("categoria", "esperado_nas_aguas"),
    [("agua", 30), ("via", 0)],  # 'via' ∩ 'agua' = 0: o filtro cruza, não substitui
)
def test_filtro_do_pedido_bate_com_sql_na_fonte_e_cruza_a_segunda(
    sessao_a, painel_exemplo_demo, conexao_plat_app, categoria, esperado_nas_aguas,
):
    """O mesmo filtro CQL2 que o barramento entrega à vista chega ao pedido (`pedidos.chave.filtro`) e
    precisa bater com o COUNT(*) em SQL direto — na fonte comum E na fonte que já tem filtro fixo
    `categoria = 'agua'` (o filtro da ação é somado por AND, nunca substitui o da fonte)."""
    pedido = {"agregacao": "indicador", "estatistica": "contagem",
              "filtro": {"op": "=", "args": [{"property": "categoria"}, categoria]}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido})
    assert r.status_code == 200, r.text
    comum = r.json()["resultados"]["i"]["valor"]
    esperado = _sql(conexao_plat_app,
                    "SELECT count(*) AS v FROM {t} WHERE categoria = %s", (categoria,))[0]["v"]
    assert comum == esperado

    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido}, fonte=F2)
    assert r.status_code == 200, r.text
    aguas = r.json()["resultados"]["i"]["valor"]
    esperado2 = _sql(conexao_plat_app,
                     "SELECT count(*) AS v FROM {t} WHERE categoria = 'agua' AND categoria = %s",
                     (categoria,))[0]["v"]
    assert aguas == esperado2 == esperado_nas_aguas


def test_filtro_por_in_da_selecao_bate_com_sql(sessao_a, painel_exemplo_demo, conexao_plat_app):
    """A tradução da relação por atributo (seleção na barra -> `in` na lista) é o que o servidor executa:
    `filtro: {op: 'in', args: [{property: 'categoria'}, ['agua','via']]}` == SQL `categoria IN (...)`."""
    pedido = {"agregacao": "indicador", "estatistica": "contagem",
              "filtro": {"op": "in", "args": [{"property": "categoria"}, ["agua", "via"]]}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido})
    assert r.status_code == 200, r.text
    esperado = _sql(conexao_plat_app,
                    "SELECT count(*) AS v FROM {t} WHERE categoria IN ('agua', 'via')")[0]["v"]
    assert r.json()["resultados"]["i"]["valor"] == esperado == 60


def test_filtro_com_campo_fora_da_fonte_e_recusado(sessao_a, painel_exemplo_demo):
    """Defesa de execução: o filtro de ação só usa campo que a FONTE expõe — um filtro forjado direto na
    rota de dado (sem passar pelo editor) não amplia a consulta."""
    pedido = {"agregacao": "indicador", "estatistica": "contagem",
              "filtro": {"op": "=", "args": [{"property": "fid"}, 1]}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_fora_da_fonte", r.text


# ---------------------------------------------------------------- cláusula 3: extensão como filtro
def test_extensao_do_mapa_no_filtro_de_execucao_bate_com_sql(
    sessao_a, painel_exemplo_demo, conexao_plat_app,
):
    """`filtro_execucao.__extensao` (caixa o,s,l,n em EPSG:4326) vira ST_MakeEnvelope na coluna de
    geometria — é o caminho do botão "filtrar pela extensão" do mapa; a contagem na tela tem de ser o
    COUNT(*) do envelope em SQL direto."""
    caixa = [-46.60, -23.50, -46.53, -23.45]
    filtro = {"__extensao": ",".join(str(v) for v in caixa)}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"i": {"agregacao": "indicador", "estatistica": "contagem"}}, filtro=filtro)
    assert r.status_code == 200, r.text
    dentro = r.json()["resultados"]["i"]["valor"]
    esperado = _sql(
        conexao_plat_app,
        "SELECT count(*) AS v FROM {t} "
        "WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
        tuple(caixa),
    )[0]["v"]
    assert dentro == esperado
    # a caixa é um SUBCONJUNTO de verdade (o teste não passa em vão): menos que as 120
    assert 0 < dentro < 120
    # combinada com o filtro de categoria da ação (o seletor diz 'agua', a caixa recorta o mapa)
    pedido = {"agregacao": "indicador", "estatistica": "contagem",
              "filtro": {"op": "=", "args": [{"property": "categoria"}, "agua"]}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido}, filtro=filtro)
    assert r.status_code == 200, r.text
    combinado = r.json()["resultados"]["i"]["valor"]
    esperado2 = _sql(
        conexao_plat_app,
        "SELECT count(*) AS v FROM {t} WHERE categoria = 'agua' "
        "AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
        tuple(caixa),
    )[0]["v"]
    assert combinado == esperado2 and combinado <= dentro
