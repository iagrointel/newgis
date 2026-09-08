"""Ferramentas GRANDES do catálogo (item L2-15-b-consultas-duckdb-em-escala).

Seis ferramentas com a MESMA interface das pequenas do L2-05-a — o mesmo decorador `@ferramenta`, o mesmo
vocabulário GP de parâmetros, o mesmo executor, a mesma publicação do resultado como camada com proveniência.
O que muda é onde a conta é feita:

| entrada | onde roda | por quê |
|---|---|---|
| item de catálogo tipo `parquet` | DuckDB, processo próprio | é o formato do grande; não passa pelo Postgres |
| camada do Postgres até `CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB` linhas | PostGIS | já está lá; mover custaria mais |
| camada do Postgres acima do limiar | recusa nomeada | publique como GeoParquet (`geoparquet.gerar`) e repita |

A recusa do terceiro caso é deliberada e não é uma lacuna disfarçada: arrastar dezenas de milhões de linhas do
Postgres para um arquivo a cada execução seria mais caro que a própria conta, e o item L2-15-a já entrega o
caminho de publicar a tabela como GeoParquet uma vez e consultá-la muitas.

**O SQL é o mesmo texto nos dois lados**, montado por um construtor por ferramenta que recebe o dialeto
(`app/consulta_grande/dialeto.py`). É isso que faz "a contagem do DuckDB é igual à do PostGIS" ser uma
afirmação verificável e não uma coincidência.

**Área e comprimento** nunca saem de `ST_Area`/`ST_Length` sobre graus: toda ferramenta que precisa de metro
projeta para o EPSG métrico que o usuário declara no parâmetro `projecao_metrica` (padrão 5880). A distância
entre dois pontos usa o elipsoide nos dois motores (`ST_Distance_Spheroid` / `geography`).
"""

from __future__ import annotations

import re

from app import limites
from app.consulta_grande import dialeto as dial
from app.consulta_grande import execucao
from app.ferramentas.registro import Parametro, ferramenta

CAMPO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
ESTATISTICAS = ("contagem", "soma", "media", "minimo", "maximo")
_AGREGADO = {"contagem": "count({c})", "soma": "sum({c})", "media": "avg({c})", "minimo": "min({c})",
             "maximo": "max({c})"}
LIMIAR = limites.CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB


def _campo(fonte: dict, nome: str, rotulo: str) -> str:
    if not nome or not CAMPO.match(nome):
        raise execucao.ErroFerramentaGrande(f"{rotulo}: nome de campo inválido: {nome!r}")
    if nome not in fonte["campos"]:
        raise execucao.ErroFerramentaGrande(
            f"{rotulo}: a fonte não tem o campo {nome!r}; tem " + ", ".join(sorted(fonte["campos"])[:20]))
    return '"' + nome + '"'


def _projecao(parametros: dict) -> int:
    epsg = int(parametros.get("projecao_metrica") or dial.EPSG_METRICO_PADRAO)
    if not 1024 <= epsg <= 99999:
        raise execucao.ErroFerramentaGrande(f"projecao_metrica: EPSG fora da faixa: {epsg}")
    return epsg


def _grao(parametros: dict, chave: str = "grao_periodo") -> str:
    grao = parametros.get(chave) or "mes"
    if grao not in dial.GRAOS:
        raise execucao.ErroFerramentaGrande(f"{chave}: use um de {', '.join(dial.GRAOS)}")
    return dial.GRAO_SQL[grao]


