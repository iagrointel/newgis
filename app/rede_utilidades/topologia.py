"""Construção da topologia derivada (item L4-01-b-topologia-derivada; ADR 0020).

Hipótese do item: as camadas de rede (`plat.rede_feicao_ponto`/`rede_feicao_linha`, ver `feicoes.py`) continuam
camadas normais e editáveis; `habilitar()` RECONSTRÓI o índice derivado inteiro — nunca lê o índice anterior, só
apaga e refaz — a partir delas: `plat.rede_topo_no` (um nó por vértice de conexão e por terminal de dispositivo)
e `plat.rede_topo_aresta` (uma aresta por trecho). Coincidência geométrica com a tolerância DA REDE (`geography`,
`ST_DWithin`) mais associações explícitas (`plat.rede_regra`, tipos `conectividade_no_trecho`/
`conectividade_entre_nos`) decidem o que vira o MESMO nó.

Por que "mais associações explícitas" não é enfeite: um dispositivo com 2+ terminais (ex.: transformador,
`alta`/`baixa`) tem os terminais no MESMO ponto físico — coincidência pura os fundiria num nó só, apagando a
fronteira MT/BT que o transformador existe para marcar. Aqui:
  1. trecho-trecho (mesma linha se tocando) sempre pode fundir, seja por MESMO grupo (continuação natural do
     mesmo tipo de ativo) seja por uma regra de conectividade explícita entre os dois tipos (ex.: ramal ->
     trecho de baixa tensão) — não há ambiguidade: uma linha só tem 2 pontas, geometricamente distintas.
  2. um terminal de dispositivo com 0 ou 1 terminal (`sem_terminal`/`um_terminal`) também nunca é ambíguo —
     funde direto com qualquer trecho compatível por regra.
  3. um terminal de dispositivo com 2+ terminais (`dois_terminais*`) é resolvido em separado, por dispositivo:
     os candidatos compatíveis são agrupados pela ORDEM do tier do trecho vizinho (`rede_tier.ordem`); havendo
     2+ tiers distintos, o terminal com `montante=true` liga ao tier de ordem menor (mais a montante) e o(s)
     `montante=false` ao(s) de ordem maior — regra genérica, não amarrada a nome de terminal. Havendo só UM tier
     entre os candidatos (ex.: uma chave em série no meio do MESMO trecho), a ordem de chegada decide, round-
     robin — fronteira honesta: sem traçado de rede não há como saber o lado real sem essa convenção.

Nunca cruzamento sem nó: só vértices DECLARADOS (ponta de linha, ponto de dispositivo) viram candidato a nó;
um cruzamento no MEIO de duas linhas nunca gera candidato, logo nunca conecta (cláusula 3 do portão)."""

import json
import math
import time
import uuid
from collections import defaultdict

import psycopg2.extras

TIPOS_REGRA_CONECTIVIDADE = ("conectividade_no_trecho", "conectividade_entre_nos")
_EPS_COMPRIMENTO_M = 1e-6  # abaixo disso o trecho é degenerado (origem == destino): "aresta sem nó"


_LOTE_MAX = 4000  # medido: acima disso, um INSERT só (tabela com FK composta + GIST) piora bem mais que linear


def _inserir_lote(cur, sql_ate_values: str, linhas: list, template: str, tamanho_lote: int = _LOTE_MAX) -> None:
    """`execute_values` reescrito à mão: `psycopg2.extras.execute_values` monta a consulta final em BYTES e
    chama `cur.execute(bytes)` — `CursorSchemaAmbiente.execute` (app/schema_ambiente.py) só reescreve `plat.`
    para o schema da trilha quando a consulta é `str` (achado deste item: nenhum outro módulo usava
    `execute_values` com uma tabela `plat.*`). Aqui o texto FINAL sempre passa por `cur.execute` como `str`.

    Em lotes de `tamanho_lote`, não tudo numa `INSERT` só: medido na escala real (`tests/medidas/L4-01-b.json`)
    que uma única `INSERT ... VALUES` com ~100 mil linhas contra uma tabela com FK composta para outra tabela
    recém-inserida NA MESMA transação (mesma sem commit no meio) degrada bem pior que linear — provável custo
    de bloqueio de linha por FK se acumulando por toda a transação. Em lotes, o custo por linha fica estável."""
    for i in range(0, len(linhas), tamanho_lote):
        pedaco = linhas[i:i + tamanho_lote]
        if not pedaco:
            continue
        partes = [cur.mogrify(template, linha).decode("utf-8") for linha in pedaco]
        cur.execute(sql_ate_values + ",".join(partes))


