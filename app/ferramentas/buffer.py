"""Área de influência (buffer) sobre uma camada vetorial do catálogo — a ferramenta de referência do registro
(itens L2-05-a e L2-05-b). Escreve `destino.schema.destino.tabela` com os campos da entrada mais `geom` e
devolve {geometria, srid, campos, metodo}; o executor cuida de fid/globalid/RLS (`plat.camada_preparar`), do
item e da proveniência.

Quatro coisas que a ferramenta faz e que o portão do L2-05-b cobra:
  * distância GEODÉSICA por padrão (`geography`, elipsoide WGS 84) — 1.000 m são 1.000 m em qualquer latitude;
    `metodo=plano` faz o buffer nas unidades da camada e por isso só vale em camada projetada;
  * distância fixa (parâmetro) ou por CAMPO numérico da própria feição, em metros;
  * anel: com `distancia_interna`, a saída é o buffer externo menos o interno (ST_Difference, que é operação
    booleana e por isso passa pela regra da casa ST_MakeValid + ST_ReducePrecision);
  * `dissolver`, que une tudo numa feição só e guarda a contagem de feições de origem.
"""

from __future__ import annotations

from app import limites
from app.ferramentas import vetor
from app.ferramentas.registro import Parametro, ferramenta

SEGMENTOS_POR_QUARTO = 48
CAMPO_DISSOLVIDO = [{"nome": "feicoes_origem", "tipo": "bigint", "alias": "feições de origem"}]


def expressao_buffer(cur, distancia: str, srid: int, metodo: str) -> str:
    """Buffer de `distancia` (expressão SQL em metros) devolvido no SRID da camada."""
    if metodo == "plano":
        if vetor.geografico(cur, srid):
            raise vetor.ErroFerramenta("buffer_plano_em_camada_geografica",
                                       "metodo=plano exige camada projetada em metros; use metodo=geodesico")
        return f"ST_Buffer(geom, {distancia}, {SEGMENTOS_POR_QUARTO})"
    geog = vetor.geografia("geom", srid)
    # 48 segmentos por quarto de círculo: o padrão do PostGIS (8) inscreve um polígono de 32 lados, cuja área
    # fica 0,64 % abaixo do círculo geodésico — mais que os 0,05 % que o portão do item aceita. Com 48 o desvio
    # medido contra a referência pyproj.Geod cai para ~0,014 % (tests/medidas/L2-05-b-vetor-basico.json).
    expr = f"ST_Buffer({geog}, {distancia}, {SEGMENTOS_POR_QUARTO})::geometry"
    return expr if srid == 4326 else f"ST_Transform({expr}, {srid})"


@ferramenta(
    nome="buffer", titulo="Área de influência (buffer)", categoria="proximidade", versao=2,
    descricao="Polígono a uma distância de cada feição; distância geodésica em metros por padrão.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada", descricao="item de camada vetorial"),
        Parametro("distancia", "GPLinearUnit", "distância", padrao={"distance": 100, "units": "esriMeters"},
                  minimo=0, maximo=limites.BUFFER_DISTANCIA_M_MAX, descricao="raio da área de influência"),
        Parametro("campo_distancia", "GPString", "campo com a distância", obrigatorio=False,
                  descricao="campo numérico com a distância em metros; substitui o parâmetro distância"),
        Parametro("distancia_interna", "GPLinearUnit", "distância interna (anel)", obrigatorio=False, minimo=0,
                  maximo=limites.BUFFER_DISTANCIA_M_MAX,
                  descricao="quando preenchida, a saída é o anel entre a distância interna e a externa"),
        Parametro("metodo", "GPString", "método", obrigatorio=False, padrao="geodesico",
                  opcoes=("geodesico", "plano"), descricao="geodesico usa geography; plano exige camada projetada"),
        Parametro("dissolver", "GPBoolean", "dissolver em uma só feição", obrigatorio=False, padrao=False),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["camada"]["feicoes"] * (3 if p.get("dissolver") else 1),
    limites={"distancia_m_max": limites.BUFFER_DISTANCIA_M_MAX, "feicoes_max": limites.VETOR_FEICOES_MAX},
)
def buffer(ctx, entradas, parametros, destino) -> dict:
    vetor.verificar_tamanho(entradas)
    origem = entradas["camada"]
    srid = origem["srid"]
    metodo = parametros.get("metodo") or "geodesico"
    interna = parametros.get("distancia_interna")
    campo = parametros.get("campo_distancia")
    fonte = vetor.tabela_de(origem)
    with ctx.db() as cur:
        if campo:
            if campo not in origem["campos"]:
                raise vetor.ErroFerramenta("campo_inexistente", f"campo_distancia: {campo!r} não é campo da camada")
            tipos = vetor.tipos_de(cur, origem["schema"], origem["tabela"])
            if tipos.get(campo) not in vetor.NUMERICAS:
                raise vetor.ErroFerramenta("campo_nao_numerico",
                                           f"campo_distancia: {campo!r} é {tipos.get(campo)}, não é numérico")
            distancia = f"GREATEST(coalesce({vetor.ident(campo)}, 0), 0)"
            rotulo = f"campo {campo}"
        else:
            distancia = repr(float(parametros["distancia"]["metros"]))
            rotulo = f"{parametros['distancia']['metros']} m"
        externo = expressao_buffer(cur, distancia, srid, metodo)
        if interna is not None:
            metros_interno = float(interna["metros"])
            if not campo and metros_interno >= float(parametros["distancia"]["metros"]):
                raise vetor.ErroFerramenta("anel_invertido",
                                           "distancia_interna deve ser menor que a distância externa")
            dentro = expressao_buffer(cur, repr(metros_interno), srid, metodo)
            expr = (f"ST_Difference({vetor.limpo(cur, externo, srid)}, {vetor.limpo(cur, dentro, srid)})")
            rotulo = f"anel de {metros_interno} m a {rotulo}"
        else:
            expr = externo
        expr = f"ST_Multi({expr})"
    relatorio = vetor.contar_invalidas(ctx, [("camada", origem)]) if interna is not None else {}
    ctx.log("INFO", f"buffer {metodo} de {rotulo} sobre {origem['feicoes']} feições de {origem['titulo']}")
    ctx.progresso(20, "calculando a área de influência")
    if parametros.get("dissolver"):
        select = (f"SELECT count(*)::bigint AS feicoes_origem, ST_Multi(ST_Union({expr})) AS geom FROM {fonte}")
    else:
        campos_sql = vetor.lista_campos(origem)
        prefixo = vetor.com_virgula(campos_sql)
        select = f"SELECT {prefixo}{expr} AS geom FROM {fonte} ORDER BY fid"
    campos = vetor.escrever(ctx, destino, select, "MultiPolygon", srid)
    if parametros.get("dissolver"):
        campos = [dict(CAMPO_DISSOLVIDO[0], tipo=campos[0]["tipo"])] if campos else list(CAMPO_DISSOLVIDO)
    ctx.progresso(70, "área de influência calculada")
    metodo_txt = (f"ST_Buffer({'geography' if metodo == 'geodesico' else 'plano'}, {rotulo})"
                  + (" + ST_Union" if parametros.get("dissolver") else "") + vetor.nota_invalidas(relatorio))
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos, "metodo": metodo_txt}
