"""e2e do item UX-15-geocodificador-esri-sem-controle: as quatro rotas de escrita do GeocodeServer compatível com Esri
(POST no descritor, findAddressCandidates, reverseGeocode e geocodeAddresses) têm controle na tela /geocodificar, e a
URL do serviço é exposta para o cliente externo copiar em /geocodificar e em /admin/tokens:

1. descritor REAL (público): versão e capacidades no painel; findAddressCandidates REAL com a sessão (a base por
   trilha não tem CNEFE: lista vazia → estado vazio nomeado, sem erro); reverseGeocode REAL (422 sem_dado_instalado
   nomeado, ou 200 quando a base tem UF); geocodeAddresses REAL em lote (1 registro, Status U ou M);
2. forjados pela própria página: 200 com candidatos (tabela Score/Match_addr/Addr_type), 403 (escopo insuficiente,
   no formato da API da casa) vira negado com o código nomeado, 500 vira erro com "tentar de novo" e referência;
3. /admin/tokens: bloco "URLs para clientes externos" com GeocodeServer e OGC Records, escopo e botão copiar;
4. axe 0 violações sérias; 0 erro de console; capturas 390/1280; medidas em
   tests/medidas/UX-15-geocodificador-esri-sem-controle.json."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-15-geocodificador-esri-sem-controle"
LARGURAS = (390, 1280)
PREFIXO = "/rest/services/Geocodificador/GeocodeServer"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def _axe(page, onde, acumulado):
    graves = serias(page)
    acumulado[onde] = len(graves)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _forjar(page, padrao, status, corpo, vezes=1):
    restantes = {"n": vezes}

    def rota(route):
        if route.request.method != "POST" or restantes["n"] <= 0:
            route.fallback()
            return
        restantes["n"] -= 1
        route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    page.route(padrao, rota)
    return lambda: page.unroute(padrao, rota)


CANDIDATOS = {"spatialReference": {"wkid": 4326}, "candidates": [
    {"address": "Avenida Brasil, 100, Centro, Boa Vista - RR", "location": {"x": -60.6714, "y": 2.8235}, "score": 97.5,
     "attributes": {"Match_addr": "Avenida Brasil, 100, Centro, Boa Vista - RR", "Addr_type": "PointAddress",
                    "Score": 97.5},
     "extent": {"xmin": -60.68, "ymin": 2.81, "xmax": -60.66, "ymax": 2.83}},
]}


def _esperar_estado_ou_resultado(page):
    page.wait_for_function("() => { const e = document.getElementById('esri-estado'); "
                           "return (!e.hidden && e.getAttribute('tipo') !== 'carregando') "
                           "|| !document.getElementById('esri-resultado').hidden; }", timeout=15000)


def test_geocodeserver_pela_tela_e_urls_para_clientes_externos(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.esperar_status(400, 404, 422, 403, 500)  # reais (respostas de negócio do motor) e forjados pela página
    violacoes = {}
    estados = []
    tela.ir("/geocodificar", "pagina_pronta_ms_geocodificar_esri")
    page.wait_for_selector("#esri-url")
    assert page.text_content("#esri-url") == f"{base_url}{PREFIXO}"
    page.click("#esri-copiar button")
    page.wait_for_function(
        "() => /Copiado|Selecionado/.test(document.querySelector('#esri-copiar button').textContent)")
    estados.append("url:copiar")

    # ------------------------------------------------------------ 1. chamadas REAIS
    page.click("#esri-descritor")
    page.wait_for_selector("#esri-resultado:not([hidden])")
    titulo = page.text_content("#esri-titulo") or ""
    assert "11.3" in titulo and "Geocode" in titulo, titulo
    assert '"capabilities"' in (page.text_content("#esri-json") or "")
    estados.append("descritor:ok")
    _axe(page, "/geocodificar descritor Esri", violacoes)
    _capturar(page, "descritor")
    page.fill("#form-endereco input[name=endereco]", "Rua Inexistente Zt, 1, Bairro Zt, Cidade Zt - RR")
    page.click("#esri-candidatos")
    _esperar_estado_ou_resultado(page)
    if page.locator("#esri-resultado").is_hidden():
        texto = page.text_content("#esri-estado") or ""
        assert page.get_attribute("#esri-estado", "tipo") == "vazio", texto
        assert ("sem candidatos" in texto or "sem_correspondencia" in texto) and "422" not in texto, texto
        estados.append("candidatos:vazio")
    else:
        estados.append("candidatos:ok:real")
    _capturar(page, "candidatos_vazio", (1280,))
    page.fill("#form-reverso input[name=lon]", "-60.67")
    page.fill("#form-reverso input[name=lat]", "2.82")
    page.click("#esri-reverso")
    _esperar_estado_ou_resultado(page)
    if page.locator("#esri-resultado").is_hidden():
        texto = page.text_content("#esri-estado") or ""
        assert ("nao_encontrado" in texto or "fora_da_distancia" in texto) and "404" not in texto.split(":")[0], texto
        estados.append("reverso:vazio")
    else:
        assert "Match_addr" in (page.text_content("#esri-tabela") or "")
        estados.append("reverso:ok:real")
    page.fill("#form-lote textarea[name=enderecos]", "Rua Zt, 1, Cidade Zt - RR\n")
    page.click("#form-lote button[type=submit]")
    page.wait_for_selector("#esri-resultado:not([hidden])")
    assert "1 registro" in (page.text_content("#esri-titulo") or "")
    assert page.locator("#esri-tabela tbody tr").count() == 1
    assert page.locator("#esri-tabela tbody tr td").nth(1).inner_text() in ("U", "M")
    estados.append("lote:ok")
    _axe(page, "/geocodificar lote Esri", violacoes)
    _capturar(page, "lote", (1280,))
    page.fill("#form-lote textarea[name=enderecos]", "")
    page.click("#form-lote button[type=submit]")
    page.wait_for_selector("#form-lote [data-campo='enderecos'] .erro-campo")
    estados.append("lote:vazio_no_campo")

    # ------------------------------------------------------------ 2. forjados: 200 com candidatos, 403 Esri, 500
    parar = _forjar(page, f"**{PREFIXO}/findAddressCandidates*", 200, CANDIDATOS)
    page.click("#esri-candidatos")
    page.wait_for_selector("#esri-tabela")
    linha = page.locator("#esri-tabela tbody tr").first.locator("td").all_inner_texts()
    assert linha[0] == "97.5" and "Avenida Brasil, 100" in linha[1] and linha[2] == "PointAddress", linha
    assert "1 candidato" in (page.text_content("#esri-titulo") or "")
    estados.append("candidatos:ok")
    parar()
    _capturar(page, "candidatos")
    # 403 como a API da casa responde (escopo insuficiente): negado com o código e o escopo nomeados
    parar = _forjar(page, f"**{PREFIXO}/reverseGeocode*", 403,
                    {"erro": "escopo_insuficiente", "mensagem": "o token não tem o escopo geocodificar:usar (forjado)",
                     "req_id": "e2e-ux15-403"})
    page.click("#esri-reverso")
    page.wait_for_selector("#esri-estado[tipo='negado']:not([hidden])")
    texto = page.text_content("#esri-estado") or ""
    assert "geocodificar:usar" in texto and "escopo_insuficiente" in texto, texto
    estados.append("reverso:negado")
    _capturar(page, "negado", (1280,))
    parar()
    parar = _forjar(page, f"**{PREFIXO}/geocodeAddresses", 500,
                    {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux15-500"})
    page.fill("#form-lote textarea[name=enderecos]", "Rua Zt, 1")
    page.click("#form-lote button[type=submit]")
    page.wait_for_selector("#esri-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#esri-estado") or ""
    assert "banco indisponível (forjado)" in texto and "e2e-ux15-500" in texto, texto
    assert page.get_attribute("#esri-estado", "role") == "alert"
    estados.append("lote:erro")
    _axe(page, "/geocodificar erro Esri", violacoes)
    _capturar(page, "erro", (1280,))
    parar()
    page.click("#esri-estado button[data-acao='tentar']")  # tentar de novo repete o lote de verdade
    page.wait_for_selector("#esri-resultado:not([hidden])")
    estados.append("lote:tentar_de_novo")

    # ------------------------------------------------------------ 3. /admin/tokens: URLs para clientes externos
    tela.ir("/admin/tokens", "pagina_pronta_ms_tokens")
    page.wait_for_selector("#servico-geocodeserver")
    assert page.text_content("#servico-geocodeserver") == f"{base_url}{PREFIXO}"
    assert page.text_content("#servico-ogc-records") == f"{base_url}/ogc/records"
    assert "geocodificar:usar" in (page.text_content("#servicos-externos") or "")
    page.click("#servicos-externos li:first-child button")
    page.wait_for_function(
        "() => /Copiado|Selecionado/.test(document.querySelector('#servicos-externos li button').textContent)")
    estados.append("tokens:urls")
    _axe(page, "/admin/tokens serviços externos", violacoes)
    _capturar(page, "tokens")

    # ------------------------------------------------------------ 4. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