class UniaoBusca:
    """Union-find com compressão de caminho; registra qualquer índice na primeira consulta (todo candidato,
    mesmo sem nenhum par, vira seu próprio grupo)."""

    def __init__(self):
        self._pai: dict[int, int] = {}

    def achar(self, x: int) -> int:
        self._pai.setdefault(x, x)
        raiz = x
        while self._pai[raiz] != raiz:
            raiz = self._pai[raiz]
        while self._pai[x] != raiz:
            self._pai[x], x = raiz, self._pai[x]
        return raiz

    def unir(self, a: int, b: int) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self._pai[rb] = ra


def _carregar_esquema(cur, rede_id: str) -> dict:
    cur.execute("SELECT id, tier_id, terminal_id FROM plat.rede_tipo WHERE rede_id = %s::uuid", (rede_id,))
    tipos = {r["id"]: r for r in cur.fetchall()}
    cur.execute("SELECT id, ordem FROM plat.rede_tier WHERE rede_id = %s::uuid", (rede_id,))
    tier_ordem = {r["id"]: r["ordem"] for r in cur.fetchall()}
    cur.execute("SELECT id, terminais FROM plat.rede_terminal_config WHERE rede_id = %s::uuid", (rede_id,))
    terminais_por_config = {r["id"]: r["terminais"] for r in cur.fetchall()}
    cur.execute(
        "SELECT tipo, de_tipo_id, para_tipo_id FROM plat.rede_regra WHERE rede_id = %s::uuid AND tipo = ANY(%s)",
        (rede_id, list(TIPOS_REGRA_CONECTIVIDADE)),
    )
    regra_pares = {frozenset((r["de_tipo_id"], r["para_tipo_id"])) for r in cur.fetchall()}

    def terminais_do_tipo(tipo_id):
        cfg_id = tipos[tipo_id]["terminal_id"]
        if cfg_id is None:
            return []
        return terminais_por_config.get(cfg_id, [])

    return {
        "tipos": tipos, "tier_ordem": tier_ordem, "regra_pares": regra_pares,
        "terminais_do_tipo": terminais_do_tipo,
    }


def _carregar_feicoes(cur, rede_id: str) -> tuple[list[dict], list[dict]]:
    cur.execute(
        "SELECT f.id, f.tipo_id, t.grupo_id, ST_X(ST_StartPoint(f.geom)) AS x0, ST_Y(ST_StartPoint(f.geom)) AS y0, "
        "ST_X(ST_EndPoint(f.geom)) AS x1, ST_Y(ST_EndPoint(f.geom)) AS y1, "
        "ST_Length(f.geom::geography) AS comprimento_m, f.fase_bitmask, f.atributos, ST_AsText(f.geom) AS geom_wkt "
        "FROM plat.rede_feicao_linha f JOIN plat.rede_tipo t ON t.id = f.tipo_id WHERE f.rede_id = %s::uuid",
        (rede_id,),
    )
    linhas = cur.fetchall()
    cur.execute(
        "SELECT f.id, f.tipo_id, ST_X(f.geom) AS x, ST_Y(f.geom) AS y "
        "FROM plat.rede_feicao_ponto f WHERE f.rede_id = %s::uuid",
        (rede_id,),
    )
    pontos = cur.fetchall()
    return linhas, pontos


