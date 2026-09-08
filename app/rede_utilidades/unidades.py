"""Unidade declarada × unidade detectada, por campo numérico da BDGD (item
L4-01-e-dicionario-unidades-bdgd).

O dicionário do pacote `eletrica-br` declara `COMP` em quilômetros e `ENE_SUM` em megawatt-hora, porque é
isso que o Módulo 10 da ANEEL escreve. O extrato de referência da casa traz os dois em metros e em
quilowatt-hora — medido pelo item L4-01-c (razão entre o COMP somado e o comprimento geodésico do mesmo
trecho: 1,024) e pelo item L4-04-c (energia por unidade consumidora). Ou seja: a unidade não é fixada pela
BDGD, é uma escolha de quem extraiu o arquivo.

Daí a regra deste módulo, que vale para toda a linha L4: **a unidade é medida no arquivo, gravada na
auditoria da importação, e lida de lá por quem soma ou exporta**. O dicionário continua dizendo o que a
ANEEL declara, e passa a dizer também que a unidade efetiva vem do arquivo. Quem consome (sumário por
subrede, exportador OpenDSS) nunca multiplica por mil de cabeça.

Como se mede cada família:

* `comp` (comprimento do trecho): razão entre a soma do COMP e a soma do comprimento geodésico das mesmas
  geometrias. Perto de 1 o arquivo está em metros; perto de 0,001, em quilômetros. É a medida do item
  L4-01-c, que aqui só ganhou nome e casa própria.
* `ene` (energia da unidade consumidora, ENE_01..ENE_12 e ENE_SUM): a energia anual declarada comparada
  com dois tetos que não dependem dela — a potência instalada dos transformadores (Σ POT_NOM × 8.760 h,
  o máximo físico que aquela rede entrega num ano) e o número de unidades consumidoras (energia média por
  unidade e por mês). Em quilowatt-hora a razão contra o teto é o fator de carga da rede, algo entre 0,05
  e 0,6; em megawatt-hora ela cai mil vezes. Quando as duas âncoras existem e discordam, o resultado é
  `indeterminada` — dizer "não sei" é melhor que escolher a unidade errada e multiplicar tudo por mil.

Sem medida possível (coluna ausente, arquivo sem geometria, rede sem transformador nem consumidor) a
unidade fica `indeterminada`: o valor entra como está no arquivo, sem conversão nenhuma, e a origem
`nao_medida` sai escrita ao lado do número. Aplicar o fator do dicionário nesse caso seria justamente o
erro que este item existe para evitar. Nada é convertido em silêncio."""

from __future__ import annotations

# família de campo -> unidade da base em que a plataforma guarda o valor
BASE = {"comp": "m", "ene": "kWh"}

# o que o dicionário do pacote eletrica-br declara (Módulo 10 da ANEEL)
DECLARADA = {"comp": "km", "ene": "MWh"}

# unidade -> fator que leva o valor à unidade da base
FATOR = {"m": 1.0, "km": 1000.0, "kWh": 1.0, "MWh": 1000.0}

# faixas da razão medida -> unidade. Entre uma faixa e a outra há um vão de propósito: razão que cai no vão
# não decide nada e vira `indeterminada`.
FAIXA_COMP = (("m", 0.5, 2.0), ("km", 0.0005, 0.002))
# razão energia anual declarada / (Σ POT_NOM × 8.760 h). Em kWh é o fator de carga; em MWh, mil vezes menor.
FAIXA_ENE_POTENCIA = (("kWh", 0.01, 3.0), ("MWh", 0.00001, 0.003))
# energia média por unidade consumidora e por mês
FAIXA_ENE_POR_UC = (("kWh", 20.0, 100000.0), ("MWh", 0.02, 100.0))

HORAS_ANO = 8760.0
MESES = 12


def _classificar(razao: float, faixas) -> str:
    for unidade, minimo, maximo in faixas:
        if minimo <= razao <= maximo:
            return unidade
    return "indeterminada"


