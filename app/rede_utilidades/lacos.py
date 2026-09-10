"""Laços, caminho mais curto e isolados sobre pgRouting (item L4-02-d-lacos-e-caminho-curto).

Hipótese do item: os três traçados novos são construídos SOBRE pgRouting, no MESMO grafo (real + arestas
virtuais de dispositivo) montado pelo item irmão `tracado.py` (L4-02-a-conectado-e-subrede) — este módulo
reusa `tracado._resolver_ponto`/`_uuid_lista`/`_info_tipos` em vez de duplicá-los, e monta a própria versão
de `_montar_sql_arestas` porque precisa de colunas extras (comprimento e atributos, para custo e para a
cláusula "nulo nunca vira zero").

  1. `detectar_lacos`: `public.pgr_biconnectedComponents` particiona as arestas do grafo em blocos; um bloco
     com UMA aresta é uma ponte (árvore, sem ciclo); um bloco com MAIS de uma aresta é biconexo e portanto
     contém pelo menos um ciclo (com um único par de nós, duas arestas paralelas já são um laço de dois
     caminhos) — é a mesma definição do artigo "Detect loops in your network" da Esri citado no item.
  2. `caminho_curto`: `public.pgr_dijkstra` (k=1) ou `public.pgr_ksp` (k>1) sobre o grafo com custo = o
     atributo escolhido; padrão SEM atributo = comprimento geodésico (`comprimento_m`, o mesmo campo que a
     topologia grava por trecho — o "COMP" da BDGD, ver `topologia.py`). Se o atributo custom estiver nulo em
     QUALQUER trecho alcançável do grafo, a função recusa ANTES de rodar o algoritmo (nunca troca nulo por
     zero, que mudaria silenciosamente o caminho escolhido).
  3. `isolados`: `public.pgr_connectedComponents` sobre o MESMO grafo; um elemento é isolado quando o
     componente do seu nó não contém nenhum nó de uma feição da categoria `categoria_controlador` (padrão
     `fonte` — a categoria que o próprio pacote descreve como "onde a energia/água entra na rede; o traçado a
     montante termina aqui", o equivalente de disciplina ao "subnetwork controller" da Esri; outra categoria
     pode ser escolhida por parâmetro, mas tem de existir no pacote da rede)."""

import time

from app.erros import ErroAPI
from app.rede_utilidades import tracado as _tr

_TAG = "lacos_sql"


def _preparar_mapa(cur, rede_id: str, barreiras: list[dict]) -> tuple[float, list[str]]:
    """Mesma preparação de `tracado.tracar`: valida a rede e a topologia, resolve as barreiras e povoa
    `tracado_mapa` (uuid -> bigint) sem elas — reusada pelos três traçados deste módulo."""
    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    tolerancia_rede = float(r["tolerancia_m"])
    cur.execute("SELECT 1 FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(409, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")

    ids_barreira = [_tr._resolver_ponto(cur, rede_id, tolerancia_rede, b) for b in barreiras]
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS tracado_mapa (no_id uuid PRIMARY KEY, iid bigserial)")
    cur.execute("TRUNCATE tracado_mapa")
    excl_lit = _tr._uuid_lista(cur, ids_barreira)
    cur.execute(
        f"INSERT INTO tracado_mapa (no_id) SELECT id FROM plat.rede_topo_no "
        f"WHERE rede_id = %s::uuid AND id <> ALL({excl_lit})",
        (rede_id,),
    )
    return tolerancia_rede, ids_barreira


