"""e2e do ciclo de vida do item de imagem (L1-01-i): a exclusão PELO NAVEGADOR com o tempo do 404 do tile
medido dentro do navegador (cláusula do portão, literal: "excluir item pelo navegador: tiles respondem 404
em <= 5 s"). O resto do ciclo (STAC sai e volta, retenção de 7 dias, job de apagar objetos, coleta de lixo
pela CLI, cota recalculada, refutação dos 3 itens) é provado em tests/api/imagens/test_ciclo_vida.py; aqui
o que se prova é a EXPERIÊNCIA: o admin apaga uma imagem de verdade pela tela, o tile morre na hora, o item
aparece na lixeira, volta pela lixeira e o "Apagar agora" expurga objeto + STAC + espelho de uma vez.
0 erro de console; captura da lixeira; medida e2e_tile_404_ms."""

import json
import secrets
import uuid
from pathlib import Path

import pytest

from app.settings import settings
from tests.e2e.apoio import Tela

ITEM = "L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo"
RAIZ = Path(__file__).resolve().parents[2]
RAIZ_WEB = RAIZ / "web"
COLECAO_SLUG = "imagens"
ROTAS_CICLO = ("/api/itens", "/api/lixeira", "/api/imagens/{item_id}")
LIMITE_TILE_MS = 5000.0

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def api_ciclo(api_auth):
    faltam = [r for r in ROTAS_CICLO if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (rotas de imagem/ciclo de vida)")
    return api_auth


def _servir_estaticos(page):
    """a app não serve /static/ sozinha (nginx faz isso em produção); contra o uvicorn puro o teste
    cumpre o papel do nginx servindo web/ do próprio worktree."""
    def cumprir(rota):
        rel = rota.request.url.split("/static/", 1)[1].split("?")[0]
        caminho = RAIZ_WEB / rel
        if caminho.is_file():
            rota.fulfill(path=str(caminho))
        else:
            rota.fulfill(status=404, body="")
    page.route("**/static/**", cumprir)


def _reescrer_origem(page):
    """CSRF do ADR 0002 5.3: escrita sob cookie exige Origin == PLAT_URL_PUBLICA (a URL de produção que
    o nginx publica; o navegador aqui navega por http://127.0.0.1, então o próprio pedido do navegador
    leva a origem errada). O teste reemite a escrita com a origem certa — é a MESMA verificação que o
    nginx força em produção, cumprida no pedido reemitido."""
    def reemitir(rota):
        if rota.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            cabecalhos = {**rota.request.headers, "origin": settings.PLAT_URL_PUBLICA}
            rota.fulfill(response=rota.fetch(headers=cabecalhos))
        else:
            rota.continue_()
    page.route("**/api/**", reemitir)


def _limpar_aviso(page, seletor="#aviso"):
    page.evaluate(f"() => document.querySelector('{seletor}')?.limpar()")


def _ids_demo(conexao_plat_app, slug, login):
    """(tenant_id, admin_id) do inquilino demo, pela função SECURITY DEFINER `plat.auth_login` (a única
    leitura que cruza inquilinos) — os MESMOS credenciais com que o navegador entra."""
    from tests.api.test_rls import contexto

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, %s)", (slug, login))
        linha = cur.fetchone()
        assert linha is not None, f"admin {login} do inquilino {slug} não semeado (rode install.sh)"
        tenant_id, admin_id = linha["tenant_id"], linha["usuario_id"]
    contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
    return tenant_id, admin_id


