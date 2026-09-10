"""Configuração de traçado nomeada e compartilhável (item L4-02-e-configuracoes-de-tracado).

O que a Esri chama *trace configuration* (about-trace-configurations.htm) é um DOCUMENTO SALVO que diz como
um traçado deve ser feito: o tipo, onde ele para (barreiras), o que sai no resultado (filtros e tipo de
resultado) e que contas são feitas ao longo do caminho (funções). Aqui vale a mesma definição, com uma regra
dura: **a configuração não é um segundo motor de traçado**. O motor continua sendo `tracado.py` (conectado e
subrede) e `direcao.py` (montante e jusante); a configuração só preenche o pedido que vai a ele e resume o
resultado que volta. Por isso `POST /api/rede/{id}/tracar` ganhou um único campo novo, `config_id`, e não uma
rota paralela.

O que a configuração guarda, campo por campo (o documento vive na coluna `config` de
`plat.rede_config_tracado`):

  * `barreiras_condicao` — condições que tornam uma feição NÃO TRAVERSÁVEL. Uma feição de ponto que casa vira
    barreira do mesmo jeito que a barreira pontual que o chamador passa hoje (os terminais dela saem do
    grafo); uma feição de linha que casa tem a ARESTA dela removida do grafo (`arestas_excluidas` em
    `tracado._montar_sql_arestas`). ⛔ Ponto de partida nunca é removido por barreira de condição: quem escolhe
    de onde o traçado sai é o pedido, e um traçado que começasse vazio por causa da própria configuração seria
    um resultado sem explicação.
  * `barreiras_filtro` — a mesma gramática, mas aplicadas SÓ à segunda passagem: o traçado corre uma vez com
    as barreiras de condição (é essa a travessia) e, se houver barreira de filtro, corre uma segunda vez com
    as duas listas somadas; o resultado publicado é a INTERSEÇÃO. É o papel das filter barriers da Esri
    (barriers.htm): estreitar o que sai sem mudar o que foi percorrido. Sem barreira de filtro, uma passagem só.
  * `filtro_saida` — condições sobre o que APARECE no resultado (categoria, grupo, tipo, atributo, fase), mais
    `incluir_estrutura`. A estrutura de suporte (poste, torre) não tem terminal e portanto nunca é percorrida;
    com `incluir_estrutura` ela entra no resultado quando coincide, dentro da tolerância da rede, com um nó
    alcançado. É o que a Esri chama de incluir contenção e estrutura no resultado — no pacote elétrico
    brasileiro as categorias estruturais são as de `categorias_estrutura` (padrão: `estrutura_de_suporte`).
  * `funcoes` — soma, contagem, mínimo, máximo e média de um atributo sobre os elementos que sobraram, com
    filtro próprio por grupo/tipo/categoria. É assim que "Σ kVA a jusante" e "quantos clientes a jusante"
    saem do mesmo traçado.
  * `tipo_resultado` — `elementos` (padrão), `geometria` (só a geometria agregada e as contas) ou
    `conectividade` (os pares de nós das arestas percorridas). Mesmos três da Esri (results.htm).

QUE ATRIBUTO EXISTE. Uma barreira sobre atributo inexistente é recusada (422), e a lista do que existe vem do
catálogo da rede (`plat.rede_atributo`, preenchido pelo pacote): vale o código do catálogo (`untrmt_pot_nom`)
e vale o nome curto, sem o prefixo da camada (`pot_nom`) — que é a chave com que o dado real é gravado em
`atributos`. `estado` entra na lista por ser a convenção de traversabilidade do produto (`tracado.py`), e não
uma coluna de fonte.
"""

import time

from psycopg2.extras import Json

from app.erros import ErroAPI

TIPOS_CONFIG = ("conectado", "subrede", "montante", "jusante")
TIPOS_RESULTADO = ("elementos", "geometria", "conectividade")
FUNCOES = ("soma", "contagem", "minimo", "maximo", "media")
FASES = {"A": 1, "B": 2, "C": 4}
# operador de condição sobre atributo -> operador SQL (ou marca de tratamento próprio)
OPERADORES = {
    "=": "=", "<>": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "contem": "contem", "comeca_com": "comeca_com", "existe": "existe", "nao_existe": "nao_existe",
}
OPERADORES_FASE = ("tem", "nao_tem")
ATRIBUTOS_RESERVADOS = ("estado",)          # convenção de traversabilidade do produto, não coluna de fonte
CATEGORIAS_ESTRUTURA_PADRAO = ("estrutura_de_suporte",)
LIMITE_CONDICOES = 50
LIMITE_FUNCOES = 20


# --- catálogo do que pode ser citado numa condição -------------------------------------------------------

