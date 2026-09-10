"""Consumidores como ativo terminal da rede e cruzamento com endereços do censo (item
L4-20-consumidores-e-enderecos). Três funções de domínio:

- ``gerar_enderecos_sem_rede``: endereço do censo com rede de média tensão a até ``raio_rede_m``
  e SEM rede de baixa tensão a até ``raio_bt_m`` vira linha da camada
  ``plat.rede_endereco_sem_rede``. Distância curta (<= raio de baixa tensão) significa rede no
  portão (candidato a ligação); acima disso, rede de média por perto e nenhum registro de
  consumidor adiante (cadastro faltante). Critério geométrico declarado, não confirmado em campo.
- ``calcular_jusante``: grafo por circuito (ctmt) a partir dos trechos; árvore de largura a partir
  da raiz (nó de maior grau do circuito, desempate por coordenada); ``clientes_jusante`` do trecho
  = soma das unidades consumidoras nos transformadores estritamente a jusante (incluído o nó que
  o trecho alcança). Trecho que fecha ciclo (malha) fica fora da árvore, com NULL, e é reportado.
- ``ficha_uc``: whitelist de campos da unidade consumidora; consumo só em agregado do
  transformador com pelo menos ``REDE_AGREGACAO_MIN_UCS`` unidades. Nada identificável sai daqui.

Regra de privacidade: nunca nome, nunca CPF/CNPJ de pessoa, nunca telefone; consumo por unidade
nunca cruza a API (vive só na tabela que alimenta o agregado)."""

import logging
import math
from collections import defaultdict, deque

from app import limites

log = logging.getLogger("plat.rede.consumidores")

SITUACOES = ("candidato_ligacao", "cadastro_faltante")

SQL_CONTAR_ENDERECOS = (
    "SELECT count(*) AS n FROM plat.rede_endereco WHERE tenant_id = plat.tenant_atual()"
)

SQL_GERAR = """
INSERT INTO plat.rede_endereco_sem_rede
       (tenant_id, endereco_id, geometria, dist_rede_m, situacao)
SELECT plat.tenant_atual(), e.endereco_id, e.geometria, knn.dist_mt,
       CASE WHEN knn.dist_mt <= %(raio_bt)s THEN 'candidato_ligacao' ELSE 'cadastro_faltante' END
  FROM plat.rede_endereco e
  JOIN LATERAL (
       -- trecho de média tensão mais próximo SEM filtro de distância: o KNN do índice acha em
       -- uma descida só; o raio entra fora, como filtro. Um ST_DWithin dentro do KNN, ou um
       -- EXISTS comum, deixa o planejador escolher o índice btree (tenant, nivel) e varrer
       -- milhares de linhas por endereço; o ORDER BY <-> só pode ser servido pelo índice
       -- espacial, então o plano fica bom independentemente de estatística. LATERAL em vez de
       -- CTE porque comando de modificação materializa CTE sempre: 182 mil endereços
       -- derramariam em arquivo temporário antes do primeiro INSERT.
       SELECT ST_Distance(m.geometria_calc, e.geometria_calc) AS dist_mt
         FROM plat.rede_trecho m
        WHERE m.tenant_id = plat.tenant_atual()
          AND m.nivel = 'mt'
        ORDER BY m.geometria_calc <-> e.geometria_calc
        LIMIT 1
  ) knn ON true
  LEFT JOIN LATERAL (
       -- baixa tensão mais próxima: se a mais próxima passa do raio, nenhuma outra passa
       -- (equivale ao "não existe baixa tensão a menos de raio_bt") e o endereço entra.
       SELECT ST_Distance(b.geometria_calc, e.geometria_calc) AS dist_bt
         FROM plat.rede_trecho b
        WHERE b.tenant_id = plat.tenant_atual()
          AND b.nivel = 'bt'
        ORDER BY b.geometria_calc <-> e.geometria_calc
        LIMIT 1
  ) bt ON true
 WHERE knn.dist_mt IS NOT NULL
   AND knn.dist_mt <= %(raio_rede)s
   AND (bt.dist_bt IS NULL OR bt.dist_bt > %(raio_bt)s)
RETURNING situacao
"""

SQL_APAGAR_CAMADA = "DELETE FROM plat.rede_endereco_sem_rede WHERE tenant_id = plat.tenant_atual()"

# tolerância declarada: transformador a até 10 m do nó (poste) do próprio circuito
TOLERANCIA_TRAFO_M = 10.0


def gerar_enderecos_sem_rede(cur, raio_rede_m: float, raio_bt_m: float) -> dict:
    """Gera (recria) a camada do inquilino e devolve as contagens por situação."""
    from app.erros import ErroAPI

    cur.execute(SQL_CONTAR_ENDERECOS)
    n_enderecos = cur.fetchone()["n"]
    if n_enderecos > limites.REDE_ENDERECOS_MAX:
        raise ErroAPI(
            422,
            "enderecos_demais",
            f"{n_enderecos} endereços carregados excede o teto de {limites.REDE_ENDERECOS_MAX}",
            {"enderecos": n_enderecos, "teto": limites.REDE_ENDERECOS_MAX},
        )
    cur.execute(SQL_APAGAR_CAMADA)
    cur.execute(SQL_GERAR, {"raio_rede": raio_rede_m, "raio_bt": raio_bt_m})
    linhas = cur.fetchall()
    contagem = {"candidato_ligacao": 0, "cadastro_faltante": 0}
    for r in linhas:
        contagem[r["situacao"]] += 1
    return {"enderecos": n_enderecos, "total": len(linhas), **contagem}


