"""Diagrama de rede — grafo esquemático derivado de um traçado, de uma subrede ou de uma seleção
(item L4-04-d-diagrama-esquematico).

O diagrama NÃO é um mapa e NÃO é dado de origem. Ele é um GRAFO derivado três vezes: a topologia
(`plat.rede_topo_no`/`rede_topo_aresta`, item L4-01-b) já é índice derivado das feições; o RECORTE (subrede
atualizada, traçado com pontos de partida, ou seleção de feições) escolhe que parte dela entra; as REGRAS do
modelo simplificam o que entrou; e o LAYOUT dá coordenadas no ESPAÇO DO DIAGRAMA — unidades adimensionais,
nunca graus. É por isso que o desenho pode "mentir" a geografia sem mentir a rede: o que ele preserva é a
CONECTIVIDADE, e é isso que as cláusulas do portão medem.

Modelo (template), regras e layout seguem os nomes da fonte declarada no item (`introduce-diagram-templates`,
`diagram-rules`, `diagram-layouts`, `reduce-junction-rule-reference`), traduzidos:

  * `reduzir_juncao_de_passagem` (Reduce Junction): um nó de passagem — grau 2, sem valor próprio para quem lê
    o esquema — sai, e as duas arestas dele viram UMA aresta que guarda as feições das duas. Nunca reduz um nó
    cujos dois vizinhos são o MESMO nó: isso apagaria a aresta de um laço, que é justamente o que o esquema
    precisa mostrar.
  * `colapsar_conteiner` (Collapse Container): os vários terminais do MESMO dispositivo viram um nó só. É a
    tradução honesta de "contêiner" no nosso modelo: a topologia deliberadamente NÃO atravessa o dispositivo
    (cada terminal é um nó próprio, ver `topologia.py`), e no esquema um transformador é uma caixa, não dois
    pontos.
  * `remover_tipos` (Remove Feature): tira do desenho os nós de tipos declarados (poste, por exemplo). Pode
    desconectar o grafo — é regra de LEITURA, e o relatório devolve quantos componentes ficaram.

Layouts implementados: `arvore_inteligente`, `radial`, `linha_principal`, `geografico`, `grade` e
`forca_dirigida`. Layout só atribui x,y: nenhum layout cria ou apaga nó ou aresta (é asserção do módulo, e o
teste do laço depende dela). Depois de posicionar, `_resolver_sobreposicao` garante a distância mínima de 1
unidade entre quaisquer dois nós, por varredura em grade (nunca comparação de todos contra todos).

CONSISTÊNCIA (network-diagram-consistency.htm): o diagrama nasce `consistente` e vira `inconsistente` quando a
rede é editada dentro da área que ele desenha — o mesmo ciclo limpa/suja da subrede. Ele NÃO se atualiza
sozinho: quem gera de novo é quem lê o desenho, e até lá o estado fica escrito na resposta e na tela."""

import hashlib
import io
import json
import math
import time
from collections import defaultdict, deque

from app.erros import ErroAPI
from app.rede_utilidades import tracado

LAYOUTS = ("arvore_inteligente", "radial", "linha_principal", "geografico", "grade", "forca_dirigida")
REGRAS = ("reduzir_juncao_de_passagem", "colapsar_conteiner", "remover_tipos")
ORIGENS = ("subrede", "tracado", "selecao")

ESPACO = 2.0  # distância nominal entre nós vizinhos, em unidades do diagrama
SEPARACAO_MINIMA = 1.0  # cláusula do portão: nenhum par de nós a menos disto
NOS_MAXIMO = 20000  # teto de tamanho do desenho: acima disso o esquema não se lê e a resposta não cabe

# Modelos embutidos (a fonte chama de *diagram templates*). O inquilino pode declarar os dele em
# `plat.rede_diagrama_modelo`; estes existem para que a primeira geração não dependa de configuração.
MODELOS_PADRAO = {
    "basico": {
        "nome": "Básico (sem simplificação)",
        "regras": [],
        "layout": "arvore_inteligente",
    },
    "esquematico": {
        "nome": "Esquemático (junções de passagem reduzidas, dispositivo colapsado)",
        "regras": [{"regra": "colapsar_conteiner"}, {"regra": "reduzir_juncao_de_passagem"}],
        "layout": "linha_principal",
    },
    "geografico": {
        "nome": "Geográfico (posição do mapa, sem simplificação)",
        "regras": [],
        "layout": "geografico",
    },
}


# --- grafo: leitura da topologia --------------------------------------------------------------------------

def _chave_terminal(feicao_id: str, terminal: int) -> str:
    return f"terminal:{feicao_id}:{terminal}"


def _chave_conexao(no_id: str) -> str:
    return f"conexao:{no_id}"


def _grafo_de_elementos(cur, rede_id: str, elementos: list[dict]) -> dict:
    """Monta o grafo do diagrama a partir dos ELEMENTOS de um recorte — a mesma forma que `tracado.tracar` e
    `plat.rede_subrede_elemento` usam: `{feicao_id, terminal}` com `terminal=None` para trecho.

    Entram: os nós de terminal dos dispositivos do recorte; as arestas de topologia dos trechos do recorte,
    com os dois nós de ponta delas (inclusive nó de conexão, que não tem feição própria); e as arestas
    INTERNAS de dispositivo (um `caminho_valido` do terminal config = uma aresta), sem as quais o desenho
    mostraria um transformador como dois pontos soltos."""
    terminais = {}
    linhas = []
    for e in elementos:
        if e.get("terminal") is None:
            linhas.append(str(e["feicao_id"]))
        else:
            terminais.setdefault(str(e["feicao_id"]), set()).add(int(e["terminal"]))

    nos: dict[str, dict] = {}
    arestas: list[dict] = []
    por_no: dict[str, str] = {}  # id do nó de topologia -> chave no diagrama

    def _registrar(linha) -> str:
        no_id = str(linha["id"])
        if linha["papel"] == "terminal":
            chave = _chave_terminal(str(linha["origem_id"]), int(linha["terminal_num"]))
        else:
            chave = _chave_conexao(no_id)
        por_no[no_id] = chave
        if chave not in nos:
            nos[chave] = {
                "chave": chave, "papel": linha["papel"],
                "feicao_id": str(linha["origem_id"]) if linha["origem_id"] else None,
                "terminal_num": linha["terminal_num"],
                "tipo_id": str(linha["tipo_id"]) if linha["tipo_id"] else None,
                "tipo_chave": None, "rotulo": None, "agregados": 1,
                "lon": linha["lon"], "lat": linha["lat"], "x": 0.0, "y": 0.0,
            }
        return chave

    sql_no = ("SELECT id, papel, origem_id, terminal_num, tipo_id, ST_X(geom) AS lon, ST_Y(geom) AS lat "
              "FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND ")

    if linhas:
        cur.execute(
            "SELECT id, origem_id, tipo_id, no_origem_id, no_destino_id, comprimento_m "
            "FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid AND origem_id = ANY(%s::uuid[]) "
            "AND no_origem_id IS NOT NULL AND no_destino_id IS NOT NULL ORDER BY id",
            (rede_id, linhas),
        )
        cruas = [dict(r) for r in cur.fetchall()]
        pontas = sorted({str(r["no_origem_id"]) for r in cruas} | {str(r["no_destino_id"]) for r in cruas})
        if pontas:
            cur.execute(sql_no + "id = ANY(%s::uuid[]) ORDER BY id", (rede_id, pontas))
            for linha in cur.fetchall():
                _registrar(linha)
        for r in cruas:
            de, para = por_no[str(r["no_origem_id"])], por_no[str(r["no_destino_id"])]
            arestas.append({"chave": f"topologia:{r['id']}", "de": de, "para": para, "origem": "topologia",
                            "feicoes": [str(r["origem_id"])], "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
                            "tipo_chave": None, "agregadas": 1,
                            "comprimento_m": float(r["comprimento_m"])})

    if terminais:
        cur.execute(sql_no + "papel = 'terminal' AND origem_id = ANY(%s::uuid[]) ORDER BY id",
                    (rede_id, sorted(terminais)))
        por_feicao_terminal: dict[tuple, str] = {}
        for linha in cur.fetchall():
            if int(linha["terminal_num"]) not in terminais[str(linha["origem_id"])]:
                continue
            chave = _registrar(linha)
            por_feicao_terminal[(str(linha["origem_id"]), int(linha["terminal_num"]))] = chave
        # aresta interna do dispositivo: um caminho válido declarado no terminal config do pacote
        cur.execute(
            "SELECT f.id, cv.de, cv.para FROM plat.rede_feicao_ponto f "
            "JOIN plat.rede_tipo t ON t.id = f.tipo_id "
            "JOIN plat.rede_terminal_config tc ON tc.id = t.terminal_id "
            "CROSS JOIN LATERAL jsonb_to_recordset(tc.caminhos_validos) AS cv(de int, para int, nome text) "
            "WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) ORDER BY f.id, cv.de, cv.para",
            (rede_id, sorted(terminais)),
        )
        for r in cur.fetchall():
            de = por_feicao_terminal.get((str(r["id"]), int(r["de"])))
            para = por_feicao_terminal.get((str(r["id"]), int(r["para"])))
            if de and para and de != para:
                arestas.append({"chave": f"dispositivo:{r['id']}:{r['de']}-{r['para']}", "de": de,
                                "para": para, "origem": "dispositivo", "feicoes": [str(r["id"])],
                                "tipo_id": None, "tipo_chave": None, "agregadas": 1, "comprimento_m": 0.0})

    if len(nos) > NOS_MAXIMO:
        raise ErroAPI(422, "diagrama_grande",
                      f"este recorte tem {len(nos)} nós; o teto de um diagrama é {NOS_MAXIMO}")
    _decorar(cur, rede_id, nos, arestas)
    return {"nos": nos, "arestas": arestas}


