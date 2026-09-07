"""Dados de um painel por fonte (item L2-06-a-modelo-painel-fontes): `POST /api/itens/{id}/paineis/fontes/
{fonte_id}/dados` (sessão) e `POST /api/compartilhado/{token}/paineis/{id}/fontes/{fonte_id}/dados` (link
anônimo). Usa o painel de exemplo da demo (`plat.painel_exemplo_semear`, migração `20260906T2145_
documento_painel.sql`): 120 ocorrências determinísticas (generate_series), 4 categorias, sem dado real.

Cobre as cláusulas do portão: filtro global aplica a todas as fontes (contagem conferida com SQL direto);
link compartilhado abre em contexto anônimo e nega após revogação; painel de A não vaza dado de B mesmo
quando o próprio documento é adulterado para referenciar a camada de outro inquilino (a refutação exigida
do item)."""

from tests.api.paineis.conftest import FONTE_AGUA, FONTE_OCORRENCIAS
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-06-a-modelo-painel-fontes"


def _contar_categoria(conexao_plat_app, categoria):
    """Conta linhas reais na tabela física da camada de exemplo, direto por SQL — a referência de
    verdade contra a qual a contagem que a API devolve é conferida."""
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
            "WHERE tipo = 'camada_vetorial' AND dados->>'semente' = 'painel_exemplo' LIMIT 1"
        )
        r = cur.fetchone()
        cur.execute(f'SELECT count(*) AS n FROM "{r["schema"]}"."{r["tabela"]}" WHERE categoria = %s', (categoria,))
        n = cur.fetchone()["n"]
    conexao_plat_app.rollback()
    return n


def _total(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
            "WHERE tipo = 'camada_vetorial' AND dados->>'semente' = 'painel_exemplo' LIMIT 1"
        )
        r = cur.fetchone()
        cur.execute(f'SELECT count(*) AS n FROM "{r["schema"]}"."{r["tabela"]}"')
        n = cur.fetchone()["n"]
    conexao_plat_app.rollback()
    return n


def test_contagem_batida_por_fonte_bate_com_sql_direto(sessao_a, painel_exemplo_demo, conexao_plat_app):
    painel_id = painel_exemplo_demo["painel_id"]
    r = sessao_a.post(
        f"/api/itens/{painel_id}/paineis/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"total": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r.status_code == 200, r.text
    total_api = r.json()["resultados"]["total"]["valor"]
    total_sql = _total(conexao_plat_app)
    assert total_api == total_sql == 120, (total_api, total_sql)


def test_um_pedido_por_elemento_uma_unica_requisicao_por_fonte(sessao_a, painel_exemplo_demo):
    """Um POST cobre N elementos da MESMA fonte (aqui: contagem + soma) — a cláusula do adversário é sobre
    número de REQUISIÇÕES por ciclo, não sobre quantas agregações o servidor roda dentro dela."""
    painel_id = painel_exemplo_demo["painel_id"]
    r = sessao_a.post(
        f"/api/itens/{painel_id}/paineis/fontes/{FONTE_OCORRENCIAS}/dados",
        json={
            "pedidos": {
                "contagem": {"agregacao": "contagem"},
                "soma": {"agregacao": "soma", "campo": "valor"},
                "categorias": {"agregacao": "categorias", "campo": "categoria", "max_categorias": 8},
            },
            "filtro_execucao": {},
        },
    )
    assert r.status_code == 200, r.text
    resultados = r.json()["resultados"]
    assert set(resultados) == {"contagem", "soma", "categorias"}
    assert resultados["contagem"]["valor"] == 120
    assert resultados["categorias"]["tipo"] == "categorias"
    assert sum(linha["valor"] for linha in resultados["categorias"]["linhas"]) == 120


def test_filtro_global_aplica_a_todas_as_fontes_contagem_conferida_com_sql(
    sessao_a, painel_exemplo_demo, conexao_plat_app,
):
    painel_id = painel_exemplo_demo["painel_id"]
    esperado = _contar_categoria(conexao_plat_app, "energia")
    assert 0 < esperado < 120  # a categoria filtra de verdade (nem tudo, nem nada)

    for fonte in (FONTE_OCORRENCIAS, FONTE_AGUA):
        r = sessao_a.post(
            f"/api/itens/{painel_id}/paineis/fontes/{fonte}/dados",
            json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {"categoria": "energia"}},
        )
        assert r.status_code == 200, r.text
        if fonte == FONTE_OCORRENCIAS:
            assert r.json()["resultados"]["n"]["valor"] == esperado
        else:
            # FONTE_AGUA já tem filtro FIXO categoria=agua; combinado com o filtro global categoria=energia
            # (AND) não sobra nenhuma linha — prova que o filtro de execução realmente chega a esta fonte
            # também, e não só à primeira.
            assert r.json()["resultados"]["n"]["valor"] == 0