def _criar_item_raster(conexao_plat_app, tenant_id, admin_id):
    """Um item de imagem completo (objeto no balde + item STAC + espelho + plat.item) SEM o job de
    conversão — mesma receita de tests/api/imagens/test_ciclo_vida.py, no inquilino demo: o ciclo de
    vida toca chaves e registros, não o conteúdo do TIFF."""
    from app import objetos, objetos_raster
    from app.catalogo import tipos as tipos_item
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri
    from tests.api.imagens.conftest import item_stac
    from tests.api.test_rls import contexto

    stac_id = f"zte2elixeira{secrets.token_hex(4)}"
    contexto(conexao_plat_app, tenant_id, usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        objetos.garantir_bucket(cur, tenant_id, "demo")
        o_vis = objetos_raster.guardar_bytes(
            cur, stac_id, "visual",
            f"conteudo do COG visual do e2e de ciclo de vida: {secrets.token_hex(8)}".encode(),
        )
        colecao = ps.nome_colecao(tenant_id, COLECAO_SLUG)
        criada = ps.colecao_obter(cur, tenant_id, colecao) is None
        if criada:
            ps.colecao_criar(cur, tenant_id, COLECAO_SLUG, {"title": "imagens do e2e de ciclo de vida"})
        stac = item_stac(stac_id, colecao)
        stac["assets"] = {
            "visual": {
                "href": f"/api/objetos/{o_vis['chave']}",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "file:checksum": f"1220{o_vis['sha256']}",
                "file:size": o_vis["bytes"],
            },
        }
        ps.item_criar(cur, tenant_id, colecao, stac)
        ri.espelhar(cur, tenant_id, colecao, stac_id, {
            "sha256": o_vis["sha256"], "perfil": "visual", "bytes": o_vis["bytes"], "estado": "ativo",
        })
        dados = {
            "colecao": colecao, "stac_id": stac_id, "perfil": "visual", "origem": "copiado",
            "srid_nativo": 4326, "guardar_original": False, "bandas": [{"nome": "banda_1"}],
        }
        tipos_item.validar("raster", dados)
        titulo = f"Imagem e2e ciclo de vida {stac_id[-6:]}"
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), tenant_id, titulo, admin_id, jsonb(dados),
             o_vis["bytes"], admin_id, admin_id),
        )
        cur.execute("SELECT id FROM plat.item WHERE dados->>'stac_id' = %s", (stac_id,))
        plat_id = str(cur.fetchone()["id"])
    conexao_plat_app.commit()
    return {"id": plat_id, "stac_id": stac_id, "titulo": titulo, "chave": o_vis["chave"],
            "colecao": colecao, "colecao_criada": criada}


def _limpar(conexao_plat_app, tenant_id, item_id, stac_id, colecao, colecao_criada):
    """Jobs deixados pelo ciclo (o de apagar objetos agendado pela exclusão e os de expurgo que o
    'Apagar agora'/limpeza enfileiraram para ESTE item) e, se o teste criou, a coleção STAC vazia."""
    from tests.api.test_rls import contexto

    contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "DELETE FROM plat.job WHERE tipo = 'imagens.raster_apagar_objetos' "
            "AND parametros->>'item_id' = %s",
            (stac_id,),
        )
        cur.execute(
            "DELETE FROM plat.job WHERE tipo = 'catalogo.lixeira_expurgar' AND estado = 'pendente' "
            "AND parametros->'ids' ? %s",
            (item_id,),
        )
        if colecao_criada:
            cur.execute("SELECT pgstac.delete_collection(%s)", (colecao,))
    conexao_plat_app.commit()


class _CtxJobExpurgo:
    """O mínimo da interface de ContextoJob que `catalogo_lixeira_expurgar` usa, para rodar o CORPO do
    job no processo do teste: o `esvaziar` da tela enfileira o job (o aviso 'ok' da tela prova o
    enfileiramento), e o corpo é o MESMO código que o worker roda — sem depender de um worker externo
    decidir quando consumir a fila da trilha."""

    def __init__(self, tenant_id: int):
        from app import db as mod_db

        self._ctx = mod_db.Contexto(tenant_id, 0, "teste")
        self.job_id = None  # sem job de verdade: o corpo só o usa no detalhe do evento (str(None) = 'None')

    def db(self):
        from app import db as mod_db

        return mod_db.db(self._ctx)

    def log(self, nivel: str, mensagem: str) -> None:  # noqa: ARG002 — o e2e não publica log de job
        pass

    def progresso(self, pct: int, mensagem: str = "") -> None:  # noqa: ARG002 — idem progresso
        pass