def _decorar(cur, rede_id: str, nos: dict, arestas: list) -> None:
    """Preenche a chave do tipo (vocabulário do pacote) e o rótulo de cada nó. O rótulo é o `cod_id` do
    arquivo quando existe — é por ele que quem opera a rede reconhece o ativo; sem ele, o nome do tipo."""
    ids = {n["tipo_id"] for n in nos.values() if n["tipo_id"]} | {a["tipo_id"] for a in arestas if a["tipo_id"]}
    tipos = tracado._info_tipos(cur, rede_id, ids)
    for n in nos.values():
        info = tipos.get(n["tipo_id"], {})
        n["tipo_chave"] = info.get("chave")
        n["tipo_nome"] = info.get("nome")
    for a in arestas:
        a["tipo_chave"] = tipos.get(a["tipo_id"], {}).get("chave")
    feicoes = sorted({n["feicao_id"] for n in nos.values() if n["feicao_id"]})
    if feicoes:
        cur.execute(
            "SELECT id, atributos->>'cod_id' AS cod_id FROM plat.rede_feicao_ponto "
            "WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
            (rede_id, feicoes),
        )
        rotulos = {str(r["id"]): r["cod_id"] for r in cur.fetchall()}
        for n in nos.values():
            n["rotulo"] = rotulos.get(n["feicao_id"]) or n.get("tipo_nome") or n["papel"]
    for n in nos.values():
        if not n["rotulo"]:
            n["rotulo"] = n.get("tipo_nome") or n["papel"]


# --- recortes ---------------------------------------------------------------------------------------------

def elementos_da_subrede(cur, rede_id: str, subrede_id: str) -> list[dict]:
    """Os elementos gravados pela última atualização da subrede (item L4-04-b). Subrede nunca atualizada não
    tem elemento nenhum: o diagrama é recusado em vez de sair vazio fingindo rede."""
    cur.execute(
        "SELECT feicao_id, terminal_num FROM plat.rede_subrede_elemento "
        "WHERE rede_id = %s::uuid AND subrede_id = %s::uuid ORDER BY feicao_id, terminal_num",
        (rede_id, subrede_id),
    )
    return [{"feicao_id": str(r["feicao_id"]), "terminal": r["terminal_num"]} for r in cur.fetchall()]


def elementos_da_selecao(cur, rede_id: str, feicoes: list[str]) -> list[dict]:
    """Uma seleção de feições (ponto e/ou linha): de um ponto entram TODOS os terminais dele, de uma linha
    entra a aresta. Feição que não é desta rede simplesmente não entra — não se inventa nó."""
    if not feicoes:
        return []
    cur.execute(
        "SELECT origem_id, terminal_num FROM plat.rede_topo_no "
        "WHERE rede_id = %s::uuid AND papel = 'terminal' AND origem_id = ANY(%s::uuid[]) "
        "ORDER BY origem_id, terminal_num",
        (rede_id, feicoes),
    )
    elementos = [{"feicao_id": str(r["origem_id"]), "terminal": r["terminal_num"]} for r in cur.fetchall()]
    cur.execute("SELECT id FROM plat.rede_feicao_linha WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) "
                "ORDER BY id", (rede_id, feicoes))
    elementos += [{"feicao_id": str(r["id"]), "terminal": None} for r in cur.fetchall()]
    return elementos


# --- regras -----------------------------------------------------------------------------------------------

def _adjacencia(grafo: dict) -> dict:
    adj = defaultdict(list)
    for i, a in enumerate(grafo["arestas"]):
        adj[a["de"]].append(i)
        if a["para"] != a["de"]:
            adj[a["para"]].append(i)
    return adj


def componentes(grafo: dict) -> int:
    """Quantos componentes conexos o grafo tem. A cláusula do portão compara este número antes e depois da
    redução: reduzir junção de passagem não pode partir a rede."""
    adj = _adjacencia(grafo)
    vistos, total = set(), 0
    for chave in sorted(grafo["nos"]):
        if chave in vistos:
            continue
        total += 1
        fila = deque([chave])
        vistos.add(chave)
        while fila:
            atual = fila.popleft()
            for i in adj[atual]:
                a = grafo["arestas"][i]
                for outro in (a["de"], a["para"]):
                    if outro not in vistos and outro in grafo["nos"]:
                        vistos.add(outro)
                        fila.append(outro)
    return total


def _remover_tipos(grafo: dict, tipos: list[str]) -> dict:
    alvo = {t for t in tipos if t}
    fora = {c for c, n in grafo["nos"].items() if n["tipo_chave"] in alvo}
    if not fora:
        return {"regra": "remover_tipos", "tipos": sorted(alvo), "nos_removidos": 0, "arestas_removidas": 0}
    antes_arestas = len(grafo["arestas"])
    for c in fora:
        del grafo["nos"][c]
    grafo["arestas"] = [a for a in grafo["arestas"] if a["de"] not in fora and a["para"] not in fora]
    return {"regra": "remover_tipos", "tipos": sorted(alvo), "nos_removidos": len(fora),
            "arestas_removidas": antes_arestas - len(grafo["arestas"])}


