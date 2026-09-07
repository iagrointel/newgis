"""Categorias de tipo, restrição de feição e traçado de isolamento (item L4-06-d-categorias-e-restricoes).

`L4-01-a-pacote-de-ativos` já entrega o ESQUEMA (`plat.rede_categoria` + `plat.rede_tipo_categoria`, carregado
do pacote de ativos). Este módulo entrega o que falta para as cláusulas do portão: alterar as categorias de um
tipo já em uso (marcando área suja em toda feição do tipo), declarar restrição de feição por tipo
(`sem_ponto_partida`, `sem_terminal`), instanciar feição/ligação, e um traçado de isolamento simples que para
na categoria `dispositivo_de_protecao` — o equivalente do "isolamento usa a categoria 'proteção'".

Escopo declarado (para os itens seguintes de L4 não refazerem decisão): `plat.rede_feicao` é a feição mínima,
sem geometria; a topologia derivada de camada é L4-01-b; área suja como extensão espacial e ciclo de validação
completo são L4-03-d; controlador com nome de subrede é L4-04-a. O traçado aqui é um passeio em largura sobre
`plat.rede_feicao_ligacao` que ilustra a regra ("isolamento para na proteção"), não o motor de traçado
completo (múltiplas fases, barreiras configuráveis, atributos de rede) — esse é item de linha própria."""

import psycopg2

from app.erros import ErroAPI

RESTRICOES_VALIDAS = ("sem_ponto_partida", "sem_terminal")
CATEGORIA_PROTECAO = "dispositivo_de_protecao"
CATEGORIA_CONTROLADOR = "controlador"


def _tipo(cur, rede_id: str, tipo_id: str) -> dict:
    cur.execute(
        "SELECT id, grupo_id, codigo, chave, nome FROM plat.rede_tipo WHERE id = %s::uuid AND rede_id = %s::uuid",
        (tipo_id, rede_id),
    )
    t = cur.fetchone()
    if t is None:
        raise ErroAPI(404, "tipo_inexistente", "tipo de ativo inexistente nesta rede")
    return t


def _categorias_do_tipo(cur, rede_id: str, tipo_id: str) -> set[str]:
    cur.execute(
        "SELECT c.codigo FROM plat.rede_tipo_categoria tc JOIN plat.rede_categoria c ON c.id = tc.categoria_id "
        "WHERE tc.rede_id = %s::uuid AND tc.tipo_id = %s::uuid",
        (rede_id, tipo_id),
    )
    return {r["codigo"] for r in cur.fetchall()}


def redefinir_categorias(cur, tenant_id: int, rede_id: str, tipo_id: str, codigos: list[str]) -> dict:
    """Substitui o conjunto de categorias do tipo. Recusa código de categoria que o pacote não declarou
    (422) e recusa remover 'controlador' de tipo com feição de controlador ATIVO (409) — é a refutação do
    item. Toda feição do tipo nasce/some suja: aqui ela é marcada suja de novo, porque o traçado que a
    consumia pode ter sido invalidado pela mudança de categoria."""
    _tipo(cur, rede_id, tipo_id)
    depois = set(dict.fromkeys(codigos))  # preserva only-uniqueness; ordem não importa para o conjunto

    cur.execute("SELECT codigo, id FROM plat.rede_categoria WHERE rede_id = %s::uuid", (rede_id,))
    disponiveis = {r["codigo"]: r["id"] for r in cur.fetchall()}
    desconhecidas = sorted(depois - disponiveis.keys())
    if desconhecidas:
        raise ErroAPI(422, "categoria_inexistente",
                      f"categoria(s) não declarada(s) no pacote desta rede: {', '.join(desconhecidas)}")

    antes = _categorias_do_tipo(cur, rede_id, tipo_id)
    removidas = antes - depois
    if CATEGORIA_CONTROLADOR in removidas:
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_feicao WHERE rede_id = %s::uuid AND tipo_id = %s::uuid "
            "AND controlador_ativo",
            (rede_id, tipo_id),
        )
        n_ativos = cur.fetchone()["n"]
        if n_ativos:
            raise ErroAPI(409, "controlador_ativo_bloqueia_categoria",
                          f"{n_ativos} feição(ões) deste tipo têm controlador ativo; desligue-o(s) antes de "
                          "remover a categoria 'controlador'", {"feicoes_controlador_ativo": n_ativos})

    cur.execute(
        "DELETE FROM plat.rede_tipo_categoria WHERE rede_id = %s::uuid AND tipo_id = %s::uuid", (rede_id, tipo_id)
    )
    for codigo in sorted(depois):
        cur.execute(
            "INSERT INTO plat.rede_tipo_categoria(tenant_id, rede_id, tipo_id, categoria_id) VALUES (%s, %s, %s, %s)",
            (tenant_id, rede_id, tipo_id, disponiveis[codigo]),
        )

    cur.execute(
        "UPDATE plat.rede_feicao SET suja = true WHERE rede_id = %s::uuid AND tipo_id = %s::uuid",
        (rede_id, tipo_id),
    )
    marcadas = cur.rowcount
    return {"antes": sorted(antes), "depois": sorted(depois), "feicoes_marcadas_sujas": marcadas}


def redefinir_restricoes(cur, tenant_id: int, rede_id: str, tipo_id: str, restricoes: list[str]) -> dict:
    """Substitui o conjunto de restrições de feição do tipo. Vocabulário fechado (pydantic já valida o
    formato; aqui confere de novo porque a função também é chamada fora da rota, em teste)."""
    _tipo(cur, rede_id, tipo_id)
    depois = set(restricoes)
    fora = sorted(depois - set(RESTRICOES_VALIDAS))
    if fora:
        raise ErroAPI(422, "restricao_desconhecida", f"restrição(ões) fora do vocabulário: {', '.join(fora)}")

    cur.execute(
        "SELECT restricao FROM plat.rede_tipo_restricao WHERE rede_id = %s::uuid AND tipo_id = %s::uuid",
        (rede_id, tipo_id),
    )
    antes = {r["restricao"] for r in cur.fetchall()}
    cur.execute(
        "DELETE FROM plat.rede_tipo_restricao WHERE rede_id = %s::uuid AND tipo_id = %s::uuid", (rede_id, tipo_id)
    )
    for restricao in sorted(depois):
        cur.execute(
            "INSERT INTO plat.rede_tipo_restricao(tenant_id, rede_id, tipo_id, restricao) VALUES (%s, %s, %s, %s)",
            (tenant_id, rede_id, tipo_id, restricao),
        )
    return {"antes": sorted(antes), "depois": sorted(depois)}


def criar_feicao(cur, tenant_id: int, rede_id: str, tipo_id: str, codigo: str, controlador_ativo: bool) -> dict:
    _tipo(cur, rede_id, tipo_id)

    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao(tenant_id, rede_id, tipo_id, codigo, controlador_ativo, suja) "
            "VALUES (%s, %s::uuid, %s::uuid, %s, %s, true) RETURNING id, codigo, controlador_ativo, suja",
            (tenant_id, rede_id, tipo_id, codigo, controlador_ativo),
        )
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "feicao_existente", "já existe feição com esse código para este tipo") from e
    r = cur.fetchone()
    return {"id": str(r["id"]), "tipo_id": tipo_id, "codigo": r["codigo"],
            "controlador_ativo": r["controlador_ativo"], "suja": r["suja"]}


def _feicao(cur, rede_id: str, feicao_id: str) -> dict:
    cur.execute(
        "SELECT id, tipo_id, codigo, controlador_ativo, suja FROM plat.rede_feicao "
        "WHERE id = %s::uuid AND rede_id = %s::uuid",
        (feicao_id, rede_id),
    )
    f = cur.fetchone()
    if f is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta rede")
    return f