def atributos_conhecidos(cur, rede_id: str) -> set[str]:
    cur.execute("SELECT codigo FROM plat.rede_atributo WHERE rede_id = %s::uuid", (rede_id,))
    conhecidos = set(ATRIBUTOS_RESERVADOS)
    for r in cur.fetchall():
        codigo = r["codigo"]
        conhecidos.add(codigo)
        if "_" in codigo:
            conhecidos.add(codigo.split("_", 1)[1])
    return conhecidos


def _codigos(cur, tabela: str, coluna: str, rede_id: str) -> set[str]:
    cur.execute(f"SELECT {coluna} AS c FROM plat.{tabela} WHERE rede_id = %s::uuid", (rede_id,))
    return {r["c"] for r in cur.fetchall()}


def _catalogo(cur, rede_id: str) -> dict:
    return {
        "atributos": atributos_conhecidos(cur, rede_id),
        "categorias": _codigos(cur, "rede_categoria", "codigo", rede_id),
        "grupos": _codigos(cur, "rede_grupo", "codigo", rede_id),
        "tipos": _codigos(cur, "rede_tipo", "chave", rede_id),
    }


# --- gramática de condição -------------------------------------------------------------------------------

def _validar_condicao(cond: dict, catalogo: dict, onde: str) -> dict:
    if not isinstance(cond, dict):
        raise ErroAPI(422, "condicao_invalida", f"{onde}: cada condição é um objeto")
    chaves = [k for k in ("atributo", "fase", "categoria", "grupo", "tipo") if cond.get(k) is not None]
    if len(chaves) != 1:
        raise ErroAPI(422, "condicao_invalida",
                      f"{onde}: cada condição cita exatamente um de atributo, fase, categoria, grupo ou tipo")
    campo = chaves[0]
    valor_campo = cond[campo]
    if campo == "atributo":
        if valor_campo not in catalogo["atributos"]:
            raise ErroAPI(422, "atributo_inexistente",
                          f"{onde}: a rede não tem o atributo '{valor_campo}'")
        operador = cond.get("operador", "=")
        if operador not in OPERADORES:
            raise ErroAPI(422, "operador_invalido",
                          f"{onde}: operador '{operador}' desconhecido; use um de {tuple(OPERADORES)}")
        if operador not in ("existe", "nao_existe") and cond.get("valor") is None:
            raise ErroAPI(422, "valor_obrigatorio", f"{onde}: o operador '{operador}' exige 'valor'")
        saida = {"atributo": valor_campo, "operador": operador, "valor": cond.get("valor")}
    elif campo == "fase":
        if valor_campo not in FASES:
            raise ErroAPI(422, "fase_invalida", f"{onde}: fase deve ser uma de {tuple(FASES)}")
        operador = cond.get("operador", "tem")
        if operador not in OPERADORES_FASE:
            raise ErroAPI(422, "operador_invalido",
                          f"{onde}: operador de fase deve ser um de {OPERADORES_FASE}")
        saida = {"fase": valor_campo, "operador": operador}
    else:
        if valor_campo not in catalogo[campo + "s"]:
            raise ErroAPI(422, f"{campo}_inexistente", f"{onde}: a rede não tem o {campo} '{valor_campo}'")
        saida = {campo: valor_campo}
    aplica = cond.get("aplica_a", "ambos")
    if aplica not in ("ponto", "linha", "ambos"):
        raise ErroAPI(422, "aplica_a_invalido", f"{onde}: aplica_a deve ser ponto, linha ou ambos")
    saida["aplica_a"] = aplica
    return saida


def _sql_condicao(cur, cond: dict, alias: str) -> str:
    """Fragmento SQL (já com os literais embutidos por `mogrify`) que decide se a feição `alias` casa."""
    def lit(v):
        return cur.mogrify("%s", (v,)).decode("utf-8")

    if "atributo" in cond:
        chave, operador, valor = cond["atributo"], cond["operador"], cond.get("valor")
        campo = f"{alias}.atributos ->> {lit(chave)}"
        if operador == "existe":
            return f"({alias}.atributos ? {lit(chave)})"
        if operador == "nao_existe":
            return f"(NOT ({alias}.atributos ? {lit(chave)}))"
        if operador == "contem":
            return f"({campo} ILIKE {lit('%' + str(valor) + '%')})"
        if operador == "comeca_com":
            return f"({campo} ILIKE {lit(str(valor) + '%')})"
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return f"({campo} {OPERADORES[operador]} {lit(str(valor))})"
        # número: compara como número, e o que não é número no arquivo simplesmente não casa
        numerico = (f"CASE WHEN jsonb_typeof({alias}.atributos -> {lit(chave)}) = 'number' "
                    f"THEN ({campo})::double precision "
                    f"WHEN {campo} ~ '^-?[0-9]+([.][0-9]+)?$' THEN ({campo})::double precision END")
        return f"(({numerico}) {OPERADORES[operador]} {lit(float(valor))})"
    if "fase" in cond:
        bit = FASES[cond["fase"]]
        tem = f"(coalesce({alias}.fase_bitmask, 0) & {bit}) <> 0"
        return f"({tem})" if cond["operador"] == "tem" else f"(NOT ({tem}))"
    if "categoria" in cond:
        return (f"(EXISTS (SELECT 1 FROM plat.rede_tipo_categoria rtc JOIN plat.rede_categoria rc "
                f"ON rc.id = rtc.categoria_id WHERE rtc.tipo_id = {alias}.tipo_id "
                f"AND rc.codigo = {lit(cond['categoria'])}))")
    if "grupo" in cond:
        return (f"(EXISTS (SELECT 1 FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
                f"WHERE tp.id = {alias}.tipo_id AND g.codigo = {lit(cond['grupo'])}))")
    return (f"(EXISTS (SELECT 1 FROM plat.rede_tipo tp WHERE tp.id = {alias}.tipo_id "
            f"AND tp.chave = {lit(cond['tipo'])}))")


def _juntar(cur, condicoes: list[dict], alias: str, geometria: str) -> str | None:
    """OR das condições que se aplicam a esta geometria ('ponto' ou 'linha'). None quando nenhuma se aplica."""
    partes = [_sql_condicao(cur, c, alias) for c in condicoes
              if c.get("aplica_a", "ambos") in ("ambos", geometria)]
    return " OR ".join(partes) if partes else None


# --- documento da configuração ---------------------------------------------------------------------------

def validar_documento(cur, rede_id: str, tipo: str, doc: dict) -> dict:
    """Valida e normaliza o documento da configuração contra o catálogo DA REDE. Recusa (422) atributo,
    categoria, grupo, tipo, operador, função ou tipo de resultado que a rede não conhece."""
    if tipo not in TIPOS_CONFIG:
        raise ErroAPI(422, "tipo_invalido", f"tipo deve ser um de {TIPOS_CONFIG}")
    if not isinstance(doc, dict):
        raise ErroAPI(422, "config_invalida", "a configuração é um objeto")
    catalogo = _catalogo(cur, rede_id)
    saida: dict = {}

    for campo in ("barreiras_condicao", "barreiras_filtro"):
        lista = doc.get(campo) or []
        if not isinstance(lista, list) or len(lista) > LIMITE_CONDICOES:
            raise ErroAPI(422, "condicao_invalida",
                          f"{campo}: lista de até {LIMITE_CONDICOES} condições")
        saida[campo] = [_validar_condicao(c, catalogo, campo) for c in lista]

    filtro = doc.get("filtro_saida") or {}
    if not isinstance(filtro, dict):
        raise ErroAPI(422, "filtro_saida_invalido", "filtro_saida é um objeto")
    condicoes = filtro.get("condicoes") or []
    if not isinstance(condicoes, list) or len(condicoes) > LIMITE_CONDICOES:
        raise ErroAPI(422, "condicao_invalida", f"filtro_saida.condicoes: até {LIMITE_CONDICOES} condições")
    estrutura = filtro.get("categorias_estrutura") or list(CATEGORIAS_ESTRUTURA_PADRAO)
    for cat in estrutura:
        if cat not in catalogo["categorias"]:
            raise ErroAPI(422, "categoria_inexistente",
                          f"filtro_saida.categorias_estrutura: a rede não tem a categoria '{cat}'")
    saida["filtro_saida"] = {
        "condicoes": [_validar_condicao(c, catalogo, "filtro_saida") for c in condicoes],
        "incluir_estrutura": bool(filtro.get("incluir_estrutura", False)),
        "categorias_estrutura": list(estrutura),
    }

    funcoes = doc.get("funcoes") or []
    if not isinstance(funcoes, list) or len(funcoes) > LIMITE_FUNCOES:
        raise ErroAPI(422, "funcao_invalida", f"funcoes: até {LIMITE_FUNCOES} funções")
    saida["funcoes"] = []
    for f in funcoes:
        if not isinstance(f, dict):
            raise ErroAPI(422, "funcao_invalida", "cada função é um objeto")
        nome = f.get("funcao")
        if nome not in FUNCOES:
            raise ErroAPI(422, "funcao_invalida", f"função '{nome}' desconhecida; use uma de {FUNCOES}")
        atributo = f.get("atributo")
        if nome != "contagem":
            if atributo not in catalogo["atributos"]:
                raise ErroAPI(422, "atributo_inexistente",
                              f"funcoes: a rede não tem o atributo '{atributo}'")
        elif atributo is not None and atributo not in catalogo["atributos"]:
            raise ErroAPI(422, "atributo_inexistente", f"funcoes: a rede não tem o atributo '{atributo}'")
        onde = f.get("onde") or []
        if not isinstance(onde, list) or len(onde) > LIMITE_CONDICOES:
            raise ErroAPI(422, "condicao_invalida", "funcoes.onde: lista de condições")
        saida["funcoes"].append({
            "codigo": str(f.get("codigo") or nome)[:63],
            "nome": str(f.get("nome") or nome)[:200],
            "funcao": nome,
            "atributo": atributo,
            "unidade": (str(f["unidade"])[:30] if f.get("unidade") else None),
            "onde": [_validar_condicao(c, catalogo, "funcoes.onde") for c in onde],
        })
    codigos = [f["codigo"] for f in saida["funcoes"]]
    if len(set(codigos)) != len(codigos):
        raise ErroAPI(422, "funcao_repetida", "duas funções com o mesmo código na mesma configuração")

    resultado = doc.get("tipo_resultado", "elementos")
    if resultado not in TIPOS_RESULTADO:
        raise ErroAPI(422, "tipo_resultado_invalido",
                      f"tipo_resultado deve ser um de {TIPOS_RESULTADO}")
    saida["tipo_resultado"] = resultado
    saida["origem_direcao"] = doc.get("origem_direcao", "auto")
    if saida["origem_direcao"] not in ("auto", "controlador", "atributo"):
        raise ErroAPI(422, "origem_direcao_invalida", "origem_direcao: auto, controlador ou atributo")
    return saida


# --- CRUD -------------------------------------------------------------------------------------------------

def _ficha(r: dict) -> dict:
    from app.auth.sessao import iso

    return {
        "id": str(r["id"]), "rede_id": str(r["rede_id"]), "codigo": r["codigo"], "nome": r["nome"],
        "descricao": r["descricao"], "tipo": r["tipo"], "config": r["config"], "origem": r["origem"],
        "compartilhada": r["compartilhada"], "dono_id": r["dono_id"],
        "criado_em": iso(r["criado_em"]), "atualizado_em": iso(r["atualizado_em"]),
    }


COLUNAS = ("id, rede_id, codigo, nome, descricao, tipo, config, origem, compartilhada, dono_id, "
           "criado_em, atualizado_em")


def criar(cur, tenant_id: int, rede_id: str, corpo, usuario_id: int, origem: str = "usuario") -> dict:
    config = validar_documento(cur, rede_id, corpo.tipo, corpo.config)
    cur.execute(
        "SELECT 1 FROM plat.rede_config_tracado WHERE rede_id = %s::uuid AND codigo = %s",
        (rede_id, corpo.codigo),
    )
    if cur.fetchone() is not None:
        raise ErroAPI(409, "codigo_repetido",
                      f"esta rede já tem uma configuração de traçado com o código '{corpo.codigo}'")
    cur.execute(
        "INSERT INTO plat.rede_config_tracado "
        "(tenant_id, rede_id, codigo, nome, descricao, tipo, config, origem, compartilhada, dono_id) "
        f"VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {COLUNAS}",
        (tenant_id, rede_id, corpo.codigo, corpo.nome, corpo.descricao, corpo.tipo, Json(config),
         origem, corpo.compartilhada, usuario_id),
    )
    return _ficha(cur.fetchone())


def listar(cur, rede_id: str, usuario_id: int, limite: int = 200) -> list[dict]:
    """As configurações que este usuário vê: as compartilhadas do inquilino e as suas próprias."""
    cur.execute(
        f"SELECT {COLUNAS} FROM plat.rede_config_tracado WHERE rede_id = %s::uuid "
        "AND (compartilhada OR dono_id = %s) ORDER BY origem DESC, codigo LIMIT %s",
        (rede_id, usuario_id, limite),
    )
    return [_ficha(r) for r in cur.fetchall()]


def obter(cur, rede_id: str, config_id: str, usuario_id: int) -> dict:
    cur.execute(
        f"SELECT {COLUNAS} FROM plat.rede_config_tracado WHERE rede_id = %s::uuid AND id = %s::uuid "
        "AND (compartilhada OR dono_id = %s)",
        (rede_id, config_id, usuario_id),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "config_inexistente", "configuração de traçado inexistente nesta rede")
    return _ficha(r)


def atualizar(cur, rede_id: str, config_id: str, corpo, usuario_id: int) -> dict:
    atual = obter(cur, rede_id, config_id, usuario_id)
    config = validar_documento(cur, rede_id, corpo.tipo, corpo.config)
    if corpo.codigo != atual["codigo"]:
        cur.execute("SELECT 1 FROM plat.rede_config_tracado WHERE rede_id = %s::uuid AND codigo = %s",
                    (rede_id, corpo.codigo))
        if cur.fetchone() is not None:
            raise ErroAPI(409, "codigo_repetido",
                          f"esta rede já tem uma configuração com o código '{corpo.codigo}'")
    cur.execute(
        "UPDATE plat.rede_config_tracado SET codigo = %s, nome = %s, descricao = %s, tipo = %s, "
        "config = %s, compartilhada = %s, atualizado_em = now() "
        f"WHERE rede_id = %s::uuid AND id = %s::uuid RETURNING {COLUNAS}",
        (corpo.codigo, corpo.nome, corpo.descricao, corpo.tipo, Json(config), corpo.compartilhada,
         rede_id, config_id),
    )
    return _ficha(cur.fetchone())


