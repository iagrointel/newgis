"""Verificações estruturais da validação incremental por área suja (item L4-03-d-areas-sujas-e-validacao;
ADR docs/adr/20260907T1243-areas-sujas-e-validacao.md).

O motor de regras (`app/rede_utilidades/regras.py`, item L4-03-a) já lança DOIS códigos no applyEdits, em
tempo de escrita: `sem_regra` e `terminal_errado`. Este módulo acrescenta TREZE verificações que rodam só na
validação (nunca bloqueiam um applyEdits) e gravam o resultado como FEIÇÃO em `plat.rede_erro` — a mesma
lógica de "sem regra = proibido" olhada de fora, mais checagens que não fazem sentido regra a regra (ciclo,
atributo nulo, geometria inválida, ...). Total: 15 códigos documentados.

Toda função recebe `feicao_ids` = o ESCOPO da validação (as feições dentro da união das áreas sujas em
processamento, ou todas as feições georreferenciadas da rede quando o escopo é 'toda a rede'). Nenhuma
função varre a rede inteira por conta própria — é isso que faz "reconstrói só dentro da área suja" ser
verdade também para as checagens estruturais, não só para a derivação de conexão.

15 códigos, na ordem em que aparecem no portão do item:
 1. sem_regra                 (regras.py, em tempo de escrita)
 2. terminal_errado           (regras.py, em tempo de escrita)
 3. regra_inexistente         — conexão/associação aponta para uma regra que já não existe (CSV substituiu).
                                Defensivo: com a FK de uma coluna só (migração 20260907T1308) o banco já
                                garante regra_id NULL-ou-válido; inalcançável pela API hoje, ver ADR.
 4. terminal_invalido         — terminal declarado pela aresta não está no terminal_config da junção
 5. terminal_obrigatorio_ausente — junção com terminal_config de >1 nome e a aresta não declarou qual
 6. feicao_sem_conexao        — feição georreferenciada sem nenhuma conexão jj/je
 7. sobreposicao_dispositivo  — dois dispositivos coincidentes sem regra juncao_juncao que os autorize
 8. ciclo_tier_hierarquico    — ciclo no grafo de conexões dentro de um tier hierárquico
 9. subrede_sem_controlador   — componente conexo (cortado em dispositivo_de_protecao) sem 'controlador'
10. atributo_obrigatorio_nulo — atributo com obrigatorio=true e valor nulo/ausente na feição
11. geometria_invalida        — ST_IsValid = false
12. associacao_ciclo          — duas associações do mesmo tipo formando A->B->A
13. tipo_sem_regra_no_pacote  — tipo de ativo que não aparece em NENHUMA regra do pacote
14. feicao_duplicada_geometria — duas feições do MESMO tipo com geometria idêntica (ST_Equals)
15. atributo_tipo_invalido    — valor do atributo não bate com o tipo_dado declarado
"""

DEVICE_CATEGORIAS = ("dispositivo_de_protecao", "seccionamento", "medicao", "transformacao", "controlador")
PROTECAO_CATEGORIA = "dispositivo_de_protecao"
CONTROLADOR_CATEGORIA = "controlador"


def _erro(codigo: str, mensagem: str, feicao_id: str | None = None, tipo_referencia: str = "feicao",
          geometria_ewkb=None, detalhe: dict | None = None) -> dict:
    return {"codigo": codigo, "mensagem": mensagem, "feicao_id": feicao_id,
            "tipo_referencia": tipo_referencia, "geometria": geometria_ewkb, "detalhe": detalhe or {}}