def _montar_candidatos(linhas: list[dict], pontos: list[dict], esquema: dict):
    """Devolve (candidatos, idx_por_ponta_trecho, idx_por_terminal_dispositivo, arestas_sem_no_ids)."""
    candidatos: list[dict] = []
    idx_trecho: dict[tuple, int] = {}
    idx_terminal: dict[tuple, int] = {}
    sem_no: set = set()

    def add(kind, feicao_id, tipo_id, grupo_id, ponta, terminal_num, x, y):
        idx = len(candidatos)
        candidatos.append({"kind": kind, "feicao_id": feicao_id, "tipo_id": tipo_id, "grupo_id": grupo_id,
                            "ponta": ponta, "terminal_num": terminal_num, "x": x, "y": y})
        return idx

    for linha in linhas:
        if linha["comprimento_m"] < _EPS_COMPRIMENTO_M:
            sem_no.add(linha["id"])
            continue
        idx_trecho[(linha["id"], "origem")] = add(
            "trecho", linha["id"], linha["tipo_id"], linha["grupo_id"], "origem", None, linha["x0"], linha["y0"])
        idx_trecho[(linha["id"], "destino")] = add(
            "trecho", linha["id"], linha["tipo_id"], linha["grupo_id"], "destino", None, linha["x1"], linha["y1"])

    for ponto in pontos:
        terminais = esquema["terminais_do_tipo"](ponto["tipo_id"])
        for t in terminais:
            idx_terminal[(ponto["id"], t["id"])] = add(
                "terminal", ponto["id"], ponto["tipo_id"], None, None, t["id"], ponto["x"], ponto["y"])

    return candidatos, idx_trecho, idx_terminal, sem_no


def _pares_proximos(cur, candidatos: list[dict], tolerancia_m: float) -> list[tuple]:
    if not candidatos:
        return []
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS topo_cand ("
                "idx int PRIMARY KEY, kind text NOT NULL, feicao_id uuid NOT NULL, tipo_id uuid NOT NULL, "
                "grupo_id uuid, terminal_num int, geom geometry(Point,4326) NOT NULL)")
    cur.execute("TRUNCATE topo_cand")
    linhas = [
        (i, c["kind"], c["feicao_id"], c["tipo_id"], c["grupo_id"], c["terminal_num"], c["x"], c["y"])
        for i, c in enumerate(candidatos)
    ]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO topo_cand (idx, kind, feicao_id, tipo_id, grupo_id, terminal_num, geom) VALUES %s",
        linhas,
        template="(%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s), 4326))",
    )
    cur.execute("CREATE INDEX IF NOT EXISTS ix_topo_cand_geom ON topo_cand USING gist (geom)")
    cur.execute("ANALYZE topo_cand")
    # achado deste item: `ST_DWithin(geom::geography, geom::geography, tol)` sozinho NUNCA usa o índice GIST
    # (o cast para geography tira o suporte de índice da função) — vira busca sequencial a(n)×a(n), inviável
    # a partir de umas dezenas de milhares de candidatos (medido: 50 mil pontos não terminava em 2 min).
    # Prefiltra por `ST_DWithin(geom, geom, graus)` (geometria pura, usa o índice) com uma folga em GRAUS
    # generosa o bastante para nunca excluir um par que a checagem geodésica de verdade aceitaria — e só
    # ENTÃO aplica `ST_DWithin(::geography)` como conferência exata sobre o punhado de pares vizinhos.
    cur.execute("SELECT max(abs(ST_Y(geom))) AS lat_max FROM topo_cand")
    lat_max = min(float((cur.fetchone() or {"lat_max": 0}).get("lat_max") or 0.0) + 1.0, 89.0)
    graus_folga = (tolerancia_m / (110_540.0 * math.cos(math.radians(lat_max)))) * 1.5
    cur.execute(
        "SELECT a.idx AS a_idx, a.kind AS a_kind, a.feicao_id AS a_feicao_id, a.tipo_id AS a_tipo_id, "
        "       a.grupo_id AS a_grupo_id, a.terminal_num AS a_terminal_num, "
        "       b.idx AS b_idx, b.kind AS b_kind, b.feicao_id AS b_feicao_id, b.tipo_id AS b_tipo_id, "
        "       b.grupo_id AS b_grupo_id, b.terminal_num AS b_terminal_num "
        "FROM topo_cand a JOIN topo_cand b ON a.idx < b.idx "
        "WHERE ST_DWithin(a.geom, b.geom, %s) "
        "  AND ST_DWithin(a.geom::geography, b.geom::geography, %s) "
        "  AND NOT (a.kind = 'trecho' AND b.kind = 'trecho' AND a.feicao_id = b.feicao_id)",
        (graus_folga, tolerancia_m),
    )
    pares = cur.fetchall()
    cur.execute("DROP TABLE topo_cand")
    return pares


