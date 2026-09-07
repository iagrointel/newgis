"""Traçado de ISOLAMENTO (item L4-02-c-isolamento).

A pergunta do operador é: caiu um trecho aqui — quais dispositivos eu preciso abrir para que este ponto fique
sem energia, e o que mais fica sem energia junto? A resposta tem três partes, e este módulo devolve as três:
`dispositivos_a_abrir`, `elementos_isolados` e um `resumo` (clientes, transformadores e quilômetros por nível
de tensão).

O grafo é o MESMO dos outros traçados: `lacos._montar_arestas_custo` monta, sobre `tracado_mapa`, a união das
arestas reais da topologia derivada com as arestas virtuais de cada dispositivo (chave com `estado = aberto`
não entra, barreira do pedido sai do mapa antes). Não existe um segundo motor de traçado nesta casa.

Como o conjunto é escolhido, passo a passo:

  1. CANDIDATO é o dispositivo (feição de PONTO) cujo tipo tem uma das `categorias_isolamento` do pedido
     (padrão: `dispositivo_de_protecao` e `seccionamento` — proteção e manobra) e que hoje conduz.
  2. OPERÁVEL é o candidato que a base declara em condição de ser aberto: `atributos.estado` PRESENTE (sem o
     estado não se sabe a posição do dispositivo, logo não se pode contar com ele) e `atributos.operavel`
     fora de {nao, false, 0}. É a barreira de CONDIÇÃO do item: ela não para o traçado, ela desqualifica o
     dispositivo como ponto de corte, e o traçado segue procurando o próximo. Com `ignorar_inoperante=false`
     o pedido abre mão dessa exigência e conta com qualquer candidato da categoria.
  3. FRONTEIRA: apagando do grafo as arestas dos dispositivos operáveis, o que se alcança a partir do ponto é
     a ZONA. Todo dispositivo operável com uma ponta na zona e outra fora é fronteira — é o primeiro
     dispositivo em cada direção que sai do ponto, que é o mesmo critério do traçado de isolamento da rede de
     utilidades da Esri (isolation-trace.htm).
  4. CORTE: o conjunto de fronteira só é resposta se ele de fato desenergiza — se, com ele aberto, o ponto
     não alcança nenhuma feição da categoria de fonte (`categoria_controlador` do pedido, padrão `fonte`).
     Quando alcança, existe caminho de energia SEM dispositivo que possa abri-lo: a resposta é
     `isolavel=false` com esse motivo, nunca um conjunto que não isola.
  5. MÍNIMO POR INCLUSÃO: cada dispositivo da fronteira só fica se for necessário — com todos os OUTROS
     abertos, o ponto ainda alcança a fonte por ele. A pergunta é respondida num grafo REDUZIDO, montado uma
     vez: cada componente do grafo sem dispositivos vira um vértice, cada dispositivo operável vira uma
     ligação. Ele tem a ordem de grandeza do número de dispositivos, não do número de trechos, e é nele que
     se percorre uma vez por dispositivo da fronteira. Não vale perguntar só "a fonte está do outro lado
     imediato deste dispositivo?": quase nunca está — ela fica adiante, atrás de dispositivos que continuam
     FECHADOS, e essa pergunta curta devolveria a fronteira inteira.

`elementos_isolados` é o que fica sem energia. Sem `incluir_isolados`, é a zona do ponto. Com
`incluir_isolados=true`, entram também os elementos de ALÉM dos dispositivos que só se alimentavam por ela —
componentes que tinham fonte antes da manobra e não têm depois. O que já estava sem fonte ANTES não entra em
nenhum dos dois casos (seria contar como consequência da manobra o que já era consequência de outra coisa);
esses ficam contados em `resumo.ja_estavam_sem_fonte`."""

import json
import time

from app.erros import ErroAPI
from app.rede_utilidades import lacos as _lac
from app.rede_utilidades import tracado as _tr

TIPO = "isolamento"
CATEGORIAS_PADRAO = ("dispositivo_de_protecao", "seccionamento")
_TAG = "isolamento_sql"
_OPERAVEL_FALSO = ("nao", "não", "false", "0")


