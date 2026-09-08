"""Conferência do controle de pressão da rede de gás (item L4-05-e-gas-e-esgoto).

Na rede de gás o tier é o degrau de pressão (transporte, alta, média, baixa — `ordem` crescente = pressão
decrescente) e quem muda de degrau é o REGULADOR. Daí saem as duas perguntas que esta passagem responde:

1. Todo ativo de categoria `controle_de_pressao` declara de qual tier recebe e para qual entrega, e a pressão
   tem de CAIR (ordem do tier de jusante maior que a do tier de montante). Regulador que sobe pressão ou que
   liga dois trechos do mesmo tier é erro.
2. Onde duas tubulações de tiers diferentes se encontram TEM DE haver um ativo de controle de pressão. Duas
   tubulações de tiers diferentes emendadas direto significam que a média pressão entrou na baixa.

Como na conferência de esgoto, nada é corrigido: a resposta nomeia a feição e o que está errado.

A vizinhança é medida em metros de verdade (`geography`), com a tolerância declarada na própria rede
(`plat.rede.tolerancia_m`) — a mesma que a topologia derivada usa para juntar pontas."""

CATEGORIA_CONTROLE = "controle_de_pressao"
CHAVE_TIER_MONTANTE = "tier_montante"
CHAVE_TIER_JUSANTE = "tier_jusante"
CHAVE_IDENTIFICADOR = "identificador"

SQL_TIERS = """
SELECT tr.codigo, tr.ordem, tr.nome
  FROM plat.rede_tier tr JOIN plat.rede_dominio d ON d.id = tr.dominio_id
 WHERE tr.rede_id = %s::uuid AND d.disciplina = 'gas'
"""

SQL_CONTROLADORES = """
SELECT f.id, f.atributos, g.codigo AS grupo, t.chave AS tipo_chave, tr.codigo AS tier
  FROM plat.rede_feicao_ponto f
  JOIN plat.rede_tipo t ON t.id = f.tipo_id
  JOIN plat.rede_tier tr ON tr.id = t.tier_id
  JOIN plat.rede_grupo g ON g.id = t.grupo_id
  JOIN plat.rede_dominio d ON d.id = g.dominio_id
 WHERE f.rede_id = %s::uuid AND d.disciplina = 'gas'
   AND EXISTS (SELECT 1 FROM plat.rede_tipo_categoria tc JOIN plat.rede_categoria c ON c.id = tc.categoria_id
                WHERE tc.tipo_id = t.id AND c.codigo = %s)
 ORDER BY f.criado_em, f.id
"""

# emenda de tubulações de tiers diferentes sem controlador de pressão a menos de `tolerancia_m` do contato.
# As pontas de cada trecho viram linhas em `pontas`; o par (a, b) é ordenado pelo id para não sair duplicado.
SQL_TRANSICOES = """
WITH linhas AS (
  SELECT f.id, tr.codigo AS tier, tr.ordem, t.chave AS tipo_chave, f.geom
    FROM plat.rede_feicao_linha f
    JOIN plat.rede_tipo t ON t.id = f.tipo_id
    JOIN plat.rede_tier tr ON tr.id = t.tier_id
    JOIN plat.rede_grupo g ON g.id = t.grupo_id
    JOIN plat.rede_dominio d ON d.id = g.dominio_id
   WHERE f.rede_id = %(rede)s::uuid AND d.disciplina = 'gas'
), pontas AS (
  SELECT id, tier, ordem, tipo_chave, ST_StartPoint(geom) AS p FROM linhas
  UNION ALL
  SELECT id, tier, ordem, tipo_chave, ST_EndPoint(geom) AS p FROM linhas
), controladores AS (
  SELECT f.geom
    FROM plat.rede_feicao_ponto f
    JOIN plat.rede_tipo t ON t.id = f.tipo_id
    JOIN plat.rede_grupo g ON g.id = t.grupo_id
    JOIN plat.rede_dominio d ON d.id = g.dominio_id
   WHERE f.rede_id = %(rede)s::uuid AND d.disciplina = 'gas'
     AND EXISTS (SELECT 1 FROM plat.rede_tipo_categoria tc
                   JOIN plat.rede_categoria c ON c.id = tc.categoria_id
                  WHERE tc.tipo_id = t.id AND c.codigo = %(categoria)s)
)
SELECT DISTINCT a.id AS a_id, a.tier AS a_tier, a.tipo_chave AS a_tipo,
       b.id AS b_id, b.tier AS b_tier, b.tipo_chave AS b_tipo,
       ST_X(a.p) AS lon, ST_Y(a.p) AS lat
  FROM pontas a JOIN pontas b
    ON a.id < b.id AND a.tier <> b.tier
   AND ST_DWithin(a.p::geography, b.p::geography, %(tol)s)
 WHERE NOT EXISTS (SELECT 1 FROM controladores c
                    WHERE ST_DWithin(c.geom::geography, a.p::geography, %(tol)s))
 ORDER BY a.id, b.id
"""