def checar_regra_inexistente(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    erros = []
    cur.execute(
        "SELECT c.id, c.de_feicao_id, c.para_feicao_id, f.geometria FROM plat.rede_conexao c "
        "JOIN plat.rede_feicao f ON f.id = c.de_feicao_id "
        "WHERE c.rede_id = %s::uuid AND c.regra_id IS NOT NULL "
        "AND (c.de_feicao_id = ANY(%s::uuid[]) OR c.para_feicao_id = ANY(%s::uuid[])) "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_regra r WHERE r.id = c.regra_id)",
        (rede_id, feicao_ids, feicao_ids),
    )
    for r in cur.fetchall():
        erros.append(_erro(
            "regra_inexistente",
            f"a conexão entre {r['de_feicao_id']} e {r['para_feicao_id']} foi gravada com uma regra que já "
            "não existe no conjunto vigente (o CSV de regras foi substituído depois desta conexão)",
            str(r["de_feicao_id"]), "conexao", r["geometria"],
        ))
    cur.execute(
        "SELECT a.id, a.de_feicao_id, a.para_feicao_id, f.geometria FROM plat.rede_associacao a "
        "JOIN plat.rede_feicao f ON f.id = a.de_feicao_id "
        "WHERE a.rede_id = %s::uuid AND a.regra_id IS NOT NULL "
        "AND (a.de_feicao_id = ANY(%s::uuid[]) OR a.para_feicao_id = ANY(%s::uuid[])) "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_regra r WHERE r.id = a.regra_id)",
        (rede_id, feicao_ids, feicao_ids),
    )
    for r in cur.fetchall():
        erros.append(_erro(
            "regra_inexistente",
            f"a associação entre {r['de_feicao_id']} e {r['para_feicao_id']} foi gravada com uma regra que "
            "já não existe no conjunto vigente",
            str(r["de_feicao_id"]), "associacao", r["geometria"],
        ))
    return erros


def checar_terminais(cur, rede_id: str, feicao_ids: list[str], terminais_por_tipo: dict) -> list[dict]:
    """`terminal_invalido` e `terminal_obrigatorio_ausente`, sobre as arestas do escopo. Reusa a mesma
    consulta de coincidência geométrica de `rotas_regras` (junções nas pontas de uma aresta)."""
    if not feicao_ids:
        return []
    erros = []
    cur.execute(
        "SELECT f.id, f.terminal_inicio, f.terminal_fim, f.geometria FROM plat.rede_feicao f "
        "JOIN plat.rede_grupo g ON g.id = f.grupo_id "
        "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) AND g.geometria = 'linha'",
        (rede_id, feicao_ids),
    )
    arestas = cur.fetchall()
    for a in arestas:
        aid = str(a["id"])
        cur.execute(
            "SELECT j.id, g.codigo AS grupo, t.codigo AS tipo, j.no_inicio, j.no_fim FROM ("
            "SELECT f.id, f.grupo_id, f.tipo_id, "
            "ST_DWithin(f.geometria::geography, ST_StartPoint(e.geometria)::geography, 0.5) AS no_inicio, "
            "ST_DWithin(f.geometria::geography, ST_EndPoint(e.geometria)::geography, 0.5) AS no_fim "
            "FROM plat.rede_feicao e, plat.rede_feicao f "
            "WHERE e.id = %s::uuid AND f.rede_id = e.rede_id AND f.id <> e.id"
            ") j JOIN plat.rede_grupo g ON g.id = j.grupo_id JOIN plat.rede_tipo t ON t.id = j.tipo_id "
            "WHERE g.geometria = 'ponto' AND (j.no_inicio OR j.no_fim)",
            (aid,),
        )
        for j in cur.fetchall():
            ref = (j["grupo"], j["tipo"])
            nomes = terminais_por_tipo.get(ref)
            if j["no_inicio"]:
                terminal = a["terminal_inicio"]
                if nomes is None:
                    continue
                if terminal is None:
                    erros.append(_erro("terminal_obrigatorio_ausente",
                                       f"a aresta {aid} chega na junção {j['id']} ({ref[0]}/{ref[1]}) sem "
                                       f"declarar terminal_inicio; a junção tem {sorted(nomes)}",
                                       aid, "feicao", a["geometria"]))
                elif terminal not in nomes:
                    erros.append(_erro("terminal_invalido",
                                       f"terminal_inicio {terminal!r} da aresta {aid} não existe na junção "
                                       f"{j['id']} ({ref[0]}/{ref[1]}); válidos: {sorted(nomes)}",
                                       aid, "feicao", a["geometria"]))
            if j["no_fim"]:
                terminal = a["terminal_fim"]
                if nomes is None:
                    continue
                if terminal is None:
                    erros.append(_erro("terminal_obrigatorio_ausente",
                                       f"a aresta {aid} chega na junção {j['id']} ({ref[0]}/{ref[1]}) sem "
                                       f"declarar terminal_fim; a junção tem {sorted(nomes)}",
                                       aid, "feicao", a["geometria"]))
                elif terminal not in nomes:
                    erros.append(_erro("terminal_invalido",
                                       f"terminal_fim {terminal!r} da aresta {aid} não existe na junção "
                                       f"{j['id']} ({ref[0]}/{ref[1]}); válidos: {sorted(nomes)}",
                                       aid, "feicao", a["geometria"]))
    return erros