def apagar(cur, rede_id: str, config_id: str, usuario_id: int) -> dict:
    ficha = obter(cur, rede_id, config_id, usuario_id)
    cur.execute("DELETE FROM plat.rede_config_tracado WHERE rede_id = %s::uuid AND id = %s::uuid",
                (rede_id, config_id))
    return ficha


# --- execução do traçado a partir da configuração ---------------------------------------------------------

def _resolver_condicoes(cur, rede_id: str, condicoes: list[dict]) -> tuple[list[str], list[str]]:
    """Traduz as condições em (nós de topologia a remover, arestas de topologia a remover). Feição de ponto
    que casa perde os terminais dela; feição de linha que casa perde a aresta dela."""
    if not condicoes:
        return [], []
    nos: list[str] = []
    arestas: list[str] = []
    onde_ponto = _juntar(cur, condicoes, "f", "ponto")
    if onde_ponto:
        cur.execute(
            "SELECT n.id FROM plat.rede_topo_no n JOIN plat.rede_feicao_ponto f ON f.id = n.origem_id "
            f"WHERE n.rede_id = %s::uuid AND n.papel = 'terminal' AND ({onde_ponto})",
            (rede_id,),
        )
        nos = [str(r["id"]) for r in cur.fetchall()]
    onde_linha = _juntar(cur, condicoes, "f", "linha")
    if onde_linha:
        cur.execute(
            "SELECT a.id FROM plat.rede_topo_aresta a JOIN plat.rede_feicao_linha f ON f.id = a.origem_id "
            f"WHERE a.rede_id = %s::uuid AND ({onde_linha})",
            (rede_id,),
        )
        arestas = [str(r["id"]) for r in cur.fetchall()]
    return nos, arestas


def _feicoes_que_passam(cur, rede_id: str, ids: list[str], condicoes: list[dict]) -> set[str]:
    """Dos `ids` de feição, os que satisfazem TODAS as condições do filtro de saída (na geometria de cada um)."""
    if not condicoes:
        return set(ids)
    passam: set[str] = set()
    for tabela, geometria in (("rede_feicao_ponto", "ponto"), ("rede_feicao_linha", "linha")):
        aplicaveis = [c for c in condicoes if c.get("aplica_a", "ambos") in ("ambos", geometria)]
        onde = " AND ".join(_sql_condicao(cur, c, "f") for c in aplicaveis) if aplicaveis else "true"
        cur.execute(
            f"SELECT f.id FROM plat.{tabela} f WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) "
            f"AND ({onde})",
            (rede_id, ids),
        )
        passam |= {str(r["id"]) for r in cur.fetchall()}
    return passam


def _estrutura_coincidente(cur, rede_id: str, nos_alcancados: list[str], categorias: list[str]) -> list[dict]:
    """Feições de estrutura (poste, torre) que coincidem, dentro da tolerância da rede, com um nó alcançado.
    A estrutura não tem terminal e por isso NUNCA é percorrida; é assim que ela entra no resultado."""
    if not nos_alcancados or not categorias:
        return []
    cur.execute(
        "SELECT f.id AS feicao_id, f.tipo_id, t.chave AS tipo_chave, t.nome AS tipo_nome, g.codigo AS grupo "
        "FROM plat.rede_feicao_ponto f "
        "JOIN plat.rede_tipo t ON t.id = f.tipo_id JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "JOIN plat.rede_tipo_categoria rtc ON rtc.tipo_id = f.tipo_id "
        "JOIN plat.rede_categoria rc ON rc.id = rtc.categoria_id "
        "JOIN plat.rede r ON r.id = f.rede_id "
        "WHERE f.rede_id = %s::uuid AND rc.codigo = ANY(%s) AND EXISTS ("
        "  SELECT 1 FROM plat.rede_topo_no n WHERE n.id = ANY(%s::uuid[]) "
        "  AND ST_DWithin(n.geom::geography, f.geom::geography, r.tolerancia_m))",
        (rede_id, list(categorias), nos_alcancados),
    )
    return [{"feicao_id": str(r["feicao_id"]), "tipo_id": str(r["tipo_id"]), "terminal": None,
             "grupo": r["grupo"], "tipo_chave": r["tipo_chave"], "tipo_nome": r["tipo_nome"],
             "origem": "estrutura"} for r in cur.fetchall()]


_AGREGADO = {"soma": "sum", "minimo": "min", "maximo": "max", "media": "avg"}


def _calcular_funcoes(cur, rede_id: str, ids: list[str], funcoes: list[dict]) -> list[dict]:
    saida = []
    for f in funcoes:
        alvo = sorted(_feicoes_que_passam(cur, rede_id, ids, f["onde"])) if f["onde"] else ids
        if f["funcao"] == "contagem":
            valor: float | int | None = len(alvo)
            if f["atributo"]:
                valor = 0
                for tabela in ("rede_feicao_ponto", "rede_feicao_linha"):
                    cur.execute(
                        f"SELECT count(*) AS n FROM plat.{tabela} f WHERE f.rede_id = %s::uuid "
                        "AND f.id = ANY(%s::uuid[]) AND f.atributos ? %s",
                        (rede_id, alvo, f["atributo"]),
                    )
                    valor += cur.fetchone()["n"]
        else:
            agregado = _AGREGADO[f["funcao"]]
            chave = f["atributo"]
            numerico = ("CASE WHEN jsonb_typeof(f.atributos -> %(chave)s) = 'number' "
                        "     THEN (f.atributos ->> %(chave)s)::double precision "
                        "     WHEN f.atributos ->> %(chave)s ~ '^-?[0-9]+([.][0-9]+)?$' "
                        "     THEN (f.atributos ->> %(chave)s)::double precision END")
            cur.execute(
                "SELECT sum(v) AS soma, count(v) AS n, min(v) AS minimo, max(v) AS maximo FROM ("
                f"  SELECT {numerico} AS v FROM plat.rede_feicao_ponto f "
                "   WHERE f.rede_id = %(rede)s::uuid AND f.id = ANY(%(ids)s::uuid[])"
                "  UNION ALL"
                f"  SELECT {numerico} AS v FROM plat.rede_feicao_linha f "
                "   WHERE f.rede_id = %(rede)s::uuid AND f.id = ANY(%(ids)s::uuid[])"
                ") u",
                {"chave": chave, "rede": rede_id, "ids": alvo},
            )
            r = cur.fetchone()
            n = r["n"] or 0
            if n == 0:
                valor = None
            elif agregado == "sum":
                valor = float(r["soma"])
            elif agregado == "min":
                valor = float(r["minimo"])
            elif agregado == "max":
                valor = float(r["maximo"])
            else:
                valor = float(r["soma"]) / n
        saida.append({"codigo": f["codigo"], "nome": f["nome"], "funcao": f["funcao"],
                      "atributo": f["atributo"], "unidade": f["unidade"], "valor": valor,
                      "elementos_considerados": len(alvo)})
    return saida


def _geometria(cur, rede_id: str, ids: list[str]) -> dict | None:
    import json as _json

    if not ids:
        return None
    cur.execute(
        "SELECT ST_AsGeoJSON(ST_Collect(geom)) AS geojson FROM ("
        "  SELECT geom FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])"
        "  UNION ALL"
        "  SELECT geom FROM plat.rede_feicao_linha WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])"
        ") u",
        (rede_id, ids, rede_id, ids),
    )
    r = cur.fetchone()
    return _json.loads(r["geojson"]) if r and r["geojson"] else None


def _conectividade(cur, rede_id: str, ids: list[str]) -> list[dict]:
    cur.execute(
        "SELECT a.origem_id AS feicao_id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
        "WHERE a.rede_id = %s::uuid AND a.origem_id = ANY(%s::uuid[]) "
        "AND a.no_origem_id IS NOT NULL AND a.no_destino_id IS NOT NULL ORDER BY a.criado_em",
        (rede_id, ids),
    )
    return [{"feicao_id": str(r["feicao_id"]), "no_origem": str(r["no_origem_id"]),
             "no_destino": str(r["no_destino_id"])} for r in cur.fetchall()]


def _rodar_motor(cur, tenant_id, rede_id, tipo, pontos, barreiras, arestas, origem_direcao):
    from app.rede_utilidades import direcao as _dir
    from app.rede_utilidades import tracado as _tr

    if tipo in _tr.TIPOS_TRACADO:
        return _tr.tracar(cur, tenant_id, rede_id, tipo, pontos, barreiras, arestas_excluidas=arestas)
    return _dir.tracar_direcao(cur, tenant_id, rede_id, tipo, pontos, barreiras, origem_direcao,
                               arestas_excluidas=arestas)


