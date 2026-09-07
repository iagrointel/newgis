"""Traçado sobre pgRouting (item L4-02-a-conectado-e-subrede).

Hipótese do item: os dois traçados básicos são construídos SOBRE pgRouting, não por uma varredura recursiva em
Python — `public.pgr_connectedComponents` (pgRouting 4.0.1, extensão em `public`, nunca reescrita pelo
`CursorSchemaAmbiente`, mesmo padrão de `plat.rede_menor_caminho` no item irmão L4-01-modelo-rede) devolve o
componente conexo de cada nó do grafo que montamos por chamada, a partir da topologia derivada
(`plat.rede_topo_no`/`rede_topo_aresta`, item L4-01-b).

Por que a topologia sozinha NÃO basta: cada terminal de um dispositivo multi-terminal (chave, regulador,
transformador — `topologia.py::_resolver_uniao`) vira um nó PRÓPRIO, nunca fundido com o outro terminal do
MESMO dispositivo — a topologia deliberadamente NÃO atravessa o dispositivo (ver o comentário de
`_resolver_uniao`). Sem mais nada, um traçado que andasse só por `rede_topo_aresta` pararia em qualquer
dispositivo multi-terminal, sempre — não haveria diferença nenhuma entre "conectado" e "subrede". O traçado
deste item soma ao grafo real uma ARESTA VIRTUAL por `caminho_valido` declarado no `rede_terminal_config` do
pacote (ex.: chave "lado_1 -> lado_2, fechado"; transformador "alta -> baixa"), condicionada a:

  1. TRAVERSABILIDADE (vale para os dois tipos de traçado): o caminho só conduz se a feição não estiver com
     `atributos.estado = "aberto"` — convenção do produto, não amarrada a nenhuma coluna de fonte específica
     (a BDGD declara a posição normal de operação da chave em `unsemt_p_n_ope`; cabe ao importador traduzir
     isso para `atributos.estado` — fora do escopo deste item). Sem a chave `estado`, o caminho conduz (regra
     "fechado é o padrão", o mesmo nome que os `caminhos_validos` do pacote usam).
  2. FRONTEIRA DE SUBREDE (só para `tipo=subrede`): um caminho cuja feição carrega a categoria `transformacao`
     ("muda o nível de tensão e separa duas subredes", descrição do pacote elétrica-BR) NUNCA conduz, mesmo
     fechado — é isso que faz "subrede" parar num controlador de outra subrede enquanto "conectado" atravessa.
  3. BARREIRA (pontos que o CHAMADOR passa, não dado da rede): qualquer nó de topologia citado em `barreiras`
     é removido do grafo inteiro antes de montar o traçado — nem ele nem nada além dele entra no resultado,
     dos dois lados (a mesma barreira serve para conter um traçado que cresce em mais de uma direção).

`GET topologia/alcance` (item L4-01-b) fica como estava: alcance puro sobre `rede_topo_aresta`, sem estas
arestas virtuais nem barreira — é o "traçado mínimo" da refutação daquele item, não este."""

import time
import uuid as uuid_mod

from app.erros import ErroAPI

TIPOS_TRACADO = ("conectado", "subrede")
_TAG_SQL = "tracado_arestas_sql"  # dollar-quote tag do texto passado a pgr_connectedComponents


def _uuid_lista(cur, valores: list[str]) -> str:
    """`ARRAY[...]::uuid[]` literal e seguro: os valores só chegam aqui depois de resolvidos por ESTE módulo
    (nunca texto cru do pedido), então embuti-los como literal no texto que vai para `pgr_connectedComponents`
    (que executa a string recebida via EXECUTE interno — não aceita bind) é seguro."""
    if not valores:
        return "ARRAY[]::uuid[]"
    return cur.mogrify("%s::uuid[]", (list(valores),)).decode("utf-8")


