"""Ferramentas de análise raster (item L2-05-e).

Treze ferramentas registradas no mesmo registro das vetoriais (`@ferramenta`, item L2-05-a), com o mesmo
manifesto tipado no vocabulário GP da Esri, o mesmo caminho de execução (em processo abaixo do custo
declarado, na fila acima dele), a mesma proveniência e a mesma superfície GPServer. O que muda é de onde
o dado vem e para onde vai:

* a ENTRADA é um item `raster` do catálogo do inquilino, lido onde ele está — COG no armazenamento de
  objetos, por caminho virtual do GDAL, janela por janela. Nenhuma ferramenta baixa o arquivo inteiro;
* a SAÍDA é um COG (perfil científico, ZSTD, blocos de 512, pirâmide) publicado como item `raster` com
  registro STAC, ou uma camada vetorial hospedada, conforme a natureza da ferramenta.

O que NÃO está aqui, e por quê: hidrologia (direção de fluxo, acumulação, bacia) fica FORA desta fase —
o `pysheds` e o `whitebox` não estão instalados nesta máquina e a decisão foi não escrever motor de
hidrologia próprio. Está escrito em docs/PARIDADE_FERRAMENTAS_RASTER.md, ao lado do resto do que falta
para o Spatial Analyst.
"""

from __future__ import annotations

from app import limites
from app.ferramentas.executor import ErroExecucao
from app.ferramentas.registro import Parametro, ferramenta
from app.raster import calculo, comandos, vetor_ponte, zonal
from app.raster import fonte as fonte_raster

ESTATISTICAS_ZONAIS = ("contagem", "soma", "media", "minimo", "maximo", "desvio", "mediana", "majoritario",
                       "classes")
PRODUTOS_TERRENO = ("declividade", "orientacao", "sombreamento", "rugosidade", "tpi")
_MODO_GDAL = {"declividade": "slope", "orientacao": "aspect", "sombreamento": "hillshade",
              "rugosidade": "roughness", "tpi": "TPI"}
TIPOS_RASTERIZACAO = ("Byte", "Int16", "Int32", "Float32", "Float64")


# ------------------------------------------------------------------ apoio comum
def _raster(entradas: dict, nome: str) -> dict:
    r = entradas.get(nome)
    if r is None:
        raise ErroExecucao(422, "raster_ausente", f"{nome}: raster de entrada obrigatório")
    return r


def _rasters(entradas: dict, nome: str) -> list[dict]:
    itens = [v for k, v in entradas.items() if k.startswith(f"{nome}[")]
    if not itens:
        raise ErroExecucao(422, "raster_ausente", f"{nome}: informe ao menos um raster")
    if len(itens) > limites.FERRAMENTA_RASTER_ENTRADAS_MAX:
        raise ErroExecucao(422, "rasters_demais",
                           f"{nome}: máximo de {limites.FERRAMENTA_RASTER_ENTRADAS_MAX} rasters por execução")
    return itens


def _aviso_nodata(ctx, raster: dict) -> dict:
    """O adversário passa raster SEM nodata declarado. Não é erro — é ambiguidade: o zero pode ser dado ou
    ausência. A ferramenta avisa em log e registra no resumo, e todo pixel entra na conta."""
    declarado = raster.get("nodata") is not None
    if not declarado:
        ctx.log("AVISO", f"o raster {raster['titulo']} não declara nodata: todos os pixels entram no cálculo, "
                         "inclusive os que valham zero por ausência de dado")
    return {"nodata_declarado": declarado, "nodata": raster.get("nodata")}


def _conferir_saida(largura: int, altura: int) -> None:
    if largura * altura > limites.FERRAMENTA_RASTER_PIXELS_SAIDA_MAX:
        raise ErroExecucao(422, "saida_grande_demais",
                           f"raster de saída com {largura * altura} pixels acima do teto desta instalação "
                           f"({limites.FERRAMENTA_RASTER_PIXELS_SAIDA_MAX})")


def _publicar_cog(ctx, bruto, env: dict, *, compressao: str = "ZSTD", categorico: bool = False,
                  metodo: str, resumo: dict, bandas: list[dict] | None = None) -> dict:
    saida = ctx.dir_trabalho / "saida.tif"
    cog = comandos.finalizar_cog(ctx, bruto, saida, env, compressao=compressao, categorico=categorico)
    return {"familia": "raster", "arquivo": saida, "env": env, "metodo": metodo, "resumo": resumo,
            "cog": cog, "bandas": bandas or [{"nome": "banda_1"}]}


def _limites_comuns(a: dict, b) -> bool:
    x0, y0, x1, y1 = a["limites"]
    return not (b[2] <= x0 or b[0] >= x1 or b[3] <= y0 or b[1] >= y1)