def checar_feicao_sem_conexao(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT f.id, f.geometria FROM plat.rede_feicao f "
        "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_conexao c WHERE c.rede_id = f.rede_id "
        "AND (c.de_feicao_id = f.id OR c.para_feicao_id = f.id)) "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_associacao a WHERE a.rede_id = f.rede_id "
        "AND (a.de_feicao_id = f.id OR a.para_feicao_id = f.id))",
        (rede_id, feicao_ids),
    )
    return [_erro("feicao_sem_conexao", f"a feição {r['id']} não tem nenhuma conexão nem associação "
                  "gravada — ficou isolada da rede", str(r["id"]), "feicao", r["geometria"])
            for r in cur.fetchall()]


def checar_sobreposicao_dispositivo(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT f.id AS a_id, f.geometria AS a_geo, o.id AS b_id, "
        "gf.codigo AS a_grupo, tf.codigo AS a_tipo, go.codigo AS b_grupo, to_.codigo AS b_tipo "
        "FROM plat.rede_feicao f "
        "JOIN plat.rede_grupo gf ON gf.id = f.grupo_id JOIN plat.rede_tipo tf ON tf.id = f.tipo_id "
        "JOIN plat.rede_tipo_categoria tcf ON tcf.tipo_id = tf.id "
        "JOIN plat.rede_categoria catf ON catf.id = tcf.categoria_id AND catf.codigo = ANY(%s) "
        "JOIN plat.rede_feicao o ON o.rede_id = f.rede_id AND o.id <> f.id "
        "JOIN plat.rede_grupo go ON go.id = o.grupo_id JOIN plat.rede_tipo to_ ON to_.id = o.tipo_id "
        "JOIN plat.rede_tipo_categoria tco ON tco.tipo_id = to_.id "
        "JOIN plat.rede_categoria cato ON cato.id = tco.categoria_id AND cato.codigo = ANY(%s) "
        "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) AND gf.geometria = 'ponto' AND go.geometria = 'ponto' "
        "AND ST_DWithin(f.geometria::geography, o.geometria::geography, 0.5) AND f.id < o.id "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_conexao c WHERE c.rede_id = f.rede_id AND c.tipo = 'jj' "
        "AND ((c.de_feicao_id = f.id AND c.para_feicao_id = o.id) "
        "OR (c.de_feicao_id = o.id AND c.para_feicao_id = f.id)) "
        "AND c.regra_id IS NOT NULL)",
        (list(DEVICE_CATEGORIAS), list(DEVICE_CATEGORIAS), rede_id, feicao_ids),
    )
    erros = []
    for r in cur.fetchall():
        erros.append(_erro(
            "sobreposicao_dispositivo",
            f"os dispositivos {r['a_id']} ({r['a_grupo']}/{r['a_tipo']}) e {r['b_id']} "
            f"({r['b_grupo']}/{r['b_tipo']}) ocupam a mesma coordenada sem uma regra juncao_juncao que "
            "autorize a coincidência",
            str(r["a_id"]), "feicao", r["a_geo"],
        ))
    return erros


