"""Metadado do fator do motor multicritério — item L3-15-metadado-fator.

Cláusulas do portão provadas aqui (as de biblioteca; as de API estão em tests/api/amc/test_metadado_api.py):

1. peso acima do teto de proxy é RECUSADO com explicação — no documento do modelo e nos pesos da execução;
2. o relatório lista proxies e âncoras;
3. o JSON Schema exige `base` e `fonte` em todo fator.
"""

import json
from pathlib import Path

import pytest

from app.amc import esquema as mod_esquema
from app.amc import metadado as mod_metadado
from app.amc import relatorio as mod_relatorio
from app.erros import ErroAPI

RAIZ = Path(__file__).resolve().parents[2]
CLAUSULA_TETO = "fatores[].proxy: fatia do peso <= proxy.teto_peso"


def fator(fid: str, peso: float, **extra) -> dict:
    f = {
        "id": fid, "nome": f"fator {fid}", "fonte": "camada de teste interno", "unidade": "m",
        "direcao": "maior_melhor", "base": "engenharia",
        "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000001"},
        "extrator": {"tipo": "valor_pronto", "parametros": {}},
        "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 100},
        "peso": peso,
    }
    f.update(extra)
    return f


def modelo(*fatores) -> dict:
    return {"esquema": "amc_modelo.v1", "nome": "modelo de teste interno", "fatores": list(fatores)}


PROXY = {"descricao": "a camada mede presença declarada de vegetação, não supressão de árvore"}


# ---------------------------------------------------------------- cláusula 3: o esquema exige base e fonte
@pytest.mark.parametrize("campo", ["base", "fonte"])
def test_esquema_exige_campo_no_fator(campo):
    """O JSON Schema, lido do arquivo, lista o campo em `required` do fator — e a validação recusa sem ele."""
    doc = json.loads((RAIZ / "docs" / "esquemas" / "amc_modelo.v1.json").read_text(encoding="utf-8"))
    assert campo in doc["$defs"]["fator"]["required"]

    m = modelo(fator("a", 1.0))
    del m["fatores"][0][campo]
    violacoes = mod_esquema.violacoes(m)
    assert any(v["caminho"] == "$.fatores[0]" and campo in v["mensagem"] for v in violacoes), violacoes


@pytest.mark.parametrize("campo", ["base", "fonte"])
def test_esquema_exige_campo_na_restricao(campo):
    doc = json.loads((RAIZ / "docs" / "esquemas" / "amc_modelo.v1.json").read_text(encoding="utf-8"))
    assert campo in doc["$defs"]["restricao"]["required"]


def test_base_so_aceita_os_tres_valores():
    m = modelo(fator("a", 1.0, base="acho_que_sim"))
    assert any(v["caminho"] == "$.fatores[0].base" for v in mod_esquema.violacoes(m))


def test_fonte_vazia_e_recusada():
    m = modelo(fator("a", 1.0, fonte=""))
    assert any(v["caminho"] == "$.fatores[0].fonte" for v in mod_esquema.violacoes(m))


def test_versao_de_fonte_e_aceita_e_chega_a_ficha():
    m = modelo(fator("a", 1.0, versao_fonte="coleção 10, lida em 2026-09"))
    assert mod_esquema.violacoes(m) == []
    assert mod_metadado.fichas(m)["fatores"][0]["versao_fonte"] == "coleção 10, lida em 2026-09"


# ---------------------------------------------------------------- cláusula 1: teto de proxy
def test_proxy_dentro_do_teto_passa():
    m = modelo(fator("proxy_veg", 6.0, proxy=PROXY), fator("b", 4.0))
    assert mod_esquema.violacoes(m) == [], "fatia de 60,0% é exatamente o teto padrão e tem de passar"


def test_proxy_acima_do_teto_e_recusado_com_explicacao():
    m = modelo(fator("proxy_veg", 9.0, proxy=PROXY), fator("b", 1.0))
    violacoes = [v for v in mod_esquema.violacoes(m) if v["clausula"] == CLAUSULA_TETO]
    assert len(violacoes) == 1, mod_esquema.violacoes(m)
    v = violacoes[0]
    assert v["caminho"] == "$.fatores[0].peso"
    # a explicação nomeia o fator, a fatia medida, o teto, o que a camada mede e qual peso caberia
    for pedaco in ("proxy_veg", "90.0%", "60.0%", "presença declarada", "1.5"):
        assert pedaco in v["mensagem"], v["mensagem"]


def test_validar_levanta_422_com_a_violacao_do_teto():
    m = modelo(fator("proxy_veg", 9.0, proxy=PROXY), fator("b", 1.0))
    with pytest.raises(ErroAPI) as e:
        mod_esquema.validar(m)
    assert e.value.status_code == 422
    assert e.value.erro == "modelo_invalido"
    assert any(v["clausula"] == CLAUSULA_TETO for v in e.value.detalhe["violacoes"])