# ------------------------------------------------------------------ 1. estatísticas zonais
@ferramenta(
    nome="estatisticas_zonais", titulo="Estatísticas zonais", categoria="resumo", versao=1,
    descricao="Resume os pixels de um raster dentro de cada polígono de uma camada, com peso pela fração "
              "de pixel coberta.",
    parametros=(
        Parametro("zonas", "GPFeatureRecordSetLayer", "camada de zonas", descricao="polígonos das zonas"),
        Parametro("raster", "GPRasterDataLayer", "raster de valores"),
        Parametro("banda", "GPLong", "banda", obrigatorio=False, padrao=1, minimo=1, maximo=64),
        Parametro("estatisticas", "GPMultiValue", "estatísticas", subtipo="GPString", obrigatorio=False,
                  padrao=["contagem", "soma", "media", "minimo", "maximo", "desvio"], opcoes=ESTATISTICAS_ZONAIS,
                  descricao="contagem, soma, media, minimo, maximo, desvio, mediana, majoritario, classes"),
        Parametro("fracao", "GPBoolean", "ponderar pela fração de pixel", obrigatorio=False, padrao=True,
                  descricao="falso reproduz o critério clássico: entra o pixel cujo CENTRO cai na zona"),
        Parametro("todos_pixels", "GPBoolean", "incluir todo pixel tocado", obrigatorio=False, padrao=False),
        Parametro("nodata", "GPDouble", "nodata declarado", obrigatorio=False,
                  descricao="usado quando o raster não declara nodata"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["zonas"]["feicoes"] * (3 if p.get("mediana") else 2),
    limites={"zonas_max": limites.FERRAMENTA_RASTER_ZONAS_MAX, "subpixel": zonal.SUBPIXEL},
)
def estatisticas_zonais(ctx, entradas, parametros, destino) -> dict:
    zonas_camada = entradas["zonas"]
    raster = _raster(entradas, "raster")
    if zonas_camada["feicoes"] > limites.FERRAMENTA_RASTER_ZONAS_MAX:
        raise ErroExecucao(422, "zonas_demais", f"a camada tem {zonas_camada['feicoes']} zonas, acima do teto "
                                                f"de {limites.FERRAMENTA_RASTER_ZONAS_MAX}")
    banda = int(parametros.get("banda") or 1)
    if banda > raster["bandas"]:
        raise ErroExecucao(422, "banda_inexistente", f"o raster tem {raster['bandas']} banda(s); pediu a {banda}")
    pedidas = tuple(parametros.get("estatisticas") or ("contagem", "media"))
    srid = raster["epsg"]
    if not srid:
        raise ErroExecucao(422, "raster_sem_epsg", "o raster não tem EPSG resolvível: reprojete-o antes")
    aviso = _aviso_nodata(ctx, raster)
    nodata = parametros.get("nodata") if raster.get("nodata") is None else raster.get("nodata")
    ctx.log("INFO", f"estatísticas zonais de {zonas_camada['feicoes']} zonas sobre {raster['titulo']} "
                    f"({raster['largura']}x{raster['altura']}, bloco {raster['bloco']})")
    resultados = []
    fora = 0
    with fonte_raster.abrir(raster["origem"]) as ds:
        for i, (fid, _props, geometria, caixa) in enumerate(vetor_ponte.zonas(ctx, zonas_camada, srid), start=1):
            if not _limites_comuns(raster, caixa):
                fora += 1
                resultados.append((fid, {k: None for k in pedidas} | {"contagem": 0, "peso": 0.0}))
                continue
            try:
                r = zonal.estatisticas_da_zona(ds, banda, geometria, caixa, pedidas,
                                               fracao=bool(parametros.get("fracao", True)),
                                               todos_pixels=bool(parametros.get("todos_pixels")), nodata=nodata)
            except zonal.ZonaGrande as e:
                raise ErroExecucao(422, "zona_grande_demais", str(e)) from e
            resultados.append((fid, r))
            if i % 200 == 0:
                ctx.progresso(min(75, 10 + int(65 * i / max(zonas_camada["feicoes"], 1))), f"{i} zonas")
                ctx.verificar()
    return _gravar_zonais(ctx, zonas_camada, destino, resultados, pedidas, srid, aviso, fora, banda)


_TIPO_ZONAL = {"contagem": "bigint", "peso": "double precision", "soma": "double precision",
               "media": "double precision", "minimo": "double precision", "maximo": "double precision",
               "desvio": "double precision", "mediana": "double precision", "majoritario": "double precision",
               "classes": "jsonb"}


def _gravar_zonais(ctx, zonas_camada, destino, resultados, pedidas, srid, aviso, fora, banda) -> dict:
    colunas = ["contagem", "peso"] + [p for p in pedidas if p not in ("contagem", "peso")]
    campos_origem = zonas_camada.get("campos") or []
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    origem = f'"{zonas_camada["schema"]}"."{zonas_camada["tabela"]}"'
    lista = ", ".join(['fid AS fid_origem'] + [f'"{c}"' for c in campos_origem]
                      + [f"ST_Multi(ST_Transform(geom, {int(srid)})) AS geom"])
    ctx.progresso(78, "gravando a camada de zonas com as estatísticas")
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} AS SELECT {lista} FROM {origem} ORDER BY fid")
        for c in colunas:
            cur.execute(f'ALTER TABLE {alvo} ADD COLUMN "zs_{c}" {_TIPO_ZONAL[c]}')
        cur.executemany(
            f'UPDATE {alvo} SET ' + ", ".join(f'"zs_{c}" = %s' for c in colunas) + " WHERE fid_origem = %s",
            [[_valor_zonal(c, r) for c in colunas] + [fid] for fid, r in resultados],
        )
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s "
                    "AND table_name = %s", (destino["schema"], destino["tabela"]))
        tipos = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
    campos = [{"nome": "fid_origem", "tipo": tipos.get("fid_origem", "bigint"), "alias": "fid de origem"}]
    campos += [{"nome": c, "tipo": tipos.get(c, "text"), "alias": c} for c in campos_origem]
    campos += [{"nome": f"zs_{c}", "tipo": tipos.get(f"zs_{c}", _TIPO_ZONAL[c]), "alias": c} for c in colunas]
    return {"geometria": "MultiPolygon", "srid": srid, "campos": campos,
            "metodo": f"estatísticas zonais banda {banda}, peso por fração de pixel "
                      f"({zonal.SUBPIXEL}x{zonal.SUBPIXEL} amostras), {len(resultados)} zonas, "
                      f"{fora} fora da extensão; {aviso}"}