def _grafo_conexoes(cur, rede_id: str, feicao_ids: list[str]) -> dict[str, set[str]]:
    """Adjacência (jj + je) só entre feições de `feicao_ids` — o grafo do ESCOPO, nunca da rede inteira."""
    cur.execute(
        "SELECT de_feicao_id, para_feicao_id FROM plat.rede_conexao "
        "WHERE rede_id = %s::uuid AND de_feicao_id = ANY(%s::uuid[]) AND para_feicao_id = ANY(%s::uuid[])",
        (rede_id, feicao_ids, feicao_ids),
    )
    grafo: dict[str, set[str]] = {}
    for r in cur.fetchall():
        a, b = str(r["de_feicao_id"]), str(r["para_feicao_id"])
        grafo.setdefault(a, set()).add(b)
        grafo.setdefault(b, set()).add(a)
    return grafo


def checar_ciclo_tier_hierarquico(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT ti.codigo FROM plat.rede_tier ti WHERE ti.rede_id = %s::uuid AND ti.tipo = 'hierarquico'",
        (rede_id,),
    )
    tiers = [r["codigo"] for r in cur.fetchall()]
    erros = []
    for tier in tiers:
        cur.execute(
            "SELECT f.id, f.geometria FROM plat.rede_feicao f JOIN plat.rede_tipo t ON t.id = f.tipo_id "
            "JOIN plat.rede_tier ti ON ti.id = t.tier_id "
            "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) AND ti.codigo = %s",
            (rede_id, feicao_ids, tier),
        )
        do_tier = {str(r["id"]): r["geometria"] for r in cur.fetchall()}
        if len(do_tier) < 2:
            continue
        grafo = _grafo_conexoes(cur, rede_id, list(do_tier))
        visitado: set[str] = set()
        for inicio in do_tier:
            if inicio in visitado:
                continue
            pilha = [(inicio, None)]
            veio_de: dict[str, str | None] = {inicio: None}
            while pilha:
                atual, pai = pilha.pop()
                if atual in visitado:
                    continue
                visitado.add(atual)
                for vizinho in grafo.get(atual, ()):
                    if vizinho == pai:
                        continue
                    if vizinho in veio_de:
                        erros.append(_erro(
                            "ciclo_tier_hierarquico",
                            f"o tier hierárquico {tier!r} tem um ciclo envolvendo a feição {atual} — tier "
                            "hierárquico não pode fechar laço",
                            atual, "feicao", do_tier.get(atual),
                        ))
                        continue
                    veio_de[vizinho] = atual
                    pilha.append((vizinho, atual))
    return erros


def checar_subrede_sem_controlador(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT f.id, cat.codigo AS categoria FROM plat.rede_feicao f "
        "LEFT JOIN plat.rede_tipo_categoria tc ON tc.tipo_id = f.tipo_id "
        "LEFT JOIN plat.rede_categoria cat ON cat.id = tc.categoria_id "
        "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[])",
        (rede_id, feicao_ids),
    )
    categorias: dict[str, set[str]] = {}
    for r in cur.fetchall():
        if r["categoria"]:
            categorias.setdefault(str(r["id"]), set()).add(r["categoria"])
    grafo = _grafo_conexoes(cur, rede_id, feicao_ids)
    visitado: set[str] = set()
    erros = []
    for inicio in feicao_ids:
        if inicio in visitado:
            continue
        componente = {inicio}
        pilha = [inicio]
        visitado.add(inicio)
        while pilha:
            atual = pilha.pop()
            if PROTECAO_CATEGORIA in categorias.get(atual, set()) and atual != inicio:
                continue  # dispositivo de proteção corta a subrede: não atravessa
            for vizinho in grafo.get(atual, ()):
                if vizinho in visitado:
                    continue
                visitado.add(vizinho)
                componente.add(vizinho)
                if PROTECAO_CATEGORIA not in categorias.get(vizinho, set()):
                    pilha.append(vizinho)
        if len(componente) < 2:
            continue  # feição isolada é 'feicao_sem_conexao', não subrede
        if not any(CONTROLADOR_CATEGORIA in categorias.get(f, set()) for f in componente):
            representante = min(componente)
            erros.append(_erro(
                "subrede_sem_controlador",
                f"a subrede com {len(componente)} feições (representante {representante}) não tem nenhuma "
                "feição de categoria 'controlador'",
                representante, "feicao", None, {"tamanho_subrede": len(componente)},
            ))
    return erros


