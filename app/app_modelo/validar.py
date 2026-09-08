"""Validação de `corpo.fontes`, `corpo.vistas` e `corpo.mensagens` de um documento `app` (item L5-07; L5_CONCEITO
D4/D5), espelho de `web/js/app/modelo.js`: forma das fontes (origem item/url/embutida, campos tipados), vistas
(fonte existente, filtro CQL2-JSON estrutural citando só campos da fonte, ordenação, seleção), mensagens (8
gatilhos, 11 ações, alvos existentes) e a regra de relação dos Dashboards — entre fontes diferentes, ação de
dado exige relação por atributo (tipos casam; inteiro/decimal e data/data_hora são as exceções) ou espacial
(geometria nas duas). Ciclos (A filtra B, B filtra A) são AVISO, não erro: o barramento corta em uma volta.
Erros seguem o contrato de `validar_grafo` (lista de {campo, erro, regra}) e viram 422 `modelo_invalido`."""

from __future__ import annotations

import re
from typing import Any

from app.app_modelo.contratos import CONTRATOS, EVENTOS_VISTA

EVENTOS = ("clique", "dado_adicionado", "filtro_mudou", "extensao_mudou", "localizacao", "registros_carregados",
           "selecao_mudou", "vista_mudou")
ACOES_DADO = ("filtrar", "selecionar", "limpar_filtro", "limpar_selecao")
ACOES_WIDGET = ("zoom", "pan", "piscar", "popup", "abrir", "fechar", "definir_parametro")
ACOES = ACOES_DADO + ACOES_WIDGET
RELACOES = ("mesma_fonte", "atributo", "espacial")
TIPOS_CAMPO = ("texto", "inteiro", "decimal", "booleano", "data", "data_hora", "geometria")
OPERADORES_RELACAO = ("=", "in")
OPERADORES_CQL2 = ("=", "<>", "<", "<=", ">", ">=", "and", "or", "not", "in", "like", "between", "isNull",
                   "s_intersects")
ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
LIMITES = {"fontes": 50, "vistas": 200, "mensagens": 500, "acoes_por_mensagem": 20, "campos": 500,
           "cql2_profundidade": 20, "in_valores": 10000, "selecao": 10000}
_FAMILIA = {"inteiro": "numero", "decimal": "numero", "data": "instante", "data_hora": "instante"}


def tipos_casam(a: str, b: str) -> bool:
    return a == b or (a in _FAMILIA and _FAMILIA[a] == _FAMILIA.get(b))


def _e_prop(x: Any) -> bool:
    return isinstance(x, dict) and isinstance(x.get("property"), str)


def _e_geom(x: Any) -> bool:
    if not isinstance(x, dict) or not isinstance(x.get("type"), str):
        return False
    return "coordinates" in x or x.get("type") == "GeometryCollection"


def validar_cql2(no: Any, profundidade: int = 0, caminho: str = "filtro") -> None:
    """Só a forma (op/args), como `cql2.validar` do navegador; levanta ValueError com a mensagem do campo."""
    if profundidade > LIMITES["cql2_profundidade"]:
        raise ValueError(f"{caminho}: filtro aninhado além de {LIMITES['cql2_profundidade']} níveis")
    if not isinstance(no, dict):
        raise ValueError(f"{caminho}: nó precisa ser um objeto {{op, args}}")
    op, args = no.get("op"), no.get("args")
    if op not in OPERADORES_CQL2:
        raise ValueError(f"{caminho}: operador desconhecido {op!r}")
    if not isinstance(args, list):
        raise ValueError(f"{caminho}: args precisa ser lista")
    if op in ("and", "or"):
        if not args:
            raise ValueError(f"{caminho}: {op} exige ao menos um argumento")
        for i, a in enumerate(args):
            validar_cql2(a, profundidade + 1, f"{caminho}.args.{i}")
        return
    if op == "not":
        if len(args) != 1:
            raise ValueError(f"{caminho}: not exige um argumento")
        validar_cql2(args[0], profundidade + 1, f"{caminho}.args.0")
        return
    if op == "isNull":
        if len(args) != 1 or not _e_prop(args[0]):
            raise ValueError(f"{caminho}: isNull exige uma propriedade")
        return
    if op == "between":
        if len(args) != 3 or not _e_prop(args[0]):
            raise ValueError(f"{caminho}: between exige propriedade, mínimo e máximo")
        return
    if op == "in":
        if len(args) != 2 or not _e_prop(args[0]) or not isinstance(args[1], list):
            raise ValueError(f"{caminho}: in exige propriedade e lista")
        if len(args[1]) > LIMITES["in_valores"]:
            raise ValueError(f"{caminho}: lista do in acima de {LIMITES['in_valores']} valores")
        return
    if op == "s_intersects":
        if len(args) != 2 or not _e_prop(args[0]) or not _e_geom(args[1]):
            raise ValueError(f"{caminho}: s_intersects exige propriedade e geometria")
        return
    if len(args) != 2 or not (_e_prop(args[0]) or _e_prop(args[1])):
        raise ValueError(f"{caminho}: {op} exige uma propriedade e um valor")