def _valor_zonal(coluna: str, r: dict):
    import json as _json

    v = r.get(coluna)
    if coluna == "classes" and v is not None:
        return _json.dumps(v)
    return v


# ------------------------------------------------------------------ 2. calculadora
@ferramenta(
    nome="calculadora_raster", titulo="Calculadora raster", categoria="raster", versao=1,
    descricao="Avalia uma expressão sobre as bandas de um ou mais rasters alinhados, bloco a bloco.",
    parametros=(
        Parametro("rasters", "GPMultiValue", "rasters", subtipo="GPRasterDataLayer",
                  descricao="na ordem; as bandas são numeradas em sequência sobre eles (b1, b2, ...)"),
        Parametro("expressao", "GPString", "expressão",
                  descricao="ex.: (b4-b1)/(b4+b1) para NDVI com b1=vermelho e b4=infravermelho"),
        Parametro("tipo_saida", "GPString", "tipo de saída", obrigatorio=False, padrao="float32",
                  opcoes=calculo.TIPOS_SAIDA),
        Parametro("nodata", "GPDouble", "nodata da saída", obrigatorio=False, padrao=-9999.0),
        Parametro("reamostragem", "GPString", "reamostragem", obrigatorio=False, opcoes=comandos.REAMOSTRAGENS,
                  descricao="declare quando os rasters não estiverem na mesma grade"),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: sum(e["largura"] * e["altura"] for e in entradas.values()) // 1000,
    limites={"expressao_max": 200, "rasters_max": limites.FERRAMENTA_RASTER_ENTRADAS_MAX},
)
def calculadora_raster(ctx, entradas, parametros, destino) -> dict:
    itens = _rasters(entradas, "rasters")
    env = fonte_raster.ambiente(*[i["origem"] for i in itens])
    caminhos = [i["caminho"] for i in itens]
    _conferir_saida(itens[0]["largura"], itens[0]["altura"])
    for i in itens:
        _aviso_nodata(ctx, i)
    alinhados = _alinhar(ctx, itens, caminhos, parametros.get("reamostragem"), env)
    ctx.progresso(30, "avaliando a expressão bloco a bloco")
    bruto = ctx.dir_trabalho / "calculo.tif"
    datasets = []
    try:
        for caminho, item in zip(alinhados, itens, strict=True):
            cm = fonte_raster.abrir(fonte_raster.do_arquivo(caminho) if caminho != item["caminho"]
                                    else item["origem"])
            datasets.append((cm, cm.__enter__()))
        try:
            info = calculo.calcular([d for _, d in datasets], parametros["expressao"], bruto,
                                    dtype=parametros.get("tipo_saida") or "float32",
                                    nodata=parametros.get("nodata"))
        except calculo.ErroCalculo as e:
            raise ErroExecucao(422, "expressao_invalida", str(e)) from e
    finally:
        for cm, _ in reversed(datasets):
            cm.__exit__(None, None, None)
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, metodo=f"numexpr: {parametros['expressao']}",
                         resumo={"expressao": parametros["expressao"], **info},
                         bandas=[{"nome": "resultado"}])


def _alinhar(ctx, itens: list[dict], caminhos: list[str], reamostragem: str | None, env: dict) -> list[str]:
    """Rasters fora da mesma grade só seguem quando a reamostragem é DECLARADA; então cada um é levado à
    grade do primeiro por gdalwarp. Sem declaração, a ferramenta recusa dizendo o que difere."""
    base = itens[0]
    fora = [i for i in itens[1:] if (i["largura"], i["altura"]) != (base["largura"], base["altura"])
            or i["epsg"] != base["epsg"] or i["resolucao"] != base["resolucao"]]
    if not fora:
        return caminhos
    if not reamostragem:
        nomes = ", ".join(i["titulo"] for i in fora)
        raise ErroExecucao(422, "rasters_desalinhados",
                           f"os rasters não estão na mesma grade ({nomes}); declare 'reamostragem' para que "
                           "eles sejam levados à grade do primeiro, ou reprojete-os antes")
    saida = [caminhos[0]]
    x0, y0, x1, y1 = base["limites"]
    for i, item in enumerate(itens[1:], start=1):
        if item not in fora:
            saida.append(caminhos[i])
            continue
        destino = ctx.dir_trabalho / f"alinhado_{i}.tif"
        ctx.log("INFO", f"reamostrando {item['titulo']} para a grade de {base['titulo']} ({reamostragem})")
        comandos.rodar(ctx, ["gdalwarp", "-of", "GTiff", "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
                             "-t_srs", f"EPSG:{base['epsg']}", "-te", x0, y0, x1, y1,
                             "-ts", base["largura"], base["altura"], "-r",
                             comandos.reamostragem_gdal(reamostragem), "-overwrite",
                             caminhos[i], str(destino)], env, "alinhamento")
        saida.append(str(destino))
    return saida


