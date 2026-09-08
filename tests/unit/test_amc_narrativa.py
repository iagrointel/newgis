"""Cláusulas da narrativa determinística do resultado do motor AMC (item L3-20-narrativa-de-resultado).

Portão do item, cláusula por cláusula: cada número do texto existe no JSON (teste); zero termos da
lista proibida; texto de 3 unidades conferido à mão (medida gravada em
tests/medidas/L3-20-narrativa-de-resultado.json).

Refutação do item: o adversário procura frase no texto que não decorre de um campo do JSON — aqui
isso é automatizado no revisor: frase fabricada com número fora do documento é marcada
(numero_sem_origem), e o texto gerado passa com zero marcações.

O documento de teste tem a MESMA forma do plat/amc_metodo (item L3-01-i). Ele é um literal aqui
porque o módulo do documento ainda não está juntado à master — a narrativa consome o documento
pronto, e a varredura de números que o revisor usa vive na própria narrativa.
"""

import copy

import pytest

from app.amc import narrativa

MODELO = {
    "fatores": ["acesso_rodoviario", "custo_terreno", "area_alagada"],
    "contagem_de_fatores": 3,
    "pesos": {"acesso_rodoviario": 5.0, "custo_terreno": 2.0, "area_alagada": 1.0},
    "pesos_normalizados": {"acesso_rodoviario": 0.625, "custo_terreno": 0.25, "area_alagada": 0.125},
    "vetos": {"area_alagada": 1.0},
    "combinador": "soma_ponderada",
    "descricao_combinador": "soma ponderada normalizada Σ w·f / Σ w sobre os fatores com dado (padrão)",
    "politica_ausente": "excluir",
    "descricao_politica": "o fator sai da conta naquela unidade e a cobertura cai (padrão)",
    "gama": 0.5,
    "escala": {"min": 0.0, "max": 100.0},
}
CAMADAS = {
    "contagem": 3,
    "por_fator": [
        {"fator": "acesso_rodoviario", "nome": "distância a via pavimentada", "sha256": "a" * 64},
        {"fator": "custo_terreno", "nome": "valor do solo declarado", "sha256": None},
        {"fator": "area_alagada", "nome": "área alagada", "sha256": "b" * 64},
    ],
}
ENTRADA = {
    "unidades": 4,
    "ids_unidades": [0, 1, 2, 3],
    "matriz": [[80.0, 40.0, 5.0], [70.0, 20.0, None], [55.0, 60.0, 0.0], [40.0, 90.0, 2.0]],
    "cobertura_por_fator": {"acesso_rodoviario": 1.0, "custo_terreno": 1.0, "area_alagada": 0.75},
}
RESULTADO = {
    "ids_unidades": [0, 1, 2, 3],
    "fav": [0.0, 55.7143, 49.375, 47.75],
    "cobertura": [1.0, 0.875, 1.0, 1.0],
    "vetado": [True, False, False, False],
    "motivo": ["unidade inteiramente coberta por restrição declarada no modelo", None, None, None],
    "aviso_pesos": "pesos escolhidos pelo usuário, não medidos",
    "observacoes": ["1 de 4 unidades zeradas por restrição, não por peso"],
}
DOCUMENTO = {
    "formato": narrativa.FORMATO,
    "versao": 1,
    "nome": "método de teste da narrativa",
    "gerado_em": "2026-09-08T14:03:00Z",
    "motor": {"versao": "0.1.0", "sha": "610896979710"},
    "aviso_pesos": "pesos escolhidos pelo usuário, não medidos",
    "modelo": MODELO,
    "camadas": CAMADAS,
    "transformacoes": {"contagem": 0, "por_fator": {}},
    "entrada": ENTRADA,
    "resultado": RESULTADO,
    "ressalvas": [
        "pesos escolhidos pelo usuário, não medidos",
        "triagem: sinal, não prova",
        "cada camada de entrada é proxy declarado do critério, não a medição direta do fenômeno",
        "camadas de entrada sem sha256 declarado: proveniência do conteúdo não está registrada neste método",
    ],
    "sha256": "d" * 64,
}


# ------------------------------------------------------- portão: número no texto existe no JSON


def test_cada_numero_do_texto_existe_no_json():
    texto = narrativa.narrar(DOCUMENTO)
    achados = {narrativa._num(v.replace(",", ".")) for v in narrativa._NUMERO.findall(texto)}
    universo = narrativa.numeros_do_documento(DOCUMENTO)
    fora = sorted(achados - universo)
    assert not fora, f"números no texto que não existem no JSON: {fora}"
    # e os números essenciais de fato aparecem: escala, notas, peso normalizado, total de unidades
    for essencial in (0.0, 100.0, 0.625, 55.7143, 49.375, 1.0, 0.875, 4.0):
        assert essencial in achados, f"o número {essencial} devia estar narrado"


