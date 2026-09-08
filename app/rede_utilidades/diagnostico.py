"""Diagnóstico dos nós órfãos da topologia, por CLASSE (item L4-01-f-alcance-do-tracado-rede-real).

Nó órfão é nó de topologia sem nenhuma aresta (`topologia.habilitar` conta esses no resumo). Contar não
explica: dois órfãos com a mesma contagem podem ter causas opostas, e a que resolve um piora o outro. Este
módulo separa os órfãos em classes com nome, contagem, exemplo e distância medida, para que o conserto seja
escolhido pela causa:

  * `sem_camada_compativel` — nenhum trecho de tipo compatível existe na rede. É o terminal do outro lado do
    dispositivo quando a camada daquele tier não foi carregada (o secundário do transformador sem a camada de
    baixa tensão). Não é defeito de topologia: é recorte de carga, e some quando a camada entra.
  * `derivacao_sem_no` — há trecho compatível a menos da tolerância do par, mas encostando no MEIO do
    trecho, não numa ponta. A ligação exige QUEBRAR a aresta no ponto de derivação; a topologia desta
    passagem só conecta em vértice declarado (ponta de linha ou ponto de dispositivo), então esse órfão fica.
  * `fora_da_tolerancia_declarada` — a ponta compatível mais próxima está além da tolerância daquele par de
    tipos, mas dentro do limiar de busca do diagnóstico. É a classe que a tolerância por par de tipos
    resolve, e a distância medida diz de quanto ela precisaria ser — nunca se sobe a tolerância no escuro.
  * `sem_vizinho_no_limiar` — nada compatível dentro do limiar de busca. Cadastro do ponto longe da rede.
  * `terminal_sem_par_no_dispositivo` — a coincidência existe (há ponta compatível dentro da tolerância do
    par), mas outro terminal do MESMO dispositivo ficou com ela. É o segundo lado de um dispositivo de dois
    terminais quando a camada do outro tier não está carregada: o primário do transformador achou o trecho de
    média tensão e o secundário ficou sem trecho de baixa tensão para achar. Também é recorte de carga.
  * `no_de_conexao_sem_aresta` — nó que não é terminal de dispositivo e mesmo assim não tem aresta. Só
    aparece com trecho degenerado (origem igual ao destino); a contagem dessas arestas vem do resumo.

Nada aqui altera a topologia: é leitura. O conserto que este item entrega é a tolerância declarada por par
de tipos (`plat.rede_regra.tolerancia_m`, usada por `topologia._resolver_uniao`)."""

from app.erros import ErroAPI

LIMIAR_PADRAO_M = 1.0   # até onde o diagnóstico procura vizinho compatível antes de dizer "não há"
LIMIAR_MAX_M = 50.0
_M_POR_GRAU = 110_540.0


def _tolerancia_da_rede(cur, rede_id: str) -> float:
    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    return float(r["tolerancia_m"])


def _exigir_topologia(cur, rede_id: str) -> dict:
    cur.execute(
        "SELECT tolerancia_m, nos, arestas, nos_orfaos, arestas_sem_no, construido_em "
        "FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(409, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")
    return dict(r)


def _pares_compativeis(cur, rede_id: str, tolerancia_rede: float) -> None:
    """`diag_compat(tipo_no, tipo_linha, tol)`: para cada tipo que pode ser nó de dispositivo, os tipos de
    trecho com que ele pode se ligar por regra de conectividade, e a tolerância daquele par (a declarada na
    regra ou, na falta, a da rede). As duas direções da regra entram: a regra é um par, não uma seta."""
    cur.execute("DROP TABLE IF EXISTS diag_compat")
    cur.execute("CREATE TEMP TABLE diag_compat (tipo_no uuid NOT NULL, tipo_linha uuid NOT NULL, "
                "tol double precision NOT NULL, PRIMARY KEY (tipo_no, tipo_linha))")
    cur.execute(
        "INSERT INTO diag_compat (tipo_no, tipo_linha, tol) "
        "SELECT tipo_no, tipo_linha, max(tol) FROM ("
        "  SELECT de_tipo_id AS tipo_no, para_tipo_id AS tipo_linha, coalesce(tolerancia_m, %s) AS tol "
        "  FROM plat.rede_regra WHERE rede_id = %s::uuid "
        "    AND tipo IN ('conectividade_no_trecho','conectividade_entre_nos') "
        "  UNION ALL "
        "  SELECT para_tipo_id, de_tipo_id, coalesce(tolerancia_m, %s) "
        "  FROM plat.rede_regra WHERE rede_id = %s::uuid "
        "    AND tipo IN ('conectividade_no_trecho','conectividade_entre_nos')"
        ") p GROUP BY 1, 2",
        (tolerancia_rede, rede_id, tolerancia_rede, rede_id),
    )


def _orfaos(cur, rede_id: str) -> None:
    """`diag_orfao(no_id, papel, tipo_id, origem_id, geom)`: nós sem nenhuma aresta."""
    cur.execute("DROP TABLE IF EXISTS diag_orfao")
    cur.execute(
        "CREATE TEMP TABLE diag_orfao AS "
        "SELECT n.id AS no_id, n.papel, n.tipo_id, n.origem_id, n.geom FROM plat.rede_topo_no n "
        "WHERE n.rede_id = %s::uuid AND NOT EXISTS ("
        "  SELECT 1 FROM plat.rede_topo_aresta a WHERE a.rede_id = n.rede_id "
        "    AND (a.no_origem_id = n.id OR a.no_destino_id = n.id))",
        (rede_id,),
    )
    cur.execute("CREATE INDEX ON diag_orfao USING gist (geom)")
    cur.execute("ANALYZE diag_orfao")


