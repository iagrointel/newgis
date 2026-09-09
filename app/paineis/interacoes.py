"""Validação das INTERAÇÕES de um painel (item L2-06-c-ações-seletores-filtros-cruzados): o array
`corpo.mensagens` (gatilho → ações, o mesmo modelo do barramento do L5-07) e o elemento `seletor`.

Paridade com `web/js/app/modelo.js`: as MESMAS regras, com os MESMOS códigos de regra, adaptadas ao
documento de painel — aqui os ids de origem/alvo são elementos (`corpo.elementos[].id`) e as fontes
são `corpo.fontes[]` (que expõe NOMES de campo, sem tipo — a conferência de tipo de campo da relação
fica para o construtor; em execução, relação com tipos que não casam devolve filtro vazio, nunca erro).
O que é ERRO aqui recusa o documento inteiro (422 `grafo_invalido` via `documento.validar_grafo`);
o que é AVISO via junto (hoje: ciclo de ações — o barramento corta a recursão em uma volta).

Regra específica do painel (documentada no ADR): o filtro do painel é SQL, e linha de camada não tem
coluna de id estável — então ação de dado com gatilho de SELEÇÃO (`selecao_mudou`/`clique`) exige
relação declarada `atributo` ou `espacial` MESMO entre elementos da mesma fonte (a `mesma_fonte` do
L5-07 traduziria seleção para `in` sobre ids, que aqui não existe). Para gatilho de FILTRO (seletor),
a relação é opcional: sem ela, o filtro CQL2 do seletor passa inteiro para o alvo da mesma fonte."""

import re

from app.erros import ErroAPI

ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

EVENTOS = ("clique", "dado_adicionado", "filtro_mudou", "extensao_mudou", "localizacao",
           "registros_carregados", "selecao_mudou", "vista_mudou")
ACOES_DADO = ("filtrar", "selecionar", "limpar_filtro", "limpar_selecao")
ACOES_WIDGET = ("zoom", "pan", "piscar", "popup", "abrir", "fechar", "definir_parametro")
ACOES = ACOES_DADO + ACOES_WIDGET
RELACOES = ("mesma_fonte", "atributo", "espacial")
GATILHOS_DE_SELECAO = ("selecao_mudou", "clique")

LIMITES = {"mensagens": 500, "acoes_por_mensagem": 20}
MODOS_SELETOR = ("categoria", "numero", "data", "feicao")
PRESETS_DATA = ("ultimos_7_dias", "ultimos_30_dias", "ultimos_90_dias", "este_ano")


def _erro(erros: list, campo: str, mensagem: str, regra: str) -> None:
    erros.append({"campo": campo, "erro": mensagem, "regra": regra})


def _indice(corpo: dict):
    elementos = corpo.get("elementos") if isinstance(corpo.get("elementos"), list) else []
    fontes = {f.get("id"): f for f in corpo.get("fontes", []) if isinstance(f, dict)}
    por_id: dict[str, dict] = {}
    for el in elementos:
        if isinstance(el, dict) and isinstance(el.get("id"), str):
            por_id[el["id"]] = el
    return por_id, fontes


def _fonte_do_elemento(el: dict, fontes: dict) -> dict | None:
    fid = el.get("fonte") if isinstance(el, dict) else None
    return fontes.get(fid) if fid else None


def _ciclos(mensagens: list) -> list[list[str]]:
    """Caminhos A -> ... -> A via ações de dado (mesmo algoritmo de modelo.js::ciclos, aqui sobre
    elementos). Cada ciclo vira AVISO, não erro: o barramento corta a recursão em uma volta."""
    grafo: dict[str, set[str]] = {}
    for m in mensagens:
        gat = m.get("gatilho") if isinstance(m, dict) else None
        de = gat.get("origem") if isinstance(gat, dict) else None
        for a in (m.get("acoes") or []) if isinstance(m, dict) else []:
            if not isinstance(a, dict) or a.get("acao") not in ACOES_DADO:
                continue
            para = a.get("alvo")
            if isinstance(de, str) and isinstance(para, str):
                grafo.setdefault(de, set()).add(para)
    achados: list[list[str]] = []

    def visita(inicio: str, atual: str, trilha: list[str], vistos: set[str]) -> None:
        for prox in sorted(grafo.get(atual, ())):
            if prox == inicio:
                achados.append([*trilha, prox])
                continue
            if prox in vistos:
                continue
            visita(inicio, prox, [*trilha, prox], {*vistos, prox})

    for inicio in sorted(grafo):
        visita(inicio, inicio, [inicio], {inicio})
    unicos: dict[str, list[str]] = {}
    for c in achados:
        unicos.setdefault(">".join(sorted(set(c))), c)
    return list(unicos.values())


