"""Série temporal da rede (item L4-15-serie-temporal-da-rede).

Várias safras da MESMA rede convivem no inquilino — na BDGD da ANEEL, uma safra por ano. Cada safra é uma
`plat.rede` importada pelo importador de L4-01-c; a SÉRIE (`plat.rede_serie`) as amarra em ordem de ano e
produz três leituras que uma safra sozinha não dá:

1. LINHAGEM por COD_ID (`plat.rede_linhagem`), par a par de safras consecutivas, em quatro classes —
   persistente, recodificado, novo, extinto. É o método da casa, medido antes em série pública de seis anos
   de uma distribuidora do Sudeste (`rs-coop/research/20260903_linhagem_bdgd_edp_es.md`): o COD_ID do
   transformador é estável em 99,0-99,4 % dos casos entre safras consecutivas, e o que sobra se resolve
   por unidades consumidoras em comum (Jaccard) e por coordenada.
2. CARREGAMENTO por transformador por safra (`plat.rede_trafo_safra`), pela fórmula de proxy da casa
   (`/home/dev/liga/pipelines/bdgd_temporal/`): carga = ((energia anual das UCs / 8760) / fator de carga)
   / fator de potência / potência nominal. É PROXY de triagem, nunca medição: a energia é a declarada na
   fonte, e os dois fatores são premissa fixa, gravada em `plat.rede_serie.metodo` junto com o resultado.
3. CRESCIMENTO por alimentador por safra (`plat.rede_alimentador_safra`): km de trecho, unidades
   consumidoras, transformadores e potência instalada.

Ressalva que o produto carrega sozinho: quando a série mostra TROCA EM MASSA de potência nominal entre duas
safras (acima de `LIMIAR_TROCA_MASSA` dos transformadores persistentes), a safra mais antiga do par é
marcada `pot_nom_confiavel = false`. A medida que originou a regra: numa safra de 2021 da série pública,
35.770 de 153.124 transformadores (23,4 %) mudaram de placa para 2022, contra 1,0 % nos pares seguintes —
34.721 declarados com 45 kVA em 2021 aparecem com 15 kVA em 2022 e assim ficam. Placa não muda em massa; a
declaração de um ano é que estava errada.

Nada aqui lê arquivo: tudo sai do que o importador já gravou em `plat.rede_no`/`plat.rede_aresta`
(`atributos` preserva os campos da fonte como vieram).
"""

from __future__ import annotations

import time

from psycopg2.extras import Json, execute_values

# Grupo do pacote `eletrica-br` que carrega os transformadores de distribuição e as unidades consumidoras.
GRUPO_TRAFO = "transformador_de_distribuicao"
GRUPO_UC = "unidade_consumidora"

# Fórmula de proxy de carregamento (ativo da casa `liga/pipelines/bdgd_temporal/analyze_temporal.py`).
FATOR_CARGA = 0.45
FATOR_POTENCIA = 0.92
HORAS_ANO = 8760
CAMPOS_ENERGIA = tuple(f"ENE_{m:02d}" for m in range(1, 13))
CAMPO_POT_NOM = "POT_NOM"
CAMPO_ALIMENTADOR = "CTMT"
CAMPO_UC_TRAFO = "UNI_TR_MT"  # a UC de baixa tensão declara o transformador que a alimenta

# Régua da linhagem (método da casa, §2 do relatório de linhagem).
J_RECODIFICADO = 0.6          # Jaccard das UCs identificadas que basta sozinho
J_RECODIFICADO_COM_GEO = 0.3  # Jaccard que basta quando a coordenada também casa
GEO_TOLERANCIA_M = 10.0       # "mesma coordenada" entre safras
UC_POUCAS = 5                 # trafo pequeno: coordenada igual basta, mesmo sem UC em comum
CONFIANCA_GEO = 0.8           # confiança do casamento decidido pela coordenada

# Troca em massa de placa: acima disto, a safra mais antiga do par perde a confiança em POT_NOM.
LIMIAR_TROCA_MASSA = 0.10

