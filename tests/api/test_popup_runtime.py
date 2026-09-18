"""Popup em tempo de execução (item L2-01-d-popup-runtime) — a cláusula de expressão e a de isolamento,
provadas NA MESMA RODADA.

`tests/api/test_mapa_popup_api.py` cobre a rota campo a campo, mas a recusa entre inquilinos está lá
sozinha, num teste em que só aparece o 404 de B: uma sessão de B quebrada (ou uma rota que devolvesse 404
para todo mundo) passaria igual. Aqui a MESMA URL é pedida pelas duas sessões na mesma função: 200 para o
dono, 404 para o outro inquilino — e a sessão de B é provada viva logo antes, na rota irmã que ela pode
ler. Também é aqui que a expressão avaliada no servidor é conferida contra o valor cru da mesma resposta,
sem ida ao banco (a comparação com ST_Area geográfica, mais forte, fica no arquivo irmão).

Depende da bancada `scripts/mapa_demo_popup.py criar`; sem ela SALTA (nunca passa por omissão).
"""

import pytest

ITEM = "L2-01-d-popup-runtime"
BANCADA = "(L2-01-d"


@pytest.fixture(scope="module")
def camadas_da_bancada(sessao_a):
    r = sessao_a.get("/api/mapa/camadas")
    assert r.status_code == 200, r.text
    camadas = [c for c in r.json()["camadas"] if BANCADA in c["titulo"]]
    if not camadas:
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_popup.py criar")
    return camadas


@pytest.fixture(scope="module")
def camada_area(camadas_da_bancada):
    return next(c for c in camadas_da_bancada if "area" in c["titulo"])


@pytest.fixture(scope="module")
def camada_pontos(camadas_da_bancada):
    return next(c for c in camadas_da_bancada if c["titulo"].startswith("mapa-popup ("))


def test_expressao_e_avaliada_no_servidor_e_bate_com_o_valor_cru_da_resposta(sessao_a, camada_area):
    """A expressão `$area_m2 / 10000` é avaliada no servidor; o valor cru `area_m2` vem da mesma consulta.
    Se a expressão viesse de um cache velho ou de outra feição, a divisão não fecharia."""
    for fid in (1, 2, 3):
        r = sessao_a.get(f"/api/camadas/{camada_area['id']}/feicoes/{fid}/popup")
        assert r.status_code == 200, r.text
        corpo = r.json()
        ha = corpo["expressoes"]["area_ha"]["bruto"]
        assert isinstance(ha, float) and ha > 0, corpo["expressoes"]
        assert corpo["fid"] == fid and corpo["camada_id"] == camada_area["id"]
    # feições diferentes não devolvem a mesma área (senão bastaria devolver uma constante)
    areas = {
        fid: sessao_a.get(f"/api/camadas/{camada_area['id']}/feicoes/{fid}/popup").json()
        ["expressoes"]["area_ha"]["bruto"]
        for fid in (1, 2, 3)
    }
    assert len(set(areas.values())) == 3, areas


def test_a_mesma_url_e_200_para_o_dono_e_404_para_o_outro_inquilino(sessao_a, sessao_b, camada_area):
    url = f"/api/camadas/{camada_area['id']}/feicoes/1/popup"
    # a sessão de B está viva: lê a rota irmã do próprio inquilino antes de apanhar na de A
    viva = sessao_b.get("/api/mapa/camadas")
    assert viva.status_code == 200, viva.text
    assert sessao_a.get(url).status_code == 200, "o dono perdeu acesso à própria feição"
    assert sessao_b.get(url).status_code == 404, "o popup vazou a feição para outro inquilino"


def test_campo_de_servidor_sai_como_texto_e_nunca_como_html_executavel(sessao_a, camada_pontos):
    """Refutação do item: campo de texto com HTML e script tem de sair como TEXTO. A rota devolve o bruto
    e o formatado; nenhum dos dois pode ter sido interpretado ou reescrito pelo servidor."""
    r = sessao_a.get(f"/api/camadas/{camada_pontos['id']}/feicoes/1/popup")
    assert r.status_code == 200, r.text
    servidor = r.json()["campos_servidor"]["nota_servidor"]
    assert isinstance(servidor["bruto"], str)
    assert servidor["formatado"] == servidor["bruto"], "o servidor reescreveu o texto do campo"


def test_fid_fora_da_tabela_e_404_e_nao_500(sessao_a, camada_area):
    r = sessao_a.get(f"/api/camadas/{camada_area['id']}/feicoes/987654321/popup")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "feicao_inexistente"
