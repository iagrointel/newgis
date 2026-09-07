"""Atributos de rede (item L4-01-d-atributos-de-rede; migração 20260907T1239).

Hipótese do item: "atributo de rede" (network attribute, no vocabulário da Esri) é a coluna da topologia
derivada que o traçado lê SEM ir à camada de origem nem ao `atributos` jsonb cru: fase (bitmask A=1/B=2/C=4,
PROPAGÁVEL), tensão nominal, estado do dispositivo (aberto/fechado, com traversabilidade), capacidade,
comprimento geodésico, `is_connected` e `subrede`. `plat.rede_atributo` (item L4-01-a) já é o catálogo de
onde cada atributo vem por tipo de ativo; este módulo:

  1. marca, no catálogo já existente, quais atributos são PROPAGÁVEIS e quais APOIAM TRAVERSABILIDADE pelo
     sufixo real da coluna BDGD (`declarar_flags_padrao`, chamada uma vez ao fim da importação do pacote;
     `declarar_flags` é a via genérica por grupo+código), e semeia as linhas SINTÉTICAS dos três atributos
     que não vêm de nenhuma coluna da BDGD — são CALCULADOS pela plataforma (`declarar_calculados`);
  2. sincroniza, em LOTE, o valor normalizado (tensão/capacidade) das feições para a topologia e (re)constrói
     `plat.rede_topo_dispositivo_aresta` — a aresta INTERNA de cada dispositivo de dois terminais, sem a qual
     o traçado nunca atravessa uma chave (`sincronizar_topologia_lote`); a sincronização de UMA feição já
     editada é o TRIGGER da migração, não este módulo;
  3. propaga a fase do(s) nó(s) controlador(es) para jusante, aplicando regra de SUBSTITUIÇÃO onde declarada,
     e grava a discrepância contra a fase DECLARADA como candidata a erro de cadastro, nunca corrigida em
     silêncio (`propagar_fase`);
  4. recalcula `is_connected`/`subrede` por alcançabilidade a partir do(s) controlador(es), respeitando a
     traversabilidade do dispositivo (`recalcular_conectividade`).

⛔ FRONTEIRA DECLARADA (achada ao medir, não um defeito de código): o extrato BDGD carregado pelo item
L4-01-b (`tests/dados/carga_bdgd.py`) só tem `ssdmt`/`ssdbt`/`ramlig`/`trafo`/`ponnot` — NENHUMA subestação
(`subestacao_de_distribuicao`, categoria `fonte`) nem chave de média tensão (categoria `seccionamento`) do
pacote `eletrica-br` está no arquivo real da cooperativa de teste. Sem um nó de categoria `fonte` real, a
propagação de fase e o recálculo de conectividade não têm de onde partir pela via "oficial" (nó com
categoria `fonte`); a via de teste honesta, `raizes_assumidas_por_alimentador` (função deste módulo), usa a
extremidade de grau 1 de CADA alimentador (coluna `ctmt`, já a junção usada pelo item anterior) como RAIZ
ASSUMIDA — nunca chamada de "subestação" no código nem no relatório. Isso mede genuinamente a mecânica de
propagação (BFS + substituição + discrepância) sobre a topologia real; não mede "o traçado achou a
subestação certa", porque a subestação não está no arquivo.
"""

from collections import defaultdict, deque

GRUPOS_LINHA_COM_COMPRIMENTO = ("trecho_de_media_tensao", "trecho_de_baixa_tensao", "ramal_de_ligacao")
CODIGO_COMPRIMENTO = "comprimento_geodesico"
CODIGO_IS_CONNECTED = "is_connected"
CODIGO_SUBREDE = "subrede"


def _grupo_id(cur, rede_id: str, grupo_codigo: str) -> str | None:
    cur.execute("SELECT id FROM plat.rede_grupo WHERE rede_id = %s::uuid AND codigo = %s",
                (rede_id, grupo_codigo))
    r = cur.fetchone()
    return str(r["id"]) if r else None