def conferir(cur, rede_id: str) -> dict:
    """Confere o controle de pressão da rede de gás. Só lê."""
    cur.execute(SQL_TIERS, (rede_id,))
    tiers = {r["codigo"]: {"ordem": r["ordem"], "nome": r["nome"]} for r in cur.fetchall()}
    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    linha = cur.fetchone()
    tolerancia = float(linha["tolerancia_m"]) if linha else 0.0

    problemas: list[dict] = []
    cur.execute(SQL_CONTROLADORES, (rede_id, CATEGORIA_CONTROLE))
    controladores = cur.fetchall()
    conformes = 0
    for c in controladores:
        atributos = c["atributos"] or {}
        base = {"feicao_id": str(c["id"]), "identificador": atributos.get(CHAVE_IDENTIFICADOR),
                "grupo": c["grupo"], "tipo": c["tipo_chave"]}
        montante = atributos.get(CHAVE_TIER_MONTANTE)
        jusante = atributos.get(CHAVE_TIER_JUSANTE)
        desconhecidos = [v for v in (montante, jusante) if v not in tiers]
        if desconhecidos:
            problemas.append({**base, "erro": "tier_desconhecido",
                              "mensagem": f"o controlador de pressão declara o tier {desconhecidos[0]!r}, que "
                                          f"não existe no pacote desta rede",
                              "tier_montante": montante, "tier_jusante": jusante})
            continue
        ordem_m, ordem_j = tiers[montante]["ordem"], tiers[jusante]["ordem"]
        if ordem_j > ordem_m:
            conformes += 1
        elif ordem_j == ordem_m:
            problemas.append({**base, "erro": "regulador_sem_transicao",
                              "mensagem": f"o controlador liga dois trechos do mesmo tier ({montante}); "
                                          f"regulador existe para mudar de degrau de pressão",
                              "tier_montante": montante, "tier_jusante": jusante})
        else:
            problemas.append({**base, "erro": "regulador_eleva_pressao",
                              "mensagem": f"o controlador declara receber em {montante} e entregar em "
                                          f"{jusante}, que é um degrau de pressão MAIOR; regulador reduz "
                                          f"pressão, não eleva",
                              "tier_montante": montante, "tier_jusante": jusante})

    cur.execute(SQL_TRANSICOES, {"rede": rede_id, "categoria": CATEGORIA_CONTROLE, "tol": tolerancia})
    transicoes = cur.fetchall()
    for t in transicoes:
        problemas.append({
            "feicao_id": str(t["a_id"]), "identificador": None, "grupo": "tubulacao_de_gas",
            "tipo": t["a_tipo"], "erro": "transicao_sem_regulador",
            "mensagem": f"tubulação de {t['a_tier']} encontra tubulação de {t['b_tier']} sem nenhum ativo de "
                        f"controle de pressão a menos de {tolerancia:g} m do contato",
            "tier_montante": t["a_tier"], "tier_jusante": t["b_tier"],
            "outra_feicao_id": str(t["b_id"]), "lon": t["lon"], "lat": t["lat"],
        })
    return {
        "controladores": len(controladores),
        "controladores_conformes": conformes,
        "transicoes_sem_regulador": len(transicoes),
        "tolerancia_m": tolerancia,
        "tiers": [{"codigo": c, "ordem": v["ordem"], "nome": v["nome"]}
                  for c, v in sorted(tiers.items(), key=lambda kv: kv[1]["ordem"])],
        "alterou_a_rede": False,
        "problemas": problemas,
    }