def _montar_arestas_custo(cur, rede_id: str, ignorar_transformacao: bool, atributo_custo: str | None) -> None:
    """Materializa `TEMP TABLE lacos_arestas (id, source, target, cost, comprimento_m, feicao_id, tipo_id)`
    com a união das arestas reais da topologia e das arestas virtuais por dispositivo (mesma regra de
    traversabilidade/fronteira de subrede de `tracado._montar_sql_arestas`), já traduzidas para os bigint de
    `tracado_mapa`. `cost` é `comprimento_m` quando `atributo_custo` é `None`, senão
    `atributos->>atributo_custo`, e a função RECUSA (ErroAPI 422) se esse atributo estiver nulo em qualquer
    trecho/dispositivo alcançável — nulo nunca vira zero."""
    rede_lit = cur.mogrify("%s::uuid", (rede_id,)).decode("utf-8")
    filtro_transformacao = (
        "AND NOT EXISTS (SELECT 1 FROM plat.rede_tipo_categoria rtc JOIN plat.rede_categoria rc "
        "ON rc.id = rtc.categoria_id WHERE rtc.tipo_id = f.tipo_id AND rc.codigo = 'transformacao')"
        if ignorar_transformacao else ""
    )
    sql_bruto = (
        "SELECT n1.iid AS source, n2.iid AS target, e.feicao_id, e.tipo_id, e.comprimento_m, e.atributos FROM ("
        f"  SELECT no_origem_id AS no_a, no_destino_id AS no_b, origem_id AS feicao_id, tipo_id,"
        f"    comprimento_m, atributos FROM plat.rede_topo_aresta"
        f"  WHERE rede_id = {rede_lit} AND no_origem_id IS NOT NULL AND no_destino_id IS NOT NULL"
        "  UNION ALL"
        "  SELECT n1.id AS no_a, n2.id AS no_b, f.id AS feicao_id, f.tipo_id, 0.0::double precision,"
        "    f.atributos"
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
        " JOIN tracado_mapa n1 ON n1.no_id = e.no_a"
        " JOIN tracado_mapa n2 ON n2.no_id = e.no_b"
    )
    cur.execute(
        "CREATE TEMP TABLE IF NOT EXISTS lacos_arestas (id bigserial PRIMARY KEY, source bigint NOT NULL, "
        "target bigint NOT NULL, cost double precision NOT NULL, comprimento_m double precision NOT NULL, "
        "feicao_id uuid, tipo_id uuid)"
    )
    cur.execute("TRUNCATE lacos_arestas")

    if atributo_custo is None:
        cur.execute(
            f"INSERT INTO lacos_arestas (source, target, cost, comprimento_m, feicao_id, tipo_id) "
            f"SELECT source, target, comprimento_m, comprimento_m, feicao_id, tipo_id FROM ({sql_bruto}) b"
        )
        return

    cur.execute(f"SELECT DISTINCT feicao_id FROM ({sql_bruto}) b WHERE atributos ->> %s IS NULL",
                (atributo_custo,))
    faltando = [str(r["feicao_id"]) for r in cur.fetchall()]
    if faltando:
        faltando.sort()
        raise ErroAPI(
            422, "atributo_custo_nulo",
            f"o atributo de custo '{atributo_custo}' está nulo em {len(faltando)} trecho(s)/dispositivo(s) "
            f"alcançável(is) nesta rede (ex.: {faltando[0]}) — nulo nunca vira zero; preencha o atributo em "
            "todos os trechos do trajeto ou escolha outro atributo",
            detalhe={"feicoes": faltando},
        )
    cur.execute(
        f"INSERT INTO lacos_arestas (source, target, cost, comprimento_m, feicao_id, tipo_id) "
        f"SELECT source, target, (atributos ->> %s)::double precision, comprimento_m, feicao_id, tipo_id "
        f"FROM ({sql_bruto}) b",
        (atributo_custo,),
    )


# --- laços: componentes biconexos ---------------------------------------------------------------------------

def detectar_lacos(cur, tenant_id: int, rede_id: str, barreiras: list[dict]) -> dict:
    """Todo bloco biconexo com mais de uma aresta é um laço (ciclo). Devolve um item por laço, com os
    elementos (feições únicas) que o compõem, para conferência manual no mapa."""
    inicio = time.perf_counter()
    _preparar_mapa(cur, rede_id, barreiras)
    _montar_arestas_custo(cur, rede_id, ignorar_transformacao=False, atributo_custo=None)

    cur.execute("SELECT 1 FROM lacos_arestas LIMIT 1")
    if cur.fetchone() is None:
        return {"tipo": "lacos", "contagem": 0, "lacos": [], "duracao_ms": _dur_ms(inicio)}

    cur.execute(
        f"SELECT component, edge FROM public.pgr_biconnectedComponents("
        f"${_TAG}$ SELECT id, source, target, cost FROM lacos_arestas ${_TAG}$)"
    )
    por_componente: dict[int, list[int]] = {}
    for row in cur.fetchall():
        por_componente.setdefault(row["component"], []).append(row["edge"])

    lacos_ids = [edges for edges in por_componente.values() if len(edges) > 1]
    resultado = []
    for edges in lacos_ids:
        cur.execute(
            "SELECT DISTINCT feicao_id, tipo_id FROM lacos_arestas WHERE id = ANY(%s)", (edges,)
        )
        elementos_raw = cur.fetchall()
        tipos = _tr._info_tipos(cur, rede_id, {str(r["tipo_id"]) for r in elementos_raw if r["tipo_id"]})
        elementos = []
        for r in elementos_raw:
            tid = str(r["tipo_id"]) if r["tipo_id"] else None
            info = tipos.get(tid, {})
            elementos.append({
                "feicao_id": str(r["feicao_id"]), "tipo_id": tid,
                "grupo": info.get("grupo"), "tipo_chave": info.get("chave"), "tipo_nome": info.get("nome"),
            })
        resultado.append({"arestas": len(edges), "elementos": elementos, "contagem": len(elementos)})

    resultado.sort(key=lambda x: -x["contagem"])
    return {"tipo": "lacos", "contagem": len(resultado), "lacos": resultado, "duracao_ms": _dur_ms(inicio)}