def propriedades_cql2(no: Any, saida: set[str] | None = None) -> set[str]:
    saida = set() if saida is None else saida
    if not isinstance(no, dict):
        return saida
    for a in no.get("args") or []:
        if _e_prop(a):
            saida.add(a["property"])
        elif isinstance(a, dict) and "op" in a:
            propriedades_cql2(a, saida)
    return saida


class _Indice:
    def __init__(self, corpo: dict):
        self.fontes = {f.get("id"): f for f in corpo.get("fontes") or [] if isinstance(f, dict)}
        self.vistas = {v.get("id"): v for v in corpo.get("vistas") or [] if isinstance(v, dict)}
        self.nos = {n.get("id"): n for n in corpo.get("nos") or [] if isinstance(n, dict)}

    def fonte_de(self, ident: str) -> dict | None:
        if ident in self.vistas:
            return self.fontes.get(self.vistas[ident].get("fonte"))
        no = self.nos.get(ident) or {}
        configuracao = no.get("configuracao") if isinstance(no.get("configuracao"), dict) else {}
        vid = configuracao.get("vista")
        return self.fontes.get(self.vistas[vid].get("fonte")) if vid in self.vistas else None


def _campo(fonte: dict | None, nome: Any) -> dict | None:
    for c in (fonte or {}).get("campos") or []:
        if isinstance(c, dict) and c.get("nome") == nome:
            return c
    return None


def _tem_geometria(fonte: dict | None) -> bool:
    return any(isinstance(c, dict) and c.get("tipo") == "geometria" for c in (fonte or {}).get("campos") or [])


def _erro(lista: list, campo: str, erro: str, regra: str) -> None:
    lista.append({"campo": campo, "erro": erro, "regra": regra})


def validar_relacao(idx: _Indice, origem: str, alvo: str, relacao: Any, caminho: str, erros: list) -> None:
    fo, fa = idx.fonte_de(origem), idx.fonte_de(alvo)
    if fo is None or fa is None:
        _erro(erros, caminho, "origem e alvo de uma ação de dado precisam estar ligados a uma vista com fonte",
              "sem_fonte")
        return
    if fo.get("id") == fa.get("id"):
        if isinstance(relacao, dict) and relacao.get("tipo") not in (None, "mesma_fonte"):
            _erro(erros, f"{caminho}.relacao.tipo", "origem e alvo têm a mesma fonte: a relação é mesma_fonte",
                  "relacao_redundante")
        return
    if not isinstance(relacao, dict) or not relacao.get("tipo"):
        nomes = f"{fo.get('nome') or fo.get('id')} e {fa.get('nome') or fa.get('id')}"
        _erro(erros, f"{caminho}.relacao",
              f"fontes diferentes ({nomes}) exigem relação declarada por atributo ou espacial", "relacao_ausente")
        return
    tipo = relacao["tipo"]
    if tipo not in RELACOES:
        _erro(erros, f"{caminho}.relacao.tipo", f"tipo de relação desconhecido: {tipo}", "relacao_tipo")
        return
    if tipo == "mesma_fonte":
        _erro(erros, f"{caminho}.relacao.tipo", "fontes diferentes não são mesma_fonte", "relacao_tipo")
        return
    if tipo == "espacial":
        if not _tem_geometria(fo) or not _tem_geometria(fa):
            _erro(erros, f"{caminho}.relacao", "relação espacial exige geometria nas duas fontes",
                  "relacao_espacial_sem_geometria")
        return
    co, ca = _campo(fo, relacao.get("campo_origem")), _campo(fa, relacao.get("campo_alvo"))
    if co is None:
        _erro(erros, f"{caminho}.relacao.campo_origem",
              f"campo {relacao.get('campo_origem')} não existe na fonte de origem", "campo_inexistente")
        return
    if ca is None:
        _erro(erros, f"{caminho}.relacao.campo_alvo",
              f"campo {relacao.get('campo_alvo')} não existe na fonte de destino", "campo_inexistente")
        return
    if not tipos_casam(co.get("tipo"), ca.get("tipo")):
        _erro(erros, f"{caminho}.relacao",
              f"tipos não casam: {co['nome']} é {co.get('tipo')} e {ca['nome']} é {ca.get('tipo')} "
              "(só inteiro/decimal e data/data_hora se equivalem)", "relacao_tipos")
    if relacao.get("operador") not in (None, *OPERADORES_RELACAO):
        _erro(erros, f"{caminho}.relacao.operador", f"operador de relação inválido: {relacao.get('operador')}",
              "relacao_operador")


