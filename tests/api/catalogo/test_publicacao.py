"""Publicação de documento de construtor (item L5-14-publicacao-links-embed; portão de pronto, cláusula a
cláusula): (1) app publicado abre anônimo por link-com-token e nega após revogação; (2) rascunho alterado
não muda o publicado até novo publish; (3) `frame-ancestors` só permite os domínios cadastrados (cabeçalho
aqui; o carregamento cross-origin de verdade é `tests/e2e/test_publicacao_embed.py`); (4) exportação
estática (conteúdo aqui; abrir por `file://` é o e2e); (5) o token da publicação lê SÓ as camadas listadas
(escopo computado, e rejeição de rota de escrita/rota fora do escopo por HTTP real); (6) contagem de
visualização por dia."""

import secrets
import time

from app.catalogo.documento import gerar_ulid
from tests.api.conftest import com_token, novo_cliente

ITEM = "L5-14-publicacao-links-embed"


def _slug() -> str:
    return f"zt-pub-{secrets.token_hex(4)}"


def _montar_app(itens_a, sessao_a):
    """camada -> mapa (cita a camada) -> app (cita o mapa): a mesma cadeia que
    `app/catalogo/publicacao.py::camadas_citadas` percorre."""
    camada = itens_a.criar("camada_vetorial", sessao=sessao_a)
    mapa = itens_a.criar("mapa", sessao=sessao_a, dados={"esquema_versao": 1, "corpo": {"camadas": [camada["id"]]}})
    no_id = gerar_ulid()
    corpo_app = {"nos": [{"id": no_id, "tipo": "visor_mapa"}], "mapas": [mapa["id"]]}
    app = itens_a.criar(
        "app", sessao=sessao_a, dados={"tipo": "app", "esquema_versao": 2, "corpo": corpo_app}
    )
    return camada, mapa, app


def test_publicar_camadas_citadas_e_slug_em_uso(sessao_a, itens_a):
    camada, mapa, app = _montar_app(itens_a, sessao_a)
    slug = _slug()
    r = sessao_a.post(f"/api/itens/{app['id']}/publicacao", json={"slug": slug, "dominios_permitidos": ["https://a.exemplo.org"]})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["slug"] == slug and j["camadas_citadas"] == [camada["id"]]
    assert j["url"].endswith(f"/p/demo/{slug}")
    # outro item não publica no mesmo slug
    _, _, app2 = _montar_app(itens_a, sessao_a)
    r2 = sessao_a.post(f"/api/itens/{app2['id']}/publicacao", json={"slug": slug})
    assert r2.status_code == 409 and r2.json()["erro"] == "slug_em_uso", r2.text
    # tipo não publicável (mapa não é app/painel)
    r3 = sessao_a.post(f"/api/itens/{mapa['id']}/publicacao", json={"slug": _slug()})
    assert r3.status_code == 422 and r3.json()["erro"] == "tipo_nao_publicavel", r3.text


