"""Hierarquia DECLARADA pelo arquivo e reconciliação com a subrede DERIVADA do controlador
(item L4-04-c-unificar-subrede; ADR 20260908T0152).

Depois da unificação existe uma tabela só, `plat.rede_subrede`, com duas origens:

  * `origem='controlador'` — a subrede CANÔNICA: nasce do controlador marcado num terminal, tem tier,
    ciclo de vida (limpa/suja), elementos, linha agregada e resumo. É o que o traçado calcula.
  * `origem='bdgd'` — a hierarquia que o ARQUIVO declara: nível 1 subestação (SUB), nível 2 alimentador
    (CTMT), nível 3 transformador (UNI_TR_MT). Não tem tier nem ciclo de vida. É o que o arquivo diz.

Duas funções:

  `declarar` lê a hierarquia dos ATRIBUTOS que as feições carregam do arquivo (`sub`, `ctmt`, `cod_id`
  do transformador) e grava as linhas de origem declarada. É o mesmo conteúdo que o importador de
  FileGDB (`bdgd.py`) grava direto durante a carga; aqui ele é lido das feições porque a rede montada
  camada a camada (o caminho da carga da distribuidora de referência) não passa pelo importador de GDB.
  Nada é inventado: campo do arquivo ausente vira contagem em `sem_pai`/`sem_codigo`, nunca um código
  fabricado.

  `reconciliar` liga cada linha declarada à subrede derivada correspondente, pelo NOME (a marcação de
  controladores nomeia a subrede do alimentador com o próprio CTMT e a do transformador com o COD_ID
  dele) dentro do TIER daquele nível. O que casa recebe `equivalente_id`; o que não casa fica NULL — e é
  esse número, não o que casou, que diz onde o arquivo e o traçado discordam.

⛔ A reconciliação NÃO é prova de que o traçado está certo: ela mede concordância entre duas leituras
independentes da mesma rede. Divergência é candidata a erro de cadastro ou a limite do traçado, nunca
erro provado de um dos lados.
"""

from app.erros import ErroAPI
from app.rede_utilidades import controladores

NIVEL_SUBESTACAO = 1
NIVEL_ALIMENTADOR = 2
NIVEL_TRANSFORMADOR = 3

# nível declarado -> grupo de ativo cujo tier é o da subrede derivada equivalente
GRUPO_DO_NIVEL = {
    NIVEL_ALIMENTADOR: controladores.GRUPO_TRECHO_MT,
    NIVEL_TRANSFORMADOR: controladores.GRUPO_TRECHO_BT,
}

_CONFLITO = "ON CONFLICT (rede_id, nivel, codigo_externo) WHERE origem = 'bdgd' DO NOTHING"


def _inserir(cur, tenant_id: int, rede_id: str, nivel: int, codigo: str, pai_id: str | None) -> str | None:
    cur.execute(
        "INSERT INTO plat.rede_subrede (tenant_id, rede_id, origem, estado, nivel, codigo_externo, nome, "
        "pai_id) VALUES (%s, %s::uuid, 'bdgd', 'declarada', %s, %s, %s, %s::uuid) " + _CONFLITO
        + " RETURNING id",
        (tenant_id, rede_id, nivel, codigo, codigo, pai_id),
    )
    r = cur.fetchone()
    return str(r["id"]) if r else None


def _ja_declaradas(cur, rede_id: str, nivel: int) -> dict[str, str]:
    cur.execute(
        "SELECT id, codigo_externo FROM plat.rede_subrede "
        "WHERE rede_id = %s::uuid AND origem = 'bdgd' AND nivel = %s",
        (rede_id, nivel),
    )
    return {r["codigo_externo"]: str(r["id"]) for r in cur.fetchall()}