def _colapsar_conteiner(grafo: dict) -> dict:
    """Os terminais do mesmo dispositivo viram um nó só (`papel='conteiner'`). A aresta interna do dispositivo
    vira laço e sai; as arestas externas são religadas ao nó colapsado."""
    por_feicao = defaultdict(list)
    for c, n in grafo["nos"].items():
        if n["papel"] == "terminal" and n["feicao_id"]:
            por_feicao[n["feicao_id"]].append(c)
    troca: dict[str, str] = {}
    colapsados = 0
    for feicao_id, chaves in sorted(por_feicao.items()):
        if len(chaves) < 2:
            continue
        chaves = sorted(chaves)
        modelo = grafo["nos"][chaves[0]]
        nova = f"conteiner:{feicao_id}"
        grafo["nos"][nova] = {**modelo, "chave": nova, "papel": "conteiner", "terminal_num": None,
                              "agregados": len(chaves)}
        for c in chaves:
            troca[c] = nova
            del grafo["nos"][c]
        colapsados += 1
    if not troca:
        return {"regra": "colapsar_conteiner", "conteineres": 0, "nos_removidos": 0, "arestas_removidas": 0}
    antes = len(grafo["arestas"])
    novas = []
    for a in grafo["arestas"]:
        de, para = troca.get(a["de"], a["de"]), troca.get(a["para"], a["para"])
        if de == para:
            continue  # laço interno do próprio dispositivo: ele virou o nó
        novas.append({**a, "de": de, "para": para})
    grafo["arestas"] = novas
    removidos = sum(len(v) for v in por_feicao.values() if len(v) >= 2) - colapsados
    return {"regra": "colapsar_conteiner", "conteineres": colapsados, "nos_removidos": removidos,
            "arestas_removidas": antes - len(grafo["arestas"])}


def _reduzir_juncao_de_passagem(grafo: dict, tipos: list[str] | None = None) -> dict:
    """Remove nó de PASSAGEM (grau 2) e funde as duas arestas dele numa só.

    Preserva a conectividade por construção: o nó só sai quando as duas arestas viram uma aresta entre os dois
    vizinhos. Duas situações em que o nó FICA, de propósito:
      * os dois vizinhos são o MESMO nó — reduzir apagaria a aresta de um laço (a rede em anel deixaria de
        parecer anel), e é exatamente o caso da refutação deste item;
      * o nó tem feição própria e `tipos` foi declarado sem o tipo dele — a regra da fonte reduz junção, não
        dispositivo. Sem `tipos`, reduz só nó de conexão (o vértice sem feição), que é o caso puro de
        "passagem".

    A varredura é INCREMENTAL (fila de candidatos, adjacência mantida a cada fusão): reduzir refazendo a
    adjacência a cada passo custaria uma passada pelo grafo inteiro por nó removido, e um alimentador de
    milhares de nós não caberia nos 10 s do portão."""
    alvo = {t for t in (tipos or []) if t}
    arestas = {a["chave"]: dict(a) for a in grafo["arestas"]}
    adj: dict[str, set] = defaultdict(set)
    for chave, a in arestas.items():
        adj[a["de"]].add(chave)
        adj[a["para"]].add(chave)

    def _reduzivel(chave_no: str) -> bool:
        no = grafo["nos"].get(chave_no)
        if no is None:
            return False
        return no["papel"] == "conexao" or no["tipo_chave"] in alvo

    fila = deque(sorted(c for c in grafo["nos"] if _reduzivel(c)))
    na_fila = set(fila)
    reduzidos = fundidas = 0
    while fila:
        chave = fila.popleft()
        na_fila.discard(chave)
        if not _reduzivel(chave) or len(adj[chave]) != 2:
            continue
        ca, cb = sorted(adj[chave])
        a, b = arestas[ca], arestas[cb]
        v1 = a["para"] if a["de"] == chave else a["de"]
        v2 = b["para"] if b["de"] == chave else b["de"]
        if v1 == chave or v2 == chave or v1 == v2:
            continue
        nova_chave = f"reduzida:{reduzidos}:{ca}"
        nova = {
            "chave": nova_chave, "de": v1, "para": v2, "origem": "reduzida",
            "feicoes": sorted(set(a["feicoes"]) | set(b["feicoes"])),
            "tipo_id": a["tipo_id"] or b["tipo_id"], "tipo_chave": a["tipo_chave"] or b["tipo_chave"],
            "agregadas": a["agregadas"] + b["agregadas"],
            "comprimento_m": (a["comprimento_m"] or 0.0) + (b["comprimento_m"] or 0.0),
        }
        for c in (ca, cb):
            velha = arestas.pop(c)
            adj[velha["de"]].discard(c)
            adj[velha["para"]].discard(c)
        arestas[nova_chave] = nova
        adj[v1].add(nova_chave)
        adj[v2].add(nova_chave)
        del grafo["nos"][chave]
        adj.pop(chave, None)
        reduzidos += 1
        fundidas += 2
        for v in (v1, v2):
            if v not in na_fila and _reduzivel(v):
                fila.append(v)
                na_fila.add(v)
    grafo["arestas"] = [arestas[c] for c in sorted(arestas)]
    return {"regra": "reduzir_juncao_de_passagem", "tipos": sorted(alvo), "nos_removidos": reduzidos,
            "arestas_fundidas": fundidas}


def aplicar_regras(grafo: dict, regras: list[dict]) -> list[dict]:
    """Aplica as regras do modelo NA ORDEM declarada (a fonte também é ordenada: uma regra vê o resultado da
    anterior). Regra desconhecida é recusada em vez de ignorada em silêncio."""
    relatorio = []
    for r in regras or []:
        nome = (r or {}).get("regra")
        if nome not in REGRAS:
            raise ErroAPI(422, "regra_desconhecida", f"regra deve ser uma de {REGRAS}")
        if nome == "remover_tipos":
            relatorio.append(_remover_tipos(grafo, list(r.get("tipos") or [])))
        elif nome == "colapsar_conteiner":
            relatorio.append(_colapsar_conteiner(grafo))
        else:
            relatorio.append(_reduzir_juncao_de_passagem(grafo, list(r.get("tipos") or [])))
    return relatorio


# --- layouts ----------------------------------------------------------------------------------------------

def _raizes(grafo: dict, adj: dict) -> list[str]:
    """Por onde a árvore começa: o nó de maior grau entre os de menor `terminal_num` não é critério estável, e
    escolher "o primeiro" faria o desenho mudar sozinho. A raiz é o nó de MENOR grau (ponta da rede) com o
    menor `chave` dentro de cada componente — determinístico e, num alimentador, cai no controlador ou numa
    ponta, que é onde o operador espera a origem."""
    vistos, raizes = set(), []
    for chave in sorted(grafo["nos"]):
        if chave in vistos:
            continue
        componente, fila = [], deque([chave])
        vistos.add(chave)
        while fila:
            atual = fila.popleft()
            componente.append(atual)
            for i in adj[atual]:
                a = grafo["arestas"][i]
                for outro in (a["de"], a["para"]):
                    if outro not in vistos and outro in grafo["nos"]:
                        vistos.add(outro)
                        fila.append(outro)
        raizes.append(min(componente, key=lambda c: (len(adj[c]), c)))
    return raizes


def _arvore(grafo: dict) -> tuple[dict, dict, list[str]]:
    """Árvore geradora por largura: pai de cada nó, filhos por pai e a ordem de visita. As arestas que sobram
    (as que fecham laço) continuam no grafo — o layout não apaga aresta nenhuma; elas só não guiam a posição."""
    adj = _adjacencia(grafo)
    pai: dict[str, str | None] = {}
    filhos: dict[str, list] = defaultdict(list)
    ordem: list[str] = []
    for raiz in _raizes(grafo, adj):
        pai[raiz] = None
        fila = deque([raiz])
        ordem.append(raiz)
        while fila:
            atual = fila.popleft()
            vizinhos = []
            for i in adj[atual]:
                a = grafo["arestas"][i]
                outro = a["para"] if a["de"] == atual else a["de"]
                if outro in grafo["nos"]:
                    vizinhos.append(outro)
            for outro in sorted(set(vizinhos)):
                if outro in pai:
                    continue
                pai[outro] = atual
                filhos[atual].append(outro)
                ordem.append(outro)
                fila.append(outro)
    return pai, filhos, ordem


def _profundidade(pai: dict, ordem: list[str]) -> dict:
    prof = {}
    for chave in ordem:
        p = pai[chave]
        prof[chave] = 0 if p is None else prof[p] + 1
    return prof