CARGA_SAUDAVEL = 80.0   # abaixo disto o transformador é folgado
CARGA_SOBRECARGA = 100.0  # acima disto passou da potência nominal


def metodo() -> dict:
    """Os parâmetros do cálculo, gravados junto com o resultado — número sem a premissa ao lado não vale."""
    return {
        "carga": {
            "formula": "((energia_ano_kwh / horas_ano) / fator_carga) / fator_potencia / pot_nom_kva",
            "fator_carga": FATOR_CARGA,
            "fator_potencia": FATOR_POTENCIA,
            "horas_ano": HORAS_ANO,
            "natureza": "proxy de triagem a partir da energia declarada na fonte, não medição",
        },
        "linhagem": {
            "jaccard_recodificado": J_RECODIFICADO,
            "jaccard_recodificado_com_geometria": J_RECODIFICADO_COM_GEO,
            "geometria_tolerancia_m": GEO_TOLERANCIA_M,
            "uc_poucas": UC_POUCAS,
            "confianca_geometria": CONFIANCA_GEO,
        },
        "pot_nom": {
            "limiar_troca_massa": LIMIAR_TROCA_MASSA,
            "regra": "acima do limiar de transformadores persistentes com placa diferente, a safra mais "
                     "antiga do par é marcada como não confiável para potência nominal",
        },
        "limiares_carga_pct": {"saudavel": CARGA_SAUDAVEL, "sobrecarga": CARGA_SOBRECARGA},
    }


class ErroSerie(Exception):
    """Série sem condição de calcular (menos de duas safras, safra sem transformador)."""


# ------------------------------------------------------------------ leitura das safras


