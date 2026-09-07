"""Ferramenta de exemplo do registro (item L2-05-a): área de influência (buffer) geodésica em metros sobre uma
camada vetorial do catálogo, com `dissolver` opcional. É a referência de como uma ferramenta se declara e de
como escreve o destino: cria `destino.schema.destino.tabela` com os campos da entrada mais `geom`, e devolve
{geometria, srid, campos, metodo}; o executor cuida de fid/globalid/RLS (`plat.camada_preparar`), item e
proveniência. Distância em metros sobre geography (4326); outra projeção vai e volta por ST_Transform."""

from __future__ import annotations

from app import limites
from app.ferramentas.registro import Parametro, ferramenta

CAMPO_DISSOLVIDO = [{"nome": "feicoes_origem", "tipo": "bigint", "alias": "feições de origem"}]


@ferramenta(
    nome="buffer", titulo="Área de influência (buffer)", categoria="proximidade", versao=1,
    descricao="Polígono a uma distância fixa de cada feição; distância geodésica em metros.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada", descricao="item de camada vetorial"),
        Parametro("distancia", "GPLinearUnit", "distância", padrao={"distance": 100, "units": "esriMeters"},
                  minimo=0, maximo=limites.BUFFER_DISTANCIA_M_MAX, descricao="raio da área de influência"),
        Parametro("dissolver", "GPBoolean", "dissolver em uma só feição", obrigatorio=False, padrao=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["camada"]["feicoes"] * (3 if p.get("dissolver") else 1),
    limites={"distancia_m_max": limites.BUFFER_DISTANCIA_M_MAX},
)
def buffer(ctx, entradas, parametros, destino) -> dict:
    origem = entradas["camada"]
    metros = float(parametros["distancia"]["metros"])
    srid = origem["srid"]
    if srid == 4326:
        expr = f"ST_Multi(ST_Buffer(geom::geography, {metros})::geometry)"
    else:
        expr = f"ST_Multi(ST_Transform(ST_Buffer(ST_Transform(geom, 4326)::geography, {metros})::geometry, {srid}))"
    colunas = [f'"{c}"' for c in origem["campos"]]
    fonte = f'"{origem["schema"]}"."{origem["tabela"]}"'
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    ctx.log("INFO", f"buffer de {metros} m sobre {origem['feicoes']} feições de {origem['titulo']}")
    ctx.progresso(20, "calculando a área de influência")
    with ctx.db() as cur:
        if parametros.get("dissolver"):
            cur.execute(f'CREATE TABLE {alvo} AS SELECT count(*)::bigint AS feicoes_origem, '
                        f'ST_Multi(ST_Union({expr})) AS geom FROM {fonte}')
            campos = list(CAMPO_DISSOLVIDO)
        else:
            lista = ", ".join(colunas + [f"{expr} AS geom"])
            cur.execute(f'CREATE TABLE {alvo} AS SELECT {lista} FROM {fonte} ORDER BY fid')
            campos = [{"nome": c, "tipo": "text", "alias": c} for c in origem["campos"]]
        cur.execute(f'ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY')
        cur.execute(f'ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry(MultiPolygon, {srid}) USING geom')
        if campos and not parametros.get("dissolver"):
            cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s "
                        "AND table_name = %s", (destino["schema"], destino["tabela"]))
            tipos = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
            for c in campos:
                c["tipo"] = tipos.get(c["nome"], c["tipo"])
    ctx.progresso(70, "área de influência calculada")
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
            "metodo": f"ST_Buffer(geography, {metros} m)" + (" + ST_Union" if parametros.get("dissolver") else "")}