# --- isolados: sem caminho a nenhum controlador -------------------------------------------------------------

def isolados(cur, tenant_id: int, rede_id: str, categoria_controlador: str, barreiras: list[dict]) -> dict:
    """Elementos (dispositivos, por terminal de topologia) sem caminho a nenhuma feição da categoria
    `categoria_controlador` no MESMO grafo de `conectado` (atravessa a fronteira de subrede — isolamento é
    sobre a rede física inteira, não sobre um recorte por nível de tensão)."""
    inicio = time.perf_counter()
    _preparar_mapa(cur, rede_id, barreiras)
    _montar_arestas_custo(cur, rede_id, ignorar_transformacao=False, atributo_custo=None)

    cur.execute(
        "SELECT DISTINCT tm.iid FROM tracado_mapa tm JOIN plat.rede_topo_no n ON n.id = tm.no_id "
        "JOIN plat.rede_tipo_categoria rtc ON rtc.tipo_id = n.tipo_id "
        "JOIN plat.rede_categoria rc ON rc.id = rtc.categoria_id "
        "WHERE n.rede_id = %s::uuid AND n.papel = 'terminal' AND rc.codigo = %s",
        (rede_id, categoria_controlador),
    )
    iids_controlador = {row["iid"] for row in cur.fetchall()}
    if not iids_controlador:
        raise ErroAPI(
            422, "categoria_controlador_sem_feicao",
            f"nenhuma feição com categoria '{categoria_controlador}' nesta rede — informe uma categoria "
            "que exista no pacote instalado (ex.: 'fonte')",
        )

    cur.execute(
        f"SELECT node, component FROM public.pgr_connectedComponents("
        f"${_TAG}$ SELECT id, source, target, cost FROM lacos_arestas ${_TAG}$)"
    )
    componente_por_no = {row["node"]: row["component"] for row in cur.fetchall()}
    componentes_com_controlador = {
        componente_por_no[i] for i in iids_controlador if i in componente_por_no
    }

    cur.execute(
        "SELECT tm.iid, n.origem_id AS feicao_id, n.tipo_id, n.terminal_num FROM tracado_mapa tm "
        "JOIN plat.rede_topo_no n ON n.id = tm.no_id WHERE n.rede_id = %s::uuid AND n.papel = 'terminal'",
        (rede_id,),
    )
    isolados_raw = [
        r for r in cur.fetchall()
        if r["iid"] not in iids_controlador
        and componente_por_no.get(r["iid"]) not in componentes_com_controlador
    ]
    feicao_ids_vistos: set[str] = set()
    elementos = []
    tipos = _tr._info_tipos(cur, rede_id, {str(r["tipo_id"]) for r in isolados_raw if r["tipo_id"]})
    for r in isolados_raw:
        fid = str(r["feicao_id"])
        if fid in feicao_ids_vistos:
            continue
        feicao_ids_vistos.add(fid)
        tid = str(r["tipo_id"]) if r["tipo_id"] else None
        info = tipos.get(tid, {})
        elementos.append({
            "feicao_id": fid, "tipo_id": tid, "terminal": r["terminal_num"],
            "grupo": info.get("grupo"), "tipo_chave": info.get("chave"), "tipo_nome": info.get("nome"),
        })
    return {
        "tipo": "isolados", "categoria_controlador": categoria_controlador,
        "contagem": len(elementos), "elementos": elementos, "duracao_ms": _dur_ms(inicio),
    }


# --- caminho mais curto (dijkstra) e k alternativas (ksp) ----------------------------------------------------