def fator_para_base(familia: str, unidade: str) -> float | None:
    """Fator que leva o valor lido do arquivo à unidade da base (metro, quilowatt-hora). None quando a
    unidade é desconhecida — o chamador não converte e diz por quê."""
    del familia
    return FATOR.get(unidade)


def detectar_comprimento(soma_comp: float, soma_geodesica_m: float, trechos: int) -> dict:
    """Unidade do COMP pela razão contra o comprimento geodésico das mesmas geometrias."""
    if trechos <= 0 or soma_geodesica_m <= 0:
        return {"familia": "comp", "declarada": DECLARADA["comp"], "detectada": "indeterminada",
                "fator_para_base": None, "base": BASE["comp"], "origem": "sem_medida",
                "razao_comp_sobre_geodesico": None, "trechos_medidos": trechos,
                "explicacao": "nenhum trecho com COMP e geometria: sem base de comparação"}
    razao = soma_comp / soma_geodesica_m
    unidade = _classificar(razao, FAIXA_COMP)
    fator = FATOR.get(unidade)
    return {
        "familia": "comp",
        "declarada": DECLARADA["comp"],
        "detectada": "metros" if unidade == "m" else ("quilometros" if unidade == "km" else "indeterminada"),
        "unidade": unidade if unidade != "indeterminada" else None,
        "fator_para_base": fator,
        "base": BASE["comp"],
        "origem": "detectada" if fator else "sem_faixa",
        "razao_comp_sobre_geodesico": round(razao, 6),
        "soma_comp_declarada": round(soma_comp, 3),
        "soma_geodesica_m": round(soma_geodesica_m, 3),
        "trechos_medidos": trechos,
        "explicacao": (
            "razão entre o COMP somado e o comprimento geodésico somado das mesmas geometrias"
            if fator else
            f"razão {razao:.6f} fora das faixas de metro (0,5-2) e de quilômetro (0,0005-0,002)"
        ),
    }


def detectar_energia(energia_anual: float, unidades_consumidoras: int, kva_instalado: float) -> dict:
    """Unidade da energia (ENE_01..12 / ENE_SUM) por ordem de grandeza, contra dois tetos independentes:
    a potência instalada dos transformadores e o número de unidades consumidoras. As duas âncoras têm de
    concordar quando as duas existem."""
    saida = {
        "familia": "ene",
        "declarada": DECLARADA["ene"],
        "base": BASE["ene"],
        "energia_anual_declarada": round(float(energia_anual), 3),
        "unidades_consumidoras": unidades_consumidoras,
        "kva_instalado": round(float(kva_instalado), 3),
    }
    por_potencia = por_uc = "indeterminada"
    if kva_instalado > 0 and energia_anual > 0:
        razao = energia_anual / (kva_instalado * HORAS_ANO)
        saida["razao_sobre_potencia_instalada"] = round(razao, 8)
        por_potencia = _classificar(razao, FAIXA_ENE_POTENCIA)
    if unidades_consumidoras > 0 and energia_anual > 0:
        media = energia_anual / (unidades_consumidoras * MESES)
        saida["energia_media_por_uc_mes"] = round(media, 6)
        por_uc = _classificar(media, FAIXA_ENE_POR_UC)
    saida["por_potencia_instalada"] = por_potencia
    saida["por_unidade_consumidora"] = por_uc

    candidatas = {u for u in (por_potencia, por_uc) if u != "indeterminada"}
    if len(candidatas) == 1:
        unidade = candidatas.pop()
        saida.update({
            "detectada": unidade, "unidade": unidade, "fator_para_base": FATOR[unidade],
            "origem": "detectada",
            "explicacao": "ordem de grandeza da energia anual contra a potência instalada e o número de "
                          "unidades consumidoras",
        })
        return saida
    if len(candidatas) > 1:
        saida.update({
            "detectada": "indeterminada", "unidade": None, "fator_para_base": None, "origem": "conflito",
            "explicacao": "as duas âncoras discordam (potência instalada e número de unidades "
                          "consumidoras apontam unidades diferentes): nada é convertido",
        })
        return saida
    saida.update({
        "detectada": "indeterminada", "unidade": None, "fator_para_base": None, "origem": "sem_medida",
        "explicacao": "sem energia declarada, sem transformador com potência e sem unidade consumidora: "
                      "não há teto contra o qual medir a ordem de grandeza",
    })
    return saida


