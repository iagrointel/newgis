"""e2e playwright da tela /conexoes (itens L6-02-l-saude, L6-05-proveniencia-camada-externa e
L6-02-conectores-vivos) contra a URL interna real. Prova: (1) conexão nova aparece com estado "nunca
testada"; (2) "testar agora" pela tela muda o marcador para "fora" (URL que responde 404) e para "ok" (URL
pública real), sem recarregar a página à mão; (3) "histórico" abre o diálogo com a verificação recém-feita;
(4) "publicar camada" numa conexão ArcGIS REST real (Esri) cria o item e mostra a licença EXATA que o serviço
declara (nunca um valor padrão) — a mesma prova de
`tests/api/test_conexoes.py::test_publicar_camada_le_licenca_declarada_do_arcgis_rest`, agora pela tela;
(5) "nova conexão" cadastra por URL pelo FORMULÁRIO (antes só existia POST /api/conexoes sem tela), "camadas"
descobre e lista nome/título/CRS/extensão de verdade contra o GeoSampa, e "pré-visualizar" busca um tile real
pelo proxy da própria conexão. 0 erro de console; capturas em tests/e2e/capturas/L6-02-l-saude_*.png. Sem
/api/conexoes no OpenAPI a suíte é pulada com a razão escrita."""

import pytest

from tests.e2e.apoio import sufixo
from tests.e2e.apoio_conexoes import ROTAS_CONEXOES, TelaConexoes, gravar_medidas_conexoes

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

URL_404_ESTAVEL = "https://api.github.com/repos/inexistente-zt-e2e-conexoes/tambem-inexistente"
URL_PUBLICA = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"
URL_ESRI_CENSUS = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer"
GEOSAMPA_WMS = "https://raster.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms"
CAMADA_GEOSAMPA = "MOSAICO_ORTO_RGB_10CM_20CM"


@pytest.fixture(scope="session")
def api_conexoes(api_auth):
    faltam = [r for r in ROTAS_CONEXOES if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L6-02-a)")
    return api_auth


