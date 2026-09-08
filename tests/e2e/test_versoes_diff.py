"""e2e do item L2-13-a: a tela /versoes mostra o diff LADO A LADO do conflito e grava a decisão.

Cenário: dois ramos editam a MESMA feição (a refutação do item-pai, adaptada). O primeiro é publicado no
padrão; o segundo, ao reconciliar, encontra o conflito — e é ESSE conflito que a tela precisa mostrar com
base, ramo e padrão nas três colunas, com captura de tela como prova.

Depende da bancada `scripts/edicao_demo_camadas.py criar` (a mesma camada de pontos do e2e do L2-03-edicao;
não se cria camada nova aqui porque não existe rota de publicação por GeoJSON). O valor original do atributo
mexido é devolvido no fim, e os dois ramos são apagados: a bancada fica como estava.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-13-a-versoes-ramo-reconciliar"


def _capturar(page, nome: str) -> Path:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho), full_page=True)
    return caminho


@pytest.fixture
def camada_versionada(admin_api, rotas_api):
    if "/api/camadas/{id}/versoes" not in rotas_api:
        pytest.skip("backend publicado ainda sem as rotas de versionamento por ramo (ramo wt/il213averso)")
    r = admin_api.get("/api/mapa/camadas")
    assert r.status == 200, r.text()
    itens = r.json().get("itens", r.json()) if isinstance(r.json(), dict) else r.json()
    alvo = next((c for c in itens if "edicao-pontos" in (c.get("titulo") or "")), None)
    if alvo is None:
        pytest.skip("bancada ausente: rode scripts/edicao_demo_camadas.py criar")
    item_id = alvo["id"]
    assert admin_api.post(f"/api/camadas/{item_id}/versionar", data={}).status == 200
    ramos = [f"zt-um-{sufixo()}", f"zt-dois-{sufixo()}"]
    yield item_id, ramos
    for ramo in ramos:
        admin_api.delete(f"/api/camadas/{item_id}/versoes/{ramo}")


def _feicoes(admin_api, item_id):
    r = admin_api.get(f"/rest/services/{item_id}/FeatureServer/0/query?where=1%3D1&outFields=*&f=json")
    assert r.status == 200, r.text()
    return r.json()["features"]


def _campo_de_texto(atributos: dict) -> str:
    for nome in ("nome", "titulo", "descricao", "rotulo"):
        if nome in atributos:
            return nome
    pytest.skip(f"bancada sem campo de texto conhecido: {sorted(atributos)}")
    return ""


def test_diff_lado_a_lado_de_dois_ramos_na_mesma_feicao(
    page, base_url, credenciais_demo, admin_api, camada_versionada, medida
):
    item_id, (ramo_um, ramo_dois) = camada_versionada
    alvo = _feicoes(admin_api, item_id)[0]["attributes"]
    globalid = alvo.get("globalid") or alvo.get("GlobalID")
    campo = _campo_de_texto(alvo)
    original = alvo[campo]

    try:
        for ramo, valor in ((ramo_um, "de-um"), (ramo_dois, "de-dois")):
            assert admin_api.post(
                f"/api/camadas/{item_id}/versoes", data={"nome": ramo, "acesso": "publico"}
            ).status == 201
            r = admin_api.post(
                f"/api/camadas/{item_id}/edicoes",
                data={"versao": ramo, "atualizar": [
                    {"id": globalid, "versao": alvo["versao"], "atributos": {campo: valor}}]},
            )
            assert r.status == 200, r.text()
        assert admin_api.post(f"/api/camadas/{item_id}/versoes/{ramo_um}/publicar", data={}).status == 200

        slug, login, senha = credenciais_demo
        tela = Tela(page, base_url)
        tela.entrar(slug, login, senha)
        tela.ir(f"/versoes?camada={item_id}", "pagina_pronta_ms_versoes")
        page.select_option("#versoes-ramo", ramo_dois)
        page.click("#btn-reconciliar")
        page.wait_for_selector(f'.conflito[data-globalid="{globalid}"]', timeout=20000)

        linha = page.locator(f'.conflito[data-globalid="{globalid}"] .diff-linha[data-campo="{campo}"]')
        assert linha.locator(".valor-base").inner_text().strip() == str(original)
        assert linha.locator(".valor-ramo").inner_text().strip() == "de-dois"
        assert linha.locator(".valor-padrao").inner_text().strip() == "de-um"
        # o lado que mudou é marcado por CLASSE, não só por cor
        assert "mudou" in (linha.locator(".valor-ramo").get_attribute("class") or "")
        assert "mudou" in (linha.locator(".valor-padrao").get_attribute("class") or "")
        _capturar(page, "diff_conflito_dois_ramos")

        page.check(f"#decisao-{globalid}-manual")
        page.fill(f"#manual-{globalid}-{campo}", "decidido-na-tela")
        page.click(f'.conflito[data-globalid="{globalid}"] .aplicar')
        page.wait_for_selector(f'.conflito[data-globalid="{globalid}"][data-resolvido="manual"]', timeout=20000)
        _capturar(page, "diff_conflito_resolvido")

        page.click("#btn-publicar")
        page.wait_for_selector('#aviso[tipo="informacao"]', timeout=20000)
        valores = [f["attributes"][campo] for f in _feicoes(admin_api, item_id)]
        assert "decidido-na-tela" in valores, valores
        tela.verificar()
        gravar = medida(ITEM)
        for nome_medida, valor in tela.medidas.items():
            gravar(nome_medida, valor, "ms", "make e2e (chromium do playwright, tests/e2e/test_versoes_diff.py)")
    finally:
        atual = next(
            (f["attributes"] for f in _feicoes(admin_api, item_id)
             if (f["attributes"].get("globalid") or f["attributes"].get("GlobalID")) == globalid),
            None,
        )
        if atual is not None and atual[campo] != original:
            admin_api.post(
                f"/api/camadas/{item_id}/edicoes",
                data={"atualizar": [
                    {"id": globalid, "versao": atual["versao"], "atributos": {campo: original}}]},
            )