def ciclos(corpo: dict) -> list[list[str]]:
    grafo: dict[str, set[str]] = {}
    for m in corpo.get("mensagens") or []:
        if not isinstance(m, dict):
            continue
        de = (m.get("gatilho") or {}).get("origem")
        for a in m.get("acoes") or []:
            if isinstance(a, dict) and a.get("acao") in ACOES_DADO and de and a.get("alvo"):
                grafo.setdefault(de, set()).add(a["alvo"])
    achados: dict[str, list[str]] = {}

    def visita(inicio: str, atual: str, trilha: list[str], vistos: set[str]) -> None:
        for prox in grafo.get(atual, ()):
            if prox == inicio:
                c = [*trilha, prox]
                achados.setdefault(">".join(sorted(set(c))), c)
            elif prox not in vistos:
                vistos.add(prox)
                visita(inicio, prox, [*trilha, prox], vistos)

    for inicio in grafo:
        visita(inicio, inicio, [inicio], {inicio})
    return list(achados.values())


def _validar_fontes(fontes: list, ids: set, erros: list) -> None:
    for i, f in enumerate(fontes):
        c = f"corpo.fontes.{i}"
        if not isinstance(f, dict):
            _erro(erros, c, "fonte precisa ser objeto", "forma")
            continue
        if not ULID_RE.match(str(f.get("id") or "")):
            _erro(erros, f"{c}.id", "id de fonte precisa ser um ULID", "ulid")
        if f.get("id") in ids:
            _erro(erros, f"{c}.id", f"id repetido: {f.get('id')}", "id_duplicado")
        ids.add(f.get("id"))
        origem = f.get("origem") if isinstance(f.get("origem"), dict) else {}
        if origem.get("tipo") not in ("item", "url", "embutida"):
            _erro(erros, f"{c}.origem.tipo", "origem precisa ser item, url ou embutida", "origem")
        if origem.get("tipo") == "url" and not re.match(r"^/[^\s]*$", str(origem.get("url") or "")):
            _erro(erros, f"{c}.origem.url", "url de fonte precisa ser caminho do próprio servidor (começa com /)",
                  "origem_url")
        campos = f.get("campos")
        if not isinstance(campos, list) or len(campos) > LIMITES["campos"]:
            _erro(erros, f"{c}.campos", f"campos precisa ser lista de até {LIMITES['campos']}", "campos")
            campos = []
        nomes: set[str] = set()
        for j, campo in enumerate(campos):
            nome = campo.get("nome") if isinstance(campo, dict) else None
            if not isinstance(nome, str) or not nome:
                _erro(erros, f"{c}.campos.{j}.nome", "campo sem nome", "campo")
            elif nome in nomes:
                _erro(erros, f"{c}.campos.{j}.nome", f"campo repetido: {nome}", "campo_duplicado")
            nomes.add(nome)
            tipo = campo.get("tipo") if isinstance(campo, dict) else campo
            if tipo not in TIPOS_CAMPO:
                _erro(erros, f"{c}.campos.{j}.tipo", f"tipo de campo desconhecido: {tipo}", "campo_tipo")