def _tipo_ids_por_categoria(cur, rede_id: str, categoria_codigo: str) -> set[str]:
    cur.execute(
        "SELECT tc.tipo_id FROM plat.rede_tipo_categoria tc "
        "JOIN plat.rede_categoria c ON c.id = tc.categoria_id "
        "WHERE tc.rede_id = %s::uuid AND c.codigo = %s",
        (rede_id, categoria_codigo),
    )
    return {str(r["tipo_id"]) for r in cur.fetchall()}


# --- 1. catálogo: flags e linhas sintéticas de atributo calculado --------------------------------------------

def declarar_flags(cur, rede_id: str, grupo_codigo: str, atributo_codigo: str, *,
                    propagavel: bool | None = None, apoia_traversabilidade: bool | None = None) -> int:
    """Marca, nas linhas já existentes de `plat.rede_atributo` do grupo (todo tipo do grupo, `tipo_id` livre),
    se o atributo é propagável e/ou se apoia traversabilidade. Nunca cria linha (isso é `declarar_calculados`
    para o que é sintético, ou o import do pacote para o que vem da BDGD) — devolve 0 se o código não existir
    no grupo, para o chamador decidir o que fazer (nunca falha em silêncio)."""
    grupo_id = _grupo_id(cur, rede_id, grupo_codigo)
    if grupo_id is None:
        return 0
    sets, valores = [], []
    if propagavel is not None:
        sets.append("propagavel = %s")
        valores.append(propagavel)
    if apoia_traversabilidade is not None:
        sets.append("apoia_traversabilidade = %s")
        valores.append(apoia_traversabilidade)
    if not sets:
        return 0
    valores += [grupo_id, atributo_codigo]
    cur.execute(
        f"UPDATE plat.rede_atributo SET {', '.join(sets)} WHERE grupo_id = %s::uuid AND codigo = %s",
        valores,
    )
    return cur.rowcount


def declarar_flags_padrao(cur, rede_id: str) -> dict:
    """Marca as flags nos atributos REAIS do pacote `eletrica-br` (codigo com o prefixo da tabela BDGD de
    origem, ex. `ssdmt_fas_con`, `unsemt_p_n_ope` — nunca um código genérico `fase`, que não existe no
    catálogo importado): todo atributo cujo código termina em `_fas_con` é a fase declarada, PROPAGÁVEL
    (hoje o único propagável); todo atributo terminado em `_p_n_ope` é a posição normal de operação da
    chave, e APOIA TRAVERSABILIDADE (hoje o único). Chamada uma vez ao fim da importação do pacote
    (`deposito.importar`); idempotente."""
    cur.execute(
        "UPDATE plat.rede_atributo SET propagavel = true "
        "WHERE rede_id = %s::uuid AND codigo LIKE '%%\\_fas\\_con' ESCAPE '\\'",
        (rede_id,),
    )
    fase = cur.rowcount
    cur.execute(
        "UPDATE plat.rede_atributo SET apoia_traversabilidade = true "
        "WHERE rede_id = %s::uuid AND codigo LIKE '%%\\_p\\_n\\_ope' ESCAPE '\\'",
        (rede_id,),
    )
    traversabilidade = cur.rowcount
    return {"fase_propagavel": fase, "traversabilidade": traversabilidade}