def _resolver_ponto(cur, rede_id: str, tolerancia_padrao_m: float, ponto: dict) -> str:
    """Devolve o id (uuid, texto) do `rede_topo_no` para um ponto de partida ou barreira: por feição+terminal
    ou por coordenada com tolerância (própria do ponto, ou a tolerância DA REDE por padrão)."""
    feicao_id = ponto.get("feicao_id")
    lon, lat = ponto.get("lon"), ponto.get("lat")
    if feicao_id and (lon is not None or lat is not None):
        raise ErroAPI(422, "ponto_ambiguo", "informe feicao_id OU lon/lat, nunca os dois")
    if feicao_id:
        try:
            feicao_id = str(uuid_mod.UUID(feicao_id))
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAPI(404, "no_inexistente", "feição de partida inexistente") from e
        terminal = ponto.get("terminal")
        if terminal is not None:
            cur.execute(
                "SELECT id FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND papel = 'terminal' "
                "AND origem_id = %s::uuid AND terminal_num = %s",
                (rede_id, feicao_id, terminal),
            )
        else:
            cur.execute(
                "SELECT id FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND papel = 'terminal' "
                "AND origem_id = %s::uuid",
                (rede_id, feicao_id),
            )
        linhas = cur.fetchall()
        if not linhas:
            raise ErroAPI(404, "no_inexistente", "esta feição não tem nó de topologia nesta rede "
                          "(topologia desatualizada ou terminal errado?)")
        if len(linhas) > 1:
            raise ErroAPI(422, "terminal_ambiguo",
                          "esta feição tem mais de um terminal; informe 'terminal' para escolher qual")
        return str(linhas[0]["id"])
    if lon is None or lat is None:
        raise ErroAPI(422, "ponto_invalido", "informe feicao_id ou lon/lat")
    tolerancia = ponto.get("tolerancia_m") or tolerancia_padrao_m
    cur.execute(
        "SELECT id FROM plat.rede_topo_no WHERE rede_id = %s::uuid "
        "AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s) "
        "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326) LIMIT 1",
        (rede_id, lon, lat, tolerancia, lon, lat),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "no_nao_encontrado_na_tolerancia",
                      f"nenhum nó de topologia a até {tolerancia} m deste ponto")
    return str(r["id"])


def _montar_sql_arestas(cur, rede_id: str, ignorar_transformacao: bool) -> str:
    """Texto SQL (sem bind — vai para `pgr_connectedComponents`) com a UNIÃO das arestas reais da topologia e
    das arestas virtuais de dispositivo (um `caminho_valido` do terminal config = uma aresta condicionada à
    traversabilidade e, no traçado de subrede, também à categoria `transformacao`). `tracado_mapa` (temp table
    já sem os nós de barreira, ver `tracar()`) faz a tradução uuid -> bigint que `pgr_connectedComponents`
    exige, e o JOIN nela é o que garante que uma ponta em nó de barreira nunca aparece nesta lista."""
    rede_lit = cur.mogrify("%s::uuid", (rede_id,)).decode("utf-8")
    filtro_transformacao = (
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_tipo_categoria rtc JOIN plat.rede_categoria rc "
        "ON rc.id = rtc.categoria_id WHERE rtc.tipo_id = f.tipo_id AND rc.codigo = 'transformacao')"
        if ignorar_transformacao else ""
    )
    return (
        "SELECT row_number() OVER () AS id, m1.iid AS source, m2.iid AS target, 1.0::float AS cost FROM ("
        f"  SELECT no_origem_id AS a, no_destino_id AS b FROM plat.rede_topo_aresta"
        f"  WHERE rede_id = {rede_lit} AND no_origem_id IS NOT NULL AND no_destino_id IS NOT NULL"
        "  UNION ALL"
        "  SELECT n1.id AS a, n2.id AS b"
        "  FROM plat.rede_feicao_ponto f"
        "  JOIN plat.rede_tipo t ON t.id = f.tipo_id"
        "  JOIN plat.rede_terminal_config tc ON tc.id = t.terminal_id"
        "  CROSS JOIN LATERAL jsonb_to_recordset(tc.caminhos_validos) AS cv(de int, para int, nome text)"
        f"  JOIN plat.rede_topo_no n1 ON n1.rede_id = {rede_lit} AND n1.papel = 'terminal'"
        "     AND n1.origem_id = f.id AND n1.terminal_num = cv.de"
        f"  JOIN plat.rede_topo_no n2 ON n2.rede_id = {rede_lit} AND n2.papel = 'terminal'"
        "     AND n2.origem_id = f.id AND n2.terminal_num = cv.para"
        f"  WHERE f.rede_id = {rede_lit}"
        "     AND coalesce(f.atributos->>'estado', 'fechado') <> 'aberto'"
        f"     {filtro_transformacao}"
        ") e"
        " JOIN tracado_mapa m1 ON m1.no_id = e.a"
        " JOIN tracado_mapa m2 ON m2.no_id = e.b"
    )


def _info_tipos(cur, rede_id: str, tipo_ids: set) -> dict:
    if not tipo_ids:
        return {}
    cur.execute(
        "SELECT t.id, t.chave, t.nome, g.codigo AS grupo FROM plat.rede_tipo t "
        "JOIN plat.rede_grupo g ON g.id = t.grupo_id WHERE t.rede_id = %s::uuid AND t.id = ANY(%s::uuid[])",
        (rede_id, list(tipo_ids)),
    )
    return {str(r["id"]): {"chave": r["chave"], "nome": r["nome"], "grupo": r["grupo"]} for r in cur.fetchall()}