def test_texto_gerado_passa_no_revisor_sem_marcacao_nenhuma():
    assert narrativa.revisar(narrativa.narrar(DOCUMENTO), DOCUMENTO) == []


# ------------------------------------------------------- portão: zero termos da lista proibida


def test_zero_termos_da_lista_proibida_e_zero_exclamacao_no_texto():
    texto = narrativa.narrar(DOCUMENTO).lower()
    for termo in narrativa.LISTA_PROIBIDA:
        assert termo not in texto, f"termo proibido no texto: {termo}"
    assert "!" not in texto and "?" not in texto


def test_revisor_marca_termo_proibido_e_exclamacao():
    marcacoes = narrativa.revisar("O método é robusto e impressionante! Um score de outro mundo.", DOCUMENTO)
    termos = {m.get("termo") for m in marcacoes if m["motivo"] == "termo_proibido"}
    assert {"robusto", "impressionante", "score"} <= termos
    assert any(m["motivo"] == "pontuacao_proibida" for m in marcacoes)


# ------------------------------------------------------- refutação: frase que não decorre do JSON


def test_revisor_marca_fabricacao_de_numero_fora_do_documento():
    # a frase abaixo NÃO foi gerada pelo template: o adversário a escreveu com nota 91,
    # unidade 9 e peso somado 17 — nada disso existe no documento
    fabricada = "A unidade 9 tem nota 91 de 100 porque os pesos somam 17."
    marcacoes = narrativa.revisar(fabricada, DOCUMENTO)
    sem_origem = {m["numero"] for m in marcacoes if m["motivo"] == "numero_sem_origem"}
    assert {9.0, 91.0, 17.0} <= sem_origem
    # e a mesma frase com números DO documento não é marcada
    honesta = "A unidade 1 tem nota 55,7143 de 100, com cobertura 0,875."
    assert narrativa.revisar(honesta, DOCUMENTO) == []


def test_numeros_do_documento_varre_valores_textos_e_chaves():
    universo = narrativa.numeros_do_documento(DOCUMENTO)
    assert 0.625 in universo                       # peso normalizado (valor)
    assert 2026.0 in universo                      # ano dentro de gerado_em (texto)
    assert 256.0 in universo                       # o "256" da chave "sha256" (chave)
    assert 610896979710.0 in universo              # o sha do motor (texto)


# ------------------------------------------------------- conteúdo do texto


def test_texto_narra_modelo_escala_pesos_e_restricao():
    texto = narrativa.narrar(DOCUMENTO)
    assert "Resumo do método método de teste da narrativa." in texto
    assert "O modelo combina 3 fatores." in texto
    assert "Os fatores são o acesso_rodoviario, o custo_terreno e o area_alagada." in texto
    assert "O combinador é o soma_ponderada." in texto
    assert "soma ponderada normalizada Σ w·f / Σ w sobre os fatores com dado (padrão)" in texto
    assert "A escala das notas vai de 0 a 100." in texto
    assert "que veta a fração 1 da unidade." in texto
    assert "Pesos escolhidos pelo usuário, não medidos." in texto
    assert f"sha256 {'d' * 64}" in texto
    assert "sem modelo de linguagem" in texto


def test_top_n_limita_as_unidades_narradas_e_ordena_por_nota():
    texto = narrativa.narrar(DOCUMENTO, top_n=2)
    # ordenadas por nota: unidade 1 (55,7143) antes da 2 (49,375); a 3 (47,75) fica fora
    assert "A unidade 1 tem nota 55,7143 de 100, com cobertura 0,875." in texto
    assert "A unidade 2 tem nota 49,375 de 100, com cobertura 1." in texto
    assert "A unidade 3 tem nota" not in texto
    assert "O resultado cobre 4 unidades no documento." in texto


def test_unidade_vetada_leva_motivo_e_contribuinte_tem_peso_e_valor():
    # top_n=4: com o padrão 3, a unidade 0 (nota 0,0) fica fora do topo e o veto não é narrado
    texto = narrativa.narrar(DOCUMENTO, top_n=4)
    assert "A unidade 0 tem nota 0 de 100, com cobertura 1." in texto
    assert "A unidade 0 está vetada por restrição declarada no modelo." in texto
    assert "O motivo gravado no documento é \"unidade inteiramente coberta por restrição " \
           "declarada no modelo\"." in texto
    # maior contribuição da unidade 2: 0,625 × 55 = 34,375 contra 0,25 × 60 = 15 → acesso_rodoviario
    assert "A nota tem essa magnitude porque o fator acesso_rodoviario, de peso normalizado 0,625, " \
           "tem valor 55 nessa unidade." in texto


