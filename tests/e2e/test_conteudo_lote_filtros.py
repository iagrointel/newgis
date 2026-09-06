"""e2e do item L0-03-f-tela-conteudo (portão): seleção em massa (marcar 50 pela tela, mover para pasta pelo
"lote-mover", conferir que os 50 mudaram de pasta no servidor); filtros laterais combinando tipo + tag + data
(o resultado da tela tem de ser igual ao de uma chamada direta com os mesmos parâmetros); paginação com 10 mil
itens no inquilino, medindo pagina_conteudo_ms de uma navegação fresca para /conteudo. Medidas gravadas em
tests/medidas/L0-03-f-tela-conteudo.json. Sem nginx na frente (uvicorn de trilha): navegador pela frente de
tests/e2e/frente_trilha.py (item L0-03-e)."""

import contextlib
import time

import pytest

from tests.e2e.apoio import sufixo
from tests.e2e.apoio_catalogo import TelaCatalogo
from tests.e2e.frente_trilha import FrenteTrilha
from tests.e2e.test_conteudo import api_catalogo  # noqa: F401 (fixture reaproveitada)

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-03-f-tela-conteudo"


def _contexto(browser, base_url, env):
    frente = FrenteTrilha.se_preciso(base_url, env["PLAT_URL_PUBLICA"])
    url = frente.url if frente else base_url
    ctx = browser.new_context(base_url=url, locale="pt-BR", viewport={"width": 1280, "height": 800})
    return frente, ctx, url


def test_selecao_em_massa_move_50_para_pasta(
    browser, base_url, credenciais_demo, admin_api, api_catalogo, env, medida
):
    """cláusula do portão: 'seleção em massa de 50 itens move para pasta'."""
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    ids = []
    r = admin_api.post("/api/pastas", data={"nome": f"E2E lote destino {s}"})
    assert r.status == 201, r.text()
    pasta_id = r.json()["id"]
    try:
        for i in range(50):
            r = admin_api.post("/api/itens", data={"tipo": "mapa", "titulo": f"E2E lote {s} {i:03d}"})
            assert r.status == 201, r.text()
            ids.append(r.json()["id"])
        frente, ctx, url = _contexto(browser, base_url, env)
        with frente or contextlib.nullcontext():
            page = ctx.new_page()
            tela = TelaCatalogo(page, url)
            try:
                tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")
                tela.ir("/conteudo")
                page.fill("#busca input", f"titulo:{s}")
                page.press("#busca input", "Enter")
                page.wait_for_function(
                    "() => document.querySelectorAll('#lista [data-id]').length === 50", timeout=15000)
                todos = page.locator("table.tabela thead input[type='checkbox']")
                todos.check()
                page.wait_for_selector("#lote:not([hidden]) #lote-contagem", timeout=10000)
                assert "50" in page.text_content("#lote-contagem")
                tela.capturar("selecao_massa")
                page.click("#lote-mover")
                d = page.locator("plat-dialogo dialog[open]").last
                d.locator("select[name='pasta_id']").select_option(pasta_id)
                d.locator("button[type='submit']").click()
                page.wait_for_selector("#aviso[data-tipo='ok']", timeout=20000)
                page.wait_for_function(
                    "() => !document.querySelector('#lote') || document.querySelector('#lote').hidden",
                    timeout=15000)
                tela.verificar()
            finally:
                ctx.close()
        r = admin_api.get(f"/api/itens?pasta_id={pasta_id}&limite=100")
        assert r.status == 200, r.text()
        corpo = r.json()
        movidos = {it["id"] for it in corpo["itens"]}
        assert corpo["total"] == 50 and movidos == set(ids), (corpo["total"], len(movidos & set(ids)))
        gravar = medida(ITEM)
        gravar(
            "selecao_massa_itens", 50, "itens",
            "playwright: marcar todos + lote-mover (tests/e2e/test_conteudo_lote_filtros.py)",
        )
    finally:
        for iid in ids:
            admin_api.delete(f"/api/itens/{iid}")
            admin_api.post("/api/lixeira/esvaziar", data={"ids": [iid]})
        admin_api.delete(f"/api/pastas/{pasta_id}")