# ------------------------------------------------------------------ 3. reclassificar
@ferramenta(
    nome="reclassificar_raster", titulo="Reclassificar", categoria="raster", versao=1,
    descricao="Troca faixas de valor por classes, segundo uma tabela declarada.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("banda", "GPLong", "banda", obrigatorio=False, padrao=1, minimo=1, maximo=64),
        Parametro("tabela", "GPString", "tabela de faixas",
                  descricao="min-max:classe separadas por ponto e vírgula; * é aberto; ex.: '0-10:1;10-*:2'"),
        Parametro("classe_fora", "GPDouble", "classe do que fica fora das faixas", obrigatorio=False),
        Parametro("tipo_saida", "GPString", "tipo de saída", obrigatorio=False, padrao="int16",
                  opcoes=calculo.TIPOS_SAIDA),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 1000,
    limites={},
)
def reclassificar_raster(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    env = fonte_raster.ambiente(raster["origem"])
    _conferir_saida(raster["largura"], raster["altura"])
    aviso = _aviso_nodata(ctx, raster)
    try:
        faixas = calculo.tabela_de_reclassificacao(parametros["tabela"])
    except calculo.ErroCalculo as e:
        raise ErroExecucao(422, "tabela_invalida", str(e)) from e
    bruto = ctx.dir_trabalho / "reclass.tif"
    ctx.progresso(30, "reclassificando bloco a bloco")
    with fonte_raster.abrir(raster["origem"]) as ds:
        info = calculo.reclassificar(ds, faixas, bruto, banda=int(parametros.get("banda") or 1),
                                     dtype=parametros.get("tipo_saida") or "int16",
                                     classe_fora=parametros.get("classe_fora"))
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, categorico=True,
                         metodo=f"reclassificação por faixas: {parametros['tabela']}",
                         resumo={"faixas": [[a, b, c] for a, b, c in faixas], **info, **aviso},
                         bandas=[{"nome": "classe"}])


# ------------------------------------------------------------------ 4. recortar
@ferramenta(
    nome="recortar_raster", titulo="Recortar por polígono", categoria="raster", versao=1,
    descricao="Recorta e mascara o raster pelos polígonos de uma camada.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("mascara", "GPFeatureRecordSetLayer", "camada de recorte"),
        Parametro("cortar_pela_camada", "GPBoolean", "encolher a extensão até a camada", obrigatorio=False,
                  padrao=True),
        Parametro("nodata", "GPDouble", "nodata da saída", obrigatorio=False, padrao=-9999.0),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 1000,
    limites={},
)
def recortar_raster(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    mascara = entradas["mascara"]
    env = fonte_raster.ambiente(raster["origem"])
    aviso = _aviso_nodata(ctx, raster)
    corte = vetor_ponte.exportar(ctx, mascara, raster["epsg"], ctx.dir_trabalho / "recorte.geojson", campos=[])
    ctx.progresso(30, "recortando (gdalwarp -cutline)")
    bruto = ctx.dir_trabalho / "recorte.tif"
    try:
        comandos.reprojetar(ctx, [raster["caminho"]], bruto, env, epsg_destino=None, resolucao=None,
                            reamostragem="vizinho", recorte=str(corte),
                            cortar_pela_camada=bool(parametros.get("cortar_pela_camada", True)),
                            nodata_destino=parametros.get("nodata"))
    except comandos.ErroComando as e:
        if "cutline" in str(e).lower() or "empty" in str(e).lower():
            raise ErroExecucao(422, "sem_intersecao",
                               "a camada de recorte não toca a extensão do raster") from e
        raise ErroExecucao(422, "recorte_falhou", str(e)) from e
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, metodo="gdalwarp -cutline", resumo={"zonas": mascara["feicoes"], **aviso},
                         bandas=[{"nome": f"banda_{i}"} for i in range(1, raster["bandas"] + 1)])


