"""e2e do item UX-23-mapa-sem-controle: as seis rotas de escrita do mapa que não tinham controle ganham
controle no visualizador, com estados e erro nomeado.

1. painel Seleção (novo, atalho `s`): por atributo (POST /api/mapa/camadas/{id}/filtrar — condições campo ·
   operador · valor, E/OU, SQL equivalente mostrado), por geometria do painel Desenho (POST .../selecionar, com
   combinação somar/subtrair) e entre camadas (POST /api/mapa/selecao-espacial); o resultado vai para a tabela
   (realce), vira filtro da camada no mapa (e sai) e é guardado como item `selecao`;
   refutação: valor não numérico em campo numérico é recusado no navegador sem chamada; 422 do servidor
   (campo fora da lista branca, interceptado) aparece nomeado com o campo;
2. anotações: criar, editar (PATCH /api/anotacoes/{id}, só o autor), resolver/reabrir, apagar (DELETE) com
   confirmação; estados sem alvo / vazio / carregando; 403 interceptado vira "só o autor";
3. importar pacote (POST /api/mapa/pacotes/importar): sem arquivo = motivo; zip sem manifesto = 422 real nomeado
   com referência; 201 interceptado = resumo e ligação para o mapa importado.
Capturas 390/1280; axe 0 sérias; console limpo; sem chave crua. Depende da bancada `mapa_demo_camadas.py criar`."""

import io
import json
import zipfile

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-23"
BANCADA_POLIGONOS = "mapa-poligonos"
BANCADA_1MI = "1 mi"
# polígono que cobre a bancada sintética inteira (ela espalha feições pelo Brasil)
BRASIL = {"type": "Polygon", "coordinates": [[[-75, -35], [-33, -35], [-33, 6], [-75, 6], [-75, -35]]]}