def test_acesso_anonimo_por_link_e_nega_apos_revogacao(sessao_a, itens_a, medida):
    _, _, app = _montar_app(itens_a, sessao_a)
    iid = app["id"]
    slug = _slug()
    assert sessao_a.post(f"/api/itens/{iid}/publicacao", json={"slug": slug}).status_code == 201
    rl = sessao_a.post(f"/api/itens/{iid}/links", json={"nome": "zt publicacao"})
    assert rl.status_code == 201, rl.text
    tok = rl.json()["token"]
    lid = rl.json()["id"]
    anon = novo_cliente()
    # sem link: 401 (o item não é público)
    r_sem = anon.get(f"/api/p/demo/{slug}")
    assert r_sem.status_code == 401, r_sem.text
    # com link: 200, conteúdo do documento
    r = anon.get(f"/api/p/demo/{slug}?link={tok}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["item_id"] == iid and corpo["titulo"] == app["titulo"] and corpo["versao_publicada"] == 1
    assert len(corpo["corpo"]["corpo"]["nos"]) == 1
    assert isinstance(corpo["token"], str) and len(corpo["token"]) > 10
    # link de outro item não serve para este slug
    _, _, app_outro = _montar_app(itens_a, sessao_a)
    rl2 = sessao_a.post(f"/api/itens/{app_outro['id']}/links", json={})
    tok_outro = rl2.json()["token"]
    r_cruzado = anon.get(f"/api/p/demo/{slug}?link={tok_outro}")
    assert r_cruzado.status_code == 403, r_cruzado.text
    # revogar: nega (401/403), nunca 200
    t0 = time.perf_counter()
    assert sessao_a.delete(f"/api/itens/{iid}/links/{lid}").status_code == 204
    r_revogado = anon.get(f"/api/p/demo/{slug}?link={tok}")
    dt_ms = round((time.perf_counter() - t0) * 1000, 1)
    assert r_revogado.status_code in (401, 403), r_revogado.text
    medida(ITEM)(
        "revogacao_nega_ms", dt_ms, "ms", "DELETE link + GET /api/p/<inquilino>/<slug>?link=<token> -> 401/403"
    )
    # publicação inexistente: 404
    assert anon.get("/api/p/demo/zt-nao-existe-nunca").status_code == 404
    assert anon.get(f"/api/p/demo-inexistente/{slug}").status_code == 404


def test_rascunho_nao_muda_publicado_ate_novo_publish(sessao_a, itens_a):
    _, _, app = _montar_app(itens_a, sessao_a)
    iid = app["id"]
    slug = _slug()
    assert sessao_a.post(f"/api/itens/{iid}/publicacao", json={"slug": slug}).status_code == 201
    tok = sessao_a.post(f"/api/itens/{iid}/links", json={}).json()["token"]
    anon = novo_cliente()
    original = anon.get(f"/api/p/demo/{slug}?link={tok}").json()
    assert original["versao_publicada"] == 1
    # edita o rascunho (novo nó, novo título) -> versao_atual sobe, versao_publicada não muda
    nos_novos = [{"id": gerar_ulid(), "tipo": "visor_mapa"}, {"id": gerar_ulid(), "tipo": "visor_mapa"}]
    novo_corpo = {"nos": nos_novos, "mapas": []}
    r_edita = sessao_a.put(
        f"/api/itens/{iid}",
        json={"titulo": "zt titulo editado", "dados": {"tipo": "app", "esquema_versao": 2, "corpo": novo_corpo}},
    )
    assert r_edita.status_code == 200 and r_edita.json()["versao_atual"] == 2, r_edita.text
    assert r_edita.json()["versao_publicada"] == 1
    ainda_original = anon.get(f"/api/p/demo/{slug}?link={tok}").json()
    assert ainda_original["titulo"] == original["titulo"] and len(ainda_original["corpo"]["corpo"]["nos"]) == 1
    # republica (sem passar versao => versao_atual = 2): agora sim muda
    r_pub2 = sessao_a.post(f"/api/itens/{iid}/publicacao", json={"slug": slug})
    assert r_pub2.status_code == 201, r_pub2.text
    depois = anon.get(f"/api/p/demo/{slug}?link={tok}").json()
    assert depois["titulo"] == "zt titulo editado" and depois["versao_publicada"] == 2
    assert len(depois["corpo"]["corpo"]["nos"]) == 2


def test_token_do_app_escopo_e_rotas_negadas(sessao_a, itens_a, conexao_plat_app):
    camada_citada, mapa, app = _montar_app(itens_a, sessao_a)
    camada_fora = itens_a.criar("camada_vetorial", sessao=sessao_a)
    slug = _slug()
    r = sessao_a.post(f"/api/itens/{app['id']}/publicacao", json={"slug": slug})
    assert r.status_code == 201
    tok = sessao_a.post(f"/api/itens/{app['id']}/links", json={}).json()["token"]
    anon = novo_cliente()
    doc = anon.get(f"/api/p/demo/{slug}?link={tok}").json()
    token_app = doc["token"]
    # o escopo gravado no banco é EXATAMENTE a camada citada, nunca a outra (RLS exige contexto de sessão
    # nesta conexão crua — o mesmo `contexto()` que `tests/api/test_rls.py` usa para varredura direta)
    from tests.api.test_rls import contexto, ids_por_slug

    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin_id = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, tenant_id, usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT k.escopos, k.restricao FROM plat.item_publicacao p JOIN plat.token_servico k ON k.id = p.token_id "
            "WHERE p.item_id = %s::uuid",
            (app["id"],),
        )
        linha = cur.fetchone()
    escopos = set(linha["escopos"])
    assert escopos == {f"camada:ler:{camada_citada['id']}", f"tiles:ler:{camada_citada['id']}"}, escopos
    assert f"camada:ler:{camada_fora['id']}" not in escopos
    # o token do app NUNCA escreve (falta admin:inquilino, escopo padrão das rotas de escrita)
    r_escrita = com_token(novo_cliente(), token_app, "PUT", f"/api/itens/{app['id']}", json={"titulo": "invadido"})
    assert r_escrita.status_code == 403, r_escrita.text
    assert r_escrita.json()["erro"] == "escopo_insuficiente"
    # o token do app não lê item de catálogo fora do mecanismo escopado (falta catalogo:ler) — na ausência,
    # nesta árvore, de uma rota de camada/tiles já ligada a `camada:ler`/`tiles:ler` (item L1-02-tiles-token
    # está numa branch ainda não integrada aqui: commit 4c7f315, não presente neste worktree), esta é a prova
    # de ponta a ponta disponível de que o token não tem alcance nenhum fora do que foi listado.
    r_leitura_fora = com_token(novo_cliente(), token_app, "GET", f"/api/itens/{camada_fora['id']}")
    assert r_leitura_fora.status_code == 403, r_leitura_fora.text
    assert r_leitura_fora.json()["erro"] == "escopo_insuficiente"
    # despublicar revoga o token e derruba a página
    assert sessao_a.delete(f"/api/itens/{app['id']}/publicacao").status_code == 204
    r_pos_despublicar = anon.get(f"/api/p/demo/{slug}?link={tok}")
    assert r_pos_despublicar.status_code == 404, r_pos_despublicar.text