def _resolver_uniao(candidatos: list[dict], pares: list, esquema: dict) -> UniaoBusca:
    uf = UniaoBusca()
    # feicao_id do dispositivo multi-terminal -> [(meu_idx, terminal_num, outro_idx, outro_tipo_id)]
    diferido: dict = defaultdict(list)

    def n_terminais(tipo_id):
        return len(esquema["terminais_do_tipo"](tipo_id))

    for r in pares:
        ia, ka, tia, ga = r["a_idx"], r["a_kind"], r["a_tipo_id"], r["a_grupo_id"]
        ib, kb, tib, gb = r["b_idx"], r["b_kind"], r["b_tipo_id"], r["b_grupo_id"]
        if ka == "trecho" and kb == "trecho":
            permitido = ga == gb or frozenset((tia, tib)) in esquema["regra_pares"]
        else:
            permitido = frozenset((tia, tib)) in esquema["regra_pares"]
        if not permitido:
            continue
        multi_a = ka == "terminal" and n_terminais(tia) >= 2
        multi_b = kb == "terminal" and n_terminais(tib) >= 2
        if not multi_a and not multi_b:
            uf.unir(ia, ib)
            continue
        ca, cb = candidatos[ia], candidatos[ib]
        if multi_a:
            diferido[ca["feicao_id"]].append((ia, ca["terminal_num"], ib, tib))
        if multi_b:
            diferido[cb["feicao_id"]].append((ib, cb["terminal_num"], ia, tia))

    idx_terminal_do_dispositivo: dict = defaultdict(dict)
    tipo_do_dispositivo: dict = {}
    for i, c in enumerate(candidatos):
        if c["kind"] == "terminal":
            idx_terminal_do_dispositivo[c["feicao_id"]][c["terminal_num"]] = i
            tipo_do_dispositivo[c["feicao_id"]] = c["tipo_id"]

    for feicao_id, entradas in diferido.items():
        # achado de performance (medido na escala real, tests/medidas/L4-01-b.json): isto era um
        # `next(... for c in candidatos if ...)` — busca LINEAR nos ~200 mil candidatos, uma vez por
        # dispositivo multi-terminal (5,5 mil vezes na rede de teste) = ~1 bilhão de comparações, 38 s
        # sozinho. O mapa acima já tem a resposta em O(1); construído numa única passada, junto do outro.
        tipo_id = tipo_do_dispositivo[feicao_id]
        terminais_cfg = esquema["terminais_do_tipo"](tipo_id)
        n = len(terminais_cfg)
        if n == 0:
            continue
        idx_por_num = idx_terminal_do_dispositivo[feicao_id]
        por_tier: dict = defaultdict(list)
        for (_meu_idx, _meu_num, outro_idx, outro_tipo_id) in entradas:
            tier_id = esquema["tipos"].get(outro_tipo_id, {}).get("tier_id")
            ordem = esquema["tier_ordem"].get(tier_id)
            por_tier[ordem].append(outro_idx)
        tiers_distintos = sorted(k for k in por_tier if k is not None)
        terminais_por_montante = sorted(terminais_cfg, key=lambda t: (not t["montante"], t["id"]))
        if len(tiers_distintos) >= 2:
            for i, ordem in enumerate(tiers_distintos):
                num = terminais_por_montante[min(i, n - 1)]["id"]
                no_idx = idx_por_num.get(num)
                if no_idx is None:
                    continue
                for outro_idx in por_tier[ordem]:
                    uf.unir(no_idx, outro_idx)
        else:
            todos_outros = sorted({idx for lst in por_tier.values() for idx in lst})
            nums_ordenados = sorted(t["id"] for t in terminais_cfg)
            for i, outro_idx in enumerate(todos_outros):
                num = nums_ordenados[i % n]
                no_idx = idx_por_num.get(num)
                if no_idx is None:
                    continue
                uf.unir(no_idx, outro_idx)

    return uf