def test_teto_e_fatia_do_peso_nao_valor_absoluto():
    """Multiplicar TODOS os pesos pelo mesmo número não muda o modelo (a soma ponderada é normalizada), então
    não pode mudar o veredito do teto."""
    for escala in (0.001, 1.0, 1000.0):
        dentro = modelo(fator("p", 6.0 * escala, proxy=PROXY), fator("b", 4.0 * escala))
        fora = modelo(fator("p", 7.0 * escala, proxy=PROXY), fator("b", 3.0 * escala))
        assert mod_esquema.violacoes(dentro) == [], escala
        assert any(v["clausula"] == CLAUSULA_TETO for v in mod_esquema.violacoes(fora)), escala


def test_teto_declarado_pelo_usuario_e_respeitado():
    apertado = {"descricao": PROXY["descricao"], "teto_peso": 0.2}
    m = modelo(fator("p", 3.0, proxy=apertado), fator("b", 7.0))
    v = [x for x in mod_esquema.violacoes(m) if x["clausula"] == CLAUSULA_TETO]
    assert len(v) == 1 and "20.0%" in v[0]["mensagem"], mod_esquema.violacoes(m)


def test_fator_unico_declarado_proxy_reprova():
    """Consequência declarada da regra: se o único fator é proxy, a nota fica 100% determinada por um dado que
    mede outra grandeza."""
    m = modelo(fator("p", 1.0, proxy=PROXY))
    assert any(v["clausula"] == CLAUSULA_TETO for v in mod_esquema.violacoes(m))


def test_fator_sem_proxy_nunca_tem_teto():
    m = modelo(fator("a", 999.0), fator("b", 0.001))
    assert mod_esquema.violacoes(m) == []


def test_teto_nos_pesos_da_execucao():
    """A porta dos fundos: modelo dentro do teto, pesos da execução fora dele."""
    m = mod_esquema.validar(modelo(fator("p", 1.0, proxy=PROXY), fator("b", 9.0)))
    with pytest.raises(ErroAPI) as e:
        mod_esquema.validar_pesos(m, {"p": 30.0})
    assert e.value.status_code == 422 and e.value.erro == "pesos_invalidos"
    assert any(v["clausula"] == CLAUSULA_TETO for v in e.value.detalhe["violacoes"])
    # e o caminho feliz continua funcionando
    assert mod_esquema.validar_pesos(m, {"p": 1.5, "b": 8.5})["p"] == 1.5


# ---------------------------------------------------------------- cláusula 2: relatório lista proxies e âncoras
def modelo_rico() -> dict:
    return modelo(
        fator("veg", 3.0, proxy=PROXY, classe_peso="apetite_de_risco", ancora_peso="escolhida",
              versao_fonte="2026-09", nao_sustenta="não distingue supressão de árvore de presença declarada"),
        fator("terreno", 5.0, classe_peso="custo_medido", ancora_peso="medida", versao_fonte="BPR 2026"),
        fator("rito", 2.0, base="norma", classe_peso="consequencia_normativa"),
    )


def test_relatorio_lista_proxies_e_ancoras():
    m = modelo_rico()
    saida = mod_relatorio.montar_relatorio([[10.0, 20.0, 30.0]], [3.0, 5.0, 2.0],
                                           ids_fatores=["veg", "terreno", "rito"], definicao=m)
    meta = saida["metadado"]
    assert [p["fator_id"] for p in meta["proxies"]] == ["veg"]
    assert meta["proxies"][0]["teto_peso"] == 0.6
    assert meta["proxies"][0]["fatia_do_peso"] == pytest.approx(3.0 / 10.0)
    assert meta["ancoras"] == {"medida": ["terreno"], "escolhida": ["veg"], "nao_declarada": ["rito"]}
    assert meta["fatores_sem_versao_de_fonte"] == ["rito"]
    assert "veg" in meta["aviso_proxy"]
    assert "escolha" in meta["aviso_ancora"]


def test_relatorio_sem_definicao_nao_inventa_metadado():
    saida = mod_relatorio.montar_relatorio([[10.0, 20.0]], [1.0, 1.0], ids_fatores=["a", "b"])
    assert "metadado" not in saida


def test_relatorio_sem_proxy_diz_que_nao_ha():
    m = modelo(fator("a", 1.0, ancora_peso="medida"))
    meta = mod_relatorio.montar_relatorio([[10.0]], [1.0], ids_fatores=["a"], definicao=m)["metadado"]
    assert meta["proxies"] == []
    assert "nenhum" in meta["aviso_proxy"]