def test_visualizacao_contada_por_dia(sessao_a, itens_a):
    _, _, app = _montar_app(itens_a, sessao_a)
    iid = app["id"]
    slug = _slug()
    assert sessao_a.post(f"/api/itens/{iid}/publicacao", json={"slug": slug}).status_code == 201
    tok = sessao_a.post(f"/api/itens/{iid}/links", json={}).json()["token"]
    anon = novo_cliente()
    n = 4
    for _ in range(n):
        assert anon.get(f"/api/p/demo/{slug}?link={tok}").status_code == 200
    r = sessao_a.get(f"/api/itens/{iid}/publicacao/visualizacoes")
    assert r.status_code == 200, r.text
    linhas = r.json()
    assert linhas and linhas[0]["visualizacoes"] == n, linhas


def test_exportacao_estatica_e_conteudo(sessao_a, itens_a):
    _, _, app = _montar_app(itens_a, sessao_a)
    iid = app["id"]
    slug = _slug()
    # exportar antes de publicar: 422
    r_cedo = sessao_a.get(f"/api/itens/{iid}/publicacao/exportacao")
    assert r_cedo.status_code == 422 and r_cedo.json()["erro"] == "nao_publicado"
    assert sessao_a.post(f"/api/itens/{iid}/publicacao", json={"slug": slug}).status_code == 201
    r = sessao_a.get(f"/api/itens/{iid}/publicacao/exportacao")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert app["titulo"] in html
    assert "nós do documento (1)" in html
    assert '<script type="application/json" id="dados-publicados">' in html
    assert "</scr" not in html.split('id="dados-publicados">', 1)[1].split("</script>", 1)[0]


def test_frame_ancestors_por_dominios(sessao_a, itens_a):
    _, _, app = _montar_app(itens_a, sessao_a)
    slug = _slug()
    r = sessao_a.post(
        f"/api/itens/{app['id']}/publicacao", json={"slug": slug, "dominios_permitidos": ["https://parceiro.exemplo.org"]}
    )
    assert r.status_code == 201
    anon = novo_cliente()
    pagina = anon.get(f"/p/demo/{slug}")
    assert pagina.status_code == 200
    csp = pagina.headers.get("content-security-policy", "")
    assert "frame-ancestors" in csp and "https://parceiro.exemplo.org" in csp and "'self'" in csp
    assert "x-frame-options" not in {k.lower() for k in pagina.headers}
    assert anon.get("/p/demo/zt-slug-que-nao-existe").status_code == 404