def declarar_calculados(cur, tenant_id: int, rede_id: str) -> int:
    """Semeia as linhas SINTÉTICAS de `plat.rede_atributo` para os três atributos que a plataforma CALCULA
    (nenhuma coluna de origem na BDGD): comprimento geodésico (todo grupo com geometria de linha),
    `is_connected` e `subrede` (todo grupo, ponto e linha — um dispositivo desligado também fica
    desconectado). `origem` marca `{"calculado": true}` em vez de câmera/coluna, para nunca ser confundido
    com um campo importado. Idempotente (`ON CONFLICT DO NOTHING` na chave existente do catálogo)."""
    cur.execute("SELECT id, codigo, geometria FROM plat.rede_grupo WHERE rede_id = %s::uuid", (rede_id,))
    grupos = cur.fetchall()
    inseridas = 0
    for g in grupos:
        candidatos = [(CODIGO_IS_CONNECTED, "booleano", None, False, False),
                      (CODIGO_SUBREDE, "texto", None, False, False)]
        if g["geometria"] == "linha":
            candidatos.append((CODIGO_COMPRIMENTO, "real", "m", False, False))
        for codigo, tipo_dado, unidade, propagavel, apoia in candidatos:
            cur.execute(
                "INSERT INTO plat.rede_atributo(tenant_id, rede_id, grupo_id, tipo_id, codigo, nome, "
                "tipo_dado, unidade, obrigatorio, origem, propagavel, apoia_traversabilidade) "
                "VALUES (%s, %s::uuid, %s::uuid, NULL, %s, %s, %s, %s, false, %s::jsonb, %s, %s) "
                "ON CONFLICT (grupo_id, coalesce(tipo_id, '00000000-0000-0000-0000-000000000000'::uuid), "
                "codigo) DO NOTHING",
                (tenant_id, rede_id, g["id"], codigo, codigo.replace("_", " "), tipo_dado, unidade,
                 '{"calculado": true}', propagavel, apoia),
            )
            inseridas += cur.rowcount
    return inseridas


# --- 2. sincronização em lote: tensão/capacidade + aresta interna do dispositivo ------------------------------

def sincronizar_topologia_lote(cur, tenant_id: int, rede_id: str) -> dict:
    """Copia tensão/capacidade normalizadas das feições para a topologia derivada e (re)constrói
    `plat.rede_topo_dispositivo_aresta` do zero para a rede (mesma filosofia de `topologia.habilitar`:
    reconstrução total, nunca incremental) — exige a topologia já habilitada (item L4-01-b)."""
    cur.execute(
        "UPDATE plat.rede_topo_aresta a SET tensao_nominal_kv = f.tensao_nominal_kv, "
        "capacidade_kva = f.capacidade_kva FROM plat.rede_feicao_linha f "
        "WHERE a.tenant_id = f.tenant_id AND a.origem_id = f.id AND a.rede_id = %s::uuid",
        (rede_id,),
    )
    arestas_atualizadas = cur.rowcount

    tipos_transformacao = _tipo_ids_por_categoria(cur, rede_id, "transformacao")

    cur.execute("DELETE FROM plat.rede_topo_dispositivo_aresta WHERE rede_id = %s::uuid", (rede_id,))

    cur.execute(
        "SELECT p.id, p.tipo_id, p.estado_dispositivo, tc.terminais "
        "FROM plat.rede_feicao_ponto p JOIN plat.rede_tipo tp ON tp.id = p.tipo_id "
        "JOIN plat.rede_terminal_config tc ON tc.id = tp.terminal_id "
        "WHERE p.rede_id = %s::uuid AND jsonb_array_length(tc.terminais) >= 2",
        (rede_id,),
    )
    dispositivos = cur.fetchall()

    cur.execute(
        "SELECT id, origem_id, terminal_num FROM plat.rede_topo_no "
        "WHERE rede_id = %s::uuid AND papel = 'terminal' AND origem_id IS NOT NULL",
        (rede_id,),
    )
    nos_por_dispositivo: dict[str, dict[int, str]] = defaultdict(dict)
    for r in cur.fetchall():
        nos_por_dispositivo[str(r["origem_id"])][r["terminal_num"]] = str(r["id"])

    linhas = []
    ignorados_transformacao = 0
    sem_dois_nos = 0
    for d in dispositivos:
        tipo_id = str(d["tipo_id"])
        if tipo_id in tipos_transformacao:
            # o transformador SEPARA duas subredes (alta x baixa tensão) — nunca conduz por dentro desta
            # aresta interna; decisão desta função, não da migração (cláusula do enunciado).
            ignorados_transformacao += 1
            continue
        nos = nos_por_dispositivo.get(str(d["id"]), {})
        numeros = sorted(nos.keys())
        if len(numeros) < 2:
            sem_dois_nos += 1
            continue
        # dispositivo com 2+ terminais: liga o primeiro e o último terminal declarado (a ordem interna,
        # ex.: montante/jusante, não interfere aqui — quem decide isso é `topologia._resolver_uniao`).
        no1, no2 = nos[numeros[0]], nos[numeros[-1]]
        traversavel = d["estado_dispositivo"] != "aberto"
        linhas.append((tenant_id, rede_id, str(d["id"]), no1, no2, traversavel))

    for tenant_id_l, rede_id_l, origem_id, no1, no2, traversavel in linhas:
        cur.execute(
            "INSERT INTO plat.rede_topo_dispositivo_aresta"
            "(tenant_id, rede_id, origem_id, no_terminal_1_id, no_terminal_2_id, traversavel) "
            "VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s) "
            "ON CONFLICT (tenant_id, rede_id, origem_id) DO UPDATE SET "
            "no_terminal_1_id = EXCLUDED.no_terminal_1_id, no_terminal_2_id = EXCLUDED.no_terminal_2_id, "
            "traversavel = EXCLUDED.traversavel, atualizado_em = now()",
            (tenant_id_l, rede_id_l, origem_id, no1, no2, traversavel),
        )

    return {
        "arestas_tensao_capacidade_atualizadas": arestas_atualizadas,
        "dispositivos_considerados": len(dispositivos),
        "dispositivo_arestas_criadas": len(linhas),
        "ignorados_transformacao": ignorados_transformacao,
        "ignorados_sem_dois_nos": sem_dois_nos,
    }