def _validar_seletor(el: dict, fonte: dict | None, erros: list, caminho: str) -> None:
    """Elemento `seletor` (item L2-06-c): modo + campo obrigatório dentro dos campos da fonte."""
    op = el.get("opcoes") if isinstance(el.get("opcoes"), dict) else {}
    modo = op.get("modo", "categoria")
    if modo not in MODOS_SELETOR:
        _erro(erros, f"{caminho}.opcoes.modo", f"modo de seletor desconhecido: {modo!r}", "modo_seletor")
        return
    if modo == "categoria" and isinstance(op.get("valores"), list) and op["valores"]:
        return  # lista fixa: não precisa de campo na fonte
    if not fonte:
        _erro(erros, f"{caminho}.fonte", "seletor precisa de fonte (ou lista fixa em opcoes.valores)", "sem_fonte")
        return
    campo = op.get("campo")
    if not isinstance(campo, str) or not IDENT_RE.match(campo):
        _erro(erros, f"{caminho}.opcoes.campo", "seletor precisa de opcoes.campo válido", "campo")
        return
    campos = fonte.get("campos") if isinstance(fonte.get("campos"), list) else []
    if campo not in campos:
        _erro(erros, f"{caminho}.opcoes.campo", f"campo {campo} não existe na fonte {fonte.get('id')}",
              "campo_inexistente")
    if modo == "data":
        presets = op.get("presets", PRESETS_DATA)
        if not isinstance(presets, list) or any(p not in PRESETS_DATA for p in presets):
            _erro(erros, f"{caminho}.opcoes.presets",
                  f"presets desconhecidos (aceitos: {', '.join(PRESETS_DATA)})", "preset_data")
    if modo == "numero":
        minimo, maximo = op.get("min"), op.get("max")
        for nome, v in (("min", minimo), ("max", maximo)):
            if (v is not None and not isinstance(v, (int, float))) or isinstance(v, bool):
                _erro(erros, f"{caminho}.opcoes.{nome}",
                      "limite do seletor numérico precisa ser número", "limite_numero")
        if (
            isinstance(minimo, (int, float)) and isinstance(maximo, (int, float)) and minimo > maximo
        ):
            _erro(erros, f"{caminho}.opcoes.min", "min maior que max", "limite_numero")


