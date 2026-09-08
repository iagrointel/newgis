"""Site do inquilino (item L5-20-sites-paginas-publicas; portão de pronto, cláusula a cláusula):

1. site com 3 páginas e os 9 cartões publicado em `/s/<inquilino>/`;
2. o HTML servido, SEM navegador e SEM JavaScript, já contém o texto de cada cartão (a resposta é lida como
   texto cru, do mesmo jeito que `curl` a leria — e o teste confere que não há `<script>` na página);
3. a galeria e a busca listam SÓ item compartilhado com 'todos' (o adversário procura o item privado por
   tipo e por busca do título exato, e o cartão que cita um item privado por uuid não mostra o item);
4. `noindex` por padrão e `index` só com a opção explícita;
5. as regras de montagem recusam documento torto (422 `site_invalido`).

Roda num inquilino temporário com `compartilhar_publico` ligado: o site é por inquilino, e ligar essa
configuração nos inquilinos de demonstração mudaria o resultado de outros testes que rodam ao mesmo tempo.
"""

import re
import secrets

import pytest

from app.catalogo.documento import gerar_ulid
from tests.api.conftest import InquilinoTemporario, novo_cliente

ITEM = "L5-20-sites-paginas-publicas"
CARTOES = ["texto", "imagem", "galeria", "mapa", "aplicativo", "busca", "chamada", "estatisticas", "incorporado"]


@pytest.fixture
def inquilino_publico(sessao_plat):
    """Inquilino temporário que PERMITE compartilhamento público (sem isso, nada é 'compartilhado com todos')."""
    inq = InquilinoTemporario(sessao_plat, config={"auth": {"compartilhar_publico": True}})
    yield inq
    inq.apagar()


def _no(tipo: str, pai=None, **props) -> dict:
    return {"id": gerar_ulid(), "tipo": tipo, "pai": pai, "propriedades": props}


def _publicar_app(admin) -> tuple[dict, str]:
    """App público E publicado em /p/<inquilino>/<slug>: é o que o cartão de mapa incorpora."""
    r = admin.post("/api/itens", json={
        "tipo": "app", "titulo": "Mapa da rede de teste",
        "dados": {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [{"id": gerar_ulid(), "tipo": "visor_mapa"}]}},
    })
    assert r.status_code == 201, r.text
    app = r.json()
    slug = f"zt-app-{secrets.token_hex(3)}"
    assert admin.post(f"/api/itens/{app['id']}/publicacao", json={"slug": slug}).status_code == 201
    assert admin.put(f"/api/itens/{app['id']}/compartilhamento", json={"acesso": "publico"}).status_code == 200
    return app, slug


def _documento(app_id: str) -> dict:
    """3 páginas; a primeira com texto/imagem/chamada/estatísticas, a segunda com galeria/busca, a terceira
    com mapa/aplicativo/incorporado — os nove cartões do vocabulário."""
    inicio = _no("pagina", titulo="Início", caminho="inicio", inicial=True, ordem=0)
    dados = _no("pagina", titulo="Dados abertos", caminho="dados", ordem=1)
    mapas = _no("pagina", titulo="Mapas e aplicativos", caminho="mapas", ordem=2)
    s1 = _no("secao", pai=inicio["id"], rotulo="Quem somos")
    s2 = _no("secao", pai=dados["id"], rotulo="Catálogo aberto")
    s3 = _no("secao", pai=mapas["id"], rotulo="Ver no mapa")
    return {
        "tipo": "site", "esquema_versao": 1,
        "corpo": {
            "ligacoes": [],
            "nos": [
                _no("cabecalho", titulo="Portal de dados do inquilino de teste", subtitulo="Serviço de teste interno"),
                _no("menu", rotulo="menu do site"),
                _no("rodape", texto="Rodapé com contato do serviço de teste interno."),
                inicio, dados, mapas, s1, s2, s3,
                _no("texto", pai=s1["id"], titulo="O que fazemos",
                    texto="Primeiro parágrafo do cartão de texto.\n\nSegundo parágrafo do cartão de texto."),
                _no("imagem", pai=s1["id"], url="/static/favicon.svg", alternativo="Marca do serviço de teste",
                    legenda="Legenda da imagem do cartão."),
                _no("chamada", pai=s1["id"], titulo="Fale com a equipe", texto="Texto da chamada com botão.",
                    rotulo_botao="Abrir o catálogo", destino="/s/exemplo-interno/dados"),
                _no("estatisticas", pai=s1["id"], titulo="Nossos números"),
                _no("galeria", pai=s2["id"], titulo="Conteúdo publicado", limite=20, mostrar_filtro=True),
                _no("busca", pai=s2["id"], titulo="Buscar no catálogo", rotulo_campo="buscar no conteúdo publicado"),
                _no("mapa", pai=s3["id"], titulo="Mapa incorporado", item_id=app_id, altura=380),
                _no("aplicativo", pai=s3["id"], titulo="Aplicativo em destaque", item_id=app_id),
                _no("incorporado", pai=s3["id"], titulo="Conteúdo incorporado",
                    url="https://www.openstreetmap.org/export/embed.html", altura=300),
            ],
        },
    }