def _componentes(cur, excluidas: list[int]) -> dict[int, int]:
    """`{no_iid: componente}` do grafo `lacos_arestas` sem as arestas de `excluidas` (as dos dispositivos que
    a manobra abre). Nó sem nenhuma aresta não aparece — quem chama trata a ausência como componente próprio."""
    if excluidas:
        filtro = cur.mogrify("WHERE id <> ALL(%s::bigint[])", (list(excluidas),)).decode("utf-8")
    else:
        filtro = ""
    cur.execute(
        f"SELECT node, component FROM public.pgr_connectedComponents("
        f"${_TAG}$ SELECT id, source, target, cost FROM lacos_arestas {filtro} ${_TAG}$)"
    )
    return {r["node"]: r["component"] for r in cur.fetchall()}


def _comp_de(componentes: dict[int, int], iid: int) -> int:
    """Componente de um nó, com nó solto (sem aresta) recebendo um componente só dele — negativo para nunca
    colidir com os que `pgr_connectedComponents` numera."""
    return componentes.get(iid, -iid)


def _iids(cur, no_ids: list[str]) -> list[int]:
    if not no_ids:
        return []
    cur.execute("SELECT iid FROM tracado_mapa WHERE no_id = ANY(%s::uuid[])", (no_ids,))
    return [r["iid"] for r in cur.fetchall()]


def _iids_da_categoria(cur, rede_id: str, categoria: str) -> set[int]:
    cur.execute(
        "SELECT DISTINCT tm.iid FROM tracado_mapa tm JOIN plat.rede_topo_no n ON n.id = tm.no_id "
        "JOIN plat.rede_tipo_categoria rtc ON rtc.tipo_id = n.tipo_id "
        "JOIN plat.rede_categoria rc ON rc.id = rtc.categoria_id "
        "WHERE n.rede_id = %s::uuid AND n.papel = 'terminal' AND rc.codigo = %s",
        (rede_id, categoria),
    )
    return {r["iid"] for r in cur.fetchall()}


def _candidatos(cur, rede_id: str, categorias: list[str], ignorar_inoperante: bool) -> tuple[list[dict], list[dict]]:
    """(operáveis, inoperáveis): as arestas de `lacos_arestas` que são caminho interno de um dispositivo de
    uma das `categorias`, com a ficha do dispositivo. Inoperável = sem `estado` declarado ou com `operavel`
    negado; com `ignorar_inoperante=false` a lista de inoperáveis sai vazia e todos entram como operáveis."""
    cur.execute(
        "SELECT la.id AS aresta_id, la.source, la.target, f.id AS feicao_id, f.tipo_id, "
        "       f.atributos ->> 'estado' AS estado, f.atributos ? 'estado' AS tem_estado, "
        "       lower(coalesce(f.atributos ->> 'operavel', 'sim')) AS operavel "
        "FROM lacos_arestas la "
        "JOIN plat.rede_feicao_ponto f ON f.id = la.feicao_id AND f.rede_id = %s::uuid "
        "WHERE EXISTS (SELECT 1 FROM plat.rede_tipo_categoria rtc JOIN plat.rede_categoria rc "
        "              ON rc.id = rtc.categoria_id "
        "              WHERE rtc.tipo_id = f.tipo_id AND rc.codigo = ANY(%s)) "
        "ORDER BY la.id",
        (rede_id, categorias),
    )
    operaveis, inoperaveis = [], []
    for r in cur.fetchall():
        ficha = {
            "aresta_id": r["aresta_id"], "source": r["source"], "target": r["target"],
            "feicao_id": str(r["feicao_id"]), "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
            "estado": r["estado"],
        }
        if not ignorar_inoperante:
            operaveis.append({**ficha, "motivo_inoperante": None})
            continue
        if not r["tem_estado"]:
            inoperaveis.append({**ficha, "motivo_inoperante": "sem_estado"})
        elif r["operavel"] in _OPERAVEL_FALSO:
            inoperaveis.append({**ficha, "motivo_inoperante": "operavel_negado"})
        else:
            operaveis.append({**ficha, "motivo_inoperante": None})
    return operaveis, inoperaveis


def _fichas(cur, rede_id: str, dispositivos: list[dict]) -> list[dict]:
    """Uma linha por DISPOSITIVO (não por aresta interna dele), com o nome do tipo e do grupo."""
    tipos = _tr._info_tipos(cur, rede_id, {d["tipo_id"] for d in dispositivos if d["tipo_id"]})
    saida, vistos = [], set()
    for d in sorted(dispositivos, key=lambda x: x["feicao_id"]):
        if d["feicao_id"] in vistos:
            continue
        vistos.add(d["feicao_id"])
        info = tipos.get(d["tipo_id"], {})
        saida.append({
            "feicao_id": d["feicao_id"], "tipo_id": d["tipo_id"], "grupo": info.get("grupo"),
            "tipo_chave": info.get("chave"), "tipo_nome": info.get("nome"), "estado": d["estado"],
            "motivo_inoperante": d["motivo_inoperante"],
        })
    return saida


