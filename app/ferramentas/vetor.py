"""Ferramentas vetoriais elementares em SQL/PostGIS (item L2-05-b), registradas no MESMO registro de
`app/ferramentas/registro.py` e executadas pelo MESMO executor do L2-05-a (em processo abaixo do custo
declarado, senão como job `ferramentas.executar`). Cada ferramenta é uma função
`f(ctx, entradas, parametros, destino)` que escreve `destino.schema.destino.tabela` e devolve
{geometria, srid, campos, metodo}; quem cuida de fid/RLS/item/proveniência é o executor.

Duas regras da casa valem para todas:

1. **ST_MakeValid + ST_ReducePrecision antes de toda operação booleana em massa.** Interseção, união,
   diferença, diferença simétrica, recorte e dissolver passam cada geometria por
   `ST_ReducePrecision(ST_MakeValid(geom), grade)` antes do operador. A grade é fina de propósito
   (1e-11 grau ≈ 1 µm; 1e-6 m em camada projetada): serve para tirar o ruído que faz o GEOS levantar
   "TopologyException", não para generalizar o dado — a diferença de área que ela introduz fica muitas
   ordens de grandeza abaixo da tolerância de 1e-6 relativa com que estas ferramentas são conferidas.
2. **Relatório de inválidas.** Antes de operar, conta as geometrias inválidas de cada entrada
   (`ST_IsValid`), escreve a contagem no log da execução e a carrega no texto do método que fica na
   procedência do item de saída. Quem lê a ficha da camada derivada vê que houve conserto.

Medida geodésica: área, perímetro, comprimento e distância de buffer saem de `geography` (elipsoide
WGS 84), não de graus quadrados. Camada em outra projeção vai e volta por ST_Transform.
"""

from __future__ import annotations

from app import limites
from app.ferramentas.executor import ErroExecucao
from app.ferramentas.registro import Parametro, ferramenta

# grade do ST_ReducePrecision: fina o bastante para não mexer na medida, grossa o bastante para tirar ruído
PRECISAO_GRAU = 1e-11
PRECISAO_METRO = 1e-6
GRAUS_POR_METRO = 1.0 / 111_320.0  # 1 grau de meridiano = 111.320 m (esfera autálica); só para tolerância linear

COLUNAS_SISTEMA = ("fid", "geom", "globalid", "versao", "tenant_id", "criado_em", "atualizado_em",
                   "criado_por", "atualizado_por")

# família da geometria: singular, plural e dimensão (0 ponto, 1 linha, 2 área)
FAMILIAS = {
    "POINT": ("Point", "MultiPoint", 0), "MULTIPOINT": ("Point", "MultiPoint", 0),
    "LINESTRING": ("LineString", "MultiLineString", 1), "MULTILINESTRING": ("LineString", "MultiLineString", 1),
    "POLYGON": ("Polygon", "MultiPolygon", 2), "MULTIPOLYGON": ("Polygon", "MultiPolygon", 2),
}
ESTATISTICAS = {"contagem": "count({c})", "soma": "sum({c})", "media": "avg({c})", "minimo": "min({c})",
                "maximo": "max({c})", "desvio": "stddev_samp({c})"}
NUMERICAS = ("smallint", "integer", "bigint", "numeric", "real", "double precision")


class ErroFerramenta(ErroExecucao):
    """Erro de uso nomeado (422): entrada de família errada, campo inexistente, parâmetro incoerente."""

    def __init__(self, codigo: str, mensagem: str, detalhe=None):
        super().__init__(422, codigo, mensagem, detalhe)


# ---------------------------------------------------------------- apoio comum
def ident(nome: str) -> str:
    """Identificador citado; recusa aspas dentro do nome em vez de escapá-las (nome assim não vem do catálogo)."""
    if not isinstance(nome, str) or not nome or '"' in nome or len(nome) > 63:
        raise ErroFerramenta("campo_invalido", f"nome de coluna inválido: {nome!r}")
    return f'"{nome}"'


def tabela_de(d: dict) -> str:
    return f'{ident(d["schema"])}.{ident(d["tabela"])}'


def familia(entrada: dict) -> tuple[str, str, int]:
    f = FAMILIAS.get(str(entrada.get("geometria", "")).upper())
    if f is None:
        raise ErroFerramenta("geometria_desconhecida",
                             f"camada {entrada['titulo']!r} sem família de geometria declarada")
    return f


def geografico(cur, srid: int) -> bool:
    cur.execute("SELECT proj4text LIKE %s AS g FROM spatial_ref_sys WHERE srid = %s", ("%+proj=longlat%", srid))
    r = cur.fetchone()
    if r is None:
        raise ErroFerramenta("srid_desconhecido", f"SRID {srid} não está em spatial_ref_sys")
    return bool(r["g"])


def limpo(cur, coluna: str, srid: int) -> str:
    """A regra da casa: nenhuma operação booleana em massa recebe geometria crua."""
    grade = PRECISAO_GRAU if geografico(cur, srid) else PRECISAO_METRO
    return f"ST_ReducePrecision(ST_MakeValid({coluna}), {grade})"