# --- grafo comum a propagação e conectividade -----------------------------------------------------------------

def _carregar_grafo(cur, rede_id: str):
    """Nó -> lista de (aresta_id, kind, vizinho, traversavel, fase_bitmask). `kind` é 'linha' (sempre
    traversável nesta passagem — o item não modela abertura de trecho) ou 'dispositivo' (traversabilidade =
    coluna `traversavel`, refletindo o estado aberto/fechado do gatilho)."""
    vizinhos: dict[str, list] = defaultdict(list)
    cur.execute(
        "SELECT id, no_origem_id, no_destino_id, fase_bitmask FROM plat.rede_topo_aresta "
        "WHERE rede_id = %s::uuid AND no_origem_id IS NOT NULL AND no_destino_id IS NOT NULL",
        (rede_id,),
    )
    arestas_linha = cur.fetchall()
    for a in arestas_linha:
        o, d = str(a["no_origem_id"]), str(a["no_destino_id"])
        vizinhos[o].append((str(a["id"]), "linha", d, True, a["fase_bitmask"]))
        vizinhos[d].append((str(a["id"]), "linha", o, True, a["fase_bitmask"]))

    cur.execute(
        "SELECT id, no_terminal_1_id, no_terminal_2_id, traversavel, origem_id "
        "FROM plat.rede_topo_dispositivo_aresta WHERE rede_id = %s::uuid",
        (rede_id,),
    )
    arestas_disp = cur.fetchall()
    for a in arestas_disp:
        n1, n2 = str(a["no_terminal_1_id"]), str(a["no_terminal_2_id"])
        vizinhos[n1].append((str(a["id"]), "dispositivo", n2, a["traversavel"], None))
        vizinhos[n2].append((str(a["id"]), "dispositivo", n1, a["traversavel"], None))

    return vizinhos, arestas_linha, arestas_disp


def _raizes_por_categoria_fonte(cur, rede_id: str) -> list[str]:
    """Nós de topologia cujo `tipo_id` (terminal de um ponto) está na categoria `fonte` do pacote — a via
    OFICIAL do enunciado. Ver fronteira no docstring do módulo: no arquivo de teste desta rede não há
    nenhum, e o chamador cai para a raiz assumida por alimentador."""
    tipos_fonte = _tipo_ids_por_categoria(cur, rede_id, "fonte")
    if not tipos_fonte:
        return []
    cur.execute(
        "SELECT id FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND papel = 'terminal' "
        "AND tipo_id = ANY(%s::uuid[])",
        (rede_id, list(tipos_fonte)),
    )
    return [str(r["id"]) for r in cur.fetchall()]