def test_filtros_combinam_tipo_tag_data_igual_a_api(
    browser, base_url, credenciais_demo, admin_api, api_catalogo, env, medida
):
    """cláusula do portão: 'filtros combinam (tipo+tag+data) com resultado igual ao da API'."""
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tag_alvo = f"e2ecombo{s}"
    ids = {}
    try:
        r = admin_api.post("/api/itens", data={"tipo": "mapa", "titulo": f"E2E combo alvo {s}", "tags": [tag_alvo]})
        assert r.status == 201, r.text()
        ids["alvo"] = r.json()["id"]
        dados_camada = {
            "schema": "plat_trabalho", "tabela": "zt_inexistente", "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
        }
        r = admin_api.post("/api/itens", data={
            "tipo": "camada_vetorial", "titulo": f"E2E combo tipo errado {s}",
            "tags": [tag_alvo], "dados": dados_camada,
        })
        assert r.status == 201, r.text()
        ids["tipo_errado"] = r.json()["id"]
        r = admin_api.post(
            "/api/itens", data={"tipo": "mapa", "titulo": f"E2E combo tag errada {s}", "tags": [f"outra{s}"]}
        )
        assert r.status == 201, r.text()
        ids["tag_errada"] = r.json()["id"]

        hoje = time.strftime("%Y-%m-%d")
        amanha = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 86400))

        # a API é a régua: mesma tríade de parâmetros que a tela vai montar
        r = admin_api.get(f"/api/itens?tipo=mapa&tags={tag_alvo}&criado_de={hoje}&limite=100")
        assert r.status == 200, r.text()
        esperado_hoje = {it["id"] for it in r.json()["itens"]}
        assert esperado_hoje == {ids["alvo"]}, (esperado_hoje, ids)
        r = admin_api.get(f"/api/itens?tipo=mapa&tags={tag_alvo}&criado_de={amanha}&limite=100")
        assert r.status == 200, r.text()
        assert r.json()["total"] == 0, r.json()  # criado_de no futuro exclui tudo: prova que a data realmente filtra

        frente, ctx, url = _contexto(browser, base_url, env)
        with frente or contextlib.nullcontext():
            page = ctx.new_page()
            tela = TelaCatalogo(page, url)
            try:
                tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")
                tela.ir("/conteudo")
                page.fill("#busca input", f"tag:{tag_alvo}")
                page.press("#busca input", "Enter")
                page.wait_for_function(
                    "() => document.querySelectorAll('#lista [data-id]').length === 2", timeout=15000)
                if not page.locator("#coluna-filtros[open]").count():
                    page.click("#coluna-filtros summary")
                page.wait_for_selector("#filtros section.faceta input[type=checkbox][value='mapa']", timeout=15000)
                page.locator("#filtros section.faceta input[type=checkbox][value='mapa']").check()
                page.wait_for_function(
                    "() => document.querySelectorAll('#lista [data-id]').length === 1", timeout=15000)
                assert page.locator(f"#lista [data-id='{ids['alvo']}']").count() == 1
                assert page.locator(f"#lista [data-id='{ids['tipo_errado']}']").count() == 0
                tela.capturar("filtros_combinados")
                criado_de = page.locator("#filtros section.faceta[aria-label] input[type='date']").first
                criado_de.fill(amanha)
                criado_de.dispatch_event("change")
                page.wait_for_selector("#lista .vazio", timeout=15000)
                assert page.locator("#lista [data-id]").count() == 0
                tela.verificar()
            finally:
                ctx.close()
        gravar = medida(ITEM)
        gravar("filtros_combinados_resultado_uds", 1, "itens",
               "tipo=mapa AND tag AND criado_de na tela == GET /api/itens com os mesmos parâmetros "
               "(tests/e2e/test_conteudo_lote_filtros.py)")
    finally:
        for iid in ids.values():
            admin_api.delete(f"/api/itens/{iid}")
            admin_api.post("/api/lixeira/esvaziar", data={"ids": [iid]})