# ---------------------------------------------------------------- 1. agregar em grade
@ferramenta(
    nome="agregar_em_grade", titulo="Agregar pontos em grade", categoria="resumo", versao=1,
    descricao="Conta (e opcionalmente soma) os pontos de cada célula quadrada de lado declarado, com recorte "
              "opcional por período. A célula é calculada na projeção métrica declarada, nunca em graus.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "fonte de pontos",
                  descricao="item Parquet do catálogo ou camada vetorial"),
        Parametro("tamanho_celula", "GPLinearUnit", "lado da célula",
                  padrao={"distance": 10, "units": "esriKilometers"},
                  minimo=limites.CONSULTA_GRANDE_GRADE_METROS_MIN,
                  maximo=limites.CONSULTA_GRANDE_GRADE_METROS_MAX),
        Parametro("campo_periodo", "GPString", "campo de data", obrigatorio=False,
                  descricao="quando preenchido, a grade é quebrada também por período"),
        Parametro("grao_periodo", "GPString", "grão do período", obrigatorio=False, padrao="mes",
                  opcoes=dial.GRAOS),
        Parametro("campo_valor", "GPString", "campo numérico a somar", obrigatorio=False),
        Parametro("projecao_metrica", "GPLong", "EPSG métrico", obrigatorio=False,
                  padrao=dial.EPSG_METRICO_PADRAO, minimo=1024, maximo=99999),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["camada"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def agregar_em_grade(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_agregar_em_grade,
                          metodo="grade quadrada na projeção métrica declarada")


def _sql_agregar_em_grade(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    fonte = fontes["camada"]
    srid = int(fonte["srid"])
    epsg = _projecao(parametros)
    lado = float(parametros["tamanho_celula"]["metros"])
    metrico = d.transformar("geom", srid, epsg)
    colunas = [f"floor(ST_X({metrico}) / {lado})::bigint AS ix",
               f"floor(ST_Y({metrico}) / {lado})::bigint AS iy"]
    grupos = ["ix", "iy"]
    selecao = ["ix", "iy"]
    if parametros.get("campo_periodo"):
        campo = _campo(fonte, parametros["campo_periodo"], "campo_periodo")
        colunas.append(f"{d.periodo(campo, _grao(parametros))} AS periodo")
        grupos.append("periodo")
        selecao.append("periodo")
    agregados = ["count(*)::bigint AS feicoes"]
    if parametros.get("campo_valor"):
        campo = _campo(fonte, parametros["campo_valor"], "campo_valor")
        colunas.append(f"{campo} AS valor")
        agregados.append("sum(valor)::double precision AS soma_valor" if d.nome == "postgis"
                         else "sum(valor)::DOUBLE AS soma_valor")
    celula = d.envelope(f"ix * {lado}", f"iy * {lado}", f"(ix + 1) * {lado}", f"(iy + 1) * {lado}")
    sql = (
        f"WITH base AS (SELECT {', '.join(colunas)} FROM {d.relacao(fonte)} WHERE geom IS NOT NULL), "
        f"grade AS (SELECT {', '.join(selecao)}, {', '.join(agregados)} FROM base GROUP BY {', '.join(grupos)}) "
        f"SELECT {', '.join(selecao)}, {', '.join(a.split(' AS ')[-1] for a in agregados)}, "
        f"{d.transformar(celula, epsg, srid)} AS geom FROM grade ORDER BY {', '.join(selecao)}"
    )
    return sql, srid


# ---------------------------------------------------------------- 2. junção espacial
@ferramenta(
    nome="juncao_espacial", titulo="Junção espacial de pontos com polígonos", categoria="sobreposicao", versao=1,
    descricao="Marca cada ponto com o atributo do polígono que o contém. Ponto fora de todo polígono sai "
              "com o atributo nulo; ponto sobre a divisa de dois polígonos sai uma vez para cada um, então o "
              "total de linhas é maior ou igual ao número de pontos.",
    parametros=(
        Parametro("pontos", "GPFeatureRecordSetLayer", "fonte de pontos"),
        Parametro("poligonos", "GPFeatureRecordSetLayer", "fonte de polígonos"),
        Parametro("campo_chave", "GPString", "campo do polígono a carregar"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["pontos"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def juncao_espacial(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_juncao_espacial,
                          metodo="ST_Intersects ponto x polígono, junção à esquerda")


def _sql_juncao_espacial(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    pontos, poligonos = fontes["pontos"], fontes["poligonos"]
    srid = int(pontos["srid"])
    chave = _campo(poligonos, parametros["campo_chave"], "campo_chave")
    geom_poligono = d.transformar("b.geom", int(poligonos["srid"]), srid)
    sql = (
        f"SELECT b.{chave} AS chave, a.geom AS geom FROM {d.relacao(pontos)} a "
        f"LEFT JOIN {d.relacao(poligonos)} b ON ST_Intersects({geom_poligono}, a.geom) "
        "WHERE a.geom IS NOT NULL"
    )
    return sql, srid


# ---------------------------------------------------------------- 3. resumir dentro
@ferramenta(
    nome="resumir_dentro", titulo="Resumir pontos dentro de polígonos", categoria="resumo", versao=1,
    descricao="Uma linha por polígono, com a contagem dos pontos que ele contém e as estatísticas pedidas "
              "sobre um campo numérico. Polígono sem nenhum ponto aparece com contagem zero.",
    parametros=(
        Parametro("poligonos", "GPFeatureRecordSetLayer", "fonte de polígonos"),
        Parametro("pontos", "GPFeatureRecordSetLayer", "fonte de pontos"),
        Parametro("campo_chave", "GPString", "campo do polígono que identifica a área"),
        Parametro("campo_valor", "GPString", "campo numérico dos pontos", obrigatorio=False),
        # `opcoes` não vale para GPMultiValue no registro do L2-05-a (só para GPString simples); a lista
        # fechada é conferida em `_sql_resumir_dentro`, com a mesma mensagem nomeando o campo.
        Parametro("estatisticas", "GPMultiValue", "estatísticas", obrigatorio=False, subtipo="GPString",
                  padrao=["contagem"],
                  descricao="uma ou mais de: " + ", ".join(ESTATISTICAS)),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["pontos"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def resumir_dentro(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_resumir_dentro,
                          metodo="agregação por polígono com ST_Intersects")


def _sql_resumir_dentro(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    poligonos, pontos = fontes["poligonos"], fontes["pontos"]
    srid = int(poligonos["srid"])
    chave = _campo(poligonos, parametros["campo_chave"], "campo_chave")
    pedidas = list(parametros.get("estatisticas") or ["contagem"])
    for e in pedidas:
        if e not in ESTATISTICAS:
            raise execucao.ErroFerramentaGrande(f"estatisticas: {e!r} fora de {', '.join(ESTATISTICAS)}")
    valor = None
    if any(e != "contagem" for e in pedidas):
        if not parametros.get("campo_valor"):
            raise execucao.ErroFerramentaGrande(
                "campo_valor é obrigatório para qualquer estatística além de contagem")
        valor = "a." + _campo(pontos, parametros["campo_valor"], "campo_valor")
    agregados = []
    for e in pedidas:
        alvo = "*" if e == "contagem" else valor
        expressao = _AGREGADO[e].format(c=alvo)
        agregados.append(f"{expressao} AS {e}" if e != "contagem"
                         else f"count(a.geom)::bigint AS contagem")
    geom_ponto = d.transformar("a.geom", int(pontos["srid"]), srid)
    sql = (
        f"SELECT b.{chave} AS chave, {', '.join(agregados)}, b.geom AS geom "
        f"FROM {d.relacao(poligonos)} b LEFT JOIN {d.relacao(pontos)} a "
        f"ON ST_Intersects(b.geom, {geom_ponto}) "
        f"GROUP BY b.{chave}, b.geom ORDER BY b.{chave}"
    )
    return sql, srid


# ---------------------------------------------------------------- 4. contagem por período
@ferramenta(
    nome="contagem_por_periodo", titulo="Contagem por período", categoria="resumo", versao=1,
    descricao="Uma linha por período (dia, mês ou ano) com a contagem das feições e a extensão que elas "
              "ocupam. Não tem geometria de saída por feição: o resultado é uma tabela.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "fonte"),
        Parametro("campo_periodo", "GPString", "campo de data"),
        Parametro("grao_periodo", "GPString", "grão do período", obrigatorio=False, padrao="mes",
                  opcoes=dial.GRAOS),
        Parametro("saida", "GPFeatureRecordSetLayer", "tabela de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["camada"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def contagem_por_periodo(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_contagem_por_periodo,
                          metodo="contagem agrupada por date_trunc do campo declarado")


def _sql_contagem_por_periodo(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    fonte = fontes["camada"]
    campo = _campo(fonte, parametros["campo_periodo"], "campo_periodo")
    sql = (
        f"SELECT {d.periodo(campo, _grao(parametros))} AS periodo, count(*)::bigint AS feicoes "
        f"FROM {d.relacao(fonte)} WHERE {campo} IS NOT NULL GROUP BY 1 ORDER BY 1"
    )
    return sql, int(fonte["srid"])


# ---------------------------------------------------------------- 5. detectar duplicatas
@ferramenta(
    nome="detectar_duplicatas", titulo="Detectar duplicatas", categoria="gestao", versao=1,
    descricao="Grupos de feições que repetem os mesmos valores nos campos escolhidos (e, quando pedido, a "
              "mesma posição). Devolve uma linha por grupo repetido, com quantas feições ele tem.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "fonte"),
        Parametro("campos", "GPMultiValue", "campos que definem a duplicata", subtipo="GPString"),
        Parametro("mesma_posicao", "GPBoolean", "exigir a mesma posição", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["camada"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def detectar_duplicatas(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_detectar_duplicatas,
                          metodo="agrupamento pelos campos declarados, com contagem > 1")


def _sql_detectar_duplicatas(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    fonte = fontes["camada"]
    srid = int(fonte["srid"])
    campos = list(parametros.get("campos") or [])
    if not campos:
        raise execucao.ErroFerramentaGrande("campos: informe ao menos um campo")
    nomes = [_campo(fonte, c, "campos") for c in campos]
    chaves = list(nomes)
    if parametros.get("mesma_posicao"):
        chaves.append("ST_AsText(geom)")
    sql = (
        f"SELECT {', '.join(nomes)}, count(*)::bigint AS repeticoes, "
        f"{'min(geom)' if d.nome == 'duckdb' else 'ST_Union(geom)'} AS geom "
        f"FROM {d.relacao(fonte)} GROUP BY {', '.join(chaves)} HAVING count(*) > 1 "
        f"ORDER BY repeticoes DESC, {', '.join(nomes)}"
    )
    return sql, srid


# ---------------------------------------------------------------- 6. padrões de deslocamento
@ferramenta(
    nome="padroes_deslocamento", titulo="Padrões de deslocamento por identificador",
    categoria="proximidade", versao=1,
    descricao="Liga cada posição à seguinte do mesmo identificador, em ordem de tempo, e devolve o segmento "
              "com a distância sobre a esfera, o tempo decorrido e a velocidade média.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "fonte de posições"),
        Parametro("campo_id", "GPString", "campo do identificador"),
        Parametro("campo_periodo", "GPString", "campo de data e hora"),
        Parametro("velocidade_maxima", "GPDouble", "velocidade acima da qual o salto é marcado (km/h)",
                  obrigatorio=False, padrao=120.0, minimo=0, maximo=100000),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: max(int(entradas["camada"]["feicoes"]), limites.FERRAMENTA_SINCRONO_CUSTO_MAX + 1),
    limites={"aceita_parquet": True, "limiar_linhas_duckdb": LIMIAR},
)
def padroes_deslocamento(ctx, entradas, parametros, destino):
    return execucao.rodar(ctx, entradas, parametros, destino, _sql_padroes_deslocamento,
                          metodo="lag() por identificador em ordem de tempo; distância sobre a esfera")


def _sql_padroes_deslocamento(d: dial.Dialeto, fontes: dict, parametros: dict) -> tuple[str, int]:
    fonte = fontes["camada"]
    srid = int(fonte["srid"])
    identificador = _campo(fonte, parametros["campo_id"], "campo_id")
    quando = _campo(fonte, parametros["campo_periodo"], "campo_periodo")
    limite = float(parametros.get("velocidade_maxima") or 120.0)
    # a distância sobre a esfera exige graus (4326) nos dois motores
    em_graus = d.transformar("geom", srid, 4326)
    anterior_graus = d.transformar("anterior", srid, 4326)
    segundos = ("EXTRACT(EPOCH FROM (quando - quando_anterior))" if d.nome == "postgis"
                else "date_diff('second', quando_anterior, quando)")
    sql = (
        f"WITH ordenado AS (SELECT {identificador} AS identificador, {quando} AS quando, geom, "
        f"lag(geom) OVER (PARTITION BY {identificador} ORDER BY {quando}) AS anterior, "
        f"lag({quando}) OVER (PARTITION BY {identificador} ORDER BY {quando}) AS quando_anterior "
        f"FROM {d.relacao(fonte)} WHERE geom IS NOT NULL AND {quando} IS NOT NULL), "
        f"segmentos AS (SELECT identificador, quando_anterior, quando, "
        f"{d.distancia_esferica(anterior_graus, em_graus)} AS metros, "
        f"{segundos} AS segundos, ST_MakeLine(anterior, geom) AS geom "
        "FROM ordenado WHERE anterior IS NOT NULL) "
        "SELECT identificador, quando_anterior, quando, metros, segundos, "
        "CASE WHEN segundos > 0 THEN metros / segundos * 3.6 ELSE NULL END AS km_por_hora, "
        f"CASE WHEN segundos > 0 AND metros / segundos * 3.6 > {limite} THEN true ELSE false END AS salto, "
        "geom FROM segmentos ORDER BY identificador, quando"
    )
    return sql, srid


FERRAMENTAS = ("agregar_em_grade", "juncao_espacial", "resumir_dentro", "contagem_por_periodo",
               "detectar_duplicatas", "padroes_deslocamento")
CONSTRUTORES = {
    "agregar_em_grade": _sql_agregar_em_grade, "juncao_espacial": _sql_juncao_espacial,
    "resumir_dentro": _sql_resumir_dentro, "contagem_por_periodo": _sql_contagem_por_periodo,
    "detectar_duplicatas": _sql_detectar_duplicatas, "padroes_deslocamento": _sql_padroes_deslocamento,
}