def _layout_arvore_inteligente(grafo: dict) -> None:
    """Árvore em camadas: x pela profundidade, y por passeio em profundidade (folha ocupa a próxima faixa
    livre, nó interno fica na média dos filhos). É o "smart tree" da fonte na leitura que importa: quem lê o
    esquema vê o caminho da fonte até a ponta sem cruzar linha à toa."""
    pai, filhos, ordem = _arvore(grafo)
    prof = _profundidade(pai, ordem)
    proximo = 0.0
    y: dict[str, float] = {}
    for raiz in [c for c in ordem if pai[c] is None]:
        pilha = [(raiz, False)]
        while pilha:
            chave, voltando = pilha.pop()
            meus = filhos.get(chave, [])
            if not meus:
                y[chave] = proximo
                proximo += ESPACO
            elif voltando:
                y[chave] = sum(y[f] for f in meus) / len(meus)
            else:
                pilha.append((chave, True))
                for f in reversed(meus):
                    pilha.append((f, False))
        proximo += ESPACO
    for chave, no in grafo["nos"].items():
        no["x"] = prof.get(chave, 0) * ESPACO * 2
        no["y"] = y.get(chave, 0.0)


def _layout_radial(grafo: dict) -> None:
    """Anéis concêntricos por profundidade. O raio de cada anel é o maior entre a distância nominal e o raio
    que dá arco de uma distância nominal para todos os nós daquele anel — sem isso o anel de fora amontoa."""
    pai, filhos, ordem = _arvore(grafo)
    prof = _profundidade(pai, ordem)
    por_nivel = defaultdict(list)
    for chave in ordem:
        por_nivel[prof[chave]].append(chave)
    for nivel, chaves in por_nivel.items():
        if nivel == 0:
            for i, chave in enumerate(chaves):
                grafo["nos"][chave]["x"] = i * ESPACO * 4
                grafo["nos"][chave]["y"] = 0.0
            continue
        raio = max(nivel * ESPACO * 2, len(chaves) * ESPACO / (2 * math.pi) + ESPACO)
        for i, chave in enumerate(chaves):
            angulo = 2 * math.pi * i / len(chaves)
            grafo["nos"][chave]["x"] = raio * math.cos(angulo)
            grafo["nos"][chave]["y"] = raio * math.sin(angulo)


