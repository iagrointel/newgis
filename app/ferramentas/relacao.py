"""Ferramentas de RELAÇÃO entre camadas (item L2-05-c): junção espacial, junção por atributo, resumir dentro,
resumir perto, agregar pontos (em polígonos ou em grade regular), contar dentro, enriquecer por proporção de
área, vizinho mais próximo e tabela de distâncias. Mesmo registro (`app/ferramentas/registro.py`) e mesmo
executor (`app/ferramentas/executor.py`) do L2-05-a; as regras da casa do L2-05-b continuam valendo
(ST_MakeValid + ST_ReducePrecision antes de operação booleana, relatório de inválidas na procedência, medida
geodésica sobre `geography`).

Três decisões que valem para o módulo inteiro:

1. **Par candidato por índice espacial, medida na geometria original.** Toda ferramenta que cruza duas camadas
   monta primeiro uma lista de pares candidatos com `ST_Intersects`/`ST_DWithin` sobre a camada de polígonos
   passada por `ST_Subdivide` (partes de no máximo `limites.SUBDIVIDIR_VERTICES` vértices), com `DISTINCT` para
   desfazer o par repetido que a subdivisão cria; depois confere a relação pedida e mede contra a geometria
   ORIGINAL. Polígono grande deixa de ser uma caixa envolvente inútil para o índice sem que a medida mude.
2. **Contagem dupla é declarada.** Se a camada de polígonos tem feições sobrepostas, uma mesma feição resumida
   entra em cada polígono que a contém — é o comportamento do Summarize Within do ArcGIS. O parâmetro
   `atribuicao='exclusivo'` desfaz isso, atribuindo cada feição a um único polígono (o de menor `fid`). O texto
   do método na procedência diz qual dos dois foi usado e quantas feições apareceram em mais de um polígono.
3. **Ponto na fronteira conta.** O predicado é `ST_Intersects`, então um ponto exatamente sobre a divisa entra
   nos dois polígonos vizinhos. Também é o comportamento do ArcGIS, e também se resolve com `atribuicao`.
"""

from __future__ import annotations

from app import limites
from app.ferramentas.registro import Parametro, ferramenta
from app.ferramentas.vetor import (
    ErroFerramenta,
    com_virgula,
    contar_invalidas,
    escrever,
    familia,
    geografia,
    ident,
    limpo,
    lista_campos,
    no_srid_de,
    nota_invalidas,
    tabela_de,
    tipos_de,
    verificar_tamanho,
)

# relação espacial pedida -> predicado exato, já com `alvo` e `outra` como apelidos das geometrias originais
RELACOES = {
    "intersecta": "ST_Intersects({alvo}, {outra})",
    "contem": "ST_Contains({alvo}, {outra})",
    "dentro": "ST_Within({alvo}, {outra})",
    "a_distancia": "ST_DWithin({alvo_geog}, {outra_geog}, {metros})",
}
# regra de mesclagem da junção um-para-um; {c} é a coluna da camada juntada, ordenada por fid para dar resultado
# estável (o "primeiro" do ArcGIS não declara ordem; aqui é o de menor fid, e isso está escrito no método)
MESCLAGEM = {
    "soma": "sum({c})", "media": "avg({c})", "minimo": "min({c})", "maximo": "max({c})",
    "contagem": "count({c})", "primeiro": "(array_agg({c} ORDER BY {ordem}))[1]",
    "concatenar": "string_agg({c}::text, ', ' ORDER BY {ordem})",
}
NUMERICAS = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
# funções de resumo que exigem campo numérico
EXIGEM_NUMERO = ("soma", "media", "minimo", "maximo")


# ---------------------------------------------------------------- apoio
def coluna_de(e: dict, campo: str, rotulo: str) -> str:
    if campo not in e["campos"]:
        raise ErroFerramenta("campo_inexistente", f"{rotulo}: {campo!r} não é campo da camada {e['titulo']!r}")
    return ident(campo)


def resumos_sql(pedidos, e: dict, tipos: dict, apelido: str, ordem: str) -> tuple[str, list[str]]:
    """"soma:valor" -> sum(b."valor") AS "soma_valor". Recusa função fora do vocabulário, campo que não é da
    camada e função numérica sobre campo de texto. Sem pedido nenhum devolve trecho vazio."""
    trechos = []
    for pedido in pedidos or ():
        funcao, _, campo = str(pedido).partition(":")
        if funcao not in MESCLAGEM:
            raise ErroFerramenta("resumo_desconhecido", f"resumos: {funcao!r} fora de {sorted(MESCLAGEM)}")
        if funcao == "contagem" and not campo:
            trechos.append(("count(*)::bigint", "contagem"))
            continue
        col = f"{apelido}.{coluna_de(e, campo, 'resumos')}"
        if funcao in EXIGEM_NUMERO and tipos.get(campo) not in NUMERICAS:
            raise ErroFerramenta("campo_nao_numerico",
                                 f"resumos: {funcao} exige campo numérico, {campo!r} é {tipos.get(campo)}")
        trechos.append((MESCLAGEM[funcao].format(c=col, ordem=ordem), f"{funcao}_{campo}"))
    if len({n for _, n in trechos}) != len(trechos):
        raise ErroFerramenta("resumo_repetido", "resumos: o mesmo par função/campo foi pedido duas vezes")
    return ", ".join(f"{expr} AS {ident(nome)}" for expr, nome in trechos), [n for _, n in trechos]