def tracar(cur, tenant_id: int, rede_id: str, tipo: str, pontos_partida: list[dict],
           barreiras: list[dict]) -> dict:
    """Traça `tipo` ('conectado' ou 'subrede') a partir de `pontos_partida`, parando em `barreiras`. Devolve
    elementos (id de ativo, tipo, terminal), geometria agregada (GeoJSON) e contagem, com o tempo medido."""
    if tipo not in TIPOS_TRACADO:
        raise ErroAPI(422, "tipo_invalido", f"tipo deve ser um de {TIPOS_TRACADO}")
    if not pontos_partida:
        raise ErroAPI(422, "sem_ponto_de_partida", "informe ao menos um ponto de partida")
    inicio = time.perf_counter()

    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    tolerancia_rede = float(r["tolerancia_m"])
    cur.execute("SELECT 1 FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(409, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")

    ids_barreira = [_resolver_ponto(cur, rede_id, tolerancia_rede, b) for b in barreiras]
    ids_inicio = [_resolver_ponto(cur, rede_id, tolerancia_rede, p) for p in pontos_partida]
    tocados_por_barreira = [i for i in ids_inicio if i in ids_barreira]
    if tocados_por_barreira:
        raise ErroAPI(422, "inicio_e_barreira", "um ponto de partida não pode também ser barreira")

    cur.execute("CREATE TEMP TABLE IF NOT EXISTS tracado_mapa (no_id uuid PRIMARY KEY, iid bigserial)")
    cur.execute("TRUNCATE tracado_mapa")
    excl_lit = _uuid_lista(cur, ids_barreira)
    cur.execute(
        f"INSERT INTO tracado_mapa (no_id) SELECT id FROM plat.rede_topo_no "
        f"WHERE rede_id = %s::uuid AND id <> ALL({excl_lit})",
        (rede_id,),
    )

    sql_arestas = _montar_sql_arestas(cur, rede_id, ignorar_transformacao=(tipo == "subrede"))
    sql_cc = f"SELECT * FROM public.pgr_connectedComponents(${_TAG_SQL}$ {sql_arestas} ${_TAG_SQL}$)"
    cur.execute(
        f"WITH cc AS ({sql_cc}), "
        "inicio AS (SELECT iid FROM tracado_mapa WHERE no_id = ANY(%(inicios)s::uuid[])), "
        "comp AS (SELECT DISTINCT cc.component FROM cc JOIN inicio ON inicio.iid = cc.node) "
        "SELECT no_id FROM tracado_mapa tm JOIN cc ON cc.node = tm.iid "
        "WHERE cc.component IN (SELECT component FROM comp) "
        "UNION "
        "SELECT unnest(%(inicios)s::uuid[])",
        {"inicios": ids_inicio},
    )
    alcancados = {str(row["no_id"]) for row in cur.fetchall()}

    cur.execute(
        "SELECT origem_id AS feicao_id, tipo_id, terminal_num FROM plat.rede_topo_no "
        "WHERE rede_id = %s::uuid AND papel = 'terminal' AND id = ANY(%s::uuid[])",
        (rede_id, list(alcancados)),
    )
    elementos_ponto = [
        {"feicao_id": str(row["feicao_id"]), "tipo_id": str(row["tipo_id"]), "terminal": row["terminal_num"]}
        for row in cur.fetchall()
    ]
    cur.execute(
        "SELECT DISTINCT origem_id AS feicao_id, tipo_id FROM plat.rede_topo_aresta "
        "WHERE rede_id = %s::uuid AND no_origem_id = ANY(%s::uuid[]) AND no_destino_id = ANY(%s::uuid[])",
        (rede_id, list(alcancados), list(alcancados)),
    )
    elementos_linha = [
        {"feicao_id": str(row["feicao_id"]), "tipo_id": str(row["tipo_id"]) if row["tipo_id"] else None,
         "terminal": None}
        for row in cur.fetchall()
    ]
    elementos = elementos_ponto + elementos_linha

    tipos = _info_tipos(cur, rede_id, {e["tipo_id"] for e in elementos if e["tipo_id"]})
    for e in elementos:
        info = tipos.get(e["tipo_id"], {})
        e["grupo"] = info.get("grupo")
        e["tipo_chave"] = info.get("chave")
        e["tipo_nome"] = info.get("nome")

    geometria = None
    if alcancados:
        cur.execute(
            "SELECT ST_AsGeoJSON(ST_Collect(geom)) AS geojson FROM ("
            "  SELECT geom FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])"
            "  UNION ALL"
            "  SELECT geom FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid"
            "    AND no_origem_id = ANY(%s::uuid[]) AND no_destino_id = ANY(%s::uuid[])"
            ") u",
            (rede_id, list(alcancados), rede_id, list(alcancados), list(alcancados)),
        )
        linha_geo = cur.fetchone()
        if linha_geo and linha_geo["geojson"]:
            import json as _json

            geometria = _json.loads(linha_geo["geojson"])

    duracao_ms = int((time.perf_counter() - inicio) * 1000)
    return {
        "tipo": tipo, "elementos": elementos, "contagem": len(elementos), "geometria": geometria,
        "duracao_ms": duracao_ms, "nos_alcancados": len(alcancados),
    }
