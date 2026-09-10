"""e2e do item UX-14-geocodificador-sem-tela: as rotas de escrita POST /api/geocodificar e POST /api/reverso têm
controle na tela /geocodificar, com os quatro estados do sistema de design (UX-01):

1. endereço → coordenada: carregando; vazio NOMEADO com a resposta real da API (422 sem_correspondencia ou
   sem_dado_instalado — nas bases por trilha o CNEFE não está carregado, e a tela mostra o código e a mensagem,
   nunca o número cru); 422 endereco_vazio REAL cai no campo endereço; 422 de validação (lista do pydantic,
   forjado) cai no campo apontado; 403 forjado vira negado; 500 forjado vira erro com "tentar de novo" e
   referência; 200 forjado desenha a tabela de candidatos (pontuação, tipo de acerto traduzido, coordenada,
   "ver no mapa");
2. coordenada → endereço: vazio nomeado (real), 422 forjado no campo lat, 403 negado, 200 forjado com o
   resultado e a marca "fora do raio";
3. axe 0 violações sérias (formulários, tabela, estados); 0 erro de console; capturas 390/1280; medidas em
   tests/medidas/UX-14-geocodificador-sem-tela.json."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-14-geocodificador-sem-tela"
LARGURAS = (390, 1280)
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


CANDIDATOS = {"total": 2, "candidatos": [
    {"endereco": "Avenida Brasil, 100, Centro, Boa Vista - RR", "lon": -60.6714, "lat": 2.8235, "score": 97.5,
     "tipo_acerto": "exato", "municipio": "Boa Vista", "uf": "RR", "cep": "69301000", "bairro": "Centro",
     "logradouro": "Avenida Brasil", "numero": 100, "avisos": []},
    {"endereco": "Avenida Brasil, Centro, Boa Vista - RR", "lon": -60.67, "lat": 2.82, "score": 71.0,
     "tipo_acerto": "aproximado_no_bairro", "municipio": "Boa Vista", "uf": "RR", "cep": None, "bairro": "Centro",
     "logradouro": "Avenida Brasil", "numero": None, "avisos": ["número não encontrado no logradouro (forjado)"]},
]}
REVERSO = {"endereco": "Rua Cecília Brasil, 50, Centro, Boa Vista - RR", "logradouro": "Rua Cecília Brasil",
           "numero": 50, "bairro": "Centro", "municipio": "Boa Vista", "uf": "RR", "cep": "69301000",
           "distancia_m": 2531.4, "fora_do_raio": True, "tipo_acerto": "reverso_vizinho_mais_proximo",
           "lon": -60.67, "lat": 2.82}


def test_endereco_e_reverso_com_estados_nomeados(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.esperar_status(422, 403, 500)  # reais (422 do motor/validação) e forjados pela própria página
    violacoes = {}
    estados = []
    tela.ir("/geocodificar", "pagina_pronta_ms_geocodificar")
    page.wait_for_selector("#form-endereco input[name=endereco]")
    _axe(page, "/geocodificar inicial", violacoes)
    _capturar(page, "inicial")

    # ------------------------------------------------------------ 1. endereço → coordenada
    # 422 endereco_vazio REAL: nenhum campo preenchido -> a mensagem nomeada da API vai para o campo endereço
    page.click("#form-endereco button[type=submit]")
    page.wait_for_selector("#form-endereco [data-campo='endereco'] .erro-campo")
    texto = page.text_content("#form-endereco [data-campo='endereco'] .erro-campo") or ""
    assert "informe ao menos" in texto and "422" not in texto, texto
    assert page.evaluate("() => document.activeElement.name") == "endereco"
    estados.append("endereco:422:endereco_vazio")
    # vazio nomeado REAL: o motor responde sem correspondência (ou sem UF instalada) -> estado vazio com o código
    page.fill("#form-endereco input[name=endereco]", "Rua Inexistente Zt, 1, Bairro Zt, Cidade Zt - RR")
    page.click("#form-endereco button[type=submit]")
    page.wait_for_selector("#endereco-estado[tipo='vazio']:not([hidden])")
    texto = page.text_content("#endereco-estado") or ""
    assert ("sem_correspondencia" in texto or "sem_dado_instalado" in texto) and "422" not in texto, texto
    assert page.locator("#endereco-estado button[data-acao='limpar']").count() == 1
    estados.append("endereco:vazio")
    _axe(page, "/geocodificar vazio", violacoes)
    _capturar(page, "endereco_vazio")
    # 422 de validação (lista do pydantic, forjado): cai no campo apontado por `loc`
    parar = _forjar(page, "**/api/geocodificar", 422,
                    {"erro": "validacao", "mensagem": "corpo inválido", "req_id": "e2e-ux14-422",
                     "detalhe": [{"loc": ["body", "uf"], "msg": "UF precisa de 2 letras (forjado)",
                                  "type": "value_error"}]})
    page.click("#form-endereco button[type=submit]")
    page.wait_for_selector("#form-endereco [data-campo='uf'] .erro-campo")
    assert "2 letras (forjado)" in (page.text_content("#form-endereco [data-campo='uf'] .erro-campo") or "")
    estados.append("endereco:422:campo")
    parar()
    # 403 forjado -> negado com o privilégio/mensagem da API
    parar = _forjar(page, "**/api/geocodificar", 403,
                    {"erro": "sem_privilegio", "mensagem": "o token não tem o escopo geocodificar:usar",
                     "req_id": "e2e-ux14-403"})
    page.click("#form-endereco button[type=submit]")
    page.wait_for_selector("#endereco-estado[tipo='negado']:not([hidden])")
    assert "geocodificar:usar" in (page.text_content("#endereco-estado") or "")
    estados.append("endereco:negado")
    _capturar(page, "endereco_negado", (1280,))
    parar()
    # 500 forjado -> erro com referência e "tentar de novo"; tentar de novo chama de novo (forjado 200)
    parar = _forjar(page, "**/api/geocodificar", 500,
                    {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux14-500"})
    page.click("#form-endereco button[type=submit]")
    page.wait_for_selector("#endereco-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#endereco-estado") or ""
    assert "banco indisponível (forjado)" in texto and "e2e-ux14-500" in texto, texto
    assert page.get_attribute("#endereco-estado", "role") == "alert"
    estados.append("endereco:erro")
    _axe(page, "/geocodificar erro", violacoes)
    _capturar(page, "endereco_erro", (1280,))
    parar()
    parar = _forjar(page, "**/api/geocodificar", 200, CANDIDATOS)
    page.click("#endereco-estado button[data-acao='tentar']")
    page.wait_for_selector("#resultados:not([hidden])")
    linhas = page.locator("#resultados-corpo tr")
    assert linhas.count() == 2
    primeira = linhas.first.locator("td").all_inner_texts()
    assert "97,5" in primeira[0] and "Avenida Brasil, 100" in primeira[1] and primeira[2] == "número exato", primeira
    assert "-60.671400, 2.823500" == primeira[3].strip(), primeira
    assert "aproximado no bairro" in linhas.nth(1).locator("td").nth(2).inner_text()
    assert "forjado" in linhas.nth(1).locator("td").nth(1).inner_text()  # aviso do candidato
    assert page.get_attribute("#resultados-corpo tr a", "href").startswith("/mapa#lon=-60.6714")
    assert "2 candidato" in (page.text_content("#resultados-contagem") or "")
    estados.append("endereco:ok")
    parar()
    _axe(page, "/geocodificar candidatos", violacoes)
    _capturar(page, "candidatos")
    page.click("#form-endereco .botoes button[type=button]")  # limpar
    page.wait_for_selector("#resultados[hidden]", state="attached")

    # ------------------------------------------------------------ 2. coordenada → endereço
    page.fill("#form-reverso input[name=lon]", "-60.67")
    page.fill("#form-reverso input[name=lat]", "2.82")
    page.click("#form-reverso button[type=submit]")
    page.wait_for_function("() => { const e = document.getElementById('reverso-estado'); "
                           "return (e.getAttribute('tipo') === 'vazio' && !e.hidden) "
                           "|| !document.getElementById('reverso-resultado').hidden; }")
    if not page.locator("#reverso-resultado").is_hidden():
        estados.append("reverso:ok:real")  # base com CNEFE instalado
    else:
        assert "sem_dado_instalado" in (page.text_content("#reverso-estado") or "")
        estados.append("reverso:vazio")
    _capturar(page, "reverso_vazio", (1280,))
    parar = _forjar(page, "**/api/reverso", 422,
                    {"erro": "validacao", "mensagem": "corpo inválido", "req_id": "e2e-ux14-422b",
                     "detalhe": [{"loc": ["body", "lat"], "msg": "latitude fora de [-90, 90] (forjado)",
                                  "type": "value_error"}]})
    page.click("#form-reverso button[type=submit]")
    page.wait_for_selector("#form-reverso [data-campo='lat'] .erro-campo")
    assert "(forjado)" in (page.text_content("#form-reverso [data-campo='lat'] .erro-campo") or "")
    estados.append("reverso:422:campo")
    parar()
    parar = _forjar(page, "**/api/reverso", 403,
                    {"erro": "sem_privilegio", "mensagem": "o token não tem o escopo geocodificar:usar",
                     "req_id": "e2e-ux14-403b"})
    page.click("#form-reverso button[type=submit]")
    page.wait_for_selector("#reverso-estado[tipo='negado']:not([hidden])")
    estados.append("reverso:negado")
    parar()
    parar = _forjar(page, "**/api/reverso", 200, REVERSO)
    page.click("#form-reverso button[type=submit]")
    page.wait_for_selector("#reverso-resultado:not([hidden])")
    texto = page.text_content("#reverso-resultado") or ""
    assert "Rua Cecília Brasil, 50" in texto and "Boa Vista - RR" in texto and "2.531,4 m" in texto, texto
    assert page.locator("#reverso-fora-do-raio").count() == 1
    estados.append("reverso:ok")
    parar()
    _axe(page, "/geocodificar reverso", violacoes)
    _capturar(page, "reverso")

    # ------------------------------------------------------------ 3. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