def raizes_assumidas_por_alimentador(cur, rede_id: str) -> dict:
    """Fallback de teste (fronteira declarada): para cada `ctmt` presente nas arestas de MT, a extremidade de
    grau 1 de índice mais baixo (ordenação estável por id de nó) vira raiz assumida daquele alimentador —
    NUNCA chamada de subestação. Devolve {ctmt: no_id}."""
    cur.execute(
        "SELECT a.no_origem_id::text AS o, a.no_destino_id::text AS d, a.atributos->>'ctmt' AS ctmt "
        "FROM plat.rede_topo_aresta a JOIN plat.rede_grupo g ON g.id = a.grupo_id "
        "WHERE a.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' AND a.no_origem_id IS NOT NULL",
        (rede_id,),
    )
    grau: dict[str, int] = defaultdict(int)
    por_ctmt: dict[str, set] = defaultdict(set)
    for r in cur.fetchall():
        grau[r["o"]] += 1
        grau[r["d"]] += 1
        por_ctmt[r["ctmt"]].add(r["o"])
        por_ctmt[r["ctmt"]].add(r["d"])
    raizes = {}
    for ctmt, nos in por_ctmt.items():
        grau1 = sorted(n for n in nos if grau[n] == 1)
        if grau1:
            raizes[ctmt] = grau1[0]
    return raizes


# --- 3. propagação de fase -------------------------------------------------------------------------------------