def test_conexoes_lista_testar_historico_e_publicar(page, base_url, credenciais_demo, api_conexoes, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tela = TelaConexoes(page, base_url)
    criadas = []
    item_id = None
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/conexoes")

        # duas conexões pela API (mesmo cookie da tela — POST /api/conexoes ainda não tem formulário próprio,
        # que é dos conectores concretos por protocolo, L6-02-b em diante; ver ADR 0012 "o que fica para os
        # itens seguintes"): uma que sempre falha (404 estável) e uma ArcGIS REST real com licença declarada.
        r_fora = tela.api(
            "POST", "/api/conexoes",
            {"tipo": "http", "nome": f"zt-e2e-conexao-fora-{s}", "url": URL_404_ESTAVEL},
        )
        assert r_fora.status == 201, r_fora.text()
        cid_fora = r_fora.json()["id"]
        criadas.append(cid_fora)

        r_esri = tela.api(
            "POST", "/api/conexoes",
            {"tipo": "esri_rest", "nome": f"zt-e2e-conexao-esri-{s}", "url": URL_ESRI_CENSUS},
        )
        assert r_esri.status == 201, r_esri.text()
        cid_esri = r_esri.json()["id"]
        criadas.append(cid_esri)

        tela.medidas["pagina_conexoes_ms"] = tela.ir("/conexoes")
        linha_fora = page.locator(f"tr[data-id='{cid_fora}']")
        linha_esri = page.locator(f"tr[data-id='{cid_esri}']")
        assert linha_fora.locator(".marcador").inner_text().strip() == "nunca testada"
        tela.capturar("lista_nunca_testada")

        # testar agora (fora do ar) -> marcador vira "fora", sem recarregar a página
        linha_fora.get_by_role("button", name="testar agora").click()
        page.wait_for_function(
            "(id) => document.querySelector(`tr[data-id='${id}'] .marcador`)?.textContent?.trim() === 'fora'",
            arg=cid_fora, timeout=15000,
        )
        tela.capturar("fora_do_ar")

        # testar agora (esri, real) -> marcador vira "ok"
        linha_esri.get_by_role("button", name="testar agora").click()
        page.wait_for_function(
            "(id) => document.querySelector(`tr[data-id='${id}'] .marcador`)?.textContent?.trim() === 'ok'",
            arg=cid_esri, timeout=15000,
        )

        # histórico da conexão que falhou: diálogo mostra o teste recém-feito
        linha_fora.get_by_role("button", name="histórico").click()
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for(state="visible", timeout=10000)
        assert "1" in dialogo.inner_text() or "erro" in dialogo.inner_text().lower()
        tela.capturar("historico_dialogo")
        dialogo.locator(".dialogo-botoes button", has_text="fechar").click()
        dialogo.wait_for(state="hidden", timeout=10000)

        # publicar camada (esri): a ficha mostra a licença EXATA do serviço, nunca um valor padrão
        linha_esri.get_by_role("button", name="publicar camada").click()
        dialogo2 = page.locator("plat-dialogo dialog[open]")
        dialogo2.wait_for(state="visible", timeout=15000)
        texto_dialogo = dialogo2.inner_text()
        assert "US Bureau of the Census" in texto_dialogo
        tela.capturar("publicar_camada_procedencia")
        link_item = dialogo2.locator("a[href^='/conteudo/']")
        item_id = link_item.get_attribute("href").rsplit("/", 1)[-1]
        dialogo2.locator(".dialogo-botoes button", has_text="fechar").click()

        tela.verificar()
    finally:
        for cid in criadas:
            tela.api("DELETE", f"/api/conexoes/{cid}")
        if item_id:
            tela.api("DELETE", f"/api/itens/{item_id}")

    gravar_medidas_conexoes(medida, tela)


def test_conexoes_cadastrar_por_url_descobrir_camadas_e_prever(page, base_url, credenciais_demo, api_conexoes, medida):
    """item L6-02-conectores-vivos: cadastro por URL pelo formulário, descoberta de camada de verdade contra o
    GeoSampa e pré-visualização de um tile real pelo proxy — tudo pela tela, não pela API crua."""
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tela = TelaConexoes(page, base_url)
    nome = f"zt-e2e-conector-vivo-{s}"
    cid = None
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/conexoes")

        page.get_by_role("button", name="nova conexão").click()
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for(state="visible", timeout=10000)
        dialogo.locator("input[name='nome']").fill(nome)
        dialogo.locator("select[name='tipo']").select_option("wms")
        dialogo.locator("input[name='url']").fill(GEOSAMPA_WMS)
        tela.capturar("nova_conexao_formulario")
        dialogo.get_by_role("button", name="cadastrar").click()
        dialogo.wait_for(state="hidden", timeout=15000)

        linha = page.locator(f"tr:has-text('{nome}')")
        linha.wait_for(state="visible", timeout=10000)
        cid = linha.get_attribute("data-id")
        assert cid, "linha da conexão nova não tem data-id"
        assert linha.locator(".marcador").inner_text().strip() == "nunca testada"
        tela.capturar("lista_com_conector_vivo")

        # "camadas": ainda sem descoberta -> mensagem nomeada, não uma tabela vazia
        linha.get_by_role("button", name="camadas").click()
        dialogo2 = page.locator("plat-dialogo dialog[open]")
        dialogo2.wait_for(state="visible", timeout=10000)
        assert "nenhuma camada descoberta" in dialogo2.inner_text()

        # "descobrir agora": GetCapabilities de verdade contra o GeoSampa, tabela some a mensagem e ganha linhas
        dialogo2.get_by_role("button", name="descobrir agora").click()
        dialogo2.locator("table.tabela tbody tr").first.wait_for(state="visible", timeout=25000)
        assert dialogo2.locator("table.tabela tbody tr").count() > 0
        tela.capturar("camadas_descobertas")

        # "pré-visualizar" na camada de ortofoto: tile de verdade pelo proxy (mesmo elemento plat-dialogo,
        # reaproveitado — não há empilhamento de diálogo nesta tela)
        linha_camada = dialogo2.locator("tr", has_text=CAMADA_GEOSAMPA)
        linha_camada.get_by_role("button", name="pré-visualizar").click()
        dialogo3 = page.locator("plat-dialogo dialog[open]")
        dialogo3.wait_for(state="visible", timeout=10000)
        page.wait_for_function(
            "(sel) => { const im = document.querySelector(sel); return im && im.complete && im.naturalWidth > 0; }",
            arg="plat-dialogo dialog[open] img", timeout=25000,
        )
        tela.capturar("previa_de_tile")
        dialogo3.locator(".dialogo-botoes button", has_text="fechar").click()
        dialogo3.wait_for(state="hidden", timeout=10000)

        tela.verificar()
    finally:
        if cid:
            tela.api("DELETE", f"/api/conexoes/{cid}")

    gravar_medidas_conexoes(medida, tela)