def test_ficha_do_fator_traz_os_nove_campos_e_o_resumo():
    m = modelo_rico()
    ficha = mod_metadado.fichas(m)["fatores"][0]
    for campo in ("fonte", "versao_fonte", "unidade", "direcao", "base", "proxy", "classe_peso", "ancora_peso",
                  "nao_sustenta"):
        assert campo in ficha
    assert ficha["proxy"] is True
    assert "Teto de peso 60.0%" in ficha["resumo"]
    assert "Não sustenta:" in ficha["resumo"]


def test_ficha_nao_inventa_campo_ausente():
    ficha = mod_metadado.fichas(modelo(fator("a", 1.0)))["fatores"][0]
    assert ficha["classe_peso"] is None and ficha["ancora_peso"] is None and ficha["versao_fonte"] is None
    assert "não declarado" in ficha["resumo"]


def test_relatorio_usa_os_pesos_da_execucao_na_fatia():
    m = modelo_rico()
    meta = mod_relatorio.montar_relatorio([[10.0, 20.0, 30.0]], [1.0, 1.0, 1.0],
                                          ids_fatores=["veg", "terreno", "rito"], definicao=m,
                                          pesos_por_id={"veg": 1.0, "terreno": 1.0, "rito": 2.0})["metadado"]
    assert meta["proxies"][0]["fatia_do_peso"] == pytest.approx(0.25)


# ---------------------------------------------------------------- o '?' do fator: dados e tela
def test_explicacao_leva_a_ficha_de_cada_fator_e_o_bloco_de_proxies():
    """A explicação por unidade (item L3-01-f) é o que a tela lê para montar o '?' do fator: cada linha traz a
    ficha completa e a explicação traz os proxies e as âncoras do modelo."""
    from app.amc import explicacao as mod_explicacao

    m = modelo_rico()
    pesos = {"veg": 3.0, "terreno": 5.0, "rito": 2.0}
    brutos = {"veg": {"valor": 40.0, "cobertura": 1.0}, "terreno": {"valor": 10.0, "cobertura": 1.0},
              "rito": {"valor": 90.0, "cobertura": 1.0}}
    saida = mod_explicacao.montar_explicacao(m, pesos, brutos).como_dicionario()

    por_id = {f["fator_id"]: f for f in saida["fatores"]}
    assert por_id["veg"]["metadado"]["proxy"] is True
    assert por_id["veg"]["metadado"]["proxy_teto_peso"] == 0.6
    assert por_id["veg"]["metadado"]["nao_sustenta"].startswith("não distingue")
    assert por_id["terreno"]["metadado"]["ancora_peso"] == "medida"
    assert por_id["rito"]["metadado"]["base"] == "norma"
    assert [p["fator_id"] for p in saida["metadado"]["proxies"]] == ["veg"]
    assert saida["metadado"]["ancoras"]["nao_declarada"] == ["rito"]


def test_explicacao_usa_o_peso_da_execucao_na_fatia_da_ficha():
    from app.amc import explicacao as mod_explicacao

    m = modelo_rico()
    saida = mod_explicacao.montar_explicacao(m, {"veg": 1.0, "terreno": 1.0, "rito": 2.0},
                                             {"veg": {"valor": 40.0, "cobertura": 1.0}}).como_dicionario()
    assert saida["metadado"]["proxies"][0]["fatia_do_peso"] == pytest.approx(0.25)


def test_tela_da_explicacao_tem_o_interrogacao_e_o_cartao_de_proxies():
    """Conferência ESTRUTURAL da tela (o navegador sem interface quebra nesta máquina — nota do CLAUDE.md):
    o `details` da ficha, o cartão "proxies e âncoras" e os campos que a ficha escreve."""
    html = (RAIZ / "web" / "amc_explicacao.html").read_text(encoding="utf-8")
    js = (RAIZ / "web" / "js" / "amc" / "explicacao_pagina.js").read_text(encoding="utf-8")

    assert 'id="metadado-cartao"' in html
    for elemento in ("aviso-proxy", "proxies-lista", "aviso-ancora", "ancoras-lista", "sem-versao"):
        assert f'id="{elemento}"' in html, elemento
    assert ".ficha > summary" in html, "sem o estilo do '?' a ficha vira uma seta sem afordância"
    assert "ficha do fator" in html

    assert "function fichaDoFator" in js
    assert "h('details', { class: 'ficha' }" in js
    assert "montarMetadado(resp.json)" in js
    for rotulo in ("versão da fonte", "base do fator", "classe do peso", "âncora do peso",
                   "teto de peso do proxy", "não sustenta"):
        assert f"'{rotulo}'" in js, rotulo
    # o '?' lê os ids que a API grava: se um deles mudar de nome, o teste cai junto
    for chave in ("versao_fonte", "base_descricao", "classe_peso_descricao", "ancora_peso_descricao",
                  "proxy_teto_peso", "fatia_do_peso", "nao_sustenta"):
        assert f"m.{chave}" in js, chave
