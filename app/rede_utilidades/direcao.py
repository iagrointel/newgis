"""Montante e jusante por DISTÂNCIA AO CONTROLADOR DE SUBREDE (item L4-02-b-montante-jusante).

Este módulo responde à pergunta que o traçado por atributo (`fluxo.py`, item L4-18) não responde numa rede de
utilidades: qual é o sentido do fluxo quando NENHUM trecho declara direção. A resposta do produto é a mesma da
rede de utilidades da Esri (find-upstream-and-downstream-features.htm): o sentido vem da SUBREDE — o que está
mais perto do controlador de subrede está a montante; o que só chega ao controlador passando por um ponto está
a jusante desse ponto.

Como é calculado, em uma frase por passo:

  1. o grafo é o MESMO de `tracado.py` (arestas reais da topologia derivada mais as arestas virtuais de cada
     dispositivo, com chave aberta cortando e barreira do chamador removida); não existe um segundo motor de
     traçado nesta casa, e a fronteira de transformação NÃO corta aqui — atravessar o transformador é o que
     permite ao montante de uma unidade consumidora chegar ao alimentador;
  2. as RAÍZES são os controladores de papel `fonte` do tier HIERÁRQUICO de menor `ordem` que tenha
     controlador com nó na topologia atual (numa rede elétrica: o alimentador, nunca o transformador, porque
     partir também do transformador quebraria o montante da baixa tensão no próprio transformador);
  3. `public.pgr_drivingDistance(..., directed := false, equicost := true)` devolve, para cada nó, a que
     controlador ele está mais perto e por qual aresta chegou — isto é, a árvore de caminhos mínimos em
     número de saltos. `pred` dá o pai de cada nó; a profundidade é a distância ao controlador;
  4. jusante de um ponto = a subárvore dele (todo nó cujo caminho ao controlador passa pelo ponto);
     montante = a cadeia de pais do ponto até a raiz, que termina no controlador declarado.

Quando o traçado NÃO responde uma direção, e nunca inventa uma:

  * TIER PARTICIONADO (malha): a hierarquia não define sentido. A direção então só pode vir do atributo
    `direcao_fluxo` de cada trecho — se algum trecho alcançável o declara, o pedido é atendido por
    `fluxo.tracar_fluxo`; se nenhum declara, a resposta é `direcao='indeterminado'`, com o motivo.
  * LAÇO: se o grafo alcançável tem uma corda (aresta que não entrou na árvore de caminhos mínimos), existe
    mais de um caminho até o controlador e o que está "acima" de quem depende do caminho escolhido. Quando
    esse laço toca o resultado pedido (a subárvore, no jusante; a cadeia de pais, no montante), a resposta é
    `direcao='indeterminado'` com `nos_do_laco` — os nós onde os dois caminhos se encontram.
  * PONTO SEM CONTROLADOR: nó que nenhum controlador alcança não tem montante nem jusante definidos.

O campo `origem_direcao` sai em toda resposta (`controlador` ou `atributo`), para que nunca seja preciso
adivinhar de onde veio o sentido; `origem_direcao` também pode ser IMPOSTO no pedido, para o operador que
quer o traçado por atributo mesmo numa rede que tem controlador (ou o contrário)."""

import time

from app.erros import ErroAPI
from app.rede_utilidades import fluxo as _fl
from app.rede_utilidades import lacos as _lac
from app.rede_utilidades import tracado as _tr

ORIGENS = ("auto", "controlador", "atributo")
TIPOS = _fl.TIPOS_FLUXO
_TAG = "direcao_sql"


def _controladores_raiz(cur, rede_id: str) -> tuple[list[dict], str | None]:
    """Os controladores de papel `fonte` do tier de menor `ordem` que tenha controlador com nó na topologia,
    e o TIPO desse tier (`hierarquico`/`particionado`). Devolve ([], None) quando a rede não tem controlador
    com nó — nesse caso não há de onde derivar sentido."""
    cur.execute(
        "SELECT c.id, c.nome, c.subrede_id, s.nome AS subrede, t.codigo AS tier, t.tipo AS tier_tipo, "
        "       t.ordem AS tier_ordem, "
        "       (SELECT n.id FROM plat.rede_topo_no n WHERE n.rede_id = c.rede_id AND ("
        "          (c.feicao_id IS NOT NULL AND n.origem_id = c.feicao_id AND n.terminal_num = c.terminal_num) "
        "          OR (c.feicao_id IS NULL AND n.geom = c.geom)) LIMIT 1) AS no_id "
        "FROM plat.rede_controlador c "
        "JOIN plat.rede_subrede s ON s.id = c.subrede_id "
        "JOIN plat.rede_tier t ON t.id = c.tier_id "
        "WHERE c.rede_id = %s::uuid AND c.papel = 'fonte' ORDER BY t.ordem, c.nome",
        (rede_id,),
    )
    linhas = [dict(r) for r in cur.fetchall() if r["no_id"] is not None]
    if not linhas:
        return [], None
    ordem = linhas[0]["tier_ordem"]
    raizes = [r for r in linhas if r["tier_ordem"] == ordem]
    return raizes, raizes[0]["tier_tipo"]