def caminho_curto(cur, tenant_id: int, rede_id: str, origem: dict, destino: dict,
                   atributo_custo: str | None, k: int, barreiras: list[dict]) -> dict:
    """`k=1`: `pgr_dijkstra`. `k>1`: `pgr_ksp` (Yen), devolvendo até `k` caminhos DISTINTOS quando existirem
    (nunca inventa alternativa que não existe — `k_encontrados` pode ser menor que `k_solicitado`, inclusive
    1 numa rede radial pura, onde só existe um caminho possível entre dois pontos quaisquer)."""
    inicio = time.perf_counter()
    tolerancia_rede, ids_barreira = _preparar_mapa(cur, rede_id, barreiras)
    origem_id = _tr._resolver_ponto(cur, rede_id, tolerancia_rede, origem)
    destino_id = _tr._resolver_ponto(cur, rede_id, tolerancia_rede, destino)
    if origem_id == destino_id:
        raise ErroAPI(422, "origem_igual_destino", "origem e destino são o mesmo nó de topologia")
    if origem_id in ids_barreira or destino_id in ids_barreira:
        raise ErroAPI(422, "extremo_e_barreira", "origem ou destino não pode também ser barreira")

    _montar_arestas_custo(cur, rede_id, ignorar_transformacao=False, atributo_custo=atributo_custo)
    cur.execute("SELECT iid FROM tracado_mapa WHERE no_id = %s::uuid", (origem_id,))
    origem_iid = cur.fetchone()["iid"]
    cur.execute("SELECT iid FROM tracado_mapa WHERE no_id = %s::uuid", (destino_id,))
    destino_iid = cur.fetchone()["iid"]

    caminhos_bruto: dict[int, list[dict]] = {}
    if k <= 1:
        cur.execute(
            f"SELECT seq, edge, agg_cost FROM public.pgr_dijkstra("
            f"${_TAG}$ SELECT id, source, target, cost FROM lacos_arestas ${_TAG}$, %s, %s, false) "
            "ORDER BY seq",
            (origem_iid, destino_iid),
        )
        linhas = cur.fetchall()
        if linhas:
            caminhos_bruto[1] = linhas
    else:
        cur.execute(
            f"SELECT path_id, seq, edge, agg_cost FROM public.pgr_ksp("
            f"${_TAG}$ SELECT id, source, target, cost FROM lacos_arestas ${_TAG}$, %s, %s, %s, false) "
            "ORDER BY path_id, seq",
            (origem_iid, destino_iid, k),
        )
        for row in cur.fetchall():
            caminhos_bruto.setdefault(row["path_id"], []).append(row)

    if not caminhos_bruto:
        raise ErroAPI(404, "sem_caminho", "não existe caminho entre origem e destino nesta rede "
                      "(travessabilidade ou barreira pode estar bloqueando)")

    resultado_caminhos = []
    for ordem in sorted(caminhos_bruto):
        linhas_c = caminhos_bruto[ordem]
        arestas_ids = [r["edge"] for r in linhas_c if r["edge"] != -1]
        custo_total = linhas_c[-1]["agg_cost"] if linhas_c else 0.0
        detalhe = {}
        if arestas_ids:
            cur.execute(
                "SELECT id, feicao_id, tipo_id, comprimento_m FROM lacos_arestas WHERE id = ANY(%s)",
                (arestas_ids,),
            )
            detalhe = {r["id"]: r for r in cur.fetchall()}
        tipos = _tr._info_tipos(cur, rede_id, {str(detalhe[e]["tipo_id"]) for e in arestas_ids
                                                if detalhe[e]["tipo_id"]})
        elementos = []
        comprimento_total_m = 0.0
        for eid in arestas_ids:
            d = detalhe[eid]
            tid = str(d["tipo_id"]) if d["tipo_id"] else None
            info = tipos.get(tid, {})
            elementos.append({
                "feicao_id": str(d["feicao_id"]), "tipo_id": tid,
                "grupo": info.get("grupo"), "tipo_chave": info.get("chave"), "tipo_nome": info.get("nome"),
            })
            comprimento_total_m += float(d["comprimento_m"])
        resultado_caminhos.append({
            "ordem": ordem, "elementos": elementos, "contagem": len(elementos),
            "comprimento_total_m": comprimento_total_m, "custo_total": float(custo_total),
        })

    return {
        "tipo": "caminho_curto", "atributo_custo": atributo_custo,
        "k_solicitado": k, "k_encontrados": len(resultado_caminhos),
        "caminhos": resultado_caminhos, "duracao_ms": _dur_ms(inicio),
    }


def _dur_ms(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)