def test_campo_fora_da_fonte_e_recusado(sessao_a, painel_exemplo_demo):
    painel_id = painel_exemplo_demo["painel_id"]
    r = sessao_a.post(
        f"/api/itens/{painel_id}/paineis/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"x": {"agregacao": "soma", "campo": "fid"}}, "filtro_execucao": {}},
    )
    assert r.status_code == 422 and r.json()["erro"] == "campo_fora_da_fonte"


def test_outro_inquilino_nao_ve_o_painel(sessao_b, painel_exemplo_demo):
    """RLS comum (nenhum mecanismo novo): o admin de demo2 não lê um item de demo."""
    painel_id = painel_exemplo_demo["painel_id"]
    r = sessao_b.post(
        f"/api/itens/{painel_id}/paineis/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r.status_code == 404


def test_link_compartilhado_abre_anonimo_e_nega_apos_revogar(sessao_a, cliente, painel_exemplo_demo):
    painel_id = painel_exemplo_demo["painel_id"]
    r = sessao_a.post(f"/api/itens/{painel_id}/links", json={"nome": "zt-painel-link", "itens_incluidos": []})
    assert r.status_code == 201, r.text
    link = r.json()
    token = link["token"]

    # contexto ANÔNIMO de verdade: cliente sem cookie de sessão nenhum
    r_anon = cliente.post(
        f"/api/compartilhado/{token}/paineis/{painel_id}/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r_anon.status_code == 200, r_anon.text
    assert r_anon.json()["resultados"]["n"]["valor"] == 120

    r_rev = sessao_a.delete(f"/api/itens/{painel_id}/links/{link['id']}")
    assert r_rev.status_code == 204

    r_negado = cliente.post(
        f"/api/compartilhado/{token}/paineis/{painel_id}/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r_negado.status_code == 404 and r_negado.json()["erro"] == "link_invalido"


def test_painel_de_a_nao_vaza_dado_de_b_mesmo_com_documento_adulterado(
    sessao_a, cliente, painel_exemplo_demo, painel_exemplo_demo2,
):
    """Refutação exigida do item: adultera o `corpo.fontes[0].camada.ref` do painel de A para apontar para
    a camada de B (outro inquilino) e confere que NEM a rota autenticada NEM a rota de link devolvem o
    dado de B — a primeira por RLS comum, a segunda porque `plat.painel_camadas_resolver` só resolve
    camada do MESMO inquilino do painel, nunca por id livre."""
    painel_a = painel_exemplo_demo["painel_id"]
    camada_b = painel_exemplo_demo2["camada_id"]

    doc = sessao_a.get(f"/api/itens/{painel_a}").json()
    corpo = doc["dados"]["corpo"]
    fontes = [dict(f) for f in corpo["fontes"]]
    assert fontes[0]["id"] == FONTE_OCORRENCIAS
    fontes[0] = {**fontes[0], "camada": {"ref": camada_b}}
    corpo_adulterado = {**corpo, "fontes": fontes}
    r_put = sessao_a.put(
        f"/api/itens/{painel_a}",
        json={"dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo_adulterado}},
    )
    assert r_put.status_code == 200, r_put.text

    # rota autenticada: RLS de plat.item já barra a leitura da camada de outro inquilino
    r_auth = sessao_a.post(
        f"/api/itens/{painel_a}/paineis/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r_auth.status_code == 404

    # rota de link anônimo: painel_camadas_resolver só devolve camada do MESMO tenant do painel
    r_link = sessao_a.post(f"/api/itens/{painel_a}/links", json={"nome": "zt-painel-adulterado", "itens_incluidos": []})
    assert r_link.status_code == 201, r_link.text
    token = r_link.json()["token"]
    r_anon = cliente.post(
        f"/api/compartilhado/{token}/paineis/{painel_a}/fontes/{FONTE_OCORRENCIAS}/dados",
        json={"pedidos": {"n": {"agregacao": "contagem"}}, "filtro_execucao": {}},
    )
    assert r_anon.status_code == 404 and r_anon.json()["erro"] == "camada_nao_encontrada"
    sessao_a.delete(f"/api/itens/{painel_a}/links/{r_link.json()['id']}")

    # devolve o documento ao estado original (não deixa o painel de exemplo quebrado para outros testes)
    r_restaura = sessao_a.put(
        f"/api/itens/{painel_a}",
        json={"dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}},
    )
    assert r_restaura.status_code == 200, r_restaura.text