def _montar_arvore(cur, rede_id: str, ids_raiz: list[str]) -> None:
    """`TEMP TABLE direcao_aresta` (o grafo traversável, o mesmo de `tracado.py`) e `TEMP TABLE direcao_arvore`
    (no, pai, profundidade, raiz, aresta usada) — a árvore de caminhos mínimos a partir dos controladores."""
    sql_arestas = _tr._montar_sql_arestas(cur, rede_id, ignorar_transformacao=False)
    cur.execute("DROP TABLE IF EXISTS direcao_aresta")
    cur.execute(f"CREATE TEMP TABLE direcao_aresta AS {sql_arestas}")
    cur.execute("CREATE INDEX ix_direcao_aresta_id ON direcao_aresta (id)")
    cur.execute("ANALYZE direcao_aresta")

    cur.execute("SELECT iid FROM tracado_mapa WHERE no_id = ANY(%s::uuid[]) ORDER BY iid", (ids_raiz,))
    iids = [r["iid"] for r in cur.fetchall()]
    cur.execute("DROP TABLE IF EXISTS direcao_arvore")
    cur.execute(
        "CREATE TEMP TABLE direcao_arvore AS "
        "SELECT m.no_id AS no, mp.no_id AS pai, d.agg_cost::int AS profundidade, mr.no_id AS raiz, "
        "       d.edge AS aresta "
        f"FROM public.pgr_drivingDistance(${_TAG}$ SELECT id, source, target, cost FROM direcao_aresta ${_TAG}$, "
        "     %s::bigint[], 'Infinity'::float, false, true) d "
        "JOIN tracado_mapa m ON m.iid = d.node "
        "LEFT JOIN tracado_mapa mp ON mp.iid = d.pred AND d.pred <> d.node "
        "JOIN tracado_mapa mr ON mr.iid = d.start_vid",
        (iids,),
    )
    cur.execute("CREATE INDEX ix_direcao_arvore_no ON direcao_arvore (no)")
    cur.execute("CREATE INDEX ix_direcao_arvore_pai ON direcao_arvore (pai)")
    cur.execute("ANALYZE direcao_arvore")


def _nos_de_laco(cur) -> list[str]:
    """Os nós das CORDAS: arestas do grafo alcançável que não entraram na árvore de caminhos mínimos. Cada
    corda fecha um ciclo, e num ciclo não existe "mais perto do controlador" que não dependa do caminho."""
    cur.execute(
        "SELECT DISTINCT m.no_id FROM direcao_aresta e "
        "JOIN tracado_mapa ms ON ms.iid = e.source JOIN tracado_mapa mt ON mt.iid = e.target "
        "JOIN direcao_arvore a1 ON a1.no = ms.no_id JOIN direcao_arvore a2 ON a2.no = mt.no_id "
        "JOIN tracado_mapa m ON m.iid IN (e.source, e.target) "
        "WHERE e.id NOT IN (SELECT aresta FROM direcao_arvore WHERE aresta IS NOT NULL AND aresta >= 0) "
        "ORDER BY 1"
    )
    return [str(r["no_id"]) for r in cur.fetchall()]


def _descendentes(cur, ids: list[str]) -> set[str]:
    cur.execute(
        "WITH RECURSIVE sub(no) AS ("
        "  SELECT unnest(%s::uuid[])"
        "  UNION"
        "  SELECT a.no FROM direcao_arvore a JOIN sub ON a.pai = sub.no"
        ") SELECT no FROM sub",
        (ids,),
    )
    return {str(r["no"]) for r in cur.fetchall()}


def _ancestrais(cur, ids: list[str]) -> set[str]:
    cur.execute(
        "WITH RECURSIVE anc(no, pai) AS ("
        "  SELECT no, pai FROM direcao_arvore WHERE no = ANY(%s::uuid[])"
        "  UNION"
        "  SELECT a.no, a.pai FROM direcao_arvore a JOIN anc ON a.no = anc.pai"
        ") SELECT no FROM anc",
        (ids,),
    )
    return {str(r["no"]) for r in cur.fetchall()}


def _tem_direcao_declarada(cur, rede_id: str) -> bool:
    """Algum trecho da rede declara `direcao_fluxo` no atributo da feição? É o que decide, num tier
    particionado, entre atender pelo atributo e responder `indeterminado`."""
    cur.execute(
        "SELECT 1 FROM plat.rede_feicao_linha WHERE rede_id = %s::uuid "
        "AND atributos ? %s LIMIT 1",
        (rede_id, _fl.CHAVE_DIRECAO),
    )
    return cur.fetchone() is not None


def _indeterminado(tipo: str, motivo: str, mensagem: str, inicio: float, *, nos_do_laco=None,
                   controladores=None) -> dict:
    return {
        "tipo": tipo, "origem_direcao": "controlador", "direcao": "indeterminado", "motivo": motivo,
        "mensagem": mensagem, "nos_do_laco": nos_do_laco or [], "controladores": controladores or [],
        "elementos": [], "contagem": 0, "geometria": None, "nos_alcancados": 0,
        "duracao_ms": int((time.perf_counter() - inicio) * 1000), "avisos": [],
    }