def checar_atributo_obrigatorio_nulo(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT at.codigo, at.tipo_id, at.grupo_id, f.id AS feicao_id, f.geometria, f.atributos "
        "FROM plat.rede_atributo at "
        "JOIN plat.rede_feicao f ON f.grupo_id = at.grupo_id AND (at.tipo_id IS NULL OR at.tipo_id = f.tipo_id) "
        "WHERE at.rede_id = %s::uuid AND at.obrigatorio = true AND f.id = ANY(%s::uuid[])",
        (rede_id, feicao_ids),
    )
    erros = []
    for r in cur.fetchall():
        valor = (r["atributos"] or {}).get(r["codigo"])
        if valor is None:
            erros.append(_erro(
                "atributo_obrigatorio_nulo",
                f"a feição {r['feicao_id']} não tem valor para o atributo obrigatório {r['codigo']!r}",
                str(r["feicao_id"]), "feicao", r["geometria"],
            ))
    return erros


def checar_atributo_tipo_invalido(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    """Valor presente mas incompatível com `tipo_dado` declarado (booleano/inteiro/real) — checagem de
    qualidade de dado, não de conectividade; roda no mesmo escopo por conveniência (mesma origem: os
    atributos das feições editadas)."""
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT at.codigo, at.tipo_dado, f.id AS feicao_id, f.geometria, f.atributos "
        "FROM plat.rede_atributo at "
        "JOIN plat.rede_feicao f ON f.grupo_id = at.grupo_id AND (at.tipo_id IS NULL OR at.tipo_id = f.tipo_id) "
        "WHERE at.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) AND at.tipo_dado IN ('inteiro', 'real', 'booleano')",
        (rede_id, feicao_ids),
    )
    erros = []
    for r in cur.fetchall():
        valor = (r["atributos"] or {}).get(r["codigo"])
        if valor is None:
            continue
        ok = (
            (r["tipo_dado"] == "inteiro" and isinstance(valor, int) and not isinstance(valor, bool)) or
            (r["tipo_dado"] == "real" and isinstance(valor, (int, float)) and not isinstance(valor, bool)) or
            (r["tipo_dado"] == "booleano" and isinstance(valor, bool))
        )
        if not ok:
            erros.append(_erro(
                "atributo_tipo_invalido",
                f"o atributo {r['codigo']!r} da feição {r['feicao_id']} devia ser {r['tipo_dado']!r}; veio "
                f"{type(valor).__name__} ({valor!r})",
                str(r["feicao_id"]), "feicao", r["geometria"],
            ))
    return erros


def checar_geometria_invalida(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT id, geometria FROM plat.rede_feicao "
        "WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) AND geometria IS NOT NULL "
        "AND NOT ST_IsValid(geometria)",
        (rede_id, feicao_ids),
    )
    return [_erro("geometria_invalida", f"a geometria da feição {r['id']} é inválida (ST_IsValid = false)",
                  str(r["id"]), "feicao", r["geometria"])
            for r in cur.fetchall()]