def _criar_site(admin, app_id: str) -> dict:
    r = admin.post("/api/itens", json={
        "tipo": "site", "titulo": "Site do serviço de teste interno", "dados": _documento(app_id)})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def site_publicado(inquilino_publico):
    admin = inquilino_publico.admin
    app, slug_app = _publicar_app(admin)
    site = _criar_site(admin, app["id"])
    r = admin.put(f"/api/itens/{site['id']}/site", json={"indexavel": False})
    assert r.status_code == 200, r.text
    return {"inq": inquilino_publico, "admin": admin, "site": site, "app": app, "slug_app": slug_app,
            "publicacao": r.json()}


# ---------------------------------------------------------------- cláusula 5: regras de montagem
@pytest.mark.parametrize(
    "corpo,regra",
    [
        ({"nos": [{"id": gerar_ulid(), "tipo": "texto", "propriedades": {"texto": "solto"}}]}, "cartao_na_secao"),
        ({"nos": [{"id": gerar_ulid(), "tipo": "inexistente"}]}, "tipo_de_no"),
    ],
)
def test_montagem_torta_recusada(inquilino_publico, corpo, regra):
    r = inquilino_publico.admin.post("/api/itens", json={
        "tipo": "site", "titulo": "zt site torto", "dados": {"tipo": "site", "esquema_versao": 1, "corpo": corpo}})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "site_invalido" and any(d["regra"] == regra for d in j["detalhe"]), j


def test_caminho_de_pagina_repetido_recusado(inquilino_publico):
    a = _no("pagina", titulo="A", caminho="mesma")
    b = _no("pagina", titulo="B", caminho="mesma")
    r = inquilino_publico.admin.post("/api/itens", json={
        "tipo": "site", "titulo": "zt site caminho",
        "dados": {"tipo": "site", "esquema_versao": 1, "corpo": {"nos": [a, b], "ligacoes": []}}})
    assert r.status_code == 422 and r.json()["erro"] == "site_invalido", r.text
    assert any(d["regra"] == "caminho_repetido" for d in r.json()["detalhe"])