def habilitar(cur, tenant_id: int, rede_id: str, usuario_id: int | None) -> dict:
    """Reconstrói a topologia inteira da rede. Devolve o resumo (mesmo formato de `plat.rede_topo_resumo`)."""
    inicio = time.perf_counter()

    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid FOR UPDATE", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise LookupError("rede_inexistente")
    tolerancia_m = float(r["tolerancia_m"])

    esquema = _carregar_esquema(cur, rede_id)
    linhas, pontos = _carregar_feicoes(cur, rede_id)
    candidatos, idx_trecho, _idx_terminal, sem_no = _montar_candidatos(linhas, pontos, esquema)
    pares = _pares_proximos(cur, candidatos, tolerancia_m)
    uf = _resolver_uniao(candidatos, pares, esquema)

    grupos: dict = defaultdict(list)
    for i in range(len(candidatos)):
        grupos[uf.achar(i)].append(i)

    nos_linhas = []
    id_do_no: dict = {}
    for raiz, membros in grupos.items():
        rep_terminal = next((candidatos[m] for m in membros if candidatos[m]["kind"] == "terminal"), None)
        rep = rep_terminal or candidatos[membros[0]]
        no_id = str(uuid.uuid4())
        id_do_no[raiz] = no_id
        if rep_terminal:
            nos_linhas.append((no_id, tenant_id, rede_id, "terminal", rep["tipo_id"], rep["feicao_id"],
                                rep["terminal_num"], rep["x"], rep["y"]))
        else:
            nos_linhas.append((no_id, tenant_id, rede_id, "conexao", None, None, None, rep["x"], rep["y"]))

    cur.execute("DELETE FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid", (rede_id,))
    cur.execute("DELETE FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rede_id,))
    # a reconstrução total resolve TODA área suja pendente da rede — por isso elas morrem aqui, junto do
    # índice velho (a manutenção incremental, reconstruir só a área, é fronteira honesta desta passagem).
    cur.execute("DELETE FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid", (rede_id,))

    _inserir_lote(
        cur,
        "INSERT INTO plat.rede_topo_no(id, tenant_id, rede_id, papel, tipo_id, origem_id, terminal_num, geom) "
        "VALUES ",
        nos_linhas,
        "(%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s), 4326))",
    )

    grau: dict = defaultdict(int)
    arestas_linhas = []
    arestas_sem_no = 0
    for linha in linhas:
        if linha["id"] in sem_no:
            no_origem = no_destino = None
            arestas_sem_no += 1
        else:
            no_origem = id_do_no[uf.achar(idx_trecho[(linha["id"], "origem")])]
            no_destino = id_do_no[uf.achar(idx_trecho[(linha["id"], "destino")])]
            grau[no_origem] += 1
            grau[no_destino] += 1
        atributos = linha["atributos"]
        if not isinstance(atributos, str):
            atributos = json.dumps(atributos, ensure_ascii=False)
        arestas_linhas.append((
            str(uuid.uuid4()), tenant_id, rede_id, linha["grupo_id"], linha["tipo_id"],
            linha["id"], no_origem, no_destino, float(linha["comprimento_m"]), linha["fase_bitmask"],
            atributos, linha["geom_wkt"],
        ))

    _inserir_lote(
        cur,
        "INSERT INTO plat.rede_topo_aresta(id, tenant_id, rede_id, grupo_id, tipo_id, origem_id, "
        "no_origem_id, no_destino_id, comprimento_m, fase_bitmask, atributos, geom) VALUES ",
        arestas_linhas,
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, ST_SetSRID(ST_GeomFromText(%s), 4326))",
    )

    nos_orfaos = sum(1 for (_no_id, *_r) in nos_linhas if grau[_no_id] == 0)
    duracao_ms = int((time.perf_counter() - inicio) * 1000)
    resumo = {
        "rede_id": rede_id, "tolerancia_m": tolerancia_m, "nos": len(nos_linhas), "arestas": len(arestas_linhas),
        "nos_orfaos": nos_orfaos, "arestas_sem_no": arestas_sem_no, "duracao_ms": duracao_ms,
    }
    cur.execute(
        "INSERT INTO plat.rede_topo_resumo(tenant_id, rede_id, tolerancia_m, nos, arestas, nos_orfaos, "
        "arestas_sem_no, duracao_ms, construido_por) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (rede_id) DO UPDATE SET tolerancia_m = EXCLUDED.tolerancia_m, nos = EXCLUDED.nos, "
        "arestas = EXCLUDED.arestas, nos_orfaos = EXCLUDED.nos_orfaos, "
        "arestas_sem_no = EXCLUDED.arestas_sem_no, duracao_ms = EXCLUDED.duracao_ms, "
        "construido_em = now(), construido_por = EXCLUDED.construido_por "
        "RETURNING construido_em",
        (tenant_id, rede_id, tolerancia_m, resumo["nos"], resumo["arestas"], nos_orfaos, arestas_sem_no,
         duracao_ms, usuario_id),
    )
    resumo["construido_em"] = cur.fetchone()["construido_em"]
    return resumo