def tracar_direcao(cur, tenant_id: int, rede_id: str, tipo: str, pontos_partida: list[dict],
                   barreiras: list[dict], origem: str = "auto") -> dict:
    """`tipo='jusante'`/`'montante'` no MESMO endpoint dos outros traçados. `origem`: `auto` (controlador
    quando a rede tem controlador com nó, atributo quando não tem), `controlador` ou `atributo`."""
    if tipo not in TIPOS:
        raise ErroAPI(422, "tipo_invalido", f"tipo deve ser um de {TIPOS}")
    if origem not in ORIGENS:
        raise ErroAPI(422, "origem_direcao_invalida", f"origem_direcao deve ser uma de {ORIGENS}")
    if not pontos_partida:
        raise ErroAPI(422, "sem_ponto_de_partida", "informe ao menos um ponto de partida")
    inicio = time.perf_counter()

    if origem == "atributo":
        return {**_fl.tracar_fluxo(cur, tenant_id, rede_id, tipo, pontos_partida, barreiras),
                "origem_direcao": "atributo", "direcao": "definida", "nos_do_laco": [], "controladores": []}

    tolerancia_rede, ids_barreira = _lac._preparar_mapa(cur, rede_id, barreiras)
    raizes, tier_tipo = _controladores_raiz(cur, rede_id)
    if not raizes:
        if origem == "controlador":
            raise ErroAPI(
                409, "sem_controlador",
                "esta rede não tem controlador de subrede com nó na topologia atual: sem controlador, o "
                "sentido só pode vir do atributo de fluxo (origem_direcao='atributo')")
        return {**_fl.tracar_fluxo(cur, tenant_id, rede_id, tipo, pontos_partida, barreiras),
                "origem_direcao": "atributo", "direcao": "definida", "nos_do_laco": [], "controladores": []}

    fichas = [{"nome": r["nome"], "subrede": r["subrede"], "tier": r["tier"], "no_id": str(r["no_id"])}
              for r in raizes]
    if tier_tipo != "hierarquico":
        if _tem_direcao_declarada(cur, rede_id):
            return {**_fl.tracar_fluxo(cur, tenant_id, rede_id, tipo, pontos_partida, barreiras),
                    "origem_direcao": "atributo", "direcao": "definida", "nos_do_laco": [],
                    "controladores": fichas}
        return _indeterminado(
            tipo, "tier_particionado",
            f"o controlador desta rede está no tier '{raizes[0]['tier']}', que é particionado (malha): a "
            "distância ao controlador não define sentido, e nenhum trecho declara o atributo "
            f"'{_fl.CHAVE_DIRECAO}'", inicio, controladores=fichas)

    ids_inicio = [_tr._resolver_ponto(cur, rede_id, tolerancia_rede, p) for p in pontos_partida]
    if [i for i in ids_inicio if i in ids_barreira]:
        raise ErroAPI(422, "inicio_e_barreira", "um ponto de partida não pode também ser barreira")

    _montar_arvore(cur, rede_id, [str(r["no_id"]) for r in raizes])
    cur.execute("SELECT no, raiz FROM direcao_arvore WHERE no = ANY(%s::uuid[])", (ids_inicio,))
    na_arvore = {str(r["no"]): str(r["raiz"]) for r in cur.fetchall()}
    fora = [i for i in ids_inicio if i not in na_arvore]
    if fora:
        return _indeterminado(
            tipo, "ponto_sem_controlador",
            "nenhum controlador de subrede alcança este ponto de partida (rede isolada, chave aberta no "
            "caminho ou barreira do próprio pedido): sem controlador não há montante nem jusante",
            inicio, controladores=fichas)

    alcancados = _descendentes(cur, ids_inicio) if tipo == "jusante" else _ancestrais(cur, ids_inicio)
    ancestrais = alcancados if tipo == "montante" else _ancestrais(cur, ids_inicio)
    laco = [n for n in _nos_de_laco(cur) if n in alcancados or n in ancestrais]
    if laco:
        return _indeterminado(
            tipo, "laco",
            "há mais de um caminho até o controlador de subrede passando por este ponto: qual elemento está "
            "a montante do outro depende do caminho escolhido, e o traçado não escolhe por conta própria",
            inicio, nos_do_laco=laco, controladores=fichas)

    elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, alcancados)
    raizes_alcancadas = sorted({na_arvore[i] for i in ids_inicio})
    return {
        "tipo": tipo, "origem_direcao": "controlador", "direcao": "definida", "motivo": None,
        "nos_do_laco": [], "avisos": [],
        "controladores": [f for f in fichas if f["no_id"] in raizes_alcancadas],
        "elementos": elementos, "contagem": len(elementos), "geometria": geometria,
        "nos_alcancados": len(alcancados),
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }
