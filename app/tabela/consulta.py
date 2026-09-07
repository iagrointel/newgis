"""Leitura da tabela física de uma camada vetorial para a tabela de atributos (item L2-01-g-tabela-atributos).

Este módulo monta SQL sobre uma tabela que NÃO é do schema `plat`: é a tabela de feições que a ingestão
criou (`d_<slug>.c_<16 hex>`, migração 029), com RLS por inquilino instalada por `plat.camada_preparar()`.
Duas consequências de desenho, e as duas valem como defesa:

1. **Nenhum identificador vem do pedido.** A lista de colunas que podem ser lidas, ordenadas, buscadas ou
   agregadas sai do CATÁLOGO DO BANCO (`information_schema.columns` da própria tabela), nunca do corpo da
   requisição. O que o cliente manda é um NOME, que é procurado nessa lista; não achou, é 422. Por isso
   `ordenar_por=nome; DROP TABLE` ou `ordenar_por=(SELECT ...)` não chega a virar SQL — morre na busca do
   nome. O nome achado ainda assim é escrito entre aspas duplas com as aspas internas dobradas.
2. **O isolamento não depende deste arquivo.** Mesmo que uma consulta daqui esquecesse o inquilino, a RLS
   FORCE da tabela de feições (`tenant_id = plat.tenant_atual()`) devolveria zero linha. O filtro de
   inquilino aqui seria redundante e por isso não existe: a única porta é a mesma que o resto da aplicação
   usa (`app.db.db(auth.contexto())`, que faz `set_config('plat.tenant_id', ...)`).

A busca em texto usa `unaccent` + `lower` + `LIKE` (a extensão `unaccent` está instalada no banco, schema
`public`). Não é `ILIKE` puro porque o pedido do item é "busca por texto em todas as colunas de texto
(ILIKE + unaccent)" — sem `unaccent` "sao paulo" não acha "São Paulo". `unaccent()` não é imutável, então
não há índice funcional para ela; a busca é varredura, e é isso que ela é em qualquer produto desta classe
(o Map Viewer também varre). Quem precisa de velocidade em texto usa filtro por coluna, não busca livre."""

import re

from app import limites
from app.erros import ErroAPI

# tipos internos do Postgres (udt_name), não o `data_type` legível: 'character varying' vira 'varchar' aqui,
# e é o udt_name que distingue geometry de qualquer outra coisa sem depender de PostGIS estar no search_path.
TIPOS_TEXTO = ("text", "varchar", "bpchar", "char", "name", "citext")
TIPOS_NUMERO = ("int2", "int4", "int8", "float4", "float8", "numeric", "money")
TIPOS_DATA = ("date", "timestamp", "timestamptz", "time", "timetz")
TIPOS_GEOMETRIA = ("geometry", "geography")
RE_IDENTIFICADOR = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _ident(nome: str) -> str:
    """Identificador citado. Só chega aqui nome que já veio do catálogo do banco; a citação é a segunda trava."""
    return '"' + nome.replace('"', '""') + '"'


def classe_do_tipo(udt: str) -> str:
    if udt in TIPOS_GEOMETRIA:
        return "geometria"
    if udt in TIPOS_TEXTO:
        return "texto"
    if udt in TIPOS_NUMERO:
        return "numero"
    if udt in TIPOS_DATA:
        return "data"
    if udt == "bool":
        return "logico"
    if udt == "uuid":
        return "uuid"
    return "outro"


def origem_da_camada(item: dict) -> tuple[str, str, int]:
    """(schema, tabela, srid) do item de catálogo `camada_vetorial`, com os nomes conferidos contra a mesma
    forma que a migração 029 aceita. Camada referenciada (sem tabela própria) não tem tabela de atributos
    hospedada — é 409, não 500."""
    dados = item.get("dados") or {}
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not isinstance(schema, str) or not isinstance(tabela, str):
        raise ErroAPI(409, "camada_sem_tabela", "esta camada não tem tabela de atributos hospedada")
    if not RE_IDENTIFICADOR.match(schema) or not RE_IDENTIFICADOR.match(tabela):
        raise ErroAPI(409, "camada_sem_tabela", "esta camada não tem tabela de atributos hospedada")
    srid = dados.get("srid")
    return schema, tabela, int(srid) if isinstance(srid, int) else 4326


def colunas_do_banco(cur, schema: str, tabela: str) -> list[dict]:
    """Colunas REAIS da tabela de feições, na ordem física. Autoridade sobre o que existe; o item de catálogo
    só acrescenta rótulo (alias). Tabela inexistente devolve lista vazia (o chamador vira 404)."""
    cur.execute(
        "SELECT column_name AS nome, udt_name AS udt, is_nullable = 'YES' AS aceita_nulo "
        "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position",
        (schema, tabela),
    )
    return [
        {"nome": r["nome"], "udt": r["udt"], "tipo": classe_do_tipo(r["udt"]), "aceita_nulo": r["aceita_nulo"]}
        for r in cur.fetchall()
    ]


def coluna_chave(cur, schema: str, tabela: str) -> str | None:
    """Nome da coluna da chave primária (uma só coluna). É o identificador que a linha da tabela e a feição do
    mapa compartilham; sem ela não há como casar seleção com linha."""
    cur.execute(
        "SELECT a.attname AS nome FROM pg_index i "
        "JOIN pg_class c ON c.oid = i.indrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey) "
        "WHERE n.nspname = %s AND c.relname = %s AND i.indisprimary AND i.indnatts = 1",
        (schema, tabela),
    )
    r = cur.fetchone()
    return r["nome"] if r else None