def geografia(coluna: str, srid: int) -> str:
    """Expressão `geography` para medida geodésica, venha a camada de onde vier."""
    return f"{coluna}::geography" if srid == 4326 else f"ST_Transform({coluna}, 4326)::geography"


def contar_invalidas(ctx, fontes: list[tuple[str, dict]]) -> dict:
    """{rótulo: nº de geometrias inválidas} nas entradas, com o total no log da execução."""
    relatorio = {}
    with ctx.db() as cur:
        for rotulo, e in fontes:
            cur.execute(f"SELECT count(*) AS n FROM {tabela_de(e)} WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)")
            relatorio[rotulo] = int(cur.fetchone()["n"])
    total = sum(relatorio.values())
    ctx.log("INFO" if total == 0 else "AVISO",
            f"relatório de inválidas: {relatorio} (total {total}; corrigidas por ST_MakeValid)")
    return relatorio


def nota_invalidas(relatorio: dict) -> str:
    total = sum(relatorio.values())
    if not total:
        return ""
    partes = ", ".join(f"{k}={v}" for k, v in relatorio.items() if v)
    return f"; {total} geometria(s) inválida(s) na entrada corrigida(s) por ST_MakeValid ({partes})"


def verificar_tamanho(entradas: dict) -> None:
    for nome, e in entradas.items():
        for uma in e if isinstance(e, list) else [e]:
            if uma["feicoes"] > limites.VETOR_FEICOES_MAX:
                raise ErroFerramenta(
                    "camada_grande_demais",
                    f"{nome}: {uma['feicoes']} feições acima do limite de {limites.VETOR_FEICOES_MAX}",
                    {"campo": nome, "feicoes": uma["feicoes"], "maximo": limites.VETOR_FEICOES_MAX},
                )


def campos_de(cur, schema: str, tabela: str) -> list[dict]:
    """Campos reais da tabela recém-criada (tipo lido do catálogo do Postgres, não adivinhado)."""
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s "
                "AND table_name = %s ORDER BY ordinal_position", (schema, tabela))
    return [{"nome": r["column_name"], "tipo": r["data_type"], "alias": r["column_name"]}
            for r in cur.fetchall() if r["column_name"] not in COLUNAS_SISTEMA]


def tipos_de(cur, schema: str, tabela: str) -> dict:
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s "
                "AND table_name = %s ORDER BY ordinal_position", (schema, tabela))
    return {r["column_name"]: r["data_type"] for r in cur.fetchall() if r["column_name"] not in COLUNAS_SISTEMA}


def escrever(ctx, destino: dict, select_sql: str, tipo_geom: str, srid: int) -> list[dict]:
    """CREATE TABLE AS + fid + tipagem da coluna geom; devolve os campos publicados no item.

    Descarta linha com geometria nula ou vazia (recorte que não pegou nada, diferença que consumiu tudo):
    o resultado é uma camada com menos feições, nunca uma camada com buraco.
    """
    alvo = tabela_de(destino)
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} AS {select_sql}")
        cur.execute(f"DELETE FROM {alvo} WHERE geom IS NULL OR ST_IsEmpty(geom)")
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
        cur.execute(f"ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry({tipo_geom}, {srid}) USING geom")
        campos = campos_de(cur, destino["schema"], destino["tabela"])
    return campos


def lista_campos(e: dict, prefixo: str = "", apelido: str = "") -> str:
    """Trecho SELECT com os campos declarados de uma entrada; o prefixo evita colisão de nome na sobreposição."""
    origem = f"{apelido}." if apelido else ""
    return ", ".join(f"{origem}{ident(c)} AS {ident(f'{prefixo}{c}')}" for c in e["campos"])


def com_virgula(*partes: str) -> str:
    """Junta trechos de coluna não vazios e deixa a vírgula final para a geometria vir em seguida."""
    junta = ", ".join(x for x in partes if x)
    return f"{junta}, " if junta else ""


def no_srid_de(coluna: str, origem: dict, alvo_srid: int) -> str:
    """A geometria de `origem` escrita no SRID de destino (sem limpeza: serve para o teste de índice)."""
    return coluna if origem["srid"] == alvo_srid else f"ST_Transform({coluna}, {alvo_srid})"


class Sobreposicao:
    """Preparação comum das ferramentas de sobreposição: SRID único, expressões já limpas pela regra da casa
    (ST_MakeValid + ST_ReducePrecision), dimensão do resultado e relatório de inválidas."""

    def __init__(self, ctx, a: dict, b: dict, rotulos=("camada_a", "camada_b")):
        self.a, self.b, self.srid = a, b, a["srid"]
        self.bruto_a = "a.geom"
        self.bruto_b = no_srid_de("b.geom", b, self.srid)
        with ctx.db() as cur:
            self.expr_a = limpo(cur, self.bruto_a, self.srid)
            self.expr_b = limpo(cur, self.bruto_b, self.srid)
            self.tipos_a = tipos_de(cur, a["schema"], a["tabela"])
            self.tipos_b = tipos_de(cur, b["schema"], b["tabela"])
        self.dimensao = min(familia(a)[2], familia(b)[2])
        self.relatorio = contar_invalidas(ctx, [(rotulos[0], a), (rotulos[1], b)])

    @property
    def tipo_saida(self) -> str:
        return FAMILIAS[["POINT", "LINESTRING", "POLYGON"][self.dimensao]][1]

    def extrair(self, expr: str, dimensao: int | None = None) -> str:
        """Só a dimensão esperada do resultado: a interseção de dois polígonos que apenas se tocam devolve uma
        linha, e essa linha não é feição de saída (mesma decisão do Clip/Intersect do ArcGIS)."""
        d = self.dimensao if dimensao is None else dimensao
        return f"ST_Multi(ST_CollectionExtract({expr}, {d + 1}))"

    def nulos(self, qual: str, prefixo: str) -> str:
        e, tipos = (self.a, self.tipos_a) if qual == "a" else (self.b, self.tipos_b)
        return ", ".join(f"NULL::{tipos.get(c, 'text')} AS {ident(prefixo + c)}" for c in e["campos"])


