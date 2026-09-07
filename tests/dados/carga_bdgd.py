"""Carga da rede REAL da cooperativa de teste (BDGD, schema `certaja` do iagro_sat — ativo da casa, somente
leitura) nas camadas de rede da plataforma, para a medição do item L4-01-b-topologia-derivada.

⛔ Não é gerador sintético (esse é `gerar_rede.py`, dos testes rápidos): aqui cada linha vem das tabelas
`certaja.ssdmt` (44.268 trechos de MT), `certaja.ssdbt` (29.244 de BT), `certaja.ramlig` (26.581 ramais),
`certaja.trafo` (5.481 transformadores) e `certaja.ponnot` (60.549 postes) — a mesma contagem que o portão
do item declara — e toda conferência de "número esperado" é computada DESTAS tabelas, por um caminho
INDEPENDENTE do construtor de topologia (contador em Python puro sobre o wkt cru, nunca reconsultando
`plat.rede_topo_*`).

Mapa de carga (vocabulário do pacote `eletrica-br`, item L4-01-a):
  ssdmt  → grupo trecho_de_media_tensao/1  (atributos: cod_id, ctmt, uni_tr_at, sub, conj, fas_con, comp, pos)
  ssdbt  → grupo trecho_de_baixa_tensao/1  (atributos: cod_id, ctmt, uni_tr_mt, fas_con, comp, tip_cnd)
  ramlig → grupo ramal_de_ligacao/1        (atributos: cod_id, ctmt, uni_tr_mt, fas_con, comp, tip_cnd)
  trafo  → grupo transformador_de_distribuicao/1 (atributos: cod_id, pot_nom, tip_trafo, ctmt, uni_tr_at)
  ponnot → grupo ponto_notavel/1           (poste — `sem_terminal`: tem de dar ZERO nó de topologia)
`fas_con` ('A','AB','CA'...) vira o bitmask de fase A=1, B=2, C=4. O wkt é MULTILINESTRING de parte única
(medido: 0 linhas com ST_NumGeometries > 1 em ssdmt) — `ST_GeometryN(...,1)` devolve a LineString.

⛔ FRONTEIRA MEDIDA (não é defeito de carga): `certaja.ramlig` tem os 26.581 registros do arquivo, mas
**0 de 26.581 têm `wkt` preenchido** (conferido por `count(wkt)` direto na tabela). O ramal de ligação
existe como atributo no ativo da casa, sem geometria armazenada nesta extração BDGD — carregar exigiria
fabricar uma linha que o arquivo não tem, o que a metodologia da casa proíbe. `carga_linha` filtra
`WHERE wkt IS NOT NULL`: para ssdmt/ssdbt isso não descarta nada (100% têm wkt); para ramlig o resultado
é 0 arestas carregadas, e é isso mesmo. A topologia geométrica medida cobre MT+BT+transformador+poste
(139.542 elementos reais); ramal de ligação fica de fora, contado e declarado, nunca inventado.
"""

import math
import time
from collections import defaultdict

TOLERANCIA_PADRAO_M = 0.05
_M_POR_GRAU_LAT = 110_540.0


def _tipos_da_rede(cur, rede_id: str) -> dict:
    cur.execute(
        "SELECT g.codigo AS grupo, tp.codigo AS tipo_codigo, tp.id FROM plat.rede_tipo tp "
        "JOIN plat.rede_grupo g ON g.id = tp.grupo_id WHERE tp.rede_id = %s::uuid",
        (rede_id,),
    )
    return {(r["grupo"], r["tipo_codigo"]): r["id"] for r in cur.fetchall()}


# '%' duplicado (`%%`) porque esta string entra numa consulta executada com parâmetros: o scanner de
# placeholder do psycopg2 trata todo '%' solto como início de um novo `%s` e estoura o índice da tupla
# de parâmetros (`IndexError: tuple index out of range`) se não for escapado — achado ao rodar a carga
# real da BDGD para medir o item L4-01-b-topologia-derivada.
_SQL_FASE = (
    "(CASE WHEN fas_con ILIKE '%%A%%' THEN 1 ELSE 0 END) + "
    "(CASE WHEN fas_con ILIKE '%%B%%' THEN 2 ELSE 0 END) + "
    "(CASE WHEN fas_con ILIKE '%%C%%' THEN 4 ELSE 0 END)"
)