def coluna_geometria(colunas: list[dict]) -> str | None:
    for c in colunas:
        if c["tipo"] == "geometria":
            return c["nome"]
    return None


def achar(colunas: list[dict], nome: str, campo: str) -> dict:
    for c in colunas:
        if c["nome"] == nome:
            return c
    raise ErroAPI(422, "coluna_invalida", f"{campo}: a camada não tem a coluna {nome!r}")


def _escapar_like(termo: str) -> str:
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filtro(colunas: list[dict], chave: str | None, geom: str | None, srid: int, pedido: dict) -> tuple[str, list]:
    """`WHERE` da tabela: busca em texto, extensão do mapa e seleção. Devolve (sql, parâmetros); sql vazio
    quando não há filtro nenhum (o chamador põe o `WHERE` só se houver)."""
    partes: list[str] = []
    params: list = []

    busca = (pedido.get("busca") or "").strip()
    if busca:
        if len(busca) > limites.TABELA_BUSCA_MAX:
            raise ErroAPI(422, "busca_longa", f"a busca aceita no máximo {limites.TABELA_BUSCA_MAX} caracteres")
        colunas_texto = [c for c in colunas if c["tipo"] == "texto"]
        if not colunas_texto:
            partes.append("false")
        else:
            alvo = f"%{_escapar_like(busca.lower())}%"
            ors = []
            for c in colunas_texto:
                ors.append(f"public.unaccent(lower({_ident(c['nome'])}::text)) LIKE public.unaccent(%s) ESCAPE '\\'")
                params.append(alvo)
            partes.append("(" + " OR ".join(ors) + ")")

    bbox = pedido.get("bbox")
    if bbox:
        if not geom:
            raise ErroAPI(422, "camada_sem_geometria",
                          "esta camada não tem geometria; o filtro de extensão não se aplica")
        if len(bbox) != 4:
            raise ErroAPI(422, "bbox_invalida", "bbox precisa de [oeste, sul, leste, norte]")
        oeste, sul, leste, norte = (float(v) for v in bbox)
        if not (-180 <= oeste <= 180 and -180 <= leste <= 180 and -90 <= sul <= 90 and -90 <= norte <= 90):
            raise ErroAPI(422, "bbox_invalida", "bbox fora do intervalo geográfico")
        if oeste >= leste or sul >= norte:
            raise ErroAPI(422, "bbox_invalida", "bbox precisa de oeste < leste e sul < norte")
        # `&&` usa o índice GIST que camada_preparar() criou; ST_Intersects refina o retângulo envolvente.
        alvo = f"ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), {srid})"
        partes.append(f"({_ident(geom)} && {alvo} AND ST_Intersects({_ident(geom)}, {alvo}))")
        params.extend([oeste, sul, leste, norte, oeste, sul, leste, norte])

    fids = pedido.get("fids")
    if fids:
        if not chave:
            raise ErroAPI(409, "camada_sem_chave", "esta camada não tem chave primária de uma coluna")
        if len(fids) > limites.TABELA_FIDS_MAX:
            raise ErroAPI(422, "selecao_grande", f"a seleção aceita no máximo {limites.TABELA_FIDS_MAX} feições")
        partes.append(f"{_ident(chave)} = ANY(%s)")
        params.append([int(v) for v in fids])

    return (" AND ".join(partes), params)


def ordenacao(colunas: list[dict], chave: str | None, ordenar_por: str | None, ordem: str) -> str:
    """`ORDER BY` estável: a coluna pedida (conferida contra o catálogo do banco) e, como desempate, a chave —
    sem desempate, duas páginas seguidas podem repetir e pular linhas com valores iguais."""
    direcao = "DESC" if (ordem or "asc").lower() == "desc" else "ASC"
    partes = []
    if ordenar_por:
        c = achar(colunas, ordenar_por, "ordenar_por")
        if c["tipo"] == "geometria":
            raise ErroAPI(422, "coluna_invalida", "ordenar_por: não se ordena por coluna de geometria")
        partes.append(f"{_ident(c['nome'])} {direcao} NULLS LAST")
    if chave:
        partes.append(f"{_ident(chave)} {direcao if not ordenar_por else 'ASC'}")
    if not partes:
        return ""
    return " ORDER BY " + ", ".join(partes)


def selecao(colunas_visiveis: list[dict], chave: str | None, geom: str | None, incluir_geometria: bool) -> str:
    """Lista do `SELECT`. Geometria nunca sai como coluna de atributo: quando pedida, sai como GeoJSON em
    4326, no campo separado `geometria`, para o mapa desenhar a mesma linha que a tabela mostra."""
    partes = [f"{_ident(c['nome'])}" for c in colunas_visiveis if c["tipo"] != "geometria"]
    if chave and chave not in [c["nome"] for c in colunas_visiveis]:
        partes.insert(0, _ident(chave))
    if incluir_geometria and geom:
        partes.append(f"ST_AsGeoJSON(ST_Transform({_ident(geom)}, 4326), 7) AS __geometria")
    return ", ".join(partes) if partes else "1"


def estatisticas_sql(coluna: dict) -> str:
    """Agregados de uma coluna numérica, com os nomes que o portão do item nomeia."""
    c = _ident(coluna["nome"])
    return (
        f"count({c}) AS contagem, sum({c}::numeric) AS soma, avg({c}::numeric) AS media, "
        f"min({c}) AS minimo, max({c}) AS maximo, count(*) FILTER (WHERE {c} IS NULL) AS nulos"
    )


def citar(nome: str) -> str:
    """Exposto para os testes e para quem monte SQL derivado (mesma citação usada aqui)."""
    return _ident(nome)