def _layout_linha_principal(grafo: dict) -> None:
    """Linha principal (main line): o caminho mais longo da árvore vira o tronco, na horizontal, e cada ramo
    sai dele para cima e para baixo alternadamente. É o desenho que um alimentador pede: o tronco de média
    tensão em linha reta e os ramais pendurados."""
    pai, filhos, ordem = _arvore(grafo)
    prof = _profundidade(pai, ordem)
    if not ordem:
        return
    folha = max(ordem, key=lambda c: (prof[c], c))
    tronco, atual = [], folha
    while atual is not None:
        tronco.append(atual)
        atual = pai[atual]
    tronco.reverse()
    no_tronco = {c: i for i, c in enumerate(tronco)}
    faixa = defaultdict(int)
    for chave in ordem:
        if chave in no_tronco:
            grafo["nos"][chave]["x"] = no_tronco[chave] * ESPACO * 2
            grafo["nos"][chave]["y"] = 0.0
            continue
        p = pai[chave]
        base_x = grafo["nos"][p]["x"] if p else 0.0
        ancora = p if p in no_tronco else chave
        faixa[ancora] += 1
        passo = faixa[ancora]
        sinal = 1 if passo % 2 else -1
        grafo["nos"][chave]["x"] = base_x + ESPACO * 2
        grafo["nos"][chave]["y"] = (grafo["nos"][p]["y"] if p else 0.0) + sinal * ESPACO * (1 + passo // 2)


def _layout_geografico(grafo: dict) -> None:
    """Posição geográfica levada para o espaço do diagrama: mesma forma do mapa, escala própria. É o layout
    que serve de ponte — quem duvida do esquema compara com este e vê a mesma rede."""
    pontos = [(n["lon"], n["lat"]) for n in grafo["nos"].values() if n["lon"] is not None]
    if not pontos:
        _layout_grade(grafo)
        return
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    larg = max(max(lons) - min(lons), 1e-9)
    alt = max(max(lats) - min(lats), 1e-9)
    lado = ESPACO * max(2.0, math.sqrt(max(len(grafo["nos"]), 1)) * 2)
    escala = lado / max(larg, alt)
    for n in grafo["nos"].values():
        n["x"] = ((n["lon"] or min(lons)) - min(lons)) * escala
        n["y"] = ((n["lat"] or min(lats)) - min(lats)) * escala


def _layout_grade(grafo: dict) -> None:
    """Grade: ordem de visita da árvore, quadrado o mais fechado possível. Não conta história nenhuma sobre a
    rede — serve de conferência (nenhum nó some) e de plano B quando não há geometria."""
    _pai, _filhos, ordem = _arvore(grafo)
    colunas = max(1, int(math.ceil(math.sqrt(max(len(ordem), 1)))))
    for i, chave in enumerate(ordem):
        grafo["nos"][chave]["x"] = (i % colunas) * ESPACO
        grafo["nos"][chave]["y"] = (i // colunas) * ESPACO


def _layout_forca_dirigida(grafo: dict, iteracoes: int = 50) -> None:
    """Força dirigida (Fruchterman-Reingold) com semente determinística: o MESMO grafo dá SEMPRE o mesmo
    desenho, porque a posição inicial vem do sha256 da chave do nó, não de um gerador aleatório."""
    chaves = sorted(grafo["nos"])
    n = len(chaves)
    if n == 0:
        return
    lado = ESPACO * math.sqrt(n) * 2
    k = lado / math.sqrt(n)
    pos = {}
    for chave in chaves:
        semente = hashlib.sha256(chave.encode("utf-8")).digest()
        pos[chave] = [int.from_bytes(semente[:4], "big") / 2**32 * lado,
                      int.from_bytes(semente[4:8], "big") / 2**32 * lado]
    arestas = [(a["de"], a["para"]) for a in grafo["arestas"] if a["de"] != a["para"]]
    temperatura = lado / 10
    for _ in range(iteracoes):
        desl = {c: [0.0, 0.0] for c in chaves}
        for i, c1 in enumerate(chaves):
            for c2 in chaves[i + 1:]:
                dx = pos[c1][0] - pos[c2][0]
                dy = pos[c1][1] - pos[c2][1]
                d = math.hypot(dx, dy) or 1e-6
                f = k * k / d
                desl[c1][0] += dx / d * f
                desl[c1][1] += dy / d * f
                desl[c2][0] -= dx / d * f
                desl[c2][1] -= dy / d * f
        for de, para in arestas:
            dx = pos[de][0] - pos[para][0]
            dy = pos[de][1] - pos[para][1]
            d = math.hypot(dx, dy) or 1e-6
            f = d * d / k
            desl[de][0] -= dx / d * f
            desl[de][1] -= dy / d * f
            desl[para][0] += dx / d * f
            desl[para][1] += dy / d * f
        for c in chaves:
            dx, dy = desl[c]
            d = math.hypot(dx, dy) or 1e-6
            passo = min(d, temperatura)
            pos[c][0] += dx / d * passo
            pos[c][1] += dy / d * passo
        temperatura *= 0.95
    for c in chaves:
        grafo["nos"][c]["x"], grafo["nos"][c]["y"] = pos[c][0], pos[c][1]


_FUNCOES_LAYOUT = {
    "arvore_inteligente": _layout_arvore_inteligente,
    "radial": _layout_radial,
    "linha_principal": _layout_linha_principal,
    "geografico": _layout_geografico,
    "grade": _layout_grade,
    "forca_dirigida": _layout_forca_dirigida,
}

# acima deste número de nós, a força dirigida (que compara todos contra todos a cada rodada) sai de cena e o
# desenho cai na grade: 2.000 nós dariam 2 milhões de pares por rodada e o pedido nunca voltaria.
FORCA_DIRIGIDA_NOS_MAXIMO = 200


def _resolver_sobreposicao(grafo: dict, minimo: float = SEPARACAO_MINIMA) -> int:
    """Empurra nós até que nenhum par fique a menos de `minimo`. Varredura em GRADE de célula `minimo`: só se
    comparam nós de células vizinhas, então o custo é proporcional ao número de nós, não ao de pares.

    O empurrão é em espiral quadrada de passo `minimo`, na ordem determinística das chaves — o mesmo grafo dá
    sempre o mesmo desenho."""
    celulas: dict[tuple, list] = defaultdict(list)
    movidos = 0

    def _celula(x, y):
        return (int(math.floor(x / minimo)), int(math.floor(y / minimo)))

    def _livre(x, y):
        cx, cy = _celula(x, y)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for (ox, oy) in celulas.get((cx + i, cy + j), ()):
                    if math.hypot(x - ox, y - oy) < minimo:
                        return False
        return True

    for chave in sorted(grafo["nos"]):
        no = grafo["nos"][chave]
        x, y = float(no["x"]), float(no["y"])
        if not _livre(x, y):
            movidos += 1
            passo = 1
            while not _livre(x, y):
                anel = [(dx, dy) for dx in range(-passo, passo + 1) for dy in range(-passo, passo + 1)
                        if max(abs(dx), abs(dy)) == passo]
                achou = False
                for dx, dy in anel:
                    cx, cy = float(no["x"]) + dx * minimo, float(no["y"]) + dy * minimo
                    if _livre(cx, cy):
                        x, y = cx, cy
                        achou = True
                        break
                if achou:
                    break
                passo += 1
        no["x"], no["y"] = x, y
        celulas[_celula(x, y)].append((x, y))
    return movidos


def aplicar_layout(grafo: dict, layout: str) -> dict:
    """Posiciona os nós e garante a separação mínima. NENHUM nó ou aresta é criado ou apagado aqui: o número
    de um e de outro é conferido antes e depois, e a diferença é erro do programa, não do desenho."""
    if layout not in LAYOUTS:
        raise ErroAPI(422, "layout_desconhecido", f"layout deve ser um de {LAYOUTS}")
    efetivo = layout
    aviso = None
    if layout == "forca_dirigida" and len(grafo["nos"]) > FORCA_DIRIGIDA_NOS_MAXIMO:
        efetivo = "grade"
        aviso = (f"força dirigida só até {FORCA_DIRIGIDA_NOS_MAXIMO} nós; este diagrama tem "
                 f"{len(grafo['nos'])} e foi desenhado em grade")
    antes = (len(grafo["nos"]), len(grafo["arestas"]))
    inicio = time.perf_counter()
    _FUNCOES_LAYOUT[efetivo](grafo)
    movidos = _resolver_sobreposicao(grafo)
    depois = (len(grafo["nos"]), len(grafo["arestas"]))
    if antes != depois:
        raise RuntimeError(f"o layout {efetivo} mudou o grafo: {antes} -> {depois}")
    return {"layout": layout, "layout_efetivo": efetivo, "nos_movidos": movidos, "aviso": aviso,
            "duracao_ms": int((time.perf_counter() - inicio) * 1000)}


DISTANCIA_VIZINHA = 2 * SEPARACAO_MINIMA


def menor_distancia(grafo: dict, raio: float = DISTANCIA_VIZINHA) -> float | None:
    """A menor distância entre dois nós PRÓXIMOS — próximos = a até `raio` unidades um do outro.

    Devolve `None` quando nenhum par está a menos de `raio`: o desenho está folgado e não há o que medir.
    Isto NÃO é "a menor distância do grafo": a varredura é em grade de célula `raio` com as 8 células
    vizinhas, então ela enxerga todo par a até `raio` e ignora o resto. É de propósito — a cláusula do portão
    pergunta se algum par ficou perto demais, não qual é o par mais próximo de um desenho esparso, e a
    resposta exata para a segunda pergunta custaria comparar todos contra todos."""
    celulas: dict[tuple, list] = defaultdict(list)
    menor = None
    for chave in sorted(grafo["nos"]):
        no = grafo["nos"][chave]
        x, y = float(no["x"]), float(no["y"])
        cx, cy = int(math.floor(x / raio)), int(math.floor(y / raio))
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for (ox, oy) in celulas.get((cx + i, cy + j), ()):
                    d = math.hypot(x - ox, y - oy)
                    if menor is None or d < menor:
                        menor = d
        celulas[(cx, cy)].append((x, y))
    return menor


def pares_sobrepostos(grafo: dict, minimo: float = SEPARACAO_MINIMA) -> int:
    """Quantos pares de nós estão a menos de `minimo` — a cláusula pede ZERO."""
    celulas: dict[tuple, list] = defaultdict(list)
    total = 0
    for chave in sorted(grafo["nos"]):
        no = grafo["nos"][chave]
        x, y = float(no["x"]), float(no["y"])
        cx, cy = int(math.floor(x / minimo)), int(math.floor(y / minimo))
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for (ox, oy) in celulas.get((cx + i, cy + j), ()):
                    if math.hypot(x - ox, y - oy) < minimo:
                        total += 1
        celulas[(cx, cy)].append((x, y))
    return total


def _menor_arredondada(grafo: dict) -> float | None:
    """`menor_distancia` arredondada para o resumo gravado; `None` quando nenhum par está próximo."""
    menor = menor_distancia(grafo)
    return round(menor, 6) if menor is not None else None


# --- modelos (templates) ----------------------------------------------------------------------------------

def _validar_regras(regras) -> list[dict]:
    if regras is None:
        return []
    if not isinstance(regras, list):
        raise ErroAPI(422, "regras_invalidas", "regras tem de ser uma lista")
    limpas = []
    for r in regras:
        if not isinstance(r, dict) or r.get("regra") not in REGRAS:
            raise ErroAPI(422, "regra_desconhecida", f"regra deve ser uma de {REGRAS}")
        item = {"regra": r["regra"]}
        tipos = r.get("tipos")
        if tipos is not None:
            if not isinstance(tipos, list) or not all(isinstance(t, str) for t in tipos):
                raise ErroAPI(422, "regras_invalidas", "tipos tem de ser uma lista de códigos de tipo")
            item["tipos"] = tipos
        limpas.append(item)
    return limpas


def definir_modelo(cur, tenant_id: int, rede_id: str, codigo: str, nome: str, regras, layout: str) -> dict:
    """Declara (ou redeclara) um modelo de diagrama da rede. O código é único na rede e não pode roubar o nome
    de um modelo embutido: quem quiser mudar o embutido cria outro código e diz por quê."""
    codigo = (codigo or "").strip()
    if codigo in MODELOS_PADRAO:
        raise ErroAPI(422, "modelo_reservado",
                      f"'{codigo}' é um modelo embutido; escolha outro código para o seu")
    if layout not in LAYOUTS:
        raise ErroAPI(422, "layout_desconhecido", f"layout deve ser um de {LAYOUTS}")
    limpas = _validar_regras(regras)
    cur.execute(
        "INSERT INTO plat.rede_diagrama_modelo(tenant_id, rede_id, codigo, nome, regras, layout) "
        "VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s) "
        "ON CONFLICT (rede_id, codigo) DO UPDATE SET nome = EXCLUDED.nome, regras = EXCLUDED.regras, "
        "  layout = EXCLUDED.layout "
        "RETURNING id, codigo, nome, regras, layout, criado_em",
        (tenant_id, rede_id, codigo, nome, json.dumps(limpas), layout),
    )
    r = cur.fetchone()
    return {"id": str(r["id"]), "codigo": r["codigo"], "nome": r["nome"], "regras": r["regras"],
            "layout": r["layout"], "embutido": False, "criado_em": r["criado_em"]}


def listar_modelos(cur, rede_id: str) -> list[dict]:
    """Os modelos embutidos e os do inquilino, na mesma lista — quem escolhe na tela não precisa saber de onde
    cada um veio, mas a resposta diz (`embutido`)."""
    itens = [{"id": None, "codigo": c, "nome": m["nome"], "regras": m["regras"], "layout": m["layout"],
              "embutido": True, "criado_em": None}
             for c, m in sorted(MODELOS_PADRAO.items())]
    cur.execute(
        "SELECT id, codigo, nome, regras, layout, criado_em FROM plat.rede_diagrama_modelo "
        "WHERE rede_id = %s::uuid ORDER BY codigo",
        (rede_id,),
    )
    itens += [{"id": str(r["id"]), "codigo": r["codigo"], "nome": r["nome"], "regras": r["regras"],
               "layout": r["layout"], "embutido": False, "criado_em": r["criado_em"]}
              for r in cur.fetchall()]
    return itens


def _modelo(cur, rede_id: str, codigo: str) -> dict:
    cur.execute(
        "SELECT id, codigo, nome, regras, layout FROM plat.rede_diagrama_modelo "
        "WHERE rede_id = %s::uuid AND codigo = %s",
        (rede_id, codigo),
    )
    r = cur.fetchone()
    if r is not None:
        return {"id": str(r["id"]), "codigo": r["codigo"], "nome": r["nome"],
                "regras": list(r["regras"] or []), "layout": r["layout"]}
    embutido = MODELOS_PADRAO.get(codigo)
    if embutido is None:
        raise ErroAPI(404, "modelo_inexistente",
                      f"esta rede não tem o modelo de diagrama '{codigo}'")
    return {"id": None, "codigo": codigo, "nome": embutido["nome"],
            "regras": [dict(x) for x in embutido["regras"]], "layout": embutido["layout"]}


# --- gerar, gravar, ler -----------------------------------------------------------------------------------

def _elementos_da_origem(cur, tenant_id: int, rede_id: str, origem: dict) -> tuple[list[dict], dict]:
    tipo = (origem or {}).get("tipo")
    if tipo not in ORIGENS:
        raise ErroAPI(422, "origem_invalida", f"origem.tipo deve ser um de {ORIGENS}")
    if tipo == "subrede":
        from app.rede_utilidades import subredes

        s = subredes.por_nome(cur, rede_id, (origem.get("subrede") or "").strip(), origem.get("tier"))
        elementos = elementos_da_subrede(cur, rede_id, str(s["id"]))
        if not elementos:
            raise ErroAPI(409, "subrede_nunca_atualizada",
                          "esta subrede ainda não foi atualizada: atualize antes de gerar o diagrama")
        return elementos, {"tipo": "subrede", "subrede": s["nome"], "tier": s["tier"],
                           "subrede_id": str(s["id"])}
    if tipo == "tracado":
        modo = origem.get("tracado") or "subrede"
        resultado = tracado.tracar(cur, tenant_id, rede_id, modo, list(origem.get("pontos_partida") or []),
                                   list(origem.get("barreiras") or []))
        if not resultado["elementos"]:
            raise ErroAPI(409, "tracado_vazio", "este traçado não alcançou elemento nenhum")
        return resultado["elementos"], {"tipo": "tracado", "tracado": modo,
                                        "pontos_partida": origem.get("pontos_partida") or [],
                                        "barreiras": origem.get("barreiras") or [],
                                        "elementos": resultado["contagem"]}
    feicoes = [str(f) for f in (origem.get("feicoes") or [])]
    elementos = elementos_da_selecao(cur, rede_id, feicoes)
    if not elementos:
        raise ErroAPI(409, "selecao_vazia", "nenhuma feição desta seleção existe nesta rede")
    return elementos, {"tipo": "selecao", "feicoes": feicoes}


def gerar(cur, tenant_id: int, rede_id: str, nome: str, origem: dict, modelo_codigo: str = "basico",
          layout: str | None = None) -> dict:
    """Gera (ou regenera, pelo mesmo nome) o diagrama: recorte → regras do modelo → layout → gravação.

    Regerar pelo mesmo nome APAGA os nós e arestas antigos e escreve os novos, mantendo o identificador do
    diagrama — é o que faz o link que alguém guardou continuar valendo depois de a rede mudar."""
    nome = (nome or "").strip()
    if not nome:
        raise ErroAPI(422, "nome_obrigatorio", "informe o nome do diagrama")
    inicio = time.perf_counter()
    modelo = _modelo(cur, rede_id, modelo_codigo)
    layout = layout or modelo["layout"]
    if layout not in LAYOUTS:
        raise ErroAPI(422, "layout_desconhecido", f"layout deve ser um de {LAYOUTS}")

    elementos, origem_gravada = _elementos_da_origem(cur, tenant_id, rede_id, origem)
    t_grafo = time.perf_counter()
    grafo = _grafo_de_elementos(cur, rede_id, elementos)
    if not grafo["nos"]:
        raise ErroAPI(409, "diagrama_vazio",
                      "este recorte não tem nó de topologia: a topologia está desatualizada?")
    bruto = {"nos": len(grafo["nos"]), "arestas": len(grafo["arestas"]),
             "componentes": componentes(grafo)}
    t_regras = time.perf_counter()
    relatorio = aplicar_regras(grafo, modelo["regras"])
    t_layout = time.perf_counter()
    medida_layout = aplicar_layout(grafo, layout)
    fim_calculo = time.perf_counter()

    resumo = {
        "bruto": bruto,
        "nos": len(grafo["nos"]), "arestas": len(grafo["arestas"]), "componentes": componentes(grafo),
        "regras": relatorio, "layout": medida_layout,
        "pares_sobrepostos": pares_sobrepostos(grafo),
        "menor_distancia_proxima": _menor_arredondada(grafo),
        "elementos_no_recorte": len(elementos),
        "duracao_ms": {
            "recorte": int((t_grafo - inicio) * 1000), "grafo": int((t_regras - t_grafo) * 1000),
            "regras": int((t_layout - t_regras) * 1000), "layout": int((fim_calculo - t_layout) * 1000),
        },
    }

    cur.execute(
        "INSERT INTO plat.rede_diagrama(tenant_id, rede_id, nome, modelo_id, modelo_codigo, layout, origem, "
        "  estado, resumo, gerado_em) "
        "VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s, %s::jsonb, 'consistente', %s::jsonb, now()) "
        "ON CONFLICT (rede_id, nome) DO UPDATE SET modelo_id = EXCLUDED.modelo_id, "
        "  modelo_codigo = EXCLUDED.modelo_codigo, layout = EXCLUDED.layout, origem = EXCLUDED.origem, "
        "  estado = 'consistente', resumo = EXCLUDED.resumo, gerado_em = now() "
        "RETURNING id, gerado_em",
        (tenant_id, rede_id, nome, modelo["id"], modelo["codigo"], layout, json.dumps(origem_gravada),
         json.dumps(resumo)),
    )
    linha = cur.fetchone()
    diagrama_id = str(linha["id"])
    _gravar_grafo(cur, tenant_id, rede_id, diagrama_id, grafo)
    resumo["duracao_ms"]["total"] = int((time.perf_counter() - inicio) * 1000)
    cur.execute("UPDATE plat.rede_diagrama SET resumo = %s::jsonb WHERE id = %s::uuid",
                (json.dumps(resumo), diagrama_id))
    return {"id": diagrama_id, "nome": nome, "modelo": modelo["codigo"], "layout": layout,
            "estado": "consistente", "origem": origem_gravada, "resumo": resumo,
            "gerado_em": linha["gerado_em"]}


def _gravar_grafo(cur, tenant_id: int, rede_id: str, diagrama_id: str, grafo: dict) -> None:
    cur.execute("DELETE FROM plat.rede_diagrama_aresta WHERE diagrama_id = %s::uuid", (diagrama_id,))
    cur.execute("DELETE FROM plat.rede_diagrama_no WHERE diagrama_id = %s::uuid", (diagrama_id,))
    chaves = sorted(grafo["nos"])
    if not chaves:
        return
    gabarito, valores = [], []
    for chave in chaves:
        n = grafo["nos"][chave]
        gabarito.append("(%s, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s)")
        valores += [tenant_id, rede_id, diagrama_id, chave, n["papel"], n["feicao_id"], n["terminal_num"],
                    n["tipo_id"], n["tipo_chave"], n["rotulo"], float(n["x"]), float(n["y"]),
                    n["lon"], n["lat"], int(n["agregados"])]
    cur.execute(
        "INSERT INTO plat.rede_diagrama_no(tenant_id, rede_id, diagrama_id, chave, papel, feicao_id, "
        "terminal_num, tipo_id, tipo_chave, rotulo, x, y, lon, lat, agregados) VALUES "
        + ", ".join(gabarito) + " RETURNING id, chave",
        valores,
    )
    por_chave = {r["chave"]: str(r["id"]) for r in cur.fetchall()}
    arestas = [a for a in grafo["arestas"] if a["de"] in por_chave and a["para"] in por_chave]
    if not arestas:
        return
    gabarito, valores = [], []
    for a in sorted(arestas, key=lambda x: x["chave"]):
        gabarito.append("(%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s)")
        valores += [tenant_id, rede_id, diagrama_id, a["chave"], por_chave[a["de"]], por_chave[a["para"]],
                    a["origem"], json.dumps(a["feicoes"]), a["tipo_chave"], int(a["agregadas"]),
                    a["comprimento_m"]]
    cur.execute(
        "INSERT INTO plat.rede_diagrama_aresta(tenant_id, rede_id, diagrama_id, chave, no_de_id, no_para_id, "
        "origem, feicoes, tipo_chave, agregadas, comprimento_m) VALUES " + ", ".join(gabarito),
        valores,
    )


def _cabecalho(cur, rede_id: str, diagrama_id: str) -> dict:
    cur.execute(
        "SELECT id, nome, modelo_codigo, layout, origem, estado, resumo, gerado_em, criado_em "
        "FROM plat.rede_diagrama WHERE rede_id = %s::uuid AND id = %s::uuid",
        (rede_id, diagrama_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "diagrama_inexistente", "esta rede não tem diagrama com esse identificador")
    return {"id": str(r["id"]), "nome": r["nome"], "modelo": r["modelo_codigo"], "layout": r["layout"],
            "origem": r["origem"], "estado": r["estado"], "resumo": r["resumo"],
            "gerado_em": r["gerado_em"], "criado_em": r["criado_em"]}


def ler(cur, rede_id: str, diagrama_id: str) -> dict:
    """O diagrama inteiro: cabeçalho, nós (com x,y no espaço do diagrama e a âncora de volta ao mapa) e
    arestas. É esta resposta que a tela desenha e que a exportação transforma em SVG ou PNG."""
    doc = _cabecalho(cur, rede_id, diagrama_id)
    cur.execute(
        "SELECT id, chave, papel, feicao_id, terminal_num, tipo_chave, rotulo, x, y, lon, lat, agregados "
        "FROM plat.rede_diagrama_no WHERE diagrama_id = %s::uuid ORDER BY chave",
        (diagrama_id,),
    )
    doc["nos"] = [{"id": str(r["id"]), "chave": r["chave"], "papel": r["papel"],
                   "feicao_id": str(r["feicao_id"]) if r["feicao_id"] else None,
                   "terminal": r["terminal_num"], "tipo": r["tipo_chave"], "rotulo": r["rotulo"],
                   "x": r["x"], "y": r["y"], "lon": r["lon"], "lat": r["lat"],
                   "agregados": r["agregados"]} for r in cur.fetchall()]
    cur.execute(
        "SELECT a.id, a.chave, a.origem, a.feicoes, a.tipo_chave, a.agregadas, a.comprimento_m, "
        "       de.chave AS de, para.chave AS para, de.x AS x1, de.y AS y1, para.x AS x2, para.y AS y2 "
        "FROM plat.rede_diagrama_aresta a "
        "JOIN plat.rede_diagrama_no de ON de.id = a.no_de_id "
        "JOIN plat.rede_diagrama_no para ON para.id = a.no_para_id "
        "WHERE a.diagrama_id = %s::uuid ORDER BY a.chave",
        (diagrama_id,),
    )
    doc["arestas"] = [{"id": str(r["id"]), "chave": r["chave"], "de": r["de"], "para": r["para"],
                       "origem": r["origem"], "feicoes": list(r["feicoes"] or []), "tipo": r["tipo_chave"],
                       "agregadas": r["agregadas"], "comprimento_m": r["comprimento_m"],
                       "x1": r["x1"], "y1": r["y1"], "x2": r["x2"], "y2": r["y2"]}
                      for r in cur.fetchall()]
    return doc


def listar(cur, rede_id: str, limite: int = 200) -> list[dict]:
    cur.execute(
        "SELECT d.id, d.nome, d.modelo_codigo, d.layout, d.origem, d.estado, d.resumo, d.gerado_em, "
        "       count(n.id) AS nos "
        "FROM plat.rede_diagrama d LEFT JOIN plat.rede_diagrama_no n ON n.diagrama_id = d.id "
        "WHERE d.rede_id = %s::uuid GROUP BY d.id ORDER BY d.nome LIMIT %s",
        (rede_id, limite),
    )
    return [{"id": str(r["id"]), "nome": r["nome"], "modelo": r["modelo_codigo"], "layout": r["layout"],
             "origem": r["origem"], "estado": r["estado"], "resumo": r["resumo"],
             "gerado_em": r["gerado_em"], "nos": r["nos"]} for r in cur.fetchall()]


def apagar(cur, rede_id: str, diagrama_id: str) -> None:
    _cabecalho(cur, rede_id, diagrama_id)
    cur.execute("DELETE FROM plat.rede_diagrama WHERE rede_id = %s::uuid AND id = %s::uuid",
                (rede_id, diagrama_id))


def reaplicar_layout(cur, rede_id: str, diagrama_id: str, layout: str) -> dict:
    """Troca o layout SEM refazer o recorte nem as regras: os mesmos nós e as mesmas arestas ganham posições
    novas. É o que a tela faz quando quem lê troca o desenho no seletor, e é barato porque nada volta ao
    traçado. O estado de consistência não muda: mudar de desenho não conserta diagrama velho."""
    if layout not in LAYOUTS:
        raise ErroAPI(422, "layout_desconhecido", f"layout deve ser um de {LAYOUTS}")
    doc = ler(cur, rede_id, diagrama_id)
    grafo = {"nos": {}, "arestas": []}
    for n in doc["nos"]:
        grafo["nos"][n["chave"]] = {"chave": n["chave"], "papel": n["papel"], "feicao_id": n["feicao_id"],
                                    "terminal_num": n["terminal"], "tipo_id": None, "tipo_chave": n["tipo"],
                                    "rotulo": n["rotulo"], "agregados": n["agregados"], "lon": n["lon"],
                                    "lat": n["lat"], "x": n["x"], "y": n["y"]}
    for a in doc["arestas"]:
        grafo["arestas"].append({"chave": a["chave"], "de": a["de"], "para": a["para"],
                                 "origem": a["origem"], "feicoes": a["feicoes"], "tipo_id": None,
                                 "tipo_chave": a["tipo"], "agregadas": a["agregadas"],
                                 "comprimento_m": a["comprimento_m"]})
    medida = aplicar_layout(grafo, layout)
    for chave, n in grafo["nos"].items():
        cur.execute("UPDATE plat.rede_diagrama_no SET x = %s, y = %s WHERE diagrama_id = %s::uuid "
                    "AND chave = %s", (float(n["x"]), float(n["y"]), diagrama_id, chave))
    resumo = dict(doc["resumo"] or {})
    resumo["layout"] = medida
    resumo["pares_sobrepostos"] = pares_sobrepostos(grafo)
    resumo["menor_distancia_proxima"] = _menor_arredondada(grafo)
    cur.execute("UPDATE plat.rede_diagrama SET layout = %s, resumo = %s::jsonb WHERE id = %s::uuid",
                (layout, json.dumps(resumo), diagrama_id))
    return {"id": diagrama_id, "nome": doc["nome"], "layout": layout, "estado": doc["estado"],
            "resumo": resumo}


# --- consistência -----------------------------------------------------------------------------------------

def marcar_inconsistentes(cur, rede_id: str, area_id: str | None = None) -> dict:
    """Cruza as áreas sujas abertas (ou só a área da edição em curso) com as feições desenhadas e marca
    `inconsistente` o diagrama que a edição tocou. Mesmo mecanismo de `subredes.marcar_sujas`, e pelo mesmo
    motivo: `topologia.habilitar()` apaga as áreas sujas, então o estado tem de ser gravado no instante da
    edição, não calculado depois."""
    cur.execute(
        "UPDATE plat.rede_diagrama d SET estado = 'inconsistente' "
        "WHERE d.rede_id = %(rede)s::uuid AND d.estado = 'consistente' AND EXISTS ("
        "  SELECT 1 FROM plat.rede_diagrama_no n "
        "  LEFT JOIN plat.rede_feicao_ponto p ON p.id = n.feicao_id "
        "  JOIN plat.rede_topo_area_suja a ON a.rede_id = %(rede)s::uuid "
        "     AND (%(area)s::uuid IS NULL OR a.id = %(area)s::uuid) "
        "  WHERE n.diagrama_id = d.id AND ("
        "     (p.geom IS NOT NULL AND ST_Intersects(a.geom, p.geom)) "
        "     OR (n.lon IS NOT NULL AND ST_Intersects(a.geom, ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326))))) "
        "RETURNING d.nome",
        {"rede": rede_id, "area": area_id},
    )
    nomes = sorted(r["nome"] for r in cur.fetchall())
    if nomes:
        return {"marcados": len(nomes), "nomes": nomes}
    # a edição pode ter mexido numa LINHA desenhada: a aresta do diagrama guarda a feição, não a geometria
    cur.execute(
        "UPDATE plat.rede_diagrama d SET estado = 'inconsistente' "
        "WHERE d.rede_id = %(rede)s::uuid AND d.estado = 'consistente' AND EXISTS ("
        "  SELECT 1 FROM plat.rede_diagrama_aresta e "
        "  JOIN plat.rede_topo_area_suja a ON a.rede_id = %(rede)s::uuid "
        "     AND (%(area)s::uuid IS NULL OR a.id = %(area)s::uuid) "
        "  JOIN plat.rede_feicao_linha l ON l.id::text IN (SELECT jsonb_array_elements_text(e.feicoes)) "
        "     AND l.rede_id = %(rede)s::uuid "
        "  WHERE e.diagrama_id = d.id AND ST_Intersects(a.geom, l.geom)) "
        "RETURNING d.nome",
        {"rede": rede_id, "area": area_id},
    )
    nomes = sorted(r["nome"] for r in cur.fetchall())
    return {"marcados": len(nomes), "nomes": nomes}


# --- exportação -------------------------------------------------------------------------------------------

FORMATOS_EXPORTACAO = ("json", "svg", "png")
_CORES = {"terminal": "#2463a8", "conexao": "#8a8f98", "conteiner": "#d98a2b"}
PNG_LADO_MAXIMO = 2000


def _quadro(doc: dict, margem: float) -> tuple[float, float, float, float]:
    xs = [n["x"] for n in doc["nos"]] or [0.0]
    ys = [n["y"] for n in doc["nos"]] or [0.0]
    return min(xs) - margem, min(ys) - margem, max(xs) + margem, max(ys) + margem


def _texto_seguro(valor) -> str:
    """Rótulo dentro de SVG: o texto vem de atributo do arquivo do usuário, então tudo que possa fechar uma
    marca é escapado. Sem isto o rótulo seria injeção de marcação no arquivo exportado."""
    return (str(valor or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def para_svg(doc: dict) -> str:
    """O diagrama em SVG: uma linha por aresta, um círculo e um rótulo por nó, tudo no espaço do diagrama
    (só o sentido do eixo y é invertido, porque em SVG o y cresce para baixo)."""
    margem = ESPACO
    x0, y0, x1, y1 = _quadro(doc, margem)
    larg, alt = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    escala = 20.0
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{larg * escala:.1f}" height="{alt * escala:.1f}" '
        f'viewBox="0 0 {larg * escala:.1f} {alt * escala:.1f}" role="img" '
        f'aria-label="{_texto_seguro(doc["nome"])}">',
        f'<title>{_texto_seguro(doc["nome"])}</title>',
        f'<rect width="100%" height="100%" fill="#ffffff"/>',
    ]

    def _px(no_x, no_y):
        return (no_x - x0) * escala, (y1 - no_y) * escala

    for a in doc["arestas"]:
        ax, ay = _px(a["x1"], a["y1"])
        bx, by = _px(a["x2"], a["y2"])
        traco = "4 3" if a["origem"] == "dispositivo" else "none"
        partes.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#3b4a5a" '
                      f'stroke-width="1.5" stroke-dasharray="{traco}"/>')
    for n in doc["nos"]:
        cx, cy = _px(n["x"], n["y"])
        cor = _CORES.get(n["papel"], "#3b4a5a")
        raio = 6 if n["papel"] != "conexao" else 3
        partes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{raio}" fill="{cor}"/>')
        if n["papel"] != "conexao" and n["rotulo"]:
            partes.append(f'<text x="{cx + raio + 3:.1f}" y="{cy + 4:.1f}" font-family="sans-serif" '
                          f'font-size="10" fill="#20262e">{_texto_seguro(n["rotulo"])}</text>')
    partes.append("</svg>")
    return "\n".join(partes)


def para_png(doc: dict) -> bytes:
    """O mesmo desenho em PNG, com Pillow (a mesma biblioteca das miniaturas do catálogo — nenhuma dependência
    nova). O lado maior é limitado: diagrama grande vira imagem grande, e imagem grande é bomba de memória."""
    from PIL import Image, ImageDraw

    margem = ESPACO
    x0, y0, x1, y1 = _quadro(doc, margem)
    larg, alt = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    escala = min(20.0, PNG_LADO_MAXIMO / max(larg, alt))
    largura_px = max(1, min(PNG_LADO_MAXIMO, int(larg * escala)))
    altura_px = max(1, min(PNG_LADO_MAXIMO, int(alt * escala)))
    imagem = Image.new("RGB", (largura_px, altura_px), (255, 255, 255))
    desenho = ImageDraw.Draw(imagem)

    def _px(no_x, no_y):
        return (no_x - x0) * escala, (y1 - no_y) * escala

    for a in doc["arestas"]:
        desenho.line([_px(a["x1"], a["y1"]), _px(a["x2"], a["y2"])], fill=(59, 74, 90), width=2)
    for n in doc["nos"]:
        cx, cy = _px(n["x"], n["y"])
        raio = 5 if n["papel"] != "conexao" else 3
        cor = tuple(int(_CORES.get(n["papel"], "#3b4a5a")[i:i + 2], 16) for i in (1, 3, 5))
        desenho.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], fill=cor)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return saida.getvalue()