def checar_associacao_ciclo(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT id, tipo, de_feicao_id, para_feicao_id FROM plat.rede_associacao "
        "WHERE rede_id = %s::uuid AND (de_feicao_id = ANY(%s::uuid[]) OR para_feicao_id = ANY(%s::uuid[]))",
        (rede_id, feicao_ids, feicao_ids),
    )
    por_tipo: dict[str, dict[str, str]] = {}
    for r in cur.fetchall():
        por_tipo.setdefault(r["tipo"], {})[str(r["de_feicao_id"])] = str(r["para_feicao_id"])
    erros = []
    for tipo, arestas in por_tipo.items():
        for de, para in arestas.items():
            if arestas.get(para) == de:
                dupla = tuple(sorted([de, para]))
                if dupla[0] != de:
                    continue  # relata uma vez só, na ordem canônica
                erros.append(_erro(
                    "associacao_ciclo",
                    f"associação {tipo!r} forma um ciclo entre {de} e {para} (A contém/fixa B e B contém/fixa A)",
                    de, "associacao",
                ))
    return erros


def checar_feicao_duplicada_geometria(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT f.id AS a_id, o.id AS b_id, f.geometria FROM plat.rede_feicao f "
        "JOIN plat.rede_feicao o ON o.rede_id = f.rede_id AND o.tipo_id = f.tipo_id AND o.id < f.id "
        "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) AND f.geometria IS NOT NULL "
        "AND o.geometria IS NOT NULL AND ST_Equals(f.geometria, o.geometria)",
        (rede_id, feicao_ids),
    )
    return [_erro("feicao_duplicada_geometria",
                  f"as feições {r['a_id']} e {r['b_id']} são do mesmo tipo e têm geometria idêntica",
                  str(r["a_id"]), "feicao", r["geometria"])
            for r in cur.fetchall()]


def checar_tipo_sem_regra_no_pacote(cur, rede_id: str, feicao_ids: list[str]) -> list[dict]:
    """Rede-level de verdade (não geométrica), mas restrita aos TIPOS que têm ao menos uma feição no
    escopo — não varre o pacote inteiro a cada validação por extensão."""
    if not feicao_ids:
        return []
    cur.execute(
        "SELECT DISTINCT t.id, t.codigo, g.codigo AS grupo, "
        "(SELECT f2.id FROM plat.rede_feicao f2 WHERE f2.tipo_id = t.id "
        "AND f2.id = ANY(%s::uuid[]) LIMIT 1) AS exemplo "
        "FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "JOIN plat.rede_feicao f ON f.tipo_id = t.id "
        "WHERE t.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) "
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_regra r WHERE r.rede_id = t.rede_id "
        "AND (r.de_tipo_id = t.id OR r.para_tipo_id = t.id OR r.via_tipo_id = t.id))",
        (feicao_ids, rede_id, feicao_ids),
    )
    erros = []
    for r in cur.fetchall():
        erros.append(_erro(
            "tipo_sem_regra_no_pacote",
            f"o tipo {r['grupo']}/{r['codigo']} não aparece em nenhuma regra do pacote — nenhuma conexão "
            "ou associação com este tipo poderá ser gravada enquanto isso não mudar",
            str(r["exemplo"]) if r["exemplo"] else None, "feicao" if r["exemplo"] else "rede",
        ))
    return erros


TODAS = (
    checar_regra_inexistente,
    checar_feicao_sem_conexao,
    checar_sobreposicao_dispositivo,
    checar_ciclo_tier_hierarquico,
    checar_subrede_sem_controlador,
    checar_atributo_obrigatorio_nulo,
    checar_atributo_tipo_invalido,
    checar_geometria_invalida,
    checar_associacao_ciclo,
    checar_feicao_duplicada_geometria,
    checar_tipo_sem_regra_no_pacote,
)


def rodar_todas(cur, rede_id: str, feicao_ids: list[str], terminais_por_tipo: dict) -> list[dict]:
    erros: list[dict] = []
    for checagem in TODAS:
        erros.extend(checagem(cur, rede_id, feicao_ids))
    erros.extend(checar_terminais(cur, rede_id, feicao_ids, terminais_por_tipo))
    return erros