def _validar_vistas(vistas: list, ids: set, idx: _Indice, erros: list) -> None:
    for i, v in enumerate(vistas):
        c = f"corpo.vistas.{i}"
        if not isinstance(v, dict):
            _erro(erros, c, "vista precisa ser objeto", "forma")
            continue
        if not ULID_RE.match(str(v.get("id") or "")):
            _erro(erros, f"{c}.id", "id de vista precisa ser um ULID", "ulid")
        if v.get("id") in ids:
            _erro(erros, f"{c}.id", f"id repetido: {v.get('id')}", "id_duplicado")
        ids.add(v.get("id"))
        f = idx.fontes.get(v.get("fonte"))
        if f is None:
            _erro(erros, f"{c}.fonte", f"vista aponta para fonte inexistente: {v.get('fonte')}",
                  "referencia_pendente")
            continue
        if v.get("filtro"):
            try:
                validar_cql2(v["filtro"])
            except ValueError as e:
                _erro(erros, f"{c}.filtro", str(e), "cql2")
            for p in propriedades_cql2(v["filtro"]):
                if p != "__id" and _campo(f, p) is None:
                    _erro(erros, f"{c}.filtro", f"filtro cita campo inexistente na fonte: {p}", "campo_inexistente")
        for j, o in enumerate(v.get("ordenacao") or []):
            campo = o.get("campo") if isinstance(o, dict) else o
            if not isinstance(o, dict) or _campo(f, campo) is None:
                _erro(erros, f"{c}.ordenacao.{j}.campo", f"campo de ordenação inexistente: {campo}",
                      "campo_inexistente")
            elif o.get("direcao") not in (None, "asc", "desc"):
                _erro(erros, f"{c}.ordenacao.{j}.direcao", "direção precisa ser asc ou desc", "ordenacao")
        for nome in v.get("campos") or []:
            if _campo(f, nome) is None:
                _erro(erros, f"{c}.campos", f"campo inexistente na fonte: {nome}", "campo_inexistente")
        sel = v.get("selecao")
        if sel is not None and (not isinstance(sel, list) or len(sel) > LIMITES["selecao"]):
            _erro(erros, f"{c}.selecao", f"seleção precisa ser lista de até {LIMITES['selecao']} ids", "selecao")


def _nome_no(idx: _Indice, ident: Any) -> str:
    v = idx.vistas.get(ident)
    if v is not None:
        return f"vista {v.get('nome') or ident}"
    n = idx.nos.get(ident)
    if n is not None:
        return f"{n.get('tipo')} {str(ident)[-4:]}"
    return str(ident)


def eventos_de(idx: _Indice, ident: Any) -> list[str]:
    """Eventos que a origem emite (item L5-01-e): vista = os cinco de dado; widget = os do contrato do tipo."""
    if ident in idx.vistas:
        return [e for e in EVENTOS_VISTA if e in EVENTOS]
    n = idx.nos.get(ident)
    c = CONTRATOS.get(n.get("tipo")) if n else None
    return [e for e in c["eventos"] if e in EVENTOS] if c else []


def acoes_de(idx: _Indice, ident: Any) -> list[str]:
    if ident in idx.vistas:
        return list(ACOES_DADO)
    n = idx.nos.get(ident)
    c = CONTRATOS.get(n.get("tipo")) if n else None
    return [a for a in c["acoes"] if a in ACOES] if c else []