def propagar_fase(cur, tenant_id: int, rede_id: str, raizes: dict | None = None) -> dict:
    """BFS a partir de cada raiz, propagando `fase_bitmask` para `fase_propagada` em `rede_topo_aresta`.
    Ao atravessar uma aresta de dispositivo cujo `tipo_id` (do PONTO que a originou) tem regra de
    substituição ATIVA para o atributo 'fase' e `de_valor` == fase corrente, a fase muda para `para_valor`
    (substituição declarada, nunca inferida — cláusula do enunciado). Ramos irmãos (fora do caminho da
    mudança) não são afetados: a fase corrente é propriedade do CAMINHO percorrido no BFS a partir da raiz,
    nunca do grafo inteiro — mudar `FAS_CON` a montante muda só a jusante alcançada dali.

    `raizes`: {rotulo: no_id}; se None, usa nós de categoria `fonte` e, se nenhum existir (fronteira
    declarada no docstring do módulo), a raiz assumida por alimentador. Devolve resumo com concordância
    contra a fase DECLARADA nos trechos de MT alcançados; grava a divergência em
    `plat.rede_atributo_discrepancia`, nunca corrigindo o valor declarado."""
    vizinhos, _arestas_linha, arestas_disp = _carregar_grafo(cur, rede_id)
    origem_da_aresta_disp = {str(a["id"]): str(a["origem_id"]) for a in arestas_disp}

    if raizes is None:
        oficiais = _raizes_por_categoria_fonte(cur, rede_id)
        if oficiais:
            raizes = {no_id: no_id for no_id in oficiais}
            via = "categoria_fonte"
        else:
            raizes = raizes_assumidas_por_alimentador(cur, rede_id)
            via = "raiz_assumida_por_alimentador"
    else:
        via = "informada"

    cur.execute(
        "SELECT fp.id AS ponto_id, s.de_valor, s.para_valor FROM plat.rede_atributo_substituicao s "
        "JOIN plat.rede_feicao_ponto fp ON fp.tipo_id = s.tipo_id AND fp.rede_id = s.rede_id "
        "WHERE s.rede_id = %s::uuid AND s.atributo_codigo = 'fase' AND s.ativa",
        (rede_id,),
    )
    regra_por_ponto: dict[str, list] = defaultdict(list)
    for r in cur.fetchall():
        regra_por_ponto[str(r["ponto_id"])].append((r["de_valor"], r["para_valor"]))

    fase_por_aresta_linha: dict[str, int | None] = {}

    for _rotulo, raiz in raizes.items():
        if raiz not in vizinhos:
            continue
        fila = deque([(raiz, None)])  # (no, fase corrente ao ENTRAR no nó pelo caminho do BFS)
        visitados_locais = {raiz}
        while fila:
            no, fase_atual = fila.popleft()
            for aresta_id, kind, vizinho, traversavel, fase_bitmask in vizinhos.get(no, []):
                if not traversavel or vizinho in visitados_locais:
                    continue
                if kind == "linha":
                    # a fase da aresta a jusante é a INTERSEÇÃO (bit a bit) entre a fase que chega pelo
                    # caminho do BFS e a fase FISICAMENTE declarada no próprio trecho: um ramal só pode
                    # carregar fase que o condutor dele tem E que veio de montante (tap monofásico de um
                    # tronco trifásico é o caso normal na BDGD; não existe fase "a mais" a jusante sem um
                    # dispositivo de substituição). Antes esta linha SOBRESCREVIA a fase toda a jusante
                    # pela da primeira aresta do alimentador (raiz->vizinho), fixando uma fase constante
                    # para a árvore inteira e derrubando a concordância contra FAS_CON sempre que havia
                    # ramal com menos fase que o tronco (achado ao medir em escala real, trilha il401datrib).
                    if fase_atual is None:
                        nova_fase = fase_bitmask
                    elif fase_bitmask is None:
                        nova_fase = fase_atual
                    else:
                        nova_fase = fase_atual & fase_bitmask
                    fase_por_aresta_linha[aresta_id] = nova_fase
                else:
                    nova_fase = fase_atual
                    ponto_id = origem_da_aresta_disp.get(aresta_id)
                    for de_valor, para_valor in regra_por_ponto.get(ponto_id, []):
                        if nova_fase == de_valor:
                            nova_fase = para_valor
                visitados_locais.add(vizinho)
                fila.append((vizinho, nova_fase))

    cur.execute("UPDATE plat.rede_topo_aresta SET fase_propagada = NULL WHERE rede_id = %s::uuid", (rede_id,))
    for aresta_id, fase in fase_por_aresta_linha.items():
        if fase is not None:
            cur.execute(
                "UPDATE plat.rede_topo_aresta SET fase_propagada = %s WHERE id = %s::uuid AND rede_id = %s::uuid",
                (fase, aresta_id, rede_id),
            )

    cur.execute(
        "SELECT a.id, a.fase_bitmask, a.fase_propagada FROM plat.rede_topo_aresta a "
        "JOIN plat.rede_grupo g ON g.id = a.grupo_id "
        "WHERE a.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' AND a.fase_propagada IS NOT NULL",
        (rede_id,),
    )
    linhas_mt = cur.fetchall()
    concordantes = sum(1 for r in linhas_mt if r["fase_bitmask"] == r["fase_propagada"])
    total = len(linhas_mt)

    cur.execute(
        "DELETE FROM plat.rede_atributo_discrepancia WHERE rede_id = %s::uuid AND atributo_codigo = 'fase'",
        (rede_id,),
    )
    discrepantes = 0
    for r in linhas_mt:
        if r["fase_bitmask"] != r["fase_propagada"]:
            cur.execute(
                "INSERT INTO plat.rede_atributo_discrepancia"
                "(tenant_id, rede_id, aresta_id, atributo_codigo, valor_declarado, valor_propagado) "
                "VALUES (%s, %s::uuid, %s::uuid, 'fase', %s, %s) "
                "ON CONFLICT (tenant_id, rede_id, aresta_id, atributo_codigo) DO UPDATE SET "
                "valor_declarado = EXCLUDED.valor_declarado, valor_propagado = EXCLUDED.valor_propagado, "
                "detectada_em = now()",
                (tenant_id, rede_id, r["id"], r["fase_bitmask"], r["fase_propagada"]),
            )
            discrepantes += 1

    return {
        "via_raiz": via, "raizes": len(raizes), "trechos_mt_alcancados": total,
        "concordantes": concordantes, "discrepantes": discrepantes,
        "concordancia": (concordantes / total) if total else None,
    }


# --- 4. conectividade (is_connected/subrede) ------------------------------------------------------------------