def diagnosticar(cur, rede_id: str, limiar_m: float = LIMIAR_PADRAO_M, exemplos: int = 1) -> dict:
    """Classes de nó órfão da rede, com contagem, distância medida e exemplo. Só leitura."""
    if not (0 < limiar_m <= LIMIAR_MAX_M):
        raise ErroAPI(400, "limiar_invalido", f"o limiar de busca vai de 0 a {LIMIAR_MAX_M} m")
    tolerancia_rede = _tolerancia_da_rede(cur, rede_id)
    resumo = _exigir_topologia(cur, rede_id)
    _pares_compativeis(cur, rede_id, tolerancia_rede)
    _orfaos(cur, rede_id)

    graus = limiar_m / _M_POR_GRAU * 2.0   # folga: a conversão exata é a geodésica do WHERE de baixo
    # o "tem camada compatível?" é resolvido UMA vez por tipo, não por órfão: como subconsulta correlacionada
    # ele varria a camada de linha inteira uma vez por nó órfão (milhares de varreduras de dezenas de milhares
    # de linhas), e o diagnóstico não terminava na escala real.
    cur.execute("DROP TABLE IF EXISTS diag_tem_linha")
    cur.execute(
        "CREATE TEMP TABLE diag_tem_linha AS "
        "SELECT DISTINCT c.tipo_no FROM diag_compat c "
        "WHERE EXISTS (SELECT 1 FROM plat.rede_feicao_linha f "
        "              WHERE f.rede_id = %s::uuid AND f.tipo_id = c.tipo_linha)",
        (rede_id,),
    )
    cur.execute("CREATE INDEX ON diag_tem_linha (tipo_no)")
    cur.execute("ANALYZE diag_tem_linha")
    cur.execute(
        "SELECT o.no_id, o.papel, o.tipo_id, o.origem_id, "
        "       EXISTS (SELECT 1 FROM diag_tem_linha t WHERE t.tipo_no = o.tipo_id) AS tem_camada, "
        "       v.d_ponta, v.d_linha, v.tol "
        "FROM diag_orfao o LEFT JOIN LATERAL ("
        "  SELECT min(least(ST_Distance(ST_StartPoint(f.geom)::geography, o.geom::geography), "
        "                   ST_Distance(ST_EndPoint(f.geom)::geography, o.geom::geography))) AS d_ponta, "
        "         min(ST_Distance(f.geom::geography, o.geom::geography)) AS d_linha, "
        "         max(c.tol) AS tol "
        "  FROM plat.rede_feicao_linha f JOIN diag_compat c ON c.tipo_linha = f.tipo_id "
        "  WHERE f.rede_id = %(r)s::uuid AND c.tipo_no = o.tipo_id "
        "    AND ST_DWithin(f.geom, o.geom, %(g)s) "
        "    AND ST_DWithin(f.geom::geography, o.geom::geography, %(m)s)"
        ") v ON true",
        {"r": rede_id, "g": graus, "m": limiar_m},
    )
    linhas = cur.fetchall()

    classes: dict[str, dict] = {}

    def somar(nome: str, r: dict, distancia: float | None, tol: float | None) -> None:
        c = classes.setdefault(nome, {"classe": nome, "contagem": 0, "exemplos": [],
                                      "distancia_min_m": None, "distancia_max_m": None})
        c["contagem"] += 1
        if distancia is not None:
            d = round(float(distancia), 4)
            c["distancia_min_m"] = d if c["distancia_min_m"] is None else min(c["distancia_min_m"], d)
            c["distancia_max_m"] = d if c["distancia_max_m"] is None else max(c["distancia_max_m"], d)
        if len(c["exemplos"]) < exemplos:
            c["exemplos"].append({
                "no_id": str(r["no_id"]), "papel": r["papel"],
                "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
                "feicao_id": str(r["origem_id"]) if r["origem_id"] else None,
                "distancia_m": round(float(distancia), 4) if distancia is not None else None,
                "tolerancia_do_par_m": round(float(tol), 4) if tol is not None else None,
            })

    for r in linhas:
        if r["papel"] != "terminal":
            somar("no_de_conexao_sem_aresta", r, None, None)
            continue
        if not r["tem_camada"]:
            somar("sem_camada_compativel", r, None, None)
            continue
        d_ponta, d_linha, tol = r["d_ponta"], r["d_linha"], r["tol"]
        if d_ponta is None:
            somar("sem_vizinho_no_limiar", r, None, None)
        elif tol is not None and d_ponta <= tol:
            somar("terminal_sem_par_no_dispositivo", r, d_ponta, tol)
        elif d_linha is not None and tol is not None and d_linha <= tol < d_ponta:
            somar("derivacao_sem_no", r, d_linha, tol)
        else:
            somar("fora_da_tolerancia_declarada", r, d_ponta, tol)

    cur.execute("DROP TABLE diag_orfao")
    cur.execute("DROP TABLE diag_compat")
    cur.execute("DROP TABLE diag_tem_linha")
    ordenadas = sorted(classes.values(), key=lambda c: (-c["contagem"], c["classe"]))
    return {
        "rede_id": rede_id,
        "tolerancia_da_rede_m": tolerancia_rede,
        "limiar_m": limiar_m,
        "nos": resumo["nos"], "arestas": resumo["arestas"],
        "nos_orfaos": len(linhas),
        "nos_orfaos_no_resumo": resumo["nos_orfaos"],
        "arestas_sem_no": resumo["arestas_sem_no"],
        "classes": ordenadas,
    }