def test_ciclo_de_vida_no_navegador(page, base_url, credenciais_demo, admin_api, api_ciclo,
                                    conexao_plat_app, medida):
    """Excluir a imagem pelo menu do painel, medir o 404 do tile DENTRO do navegador, restaurar pela
    lixeira e expurgar com "Apagar agora" (o destruidor do tipo raster apaga objeto + STAC + espelho)."""
    slug, login, senha = credenciais_demo
    tenant_id, admin_id = _ids_demo(conexao_plat_app, slug, login)
    criado = _criar_item_raster(conexao_plat_app, tenant_id, admin_id)
    item_id, stac_id, titulo = criado["id"], criado["stac_id"], criado["titulo"]
    expurgado = False
    tela = Tela(page, base_url)
    _servir_estaticos(page)
    _reescrer_origem(page)
    tela.esperar_status(404)  # o tile do item apagado (a resposta esperada do fluxo)
    try:
        tela.entrar(slug, login, senha, proximo="/conteudo")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=20000)

        # exclusão pelo menu do painel: ⋯ → Apagar → confirmação → aviso ok
        page.locator(f"#lista tr[data-id='{item_id}'] .titulo-item").click()
        page.wait_for_selector("#painel dialog[open] #item-mais", timeout=20000)
        tela.capturar("painel")
        page.click("#item-mais")
        page.click("#item-apagar")
        page.wait_for_selector("#painel-editar dialog[open] .dialogo-botoes button", timeout=15000)
        page.locator("#painel-editar dialog[open] .dialogo-botoes button", has_text="Apagar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)

        # cláusula do portão: o tile responde 404 em <= 5 s, medido pelo relógio do NAVEGADOR
        medicao = page.evaluate(
            """async (u) => { const t0 = performance.now(); const r = await fetch(u);
               return { status: r.status, ms: performance.now() - t0 }; }""",
            f"{base_url}/api/imagens/{item_id}/tiles/3/2/1.png",
        )
        assert medicao["status"] == 404, medicao
        assert 0 <= medicao["ms"] < LIMITE_TILE_MS, (
            f"tile levou {medicao['ms']:.0f} ms para dar 404 (portão: <= {LIMITE_TILE_MS:.0f} ms)"
        )
        gravar = medida(ITEM)
        gravar("e2e_tile_404_ms", round(medicao["ms"], 1), "ms",
               "PLAT_GRAVAR_MEDIDAS=1 bash laco/roda_teste.sh tests/e2e/test_ciclo_vida.py "
               "--base-url http://127.0.0.1:<porta>")

        # a lixeira tem o item e a restauração devolve o item inteiro (o tile volta a existir como rota)
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({json.dumps(titulo)})", timeout=15000)
        assert page.locator("#lixeira-tabela tbody tr", has_text=titulo).count() == 1
        tela.capturar("lixeira")
        _limpar_aviso(page, "#aviso")
        page.locator("#lixeira-tabela tbody tr", has_text=titulo).locator(
            "button", has_text="Restaurar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        ver = tela.api("GET", f"/api/imagens/{item_id}")
        assert ver.status == 200, (ver.status, ver.text())
        assert ver.json()["stac_id"] == stac_id, ver.json()

        # apaga de novo e expurga pela lixeira: objeto, STAC e espelho saem de uma vez
        assert tela.api("DELETE", f"/api/itens/{item_id}").status == 204
        page.click("#aba-meus")
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({json.dumps(titulo)})", timeout=15000)
        linha_lix = page.locator("#lixeira-tabela tbody tr", has_text=titulo)
        _limpar_aviso(page, "#aviso")
        linha_lix.locator("button", has_text="Apagar agora").click()
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button", has_text="Apagar agora").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        expurgado = True
        assert tela.api("GET", f"/api/imagens/{item_id}").status == 404

        # o "Apagar agora" enfileira o job de expurgo (202): rodar o CORPO do job (o mesmo código do
        # worker) e conferir que o destruidor do tipo raster apaga objeto + STAC + espelho de uma vez
        from app.catalogo.tarefas import catalogo_lixeira_expurgar

        resultado = catalogo_lixeira_expurgar(_CtxJobExpurgo(tenant_id), dias=0, ids=[uuid.UUID(item_id)])
        assert resultado["expurgados"] == 1, resultado
        from app import objetos_raster
        from app.imagens import pgstac as ps
        from tests.api.test_rls import contexto

        contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT 1 FROM plat.raster_item WHERE item_id = %s", (stac_id,))
            assert cur.fetchone() is None, "espelho do item sobreviveu ao expurgo"
            assert ps.item_obter(cur, tenant_id, criado["colecao"], stac_id) is None
        assert objetos_raster.existe(criado["chave"]) is False, "objeto do balde sobreviveu ao expurgo"
        tela.verificar()
    finally:
        if not expurgado:
            admin_api.delete(f"/api/itens/{item_id}")
            admin_api.post("/api/lixeira/esvaziar", data={"ids": [item_id]})
        _limpar(conexao_plat_app, tenant_id, item_id, stac_id, criado["colecao"], criado["colecao_criada"])