def _resumo(cur, rede_id: str, nos: list[str], ja_sem_fonte: int) -> dict:
    """Clientes (categoria `consumo`), transformadores (categoria `transformacao`) e quilômetros por nível —
    nível é o GRUPO do tipo do trecho (trecho de média tensão, de baixa tensão, ramal de ligação)."""
    clientes = trafos = 0
    if nos:
        cur.execute(
            "SELECT rc.codigo, count(DISTINCT n.origem_id) AS n FROM plat.rede_topo_no n "
            "JOIN plat.rede_tipo_categoria rtc ON rtc.tipo_id = n.tipo_id "
            "JOIN plat.rede_categoria rc ON rc.id = rtc.categoria_id "
            "WHERE n.rede_id = %s::uuid AND n.id = ANY(%s::uuid[]) AND n.papel = 'terminal' "
            "AND rc.codigo IN ('consumo', 'transformacao') GROUP BY rc.codigo",
            (rede_id, nos),
        )
        por_categoria = {r["codigo"]: r["n"] for r in cur.fetchall()}
        clientes = por_categoria.get("consumo", 0)
        trafos = por_categoria.get("transformacao", 0)
    km_por_nivel: dict[str, float] = {}
    if nos:
        cur.execute(
            "SELECT g.codigo AS nivel, sum(a.comprimento_m) AS metros FROM plat.rede_topo_aresta a "
            "JOIN plat.rede_grupo g ON g.id = a.grupo_id "
            "WHERE a.rede_id = %s::uuid AND a.no_origem_id = ANY(%s::uuid[]) "
            "AND a.no_destino_id = ANY(%s::uuid[]) GROUP BY g.codigo ORDER BY g.codigo",
            (rede_id, nos, nos),
        )
        km_por_nivel = {r["nivel"]: round(float(r["metros"]) / 1000.0, 6) for r in cur.fetchall()}
    return {
        "clientes": clientes, "trafos": trafos,
        "km_total": round(sum(km_por_nivel.values()), 6), "km_por_nivel": km_por_nivel,
        "ja_estavam_sem_fonte": ja_sem_fonte,
    }


def _nos_de(cur, iids: list[int]) -> list[str]:
    if not iids:
        return []
    cur.execute("SELECT no_id FROM tracado_mapa WHERE iid = ANY(%s::bigint[])", (list(iids),))
    return [str(r["no_id"]) for r in cur.fetchall()]


def _saida(*, isolavel: bool, motivo: str | None, mensagem: str | None, dispositivos: list[dict],
           inoperaveis: list[dict], elementos: list[dict], geometria: dict | None, nos: list[str],
           resumo: dict, pedido: dict, inicio: float, geometria_dispositivos: dict | None = None) -> dict:
    return {
        "tipo": TIPO, "isolavel": isolavel, "motivo": motivo, "mensagem": mensagem,
        "dispositivos_a_abrir": dispositivos, "dispositivos_inoperantes": inoperaveis,
        "elementos_isolados": elementos, "contagem": len(elementos), "nos_alcancados": len(nos),
        "geometria": geometria, "geometria_dispositivos": geometria_dispositivos, "resumo": resumo, **pedido,
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }


def tracar_isolamento(cur, tenant_id: int, rede_id: str, pontos_partida: list[dict], barreiras: list[dict],
                      categorias_isolamento: list[str], categoria_fonte: str, incluir_isolados: bool,
                      ignorar_inoperante: bool) -> dict:
    """Ver o cabeçalho do módulo. `categoria_fonte` é a categoria que representa a entrada de energia
    (`categoria_controlador` do pedido, padrão `fonte`), a mesma de `lacos.isolados`."""
    if not pontos_partida:
        raise ErroAPI(422, "sem_ponto_de_partida", "informe ao menos um ponto de partida")
    categorias = list(dict.fromkeys(categorias_isolamento or CATEGORIAS_PADRAO))
    inicio = time.perf_counter()
    pedido = {
        "categorias_isolamento": categorias, "categoria_fonte": categoria_fonte,
        "incluir_isolados": incluir_isolados, "ignorar_inoperante": ignorar_inoperante,
    }

    tolerancia_rede, ids_barreira = _lac._preparar_mapa(cur, rede_id, barreiras)
    ids_inicio = [_tr._resolver_ponto(cur, rede_id, tolerancia_rede, p) for p in pontos_partida]
    if [i for i in ids_inicio if i in ids_barreira]:
        raise ErroAPI(422, "inicio_e_barreira", "um ponto de partida não pode também ser barreira")
    _lac._montar_arestas_custo(cur, rede_id, ignorar_transformacao=False, atributo_custo=None)

    iids_inicio = _iids(cur, ids_inicio)
    iids_fonte = _iids_da_categoria(cur, rede_id, categoria_fonte)
    if not iids_fonte:
        raise ErroAPI(
            422, "categoria_controlador_sem_feicao",
            f"nenhuma feição com categoria '{categoria_fonte}' nesta rede — sem fonte declarada não há o que "
            "desenergizar; informe uma categoria que exista no pacote instalado (ex.: 'fonte')")

    operaveis, inoperaveis = _candidatos(cur, rede_id, categorias, ignorar_inoperante)
    arestas_operaveis = [d["aresta_id"] for d in operaveis]

    antes = _componentes(cur, [])
    comps_com_fonte_antes = {_comp_de(antes, i) for i in iids_fonte}
    if not any(_comp_de(antes, i) in comps_com_fonte_antes for i in iids_inicio):
        nos_zona = _nos_de(cur, [i for i in antes
                                if _comp_de(antes, i) in {_comp_de(antes, j) for j in iids_inicio}] or iids_inicio)
        elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, nos_zona)
        return _saida(
            isolavel=True, motivo="ponto_ja_sem_fonte",
            mensagem="este ponto já não alcança nenhuma fonte na rede como ela está agora (chave aberta, "
                     "trecho faltando ou barreira do próprio pedido): nenhum dispositivo precisa ser aberto",
            dispositivos=[], inoperaveis=_fichas(cur, rede_id, inoperaveis), elementos=elementos,
            geometria=geometria, nos=nos_zona,
            resumo=_resumo(cur, rede_id, nos_zona, 0), pedido=pedido, inicio=inicio)

    # zona: o que se alcança do ponto quando as arestas de cada um dos dispositivos operáveis somem
    sem_dispositivos = _componentes(cur, arestas_operaveis)
    comps_zona = {_comp_de(sem_dispositivos, i) for i in iids_inicio}
    iids_zona = {i for i in sem_dispositivos if sem_dispositivos[i] in comps_zona} | set(iids_inicio)
    fronteira = [d for d in operaveis
                 if (d["source"] in iids_zona) != (d["target"] in iids_zona)]

    comps_com_fonte = {_comp_de(sem_dispositivos, i) for i in iids_fonte}
    if comps_zona & comps_com_fonte:
        elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, _nos_de(cur, sorted(iids_zona)))
        return _saida(
            isolavel=False, motivo="caminho_sem_dispositivo",
            mensagem="existe caminho de energia entre este ponto e uma fonte sem nenhum dispositivo das "
                     f"categorias {categorias} que possa ser aberto: com o que a rede declara hoje, este "
                     "ponto não pode ser isolado por manobra",
            dispositivos=[], inoperaveis=_fichas(cur, rede_id, inoperaveis), elementos=elementos,
            geometria=geometria, nos=_nos_de(cur, sorted(iids_zona)),
            resumo=_resumo(cur, rede_id, _nos_de(cur, sorted(iids_zona)), 0), pedido=pedido, inicio=inicio)

    # mínimo por inclusão, no grafo REDUZIDO: cada componente do grafo sem dispositivos vira um vértice e
    # cada dispositivo operável vira uma ligação entre dois vértices. Abrir um conjunto de dispositivos é
    # apagar as ligações correspondentes. O grafo reduzido tem tantos vértices quantos componentes (ordem do
    # número de dispositivos), então percorrê-lo uma vez por dispositivo da fronteira é barato — e é a única
    # maneira honesta de perguntar "com todos os OUTROS abertos, este ainda liga o ponto à fonte?", porque a
    # fonte quase nunca está do outro lado imediato do dispositivo: está adiante, atrás de dispositivos que
    # continuam FECHADOS.
    vizinhos: dict[int, list[tuple[int, int]]] = {}
    for d in operaveis:
        ca, cb = _comp_de(sem_dispositivos, d["source"]), _comp_de(sem_dispositivos, d["target"])
        if ca == cb:
            continue
        vizinhos.setdefault(ca, []).append((cb, d["aresta_id"]))
        vizinhos.setdefault(cb, []).append((ca, d["aresta_id"]))

    def alcanca_fonte(abertas: set[int]) -> bool:
        vistos, fila = set(comps_zona), list(comps_zona)
        if vistos & comps_com_fonte:
            return True
        while fila:
            atual = fila.pop()
            for vizinho, aresta in vizinhos.get(atual, ()):
                if aresta in abertas or vizinho in vistos:
                    continue
                if vizinho in comps_com_fonte:
                    return True
                vistos.add(vizinho)
                fila.append(vizinho)
        return False

    escolhidos = list(fronteira)
    if alcanca_fonte({d["aresta_id"] for d in escolhidos}):
        # não deveria acontecer (a fronteira é tudo o que sai da zona), mas se acontecer o produto diz que
        # não isola em vez de devolver um conjunto que não corta
        elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, _nos_de(cur, sorted(iids_zona)))
        nos_zona = _nos_de(cur, sorted(iids_zona))
        return _saida(
            isolavel=False, motivo="caminho_sem_dispositivo",
            mensagem="mesmo abrindo todos os dispositivos operáveis que cercam este ponto ele continua "
                     "ligado a uma fonte: com o que a rede declara hoje, não pode ser isolado por manobra",
            dispositivos=[], inoperaveis=_fichas(cur, rede_id, inoperaveis), elementos=elementos,
            geometria=geometria, nos=nos_zona, resumo=_resumo(cur, rede_id, nos_zona, 0), pedido=pedido,
            inicio=inicio)
    for d in sorted(fronteira, key=lambda x: (x["feicao_id"], x["aresta_id"])):
        sobra = [o for o in escolhidos if o["aresta_id"] != d["aresta_id"]]
        if not alcanca_fonte({o["aresta_id"] for o in sobra}):
            escolhidos = sobra  # dispositivo dispensável: sem ele o conjunto ainda desenergiza o ponto

    # o que fica sem energia. Sem `incluir_isolados`, é a ZONA — o trecho entre dispositivos, que é onde a
    # equipe vai trabalhar. Com `incluir_isolados`, é tudo o que perde a fonte depois da manobra: a zona mais
    # o que está além dos dispositivos que NÃO foram abertos e se alimentava por ela.
    ja_sem_fonte = 0
    if not incluir_isolados:
        iids_isolados = set(iids_zona)
    else:
        depois = _componentes(cur, [d["aresta_id"] for d in escolhidos])
        comps_fonte_depois = {_comp_de(depois, i) for i in iids_fonte}
        comps_alvo = {_comp_de(depois, i) for i in iids_inicio}
        for comp in set(depois.values()) - comps_fonte_depois:
            nos_comp = [i for i in depois if depois[i] == comp]
            tinha_fonte_antes = any(_comp_de(antes, i) in comps_com_fonte_antes for i in nos_comp)
            if tinha_fonte_antes:
                comps_alvo.add(comp)
            elif comp not in comps_alvo:
                ja_sem_fonte += len(nos_comp)
        iids_isolados = {i for i in depois if depois[i] in comps_alvo} | set(iids_inicio) | set(iids_zona)
    nos_isolados = _nos_de(cur, sorted(iids_isolados))
    elementos, geometria = _tr.elementos_e_geometria(cur, rede_id, nos_isolados)
    fichas = _fichas(cur, rede_id, escolhidos)
    return _saida(
        isolavel=True, motivo=None, mensagem=None,
        dispositivos=fichas, inoperaveis=_fichas(cur, rede_id, inoperaveis),
        elementos=elementos, geometria=geometria, nos=nos_isolados,
        geometria_dispositivos=geometria_dos_dispositivos(cur, rede_id, [f["feicao_id"] for f in fichas]),
        resumo=_resumo(cur, rede_id, nos_isolados, ja_sem_fonte), pedido=pedido, inicio=inicio)


def geometria_dos_dispositivos(cur, rede_id: str, feicao_ids: list[str]) -> dict | None:
    """GeoJSON dos dispositivos escolhidos, para a tela desenhá-los em cor própria por cima do traçado."""
    if not feicao_ids:
        return None
    cur.execute(
        "SELECT ST_AsGeoJSON(ST_Collect(geom)) AS geojson FROM plat.rede_feicao_ponto "
        "WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
        (rede_id, feicao_ids),
    )
    r = cur.fetchone()
    return json.loads(r["geojson"]) if r and r["geojson"] else None