# ---------------------------------------------------------------- cláusulas 1 e 2: 3 páginas, 9 cartões, sem JS
def test_html_sem_navegador_tem_o_texto_das_tres_paginas(site_publicado, medida):
    anon = novo_cliente()
    slug = site_publicado["inq"].slug
    r = anon.get(f"/s/{slug}/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), r.text
    html = r.text
    # o texto dos cartões da página inicial está no HTML servido, sem uma linha de JavaScript
    assert "<script" not in html.lower(), "a página de site não pode depender de script"
    for trecho in ("Primeiro parágrafo do cartão de texto.", "Segundo parágrafo do cartão de texto.",
                   "Marca do serviço de teste", "Legenda da imagem do cartão.", "Texto da chamada com botão.",
                   "Abrir o catálogo", "Nossos números", "Portal de dados do inquilino de teste",
                   "Rodapé com contato do serviço de teste interno."):
        assert trecho in html, trecho
    # o menu leva às outras duas páginas, e as duas trazem os seus cartões
    assert f'href="/s/{slug}/dados"' in html and f'href="/s/{slug}/mapas"' in html
    r2 = anon.get(f"/s/{slug}/dados")
    assert r2.status_code == 200 and "Conteúdo publicado" in r2.text and "buscar no conteúdo publicado" in r2.text
    r3 = anon.get(f"/s/{slug}/mapas")
    assert r3.status_code == 200 and "Mapa incorporado" in r3.text and "Aplicativo em destaque" in r3.text
    assert f'src="/p/{slug}/{site_publicado["slug_app"]}"' in r3.text
    assert 'src="https://www.openstreetmap.org/export/embed.html"' in r3.text
    # cada quadro tem título (exigência de acessibilidade) e nenhuma imagem sem texto alternativo
    assert not re.search(r"<iframe(?![^>]*\btitle=)", r3.text)
    assert not re.search(r"<img(?![^>]*\balt=)", r.text + r3.text)
    medida(ITEM)("paginas_publicadas", 3, "páginas", "GET /s/<inquilino>/{,dados,mapas} = 200")
    medida(ITEM)("cartoes_no_html", len(CARTOES), "tipos de cartão",
                 "classes cartao-<tipo> presentes no HTML das 3 páginas")
    juntos = html + r2.text + r3.text
    faltando = [c for c in CARTOES if f"cartao-{c}" not in juntos]
    assert faltando == [], faltando


def test_pagina_inexistente_e_site_nao_publicado_sao_404(site_publicado):
    anon = novo_cliente()
    slug = site_publicado["inq"].slug
    assert anon.get(f"/s/{slug}/pagina-que-nao-existe").status_code == 404
    assert anon.get("/s/zt-inquilino-que-nao-existe/").status_code == 404
    assert site_publicado["admin"].delete(f"/api/itens/{site_publicado['site']['id']}/site").status_code == 204
    assert anon.get(f"/s/{slug}/").status_code == 404


# ---------------------------------------------------------------- cláusula 3: só o que é público
def test_galeria_e_busca_so_mostram_item_compartilhado_com_todos(site_publicado, medida):
    admin = site_publicado["admin"]
    slug = site_publicado["inq"].slug
    titulo_privado = f"Camada secreta {secrets.token_hex(3)}"
    r = admin.post("/api/itens", json={
        "tipo": "mapa", "titulo": titulo_privado, "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    privado = r.json()
    titulo_publico = f"Mapa aberto {secrets.token_hex(3)}"
    r = admin.post("/api/itens", json={
        "tipo": "mapa", "titulo": titulo_publico, "dados": {"esquema_versao": 1, "corpo": {}}})
    publico = r.json()
    assert admin.put(f"/api/itens/{publico['id']}/compartilhamento", json={"acesso": "publico"}).status_code == 200

    anon = novo_cliente()
    galeria = anon.get(f"/s/{slug}/dados").text
    assert titulo_publico in galeria and titulo_privado not in galeria
    assert privado["id"] not in galeria

    # adversário: filtra pelo tipo do item privado e busca o título exato dele
    campo_filtro = re.search(r'name="(g[0-7][0-9A-HJKMNP-TV-Z]{25})"', galeria).group(1)
    filtrado = anon.get(f"/s/{slug}/dados?{campo_filtro}=mapa").text
    assert titulo_privado not in filtrado and privado["id"] not in filtrado and titulo_publico in filtrado
    campo_busca = re.search(r'name="(q[0-7][0-9A-HJKMNP-TV-Z]{25})"', galeria).group(1)
    buscado = anon.get(f"/s/{slug}/dados?{campo_busca}={titulo_privado}").text
    # o termo digitado volta no campo do formulário (é a entrada do próprio visitante, não vazamento); o que
    # não pode aparecer é o ITEM: nem o uuid, nem uma linha de resultado
    assert privado["id"] not in buscado and "nada encontrado" in buscado
    assert '<ul class="site-lista">' not in buscado.split("cartao-busca", 1)[1]  # nenhuma linha de resultado
    medida(ITEM)("itens_privados_vazados", 0, "itens",
                 "galeria, filtro por tipo e busca pelo título exato do item privado")


def test_cartao_que_cita_item_privado_nao_mostra_o_item(site_publicado):
    admin = site_publicado["admin"]
    slug = site_publicado["inq"].slug
    app_id = site_publicado["app"]["id"]
    assert admin.put(f"/api/itens/{app_id}/compartilhamento", json={"acesso": "privado"}).status_code == 200
    anon = novo_cliente()
    pagina = anon.get(f"/s/{slug}/mapas").text
    assert "não está compartilhado com todos" in pagina
    assert f'src="/p/{slug}/{site_publicado["slug_app"]}"' not in pagina
    assert "Mapa da rede de teste" not in pagina


# ---------------------------------------------------------------- cláusula 4: noindex por padrão
def test_noindex_por_padrao_e_index_so_por_opcao_explicita(site_publicado, medida):
    anon = novo_cliente()
    slug = site_publicado["inq"].slug
    admin = site_publicado["admin"]
    r = anon.get(f"/s/{slug}/")
    assert r.status_code == 200, r.text
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow">' in r.text
    assert site_publicado["publicacao"]["indexavel"] is False
    rp = admin.put(f"/api/itens/{site_publicado['site']['id']}/site", json={"indexavel": True})
    assert rp.status_code == 200 and rp.json()["indexavel"] is True, rp.text
    r2 = anon.get(f"/s/{slug}/")
    assert r2.headers["x-robots-tag"] == "index, follow"
    assert '<meta name="robots" content="index, follow">' in r2.text
    for pagina in ("", "dados", "mapas"):
        assert anon.get(f"/s/{slug}/{pagina}").headers["x-robots-tag"] == "index, follow"
    medida(ITEM)("noindex_padrao", True, "booleano",
                 "PUT /api/itens/<id>/site sem 'indexavel' -> X-Robots-Tag: noindex, nofollow")


def test_publicacao_recusa_tipo_errado_e_segundo_site(site_publicado):
    admin = site_publicado["admin"]
    r = admin.post("/api/itens", json={"tipo": "mapa", "titulo": "zt nao é site",
                                       "dados": {"esquema_versao": 1, "corpo": {}}})
    mapa = r.json()
    r = admin.put(f"/api/itens/{mapa['id']}/site", json={})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_nao_publicavel", r.text
    outro = _criar_site(admin, site_publicado["app"]["id"])
    r = admin.put(f"/api/itens/{outro['id']}/site", json={})
    assert r.status_code == 409 and r.json()["erro"] == "site_em_uso", r.text