# ------------------------------------------------------------------ 5. reprojetar / reamostrar
@ferramenta(
    nome="reprojetar_raster", titulo="Reprojetar e reamostrar", categoria="raster", versao=1,
    descricao="Muda o sistema de coordenadas e/ou a resolução do raster, com reamostragem declarada.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("epsg", "GPLong", "EPSG de destino", obrigatorio=False, minimo=1024, maximo=999999),
        Parametro("resolucao", "GPDouble", "resolução de destino", obrigatorio=False, minimo=0),
        Parametro("reamostragem", "GPString", "reamostragem", obrigatorio=False, padrao="bilinear",
                  opcoes=comandos.REAMOSTRAGENS),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 800,
    limites={},
)
def reprojetar_raster(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    if not parametros.get("epsg") and not parametros.get("resolucao"):
        raise ErroExecucao(422, "sem_destino", "informe ao menos 'epsg' ou 'resolucao'")
    env = fonte_raster.ambiente(raster["origem"])
    aviso = _aviso_nodata(ctx, raster)
    bruto = ctx.dir_trabalho / "reprojetado.tif"
    ctx.progresso(30, "reprojetando (gdalwarp)")
    comandos.reprojetar(ctx, [raster["caminho"]], bruto, env, epsg_destino=parametros.get("epsg"),
                        resolucao=parametros.get("resolucao"),
                        reamostragem=parametros.get("reamostragem") or "bilinear")
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(
        ctx, bruto, env,
        metodo=f"gdalwarp -t_srs EPSG:{parametros.get('epsg') or raster['epsg']} "
               f"-r {parametros.get('reamostragem') or 'bilinear'}",
        resumo={"epsg_origem": raster["epsg"], "epsg_destino": parametros.get("epsg") or raster["epsg"],
                "resolucao": parametros.get("resolucao"), **aviso},
        bandas=[{"nome": f"banda_{i}"} for i in range(1, raster["bandas"] + 1)])


# ------------------------------------------------------------------ 6. mosaico
@ferramenta(
    nome="mosaico_raster", titulo="Mosaico", categoria="raster", versao=1,
    descricao="Junta vários rasters num só, com reamostragem declarada.",
    parametros=(
        Parametro("rasters", "GPMultiValue", "rasters", subtipo="GPRasterDataLayer"),
        Parametro("epsg", "GPLong", "EPSG de destino", obrigatorio=False, minimo=1024, maximo=999999),
        Parametro("resolucao", "GPDouble", "resolução de destino", obrigatorio=False, minimo=0),
        Parametro("reamostragem", "GPString", "reamostragem", obrigatorio=False, padrao="vizinho",
                  opcoes=comandos.REAMOSTRAGENS),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: sum(e["largura"] * e["altura"] for e in entradas.values()) // 800,
    limites={"rasters_max": limites.FERRAMENTA_RASTER_ENTRADAS_MAX},
)
def mosaico_raster(ctx, entradas, parametros, destino) -> dict:
    itens = _rasters(entradas, "rasters")
    env = fonte_raster.ambiente(*[i["origem"] for i in itens])
    bandas = {i["bandas"] for i in itens}
    if len(bandas) > 1:
        raise ErroExecucao(422, "bandas_diferentes",
                           f"os rasters têm contagens de banda diferentes ({sorted(bandas)}): o mosaico exige "
                           "a mesma contagem")
    bruto = ctx.dir_trabalho / "mosaico.tif"
    ctx.progresso(30, "montando o mosaico (gdalwarp)")
    comandos.reprojetar(ctx, [i["caminho"] for i in itens], bruto, env, epsg_destino=parametros.get("epsg"),
                        resolucao=parametros.get("resolucao"),
                        reamostragem=parametros.get("reamostragem") or "vizinho")
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, metodo="gdalwarp (mosaico)",
                         resumo={"rasters": len(itens), "titulos": [i["titulo"] for i in itens]},
                         bandas=[{"nome": f"banda_{i}"} for i in range(1, itens[0]["bandas"] + 1)])


# ------------------------------------------------------------------ 7. terreno
@ferramenta(
    nome="terreno_raster", titulo="Terreno (declividade, orientação, sombreamento)", categoria="raster",
    versao=1,
    descricao="Declividade, orientação, sombreamento, rugosidade ou índice de posição topográfica sobre um "
              "modelo de elevação, pelo gdaldem.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "modelo de elevação"),
        Parametro("produto", "GPString", "produto", obrigatorio=False, padrao="declividade",
                  opcoes=PRODUTOS_TERRENO),
        Parametro("unidade", "GPString", "unidade da declividade", obrigatorio=False, padrao="grau",
                  opcoes=("grau", "porcento")),
        Parametro("fator_z", "GPDouble", "fator z", obrigatorio=False, padrao=1.0, minimo=0,
                  descricao="razão entre a unidade vertical e a horizontal"),
        Parametro("escala", "GPDouble", "escala (unidades horizontais por unidade vertical)", obrigatorio=False,
                  minimo=0, descricao="obrigatória quando o CRS é geográfico: ~111320 para metros/grau"),
        Parametro("azimute", "GPDouble", "azimute do sol", obrigatorio=False, padrao=315.0, minimo=0,
                  maximo=360),
        Parametro("altitude", "GPDouble", "altitude do sol", obrigatorio=False, padrao=45.0, minimo=0,
                  maximo=90),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 800,
    limites={},
)
def terreno_raster(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    produto = parametros.get("produto") or "declividade"
    escala = parametros.get("escala")
    if raster.get("geografico") and produto in ("declividade", "sombreamento") and not escala:
        raise ErroExecucao(
            422, "crs_geografico",
            f"o raster está em coordenadas geográficas (EPSG:{raster['epsg']}): a {produto} sairia em graus "
            "por grau, que não é declividade. Reprojete para um CRS métrico ou declare 'escala' (a razão "
            "entre unidade horizontal e vertical; ~111320 para metros por grau perto do equador).",
            {"campo": "escala", "epsg": raster["epsg"]})
    env = fonte_raster.ambiente(raster["origem"])
    aviso = _aviso_nodata(ctx, raster)
    bruto = ctx.dir_trabalho / "terreno.tif"
    ctx.progresso(30, f"gdaldem {_MODO_GDAL[produto]}")
    comandos.declividade(ctx, raster["caminho"], bruto, env, modo=_MODO_GDAL[produto], escala=escala,
                         fator_z=float(parametros.get("fator_z") or 1.0),
                         unidade=parametros.get("unidade") or "grau",
                         azimute=float(parametros.get("azimute") or 315.0),
                         altitude=float(parametros.get("altitude") or 45.0))
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env,
                         metodo=f"gdaldem {_MODO_GDAL[produto]} (fator z {parametros.get('fator_z') or 1.0}"
                                + (f", escala {escala}" if escala else "") + ")",
                         resumo={"produto": produto, "escala": escala, **aviso},
                         bandas=[{"nome": produto}])


# ------------------------------------------------------------------ 8. curvas de nível
@ferramenta(
    nome="curvas_de_nivel", titulo="Curvas de nível", categoria="raster", versao=1,
    descricao="Isolinhas de um raster contínuo, pelo gdal_contour.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("banda", "GPLong", "banda", obrigatorio=False, padrao=1, minimo=1, maximo=64),
        Parametro("intervalo", "GPDouble", "intervalo entre curvas", minimo=0),
        Parametro("base", "GPDouble", "cota de base", obrigatorio=False, padrao=0.0),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 500,
    limites={"feicoes_max": limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX},
)
def curvas_de_nivel(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    if not float(parametros.get("intervalo") or 0):
        raise ErroExecucao(422, "intervalo_invalido", "o intervalo entre curvas tem de ser maior que zero")
    env = fonte_raster.ambiente(raster["origem"])
    arquivo = ctx.dir_trabalho / "curvas.geojson"
    ctx.progresso(30, "gdal_contour")
    comandos.curvas(ctx, raster["caminho"], arquivo, env, intervalo=float(parametros["intervalo"]),
                    banda=int(parametros.get("banda") or 1), base=float(parametros.get("base") or 0.0))
    ctx.progresso(60, "carregando as curvas na camada")
    n = vetor_ponte.carregar_geojson(ctx, destino, arquivo, raster["epsg"],
                                     [{"nome": "cota", "tipo": "double precision"}], "MultiLineString")
    if n > limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX:
        raise ErroExecucao(422, "feicoes_demais", f"{n} curvas acima do teto "
                                                  f"{limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX}: aumente o "
                                                  "intervalo")
    return {"geometria": "MultiLineString", "srid": raster["epsg"],
            "campos": [{"nome": "cota", "tipo": "double precision", "alias": "cota"}],
            "metodo": f"gdal_contour -i {parametros['intervalo']} (banda {parametros.get('banda') or 1})"}


# ------------------------------------------------------------------ 9. vetorizar
@ferramenta(
    nome="vetorizar_raster", titulo="Vetorizar", categoria="raster", versao=1,
    descricao="Converte regiões de mesmo valor em polígonos, pelo gdal_polygonize.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("banda", "GPLong", "banda", obrigatorio=False, padrao=1, minimo=1, maximo=64),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 500,
    limites={"feicoes_max": limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX},
)
def vetorizar_raster(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    env = fonte_raster.ambiente(raster["origem"])
    arquivo = ctx.dir_trabalho / "vetorizado.geojson"
    ctx.progresso(30, "gdal_polygonize")
    comandos.vetorizar(ctx, raster["caminho"], arquivo, env, banda=int(parametros.get("banda") or 1))
    ctx.progresso(60, "carregando os polígonos na camada")
    n = vetor_ponte.carregar_geojson(ctx, destino, arquivo, raster["epsg"],
                                     [{"nome": "valor", "tipo": "double precision"}], "MultiPolygon")
    if n > limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX:
        raise ErroExecucao(422, "feicoes_demais",
                           f"{n} polígonos acima do teto {limites.FERRAMENTA_RASTER_FEICOES_SAIDA_MAX}: "
                           "reclassifique o raster antes de vetorizar")
    return {"geometria": "MultiPolygon", "srid": raster["epsg"],
            "campos": [{"nome": "valor", "tipo": "double precision", "alias": "valor"}],
            "metodo": f"gdal_polygonize (banda {parametros.get('banda') or 1})"}


# ------------------------------------------------------------------ 10. rasterizar
@ferramenta(
    nome="rasterizar_camada", titulo="Rasterizar camada", categoria="raster", versao=1,
    descricao="Queima uma camada vetorial numa grade regular, pelo gdal_rasterize.",
    parametros=(
        Parametro("camada", "GPFeatureRecordSetLayer", "camada de entrada"),
        Parametro("campo", "GPString", "campo do valor", obrigatorio=False,
                  descricao="sem campo, queima o valor fixo"),
        Parametro("valor", "GPDouble", "valor fixo", obrigatorio=False, padrao=1.0),
        Parametro("resolucao", "GPDouble", "resolução da grade", minimo=0),
        Parametro("tipo_saida", "GPString", "tipo de saída", obrigatorio=False, padrao="Float32",
                  opcoes=TIPOS_RASTERIZACAO),
        Parametro("nodata", "GPDouble", "nodata da saída", obrigatorio=False, padrao=-9999.0),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["camada"]["feicoes"] * 2,
    limites={"pixels_saida_max": limites.FERRAMENTA_RASTER_PIXELS_SAIDA_MAX},
)
def rasterizar_camada(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["camada"]
    campo = parametros.get("campo")
    campos = camada.get("campos") or []
    if campo and campo not in campos:
        raise ErroExecucao(422, "campo_inexistente",
                           f"a camada não tem o campo {campo!r} (tem: {', '.join(campos) or 'nenhum'})",
                           {"campo": "campo"})
    resolucao = float(parametros["resolucao"])
    arquivo = vetor_ponte.exportar(ctx, camada, camada["srid"], ctx.dir_trabalho / "rasterizar.geojson",
                                   campos=[campo] if campo else [])
    with ctx.db() as cur:
        cur.execute(f'SELECT ST_XMin(e) AS x0, ST_YMin(e) AS y0, ST_XMax(e) AS x1, ST_YMax(e) AS y1 FROM '
                    f'(SELECT ST_Extent(geom) AS e FROM "{camada["schema"]}"."{camada["tabela"]}") s')
        e = cur.fetchone()
    if e is None or e["x0"] is None:
        raise ErroExecucao(422, "camada_vazia", "a camada não tem geometria para rasterizar")
    x0 = float(e["x0"]) - resolucao
    y0 = float(e["y0"]) - resolucao
    x1 = float(e["x1"]) + resolucao
    y1 = float(e["y1"]) + resolucao
    _conferir_saida(int((x1 - x0) / resolucao) + 1, int((y1 - y0) / resolucao) + 1)
    bruto = ctx.dir_trabalho / "rasterizado.tif"
    ctx.progresso(40, "gdal_rasterize")
    comandos.rasterizar(ctx, str(arquivo), bruto, fonte_raster.ambiente(), campo=campo,
                        valor_fixo=parametros.get("valor"), resolucao=resolucao, limites=(x0, y0, x1, y1),
                        tipo=parametros.get("tipo_saida") or "Float32",
                        nodata=float(parametros.get("nodata") if parametros.get("nodata") is not None else -9999))
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, fonte_raster.ambiente(),
                         metodo=f"gdal_rasterize {'-a ' + campo if campo else '-burn'} -tr {resolucao}",
                         resumo={"feicoes": camada["feicoes"], "campo": campo, "resolucao": resolucao},
                         bandas=[{"nome": campo or "valor"}])


# ------------------------------------------------------------------ 11. amostrar
@ferramenta(
    nome="amostrar_raster", titulo="Amostrar valores em pontos", categoria="resumo", versao=1,
    descricao="Lê o valor de cada banda do raster na posição de cada ponto de uma camada.",
    parametros=(
        Parametro("pontos", "GPFeatureRecordSetLayer", "camada de pontos"),
        Parametro("raster", "GPRasterDataLayer", "raster de valores"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["pontos"]["feicoes"],
    limites={"pontos_max": limites.FERRAMENTA_RASTER_ZONAS_MAX},
)
def amostrar_raster(ctx, entradas, parametros, destino) -> dict:
    pontos = entradas["pontos"]
    raster = _raster(entradas, "raster")
    if pontos["feicoes"] > limites.FERRAMENTA_RASTER_ZONAS_MAX:
        raise ErroExecucao(422, "pontos_demais", f"{pontos['feicoes']} pontos acima do teto "
                                                 f"{limites.FERRAMENTA_RASTER_ZONAS_MAX}")
    srid = raster["epsg"]
    bandas = list(range(1, raster["bandas"] + 1))
    _aviso_nodata(ctx, raster)
    ctx.progresso(30, "lendo os valores")
    fids, coordenadas = [], []
    with ctx.db() as cur:
        cur.execute(f'SELECT fid, ST_X(p) AS x, ST_Y(p) AS y FROM (SELECT fid, '
                    f'ST_PointOnSurface(ST_Transform(geom, {int(srid)})) AS p '
                    f'FROM "{pontos["schema"]}"."{pontos["tabela"]}" WHERE geom IS NOT NULL) s ORDER BY fid')
        for r in cur.fetchall():
            fids.append(int(r["fid"]))
            coordenadas.append((float(r["x"]), float(r["y"])))
    with fonte_raster.abrir(raster["origem"]) as ds:
        valores = calculo.amostrar(ds, coordenadas, bandas)
    colunas = [f"valor_b{b}" for b in bandas]
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    origem = f'"{pontos["schema"]}"."{pontos["tabela"]}"'
    campos_origem = pontos.get("campos") or []
    lista = ", ".join(['fid AS fid_origem'] + [f'"{c}"' for c in campos_origem]
                      + [f"ST_Multi(ST_Transform(geom, {int(srid)})) AS geom"])
    ctx.progresso(70, "gravando a camada de saída")
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} AS SELECT {lista} FROM {origem} WHERE geom IS NOT NULL ORDER BY fid")
        for c in colunas:
            cur.execute(f'ALTER TABLE {alvo} ADD COLUMN "{c}" double precision')
        cur.executemany(f'UPDATE {alvo} SET ' + ", ".join(f'"{c}" = %s' for c in colunas)
                        + " WHERE fid_origem = %s",
                        [[*v, fid] for fid, v in zip(fids, valores, strict=True)])
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s "
                    "AND table_name = %s", (destino["schema"], destino["tabela"]))
        tipos = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
    campos = [{"nome": "fid_origem", "tipo": tipos.get("fid_origem", "bigint"), "alias": "fid de origem"}]
    campos += [{"nome": c, "tipo": tipos.get(c, "text"), "alias": c} for c in campos_origem]
    campos += [{"nome": c, "tipo": "double precision", "alias": c} for c in colunas]
    fora = sum(1 for v in valores if all(x is None for x in v))
    return {"geometria": "MultiPoint", "srid": srid, "campos": campos,
            "metodo": f"amostragem de {len(bandas)} banda(s) em {len(fids)} ponto(s); {fora} sem valor "
                      "(fora da extensão ou nodata)"}


# ------------------------------------------------------------------ 12. visibilidade
@ferramenta(
    nome="visibilidade", titulo="Visibilidade a partir de um ponto", categoria="raster", versao=1,
    descricao="Área visível de um observador sobre o modelo de elevação, pelo gdal_viewshed.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "modelo de elevação"),
        Parametro("ponto", "GPFeatureRecordSetLayer", "camada com o ponto do observador",
                  descricao="usa a primeira feição da camada"),
        Parametro("altura_observador", "GPDouble", "altura do observador", obrigatorio=False, padrao=2.0,
                  minimo=0),
        Parametro("altura_alvo", "GPDouble", "altura do alvo", obrigatorio=False, padrao=0.0, minimo=0),
        Parametro("raio", "GPDouble", "raio máximo", obrigatorio=False, padrao=0.0, minimo=0,
                  descricao="0 = sem limite de distância"),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 500,
    limites={},
)
def visibilidade(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    camada = entradas["ponto"]
    env = fonte_raster.ambiente(raster["origem"])
    with ctx.db() as cur:
        cur.execute(f'SELECT ST_X(p) AS x, ST_Y(p) AS y FROM (SELECT '
                    f'ST_PointOnSurface(ST_Transform(geom, {int(raster["epsg"])})) AS p '
                    f'FROM "{camada["schema"]}"."{camada["tabela"]}" WHERE geom IS NOT NULL '
                    f'ORDER BY fid LIMIT 1) s')
        r = cur.fetchone()
    if r is None:
        raise ErroExecucao(422, "camada_vazia", "a camada do observador não tem geometria")
    x, y = float(r["x"]), float(r["y"])
    x0, y0, x1, y1 = raster["limites"]
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        raise ErroExecucao(422, "observador_fora",
                           "o ponto do observador está fora da extensão do modelo de elevação",
                           {"ponto": [x, y], "extensao": raster["limites"]})
    bruto = ctx.dir_trabalho / "visibilidade.tif"
    ctx.progresso(30, "gdal_viewshed")
    comandos.visibilidade(ctx, raster["caminho"], bruto, env, x=x, y=y,
                          altura_observador=float(parametros.get("altura_observador") or 2.0),
                          altura_alvo=float(parametros.get("altura_alvo") or 0.0),
                          raio=float(parametros.get("raio") or 0.0))
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, categorico=True,
                         metodo=f"gdal_viewshed -ox {x} -oy {y} "
                                f"-oz {parametros.get('altura_observador') or 2.0}",
                         resumo={"observador": [x, y], "altura_observador": parametros.get("altura_observador"),
                                 "raio": parametros.get("raio")},
                         bandas=[{"nome": "visivel"}])


# ------------------------------------------------------------------ 13. distância euclidiana
@ferramenta(
    nome="distancia_euclidiana", titulo="Distância euclidiana", categoria="proximidade", versao=1,
    descricao="Distância de cada pixel ao pixel-alvo mais próximo, pelo gdal_proximity.",
    parametros=(
        Parametro("raster", "GPRasterDataLayer", "raster de entrada"),
        Parametro("banda", "GPLong", "banda", obrigatorio=False, padrao=1, minimo=1, maximo=64),
        Parametro("valores", "GPMultiValue", "valores-alvo", subtipo="GPLong", obrigatorio=False,
                  descricao="sem lista, o alvo é todo pixel diferente de zero e de nodata"),
        Parametro("unidade", "GPString", "unidade", obrigatorio=False, padrao="mapa",
                  opcoes=("mapa", "pixel")),
        Parametro("maxima", "GPDouble", "distância máxima", obrigatorio=False, minimo=0),
        Parametro("saida", "GPRasterDataLayer", "raster de saída", direcao="saida"),
    ),
    custo=lambda entradas, p: entradas["raster"]["largura"] * entradas["raster"]["altura"] // 400,
    limites={},
)
def distancia_euclidiana(ctx, entradas, parametros, destino) -> dict:
    raster = _raster(entradas, "raster")
    env = fonte_raster.ambiente(raster["origem"])
    _conferir_saida(raster["largura"], raster["altura"])
    bruto = ctx.dir_trabalho / "proximidade.tif"
    ctx.progresso(30, "gdal_proximity")
    comandos.proximidade(ctx, raster["caminho"], bruto, env, banda=int(parametros.get("banda") or 1),
                         valores=parametros.get("valores"), unidade=parametros.get("unidade") or "mapa",
                         maxima=parametros.get("maxima"))
    ctx.progresso(70, "escrevendo o COG do resultado")
    return _publicar_cog(ctx, bruto, env, metodo="gdal_proximity",
                         resumo={"valores": parametros.get("valores"),
                                 "unidade": parametros.get("unidade") or "mapa"},
                         bandas=[{"nome": "distancia"}])


__all__ = ["ESTATISTICAS_ZONAIS", "PRODUTOS_TERRENO", "amostrar_raster", "calculadora_raster",
           "curvas_de_nivel", "distancia_euclidiana", "estatisticas_zonais", "mosaico_raster",
           "rasterizar_camada", "reclassificar_raster", "recortar_raster", "reprojetar_raster",
           "terreno_raster", "vetorizar_raster", "visibilidade"]