# ---------------------------------------------------------------- jusante


def _no_de_texto(wkt: str) -> tuple[float, float]:
    """'POINT(x y)' -> (x, y); falha alto em geometria quebrada."""
    corpo = wkt[wkt.index("(") + 1 : wkt.rindex(")")]
    x, y = corpo.split()
    return (float(x), float(y))


def _chave_no(x: float, y: float) -> tuple[int, int]:
    """Nó arredondado a milímetro: extremidades de trechos distintos que se tocam caem na mesma chave."""
    return (round(x, 3), round(y, 3))


def calcular_jusante(cur) -> dict:
    """Calcula ``clientes_jusante`` de todo trecho de mt do inquilino e grava na tabela.

    Teto de memória: ``REDE_JUSANTE_TRECHOS_MAX`` trechos e ``REDE_JUSANTE_NO_MAX`` nós.
    """
    from app.erros import ErroAPI

    cur.execute(
        "SELECT codigo, ctmt, ST_AsText(ST_PointN(geometria_calc, 1)) AS p1,"
        "       ST_AsText(ST_PointN(geometria_calc, ST_NumPoints(geometria_calc))) AS p2"
        "  FROM plat.rede_trecho"
        " WHERE tenant_id = plat.tenant_atual() AND nivel = 'mt'"
    )
    trechos = cur.fetchall()
    if len(trechos) > limites.REDE_JUSANTE_TRECHOS_MAX:
        raise ErroAPI(
            422,
            "trechos_demais",
            f"{len(trechos)} trechos de mt excede o teto de {limites.REDE_JUSANTE_TRECHOS_MAX}",
            {"trechos": len(trechos), "teto": limites.REDE_JUSANTE_TRECHOS_MAX},
        )
    cur.execute(
        "SELECT codigo, ctmt, ST_AsText(geometria_calc) AS ponto"
        "  FROM plat.rede_trafo WHERE tenant_id = plat.tenant_atual() AND geometria_calc IS NOT NULL"
    )
    trafos = cur.fetchall()
    cur.execute(
        "SELECT uni_tr_mt, count(*) AS n FROM plat.rede_uc"
        " WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt IS NOT NULL"
        " GROUP BY uni_tr_mt"
    )
    ucs_por_trafo: dict[str, int] = {r["uni_tr_mt"]: r["n"] for r in cur.fetchall()}

    # arestas e nós por circuito
    adj: dict[str, dict[tuple, list[tuple[str, tuple]]]] = defaultdict(lambda: defaultdict(list))
    grau: dict[str, dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
    nos_do_ctmt: dict[str, set[tuple]] = defaultdict(set)
    arestas_por_ctmt: dict[str, dict[str, tuple[tuple, tuple]]] = defaultdict(dict)
    for t in trechos:
        n1 = _chave_no(*_no_de_texto(t["p1"]))
        n2 = _chave_no(*_no_de_texto(t["p2"]))
        nos_do_ctmt[t["ctmt"]].update((n1, n2))
        arestas_por_ctmt[t["ctmt"]][t["codigo"]] = (n1, n2)
        if n1 != n2:
            adj[t["ctmt"]][n1].append((t["codigo"], n2))
            adj[t["ctmt"]][n2].append((t["codigo"], n1))
            grau[t["ctmt"]][n1] += 1
            grau[t["ctmt"]][n2] += 1
    total_nos = sum(len(v) for v in nos_do_ctmt.values())
    if total_nos > limites.REDE_JUSANTE_NO_MAX:
        raise ErroAPI(
            422,
            "nos_demais",
            f"{total_nos} nós de rede excede o teto de {limites.REDE_JUSANTE_NO_MAX}",
            {"nos": total_nos, "teto": limites.REDE_JUSANTE_NO_MAX},
        )

    # transformador -> nó mais próximo do próprio circuito (tolerância declarada acima)
    ucs_no: dict[tuple, int] = defaultdict(int)
    nos_ordenados = {c: sorted(n) for c, n in nos_do_ctmt.items()}
    for tf in trafos:
        nos = nos_ordenados.get(tf["ctmt"])
        if not nos:
            continue
        x, y = _no_de_texto(tf["ponto"])
        no = min(nos, key=lambda n: (n[0] - x) ** 2 + (n[1] - y) ** 2)
        if math.hypot(no[0] - x, no[1] - y) <= TOLERANCIA_TRAFO_M:
            ucs_no[no] += ucs_por_trafo.get(tf["codigo"], 0)

    jusante: dict[str, int | None] = {t["codigo"]: None for t in trechos}
    trechos_em_malha: set[str] = set()
    for ctmt, arestas in list(arestas_por_ctmt.items()):
        # trecho degenerado (extremidades iguais): malha sobre si mesmo, sai do grafo
        for codigo in [c for c, (a, b) in arestas.items() if a == b]:
            trechos_em_malha.add(codigo)
            del arestas[codigo]
        lista_adj = adj.get(ctmt)
        if not lista_adj:
            trechos_em_malha.update(arestas)
            continue
        # raiz: nó de maior grau (convergência do circuito); desempate por menor coordenada
        raiz = max(lista_adj, key=lambda n: (grau[ctmt][n], tuple(-v for v in n)))
        # árvore de largura: trecho que descobre um nó é aresta de árvore; os demais são malha.
        # `ordem` tem pais antes de filhos, então a varredura invertida acumula folhas primeiro.
        descoberto: set[tuple] = {raiz}
        pai: dict[tuple, tuple] = {}
        trecho_filho: dict[str, tuple] = {}
        ordem: list[tuple] = [raiz]
        fila = deque([raiz])
        while fila:
            no = fila.popleft()
            for codigo, outro in lista_adj[no]:
                if outro in descoberto:
                    if codigo not in trecho_filho:
                        trechos_em_malha.add(codigo)
                    continue
                descoberto.add(outro)
                pai[outro] = no
                trecho_filho[codigo] = outro
                ordem.append(outro)
                fila.append(outro)
        uc_subarvore: dict[tuple, int] = {no: ucs_no.get(no, 0) for no in ordem}
        for no in reversed(ordem[1:]):
            uc_subarvore[pai[no]] += uc_subarvore[no]
        for codigo, filho in trecho_filho.items():
            jusante[codigo] = uc_subarvore[filho]

    # grava de uma vez (UPDATE ... FROM VALUES)
    pares = [(codigo, valor) for codigo, valor in jusante.items()]
    for inicio in range(0, len(pares), 5_000):
        lote = pares[inicio : inicio + 5_000]
        valores = b",".join(
            cur.mogrify("(%s,%s)", (codigo, valor)) for codigo, valor in lote
        ).decode()
        cur.execute(
            "UPDATE plat.rede_trecho t SET clientes_jusante = v.j"
            f"  FROM (VALUES {valores}) AS v(codigo, j)"
            " WHERE t.tenant_id = plat.tenant_atual() AND t.nivel = 'mt' AND t.codigo = v.codigo"
        )
    return {
        "trechos": len(trechos),
        "trechos_calculados": sum(1 for v in jusante.values() if v is not None),
        "trechos_em_malha": len(trechos_em_malha),
        "ucs": sum(ucs_no.values()),  # só as unidades atribuídas a um nó da árvore
        "ctmts": len(arestas_por_ctmt),
    }


def ficha_uc(cur, uc_id: str) -> dict | None:
    """Ficha da unidade consumidora: whitelist de campos de rede, sem nada identificável."""
    cur.execute(
        "SELECT id::text AS id, codigo, ctmt, uni_tr_mt, situacao, grupo_tensao, criado_em"
        "  FROM plat.rede_uc WHERE id = %s",
        (uc_id,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    ficha = {c: r[c] for c in ("id", "codigo", "ctmt", "uni_tr_mt", "situacao", "grupo_tensao", "criado_em")}
    ficha["criado_em"] = ficha["criado_em"].isoformat()
    ficha["consumo"] = _consumo_agregado_trafo(cur, r["uni_tr_mt"])
    return ficha


def _consumo_agregado_trafo(cur, uni_tr_mt: str | None) -> dict | None:
    """Consumo do transformador em agregado: só com >= REDE_AGREGACAO_MIN_UCS unidades no ano."""
    if not uni_tr_mt:
        return None
    cur.execute("SELECT max(ano) AS ano FROM plat.rede_uc_consumo WHERE tenant_id = plat.tenant_atual()")
    ano = cur.fetchone()["ano"]
    if ano is None:
        return None
    cur.execute(
        "SELECT count(*) AS ucs, sum(c.ene_kwh) AS ene_kwh"
        "  FROM plat.rede_uc_consumo c JOIN plat.rede_uc u ON u.id = c.uc_id"
        " WHERE c.tenant_id = plat.tenant_atual() AND c.ano = %s AND u.uni_tr_mt = %s",
        (ano, uni_tr_mt),
    )
    r = cur.fetchone()
    if r is None or r["ucs"] is None or r["ucs"] < limites.REDE_AGREGACAO_MIN_UCS:
        return {
            "ucs": r["ucs"] or 0,
            "ene_kwh": None,
            "ano": ano,
            "motivo": f"agregação mínima de {limites.REDE_AGREGACAO_MIN_UCS} unidades não atingida",
        }
    return {"ucs": r["ucs"], "ene_kwh": round(r["ene_kwh"], 3), "ano": ano, "motivo": None}