def uniao_da(s: Sobreposicao, qual: str) -> str:
    """Subconsulta com a união (já limpa) de uma das camadas — o `erase` do ArcGIS apaga contra a camada inteira."""
    e = s.b if qual == "b" else s.a
    expr = s.expr_b if qual == "b" else s.expr_a
    apelido = "b" if qual == "b" else "a"
    return f"SELECT ST_Union({expr}) AS g FROM {tabela_de(e)} {apelido}"


# ---------------------------------------------------------------- sobreposição
@ferramenta(
    nome="recorte", titulo="Recortar (clip)", categoria="sobreposicao", versao=1,
    descricao="Mantém de cada feição só a parte dentro da camada de recorte; conserva os campos da entrada.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("camada_recorte", "GPFeatureRecordSetLayer", "camada de recorte",
                  descricao="polígonos que delimitam o que fica"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2 + e["camada_recorte"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def recorte(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    a, b = entradas["camada"], entradas["camada_recorte"]
    if familia(b)[2] != 2:
        raise ErroFerramenta("recorte_nao_poligonal", "camada_recorte precisa ser poligonal")
    s = Sobreposicao(ctx, a, b, ("camada", "camada_recorte"))
    campos_sql = lista_campos(a, apelido="a")
    prefixo = com_virgula(campos_sql)
    ctx.progresso(20, "unindo a camada de recorte")
    select = (f"WITH r AS ({uniao_da(s, 'b')}) "
              f"SELECT {prefixo}{s.extrair(f'ST_Intersection({s.expr_a}, r.g)', familia(a)[2])} AS geom "
              f"FROM {tabela_de(a)} a, r WHERE ST_Intersects(a.geom, r.g) ORDER BY a.fid")
    tipo = FAMILIAS[familia(a)[0].upper()][1]
    campos = escrever(ctx, destino, select, tipo, s.srid)
    return {"geometria": tipo, "srid": s.srid, "campos": campos,
            "metodo": "ST_Intersection contra ST_Union da camada de recorte" + nota_invalidas(s.relatorio)}


@ferramenta(
    nome="intersecao", titulo="Interseção", categoria="sobreposicao", versao=1,
    descricao="Uma feição por par que se sobrepõe, com os campos das duas camadas (prefixos a_ e b_).",
    parametros=(
        Parametro("camada_a", "GPFeatureRecordSetLayer", "primeira camada"),
        Parametro("camada_b", "GPFeatureRecordSetLayer", "segunda camada"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: (e["camada_a"]["feicoes"] + e["camada_b"]["feicoes"]) * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def intersecao(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    s = Sobreposicao(ctx, entradas["camada_a"], entradas["camada_b"])
    ca = lista_campos(s.a, "a_", "a")
    cb = lista_campos(s.b, "b_", "b")
    campos_sql = ", ".join(x for x in (ca, cb) if x)
    prefixo = com_virgula(campos_sql)
    ctx.progresso(20, "cruzando as duas camadas")
    select = (f"SELECT {prefixo}{s.extrair(f'ST_Intersection({s.expr_a}, {s.expr_b})')} AS geom "
              f"FROM {tabela_de(s.a)} a JOIN {tabela_de(s.b)} b ON ST_Intersects(a.geom, {s.bruto_b}) "
              f"ORDER BY a.fid, b.fid")
    campos = escrever(ctx, destino, select, s.tipo_saida, s.srid)
    return {"geometria": s.tipo_saida, "srid": s.srid, "campos": campos,
            "metodo": "ST_Intersection par a par" + nota_invalidas(s.relatorio)}


@ferramenta(
    nome="uniao", titulo="União (union)", categoria="sobreposicao", versao=1,
    descricao="Recorta as duas camadas poligonais uma pela outra: sobreposição, só A e só B, num único conjunto.",
    parametros=(
        Parametro("camada_a", "GPFeatureRecordSetLayer", "primeira camada"),
        Parametro("camada_b", "GPFeatureRecordSetLayer", "segunda camada"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: (e["camada_a"]["feicoes"] + e["camada_b"]["feicoes"]) * 4,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def uniao(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    s = Sobreposicao(ctx, entradas["camada_a"], entradas["camada_b"])
    if familia(s.a)[2] != 2 or familia(s.b)[2] != 2:
        raise ErroFerramenta("uniao_nao_poligonal", "união exige as duas camadas poligonais")
    ca = lista_campos(s.a, "a_", "a")
    cb = lista_campos(s.b, "b_", "b")
    ca_nulo, cb_nulo = s.nulos("a", "a_"), s.nulos("b", "b_")
    ctx.progresso(20, "sobreposição das duas camadas")
    sobrepoe = (f"SELECT 'ambas'::text AS origem, {com_virgula(ca, cb)}"
                f"{s.extrair(f'ST_Intersection({s.expr_a}, {s.expr_b})')} AS geom "
                f"FROM {tabela_de(s.a)} a JOIN {tabela_de(s.b)} b ON ST_Intersects(a.geom, {s.bruto_b})")
    so_a = (f"SELECT 'a'::text AS origem, {com_virgula(ca, cb_nulo)}"
            f"{s.extrair(f'ST_Difference({s.expr_a}, ub.g)')} AS geom "
            f"FROM {tabela_de(s.a)} a, ub")
    so_b = (f"SELECT 'b'::text AS origem, {com_virgula(ca_nulo, cb)}"
            f"{s.extrair(f'ST_Difference({s.expr_b}, ua.g)')} AS geom "
            f"FROM {tabela_de(s.b)} b, ua")
    select = (f"WITH ua AS ({uniao_da(s, 'a')}), ub AS ({uniao_da(s, 'b')}) "
              f"{sobrepoe} UNION ALL {so_a} UNION ALL {so_b}")
    campos = escrever(ctx, destino, select, s.tipo_saida, s.srid)
    return {"geometria": s.tipo_saida, "srid": s.srid, "campos": campos,
            "metodo": "ST_Intersection + ST_Difference nos dois sentidos" + nota_invalidas(s.relatorio)}


@ferramenta(
    nome="diferenca", titulo="Diferença (erase)", categoria="sobreposicao", versao=1,
    descricao="Apaga de cada feição da entrada a parte coberta pela camada de recorte.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("camada_apagar", "GPFeatureRecordSetLayer", "camada a apagar"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2 + e["camada_apagar"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def diferenca(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    s = Sobreposicao(ctx, entradas["camada"], entradas["camada_apagar"], ("camada", "camada_apagar"))
    if familia(s.b)[2] != 2:
        raise ErroFerramenta("apagar_nao_poligonal", "camada_apagar precisa ser poligonal")
    campos_sql = lista_campos(s.a, apelido="a")
    prefixo = com_virgula(campos_sql)
    ctx.progresso(20, "unindo a camada a apagar")
    dim = familia(s.a)[2]
    select = (f"WITH ub AS ({uniao_da(s, 'b')}) "
              f"SELECT {prefixo}{s.extrair(f'ST_Difference({s.expr_a}, ub.g)', dim)} AS geom "
              f"FROM {tabela_de(s.a)} a, ub ORDER BY a.fid")
    tipo = FAMILIAS[familia(s.a)[0].upper()][1]
    campos = escrever(ctx, destino, select, tipo, s.srid)
    return {"geometria": tipo, "srid": s.srid, "campos": campos,
            "metodo": "ST_Difference contra ST_Union da camada a apagar" + nota_invalidas(s.relatorio)}


@ferramenta(
    nome="diferenca_simetrica", titulo="Diferença simétrica", categoria="sobreposicao", versao=1,
    descricao="O que está numa camada e não na outra, nos dois sentidos; o campo origem diz de qual veio.",
    parametros=(
        Parametro("camada_a", "GPFeatureRecordSetLayer", "primeira camada"),
        Parametro("camada_b", "GPFeatureRecordSetLayer", "segunda camada"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: (e["camada_a"]["feicoes"] + e["camada_b"]["feicoes"]) * 3,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def diferenca_simetrica(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    s = Sobreposicao(ctx, entradas["camada_a"], entradas["camada_b"])
    if familia(s.a)[2] != 2 or familia(s.b)[2] != 2:
        raise ErroFerramenta("diferenca_simetrica_nao_poligonal",
                             "diferença simétrica exige as duas camadas poligonais")
    ca = lista_campos(s.a, "a_", "a")
    cb = lista_campos(s.b, "b_", "b")
    ca_nulo, cb_nulo = s.nulos("a", "a_"), s.nulos("b", "b_")
    ctx.progresso(20, "diferença nos dois sentidos")
    so_a = (f"SELECT 'a'::text AS origem, {com_virgula(ca, cb_nulo)}"
            f"{s.extrair(f'ST_Difference({s.expr_a}, ub.g)')} AS geom FROM {tabela_de(s.a)} a, ub")
    so_b = (f"SELECT 'b'::text AS origem, {com_virgula(ca_nulo, cb)}"
            f"{s.extrair(f'ST_Difference({s.expr_b}, ua.g)')} AS geom FROM {tabela_de(s.b)} b, ua")
    select = f"WITH ua AS ({uniao_da(s, 'a')}), ub AS ({uniao_da(s, 'b')}) {so_a} UNION ALL {so_b}"
    campos = escrever(ctx, destino, select, s.tipo_saida, s.srid)
    return {"geometria": s.tipo_saida, "srid": s.srid, "campos": campos,
            "metodo": "ST_Difference nos dois sentidos" + nota_invalidas(s.relatorio)}


# ---------------------------------------------------------------- resumo
def estatisticas_sql(pedidos: list[str], e: dict, tipos: dict) -> tuple[str, list[str]]:
    """"soma:valor" -> sum("valor") AS "soma_valor". Recusa função fora do vocabulário, campo que não é da
    camada e média/soma/desvio sobre campo não numérico."""
    trechos = []
    for pedido in pedidos:
        funcao, _, campo = str(pedido).partition(":")
        if funcao not in ESTATISTICAS:
            raise ErroFerramenta("estatistica_desconhecida",
                                 f"estatisticas: {funcao!r} fora de {sorted(ESTATISTICAS)}")
        if funcao == "contagem" and not campo:
            trechos.append(('count(*)::bigint', "contagem"))
            continue
        if campo not in e["campos"]:
            raise ErroFerramenta("campo_inexistente", f"estatisticas: {campo!r} não é campo da camada")
        if funcao in ("soma", "media", "desvio") and tipos.get(campo) not in NUMERICAS:
            raise ErroFerramenta("campo_nao_numerico",
                                 f"estatisticas: {funcao} exige campo numérico, {campo!r} é {tipos.get(campo)}")
        trechos.append((ESTATISTICAS[funcao].format(c=ident(campo)), f"{funcao}_{campo}"))
    return ", ".join(f"{expr} AS {ident(nome)}" for expr, nome in trechos), [n for _, n in trechos]


@ferramenta(
    nome="dissolver", titulo="Dissolver", categoria="resumo", versao=1,
    descricao="Une as feições que compartilham os mesmos valores nos campos escolhidos, com estatísticas.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("campos", "GPMultiValue", "campos de agrupamento", subtipo="GPString", obrigatorio=False,
                  descricao="sem campos, a camada inteira vira uma feição"),
        Parametro("estatisticas", "GPMultiValue", "estatísticas", subtipo="GPString", obrigatorio=False,
                  descricao="lista de funcao:campo (soma, media, minimo, maximo, desvio, contagem)"),
        Parametro("multipartes", "GPBoolean", "manter multipartes", obrigatorio=False, padrao=True,
                  descricao="falso separa cada parte do resultado em uma feição"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 3,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def dissolver(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    grupo = list(parametros.get("campos") or [])
    for c in grupo:
        if c not in e["campos"]:
            raise ErroFerramenta("campo_inexistente", f"campos: {c!r} não é campo da camada")
    with ctx.db() as cur:
        tipos = tipos_de(cur, e["schema"], e["tabela"])
        expr = limpo(cur, "geom", e["srid"])
    relatorio = contar_invalidas(ctx, [("camada", e)])
    estat_sql, nomes_estat = estatisticas_sql(list(parametros.get("estatisticas") or []), e, tipos)
    cols_grupo = ", ".join(ident(c) for c in grupo)
    cabeca = f"{cols_grupo}, " if cols_grupo else ""
    corpo = f"{estat_sql}, " if estat_sql else ""
    ctx.progresso(20, "agrupando e unindo")
    agrupado = (f"SELECT {cabeca}count(*)::bigint AS feicoes_origem, {corpo}"
                f"ST_Multi(ST_Union({expr})) AS geom FROM {tabela_de(e)}"
                + (f" GROUP BY {cols_grupo} ORDER BY {cols_grupo}" if cols_grupo else ""))
    tipo = FAMILIAS[familia(e)[0].upper()][1]
    if parametros.get("multipartes") is False:
        colunas = grupo + ["feicoes_origem"] + nomes_estat
        select = (f"SELECT {', '.join('t.' + ident(c) for c in colunas)}, "
                  f"ST_Multi((ST_Dump(t.geom)).geom) AS geom FROM ({agrupado}) t")
    else:
        select = agrupado
    campos = escrever(ctx, destino, select, tipo, e["srid"])
    return {"geometria": tipo, "srid": e["srid"], "campos": campos,
            "metodo": f"ST_Union agrupado por {grupo or 'nada'}" + nota_invalidas(relatorio)}


@ferramenta(
    nome="calcular_geometria", titulo="Calcular geometria", categoria="resumo", versao=1,
    descricao="Acrescenta área, perímetro, comprimento (geodésicos, elipsoide WGS 84) e x/y do ponto interior.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("medidas", "GPMultiValue", "medidas", subtipo="GPString", obrigatorio=False,
                  descricao="area_m2, perimetro_m, comprimento_m, x, y; vazio calcula as que couberem"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def calcular_geometria(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    dim = familia(e)[2]
    possiveis = {0: ["x", "y"], 1: ["comprimento_m", "x", "y"], 2: ["area_m2", "perimetro_m", "x", "y"]}[dim]
    pedidas = [m for m in (parametros.get("medidas") or possiveis)]
    for m in pedidas:
        if m not in possiveis:
            raise ErroFerramenta("medida_indisponivel",
                                 f"medidas: {m!r} não se aplica a geometria de dimensão {dim} (use {possiveis})")
    geog = geografia("geom", e["srid"])
    ponto = "ST_PointOnSurface(geom)" if e["srid"] == 4326 else "ST_Transform(ST_PointOnSurface(geom), 4326)"
    expr = {"area_m2": f"ST_Area({geog})", "perimetro_m": f"ST_Perimeter({geog})",
            "comprimento_m": f"ST_Length({geog})", "x": f"ST_X({ponto})", "y": f"ST_Y({ponto})"}
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    medidas_sql = ", ".join(f"{expr[m]}::double precision AS {ident(m)}" for m in pedidas)
    select = f"SELECT {prefixo}{medidas_sql}, geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, e["geometria"], e["srid"])
    return {"geometria": e["geometria"], "srid": e["srid"], "campos": campos,
            "metodo": f"medida geodésica sobre geography (WGS 84): {', '.join(pedidas)}"}


@ferramenta(
    nome="casco", titulo="Casco convexo ou côncavo", categoria="resumo", versao=1,
    descricao="Menor polígono que envolve as feições; convexo por padrão, côncavo com percentual de convexidade.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("tipo", "GPString", "tipo de casco", obrigatorio=False, padrao="convexo",
                  opcoes=("convexo", "concavo")),
        Parametro("percentual_convexo", "GPDouble", "percentual de convexidade", obrigatorio=False, padrao=0.8,
                  minimo=0.0, maximo=1.0, descricao="só para o casco côncavo; 1 devolve o casco convexo"),
        Parametro("por_feicao", "GPBoolean", "um casco por feição", obrigatorio=False, padrao=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def casco(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    pct = float(parametros.get("percentual_convexo") if parametros.get("percentual_convexo") is not None else 0.8)
    def envolver(g: str) -> str:
        return f"ST_ConvexHull({g})" if parametros.get("tipo", "convexo") == "convexo" \
            else f"ST_ConcaveHull({g}, {pct})"
    ctx.progresso(20, "envolvendo as feições")
    if parametros.get("por_feicao"):
        campos_sql = lista_campos(e)
        prefixo = com_virgula(campos_sql)
        select = f"SELECT {prefixo}ST_Multi({envolver('geom')}) AS geom FROM {tabela_de(e)} ORDER BY fid"
    else:
        select = (f"SELECT count(*)::bigint AS feicoes_origem, ST_Multi({envolver('ST_Collect(geom)')}) AS geom "
                  f"FROM {tabela_de(e)}")
    campos = escrever(ctx, destino, select, "MultiPolygon", e["srid"])
    return {"geometria": "MultiPolygon", "srid": e["srid"], "campos": campos,
            "metodo": ("ST_ConvexHull" if parametros.get("tipo", "convexo") == "convexo"
                       else f"ST_ConcaveHull({pct})") + (" por feição" if parametros.get("por_feicao") else "")}


# ---------------------------------------------------------------- gestão de dado
@ferramenta(
    nome="mesclar", titulo="Mesclar camadas", categoria="gestao", versao=1,
    descricao="Empilha várias camadas numa só; campo com o mesmo nome vira uma coluna, o que falta fica nulo.",
    parametros=(
        Parametro("camadas", "GPMultiValue", "camadas de entrada", subtipo="GPFeatureRecordSetLayer",
                  descricao="duas ou mais camadas; a primeira define o SRID e o tipo de geometria"),
        Parametro("campo_origem", "GPString", "campo com a camada de origem", obrigatorio=False,
                  padrao="camada_origem", descricao="nome do campo que guarda o título da camada de origem"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: sum(c["feicoes"] for c in e["camadas"]),
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def mesclar(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    camadas = entradas["camadas"]
    if len(camadas) < 2:
        raise ErroFerramenta("mesclar_precisa_de_duas", "camadas: informe ao menos duas camadas")
    srid = camadas[0]["srid"]
    campo_origem = parametros.get("campo_origem") or "camada_origem"
    ident(campo_origem)
    familias = {familia(c)[1] for c in camadas}
    tipo = familias.pop() if len(familias) == 1 else "Geometry"
    with ctx.db() as cur:
        tipos = {}
        for c in camadas:
            for nome, t in tipos_de(cur, c["schema"], c["tabela"]).items():
                if nome in c["campos"]:
                    tipos.setdefault(nome, t)
    nomes = [n for n in tipos if n != campo_origem]
    ramos = []
    for c in camadas:
        colunas = ", ".join(
            (f"{ident(n)}::{tipos[n]}" if n in c["campos"] else f"NULL::{tipos[n]}") + f" AS {ident(n)}"
            for n in nomes
        )
        geom = f"ST_Multi({no_srid_de('geom', c, srid)})" if tipo != "Geometry" else no_srid_de("geom", c, srid)
        cabeca = com_virgula(colunas)
        ramos.append(f"SELECT {cabeca}%s::text AS {ident(campo_origem)}, {geom} AS geom FROM {tabela_de(c)}")
    select = " UNION ALL ".join(ramos)
    ctx.progresso(20, f"empilhando {len(camadas)} camadas")
    alvo = tabela_de(destino)
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} AS {select}", [c["titulo"][:200] for c in camadas])
        cur.execute(f"DELETE FROM {alvo} WHERE geom IS NULL OR ST_IsEmpty(geom)")
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
        cur.execute(f"ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry({tipo}, {srid}) USING geom")
        campos = campos_de(cur, destino["schema"], destino["tabela"])
    return {"geometria": tipo, "srid": srid, "campos": campos,
            "metodo": f"UNION ALL de {len(camadas)} camadas no SRID {srid}"}


@ferramenta(
    nome="explodir", titulo="Explodir multipartes", categoria="gestao", versao=1,
    descricao="Cada parte de uma feição multiparte vira uma feição, repetindo os campos da original.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def explodir(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    tipo = familia(e)[0]
    select = f"SELECT {prefixo}(ST_Dump(geom)).geom AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, tipo, e["srid"])
    return {"geometria": tipo, "srid": e["srid"], "campos": campos, "metodo": "ST_Dump"}


@ferramenta(
    nome="centroide", titulo="Centroide ou ponto interior", categoria="gestao", versao=1,
    descricao="Um ponto por feição: o centro de massa, ou um ponto garantidamente dentro da feição.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("tipo", "GPString", "tipo de ponto", obrigatorio=False, padrao="centroide",
                  opcoes=("centroide", "ponto_interior")),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def centroide(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    funcao = "ST_Centroid" if parametros.get("tipo", "centroide") == "centroide" else "ST_PointOnSurface"
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = f"SELECT {prefixo}{funcao}(geom) AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, "Point", e["srid"])
    return {"geometria": "Point", "srid": e["srid"], "campos": campos, "metodo": funcao}


@ferramenta(
    nome="simplificar", titulo="Simplificar", categoria="gestao", versao=1,
    descricao="Tira vértices mantendo a forma; por padrão preserva a topologia (não cria geometria inválida).",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("tolerancia", "GPLinearUnit", "tolerância", padrao={"distance": 10, "units": "esriMeters"},
                  minimo=0, descricao="desvio máximo aceito, em unidade linear"),
        Parametro("preservar_topologia", "GPBoolean", "preservar topologia", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def simplificar(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    metros = float(parametros["tolerancia"]["metros"])
    with ctx.db() as cur:
        tolerancia = metros * GRAUS_POR_METRO if geografico(cur, e["srid"]) else metros
    funcao = "ST_SimplifyPreserveTopology" if parametros.get("preservar_topologia", True) is not False \
        else "ST_Simplify"
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = f"SELECT {prefixo}{funcao}(geom, {tolerancia!r}) AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, e["geometria"], e["srid"])
    return {"geometria": e["geometria"], "srid": e["srid"], "campos": campos,
            "metodo": f"{funcao}({tolerancia!r}) — {metros} m convertidos à unidade da camada"}


@ferramenta(
    nome="suavizar", titulo="Suavizar", categoria="gestao", versao=1,
    descricao="Arredonda os cantos por corte de esquina (Chaikin), sem acrescentar detalhe que não existe.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("iteracoes", "GPLong", "iterações", obrigatorio=False, padrao=3, minimo=1, maximo=5),
        Parametro("preservar_extremos", "GPBoolean", "preservar extremos", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def suavizar(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    n = int(parametros.get("iteracoes") or 3)
    preservar = "true" if parametros.get("preservar_extremos", True) is not False else "false"
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = (f"SELECT {prefixo}ST_ChaikinSmoothing(geom, {n}, {preservar}) AS geom "
              f"FROM {tabela_de(e)} ORDER BY fid")
    campos = escrever(ctx, destino, select, e["geometria"], e["srid"])
    return {"geometria": e["geometria"], "srid": e["srid"], "campos": campos,
            "metodo": f"ST_ChaikinSmoothing({n}, {preservar})"}


@ferramenta(
    nome="reprojetar", titulo="Reprojetar", categoria="gestao", versao=1,
    descricao="Passa a camada para outro sistema de referência; os campos não mudam.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("srid_destino", "GPLong", "SRID de destino", minimo=1024, maximo=999999,
                  descricao="código EPSG presente em spatial_ref_sys"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def reprojetar(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    srid = int(parametros["srid_destino"])
    with ctx.db() as cur:
        cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (srid,))
        if cur.fetchone() is None:
            raise ErroFerramenta("srid_desconhecido", f"srid_destino: {srid} não está em spatial_ref_sys")
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = f"SELECT {prefixo}ST_Transform(geom, {srid}) AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, e["geometria"], srid)
    return {"geometria": e["geometria"], "srid": srid, "campos": campos,
            "metodo": f"ST_Transform({e['srid']} -> {srid})"}


@ferramenta(
    nome="densificar", titulo="Densificar", categoria="gestao", versao=1,
    descricao="Acrescenta vértices para que nenhum segmento passe do comprimento pedido (medida geodésica).",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("intervalo", "GPLinearUnit", "comprimento máximo do segmento",
                  padrao={"distance": 100, "units": "esriMeters"}, minimo=0.001),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def densificar(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    metros = float(parametros["intervalo"]["metros"])
    if familia(e)[2] == 0:
        raise ErroFerramenta("densificar_ponto", "densificar não se aplica a camada de pontos")
    with ctx.db() as cur:
        if geografico(cur, e["srid"]):
            expr = f"ST_Segmentize(geom::geography, {metros!r})::geometry"
        else:
            expr = f"ST_Segmentize(geom, {metros!r})"
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = f"SELECT {prefixo}{expr} AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, e["geometria"], e["srid"])
    return {"geometria": e["geometria"], "srid": e["srid"], "campos": campos,
            "metodo": f"ST_Segmentize({metros} m)"}


@ferramenta(
    nome="poligonos_para_linhas", titulo="Polígonos para linhas", categoria="gestao", versao=1,
    descricao="A borda de cada polígono vira linha; anéis internos entram como partes da mesma feição.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def poligonos_para_linhas(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    if familia(e)[2] != 2:
        raise ErroFerramenta("camada_nao_poligonal", "camada precisa ser poligonal")
    campos_sql = lista_campos(e)
    prefixo = com_virgula(campos_sql)
    select = f"SELECT {prefixo}ST_Multi(ST_Boundary(geom)) AS geom FROM {tabela_de(e)} ORDER BY fid"
    campos = escrever(ctx, destino, select, "MultiLineString", e["srid"])
    return {"geometria": "MultiLineString", "srid": e["srid"], "campos": campos, "metodo": "ST_Boundary"}


@ferramenta(
    nome="pontos_aleatorios", titulo="Pontos aleatórios em polígono", categoria="gestao", versao=1,
    descricao="Sorteia pontos dentro de cada polígono; com semente declarada, o sorteio se repete igual.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de polígonos"),
        Parametro("quantidade", "GPLong", "pontos por feição", padrao=10, minimo=1,
                  maximo=limites.PONTOS_ALEATORIOS_MAX),
        Parametro("semente", "GPLong", "semente", obrigatorio=False, minimo=1,
                  descricao="mesmo valor devolve o mesmo conjunto de pontos"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * int(p.get("quantidade") or 10),
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX, "pontos_por_feicao_max": limites.PONTOS_ALEATORIOS_MAX},
)
def pontos_aleatorios(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    if familia(e)[2] != 2:
        raise ErroFerramenta("camada_nao_poligonal", "pontos aleatórios exigem camada poligonal")
    n = int(parametros.get("quantidade") or 10)
    semente = parametros.get("semente")
    gerar = f"ST_GeneratePoints(geom, {n}, {int(semente)})" if semente else f"ST_GeneratePoints(geom, {n})"
    campos_sql = lista_campos(e, apelido="t")
    prefixo = com_virgula(campos_sql)
    select = (f"SELECT {prefixo}(ST_Dump(t.pontos)).geom AS geom FROM "
              f"(SELECT *, {gerar} AS pontos FROM {tabela_de(e)}) t ORDER BY t.fid")
    campos = escrever(ctx, destino, select, "Point", e["srid"])
    return {"geometria": "Point", "srid": e["srid"], "campos": campos,
            "metodo": f"ST_GeneratePoints({n}" + (f", semente {int(semente)})" if semente else ")")}


@ferramenta(
    nome="linhas_para_pontos", titulo="Linhas para pontos", categoria="gestao", versao=1,
    descricao="Ponto em cada vértice da linha, ou pontos espaçados a um intervalo geodésico ao longo dela.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de linhas"),
        Parametro("modo", "GPString", "modo", obrigatorio=False, padrao="vertices",
                  opcoes=("vertices", "intervalo")),
        Parametro("intervalo", "GPLinearUnit", "intervalo", obrigatorio=False,
                  padrao={"distance": 100, "units": "esriMeters"}, minimo=0.001,
                  descricao="distância entre pontos no modo intervalo"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 5,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def linhas_para_pontos(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    e = entradas["camada"]
    if familia(e)[2] != 1:
        raise ErroFerramenta("camada_nao_linear", "camada precisa ser de linhas")
    campos_sql = lista_campos(e, apelido="l")
    prefixo = com_virgula(campos_sql)
    if parametros.get("modo", "vertices") != "intervalo":
        colunas = lista_campos(e)
        pre = com_virgula(colunas)
        select = f"SELECT {pre}(ST_DumpPoints(geom)).geom AS geom FROM {tabela_de(e)} ORDER BY fid"
        metodo = "ST_DumpPoints"
    else:
        metros = float(parametros["intervalo"]["metros"])
        comprimento = f"ST_Length({geografia('l.g', e['srid'])})"
        select = (
            f"WITH l AS (SELECT {', '.join(ident(c) for c in e['campos'] + ['fid'])}, "
            f"(ST_Dump(geom)).geom AS g FROM {tabela_de(e)}) "
            f"SELECT {prefixo}ST_LineInterpolatePoint(l.g, i::double precision / k.n) AS geom "
            f"FROM l, LATERAL (SELECT GREATEST(1, floor({comprimento} / {metros!r}))::int AS n) k, "
            f"LATERAL generate_series(0, k.n) i ORDER BY l.fid, i"
        )
        metodo = f"ST_LineInterpolatePoint a cada {metros} m (comprimento geodésico)"
    campos = escrever(ctx, destino, select, "Point", e["srid"])
    return {"geometria": "Point", "srid": e["srid"], "campos": campos, "metodo": metodo}