def declarar(cur, tenant_id: int, rede_id: str) -> dict:
    """Grava a hierarquia declarada pelo arquivo a partir dos atributos das feições já carregadas.
    Idempotente: rodar de novo não duplica (chave (rede, nível, código) das linhas declaradas)."""
    contagem = {"subestacoes": 0, "alimentadores": 0, "transformadores": 0,
                "alimentadores_sem_subestacao": 0, "transformadores_sem_alimentador": 0,
                "ja_declaradas": 0}

    # nível 1 e 2 saem do mesmo lugar: o trecho de média tensão carrega `sub` e `ctmt` do arquivo.
    cur.execute(
        "SELECT f.atributos->>'ctmt' AS ctmt, max(f.atributos->>'sub') AS sub "
        "FROM plat.rede_feicao_linha f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %s::uuid AND g.codigo = %s AND f.atributos->>'ctmt' IS NOT NULL "
        "GROUP BY 1 ORDER BY 1",
        (rede_id, controladores.GRUPO_TRECHO_MT),
    )
    alimentadores = [dict(r) for r in cur.fetchall()]

    subestacoes = _ja_declaradas(cur, rede_id, NIVEL_SUBESTACAO)
    for cod in sorted({a["sub"] for a in alimentadores if a["sub"]}):
        if cod in subestacoes:
            contagem["ja_declaradas"] += 1
            continue
        novo = _inserir(cur, tenant_id, rede_id, NIVEL_SUBESTACAO, cod, None)
        if novo:
            subestacoes[cod] = novo
            contagem["subestacoes"] += 1

    ja_alimentadores = _ja_declaradas(cur, rede_id, NIVEL_ALIMENTADOR)
    for al in alimentadores:
        cod, sub = al["ctmt"], al["sub"]
        if cod in ja_alimentadores:
            contagem["ja_declaradas"] += 1
            continue
        if not sub or sub not in subestacoes:
            # o gatilho recusa nível 2 sem pai; sem o campo SUB no arquivo a linha declarada não existe
            contagem["alimentadores_sem_subestacao"] += 1
            continue
        novo = _inserir(cur, tenant_id, rede_id, NIVEL_ALIMENTADOR, cod, subestacoes[sub])
        if novo:
            ja_alimentadores[cod] = novo
            contagem["alimentadores"] += 1

    cur.execute(
        "SELECT f.atributos->>'cod_id' AS cod_id, f.atributos->>'ctmt' AS ctmt "
        "FROM plat.rede_feicao_ponto f JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE f.rede_id = %s::uuid AND g.codigo = %s AND f.atributos->>'cod_id' IS NOT NULL "
        "ORDER BY 1",
        (rede_id, controladores.GRUPO_TRAFO),
    )
    ja_trafos = _ja_declaradas(cur, rede_id, NIVEL_TRANSFORMADOR)
    for tr in cur.fetchall():
        cod, ctmt = tr["cod_id"], tr["ctmt"]
        if cod in ja_trafos:
            contagem["ja_declaradas"] += 1
            continue
        if not ctmt or ctmt not in ja_alimentadores:
            contagem["transformadores_sem_alimentador"] += 1
            continue
        novo = _inserir(cur, tenant_id, rede_id, NIVEL_TRANSFORMADOR, cod, ja_alimentadores[ctmt])
        if novo:
            ja_trafos[cod] = novo
            contagem["transformadores"] += 1
    return contagem


def _tier_id_ou_none(cur, rede_id: str, grupo: str) -> str | None:
    try:
        return str(controladores.tier_do_grupo(cur, rede_id, grupo)["id"])
    except ErroAPI:
        return None  # pacote sem esse grupo: não há tier para comparar, e o nível fica sem equivalente


def reconciliar(cur, rede_id: str) -> dict:
    """Liga cada subrede declarada pelo arquivo à derivada de mesmo nome no tier daquele nível.
    Devolve, por nível, o universo declarado, quantas casaram e a razão sobre esse universo."""
    saida: dict = {}
    for nivel, grupo in GRUPO_DO_NIVEL.items():
        tier_id = _tier_id_ou_none(cur, rede_id, grupo)
        if tier_id is None:
            cur.execute(
                "SELECT count(*) AS n FROM plat.rede_subrede "
                "WHERE rede_id = %s::uuid AND origem = 'bdgd' AND nivel = %s", (rede_id, nivel))
            saida[nivel] = {"declaradas": int(cur.fetchone()["n"]), "com_equivalente": 0,
                            "sem_equivalente": None, "taxa": None,
                            "sem_tier": f"o pacote desta rede não tem o grupo '{grupo}'"}
            continue
        cur.execute(
            "UPDATE plat.rede_subrede d SET equivalente_id = c.id "
            "FROM plat.rede_subrede c "
            "WHERE d.rede_id = %(rede)s::uuid AND d.origem = 'bdgd' AND d.nivel = %(nivel)s "
            "  AND c.rede_id = d.rede_id AND c.origem = 'controlador' AND c.tier_id = %(tier)s::uuid "
            "  AND c.nome = d.codigo_externo "
            "  AND d.equivalente_id IS DISTINCT FROM c.id",
            {"rede": rede_id, "nivel": nivel, "tier": tier_id},
        )
        cur.execute(
            "SELECT count(*) AS declaradas, count(equivalente_id) AS com_equivalente "
            "FROM plat.rede_subrede WHERE rede_id = %s::uuid AND origem = 'bdgd' AND nivel = %s",
            (rede_id, nivel),
        )
        r = cur.fetchone()
        declaradas, com = int(r["declaradas"]), int(r["com_equivalente"])
        saida[nivel] = {"declaradas": declaradas, "com_equivalente": com,
                        "sem_equivalente": declaradas - com,
                        "taxa": round(com / declaradas, 6) if declaradas else None}
    return {"alimentadores": saida[NIVEL_ALIMENTADOR], "transformadores": saida[NIVEL_TRANSFORMADOR]}