def executar(cur, tenant_id: int, rede_id: str, ficha: dict, pontos_partida: list[dict],
             barreiras_pedido: list[dict]) -> dict:
    """Roda o traçado descrito pela configuração e devolve o resultado já filtrado, com as funções calculadas
    e no tipo de resultado pedido. O motor é o mesmo de sempre; aqui só se decide o pedido e o resumo."""
    from app.rede_utilidades import tracado as _tr

    inicio = time.perf_counter()
    cfg = ficha["config"] or {}
    tipo = ficha["tipo"]
    nos_cond, arestas_cond = _resolver_condicoes(cur, rede_id, cfg.get("barreiras_condicao") or [])

    cur.execute("SELECT tolerancia_m FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    tolerancia = float(linha["tolerancia_m"])
    ids_inicio = {_tr._resolver_ponto(cur, rede_id, tolerancia, p) for p in pontos_partida}
    # ponto de partida nunca é apagado pela própria configuração (ver docstring do módulo)
    nos_cond = [n for n in nos_cond if n not in ids_inicio]
    barreiras_cond = list(barreiras_pedido) + [{"no_id": n} for n in nos_cond]

    bruto = _rodar_motor(cur, tenant_id, rede_id, tipo, pontos_partida, barreiras_cond, arestas_cond,
                         cfg.get("origem_direcao", "auto"))
    elementos = list(bruto.get("elementos") or [])

    filtros = cfg.get("barreiras_filtro") or []
    passagens = 1
    if filtros and elementos:
        nos_f, arestas_f = _resolver_condicoes(cur, rede_id, filtros)
        nos_f = [n for n in nos_f if n not in ids_inicio]
        segundo = _rodar_motor(
            cur, tenant_id, rede_id, tipo, pontos_partida,
            barreiras_cond + [{"no_id": n} for n in nos_f], arestas_cond + arestas_f,
            cfg.get("origem_direcao", "auto"))
        mantidos = {(e["feicao_id"], e.get("terminal")) for e in (segundo.get("elementos") or [])}
        elementos = [e for e in elementos if (e["feicao_id"], e.get("terminal")) in mantidos]
        passagens = 2

    filtro = cfg.get("filtro_saida") or {}
    ids = sorted({e["feicao_id"] for e in elementos})
    if filtro.get("condicoes"):
        passam = _feicoes_que_passam(cur, rede_id, ids, filtro["condicoes"])
        elementos = [e for e in elementos if e["feicao_id"] in passam]
        ids = sorted(passam & set(ids))

    estruturas = []
    if filtro.get("incluir_estrutura"):
        cur.execute(
            "SELECT id FROM plat.rede_topo_no WHERE rede_id = %s::uuid AND papel = 'terminal' "
            "AND origem_id = ANY(%s::uuid[])",
            (rede_id, sorted({e["feicao_id"] for e in (bruto.get("elementos") or [])})),
        )
        nos_alcancados = [str(r["id"]) for r in cur.fetchall()]
        estruturas = _estrutura_coincidente(
            cur, rede_id, nos_alcancados, filtro.get("categorias_estrutura") or [])
        elementos = elementos + estruturas
        ids = sorted(set(ids) | {e["feicao_id"] for e in estruturas})

    funcoes = _calcular_funcoes(cur, rede_id, ids, cfg.get("funcoes") or [])
    tipo_resultado = cfg.get("tipo_resultado", "elementos")
    saida = {
        "tipo": tipo,
        "config": {"id": ficha["id"], "codigo": ficha["codigo"], "nome": ficha["nome"],
                   "origem": ficha["origem"]},
        "tipo_resultado": tipo_resultado,
        "contagem": len(elementos),
        "funcoes": funcoes,
        "passagens": passagens,
        "barreiras_de_condicao": {"nos": len(nos_cond), "arestas": len(arestas_cond)},
        "estruturas_incluidas": len(estruturas),
        "nos_alcancados": bruto.get("nos_alcancados"),
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
    }
    for extra in ("origem_direcao", "direcao", "motivo", "nos_do_laco", "controladores", "avisos"):
        if extra in bruto:
            saida[extra] = bruto[extra]
    if tipo_resultado == "elementos":
        saida["elementos"] = elementos
        saida["geometria"] = _geometria(cur, rede_id, ids)
    elif tipo_resultado == "geometria":
        saida["elementos"] = []
        saida["geometria"] = _geometria(cur, rede_id, ids)
    else:
        saida["elementos"] = []
        saida["geometria"] = None
        saida["conectividade"] = _conectividade(cur, rede_id, ids)
    return saida


# --- configurações prontas do pacote ----------------------------------------------------------------------
#
# Estas seis vêm com o pacote elétrica-BR, com `origem='pacote'`. Ficam aqui, e não dentro do arquivo do
# pacote, porque o esquema JSON do pacote é fechado (`additionalProperties: false`, `esquema_versao 1`) e
# acrescentar uma seção nova a ele obrigaria a subir a versão do esquema e reimportar todo pacote já
# instalado. Elas são semeadas na importação do pacote (`deposito.importar`), na rede do inquilino, e a
# partir daí são linhas comuns de `plat.rede_config_tracado`: dá para editar, copiar e apagar.

CONFIGS_PADRAO = {
    "eletrica-br": [
        {
            "codigo": "clientes_a_jusante",
            "nome": "Clientes a jusante",
            "descricao": "Unidades consumidoras e pontos de iluminação alimentados a partir do ponto "
                         "escolhido, com a contagem.",
            "tipo": "jusante",
            "config": {
                "filtro_saida": {"condicoes": [{"categoria": "consumo"}]},
                "funcoes": [{"codigo": "clientes", "nome": "Clientes a jusante", "funcao": "contagem"}],
                "tipo_resultado": "elementos",
            },
        },
        {
            "codigo": "kva_a_jusante",
            "nome": "kVA instalado a jusante",
            "descricao": "Soma da potência nominal dos transformadores de distribuição alimentados a "
                         "partir do ponto escolhido.",
            "tipo": "jusante",
            "config": {
                "filtro_saida": {"condicoes": [{"grupo": "transformador_de_distribuicao"}]},
                "funcoes": [{"codigo": "kva_instalado", "nome": "Potência instalada a jusante",
                             "funcao": "soma", "atributo": "pot_nom", "unidade": "kVA"}],
                "tipo_resultado": "elementos",
            },
        },
        {
            "codigo": "isolamento_por_fusivel",
            "nome": "Isolamento por chave fusível",
            "descricao": "O que fica sem energia a jusante do ponto escolhido quando a próxima chave "
                         "fusível abre: o traçado para na primeira chave fusível de cada caminho.",
            "tipo": "jusante",
            "config": {
                "barreiras_condicao": [{"tipo": "chave_fusivel", "aplica_a": "ponto"}],
                "funcoes": [
                    {"codigo": "clientes", "nome": "Clientes afetados", "funcao": "contagem",
                     "onde": [{"categoria": "consumo"}]},
                    {"codigo": "kva", "nome": "Potência afetada", "funcao": "soma", "atributo": "pot_nom",
                     "unidade": "kVA", "onde": [{"grupo": "transformador_de_distribuicao"}]},
                ],
                "tipo_resultado": "elementos",
            },
        },
        {
            "codigo": "alimentador_inteiro",
            "nome": "Alimentador inteiro",
            "descricao": "Tudo que pertence à mesma subrede do ponto escolhido: o traçado atravessa chave "
                         "fechada e para no transformador, que separa duas subredes. Devolve a geometria "
                         "agregada e a extensão declarada.",
            "tipo": "subrede",
            "config": {
                "funcoes": [{"codigo": "extensao", "nome": "Extensão declarada", "funcao": "soma",
                             "atributo": "comp", "unidade": "unidade do arquivo, detectada"}],
                "tipo_resultado": "geometria",
            },
        },
        {
            "codigo": "protetores_a_montante",
            "nome": "Protetores a montante",
            "descricao": "Os dispositivos de proteção entre o ponto escolhido e a fonte, na ordem em que "
                         "o traçado a montante os encontra.",
            "tipo": "montante",
            "config": {
                "filtro_saida": {"condicoes": [{"categoria": "dispositivo_de_protecao"}]},
                "funcoes": [{"codigo": "protetores", "nome": "Protetores a montante", "funcao": "contagem"}],
                "tipo_resultado": "elementos",
            },
        },
        {
            "codigo": "trechos_sem_fase_c",
            "nome": "Trechos sem fase C",
            "descricao": "Os trechos alcançáveis a partir do ponto escolhido cujo cadastro não declara a "
                         "fase C — leitura de qualidade de cadastro, não de defeito na rede.",
            "tipo": "conectado",
            "config": {
                "filtro_saida": {"condicoes": [
                    {"categoria": "conducao"},
                    {"fase": "C", "operador": "nao_tem", "aplica_a": "linha"},
                ]},
                "funcoes": [{"codigo": "extensao", "nome": "Extensão sem fase C", "funcao": "soma",
                             "atributo": "comp", "unidade": "unidade do arquivo, detectada"}],
                "tipo_resultado": "elementos",
            },
        },
    ],
}


class _CorpoPadrao:
    """Adaptador mínimo: `criar` lê os mesmos campos do modelo de entrada da rota."""

    def __init__(self, d: dict):
        self.codigo = d["codigo"]
        self.nome = d["nome"]
        self.descricao = d.get("descricao")
        self.tipo = d["tipo"]
        self.config = d["config"]
        self.compartilhada = True


def semear(cur, tenant_id: int, rede_id: str, codigo_pacote: str, usuario_id: int) -> int:
    """Instala as configurações prontas do pacote nesta rede. Idempotente: código já existente é pulado."""
    n = 0
    for bruto in CONFIGS_PADRAO.get(codigo_pacote, []):
        cur.execute("SELECT 1 FROM plat.rede_config_tracado WHERE rede_id = %s::uuid AND codigo = %s",
                    (rede_id, bruto["codigo"]))
        if cur.fetchone() is not None:
            continue
        criar(cur, tenant_id, rede_id, _CorpoPadrao(bruto), usuario_id, origem="pacote")
        n += 1
    return n