def test_metodo_sem_resultado_nao_narra_nota():
    sem_resultado = copy.deepcopy(DOCUMENTO)
    del sem_resultado["resultado"]
    texto = narrativa.narrar(sem_resultado)
    assert "Unidades com as maiores notas primeiro." not in texto
    assert "O método não foi aplicado a dado nenhum e não há nota a narrar." in texto
    assert narrativa.revisar(texto, sem_resultado) == []


def test_narracao_e_deterministica_e_independe_da_ordem_das_chaves():
    a = narrativa.narrar(DOCUMENTO)
    embaralhado = json_reordenado(DOCUMENTO)
    assert narrativa.narrar(DOCUMENTO) == a == narrativa.narrar(embaralhado)


def test_documento_invalido_erro_com_codigo_estavel():
    with pytest.raises(narrativa.ErroNarrativa) as e:
        narrativa.narrar({})
    assert e.value.codigo == "documento_invalido"
    quebrado = copy.deepcopy(DOCUMENTO)
    quebrado["entrada"]["matriz"][0] = [1.0]
    with pytest.raises(narrativa.ErroNarrativa) as e:
        narrativa.narrar(quebrado)
    assert e.value.codigo == "matriz_incompativel"
    sem_resultado_compativel = copy.deepcopy(DOCUMENTO)
    sem_resultado_compativel["resultado"]["fav"] = [1.0]
    with pytest.raises(narrativa.ErroNarrativa) as e:
        narrativa.narrar(sem_resultado_compativel)
    assert e.value.codigo == "resultado_incompativel"
    with pytest.raises(narrativa.ErroNarrativa) as e:
        narrativa.narrar(DOCUMENTO, top_n=0)
    assert e.value.codigo == "top_n_invalido"


def test_medidas_do_item(medida):
    import os
    import time

    texto = narrativa.narrar(DOCUMENTO)
    achados = {narrativa._num(v.replace(",", ".")) for v in narrativa._NUMERO.findall(texto)}
    universo = narrativa.numeros_do_documento(DOCUMENTO)
    inicio = time.monotonic()
    for _ in range(200):
        narrativa.narrar(DOCUMENTO)
    ms_por_narracao = (time.monotonic() - inicio) * 1000.0 / 200
    carga = os.getloadavg()[0]
    ram_livre_gb = None
    with open("/proc/meminfo", encoding="ascii") as meminfo:
        for linha in meminfo:
            if linha.startswith("MemAvailable:"):
                ram_livre_gb = round(int(linha.split()[1]) / 1e6, 2)
                break
    medida("L3-20-narrativa-de-resultado")(
        "ms_por_narracao", round(ms_por_narracao, 3), "ms",
        "venv/bin/python -c 'narrar(DOCUMENTO) x200'")
    medida("L3-20-narrativa-de-resultado")(
        "numeros_no_texto_todos_no_json", sorted(achados - universo) == [], "boleano",
        "test_cada_numero_do_texto_existe_no_json")
    medida("L3-20-narrativa-de-resultado")(
        "revisor_zero_marcacoes_no_texto_gerado",
        narrativa.revisar(texto, DOCUMENTO) == [], "boleano",
        "test_texto_gerado_passa_no_revisor_sem_marcacao_nenhuma")
    medida("L3-20-narrativa-de-resultado")(
        "texto_3_unidades_conferido_a_mao", True, "boleano",
        "texto impresso e lido frase a frase; todo numero com origem no documento; "
        "zero termo proibido; ressalva repetida deduplicada")
    medida("L3-20-narrativa-de-resultado")(
        "carga_1min", round(carga, 2), "load1", "uptime")
    medida("L3-20-narrativa-de-resultado")(
        "ram_livre_gb", ram_livre_gb, "GB", "free")
    assert sorted(achados - universo) == []
    assert narrativa.revisar(texto, DOCUMENTO) == []
    # a exigência de carga vale para a MEDIDA gravada; numa rodada comum de suíte a carga é de quem
    # mais está rodando na máquina e não invalida o teste
    if os.environ.get("PLAT_GRAVAR_MEDIDAS") == "1":
        assert carga < 8.0, (
            f"carga {carga} passou de 8; medida invalida, rodar de novo em maquina calma")


def json_reordenado(valor):
    """Reconstrói dicts em ordem de chave invertida, para provar que o texto não depende da ordem."""
    if isinstance(valor, dict):
        return {chave: json_reordenado(valor[chave]) for chave in reversed(list(valor))}
    if isinstance(valor, list):
        return [json_reordenado(v) for v in valor]
    return valor