def utm_da_camada(ctx, e: dict) -> int:
    """SRID UTM WGS 84 do centro da camada (32600+fuso ao norte, 32700+fuso ao sul). Usado para gerar grade
    métrica de verdade: quadrado e hexágono desenhados em grau ficam achatados conforme a latitude."""
    with ctx.db() as cur:
        cur.execute(f"SELECT ST_X(c) AS x, ST_Y(c) AS y FROM (SELECT ST_Centroid(ST_Transform("
                    f"ST_SetSRID(ST_Extent(geom)::geometry, {int(e['srid'])}), 4326)) AS c "
                    f"FROM {tabela_de(e)}) t")
        r = cur.fetchone()
    if r is None or r["x"] is None:
        raise ErroFerramenta("camada_vazia", f"camada {e['titulo']!r} sem feições para definir a grade")
    fuso = int((float(r["x"]) + 180.0) // 6.0) + 1
    fuso = min(60, max(1, fuso))
    return (32600 if float(r["y"]) >= 0 else 32700) + fuso


def pares_candidatos(ctx, poligonos: dict, outra: dict, metros: float | None = None) -> str:
    """CTE `pares(pfid, ofid)` com os pares que o índice espacial deixa passar. A camada de polígonos entra
    subdividida (ST_Subdivide) e o DISTINCT desfaz a repetição que a subdivisão cria."""
    srid = poligonos["srid"]
    outra_geom = no_srid_de("o.geom", outra, srid)
    with ctx.db() as cur:
        expr = limpo(cur, "p.geom", srid)
    filtro = (f"ST_DWithin({geografia('s.g', srid)}, {geografia('o.geom', outra['srid'])}, {float(metros)!r})"
              if metros is not None else f"ST_Intersects(s.g, {outra_geom})")
    return (f"sub AS (SELECT p.fid AS pfid, ST_Subdivide({expr}, {int(limites.SUBDIVIDIR_VERTICES)}) AS g "
            f"FROM {tabela_de(poligonos)} p), "
            f"pares AS (SELECT DISTINCT s.pfid, o.fid AS ofid FROM sub s "
            f"JOIN {tabela_de(outra)} o ON {filtro})")


def atribuicao_sql(exclusivo: bool) -> str:
    """`pares_final`: todos os pares, ou um polígono por feição resumida (o de menor fid)."""
    if not exclusivo:
        return "pares_final AS (SELECT pfid, ofid FROM pares)"
    return "pares_final AS (SELECT DISTINCT ON (ofid) pfid, ofid FROM pares ORDER BY ofid, pfid)"


def contar_repetidas(ctx, poligonos: dict, outra: dict, metros: float | None = None) -> int:
    """Quantas feições da camada resumida caem em mais de um polígono (o número que a nota de método publica)."""
    cte = pares_candidatos(ctx, poligonos, outra, metros)
    with ctx.db() as cur:
        cur.execute(f"WITH {cte} SELECT count(*) AS n FROM "
                    f"(SELECT ofid FROM pares GROUP BY ofid HAVING count(*) > 1) t")
        return int(cur.fetchone()["n"])


def nota_atribuicao(exclusivo: bool, repetidas: int) -> str:
    if exclusivo:
        return f"; atribuição exclusiva (cada feição em um só polígono); {repetidas} feição(ões) cabiam em mais de um"
    if repetidas:
        return (f"; {repetidas} feição(ões) contada(s) em mais de um polígono (camada de resumo com sobreposição; "
                f"use atribuicao='exclusivo' para evitar)")
    return "; nenhuma feição caiu em mais de um polígono"


def medida_da_parte(dimensao: int, srid: int, outra: str) -> tuple[str, str]:
    """(expressão, nome) da medida geodésica da PARTE contida: área para polígono, comprimento para linha."""
    parte = geografia(f"ST_Intersection(p.geom, {outra})", srid)
    if dimensao == 2:
        return f"ST_Area({parte})", "area_m2"
    if dimensao == 1:
        return f"ST_Length({parte})", "comprimento_m"
    return "", ""


PARAMETRO_ATRIBUICAO = Parametro(
    "atribuicao", "GPString", "atribuição", obrigatorio=False, padrao="todos", opcoes=("todos", "exclusivo"),
    descricao="todos conta a feição em cada polígono que a contém; exclusivo a atribui só ao de menor fid")


# ---------------------------------------------------------------- junção espacial
@ferramenta(
    nome="juncao_espacial", titulo="Junção espacial", categoria="sobreposicao", versao=1,
    descricao="Leva à camada alvo os dados da outra camada pela relação espacial escolhida, um-para-um "
              "(com regra de mesclagem) ou um-para-muitos (uma feição por par).",
    parametros=(
        Parametro("camada_alvo", "GPFeatureRecordSetLayer", "camada alvo",
                  descricao="a geometria do resultado é a desta camada"),
        Parametro("camada_juntar", "GPFeatureRecordSetLayer", "camada a juntar"),
        Parametro("relacao", "GPString", "relação espacial", obrigatorio=False, padrao="intersecta",
                  opcoes=("intersecta", "contem", "dentro", "a_distancia", "mais_proximo")),
        Parametro("distancia", "GPLinearUnit", "distância", obrigatorio=False,
                  padrao={"distance": 1000, "units": "esriMeters"}, minimo=0,
                  descricao="só vale para a relação a_distancia; mais_proximo procura sem teto"),
        Parametro("tipo_juncao", "GPString", "tipo de junção", obrigatorio=False, padrao="um_para_um",
                  opcoes=("um_para_um", "um_para_muitos")),
        Parametro("resumos", "GPMultiValue", "regras de mesclagem", subtipo="GPString", obrigatorio=False,
                  descricao="lista funcao:campo com soma, media, minimo, maximo, contagem, primeiro, concatenar"),
        Parametro("manter_sem_par", "GPBoolean", "manter feições sem par", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: (e["camada_alvo"]["feicoes"] + e["camada_juntar"]["feicoes"]) * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def juncao_espacial(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    a, b = entradas["camada_alvo"], entradas["camada_juntar"]
    relacao = parametros.get("relacao") or "intersecta"
    um_para_um = (parametros.get("tipo_juncao") or "um_para_um") == "um_para_um"
    esquerda = parametros.get("manter_sem_par", True) is not False
    metros = float((parametros.get("distancia") or {}).get("metros") or 0.0)
    srid = a["srid"]
    with ctx.db() as cur:
        tipos_b = tipos_de(cur, b["schema"], b["tabela"])
    relatorio = contar_invalidas(ctx, [("camada_alvo", a), ("camada_juntar", b)])
    ordem = "b.fid"
    campos_a = lista_campos(a, apelido="a")

    if relacao == "mais_proximo":
        ga, gb = geografia("a.geom", srid), geografia("b.geom", b["srid"])
        onde = ""  # o teto de distância é de `a_distancia`; `mais_proximo` procura o vizinho onde ele estiver
        extras = "".join(f", b.{ident(c)} AS {ident('juntada_' + c)}" for c in b["campos"])
        traz = "".join(f", v.{ident('juntada_' + c)}" for c in b["campos"])
        juncao = "LEFT JOIN LATERAL" if esquerda else "CROSS JOIN LATERAL"
        fecha = " ON true" if esquerda else ""
        ctx.progresso(20, "procurando o vizinho de cada feição")
        select = (f"SELECT {com_virgula(campos_a)}v.juntada_fid, v.distancia_m{traz}, a.geom AS geom "
                  f"FROM {tabela_de(a)} a {juncao} ("
                  f"SELECT b.fid AS juntada_fid, ST_Distance({ga}, {gb})::double precision AS distancia_m{extras} "
                  f"FROM {tabela_de(b)} b {onde}ORDER BY {gb} <-> {ga}, b.fid LIMIT 1) v{fecha} ORDER BY a.fid")
        campos = escrever(ctx, destino, select, a["geometria"], srid)
        return {"geometria": a["geometria"], "srid": srid, "campos": campos,
                "metodo": ("junção com o vizinho mais próximo: ST_Distance sobre geography (elipsoide WGS 84), "
                           "sem teto de distância" + nota_invalidas(relatorio))}

    if relacao not in RELACOES:
        conhecidas = sorted([*RELACOES, "mais_proximo"])
        raise ErroFerramenta("relacao_desconhecida", f"relacao: {relacao!r} fora de {conhecidas}")
    predicado = RELACOES[relacao].format(
        alvo="a.geom", outra=no_srid_de("b.geom", b, srid),
        alvo_geog=geografia("a.geom", srid), outra_geog=geografia("b.geom", b["srid"]), metros=repr(metros))
    ctx.progresso(20, "cruzando as camadas")
    if um_para_um:
        resumo_sql, _ = resumos_sql(parametros.get("resumos"), b, tipos_b, "b", ordem)
        corpo = f"{resumo_sql}, " if resumo_sql else ""
        juncao = "LEFT JOIN" if esquerda else "JOIN"
        select = (f"SELECT {com_virgula(campos_a)}count(b.fid)::bigint AS feicoes_juntadas, {corpo}a.geom AS geom "
                  f"FROM {tabela_de(a)} a {juncao} {tabela_de(b)} b ON {predicado} "
                  f"GROUP BY a.fid ORDER BY a.fid")
        metodo = f"junção espacial um-para-um por {relacao}"
    else:
        campos_b = lista_campos(b, "juntada_", "b")
        juncao = "LEFT JOIN" if esquerda else "JOIN"
        select = (f"SELECT {com_virgula(lista_campos(a, 'alvo_', 'a'), campos_b)}"
                  f"b.fid AS juntada_fid, a.geom AS geom "
                  f"FROM {tabela_de(a)} a {juncao} {tabela_de(b)} b ON {predicado} ORDER BY a.fid, b.fid")
        metodo = f"junção espacial um-para-muitos por {relacao}"
    if relacao == "a_distancia":
        metodo += f" a {metros} m (distância geodésica, elipsoide WGS 84)"
    campos = escrever(ctx, destino, select, a["geometria"], srid)
    return {"geometria": a["geometria"], "srid": srid, "campos": campos,
            "metodo": metodo + nota_invalidas(relatorio)}


# ---------------------------------------------------------------- junção por atributo
@ferramenta(
    nome="juncao_atributo", titulo="Junção por atributo", categoria="gestao", versao=1,
    descricao="Leva à camada os campos de outra camada pela igualdade de uma chave; a geometria da camada "
              "juntada não é levada.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("camada_juntar", "GPFeatureRecordSetLayer", "camada a juntar",
                  descricao="só os atributos entram no resultado; a geometria dela é ignorada"),
        Parametro("chave", "GPString", "campo chave da camada de entrada"),
        Parametro("chave_juntar", "GPString", "campo chave da camada a juntar"),
        Parametro("tipo", "GPString", "tipo de junção", obrigatorio=False, padrao="left",
                  opcoes=("inner", "left")),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] + e["camada_juntar"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def juncao_atributo(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    a, b = entradas["camada"], entradas["camada_juntar"]
    ca = coluna_de(a, parametros["chave"], "chave")
    cb = coluna_de(b, parametros["chave_juntar"], "chave_juntar")
    with ctx.db() as cur:
        tipos_a, tipos_b = tipos_de(cur, a["schema"], a["tabela"]), tipos_de(cur, b["schema"], b["tabela"])
    if tipos_a.get(parametros["chave"]) != tipos_b.get(parametros["chave_juntar"]):
        raise ErroFerramenta(
            "chaves_de_tipos_diferentes",
            f"chave {tipos_a.get(parametros['chave'])} não casa com chave_juntar "
            f"{tipos_b.get(parametros['chave_juntar'])}")
    juncao = "INNER JOIN" if (parametros.get("tipo") or "left") == "inner" else "LEFT JOIN"
    campos_b = lista_campos(b, "juntada_", "b")
    ctx.progresso(20, "juntando pela chave")
    select = (f"SELECT {com_virgula(lista_campos(a, apelido='a'), campos_b)}a.geom AS geom "
              f"FROM {tabela_de(a)} a {juncao} {tabela_de(b)} b ON a.{ca} = b.{cb} ORDER BY a.fid, b.fid")
    campos = escrever(ctx, destino, select, a["geometria"], a["srid"])
    return {"geometria": a["geometria"], "srid": a["srid"], "campos": campos,
            "metodo": f"{juncao} por {parametros['chave']} = {parametros['chave_juntar']}"}


# ---------------------------------------------------------------- resumir dentro
def _resumir_dentro(ctx, entradas, parametros, destino, so_contagem: bool) -> dict:
    verificar_tamanho(entradas)
    p, o = entradas["camada_poligonos"], entradas["camada_resumir"]
    if familia(p)[2] != 2:
        raise ErroFerramenta("camada_nao_poligonal", "camada_poligonos precisa ser poligonal")
    exclusivo = (parametros.get("atribuicao") or "todos") == "exclusivo"
    manter_vazios = parametros.get("manter_vazios", True) is not False
    grupo = parametros.get("campo_grupo") or None
    srid = p["srid"]
    with ctx.db() as cur:
        tipos_o = tipos_de(cur, o["schema"], o["tabela"])
    relatorio = contar_invalidas(ctx, [("camada_poligonos", p), ("camada_resumir", o)])
    repetidas = contar_repetidas(ctx, p, o)
    resumo_sql, _ = ("", []) if so_contagem else resumos_sql(parametros.get("estatisticas"), o, tipos_o, "o", "o.fid")
    medida, nome_medida = ("", "") if so_contagem else medida_da_parte(
        familia(o)[2], srid, no_srid_de("o.geom", o, srid))
    if grupo:
        coluna_de(o, grupo, "campo_grupo")
    ctx.progresso(20, "montando os pares por índice espacial")
    predicado = f"ST_Intersects(p.geom, {no_srid_de('o.geom', o, srid)})"
    colunas_grupo = f"o.{ident(grupo)} AS {ident('grupo')}, " if grupo else ""
    agregados = ", ".join(x for x in [
        "count(o.fid)::bigint AS contagem",
        (f"sum({medida})::double precision AS {ident(nome_medida)}" if medida else ""),
        resumo_sql,
    ] if x)
    grupo_por = "p.fid" + (f", o.{ident(grupo)}" if grupo else "")
    juncao = "LEFT JOIN" if (manter_vazios and not grupo) else "JOIN"
    select = (
        f"WITH {pares_candidatos(ctx, p, o)}, {atribuicao_sql(exclusivo)} "
        f"SELECT {com_virgula(lista_campos(p, apelido='p'))}{colunas_grupo}{agregados}, p.geom AS geom "
        f"FROM {tabela_de(p)} p {juncao} pares_final f ON f.pfid = p.fid "
        f"{juncao} {tabela_de(o)} o ON o.fid = f.ofid AND {predicado} "
        f"GROUP BY {grupo_por}, p.fid ORDER BY p.fid" + (f", o.{ident(grupo)}" if grupo else "")
    )
    campos = escrever(ctx, destino, select, p["geometria"], srid)
    metodo = ("contagem dentro de cada polígono" if so_contagem else
              "resumo dentro de cada polígono, com a medida geodésica da parte contida")
    if grupo:
        metodo += f", uma feição por polígono e valor de {grupo!r}"
    return {"geometria": p["geometria"], "srid": srid, "campos": campos,
            "metodo": metodo + nota_atribuicao(exclusivo, repetidas) + nota_invalidas(relatorio)}


@ferramenta(
    nome="resumir_dentro", titulo="Resumir dentro", categoria="resumo", versao=1,
    descricao="Para cada polígono: quantas feições da outra camada caem dentro, a medida geodésica da parte "
              "contida e as estatísticas pedidas; opcionalmente separadas por um campo de grupo.",
    parametros=(
        Parametro("camada_poligonos", "GPFeatureRecordSetLayer", "camada de polígonos"),
        Parametro("camada_resumir", "GPFeatureRecordSetLayer", "camada a resumir"),
        Parametro("estatisticas", "GPMultiValue", "estatísticas", subtipo="GPString", obrigatorio=False,
                  descricao="lista funcao:campo com soma, media, minimo, maximo, contagem, primeiro, concatenar"),
        Parametro("campo_grupo", "GPString", "campo de grupo", obrigatorio=False,
                  descricao="separa o resumo por valor deste campo da camada resumida"),
        PARAMETRO_ATRIBUICAO,
        Parametro("manter_vazios", "GPBoolean", "manter polígonos sem feição", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_poligonos"]["feicoes"] * 2 + e["camada_resumir"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def resumir_dentro(ctx, entradas, parametros, destino) -> dict:
    return _resumir_dentro(ctx, entradas, parametros, destino, so_contagem=False)


@ferramenta(
    nome="contar_dentro", titulo="Contar dentro", categoria="resumo", versao=1,
    descricao="Quantas feições da outra camada caem dentro de cada polígono, sem outras estatísticas.",
    parametros=(
        Parametro("camada_poligonos", "GPFeatureRecordSetLayer", "camada de polígonos"),
        Parametro("camada_resumir", "GPFeatureRecordSetLayer", "camada a contar"),
        PARAMETRO_ATRIBUICAO,
        Parametro("manter_vazios", "GPBoolean", "manter polígonos sem feição", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_poligonos"]["feicoes"] + e["camada_resumir"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def contar_dentro(ctx, entradas, parametros, destino) -> dict:
    return _resumir_dentro(ctx, entradas, parametros, destino, so_contagem=True)


# ---------------------------------------------------------------- resumir perto
@ferramenta(
    nome="resumir_perto", titulo="Resumir perto", categoria="proximidade", versao=1,
    descricao="Área de proximidade geodésica em volta de cada feição de referência, com a contagem e as "
              "estatísticas das feições da outra camada que caem dentro dela.",
    parametros=(
        Parametro("camada_referencia", "GPFeatureRecordSetLayer", "camada de referência"),
        Parametro("camada_resumir", "GPFeatureRecordSetLayer", "camada a resumir"),
        Parametro("distancia", "GPLinearUnit", "distância", padrao={"distance": 1000, "units": "esriMeters"},
                  minimo=1, maximo=limites.BUFFER_DISTANCIA_M_MAX),
        Parametro("estatisticas", "GPMultiValue", "estatísticas", subtipo="GPString", obrigatorio=False),
        Parametro("segmentos", "GPLong", "segmentos por quadrante", obrigatorio=False, padrao=8, minimo=1,
                  maximo=64),
        Parametro("manter_vazios", "GPBoolean", "manter referências sem feição", obrigatorio=False, padrao=True),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_referencia"]["feicoes"] * 3 + e["camada_resumir"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX, "distancia_m_max": limites.BUFFER_DISTANCIA_M_MAX},
)
def resumir_perto(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    r, o = entradas["camada_referencia"], entradas["camada_resumir"]
    metros = float(parametros["distancia"]["metros"])
    segmentos = int(parametros.get("segmentos") or 8)
    manter_vazios = parametros.get("manter_vazios", True) is not False
    srid = r["srid"]
    with ctx.db() as cur:
        tipos_o = tipos_de(cur, o["schema"], o["tabela"])
    relatorio = contar_invalidas(ctx, [("camada_referencia", r), ("camada_resumir", o)])
    resumo_sql, nomes = resumos_sql(parametros.get("estatisticas"), o, tipos_o, "o", "o.fid")
    corpo = f"{resumo_sql}, " if resumo_sql else ""
    de_volta = ("a.g::geometry" if srid == 4326 else f"ST_Transform(a.g::geometry, {srid})")
    juncao = "LEFT JOIN" if manter_vazios else "JOIN"
    campos_r = "".join(f", r.{ident(c)}" for c in r["campos"])
    ctx.progresso(20, "desenhando as áreas de proximidade")
    select = (
        f"WITH area AS (SELECT r.fid{campos_r}, "
        f"ST_Buffer({geografia('r.geom', srid)}, {metros!r}, {segmentos}) AS g FROM {tabela_de(r)} r), "
        f"resumo AS (SELECT a.fid, {corpo}count(o.fid)::bigint AS contagem "
        f"FROM area a {juncao} {tabela_de(o)} o "
        f"ON ST_DWithin(a.g, {geografia('o.geom', o['srid'])}, 0) GROUP BY a.fid) "
        f"SELECT {com_virgula(lista_campos(r, apelido='a'))}s.contagem"
        f"{''.join(f', s.{ident(n)}' for n in nomes)}, ST_Multi({de_volta}) AS geom "
        f"FROM area a JOIN resumo s ON s.fid = a.fid ORDER BY a.fid"
    )
    campos = escrever(ctx, destino, select, "MultiPolygon", srid)
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
            "metodo": (f"área de proximidade geodésica de {metros} m (ST_Buffer sobre geography, {segmentos} "
                       f"segmentos por quadrante) e resumo do que cai dentro" + nota_invalidas(relatorio))}


# ---------------------------------------------------------------- agregar pontos
@ferramenta(
    nome="agregar_pontos", titulo="Agregar pontos", categoria="resumo", versao=1,
    descricao="Conta e resume pontos em polígonos existentes ou numa grade regular (quadrada ou hexagonal) "
              "desenhada em metros sobre a extensão dos pontos.",
    parametros=(
        Parametro("camada_pontos", "GPFeatureRecordSetLayer", "camada de pontos"),
        Parametro("camada_poligonos", "GPFeatureRecordSetLayer", "camada de polígonos", obrigatorio=False,
                  descricao="sem ela, a ferramenta desenha a grade"),
        Parametro("grade", "GPString", "tipo de grade", obrigatorio=False, padrao="quadrada",
                  opcoes=("quadrada", "hexagonal")),
        Parametro("tamanho", "GPLinearUnit", "tamanho da célula", obrigatorio=False,
                  padrao={"distance": 1, "units": "esriKilometers"}, minimo=1),
        Parametro("estatisticas", "GPMultiValue", "estatísticas", subtipo="GPString", obrigatorio=False),
        Parametro("manter_vazios", "GPBoolean", "manter células sem ponto", obrigatorio=False, padrao=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_pontos"]["feicoes"] * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX, "celulas_max": limites.GRADE_CELULAS_MAX},
)
def agregar_pontos(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    pts = entradas["camada_pontos"]
    if familia(pts)[2] != 0:
        raise ErroFerramenta("camada_nao_pontual", "camada_pontos precisa ser de pontos")
    if entradas.get("camada_poligonos"):
        return _resumir_dentro(
            ctx, {"camada_poligonos": entradas["camada_poligonos"], "camada_resumir": pts},
            {"estatisticas": parametros.get("estatisticas"), "atribuicao": "exclusivo",
             "manter_vazios": parametros.get("manter_vazios", False)}, destino, so_contagem=False)
    lado = float((parametros.get("tamanho") or {}).get("metros") or 1000.0)
    hexagonal = (parametros.get("grade") or "quadrada") == "hexagonal"
    manter_vazios = parametros.get("manter_vazios", False) is True
    srid, utm = pts["srid"], utm_da_camada(ctx, pts)
    with ctx.db() as cur:
        tipos_p = tipos_de(cur, pts["schema"], pts["tabela"])
        cur.execute(f"SELECT ceil((ST_XMax(e) - ST_XMin(e)) / %s + 1) * ceil((ST_YMax(e) - ST_YMin(e)) / %s + 1) "
                    f"AS n FROM (SELECT ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, {int(srid)}), "
                    f"{utm}) AS e FROM {tabela_de(pts)}) t", (lado, lado))
        celulas = int(cur.fetchone()["n"] or 0)
    if celulas > limites.GRADE_CELULAS_MAX:
        raise ErroFerramenta("grade_grande_demais",
                             f"tamanho: a grade teria {celulas} células, acima do limite de "
                             f"{limites.GRADE_CELULAS_MAX}; aumente o tamanho da célula",
                             {"campo": "tamanho", "celulas": celulas, "maximo": limites.GRADE_CELULAS_MAX})
    resumo_sql, _ = resumos_sql(parametros.get("estatisticas"), pts, tipos_p, "p", "p.fid")
    corpo = f"{resumo_sql}, " if resumo_sql else ""
    funcao = "ST_HexagonGrid" if hexagonal else "ST_SquareGrid"
    juncao = "LEFT JOIN" if manter_vazios else "JOIN"
    ctx.progresso(20, f"desenhando a grade {'hexagonal' if hexagonal else 'quadrada'} de {lado} m")
    select = (
        f"WITH ext AS (SELECT ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, {int(srid)}), {utm}) AS e "
        f"FROM {tabela_de(pts)}), "
        f"g AS (SELECT (c).i AS coluna, (c).j AS linha, ST_Transform((c).geom, {int(srid)}) AS geom "
        f"FROM ext, LATERAL {funcao}({lado!r}, ext.e) AS c) "
        f"SELECT g.coluna, g.linha, count(p.fid)::bigint AS contagem, {corpo}ST_Multi(g.geom) AS geom "
        f"FROM g {juncao} {tabela_de(pts)} p ON ST_Intersects(g.geom, {no_srid_de('p.geom', pts, srid)}) "
        f"GROUP BY g.coluna, g.linha, g.geom ORDER BY g.coluna, g.linha"
    )
    campos = escrever(ctx, destino, select, "MultiPolygon", srid)
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
            "metodo": (f"{funcao}({lado} m) desenhada em EPSG:{utm} e trazida de volta para EPSG:{srid}; "
                       f"ponto exatamente na aresta entra nas duas células vizinhas")}


# ---------------------------------------------------------------- enriquecer por proporção de área
@ferramenta(
    nome="enriquecer_por_area", titulo="Enriquecer por proporção de área", categoria="sobreposicao", versao=1,
    descricao="Distribui campos numéricos dos polígonos de origem para os polígonos de destino na proporção da "
              "área geodésica sobreposta; a soma distribuída conserva a soma de origem.",
    parametros=(
        Parametro("camada_destino", "GPFeatureRecordSetLayer", "polígonos a enriquecer"),
        Parametro("camada_origem", "GPFeatureRecordSetLayer", "polígonos com a variável"),
        Parametro("campos", "GPMultiValue", "campos a distribuir", subtipo="GPString",
                  descricao="campos numéricos da camada de origem; saem com o prefixo origem_"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: (e["camada_destino"]["feicoes"] + e["camada_origem"]["feicoes"]) * 3,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def enriquecer_por_area(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    d, o = entradas["camada_destino"], entradas["camada_origem"]
    for e in (d, o):
        if familia(e)[2] != 2:
            raise ErroFerramenta("camada_nao_poligonal", f"camada {e['titulo']!r} precisa ser poligonal")
    campos_pedidos = list(parametros.get("campos") or ())
    if not campos_pedidos:
        raise ErroFerramenta("sem_campos", "campos: informe ao menos um campo numérico a distribuir")
    srid = d["srid"]
    with ctx.db() as cur:
        tipos_o = tipos_de(cur, o["schema"], o["tabela"])
        limpa_d, limpa_o = limpo(cur, "d.geom", srid), limpo(cur, no_srid_de("o.geom", o, srid), srid)
    for c in campos_pedidos:
        coluna_de(o, c, "campos")
        if tipos_o.get(c) not in NUMERICAS:
            raise ErroFerramenta("campo_nao_numerico", f"campos: {c!r} é {tipos_o.get(c)}, não é numérico")
    relatorio = contar_invalidas(ctx, [("camada_destino", d), ("camada_origem", o)])
    fracao = (f"ST_Area({geografia(f'ST_Intersection({limpa_d}, {limpa_o})', srid)}) / "
              f"NULLIF(ST_Area({geografia(limpa_o, srid)}), 0)")
    # prefixo fixo: a camada de destino pode ter campo com o mesmo nome do campo distribuído
    distribuidos = ", ".join(
        f"COALESCE(sum(o.{ident(c)}::double precision * f.fr), 0)::double precision AS {ident('origem_' + c)}"
        for c in campos_pedidos)
    ctx.progresso(20, "repartindo por proporção de área")
    select = (
        f"SELECT {com_virgula(lista_campos(d, apelido='d'))}{distribuidos}, d.geom AS geom "
        f"FROM {tabela_de(d)} d "
        f"LEFT JOIN {tabela_de(o)} o ON ST_Intersects(d.geom, {no_srid_de('o.geom', o, srid)}) "
        f"LEFT JOIN LATERAL (SELECT {fracao} AS fr) f ON true "
        f"GROUP BY d.fid ORDER BY d.fid"
    )
    campos = escrever(ctx, destino, select, d["geometria"], srid)
    return {"geometria": d["geometria"], "srid": srid, "campos": campos,
            "metodo": ("repartição por proporção de área geodésica (ST_Area sobre geography, elipsoide WGS 84); "
                       "a soma só se conserva onde os polígonos de destino cobrem os de origem"
                       + nota_invalidas(relatorio))}


# ---------------------------------------------------------------- vizinho mais próximo e tabela de distâncias
@ferramenta(
    nome="vizinho_mais_proximo", titulo="Vizinho mais próximo (near)", categoria="proximidade", versao=1,
    descricao="Para cada feição, o identificador e a distância geodésica da feição mais próxima da outra camada.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("camada_vizinha", "GPFeatureRecordSetLayer", "camada dos vizinhos"),
        Parametro("distancia_maxima", "GPLinearUnit", "distância máxima", obrigatorio=False, minimo=0,
                  descricao="sem valor, procura o vizinho a qualquer distância"),
        Parametro("campos_vizinho", "GPMultiValue", "campos do vizinho", subtipo="GPString", obrigatorio=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada"]["feicoes"] * 2,
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX},
)
def vizinho_mais_proximo(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    a, b = entradas["camada"], entradas["camada_vizinha"]
    srid = a["srid"]
    pedidos = list(parametros.get("campos_vizinho") or ())
    for c in pedidos:
        coluna_de(b, c, "campos_vizinho")
    metros = (parametros.get("distancia_maxima") or {}).get("metros")
    ga, gb = geografia("a.geom", srid), geografia("b.geom", b["srid"])
    onde = f"WHERE ST_DWithin({ga}, {gb}, {float(metros)!r}) " if metros is not None else ""
    extras = "".join(f", b.{ident(c)} AS {ident('vizinho_' + c)}" for c in pedidos)
    traz = "".join(f", v.{ident('vizinho_' + c)}" for c in pedidos)
    ctx.progresso(20, "procurando o vizinho de cada feição")
    select = (
        f"SELECT {com_virgula(lista_campos(a, apelido='a'))}v.vizinho_fid, v.distancia_m"
        f"{traz}, a.geom AS geom "
        f"FROM {tabela_de(a)} a LEFT JOIN LATERAL ("
        f"SELECT b.fid AS vizinho_fid, ST_Distance({ga}, {gb})::double precision AS distancia_m{extras} "
        f"FROM {tabela_de(b)} b {onde}ORDER BY {gb} <-> {ga}, b.fid LIMIT 1) v ON true ORDER BY a.fid"
    )
    campos = escrever(ctx, destino, select, a["geometria"], srid)
    return {"geometria": a["geometria"], "srid": srid, "campos": campos,
            "metodo": ("ST_Distance sobre geography (elipsoide WGS 84), vizinho escolhido pelo operador de "
                       "distância do índice" + (f", teto de {metros} m" if metros is not None else ""))}


@ferramenta(
    nome="tabela_distancias", titulo="Tabela de distâncias", categoria="proximidade", versao=1,
    descricao="Uma linha por par origem-destino com a distância geodésica; a geometria é o segmento que liga o "
              "par, para o resultado poder ser desenhado no mapa.",
    parametros=(
        Parametro("camada_origem", "GPFeatureRecordSetLayer", "camada de origem"),
        Parametro("camada_destino", "GPFeatureRecordSetLayer", "camada de destino"),
        Parametro("distancia_maxima", "GPLinearUnit", "distância máxima", obrigatorio=False, minimo=0),
        Parametro("vizinhos_por_origem", "GPLong", "vizinhos por origem", obrigatorio=False, minimo=1,
                  maximo=limites.DISTANCIAS_VIZINHOS_MAX,
                  descricao="sem valor, todos os pares dentro da distância máxima"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["camada_origem"]["feicoes"] * e["camada_destino"]["feicoes"],
    limites={"feicoes_max": limites.VETOR_FEICOES_MAX, "pares_max": limites.DISTANCIAS_PARES_MAX},
)
def tabela_distancias(ctx, entradas, parametros, destino) -> dict:
    verificar_tamanho(entradas)
    a, b = entradas["camada_origem"], entradas["camada_destino"]
    srid = a["srid"]
    k = parametros.get("vizinhos_por_origem")
    metros = (parametros.get("distancia_maxima") or {}).get("metros")
    if k is None and a["feicoes"] * b["feicoes"] > limites.DISTANCIAS_PARES_MAX:
        raise ErroFerramenta(
            "pares_demais",
            f"{a['feicoes']} x {b['feicoes']} passa do limite de {limites.DISTANCIAS_PARES_MAX} pares; use "
            f"vizinhos_por_origem ou distancia_maxima",
            {"pares": a["feicoes"] * b["feicoes"], "maximo": limites.DISTANCIAS_PARES_MAX})
    ga, gb = geografia("a.geom", srid), geografia("b.geom", b["srid"])
    onde = f"WHERE ST_DWithin({ga}, {gb}, {float(metros)!r}) " if metros is not None else ""
    limite = f"LIMIT {int(k)}" if k is not None else ""
    ligacao = (f"ST_MakeLine(ST_ClosestPoint(a.geom, {no_srid_de('b.geom', b, srid)}), "
               f"ST_ClosestPoint({no_srid_de('b.geom', b, srid)}, a.geom))")
    ctx.progresso(20, "medindo as distâncias")
    select = (
        f"SELECT a.fid AS origem_fid, v.destino_fid, v.distancia_m, v.geom AS geom "
        f"FROM {tabela_de(a)} a JOIN LATERAL ("
        f"SELECT b.fid AS destino_fid, ST_Distance({ga}, {gb})::double precision AS distancia_m, "
        f"{ligacao} AS geom FROM {tabela_de(b)} b {onde}ORDER BY {gb} <-> {ga}, b.fid {limite}) v ON true "
        f"ORDER BY a.fid, v.destino_fid"
    )
    campos = escrever(ctx, destino, select, "LineString", srid)
    return {"geometria": "LineString", "srid": srid, "campos": campos,
            "metodo": ("ST_Distance sobre geography (elipsoide WGS 84) por par; a geometria é o segmento entre "
                       "os pontos mais próximos das duas feições"
                       + (f"; teto de {metros} m" if metros is not None else "")
                       + (f"; {int(k)} vizinho(s) por origem" if k is not None else ""))}