def test_pagina_conteudo_com_10_mil_itens(
    browser, base_url, credenciais_demo, admin_api, api_catalogo, env, conexao_plat_app, medida
):
    """cláusula do portão: 'lista de 10 mil itens pagina em ≤ 1,5 s de primeira pintura medida (pagina_conteudo_ms)'.
    Insere 10.000 itens direto no banco (rápido; a API faz 1 INSERT por chamada e levaria minutos) no MESMO
    inquilino/dono do admin de demo, mede uma navegação fresca para /conteudo e apaga tudo ao final."""
    from tests.api.test_rls import contexto

    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    marcador = f"e2e10k{s}"
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, %s)", (slug, admin_login))
        r = cur.fetchone()
        assert r is not None, f"admin de {slug} não semeado"
        dono_id, tenant_id = r["usuario_id"], r["tenant_id"]
    try:
        with conexao_plat_app.cursor() as cur:
            contexto(conexao_plat_app, tenant_id, usuario_id=dono_id, login=admin_login)
            cur.execute(
                "INSERT INTO plat.item (tenant_id, tipo, titulo, tags, dono_id, dados) "
                "SELECT %s, 'mapa', 'E2E 10k ' || %s || ' ' || g, ARRAY[%s]::text[], %s, '{}'::jsonb "
                "FROM generate_series(1, 10000) AS g",
                (tenant_id, s, marcador, dono_id),
            )
            cur.execute("SELECT count(*) AS n FROM plat.item WHERE %s = ANY(tags)", (marcador,))
            n = cur.fetchone()["n"]
        conexao_plat_app.commit()
        assert n == 10000, n

        frente, ctx, url = _contexto(browser, base_url, env)
        with frente or contextlib.nullcontext():
            page = ctx.new_page()
            tela = TelaCatalogo(page, url)
            try:
                tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")
                ms = tela.ir("/conteudo")
                total = page.evaluate("() => document.querySelector('#contagem')?.textContent || ''")
                tela.capturar("dez_mil")
                tela.verificar()
            finally:
                ctx.close()
        gravar = medida(ITEM)
        gravar(
            "pagina_conteudo_ms", ms, "ms",
            "goto /conteudo ate body[data-pronto=1], inquilino com 10.000 itens "
            "(tests/e2e/test_conteudo_lote_filtros.py)",
        )
        gravar("pagina_conteudo_itens_no_inquilino", 10000, "itens", "generate_series direto em plat.item")
        assert ms <= 1500, (ms, total)
    finally:
        # lixeira (RLS normal) + expurgo físico (plat.item_expurgar, SECURITY DEFINER) num único DO server-side:
        # 10.000 chamadas de função pela rede seriam lentas; um laço dentro do próprio servidor não é.
        conexao_plat_app.rollback()
        with conexao_plat_app.cursor() as cur:
            contexto(conexao_plat_app, tenant_id, usuario_id=dono_id, login=admin_login)
            cur.execute("SET LOCAL statement_timeout = '60s'")
            cur.execute(
                "UPDATE plat.item SET apagado_em = now(), apagado_por = %s "
                "WHERE tenant_id = %s AND %s = ANY(tags) AND apagado_em IS NULL",
                (dono_id, tenant_id, marcador),
            )
            cur.execute(
                "DO $$ DECLARE r uuid; BEGIN "
                "FOR r IN SELECT id FROM plat.item WHERE tenant_id = %(t)s AND %(m)s = ANY(tags) LOOP "
                "PERFORM plat.item_expurgar(r); END LOOP; END $$;",
                {"t": tenant_id, "m": marcador},
            )
            cur.execute("SELECT count(*) AS n FROM plat.item WHERE tenant_id = %s AND %s = ANY(tags)",
                        (tenant_id, marcador))
            restam = cur.fetchone()["n"]
        conexao_plat_app.commit()
        assert restam == 0, f"{restam} dos 10.000 itens de teste sobraram no banco"