def carregar(cur, tenant_id: int, rede_id: str, ctmts: list[str] | None = None,
             com_postes: bool = True) -> dict:
    """Insere a rede da cooperativa nas camadas `plat.rede_feicao_*` da rede `rede_id` (que já tem de estar
    com o pacote eletrica-br importado). Um INSERT...SELECT por tabela de origem; devolve a contagem e o
    tempo de cada uma. A conexão já vem com o contexto do inquilino (RLS vale para esta carga também).

    `ctmts` (item L4-04-b) restringe a carga a uma lista de alimentadores DO ARQUIVO — nada é fabricado, é o
    mesmo dado com um recorte declarado. Serve para medir em janela de tempo menor que a da rede inteira, e
    quem usa tem de dizer no relatório quantos dos 20 alimentadores entraram. `com_postes=False` deixa de
    fora `certaja.ponnot` (60.549 postes que, por serem `sem_terminal`, dão zero nó de topologia — medido no
    item L4-01-b)."""
    tipos = _tipos_da_rede(cur, rede_id)
    cron = {}
    recorte_linha = "" if ctmts is None else " AND ctmt = ANY(%(ctmts)s)"
    recorte_ponto = "" if ctmts is None else " WHERE ctmt = ANY(%(ctmts)s)"

    def rodar(rotulo, sql, params):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        n = cur.fetchone()["n"]
        cron[rotulo] = {"linhas": n, "segundos": round(time.perf_counter() - t0, 3)}
        return n

    def carga_linha(rotulo, origem, atributos_json, tipo_id):
        # só as linhas com wkt preenchido: `certaja.ramlig` (ativo da casa, ver docstring do módulo)
        # tem 0 de 26.581 registros com geometria — carregar exige geom NOT NULL (segurança de linha
        # da tabela derivada), e fabricar geometria que o arquivo não tem seria inventar dado.
        rodar(rotulo, f"""
            WITH carga AS (
              INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos)
              SELECT %(a)s, %(b)s::uuid, %(c)s::uuid,
                     ST_GeometryN(ST_GeomFromText(wkt, 4326), 1),
                     {_SQL_FASE},
                     {atributos_json}
              FROM {origem}
              WHERE wkt IS NOT NULL{recorte_linha}
              RETURNING 1
            ) SELECT count(*) AS n FROM carga
        """, {"a": tenant_id, "b": rede_id, "c": tipo_id, "ctmts": ctmts})

    carga_linha(
        "ssdmt", "certaja.ssdmt",
        "jsonb_build_object('cod_id', cod_id, 'ctmt', ctmt, 'uni_tr_at', uni_tr_at, 'sub', sub, "
        "'conj', conj, 'fas_con', fas_con, 'comp', comp, 'pos', pos)",
        tipos[("trecho_de_media_tensao", 1)])
    carga_linha(
        "ssdbt", "certaja.ssdbt",
        "jsonb_build_object('cod_id', cod_id, 'ctmt', ctmt, 'uni_tr_mt', uni_tr_mt, 'fas_con', fas_con, "
        "'comp', comp, 'tip_cnd', tip_cnd)",
        tipos[("trecho_de_baixa_tensao", 1)])
    carga_linha(
        "ramlig", "certaja.ramlig",
        "jsonb_build_object('cod_id', cod_id, 'ctmt', ctmt, 'uni_tr_mt', uni_tr_mt, 'fas_con', fas_con, "
        "'comp', comp, 'tip_cnd', tip_cnd)",
        tipos[("ramal_de_ligacao", 1)])

    rodar("trafo", """
        WITH carga AS (
          INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
          SELECT %(a)s, %(b)s::uuid, %(c)s::uuid, ST_SetSRID(ST_MakePoint(x, y), 4326),
                 jsonb_build_object('cod_id', cod_id, 'pot_nom', pot_nom, 'tip_trafo', tip_trafo,
                                    'ctmt', ctmt, 'uni_tr_at', uni_tr_at)
          FROM certaja.trafo""" + recorte_ponto + """
          RETURNING 1
        ) SELECT count(*) AS n FROM carga
    """, {"a": tenant_id, "b": rede_id, "c": tipos[("transformador_de_distribuicao", 1)], "ctmts": ctmts})

    if com_postes:
        rodar("ponnot", """
            WITH carga AS (
              INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, atributos)
              SELECT %s, %s::uuid, %s::uuid, ST_SetSRID(ST_MakePoint(x, y), 4326),
                     jsonb_build_object('cod_id', cod_id, 'tip_pn', tip_pn, 'pos', pos)
              FROM certaja.ponnot
              RETURNING 1
            ) SELECT count(*) AS n FROM carga
        """, (tenant_id, rede_id, tipos[("ponto_notavel", 1)]))

    return cron