def ligar_feicoes(cur, tenant_id: int, rede_id: str, de_id: str, para_id: str) -> dict:
    """Cria a aresta de conectividade entre duas feições da mesma rede (par não dirigido; a coluna
    `de_feicao_id` armazena sempre o menor uuid em forma de texto, como a migração exige)."""
    if de_id == para_id:
        raise ErroAPI(422, "ligacao_reflexiva", "uma feição não pode se ligar a si mesma")
    _feicao(cur, rede_id, de_id)
    _feicao(cur, rede_id, para_id)
    a, b = sorted((de_id, para_id))

    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao_ligacao(tenant_id, rede_id, de_feicao_id, para_feicao_id) "
            "VALUES (%s, %s::uuid, %s::uuid, %s::uuid) RETURNING id",
            (tenant_id, rede_id, a, b),
        )
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "ligacao_existente", "já existe ligação entre essas duas feições") from e
    r = cur.fetchone()
    return {"id": str(r["id"]), "de_feicao_id": a, "para_feicao_id": b}


def isolar(cur, rede_id: str, partida_feicao_id: str) -> dict:
    """Passeio em largura a partir de `partida_feicao_id` sobre `plat.rede_feicao_ligacao`, que NÃO atravessa
    feição cujo tipo tem a categoria 'dispositivo_de_protecao' — a proteção entra no resultado (é o ponto
    onde o isolamento "corta"), mas seus vizinhos não são expandidos. Recusa (422) partir de feição cujo tipo
    tem a restrição 'sem_ponto_partida' — o caso do portão é a unidade consumidora."""
    partida = _feicao(cur, rede_id, partida_feicao_id)
    cur.execute(
        "SELECT 1 FROM plat.rede_tipo_restricao WHERE rede_id = %s::uuid AND tipo_id = %s::uuid "
        "AND restricao = 'sem_ponto_partida'",
        (rede_id, partida["tipo_id"]),
    )
    if cur.fetchone() is not None:
        raise ErroAPI(422, "ponto_partida_restrito",
                      "o tipo desta feição está configurado com a restrição 'sem_ponto_partida'")

    cur.execute(
        "SELECT de_feicao_id, para_feicao_id FROM plat.rede_feicao_ligacao WHERE rede_id = %s::uuid",
        (rede_id,),
    )
    vizinhos: dict[str, set[str]] = {}
    for r in cur.fetchall():
        de, pa = str(r["de_feicao_id"]), str(r["para_feicao_id"])
        vizinhos.setdefault(de, set()).add(pa)
        vizinhos.setdefault(pa, set()).add(de)

    cur.execute(
        "SELECT tf.id AS feicao_id, c.codigo = %s AS eh_protecao "
        "FROM plat.rede_feicao tf "
        "JOIN plat.rede_tipo_categoria tc ON tc.tipo_id = tf.tipo_id AND tc.rede_id = tf.rede_id "
        "JOIN plat.rede_categoria c ON c.id = tc.categoria_id AND c.codigo = %s "
        "WHERE tf.rede_id = %s::uuid",
        (CATEGORIA_PROTECAO, CATEGORIA_PROTECAO, rede_id),
    )
    protecao = {str(r["feicao_id"]) for r in cur.fetchall()}

    partida_id = str(partida["id"])
    visitadas = {partida_id}
    fronteira_protecao: set[str] = set()
    fila = [partida_id]
    while fila:
        atual = fila.pop(0)
        if atual in protecao and atual != partida_id:
            fronteira_protecao.add(atual)
            continue  # entra no resultado, mas o isolamento não passa por ela
        for viz in vizinhos.get(atual, ()):
            if viz not in visitadas:
                visitadas.add(viz)
                fila.append(viz)

    return {
        "partida_feicao_id": partida_id,
        "visitadas": sorted(visitadas),
        "fronteira_protecao": sorted(fronteira_protecao),
        "total_visitadas": len(visitadas),
    }