def recalcular_conectividade(cur, tenant_id: int, rede_id: str, raizes: dict | None = None) -> dict:
    """Job: alcançabilidade a partir de cada raiz, respeitando a traversabilidade do dispositivo (o mesmo
    grafo de `propagar_fase`). Todo nó/aresta alcançado por alguma raiz recebe `is_connected = true` e
    `subrede_codigo` = rótulo da raiz que o alcançou primeiro (component id); o que sobra fica
    `is_connected = false` e `subrede_codigo = NULL` — inclusive o lado morto de uma chave aberta, que some
    do alcance assim que ela abre (refutação do item)."""
    vizinhos, arestas_linha, arestas_disp = _carregar_grafo(cur, rede_id)

    if raizes is None:
        oficiais = _raizes_por_categoria_fonte(cur, rede_id)
        if oficiais:
            raizes = {no_id: no_id for no_id in oficiais}
        else:
            raizes = raizes_assumidas_por_alimentador(cur, rede_id)

    subrede_do_no: dict[str, str] = {}
    for rotulo, raiz in raizes.items():
        fila = deque([raiz])
        visitados_locais = {raiz}
        subrede_do_no[raiz] = rotulo
        while fila:
            no = fila.popleft()
            for _aresta_id, _kind, vizinho, traversavel, _fase in vizinhos.get(no, []):
                if not traversavel or vizinho in visitados_locais:
                    continue
                visitados_locais.add(vizinho)
                subrede_do_no[vizinho] = rotulo
                fila.append(vizinho)

    cur.execute(
        "UPDATE plat.rede_topo_no SET is_connected = false, subrede_codigo = NULL WHERE rede_id = %s::uuid",
        (rede_id,),
    )
    cur.execute(
        "UPDATE plat.rede_topo_aresta SET is_connected = false, subrede_codigo = NULL WHERE rede_id = %s::uuid",
        (rede_id,),
    )
    nos_conectados = 0
    for no_id, rotulo in subrede_do_no.items():
        cur.execute(
            "UPDATE plat.rede_topo_no SET is_connected = true, subrede_codigo = %s "
            "WHERE id = %s::uuid AND rede_id = %s::uuid",
            (rotulo, no_id, rede_id),
        )
        nos_conectados += cur.rowcount

    arestas_conectadas = 0
    for a in arestas_linha:
        o, d = str(a["no_origem_id"]), str(a["no_destino_id"])
        rotulo = subrede_do_no.get(o) or subrede_do_no.get(d)
        if rotulo is None:
            continue
        cur.execute(
            "UPDATE plat.rede_topo_aresta SET is_connected = true, subrede_codigo = %s "
            "WHERE id = %s::uuid AND rede_id = %s::uuid",
            (rotulo, str(a["id"]), rede_id),
        )
        arestas_conectadas += cur.rowcount

    cur.execute("SELECT count(*) AS n FROM plat.rede_topo_no WHERE rede_id = %s::uuid", (rede_id,))
    total_nos = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid", (rede_id,))
    total_arestas = cur.fetchone()["n"]

    return {
        "raizes": len(raizes), "nos_conectados": nos_conectados, "nos_total": total_nos,
        "arestas_conectadas": arestas_conectadas, "arestas_total": total_arestas,
        "subredes": len({v for v in subrede_do_no.values()}),
    }


# --- regra de substituição --------------------------------------------------------------------------------------

def definir_substituicao(cur, tenant_id: int, rede_id: str, tipo_id: str, atributo_codigo: str,
                          de_valor: int, para_valor: int, descricao: str | None = None) -> str:
    """Registra (ou atualiza) a regra de substituição: um dispositivo do TIPO dado troca o valor do atributo
    propagável de `de_valor` para `para_valor` ao ser atravessado — nunca aplicada em silêncio, sempre por
    regra explícita nesta tabela (cláusula do enunciado)."""
    cur.execute(
        "INSERT INTO plat.rede_atributo_substituicao"
        "(tenant_id, rede_id, tipo_id, atributo_codigo, de_valor, para_valor, descricao) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s) "
        "ON CONFLICT (rede_id, tipo_id, atributo_codigo, de_valor) DO UPDATE SET "
        "para_valor = EXCLUDED.para_valor, descricao = EXCLUDED.descricao, ativa = true "
        "RETURNING id",
        (tenant_id, rede_id, tipo_id, atributo_codigo, de_valor, para_valor, descricao),
    )
    return str(cur.fetchone()["id"])