def _consolidar(familia: str, entradas: list[dict]) -> dict:
    """Uma unidade por família a partir das medidas por camada. Camadas que discordam entre si não viram
    média: nada é convertido e a origem diz que houve conflito."""
    declarada = DECLARADA[familia]
    # Sem medida, o valor NÃO é convertido: fator 1, e a origem diz que a unidade não foi medida. Aplicar
    # o fator do dicionário aqui seria o erro que este item existe para evitar — o dicionário declara km e
    # MWh, e o extrato de referência da casa traz metro e kWh; multiplicar por mil de cabeça estragaria o
    # número em vez de corrigi-lo.
    padrao = {"familia": familia, "unidade": None, "fator_para_base": 1.0,
              "base": BASE[familia], "declarada": declarada, "origem": "nao_medida",
              "explicacao": "nenhuma medida de unidade na auditoria desta rede: o valor entra como está no "
                            "arquivo, e o dicionário declara " + declarada}
    medidas = {e.get("unidade") for e in entradas if e.get("origem") == "detectada" and e.get("unidade")}
    if not medidas:
        return padrao
    if len(medidas) > 1:
        return {**padrao, "origem": "conflito_entre_camadas",
                "camadas_em_conflito": sorted({e.get("camada", "?") for e in entradas
                                               if e.get("origem") == "detectada"}),
                "explicacao": "as camadas do arquivo foram medidas com unidades diferentes para o mesmo "
                              "campo: nada é convertido, e o conflito fica escrito"}
    unidade = medidas.pop()
    return {"familia": familia, "unidade": unidade, "fator_para_base": FATOR[unidade],
            "base": BASE[familia], "declarada": declarada, "origem": "detectada",
            "camadas": sorted({e.get("camada", "?") for e in entradas if e.get("origem") == "detectada"}),
            "explicacao": "unidade medida no próprio arquivo pela importação (auditoria da importação)"}


def consolidar(por_campo: dict) -> dict:
    """`{campo: medida}` da auditoria -> `{familia: {unidade, fator_para_base, origem}}`."""
    por_familia: dict[str, list[dict]] = {}
    for medida in (por_campo or {}).values():
        familia = medida.get("familia")
        if familia in BASE:
            por_familia.setdefault(familia, []).append(medida)
    return {familia: _consolidar(familia, por_familia.get(familia, [])) for familia in BASE}


def fatores_da_rede(cur, rede_id: str) -> dict:
    """Unidade por família para uma rede, lida da ÚLTIMA importação concluída (`plat.rede_importacao`).

    É por aqui que o sumário por subrede e o exportador OpenDSS descobrem se o arquivo veio em metro ou em
    quilômetro, em quilowatt-hora ou em megawatt-hora. Rede sem importação registrada (carga por outro
    caminho) devolve fator 1 com `origem: "nao_medida"` — o valor entra como está no arquivo e o chamador
    grava essa origem no que devolve, para que ninguém confunda medido com suposto."""
    cur.execute(
        "SELECT unidades FROM plat.rede_importacao WHERE rede_id = %s::uuid AND estado = 'concluida' "
        "AND unidades IS NOT NULL ORDER BY coalesce(concluido_em, atualizado_em) DESC, "
        "atualizado_em DESC LIMIT 1",
        (rede_id,),
    )
    linha = cur.fetchone()
    return consolidar(linha["unidades"] if linha else {})