def validar_interacoes(corpo: dict) -> tuple[list, list]:
    """Devolve (erros, avisos) das interações do painel. `erros` vira detalhe do 422 `grafo_invalido`."""
    erros: list = []
    avisos: list = []
    elementos, fontes = _indice(corpo)
    mensagens = corpo.get("mensagens")
    if mensagens is None:
        mensagens = []
    if not isinstance(mensagens, list):
        _erro(erros, "corpo.mensagens", "mensagens precisa ser uma lista", "mensagens")
        return erros, avisos
    if len(mensagens) > LIMITES["mensagens"]:
        _erro(erros, "corpo.mensagens", f"mais de {LIMITES['mensagens']} mensagens", "limite")

    # elementos `seletor` (a forma nova de elemento deste item)
    for el_id, el in elementos.items():
        if el.get("tipo") != "seletor":
            continue
        _validar_seletor(el, _fonte_do_elemento(el, fontes), erros, f"corpo.elementos.{el_id}")

    vistos: set = set()
    for i, m in enumerate(mensagens):
        c = f"corpo.mensagens.{i}"
        if not isinstance(m, dict):
            _erro(erros, c, "mensagem precisa ser um objeto", "mensagem")
            continue
        mid = m.get("id")
        if not isinstance(mid, str) or not ULID_RE.match(mid):
            _erro(erros, f"{c}.id", "id de mensagem precisa ser um ULID", "ulid")
        elif mid in vistos:
            _erro(erros, f"{c}.id", f"id de mensagem repetido: {mid}", "id_duplicado")
        vistos.add(mid)
        gatilho = m.get("gatilho")
        if not isinstance(gatilho, dict):
            _erro(erros, f"{c}.gatilho", "mensagem sem gatilho", "gatilho")
            continue
        origem = gatilho.get("origem")
        evento = gatilho.get("evento")
        el_origem = elementos.get(origem) if isinstance(origem, str) else None
        if el_origem is None:
            _erro(erros, f"{c}.gatilho.origem",
                  f"origem do gatilho não é elemento do painel: {origem}", "referencia_pendente")
        elif evento not in EVENTOS:
            _erro(erros, f"{c}.gatilho.evento",
                  f"evento desconhecido: {evento!r} (aceitos: {', '.join(EVENTOS)})", "evento")
        acoes = m.get("acoes")
        if not isinstance(acoes, list) or not acoes:
            _erro(erros, f"{c}.acoes", "mensagem sem ações", "acoes")
            continue
        if len(acoes) > LIMITES["acoes_por_mensagem"]:
            _erro(erros, f"{c}.acoes", f"mais de {LIMITES['acoes_por_mensagem']} ações", "limite")
        fo = _fonte_do_elemento(el_origem or {}, fontes)
        for j, a in enumerate(acoes):
            ca = f"{c}.acoes.{j}"
            if not isinstance(a, dict):
                _erro(erros, ca, "ação precisa ser um objeto", "acao")
                continue
            alvo = a.get("alvo")
            el_alvo = elementos.get(alvo) if isinstance(alvo, str) else None
            if el_alvo is None:
                _erro(erros, f"{ca}.alvo", f"alvo não é elemento do painel: {alvo}", "referencia_pendente")
                continue
            acao = a.get("acao")
            if acao not in ACOES:
                _erro(erros, f"{ca}.acao",
                      f"ação desconhecida: {acao!r} (aceitas: {', '.join(ACOES)})", "acao")
                continue
            relacao = a.get("relacao")
            if acao in ACOES_DADO:
                fa = _fonte_do_elemento(el_alvo, fontes)
                if fo is None or fa is None:
                    _erro(erros, ca,
                          "ação de dado exige origem e alvo ligados a uma fonte do painel", "sem_fonte")
                    continue
                mesma = fo.get("id") == fa.get("id")
                if relacao is None:
                    if not mesma:
                        _erro(erros, f"{ca}.relacao",
                              f"fontes diferentes ({fo.get('nome') or fo.get('id')} e "
                              f"{fa.get('nome') or fa.get('id')}) exigem relação declarada por atributo "
                              "ou espacial", "relacao_ausente")
                    elif evento in GATILHOS_DE_SELECAO:
                        _erro(erros, f"{ca}.relacao",
                              "ação de dado com gatilho de seleção exige relação atributo ou espacial "
                              "(linha de painel não tem coluna de id para mesma_fonte)", "relacao_ausente")
                    continue
                if not isinstance(relacao, dict) or relacao.get("tipo") not in RELACOES:
                    _erro(erros, f"{ca}.relacao.tipo",
                          f"tipo de relação desconhecido: {relacao!r}", "relacao_tipo")
                    continue
                tipo_rel = relacao["tipo"]
                if mesma and tipo_rel == "espacial":
                    _erro(erros, f"{ca}.relacao.tipo",
                          "origem e alvo têm a mesma fonte: relação espacial redundante", "relacao_redundante")
                if not mesma and tipo_rel == "mesma_fonte":
                    _erro(erros, f"{ca}.relacao.tipo", "fontes diferentes não são mesma_fonte", "relacao_tipo")
                if tipo_rel == "espacial":
                    continue  # toda fonte de painel vem de camada com geometria (plat.camada_preparar)
                if tipo_rel == "atributo":
                    co = relacao.get("campo_origem")
                    ca_alvo = relacao.get("campo_alvo")
                    campos_o = fo.get("campos") if isinstance(fo.get("campos"), list) else []
                    campos_a = fa.get("campos") if isinstance(fa.get("campos"), list) else []
                    if not isinstance(co, str) or not IDENT_RE.match(co):
                        _erro(erros, f"{ca}.relacao.campo_origem", "campo_origem inválido", "campo_inexistente")
                    elif co not in campos_o:
                        _erro(erros, f"{ca}.relacao.campo_origem",
                              f"campo {co} não existe na fonte de origem ({fo.get('nome') or fo.get('id')})",
                              "campo_inexistente")
                    if not isinstance(ca_alvo, str) or not IDENT_RE.match(ca_alvo):
                        _erro(erros, f"{ca}.relacao.campo_alvo", "campo_alvo inválido", "campo_inexistente")
                    elif ca_alvo not in campos_a:
                        _erro(erros, f"{ca}.relacao.campo_alvo",
                              f"campo {ca_alvo} não existe na fonte de destino ({fa.get('nome') or fa.get('id')})",
                              "campo_inexistente")
                    operador = relacao.get("operador")
                    if operador is not None and operador not in ("=", "in"):
                        _erro(erros, f"{ca}.relacao.operador",
                              f"operador de relação inválido: {operador!r}", "relacao_operador")
            elif acao == "definir_parametro":
                parametros = a.get("parametros")
                if not isinstance(parametros, dict) or not isinstance(parametros.get("nome"), str):
                    _erro(erros, f"{ca}.parametros.nome", "definir_parametro exige parametros.nome", "parametros")

    for c in _ciclos(mensagens):
        avisos.append({"campo": "corpo.mensagens",
                       "aviso": f"ciclo de mensagens {' -> '.join(c)}: o barramento corta a recursão em "
                                "uma volta",
                       "regra": "ciclo"})
    return erros, avisos


def validar_ou_recusar(corpo: dict) -> None:
    """Ponto de entrada de `documento.validar_grafo`: levanta 422 `grafo_invalido` com o detalhe das
    regras quebradas (a mensagem específica vai em `detail`, que a tela do editor mostra)."""
    erros, _avisos = validar_interacoes(corpo)
    if erros:
        raise ErroAPI(422, "grafo_invalido", "interações do painel inválidas", erros)
