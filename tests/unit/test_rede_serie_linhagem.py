"""Régua da linhagem da série temporal da rede (item L4-15-serie-temporal-da-rede), sem banco.

O que se prova aqui é a DECISÃO: dado quem some, quem nasce, a carteira de unidades consumidoras de cada
transformador e quais pares a coordenada aproxima, quem vira `recodificado` e com que confiança. As três
formas de evidência do método da casa são exercitadas uma a uma, e também o caso que interessa ao
adversário: sem evidência nenhuma, nada é casado — o COD_ID que some é `extinto` e o que nasce é `novo`.
"""

from app.rede_utilidades import serie


def test_jaccard_alto_casa_o_par():
    """Carteira quase igual (7 de 8 UCs em comum) casa acima do limiar, e a confiança É o Jaccard."""
    somem, nascem = {"T1"}, {"T9"}
    ucs = {f"U{i}" for i in range(8)}
    casados = serie.casar(somem, nascem, {"T1": ucs}, {"T9": ucs | {"U8"}}, ucs | {"U8"}, set())
    assert set(casados) == {"T1"}
    alvo, confianca, evidencia = casados["T1"]
    assert alvo == "T9"
    assert evidencia["motivo"] == "jaccard"
    assert confianca == 8 / 9
    assert evidencia["ucs_em_comum"] == 8


def test_sem_evidencia_nao_casa():
    """Carteiras disjuntas e sem coordenada em comum: nada é casado (vira novo e extinto no chamador)."""
    casados = serie.casar({"T1"}, {"T9"}, {"T1": {"U1", "U2"}}, {"T9": {"U7", "U8"}},
                          {"U1", "U2", "U7", "U8"}, set())
    assert casados == {}


def test_jaccard_fraco_precisa_da_coordenada():
    """Jaccard 0,33: sozinho não basta (limiar 0,6); com a coordenada casando, basta — e a confiança
    passa a ser a fixa do casamento por geometria, nunca o Jaccard fraco."""
    base, alvo = {"T1": {"U1", "U2"}}, {"T9": {"U2", "U3"}}
    ucs = {"U1", "U2", "U3"}
    assert serie.casar({"T1"}, {"T9"}, base, alvo, ucs, set()) == {}
    casados = serie.casar({"T1"}, {"T9"}, base, alvo, ucs, {("T1", "T9")})
    assert casados["T1"][1] == serie.CONFIANCA_GEO
    assert casados["T1"][2]["motivo"] == "geometria_e_jaccard"


def test_trafo_pequeno_casa_so_pela_coordenada():
    """Transformador com menos de cinco UCs não tem carteira que sirva de prova: a coordenada decide."""
    casados = serie.casar({"T1"}, {"T9"}, {"T1": {"U1"}}, {"T9": {"U7"}}, {"U1", "U7"}, {("T1", "T9")})
    assert casados["T1"][2]["motivo"] == "geometria_e_poucas_ucs"
    assert casados["T1"][1] == serie.CONFIANCA_GEO


def test_trafo_grande_nao_casa_so_pela_coordenada():
    """A mesma coordenada NÃO basta quando os dois lados têm carteira grande e nada em comum: dois
    transformadores no mesmo poste são coisas diferentes, e o método da casa não os funde."""
    grande_a = {f"A{i}" for i in range(10)}
    grande_b = {f"B{i}" for i in range(10)}
    casados = serie.casar({"T1"}, {"T9"}, {"T1": grande_a}, {"T9": grande_b},
                          grande_a | grande_b, {("T1", "T9")})
    assert casados == {}


def test_cada_codigo_e_usado_uma_vez_so():
    """Dois candidatos disputam o mesmo alvo: fica o de maior confiança, e o outro sobra (vira extinto)."""
    ucs = {f"U{i}" for i in range(6)}
    somem = {"T1", "T2"}
    base = {"T1": ucs, "T2": {"U0", "U1", "U2", "U3"}}
    casados = serie.casar(somem, {"T9"}, base, {"T9": ucs}, ucs, set())
    assert set(casados) == {"T1"}
    assert casados["T1"][0] == "T9"


def test_uc_fora_da_intersecao_nao_conta_como_evidencia():
    """Só UC identificada (presente nas DUAS safras) entra no Jaccard: uma UC que só existe num ano não
    pode sustentar o casamento, senão a mudança de carteira viraria prova de identidade."""
    casados = serie.casar({"T1"}, {"T9"}, {"T1": {"U1", "X1", "X2"}}, {"T9": {"U1", "Y1", "Y2"}},
                          {"U1"}, set())
    assert casados["T1"][2]["jaccard"] == 1.0  # dentro das identificadas, só U1 existe dos dois lados
    assert casados["T1"][2]["ucs_base"] == 1


def test_metodo_declara_as_premissas():
    """Número de carregamento sem a premissa ao lado não vale: o método gravado carrega os dois fatores,
    a fórmula, os limiares da linhagem e a natureza de proxy."""
    m = serie.metodo()
    assert m["carga"]["fator_carga"] == serie.FATOR_CARGA
    assert m["carga"]["fator_potencia"] == serie.FATOR_POTENCIA
    assert m["carga"]["horas_ano"] == serie.HORAS_ANO
    assert "proxy" in m["carga"]["natureza"]
    assert m["linhagem"]["jaccard_recodificado"] == serie.J_RECODIFICADO
    assert m["pot_nom"]["limiar_troca_massa"] == serie.LIMIAR_TROCA_MASSA


def test_csv_de_tendencia_tem_uma_coluna_por_safra():
    """A exportação abre com o código e traz uma coluna de carregamento por ano, mais a ressalva da placa."""
    from app.rede_utilidades.rotas_serie import _csv_tendencia

    itens = [{
        "codigo": "T1", "alimentador": "AL1", "por_ano": {"2023": {"carga_pct": 60.0},
                                                          "2024": {"carga_pct": 130.0}},
        "ano_inicial": 2023, "ano_final": 2024, "carga_inicial_pct": 60.0, "carga_final_pct": 130.0,
        "variacao_pp": 70.0, "variacao_pp_ano": 70.0, "virou_sobrecarga": True, "pot_nom_confiavel": False,
    }]
    linhas = _csv_tendencia(itens, [2023, 2024]).decode("utf-8").splitlines()
    assert linhas[0].split(",")[:4] == ["codigo", "alimentador", "carga_pct_2023", "carga_pct_2024"]
    assert linhas[1].startswith("T1,AL1,60.0,130.0,")
    assert linhas[1].endswith(",sim,nao")