def safras(cur, serie_id: str) -> list[dict]:
    cur.execute(
        "SELECT s.id, s.ano, s.rede_id, s.pot_nom_confiavel, s.pot_nom_motivo, r.nome AS rede_nome "
        "FROM plat.rede_serie_safra s JOIN plat.rede r ON r.id = s.rede_id "
        "WHERE s.serie_id = %s::uuid ORDER BY s.ano",
        (serie_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def _sql_energia() -> str:
    """Soma dos doze meses declarados na UC, com o que não for número valendo zero."""
    partes = [
        f"coalesce((CASE WHEN n.atributos->>'{c}' ~ '^-?[0-9]+([.][0-9]+)?$' "
        f"THEN (n.atributos->>'{c}')::double precision END), 0)"
        for c in CAMPOS_ENERGIA
    ]
    return " + ".join(partes)


def _numero(coluna: str) -> str:
    """Campo de texto do `atributos` lido como número; o que não for número vira NULL, nunca zero."""
    return f"(CASE WHEN {coluna} ~ '^-?[0-9]+([.][0-9]+)?$' THEN ({coluna})::double precision END)"


SQL_POT_NOM = _numero(f"n.atributos->>'{CAMPO_POT_NOM}'")


def _codigos(cur, rede_id: str, grupo: str) -> set[str]:
    cur.execute(
        "SELECT n.codigo_externo FROM plat.rede_no n "
        "JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE n.rede_id = %s::uuid AND g.codigo = %s AND n.codigo_externo IS NOT NULL",
        (rede_id, grupo),
    )
    return {r["codigo_externo"] for r in cur.fetchall()}


def _ucs_por_trafo(cur, rede_id: str) -> dict[str, set[str]]:
    """COD_ID do transformador -> conjunto de COD_ID das unidades consumidoras que o declaram."""
    cur.execute(
        f"SELECT n.atributos->>'{CAMPO_UC_TRAFO}' AS trafo, n.codigo_externo AS uc FROM plat.rede_no n "
        "JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        f"WHERE n.rede_id = %s::uuid AND g.codigo = %s AND n.atributos->>'{CAMPO_UC_TRAFO}' IS NOT NULL "
        "AND n.codigo_externo IS NOT NULL",
        (rede_id, GRUPO_UC),
    )
    out: dict[str, set[str]] = {}
    for r in cur.fetchall():
        out.setdefault(r["trafo"], set()).add(r["uc"])
    return out


def _pares_por_geometria(cur, rede_base: str, rede_alvo: str,
                         somem: set[str], nascem: set[str]) -> set[tuple[str, str]]:
    """Pares (some, nasce) cujos transformadores estão a menos de `GEO_TOLERANCIA_M` um do outro. O
    cruzamento é feito no banco (índice espacial), restrito aos códigos que somem e aos que nascem."""
    if not somem or not nascem:
        return set()
    cur.execute(
        "WITH b AS (SELECT n.codigo_externo AS cod, n.geom FROM plat.rede_no n "
        "            WHERE n.rede_id = %s::uuid AND n.codigo_externo = ANY(%s) AND n.geom IS NOT NULL), "
        "     a AS (SELECT n.codigo_externo AS cod, n.geom FROM plat.rede_no n "
        "            WHERE n.rede_id = %s::uuid AND n.codigo_externo = ANY(%s) AND n.geom IS NOT NULL) "
        "SELECT b.cod AS base, a.cod AS alvo FROM b JOIN a "
        "  ON ST_DWithin(b.geom::geography, a.geom::geography, %s)",
        (rede_base, sorted(somem), rede_alvo, sorted(nascem), GEO_TOLERANCIA_M),
    )
    return {(r["base"], r["alvo"]) for r in cur.fetchall()}


def _jaccard(a: set[str], b: set[str]) -> float:
    uniao = len(a | b)
    return (len(a & b) / uniao) if uniao else 0.0


def casar(somem: set[str], nascem: set[str], ucs_base: dict[str, set[str]],
          ucs_alvo: dict[str, set[str]], ucs_identificadas: set[str],
          pares_geo: set[tuple[str, str]]) -> dict[str, tuple[str, float, dict]]:
    """Casamento dos COD_ID que somem com os que nascem, pelo método da casa. Devolve
    {codigo_base: (codigo_alvo, confianca, evidencia)}.

    Candidatos: os pares com pelo menos uma UC identificada em comum, mais os pares que a coordenada
    aproxima. Régua: Jaccard >= 0,6; ou coordenada igual com Jaccard >= 0,3; ou coordenada igual quando os
    dois lados têm menos de `UC_POUCAS` unidades consumidoras (trafo pequeno não tem carteira para casar).
    Um COD_ID é usado uma vez só de cada lado: os pares são ordenados por confiança e tomados de cima para
    baixo (a "melhor escolha mútua" do relatório da casa, aqui em forma gulosa — dá o mesmo par quando a
    melhor escolha é recíproca, que é o caso de 99 % dos casamentos medidos)."""
    # índice UC identificada -> quem a tem, para não cruzar todos contra todos
    dono_alvo: dict[str, set[str]] = {}
    for cod, ucs in ucs_alvo.items():
        if cod not in nascem:
            continue
        for uc in ucs & ucs_identificadas:
            dono_alvo.setdefault(uc, set()).add(cod)

    candidatos: set[tuple[str, str]] = set()
    for cod in somem:
        for uc in ucs_base.get(cod, set()) & ucs_identificadas:
            for alvo in dono_alvo.get(uc, ()):  # noqa: PLC0206 (o dicionário é o índice, não o laço)
                candidatos.add((cod, alvo))
    candidatos |= {p for p in pares_geo if p[0] in somem and p[1] in nascem}

    pontuados = []
    for base, alvo in candidatos:
        a = ucs_base.get(base, set()) & ucs_identificadas
        b = ucs_alvo.get(alvo, set()) & ucs_identificadas
        j = _jaccard(a, b)
        geo = (base, alvo) in pares_geo
        if j >= J_RECODIFICADO:
            motivo, confianca = "jaccard", j
        elif geo and j >= J_RECODIFICADO_COM_GEO:
            motivo, confianca = "geometria_e_jaccard", CONFIANCA_GEO
        elif geo and len(a) < UC_POUCAS and len(b) < UC_POUCAS:
            motivo, confianca = "geometria_e_poucas_ucs", CONFIANCA_GEO
        else:
            continue
        pontuados.append((confianca, base, alvo, {
            "motivo": motivo, "jaccard": round(j, 4), "geometria": geo,
            "ucs_base": len(a), "ucs_alvo": len(b), "ucs_em_comum": len(a & b),
        }))

    pontuados.sort(key=lambda p: (-p[0], p[1], p[2]))
    escolhidos: dict[str, tuple[str, float, dict]] = {}
    usados_alvo: set[str] = set()
    for confianca, base, alvo, evid in pontuados:
        if base in escolhidos or alvo in usados_alvo:
            continue
        escolhidos[base] = (alvo, confianca, evid)
        usados_alvo.add(alvo)
    return escolhidos


# ------------------------------------------------------------------ gravação


def _gravar_linhagem(cur, tenant_id: int, serie_id: str, entidade: str, ano_base: int, ano_alvo: int,
                     linhas: list[tuple]) -> None:
    if not linhas:
        return
    execute_values(
        cur,
        "INSERT INTO plat.rede_linhagem (tenant_id, serie_id, entidade, ano_base, ano_alvo, "
        "codigo_base, codigo_alvo, classe, confianca, evidencia) VALUES %s",
        [(tenant_id, serie_id, entidade, ano_base, ano_alvo, *linha) for linha in linhas],
        template="(%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)",
        page_size=5000,
    )


def _linhagem_do_par(cur, tenant_id: int, serie_id: str, base: dict, alvo: dict) -> dict:
    """Classifica trafos e UCs entre duas safras consecutivas e grava em `plat.rede_linhagem`."""
    trafos_b = _codigos(cur, base["rede_id"], GRUPO_TRAFO)
    trafos_a = _codigos(cur, alvo["rede_id"], GRUPO_TRAFO)
    ucs_b = _codigos(cur, base["rede_id"], GRUPO_UC)
    ucs_a = _codigos(cur, alvo["rede_id"], GRUPO_UC)

    carteira_b = _ucs_por_trafo(cur, base["rede_id"])
    carteira_a = _ucs_por_trafo(cur, alvo["rede_id"])
    identificadas = ucs_b & ucs_a

    persistentes = trafos_b & trafos_a
    somem = trafos_b - trafos_a
    nascem = trafos_a - trafos_b
    pares_geo = _pares_por_geometria(cur, base["rede_id"], alvo["rede_id"], somem, nascem)
    casados = casar(somem, nascem, carteira_b, carteira_a, identificadas, pares_geo)

    linhas: list[tuple] = []
    for cod in sorted(persistentes):
        a = carteira_b.get(cod, set()) & identificadas
        b = carteira_a.get(cod, set()) & identificadas
        linhas.append((cod, cod, "persistente", 1.0, Json({"jaccard": round(_jaccard(a, b), 4)})))
    for cod in sorted(casados):
        alvo_cod, confianca, evid = casados[cod]
        linhas.append((cod, alvo_cod, "recodificado", round(confianca, 4), Json(evid)))
    usados = {v[0] for v in casados.values()}
    for cod in sorted(nascem - usados):
        linhas.append((None, cod, "novo", 1.0, Json({"ucs": len(carteira_a.get(cod, set()))})))
    for cod in sorted(somem - set(casados)):
        linhas.append((cod, None, "extinto", 1.0, Json({"ucs": len(carteira_b.get(cod, set()))})))
    _gravar_linhagem(cur, tenant_id, serie_id, "trafo", base["ano"], alvo["ano"], linhas)
    contagem = {"trafo": {"persistente": len(persistentes), "recodificado": len(casados),
                          "novo": len(nascem - usados), "extinto": len(somem - set(casados))}}

    # Unidade consumidora: só persistente / novo / extinto. O casamento de UC por perfil de consumo foi
    # MEDIDO na casa e reprovado como número agregado (precisão do melhor par cai a 0,30 em bloco grande;
    # 1.061 elos em cinco pares de anos, 0,1-1,3 % das que saem) — o que sai do arquivo é, na esmagadora
    # maioria, cliente desligado, e afirmar recodificação de UC aqui seria afirmar o que não se mediu.
    linhas_uc: list[tuple] = []
    for cod in sorted(ucs_b & ucs_a):
        linhas_uc.append((cod, cod, "persistente", 1.0, Json({})))
    for cod in sorted(ucs_a - ucs_b):
        linhas_uc.append((None, cod, "novo", 1.0, Json({})))
    for cod in sorted(ucs_b - ucs_a):
        linhas_uc.append((cod, None, "extinto", 1.0, Json({})))
    _gravar_linhagem(cur, tenant_id, serie_id, "uc", base["ano"], alvo["ano"], linhas_uc)
    contagem["uc"] = {"persistente": len(ucs_b & ucs_a), "recodificado": 0,
                      "novo": len(ucs_a - ucs_b), "extinto": len(ucs_b - ucs_a)}
    return contagem


def _placa(cur, rede_id: str) -> dict[str, float]:
    cur.execute(
        f"SELECT n.codigo_externo AS cod, {SQL_POT_NOM} AS pot "
        "FROM plat.rede_no n JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "WHERE n.rede_id = %s::uuid AND g.codigo = %s AND n.codigo_externo IS NOT NULL",
        (rede_id, GRUPO_TRAFO),
    )
    return {r["cod"]: r["pot"] for r in cur.fetchall() if r["pot"] is not None}


def _veredito_pot_nom(cur, tenant_id: int, serie_id: str, lista: list[dict]) -> list[dict]:
    """Marca a safra mais antiga de todo par que mostrar troca em massa de placa. O par seguinte não é
    exigido estável: a regra fica sobre o que se mede no próprio par, e o motivo grava a fração."""
    cur.execute("UPDATE plat.rede_serie_safra SET pot_nom_confiavel = true, pot_nom_motivo = NULL "
                "WHERE serie_id = %s::uuid", (serie_id,))
    vereditos = []
    placas = {s["ano"]: _placa(cur, s["rede_id"]) for s in lista}
    for base, alvo in zip(lista, lista[1:]):
        pb, pa = placas[base["ano"]], placas[alvo["ano"]]
        comuns = set(pb) & set(pa)
        trocaram = sum(1 for c in comuns if pb[c] != pa[c])
        fracao = (trocaram / len(comuns)) if comuns else 0.0
        vereditos.append({"ano": base["ano"], "ano_seguinte": alvo["ano"], "persistentes": len(comuns),
                          "trocaram": trocaram, "fracao": round(fracao, 4),
                          "em_massa": fracao >= LIMIAR_TROCA_MASSA})
    for v in vereditos:
        motivo = None
        if v["em_massa"]:
            motivo = (
                f"troca em massa de potência nominal entre {v['ano']} e {v['ano_seguinte']}: "
                f"{v['trocaram']} de {v['persistentes']} transformadores persistentes ({v['fracao'] * 100:.1f} %) "
                f"mudaram de placa, acima do limiar de {LIMIAR_TROCA_MASSA * 100:.0f} %. Placa de "
                f"transformador não muda em massa em um ano: a potência nominal declarada em {v['ano']} não "
                "serve como placa e não deve ser usada como denominador de carregamento."
            )
        cur.execute(
            "UPDATE plat.rede_serie_safra SET pot_nom_confiavel = %s, pot_nom_motivo = %s "
            "WHERE serie_id = %s::uuid AND ano = %s",
            (not v["em_massa"], motivo, serie_id, v["ano"]),
        )
    return vereditos


def _carga_da_safra(cur, tenant_id: int, serie_id: str, safra: dict, confiavel: bool) -> int:
    """Grava `plat.rede_trafo_safra` para uma safra: placa, energia anual das UCs, número de UCs e o
    carregamento em porcentagem. Tudo numa consulta de conjunto — a energia sai do que o importador
    preservou em `atributos`."""
    cur.execute(
        "WITH trafo AS ("
        "  SELECT n.codigo_externo AS cod, "
        f"        {SQL_POT_NOM} AS pot, "
        f"        n.atributos->>'{CAMPO_ALIMENTADOR}' AS alimentador "
        "  FROM plat.rede_no n JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "  JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "  WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo_trafo)s AND n.codigo_externo IS NOT NULL"
        "), uc AS ("
        f"  SELECT n.atributos->>'{CAMPO_UC_TRAFO}' AS cod, count(*) AS n_uc, "
        f"        sum({_sql_energia()}) AS energia "
        "  FROM plat.rede_no n JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "  JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "  WHERE n.rede_id = %(rede)s::uuid AND g.codigo = %(grupo_uc)s "
        f"    AND n.atributos->>'{CAMPO_UC_TRAFO}' IS NOT NULL "
        "  GROUP BY 1"
        ") "
        "INSERT INTO plat.rede_trafo_safra (tenant_id, serie_id, ano, codigo, alimentador, pot_nom_kva, "
        "  energia_ano_kwh, n_uc, carga_pct, pot_nom_confiavel) "
        "SELECT %(tenant)s, %(serie)s::uuid, %(ano)s, trafo.cod, trafo.alimentador, trafo.pot, "
        "  coalesce(uc.energia, 0), coalesce(uc.n_uc, 0), "
        "  CASE WHEN trafo.pot > 0 THEN "
        "    ((coalesce(uc.energia, 0) / %(horas)s) / %(fc)s) / %(fp)s / trafo.pot * 100.0 END, "
        "  %(confiavel)s "
        "FROM trafo LEFT JOIN uc ON uc.cod = trafo.cod "
        "ON CONFLICT (serie_id, ano, codigo) DO NOTHING",
        {"rede": safra["rede_id"], "grupo_trafo": GRUPO_TRAFO, "grupo_uc": GRUPO_UC,
         "tenant": tenant_id, "serie": serie_id, "ano": safra["ano"], "horas": HORAS_ANO,
         "fc": FATOR_CARGA, "fp": FATOR_POTENCIA, "confiavel": confiavel},
    )
    return cur.rowcount


def _crescimento_da_safra(cur, tenant_id: int, serie_id: str, safra: dict) -> int:
    """Grava `plat.rede_alimentador_safra`: km de trecho, UCs, transformadores e potência instalada por
    alimentador (o campo do alimentador que a fonte declara em cada elemento)."""
    cur.execute(
        "WITH aresta AS ("
        f"  SELECT a.atributos->>'{CAMPO_ALIMENTADOR}' AS cod, "
        "         sum(coalesce(a.comprimento_m, 0)) / 1000.0 AS km "
        "  FROM plat.rede_aresta a WHERE a.rede_id = %(rede)s::uuid "
        f"    AND a.atributos->>'{CAMPO_ALIMENTADOR}' IS NOT NULL GROUP BY 1"
        "), no AS ("
        f"  SELECT n.atributos->>'{CAMPO_ALIMENTADOR}' AS cod, "
        "         count(*) FILTER (WHERE g.codigo = %(grupo_uc)s) AS n_uc, "
        "         count(*) FILTER (WHERE g.codigo = %(grupo_trafo)s) AS n_trafo, "
        f"         coalesce(sum({SQL_POT_NOM}) "
        "                  FILTER (WHERE g.codigo = %(grupo_trafo)s), 0) AS pot "
        "  FROM plat.rede_no n JOIN plat.rede_tipo t ON t.id = n.tipo_id "
        "  JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        f"  WHERE n.rede_id = %(rede)s::uuid AND n.atributos->>'{CAMPO_ALIMENTADOR}' IS NOT NULL "
        "    AND g.codigo IN (%(grupo_uc)s, %(grupo_trafo)s) GROUP BY 1"
        "), cod AS (SELECT cod FROM aresta UNION SELECT cod FROM no) "
        "INSERT INTO plat.rede_alimentador_safra (tenant_id, serie_id, ano, codigo, km_rede, n_uc, "
        "  n_trafo, pot_inst_kva) "
        "SELECT %(tenant)s, %(serie)s::uuid, %(ano)s, cod.cod, coalesce(aresta.km, 0), "
        "  coalesce(no.n_uc, 0), coalesce(no.n_trafo, 0), coalesce(no.pot, 0) "
        "FROM cod LEFT JOIN aresta ON aresta.cod = cod.cod LEFT JOIN no ON no.cod = cod.cod "
        "ON CONFLICT (serie_id, ano, codigo) DO NOTHING",
        {"rede": safra["rede_id"], "grupo_uc": GRUPO_UC, "grupo_trafo": GRUPO_TRAFO,
         "tenant": tenant_id, "serie": serie_id, "ano": safra["ano"]},
    )
    return cur.rowcount


def calcular(cur, tenant_id: int, serie_id: str) -> dict:
    """Recalcula a série inteira: apaga o que havia e grava linhagem, carregamento e crescimento. É
    idempotente por construção (recalcular duas vezes dá o mesmo resultado)."""
    t0 = time.monotonic()
    lista = safras(cur, serie_id)
    if len(lista) < 2:
        raise ErroSerie("a série precisa de pelo menos duas safras para ter linhagem")

    for tabela in ("rede_linhagem", "rede_trafo_safra", "rede_alimentador_safra"):
        cur.execute(f"DELETE FROM plat.{tabela} WHERE serie_id = %s::uuid", (serie_id,))

    contagens = {}
    for base, alvo in zip(lista, lista[1:]):
        contagens[f"{base['ano']}-{alvo['ano']}"] = _linhagem_do_par(cur, tenant_id, serie_id, base, alvo)

    vereditos = _veredito_pot_nom(cur, tenant_id, serie_id, lista)
    nao_confiaveis = {v["ano"] for v in vereditos if v["em_massa"]}
    trafos = 0
    alimentadores = 0
    for safra in lista:
        trafos += _carga_da_safra(cur, tenant_id, serie_id, safra, safra["ano"] not in nao_confiaveis)
        alimentadores += _crescimento_da_safra(cur, tenant_id, serie_id, safra)

    resumo = {
        "safras": [s["ano"] for s in lista],
        "linhagem": contagens,
        "pot_nom": vereditos,
        "trafo_safra": trafos,
        "alimentador_safra": alimentadores,
        "duracao_ms": int((time.monotonic() - t0) * 1000),
    }
    cur.execute(
        "UPDATE plat.rede_serie SET calculado_em = now(), metodo = %s WHERE id = %s::uuid",
        (Json({**metodo(), "ultimo_resumo": resumo}), serie_id),
    )
    return resumo


# ------------------------------------------------------------------ leituras


def tendencia(cur, serie_id: str, so_viraram_sobrecarga: bool = False) -> list[dict]:
    """Uma linha por transformador com o carregamento de cada safra, o primeiro e o último valor, a
    variação em pontos percentuais e se ele PASSOU de folgado (< 80 %) a acima da potência nominal
    (> 100 %) entre a primeira e a última safra em que aparece. É a tabela exportável do item."""
    cur.execute(
        "WITH s AS (SELECT codigo, ano, carga_pct, pot_nom_kva, alimentador, n_uc, pot_nom_confiavel "
        "           FROM plat.rede_trafo_safra WHERE serie_id = %s::uuid), "
        "ext AS (SELECT codigo, min(ano) AS ano_ini, max(ano) AS ano_fim FROM s "
        "        WHERE carga_pct IS NOT NULL GROUP BY codigo) "
        "SELECT s.codigo, "
        "       jsonb_object_agg(s.ano::text, jsonb_build_object("
        "         'carga_pct', round(s.carga_pct::numeric, 2), 'pot_nom_kva', s.pot_nom_kva, "
        "         'n_uc', s.n_uc, 'pot_nom_confiavel', s.pot_nom_confiavel)) AS por_ano, "
        "       ext.ano_ini, ext.ano_fim, "
        "       max(s.carga_pct) FILTER (WHERE s.ano = ext.ano_ini) AS carga_ini, "
        "       max(s.carga_pct) FILTER (WHERE s.ano = ext.ano_fim) AS carga_fim, "
        "       max(s.alimentador) FILTER (WHERE s.ano = ext.ano_fim) AS alimentador, "
        "       bool_and(s.pot_nom_confiavel) AS pot_nom_confiavel "
        "FROM s JOIN ext ON ext.codigo = s.codigo GROUP BY s.codigo, ext.ano_ini, ext.ano_fim "
        "ORDER BY s.codigo",
        (serie_id,),
    )
    itens = []
    for r in cur.fetchall():
        ini, fim = r["carga_ini"], r["carga_fim"]
        virou = (ini is not None and fim is not None and ini < CARGA_SAUDAVEL and fim > CARGA_SOBRECARGA
                 and r["ano_fim"] > r["ano_ini"])
        if so_viraram_sobrecarga and not virou:
            continue
        anos = max(r["ano_fim"] - r["ano_ini"], 1)
        itens.append({
            "codigo": r["codigo"], "alimentador": r["alimentador"], "por_ano": r["por_ano"],
            "ano_inicial": r["ano_ini"], "ano_final": r["ano_fim"],
            "carga_inicial_pct": None if ini is None else round(ini, 2),
            "carga_final_pct": None if fim is None else round(fim, 2),
            "variacao_pp": None if (ini is None or fim is None) else round(fim - ini, 2),
            "variacao_pp_ano": None if (ini is None or fim is None) else round((fim - ini) / anos, 2),
            "virou_sobrecarga": virou,
            "pot_nom_confiavel": r["pot_nom_confiavel"],
        })
    return itens


def crescimento(cur, serie_id: str) -> list[dict]:
    """Crescimento por alimentador: uma linha por alimentador, com os números de cada safra e a variação
    entre a primeira e a última em que ele aparece."""
    cur.execute(
        "SELECT codigo, ano, km_rede, n_uc, n_trafo, pot_inst_kva FROM plat.rede_alimentador_safra "
        "WHERE serie_id = %s::uuid ORDER BY codigo, ano",
        (serie_id,),
    )
    por_codigo: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        por_codigo.setdefault(r["codigo"], []).append(dict(r))
    itens = []
    for codigo, linhas in sorted(por_codigo.items()):
        ini, fim = linhas[0], linhas[-1]
        itens.append({
            "codigo": codigo,
            "por_ano": {str(x["ano"]): {"km_rede": round(x["km_rede"], 3), "n_uc": x["n_uc"],
                                        "n_trafo": x["n_trafo"], "pot_inst_kva": x["pot_inst_kva"]}
                        for x in linhas},
            "ano_inicial": ini["ano"], "ano_final": fim["ano"],
            "delta_km": round(fim["km_rede"] - ini["km_rede"], 3),
            "delta_uc": fim["n_uc"] - ini["n_uc"],
            "delta_trafo": fim["n_trafo"] - ini["n_trafo"],
        })
    return itens


def contagem_linhagem(cur, serie_id: str) -> list[dict]:
    cur.execute(
        "SELECT entidade, ano_base, ano_alvo, classe, count(*) AS n FROM plat.rede_linhagem "
        "WHERE serie_id = %s::uuid GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 4",
        (serie_id,),
    )
    return [dict(r) for r in cur.fetchall()]
