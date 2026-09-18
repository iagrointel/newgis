"""e2e do item L2-03-d-historico-restauracao: o DIFF VISUAL do histórico de uma feição, com captura.

Cenário: na bancada `edicao-pontos` (scripts/edicao_demo_camadas.py), uma feição nova é criada e editada
(atributo + geometria) pela API. A tela `/camadas/{id}/feicoes/{globalid}/historico` tem de mostrar, na
entrada 'atualizar':

  * o diff CAMPO A CAMPO — `nome` marcado como mudado (classe, nunca só cor), `categoria` intacto sem a
    marca — com os valores antes/depois exatos;
  * o diff DA GEOMETRIA — área/comprimento antes/depois em metros e os DOIS MAPAS lado a lado (canvas do
    maplibre renderizado nos dois lados);
  * o resumo com o total de entradas.

A feição é apagada no fim: a bancada fica como estava. Captura em tests/e2e/capturas/ (inventário no
relatório do item)."""

from __future__ import annotations

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-03-d-historico-restauracao"


def _capturar(page, nome: str):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho), full_page=True)
    return caminho


@pytest.fixture
def camada_demo(admin_api, rotas_api):
    if "/api/camadas/{id}/feicoes/{globalid}/historico" not in rotas_api:
        pytest.skip("backend publicado ainda sem a rota de histórico de feição")
    r = admin_api.get("/api/mapa/camadas")
    assert r.status == 200, r.text()
    alvo = next((c for c in r.json().get("camadas", []) if "edicao-pontos" in (c.get("titulo") or "")), None)
    if alvo is None:
        pytest.skip("bancada ausente: rode scripts/edicao_demo_camadas.py criar")
    return alvo["id"]


def test_diff_visual_do_historico_com_captura(page, base_url, credenciais_demo, admin_api, camada_demo, medida):
    item_id = camada_demo
    r = admin_api.post(
        f"/api/camadas/{item_id}/edicoes",
        data={"adicionar": [{"atributos": {"nome": "diff-original", "categoria": "A"},
                             "geometria": {"type": "Point", "coordinates": [-46.10, -23.50]}}]},
    )
    assert r.status == 200, r.text()
    feicao = r.json()["adicionar"][0]
    gid = feicao["id"]
    try:
        r = admin_api.post(
            f"/api/camadas/{item_id}/edicoes",
            data={"atualizar": [{"id": gid, "versao": feicao["versao"],
                                 "atributos": {"nome": "diff-mudado"},
                                 "geometria": {"type": "Point", "coordinates": [-45.90, -23.45]}}]},
        )
        assert r.status == 200, r.text()

        slug, login, senha = credenciais_demo
        tela = Tela(page, base_url, item=ITEM)
        tela.entrar(slug, login, senha)
        tela.ir(f"/camadas/{item_id}/feicoes/{gid}/historico", "pagina_pronta_ms_histfeicao")
        page.wait_for_selector('.entrada[data-operacao="atualizar"]', timeout=20000)

        assert "2 entrada" in page.locator("#histfeicao-resumo").inner_text()

        # diff campo a campo: o que mudou marcado por CLASSE, o que não mudou sem marca
        entrada = page.locator('.entrada[data-operacao="atualizar"]').first
        nome = entrada.locator('.diff-linha[data-campo="nome"]')
        assert nome.locator(".valor-antes").inner_text().strip() == "diff-original"
        assert nome.locator(".valor-depois").inner_text().strip() == "diff-mudado"
        assert "mudou" in (nome.locator(".valor-depois").get_attribute("class") or "")
        categoria = entrada.locator('.diff-linha[data-campo="categoria"]')
        assert categoria.locator(".valor-depois").inner_text().strip() == "A"
        assert "mudou" not in (categoria.locator(".valor-depois").get_attribute("class") or "")

        # diff da geometria: números em metros nos dois lados e os DOIS mapas renderizados
        geom = entrada.locator(".geom-dif")
        assert "área (m²)" in geom.locator(".area-antes").inner_text()
        assert "comprimento (m)" in geom.locator(".comp-depois").inner_text()
        page.wait_for_selector(".mapa-antes canvas", timeout=20000)
        page.wait_for_selector(".mapa-depois canvas", timeout=20000)
        _capturar(page, "diff_historico_feicao")

        tela.verificar()
        gravar = medida(ITEM)
        for nome_medida, valor in tela.medidas.items():
            gravar(nome_medida, valor, "ms",
                   "pytest tests/e2e/test_historico_diff.py (chromium do playwright)")
    finally:
        atual = admin_api.get(f"/api/camadas/{item_id}/feicoes/{gid}")
        if atual.status == 200:
            admin_api.post(
                f"/api/camadas/{item_id}/edicoes",
                data={"apagar": [{"id": gid, "versao": atual.json()["versao"]}]},
            )