def _validar_mensagens(mensagens: list, idx: _Indice, erros: list) -> None:
    def alvos(ident: Any) -> bool:
        return ident in idx.nos or ident in idx.vistas

    vistos: dict[str, int] = {}  # item L5-01-e: gatilho + alvo + ação repetidos = erro `gatilho_repetido`
    for i, m in enumerate(mensagens):
        c = f"corpo.mensagens.{i}"
        if not isinstance(m, dict):
            _erro(erros, c, "mensagem precisa ser objeto", "forma")
            continue
        if not ULID_RE.match(str(m.get("id") or "")):
            _erro(erros, f"{c}.id", "id de mensagem precisa ser um ULID", "ulid")
        g = m.get("gatilho") if isinstance(m.get("gatilho"), dict) else {}
        if not alvos(g.get("origem")):
            _erro(erros, f"{c}.gatilho.origem",
                  f"origem do gatilho não é widget nem vista do documento: {g.get('origem')}", "referencia_pendente")
        if g.get("evento") not in EVENTOS:
            _erro(erros, f"{c}.gatilho.evento",
                  f"evento desconhecido: {g.get('evento')} (aceitos: {', '.join(EVENTOS)})", "evento")
        elif alvos(g.get("origem")):
            emitidos = eventos_de(idx, g["origem"])
            if g["evento"] not in emitidos:
                _erro(erros, f"{c}.gatilho.evento",
                      f"a origem {_nome_no(idx, g['origem'])} não emite {g['evento']} "
                      f"(emite: {', '.join(emitidos) or 'nada'})", "evento_incompativel")
        acoes = m.get("acoes")
        if not isinstance(acoes, list) or not acoes:
            _erro(erros, f"{c}.acoes", "mensagem sem ações", "acoes")
            continue
        if len(acoes) > LIMITES["acoes_por_mensagem"]:
            _erro(erros, f"{c}.acoes", f"mais de {LIMITES['acoes_por_mensagem']} ações", "limite")
        for j, a in enumerate(acoes):
            ca = f"{c}.acoes.{j}"
            if not isinstance(a, dict):
                _erro(erros, ca, "ação precisa ser objeto", "forma")
                continue
            if not alvos(a.get("alvo")):
                _erro(erros, f"{ca}.alvo", f"alvo não é widget nem vista do documento: {a.get('alvo')}",
                      "referencia_pendente")
                continue
            if a.get("acao") not in ACOES:
                _erro(erros, f"{ca}.acao", f"ação desconhecida: {a.get('acao')} (aceitas: {', '.join(ACOES)})", "acao")
                continue
            aceitas = acoes_de(idx, a["alvo"])
            if a["acao"] not in aceitas:
                _erro(erros, f"{ca}.acao", f"o alvo {_nome_no(idx, a['alvo'])} não aceita {a['acao']} "
                      f"(aceita: {', '.join(aceitas) or 'nada'})", "alvo_incompativel")
                continue
            chave = f"{g.get('origem')}|{g.get('evento')}|{a['alvo']}|{a['acao']}"
            if chave in vistos:
                _erro(erros, ca, f"gatilho já usado: {g.get('evento')} de {_nome_no(idx, g.get('origem'))} já dispara "
                      f"{a['acao']} em {_nome_no(idx, a['alvo'])} (mensagem {vistos[chave]})", "gatilho_repetido")
            else:
                vistos[chave] = i
            if a["acao"] in ACOES_DADO and g.get("origem"):
                validar_relacao(idx, g["origem"], a["alvo"], a.get("relacao"), ca, erros)
            cond = (a.get("parametros") or {}).get("condicao") if isinstance(a.get("parametros"), dict) else None
            if cond is not None:
                try:
                    validar_cql2(cond)
                except ValueError as e:
                    _erro(erros, f"{ca}.parametros.condicao", f"condição inválida: {e}", "cql2")
                else:
                    fo = idx.fonte_de(g.get("origem")) if g.get("origem") else None
                    if fo is not None:
                        for p in sorted(propriedades_cql2(cond)):
                            if _campo(fo, p) is None:
                                _erro(erros, f"{ca}.parametros.condicao",
                                      f"condição cita campo inexistente na fonte de origem: {p}", "campo_inexistente")
            if a["acao"] == "definir_parametro" and not isinstance((a.get("parametros") or {}).get("nome"), str):
                _erro(erros, f"{ca}.parametros.nome", "definir_parametro exige parametros.nome", "parametros")


def validar_modelo(corpo: dict) -> tuple[list[dict], list[dict]]:
    """Devolve (erros, avisos) — mesma lista que `validarModelo` do navegador produz para o mesmo corpo."""
    erros: list[dict] = []
    avisos: list[dict] = []
    fontes = corpo.get("fontes") or []
    vistas = corpo.get("vistas") or []
    mensagens = corpo.get("mensagens") or []
    for nome, lista in (("fontes", fontes), ("vistas", vistas), ("mensagens", mensagens)):
        if not isinstance(lista, list):
            _erro(erros, f"corpo.{nome}", f"{nome} precisa ser lista", "forma")
            return erros, avisos
        if len(lista) > LIMITES[nome]:
            _erro(erros, f"corpo.{nome}", f"mais de {LIMITES[nome]} {nome}", "limite")
    ids = {n.get("id") for n in corpo.get("nos") or [] if isinstance(n, dict)}
    _validar_fontes(fontes, ids, erros)
    idx = _Indice(corpo)
    _validar_vistas(vistas, ids, idx, erros)
    _validar_mensagens(mensagens, idx, erros)
    for c in ciclos(corpo):
        avisos.append({"campo": "corpo.mensagens", "regra": "ciclo",
                       "aviso": f"ciclo de mensagens {' -> '.join(c)}: o barramento corta a recursão em uma volta"})
    return erros, avisos