def _capturar(page, nome, larguras=(390, 1280)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"))
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def _entrar_no_mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def _abrir(page, painel):
    page.evaluate("(p) => window.plat.mapa.abrirPainel(p, { foco: false })", painel)
    page.wait_for_selector(f"#painel-{painel}:not([hidden])", timeout=5000)


def _ligar(page, trecho):
    """liga a camada cujo título contém `trecho`; devolve o id dela (salta sem a bancada)."""
    _abrir(page, "camadas")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    ids = page.evaluate(
        "(t) => window.plat.mapa.catalogo.disponiveis.filter(f => f.titulo.includes(t)).map(f => f.id)", trecho
    )
    if not ids:
        pytest.skip(f"bancada ausente ({trecho}): rode scripts/mapa_demo_camadas.py criar")
    page.evaluate("(id) => window.plat.mapa.catalogo.ligar(id)", ids[0])
    page.wait_for_function("(id) => window.plat.mapa.catalogo.ativas.includes(id)", arg=ids[0], timeout=20000)
    return ids[0]


def _erro_json(status, erro, mensagem, detalhe=None, req_id="e2e-ux23-ref"):
    corpo = {"erro": erro, "mensagem": mensagem, "req_id": req_id}
    if detalhe is not None:
        corpo["detalhe"] = detalhe
    return {"status": status, "content_type": "application/json", "body": json.dumps(corpo)}


# ---------------------------------------------------------------- 1. seleção


def test_selecao_atributo_geometria_camadas_tabela_filtro_e_guardar(page, base_url, credenciais_demo, api_auth):
    if "/api/mapa/selecao-espacial" not in api_auth:
        pytest.skip("backend sem /api/mapa/selecao-espacial no OpenAPI")
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    _abrir(page, "selecao")
    # sem camada hospedada ligada: estado vazio nomeado, botão desligado
    page.wait_for_selector("#sel-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#sel-executar").is_disabled()
    _axe(page, "seleção vazia")
    poligonos = _ligar(page, BANCADA_POLIGONOS)
    _abrir(page, "selecao")
    page.wait_for_function("() => !document.querySelector('#sel-executar').disabled", timeout=10000)
    assert page.input_value("#sel-camada") == poligonos
    # refutação: valor não numérico em campo numérico é recusado no navegador, sem chamada
    chamadas = []
    page.on("request", lambda r: chamadas.append(r.url) if "/filtrar" in r.url and r.method == "POST" else 0)
    page.select_option("#sel-condicoes li[data-condicao='0'] select[data-parte='campo']", "area_ha")
    page.select_option("#sel-condicoes li[data-condicao='0'] select[data-parte='op']", ">")
    page.fill("#sel-condicoes li[data-condicao='0'] input[data-parte='valor']", "abc")
    page.click("#sel-executar")
    page.wait_for_selector("#sel-estado[tipo='erro']:not([hidden])")
    assert "area_ha" in (page.text_content("#sel-estado") or "")
    assert chamadas == []
    # por atributo: classe é nulo (a bancada tem 1 em 4 com campo nulo); depois OU area_ha > 0
    page.select_option("#sel-condicoes li[data-condicao='0'] select[data-parte='campo']", "classe")
    page.select_option("#sel-condicoes li[data-condicao='0'] select[data-parte='op']", "isNull")
    assert page.locator("#sel-condicoes li[data-condicao='0'] input[data-parte='valor']").is_hidden()
    page.click("#sel-executar")
    page.wait_for_selector("#sel-resultado:not([hidden]) .sel-n", timeout=30000)
    n_nulos = page.evaluate("() => window.plat.mapa.selecao.resultado.n")
    assert 0 < n_nulos < 5000, n_nulos
    assert "IS NULL" in (page.text_content("#sel-resultado .sel-sql") or "").upper()
    page.click("#sel-mais")
    page.select_option("#sel-condicoes li[data-condicao='1'] select[data-parte='campo']", "area_ha")
    page.select_option("#sel-condicoes li[data-condicao='1'] select[data-parte='op']", ">")
    page.fill("#sel-condicoes li[data-condicao='1'] input[data-parte='valor']", "0")
    page.select_option("#sel-combinador", "or")
    page.click("#sel-executar")
    page.wait_for_function("(n) => window.plat.mapa.selecao.resultado.n !== n", arg=n_nulos, timeout=30000)
    n_ou = page.evaluate("() => window.plat.mapa.selecao.resultado.n")
    assert n_ou >= n_nulos, (n_ou, n_nulos)
    assert " OR " in (page.text_content("#sel-resultado .sel-sql") or "").upper()
    _sem_chave_crua(page, extras={"area_ha", "classe", "nome", "fid"})
    _capturar(page, "selecao_atributo")
    # o resultado cai na tabela (realce + contagem), e vira filtro da camada no mapa
    page.click("#sel-ver-tabela")
    page.wait_for_selector("#painel-tabela:not([hidden])", timeout=10000)
    page.wait_for_function(
        "(n) => (document.querySelector('#tabela-selecao').textContent || '').includes(String(n))",
        arg=min(n_ou, 5000), timeout=15000,
    )
    estilo = page.evaluate("(id) => window.plat.mapa.catalogo.idsDeEstilo(id)[0]", poligonos)
    page.click("#sel-filtrar-mapa")
    filtro = page.evaluate("(c) => JSON.stringify(window.plat.mapa.map.getFilter(c))", estilo)
    assert '"in"' in filtro and '"fid"' in filtro, filtro
    assert page.locator("#sel-limpar-mapa:not([hidden])").count() == 1
    _capturar(page, "selecao_filtro_mapa", larguras=(1280,))
    page.click("#sel-limpar-mapa")
    filtro2 = page.evaluate("(c) => JSON.stringify(window.plat.mapa.map.getFilter(c) || null)", estilo)
    assert '"fid"' not in filtro2, filtro2
    # 422 do servidor nomeado com o campo (interceptado: a lista branca do cliente já impede o caso real)
    page.route("**/api/mapa/camadas/*/filtrar", lambda r: r.fulfill(
        **_erro_json(422, "campo_nao_permitido", "campo não está na lista branca da camada: segredo",
                     {"campo": "segredo"})))
    tela.esperar_status(422)
    page.click("#sel-executar")
    page.wait_for_selector("#sel-estado[tipo='erro']:not([hidden])")
    assert "segredo" in (page.text_content("#sel-estado") or "")
    assert "e2e-ux23-ref" in (page.text_content("#sel-estado") or "")
    page.unroute("**/api/mapa/camadas/*/filtrar")
    _capturar(page, "selecao_erro_campo", larguras=(1280,))
    # por geometria: polígono do painel Desenho, subtraindo da seleção atual
    page.evaluate(
        "(g) => window.plat.mapa.desenho.importarGeoJSON({ type: 'Feature', geometry: g, properties: {} })", BRASIL
    )
    page.click("#painel-selecao [data-modo='geometria']")
    page.wait_for_function("() => document.querySelectorAll('#sel-desenho option').length >= 1", timeout=5000)
    page.select_option("#sel-modo-combinacao", "subtrair")
    page.click("#sel-executar")
    page.wait_for_function("(n) => window.plat.mapa.selecao.resultado.n !== n", arg=n_ou, timeout=30000)
    n_sub = page.evaluate("() => window.plat.mapa.selecao.resultado.n")
    assert n_sub < n_ou, (n_sub, n_ou)
    page.select_option("#sel-modo-combinacao", "novo")
    page.click("#sel-executar")
    page.wait_for_function("(n) => window.plat.mapa.selecao.resultado.n !== n", arg=n_sub, timeout=30000)
    n_geo = page.evaluate("() => window.plat.mapa.selecao.resultado.n")
    # aritmética de conjuntos sobre a amostra (a bancada tem 5.000 polígonos, dentro do limite de amostra): o que
    # sobrou ao subtrair a caixa é no mínimo a seleção menos o que cai na caixa, e é menor que a seleção inteira
    assert n_geo > 0 and n_ou - n_geo <= n_sub < n_ou, (n_geo, n_sub, n_ou)
    _capturar(page, "selecao_geometria", larguras=(1280,))
    # entre camadas: polígonos que intersectam a camada de 1 milhão de pontos
    page.click("#painel-selecao [data-modo='camadas']")
    outra = page.evaluate(
        "(t) => [...document.querySelectorAll('#sel-camada-b option')].find(o => o.textContent.includes(t))?.value",
        BANCADA_1MI,
    )
    if outra:
        page.select_option("#sel-camada-b", outra)
        page.click("#sel-executar")
        page.wait_for_function("() => window.plat.mapa.selecao.resultado.criterio.tipo === 'camadas'", timeout=60000)
        assert page.evaluate("() => window.plat.mapa.selecao.resultado.n") >= 0
        _capturar(page, "selecao_camadas", larguras=(1280,))
    # guardar como item `selecao`
    page.click("#sel-salvar")
    page.wait_for_selector("#sel-saida a[href^='/conteudo/']", timeout=15000)
    href = page.get_attribute("#sel-saida a", "href")
    item_id = href.rsplit("/", 1)[1]
    try:
        r = tela.api("GET", f"/api/itens/{item_id}")
        assert r.status == 200 and r.json()["tipo"] == "selecao", r.status
        assert r.json()["dados"]["camada_id"] == poligonos
    finally:
        tela.api("DELETE", f"/api/itens/{item_id}")
    _axe(page, "seleção com resultado")
    tela.verificar()


# ---------------------------------------------------------------- 2. anotações


def test_anotacoes_criar_editar_resolver_apagar_e_estados(page, base_url, credenciais_demo, api_auth):
    if "/api/anotacoes/{id}" not in api_auth:
        pytest.skip("backend sem /api/anotacoes/{id} no OpenAPI")
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    s = sufixo()
    grupo = tela.api("POST", "/api/grupos", {"nome": f"zt-ux23-{s}"})
    grupo_id = grupo.json().get("id") if grupo.status == 201 else None
    try:
        poligonos = _ligar(page, BANCADA_POLIGONOS)
        _abrir(page, "anotacoes")
        page.wait_for_selector("#anotacoes-estado[tipo='vazio']:not([hidden])")
        assert page.locator("#anotacoes-corpo").is_hidden()
        _axe(page, "anotações sem alvo")
        page.evaluate("([c, f]) => window.plat.mapa.painelAnotacoes.abrir(c, f)", [poligonos, "1"])
        page.wait_for_function(
            "() => { const e = document.querySelector('#anotacoes-estado'); "
            "return !e.hidden && e.getAttribute('tipo') !== 'carregando'; }",
            timeout=15000,
        )
        if not grupo_id:
            pytest.skip(f"sem grupo para anotar (POST /api/grupos = {grupo.status})")
        # criar
        page.fill("#anotacao-texto", f"primeira nota {s}")
        page.click("#btn-anotacao-enviar")
        page.wait_for_selector(f"#lista-anotacoes li[data-minha='1']:has-text('primeira nota {s}')", timeout=15000)
        assert page.locator("#anotacoes-estado").is_hidden()
        _sem_chave_crua(page)
        _capturar(page, "anotacoes_lista")
        # editar o texto (PATCH, só o autor)
        page.click("#lista-anotacoes li [data-acao='editar']")
        page.fill("#lista-anotacoes li textarea", f"nota editada {s}")
        page.click("#lista-anotacoes li [data-acao='gravar']")
        page.wait_for_selector(f"#lista-anotacoes li:has-text('nota editada {s}')", timeout=15000)
        assert "editada" in (page.text_content("#lista-anotacoes li .anotacao-cabecalho") or "")
        # resolver e reabrir
        page.click("#lista-anotacoes li [data-acao='resolver']")
        page.wait_for_selector("#lista-anotacoes li[data-resolvido='1']", timeout=15000)
        page.click("#lista-anotacoes li [data-acao='resolver']")
        page.wait_for_selector("#lista-anotacoes li[data-resolvido='0']", timeout=15000)
        _axe(page, "anotações com lista")
        # 403 interceptado (outro autor) aparece nomeado, a lista fica
        page.route("**/api/anotacoes/*", lambda r: r.fulfill(**_erro_json(403, "sem_permissao", "só o autor edita"))
                   if r.request.method == "PATCH" else r.continue_())
        tela.esperar_status(403)
        page.click("#lista-anotacoes li [data-acao='resolver']")
        page.wait_for_function(
            "() => (document.querySelector('#anotacoes-aviso').textContent || '').includes('autor')", timeout=10000
        )
        page.unroute("**/api/anotacoes/*")
        _capturar(page, "anotacoes_negado", larguras=(1280,))
        # apagar com confirmação → estado vazio
        page.click("#lista-anotacoes li [data-acao='apagar']")
        page.wait_for_selector("plat-dialogo:not([hidden]) button.perigo", timeout=5000)
        page.click("plat-dialogo button.perigo")
        page.wait_for_selector("#anotacoes-estado[tipo='vazio']:not([hidden])", timeout=15000)
        assert page.locator("#lista-anotacoes li").count() == 0
        tela.verificar()
    finally:
        if grupo_id:
            tela.api("DELETE", f"/api/grupos/{grupo_id}")


# ---------------------------------------------------------------- 3. importar pacote


def test_importar_pacote_sem_arquivo_zip_invalido_e_sucesso(page, base_url, credenciais_demo, api_auth):
    if "/api/mapa/pacotes/importar" not in api_auth:
        pytest.skip("backend sem /api/mapa/pacotes/importar no OpenAPI")
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    _abrir(page, "exportar")
    page.wait_for_selector("#imp-bloco", timeout=10000)
    assert page.locator("#btn-importar-pacote").is_disabled()
    # zip real sem manifesto → 422 pacote_invalido do servidor, nomeado com referência
    zip_ruim = io.BytesIO()
    with zipfile.ZipFile(zip_ruim, "w") as z:
        z.writestr("leia-me.txt", "sem manifesto")
    ruim = {"name": "pacote-ruim.zip", "mimeType": "application/zip", "buffer": zip_ruim.getvalue()}
    page.set_input_files("#imp-arquivo", ruim)
    assert page.locator("#btn-importar-pacote").is_enabled()
    tela.esperar_status(422)
    page.click("#btn-importar-pacote")
    page.wait_for_selector("#imp-estado[tipo='erro']:not([hidden])", timeout=30000)
    texto = page.text_content("#imp-estado") or ""
    assert "inválido" in texto and "referência" in texto, texto
    _axe(page, "pacote inválido")
    _sem_chave_crua(page)
    _capturar(page, "pacote_invalido")
    # arquivo que não é zip: recusado no navegador, sem chamada
    chamadas = []
    page.on("request", lambda r: chamadas.append(r.url) if "/pacotes/importar" in r.url else 0)
    page.set_input_files("#imp-arquivo", {"name": "nota.txt", "mimeType": "text/plain", "buffer": b"x"})
    page.click("#btn-importar-pacote")
    page.wait_for_selector("#imp-estado[tipo='erro']:not([hidden])")
    assert "nota.txt" in (page.text_content("#imp-estado") or "")
    assert chamadas == []
    # 201 interceptado: resumo e ligação para o mapa importado
    page.route("**/api/mapa/pacotes/importar", lambda r: r.fulfill(
        status=201, content_type="application/json",
        body=json.dumps({"mapa_id": "00000000-0000-4000-8000-0000000000aa", "titulo": "Mapa de teste",
                         "camadas": [{"id": "1", "titulo": "a"}, {"id": "2", "titulo": "b"}]})))
    page.set_input_files("#imp-arquivo", {**ruim, "name": "pacote.zip"})
    page.click("#btn-importar-pacote")
    page.wait_for_selector("#imp-saida a#imp-abrir", timeout=15000)
    assert "2" in (page.text_content("#imp-saida") or "")
    assert (page.get_attribute("#imp-abrir", "href") or "").startswith("/mapa?mapa=")
    page.unroute("**/api/mapa/pacotes/importar")
    _capturar(page, "pacote_importado", larguras=(1280,))
    tela.verificar()