# --- conferências independentes (o "arquivo" do portão: SSDMT × CTMT × UNTRMT) ------------------------------

def _parse_pontas(wkt: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Pontas de um 'MULTILINESTRING ((x y, x y, ...))' de parte única, sem biblioteca: texto cru."""
    corpo = wkt[wkt.index("((") + 2:wkt.rindex("))")]
    pares = corpo.split(",")
    def xy(par):
        a, b = par.strip().split()
        return float(a), float(b)
    return xy(pares[0]), xy(pares[-1])


class _Agrupador:
    """Agrupamento por coincidência com tolerância em metros, por grade de células + union-find — caminho
    INDEPENDENTE do construtor da plataforma (que usa ST_DWithin + union-find sobre candidatos). Converte
    grau→metro por equiretangular local; a 0,05 m de limiar o erro contra a geodésica é < 1 mm."""

    def __init__(self, tolerancia_m: float, lat_media: float):
        self.tol = tolerancia_m
        self.cos_lat = math.cos(math.radians(lat_media))
        self.pai: dict[int, int] = {}
        self.pontos: list[tuple[float, float]] = []
        self.grau: dict[int, int] = defaultdict(int)
        self.arestas: list[tuple[int, int]] = []

    def achar(self, x: int) -> int:
        self.pai.setdefault(x, x)
        raiz = x
        while self.pai[raiz] != raiz:
            raiz = self.pai[raiz]
        while self.pai[x] != raiz:
            self.pai[x], x = raiz, self.pai[x]
        return raiz

    def _para_m(self, lon: float, lat: float) -> tuple[float, float]:
        return lon * _M_POR_GRAU_LAT * self.cos_lat, lat * _M_POR_GRAU_LAT

    def montar(self, pontas: list[tuple[tuple[float, float], tuple[float, float]]]) -> None:
        """`pontas` = [(p0, p1), ...] de cada trecho. Ao final: nós = grupos de pontas coincidentes,
        grau = nº de pontas no grupo, arestas = trechos entre grupos."""
        celula = self.tol
        grade: dict[tuple[int, int], list[int]] = defaultdict(list)
        idx_ponta: list[int] = []

        def registrar(lon: float, lat: float) -> int:
            x, y = self._para_m(lon, lat)
            cx, cy = int(math.floor(x / celula)), int(math.floor(y / celula))
            novo = len(self.pontos)
            self.pontos.append((lon, lat))
            self.pai[novo] = novo
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grade.get((cx + dx, cy + dy), []):
                        xj, yj = self._para_m(*self.pontos[j])
                        if (x - xj) ** 2 + (y - yj) ** 2 <= self.tol ** 2:
                            ra, rb = self.achar(novo), self.achar(j)
                            if ra != rb:
                                self.pai[rb] = ra
            grade[(cx, cy)].append(novo)
            return novo

        for p0, p1 in pontas:
            i0, i1 = registrar(*p0), registrar(*p1)
            idx_ponta.append((i0, i1))
        for i0, i1 in idx_ponta:
            r0, r1 = self.achar(i0), self.achar(i1)
            self.grau[r0] += 1
            self.grau[r1] += 1
            self.arestas.append((r0, r1))


def esperado_mt(cur, tolerancia_m: float = TOLERANCIA_PADRAO_M) -> dict:
    """O que o ARQUIVO diz para a média tensão (caminho independente, em cima do wkt cru de certaja.ssdmt):
    nº de nós (pontas coincidentes dentro da tolerância), nº de nós de grau 1 (fins de linha) e nº de
    componentes conexas POR ALIMENTADOR (coluna ctmt — a junção SSDMT × CTMT do portão)."""
    cur.execute("SELECT ctmt, wkt FROM certaja.ssdmt")
    linhas = cur.fetchall()
    lat_media = sum(_parse_pontas(linha["wkt"])[0][1] for linha in linhas[:500]) / min(len(linhas), 500)

    por_ctmt: dict[str, list] = defaultdict(list)
    for linha in linhas:
        por_ctmt[linha["ctmt"]].append(_parse_pontas(linha["wkt"]))

    todos = _Agrupador(tolerancia_m, lat_media)
    todos.montar([p for pontas in por_ctmt.values() for p in pontas])
    raizes = {todos.achar(i) for i in todos.pai}
    fins = sum(1 for r in raizes if todos.grau[r] == 1)

    componentes_por_ctmt = {}
    for ctmt, pontas in por_ctmt.items():
        ag = _Agrupador(tolerancia_m, lat_media)
        ag.montar(pontas)
        # componentes = nº de sub-grafos desconexos DENTRO do alimentador: union-find sobre as arestas
        # `pai` como argumento padrão (não fechado por referência de nome): evita o B023 de closure em
        # laço — `pai` é sempre o dict desta iteração porque é vinculado na DEFINIÇÃO da função, não lido
        # de fora dela em cada chamada.
        pai: dict[int, int] = {}

        def achar(x, pai=pai):
            pai.setdefault(x, x)
            while pai[x] != x:
                pai[x] = pai[pai[x]]
                x = pai[x]
            return x

        for r0, r1 in ag.arestas:
            a, b = achar(r0), achar(r1)
            if a != b:
                pai[b] = a
        nos_do_alimentador = {ag.achar(i) for i in ag.pai}
        componentes_por_ctmt[ctmt] = len({achar(n) for n in nos_do_alimentador})

    return {
        "trechos": len(linhas),
        "nos": len(raizes),
        "fins_de_linha_grau1": fins,
        "alimentadores": len(por_ctmt),
        "componentes_por_ctmt": componentes_por_ctmt,
    }


def esperado_orfaos_alta(cur, tolerancia_m: float = TOLERANCIA_PADRAO_M) -> int:
    """Quantos transformadores do ARQUIVO NÃO têm nenhuma ponta de trecho de MT dentro da tolerância — o
    número esperado de terminais de alta órfãos (a junção SSDMT × UNTRMT do portão: `certaja.trafo` cruza
    com as pontas de `certaja.ssdmt`)."""
    cur.execute("DROP TABLE IF EXISTS topo_pontas_mt")
    cur.execute("""
        CREATE TEMP TABLE topo_pontas_mt AS
        SELECT ST_StartPoint(g) AS p FROM (SELECT ST_GeometryN(ST_GeomFromText(wkt, 4326), 1) AS g
                                         FROM certaja.ssdmt) s
        UNION ALL
        SELECT ST_EndPoint(g) FROM (SELECT ST_GeometryN(ST_GeomFromText(wkt, 4326), 1) AS g
                                    FROM certaja.ssdmt) s
    """)
    cur.execute("CREATE INDEX ON topo_pontas_mt USING gist (p)")
    cur.execute("ANALYZE topo_pontas_mt")
    cur.execute(
        "SELECT count(*) AS n FROM certaja.trafo t WHERE NOT EXISTS ("
        "  SELECT 1 FROM topo_pontas_mt p "
        "  WHERE ST_DWithin(p.p, ST_SetSRID(ST_MakePoint(t.x, t.y), 4326), %s / 111320.0 * 2)"
        "   AND ST_DWithin(p.p::geography, ST_SetSRID(ST_MakePoint(t.x, t.y), 4326)::geography, %s))",
        (tolerancia_m, tolerancia_m),
    )
    n = cur.fetchone()["n"]
    cur.execute("DROP TABLE topo_pontas_mt")
    return n


def contagens_arquivo(cur) -> dict:
    """As contagens do arquivo que o portão declara — medidas, nunca copiadas do enunciado."""
    saida = {}
    for tabela in ("ssdmt", "ssdbt", "ramlig", "trafo", "ponnot", "ctmt"):
        cur.execute(f"SELECT count(*) AS n FROM certaja.{tabela}")
        saida[tabela] = cur.fetchone()["n"]
    return saida
