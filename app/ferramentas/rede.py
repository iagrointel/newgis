"""Ferramentas de rede (item L2-05-f): área de serviço (isócrona), rota por paradas, matriz origem-destino,
K instalações mais próximas, conexão à rede (snap) e localizar-alocar simplificado. Todas são ferramentas do
registro `@ferramenta` (L2-05-a): entram pelo mesmo catálogo, pelo mesmo `/api/ferramentas/<nome>/executar`,
pelo mesmo GPServer e publicam o resultado como camada com proveniência e `derivado_de`.

O cálculo NUNCA é refeito aqui: quem fala com o grafo é o serviço de rota do item L2-11-c (`app/rede/osrm.py`
e `app/rede/isocrona.py`), o mesmo que atende `/api/rota`, `/api/matriz` e `/api/isocrona`. Estas ferramentas
só leem pontos de uma camada, chamam aquele serviço e escrevem o resultado como camada. Por isso a isócrona
de um ponto sai idêntica à do serviço: é a mesma função.

Proveniência: além do bloco que o executor grava (ferramenta, versão, parâmetros, entradas com sha256), cada
ferramenta devolve em `metodo` a versão do grafo OSM usada — arquivo, sha256 e data de extração do .pbf, lidos
de `osrm/proveniencia.json` por `app.rede.osrm.PROVENIENCIA`.

Célula ou ponto sem rota é NULL, nunca 0: um ponto fora da rede (no mar, fora do recorte) devolve linha com
tempo e distância nulos, e a isócrona dele sai com geometria nula — nunca um polígono vazio nem tempo zero.
"""

from __future__ import annotations

import json

import psycopg2.extras

from app import limites
from app.erros import ErroAPI
from app.ferramentas.executor import ErroExecucao
from app.ferramentas.registro import Parametro, ferramenta
from app.rede import isocrona as isocrona_mod
from app.rede import osrm
from app.rede.instrucoes import resumir_rota

PERFIS = limites.ROTA_PERFIS


def _grafo() -> str:
    """Uma linha com a versão do grafo OSM: arquivo, data de extração e sha256 (procedência do resultado)."""
    p = osrm.PROVENIENCIA
    return f"grafo OSM {p.get('arquivo')} de {p.get('extraido_em')} (sha256 {str(p.get('sha256'))[:16]}…)"


def _erro(codigo: str, mensagem: str, detalhe=None) -> ErroExecucao:
    return ErroExecucao(422, codigo, mensagem, detalhe)


def _pontos(cur, camada: dict, teto: int, nome_parametro: str) -> list[dict]:
    """Pontos de uma camada de entrada, em 4326, na ordem de fid. Feição que não é ponto entra pelo centroide
    (declarado no `metodo`); feição sem geometria fica de fora."""
    if camada["feicoes"] > teto:
        raise _erro("rede_pontos_demais", f"{nome_parametro}: {camada['feicoes']} feições acima do teto {teto}",
                    {"campo": nome_parametro, "feicoes": camada["feicoes"], "teto": teto})
    cur.execute(
        f'SELECT fid, ST_X(p) AS lon, ST_Y(p) AS lat FROM (SELECT fid, '
        f'ST_Centroid(ST_Transform(geom, 4326)) AS p FROM "{camada["schema"]}"."{camada["tabela"]}" '
        f'WHERE geom IS NOT NULL ORDER BY fid) q'
    )
    pontos = [{"fid": int(r["fid"]), "lon": float(r["lon"]), "lat": float(r["lat"])} for r in cur.fetchall()]
    if not pontos:
        raise _erro("camada_sem_ponto", f"{nome_parametro}: nenhuma feição com geometria", {"campo": nome_parametro})
    return pontos


def _coords(pontos: list[dict]) -> list[list[float]]:
    return [[p["lon"], p["lat"]] for p in pontos]


def _criar(cur, destino: dict, colunas: str, tipo_geom: str) -> str:
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    cur.execute(f"CREATE TABLE {alvo} (fid bigserial PRIMARY KEY, {colunas}, "
                f"geom geometry({tipo_geom}, 4326))")
    return alvo


def _inserir(cur, alvo: str, colunas: list[str], gabarito_geom: str, linhas: list[tuple]) -> None:
    """Insere em lote; `gabarito_geom` é a expressão SQL da geometria (última posição de cada linha)."""
    if not linhas:
        return
    campos = ", ".join(colunas + ["geom"])
    marcadores = "(" + ", ".join(["%s"] * len(colunas)) + ", " + gabarito_geom + ")"
    psycopg2.extras.execute_values(cur, f"INSERT INTO {alvo}({campos}) VALUES %s", linhas, template=marcadores,
                                   page_size=500)


def _linha_reta(a: dict, b: dict) -> str:
    return json.dumps({"type": "LineString", "coordinates": [[a["lon"], a["lat"]], [b["lon"], b["lat"]]]})


def _campos(*nomes_tipos) -> list[dict]:
    return [{"nome": n, "tipo": t, "alias": a} for n, t, a in nomes_tipos]


# ---------------------------------------------------------------- área de serviço (isócrona)
@ferramenta(
    nome="area_de_servico", titulo="Área de serviço (isócrona)", categoria="rede", versao=1,
    descricao="Polígono alcançável a partir de cada ponto, por intervalo de tempo, sobre a rede viária.",
    parametros=(
        Parametro("pontos", "GPFeatureRecordSetLayer", "camada de origens",
                  descricao="pontos de partida (outra geometria entra pelo centroide)"),
        Parametro("minutos", "GPMultiValue", "intervalos de tempo (minutos)", subtipo="GPDouble",
                  padrao=[15.0], minimo=0.1, maximo=limites.ROTA_MINUTOS_MAX,
                  descricao="um polígono por intervalo, do menor para o maior"),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("combinar", "GPString", "saída", obrigatorio=False, padrao="por_origem",
                  opcoes=("por_origem", "dissolver"), descricao="um polígono por origem ou dissolvido por intervalo"),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["pontos"]["feicoes"] * max(len(p.get("minutos") or [1]), 1) * 50,
    limites={"isocronas_max": limites.REDE_ISOCRONAS_MAX, "intervalos_max": limites.REDE_INTERVALOS_MAX,
             "minutos_max": limites.ROTA_MINUTOS_MAX},
)
def area_de_servico(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["pontos"]
    perfil = parametros["perfil"]
    minutos = sorted({float(m) for m in parametros["minutos"]})
    if len(minutos) > limites.REDE_INTERVALOS_MAX:
        raise _erro("rede_intervalos_demais",
                    f"{len(minutos)} intervalos acima do teto {limites.REDE_INTERVALOS_MAX}", {"campo": "minutos"})
    dissolver = parametros["combinar"] == "dissolver"
    with ctx.db() as cur:
        pontos = _pontos(cur, camada, limites.REDE_ISOCRONAS_MAX, "pontos")
        if len(pontos) * len(minutos) > limites.REDE_ISOCRONAS_MAX:
            raise _erro("rede_isocronas_demais",
                        f"{len(pontos)} origens × {len(minutos)} intervalos acima do teto "
                        f"{limites.REDE_ISOCRONAS_MAX}", {"origens": len(pontos), "intervalos": len(minutos)})
        ctx.log("INFO", f"área de serviço: {len(pontos)} origens × {len(minutos)} intervalos, perfil {perfil}")
        calculadas = []
        for i, p in enumerate(pontos):
            for m in minutos:
                calculadas.append((p["fid"], m, _isocrona_de(ctx, [p["lon"], p["lat"]], m, perfil)))
            ctx.progresso(10 + int(60 * (i + 1) / len(pontos)), f"isócronas de {i + 1} de {len(pontos)} origens")
        colunas = ("minutos double precision, origens bigint, pontos_alcancaveis bigint, "
                   "resolucao_m double precision") if dissolver else (
                   "origem_fid bigint, minutos double precision, pontos_alcancaveis bigint, "
                   "resolucao_m double precision, raio_km double precision")
        alvo = _criar(cur, destino, colunas, "MultiPolygon")
        if dissolver:
            cur.execute("CREATE TEMP TABLE t_iso (minutos double precision, alcancaveis bigint, "
                        "resolucao_m double precision, geom geometry(MultiPolygon, 4326)) ON COMMIT DROP")
            linhas = [(m, r["grade"]["pontos_alcancaveis"], r["grade"]["resolucao_m"], json.dumps(r["poligono"]))
                      for _fid, m, r in calculadas if r["poligono"] is not None]
            _inserir(cur, "t_iso", ["minutos", "alcancaveis", "resolucao_m"],
                     "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))", linhas)
            cur.execute("INSERT INTO " + alvo + "(minutos, origens, pontos_alcancaveis, resolucao_m, geom) "
                        "SELECT minutos, count(*), sum(alcancaveis), max(resolucao_m), ST_Multi(ST_Union(geom)) "
                        "FROM t_iso GROUP BY minutos ORDER BY minutos")
            campos = _campos(("minutos", "double precision", "intervalo (min)"),
                             ("origens", "bigint", "origens dissolvidas"),
                             ("pontos_alcancaveis", "bigint", "pontos de grade alcançáveis"),
                             ("resolucao_m", "double precision", "resolução da grade (m)"))
        else:
            linhas = [(fid, m, r["grade"]["pontos_alcancaveis"], r["grade"]["resolucao_m"], r["grade"]["raio_km"],
                       json.dumps(r["poligono"]) if r["poligono"] is not None else None)
                      for fid, m, r in calculadas]
            _inserir(cur, alvo, ["origem_fid", "minutos", "pontos_alcancaveis", "resolucao_m", "raio_km"],
                     "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))", linhas)
            campos = _campos(("origem_fid", "bigint", "fid da origem"), ("minutos", "double precision",
                             "intervalo (min)"), ("pontos_alcancaveis", "bigint", "pontos de grade alcançáveis"),
                             ("resolucao_m", "double precision", "resolução da grade (m)"),
                             ("raio_km", "double precision", "raio amostrado (km)"))
    ctx.progresso(75, "isócronas escritas")
    return {"geometria": "MultiPolygon", "srid": 4326, "campos": campos,
            "metodo": f"serviço de rota do L2-11-c (matriz OSRM sobre grade + casco côncavo); {_grafo()}"}


def _isocrona_de(ctx, ponto: list[float], minutos: float, perfil: str) -> dict:
    """Chama a MESMA função de `/api/isocrona`. Ponto fora da rede não é erro da execução: vira polígono nulo."""
    try:
        return isocrona_mod.calcular(ponto, minutos, perfil, None)
    except ErroAPI as e:
        if e.status_code == 422:
            ctx.log("AVISO", f"ponto {ponto} sem rota no grafo ({e.erro}); isócrona nula")
            return {"poligono": None, "grade": {"pontos_alcancaveis": 0, "resolucao_m": None, "raio_km": None}}
        raise


# ---------------------------------------------------------------- rota por paradas
@ferramenta(
    nome="rota_paradas", titulo="Rota por paradas", categoria="rede", versao=1,
    descricao="Rota pela rede viária passando por todas as paradas, na ordem dada ou na ordem otimizada.",
    parametros=(
        Parametro("paradas", "GPFeatureRecordSetLayer", "camada de paradas",
                  descricao=f"de 2 a {limites.REDE_PARADAS_MAX} pontos, na ordem de fid"),
        Parametro("otimizar", "GPBoolean", "otimizar a ordem", obrigatorio=False, padrao=False,
                  descricao="ordem de visita pelo serviço /trip do OSRM (inserção do mais distante)"),
        Parametro("fechar_ciclo", "GPBoolean", "voltar ao início", obrigatorio=False, padrao=False),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["paradas"]["feicoes"] * 10,
    limites={"paradas_max": limites.REDE_PARADAS_MAX},
)
def rota_paradas(ctx, entradas, parametros, destino) -> dict:
    camada = entradas["paradas"]
    perfil = parametros["perfil"]
    otimizar = bool(parametros["otimizar"])
    ciclo = bool(parametros["fechar_ciclo"])
    with ctx.db() as cur:
        pontos = _pontos(cur, camada, limites.REDE_PARADAS_MAX, "paradas")
        if len(pontos) < 2:
            raise _erro("rede_paradas_de_menos", "a rota precisa de ao menos 2 paradas", {"campo": "paradas"})
        ctx.progresso(20, f"calculando a rota de {len(pontos)} paradas")
        rota, ordem = _rota_e_ordem(pontos, perfil, otimizar, ciclo)
        ctx.progresso(60, "rota calculada")
        alvo = _criar(cur, destino, "trecho bigint, de_fid bigint, para_fid bigint, distancia_m double precision, "
                                    "duracao_s double precision, instrucoes text", "LineString")
        linhas = []
        for i, perna in enumerate(rota["legs"]):
            passos = perna.get("steps") or []
            coordenadas = []
            for passo in passos:
                for c in (passo.get("geometry") or {}).get("coordinates") or []:
                    if not coordenadas or coordenadas[-1] != c:
                        coordenadas.append(c)
            if len(coordenadas) < 2:
                coordenadas = [[pontos[0]["lon"], pontos[0]["lat"]], [pontos[0]["lon"], pontos[0]["lat"]]]
            texto = "; ".join(p["texto"] for p in resumir_rota(passos))
            linhas.append((i + 1, ordem[i], ordem[i + 1], perna.get("distance"), perna.get("duration"), texto,
                           json.dumps({"type": "LineString", "coordinates": coordenadas})))
        _inserir(cur, alvo, ["trecho", "de_fid", "para_fid", "distancia_m", "duracao_s", "instrucoes"],
                 "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", linhas)
    ctx.log("INFO", f"rota de {len(pontos)} paradas: {rota.get('distance')} m, {rota.get('duration')} s"
                    + (" (ordem otimizada)" if otimizar else " (ordem original)"))
    ctx.progresso(75, "trechos escritos")
    metodo = ("serviço /trip do OSRM (inserção do mais distante)" if otimizar
              else "serviço /route do OSRM na ordem de fid")
    return {"geometria": "LineString", "srid": 4326,
            "campos": _campos(("trecho", "bigint", "nº do trecho"), ("de_fid", "bigint", "parada de origem"),
                              ("para_fid", "bigint", "parada de destino"),
                              ("distancia_m", "double precision", "distância (m)"),
                              ("duracao_s", "double precision", "tempo (s)"),
                              ("instrucoes", "text", "instruções do trecho")),
            "metodo": f"{metodo}; {_grafo()}"}


def _rota_e_ordem(pontos: list[dict], perfil: str, otimizar: bool, ciclo: bool) -> tuple[dict, list[int]]:
    """Devolve (rota do OSRM, lista de fid na ordem de visita — com o primeiro repetido no fim se for ciclo)."""
    coords = _coords(pontos)
    if otimizar:
        resposta = osrm.viagem(coords, perfil, ciclo)
        viagem = resposta["trips"][0]
        posicao = {}
        for i, w in enumerate(resposta.get("waypoints") or []):
            posicao[int(w["waypoint_index"])] = pontos[i]["fid"]
        ordem = [posicao[k] for k in sorted(posicao)]
        if ciclo:
            ordem = ordem + [ordem[0]]
        return viagem, ordem
    ordem = [p["fid"] for p in pontos]
    if ciclo:
        coords = coords + [coords[0]]
        ordem = ordem + [ordem[0]]
    return osrm.rota_por_pontos(coords, perfil)["routes"][0], ordem


def custo_da_rota(pontos: list[dict], perfil: str, otimizar: bool, ciclo: bool = False) -> dict:
    """Tempo e distância totais de uma ordem (usado pelo teste que compara ordem original × otimizada)."""
    rota, ordem = _rota_e_ordem(pontos, perfil, otimizar, ciclo)
    return {"duracao_s": rota.get("duration"), "distancia_m": rota.get("distance"), "ordem": ordem}


# ---------------------------------------------------------------- matriz origem-destino
def _matriz(ctx, origens: list[dict], destinos: list[dict], perfil: str) -> dict:
    total = len(origens) * len(destinos)
    if len(origens) > limites.REDE_MATRIZ_LADO_MAX or len(destinos) > limites.REDE_MATRIZ_LADO_MAX:
        raise _erro("rede_matriz_lado", f"cada lado da matriz vai até {limites.REDE_MATRIZ_LADO_MAX} pontos")
    if total > limites.REDE_MATRIZ_PARES_MAX:
        raise _erro("rede_matriz_grande", f"{len(origens)}×{len(destinos)} acima do teto declarado "
                                          f"{limites.REDE_MATRIZ_PARES_MAX}")
    ctx.log("INFO", f"matriz {len(origens)}×{len(destinos)} pelo serviço de rota (blocos do teto do OSRM)")
    return osrm.matriz_grande(_coords(origens), _coords(destinos), perfil)


@ferramenta(
    nome="matriz_od", titulo="Matriz origem-destino", categoria="rede", versao=1,
    descricao="Tempo e distância pela rede entre cada origem e cada destino; um par por feição de saída.",
    parametros=(
        Parametro("origens", "GPFeatureRecordSetLayer", "camada de origens"),
        Parametro("destinos", "GPFeatureRecordSetLayer", "camada de destinos"),
        Parametro("apenas_com_rota", "GPBoolean", "só pares com rota", obrigatorio=False, padrao=False),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["origens"]["feicoes"] * e["destinos"]["feicoes"],
    limites={"lado_max": limites.REDE_MATRIZ_LADO_MAX, "pares_max": limites.REDE_MATRIZ_PARES_MAX},
)
def matriz_od(ctx, entradas, parametros, destino) -> dict:
    perfil = parametros["perfil"]
    so_com_rota = bool(parametros["apenas_com_rota"])
    with ctx.db() as cur:
        origens = _pontos(cur, entradas["origens"], limites.REDE_MATRIZ_LADO_MAX, "origens")
        destinos = _pontos(cur, entradas["destinos"], limites.REDE_MATRIZ_LADO_MAX, "destinos")
        ctx.progresso(20, f"matriz {len(origens)}×{len(destinos)}")
        m = _matriz(ctx, origens, destinos, perfil)
        ctx.progresso(60, "matriz calculada")
        alvo = _criar(cur, destino, "origem_fid bigint, destino_fid bigint, duracao_s double precision, "
                                    "distancia_m double precision", "LineString")
        linhas = []
        for i, o in enumerate(origens):
            for j, d in enumerate(destinos):
                dur, dist = m["durations"][i][j], m["distances"][i][j]
                if dur is None and so_com_rota:
                    continue
                linhas.append((o["fid"], d["fid"], dur, dist, _linha_reta(o, d)))
        _inserir(cur, alvo, ["origem_fid", "destino_fid", "duracao_s", "distancia_m"],
                 "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", linhas)
    ctx.progresso(75, f"{len(linhas)} pares escritos")
    return {"geometria": "LineString", "srid": 4326,
            "campos": _campos(("origem_fid", "bigint", "fid da origem"), ("destino_fid", "bigint", "fid do destino"),
                              ("duracao_s", "double precision", "tempo (s); nulo se não há rota"),
                              ("distancia_m", "double precision", "distância (m); nula se não há rota")),
            "metodo": f"serviço /table do OSRM em {m['chamadas']} bloco(s) (linha reta origem→destino como "
                      f"geometria); {_grafo()}"}


# ---------------------------------------------------------------- K instalações mais próximas
@ferramenta(
    nome="mais_proximas", titulo="Instalações mais próximas", categoria="rede", versao=1,
    descricao="Para cada origem, as K instalações mais próximas por tempo de viagem pela rede.",
    parametros=(
        Parametro("origens", "GPFeatureRecordSetLayer", "camada de origens"),
        Parametro("instalacoes", "GPFeatureRecordSetLayer", "camada de instalações"),
        Parametro("quantidade", "GPLong", "quantas mais próximas", obrigatorio=False, padrao=1, minimo=1,
                  maximo=limites.REDE_K_MAX),
        Parametro("tempo_max_min", "GPDouble", "tempo máximo (min)", obrigatorio=False, minimo=0.1,
                  maximo=limites.ROTA_MINUTOS_MAX, descricao="corta as que estão além deste tempo"),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["origens"]["feicoes"] * e["instalacoes"]["feicoes"],
    limites={"k_max": limites.REDE_K_MAX, "lado_max": limites.REDE_MATRIZ_LADO_MAX},
)
def mais_proximas(ctx, entradas, parametros, destino) -> dict:
    perfil = parametros["perfil"]
    k = int(parametros["quantidade"])
    teto_s = float(parametros["tempo_max_min"]) * 60.0 if parametros["tempo_max_min"] is not None else None
    with ctx.db() as cur:
        origens = _pontos(cur, entradas["origens"], limites.REDE_MATRIZ_LADO_MAX, "origens")
        instalacoes = _pontos(cur, entradas["instalacoes"], limites.REDE_MATRIZ_LADO_MAX, "instalacoes")
        ctx.progresso(20, f"{len(origens)} origens × {len(instalacoes)} instalações")
        m = _matriz(ctx, origens, instalacoes, perfil)
        ctx.progresso(60, "matriz calculada")
        alvo = _criar(cur, destino, "origem_fid bigint, instalacao_fid bigint, posicao bigint, "
                                    "duracao_s double precision, distancia_m double precision", "LineString")
        linhas = []
        for i, o in enumerate(origens):
            candidatas = [(m["durations"][i][j], m["distances"][i][j], j)
                          for j in range(len(instalacoes)) if m["durations"][i][j] is not None
                          and (teto_s is None or m["durations"][i][j] <= teto_s)]
            candidatas.sort(key=lambda c: (c[0], c[2]))
            for posicao, (dur, dist, j) in enumerate(candidatas[:k], start=1):
                linhas.append((o["fid"], instalacoes[j]["fid"], posicao, dur, dist, _linha_reta(o, instalacoes[j])))
        _inserir(cur, alvo, ["origem_fid", "instalacao_fid", "posicao", "duracao_s", "distancia_m"],
                 "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", linhas)
    ctx.progresso(75, f"{len(linhas)} pares escritos")
    return {"geometria": "LineString", "srid": 4326,
            "campos": _campos(("origem_fid", "bigint", "fid da origem"),
                              ("instalacao_fid", "bigint", "fid da instalação"),
                              ("posicao", "bigint", "1 = mais próxima"),
                              ("duracao_s", "double precision", "tempo (s)"),
                              ("distancia_m", "double precision", "distância (m)")),
            "metodo": f"mesma matriz /table do serviço de rota, ordenada por tempo (K={k}"
                      + (f", teto {parametros['tempo_max_min']} min" if teto_s else "") + f"); {_grafo()}"}


# ---------------------------------------------------------------- conectar à rede (snap)
@ferramenta(
    nome="conectar_a_rede", titulo="Conectar pontos à rede", categoria="rede", versao=1,
    descricao="Move cada ponto para o ponto mais próximo da rede viária e registra o deslocamento.",
    parametros=(
        Parametro("pontos", "GPFeatureRecordSetLayer", "camada de pontos"),
        Parametro("distancia_max", "GPLinearUnit", "deslocamento máximo", obrigatorio=False, minimo=0,
                  maximo=limites.BUFFER_DISTANCIA_M_MAX,
                  descricao="ponto que exigiria mais que isto sai com geometria nula"),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["pontos"]["feicoes"] * 2,
    limites={"pontos_max": limites.REDE_SNAP_PONTOS_MAX},
)
def conectar_a_rede(ctx, entradas, parametros, destino) -> dict:
    perfil = parametros["perfil"]
    teto_m = parametros["distancia_max"]["metros"] if parametros["distancia_max"] else None
    with ctx.db() as cur:
        pontos = _pontos(cur, entradas["pontos"], limites.REDE_SNAP_PONTOS_MAX, "pontos")
        alvo = _criar(cur, destino, "origem_fid bigint, distancia_m double precision, via text", "Point")
        linhas = []
        for i, p in enumerate(pontos):
            fixado = _mais_proximo(ctx, [p["lon"], p["lat"]], perfil)
            if fixado is None or (teto_m is not None and fixado["distancia_m"] > teto_m):
                linhas.append((p["fid"], fixado["distancia_m"] if fixado else None,
                               fixado["via"] if fixado else None, None))
            else:
                linhas.append((p["fid"], fixado["distancia_m"], fixado["via"],
                               json.dumps({"type": "Point", "coordinates": fixado["ponto"]})))
            if (i + 1) % 25 == 0:
                ctx.progresso(10 + int(60 * (i + 1) / len(pontos)), f"{i + 1} de {len(pontos)} pontos")
        _inserir(cur, alvo, ["origem_fid", "distancia_m", "via"],
                 "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", linhas)
    ctx.progresso(75, "pontos conectados")
    return {"geometria": "Point", "srid": 4326,
            "campos": _campos(("origem_fid", "bigint", "fid de origem"),
                              ("distancia_m", "double precision", "deslocamento até a rede (m)"),
                              ("via", "text", "nome da via")),
            "metodo": f"serviço /nearest do OSRM (1 candidato por ponto); {_grafo()}"}


def _mais_proximo(ctx, ponto: list[float], perfil: str) -> dict | None:
    try:
        resposta = osrm.mais_proximo(ponto, perfil)
    except ErroAPI as e:
        if e.status_code == 422:
            ctx.log("AVISO", f"ponto {ponto} sem segmento de rede próximo ({e.erro})")
            return None
        raise
    candidatos = resposta.get("waypoints") or []
    if not candidatos:
        return None
    w = candidatos[0]
    return {"ponto": w["location"], "distancia_m": float(w.get("distance") or 0.0),
            "via": (w.get("name") or "").strip() or None}


# ---------------------------------------------------------------- localizar-alocar (cobertura máxima)
@ferramenta(
    nome="localizar_alocar", titulo="Localizar-alocar (cobertura máxima)", categoria="rede", versao=1,
    descricao="Escolhe P instalações entre as candidatas para cobrir o maior número de pontos de demanda "
              "dentro de um tempo de viagem, por heurística gulosa declarada.",
    parametros=(
        Parametro("candidatas", "GPFeatureRecordSetLayer", "camada de instalações candidatas"),
        Parametro("demanda", "GPFeatureRecordSetLayer", "camada de pontos de demanda"),
        Parametro("instalacoes_p", "GPLong", "quantas escolher", obrigatorio=False, padrao=1, minimo=1,
                  maximo=limites.REDE_ALOCAR_P_MAX),
        Parametro("tempo_max_min", "GPDouble", "tempo de cobertura (min)", obrigatorio=False, padrao=15.0,
                  minimo=0.1, maximo=limites.ROTA_MINUTOS_MAX),
        Parametro("perfil", "GPString", "modo de viagem", obrigatorio=False, padrao="carro", opcoes=PERFIS),
        Parametro("saida", "GPFeatureRecordSetLayer", "camada de saída", direcao="saida"),
    ),
    custo=lambda e, p: e["candidatas"]["feicoes"] * e["demanda"]["feicoes"],
    limites={"p_max": limites.REDE_ALOCAR_P_MAX, "lado_max": limites.REDE_MATRIZ_LADO_MAX},
)
def localizar_alocar(ctx, entradas, parametros, destino) -> dict:
    perfil = parametros["perfil"]
    p_alvo = int(parametros["instalacoes_p"])
    teto_s = float(parametros["tempo_max_min"]) * 60.0
    with ctx.db() as cur:
        candidatas = _pontos(cur, entradas["candidatas"], limites.REDE_MATRIZ_LADO_MAX, "candidatas")
        demanda = _pontos(cur, entradas["demanda"], limites.REDE_MATRIZ_LADO_MAX, "demanda")
        ctx.progresso(20, f"{len(candidatas)} candidatas × {len(demanda)} pontos de demanda")
        m = _matriz(ctx, candidatas, demanda, perfil)
        ctx.progresso(60, "matriz calculada")
        cobertura = [{j for j in range(len(demanda))
                      if m["durations"][i][j] is not None and m["durations"][i][j] <= teto_s}
                     for i in range(len(candidatas))]
        escolhidas, cobertos = [], set()
        for _ in range(min(p_alvo, len(candidatas))):
            melhor, ganho_melhor = None, 0
            for i in range(len(candidatas)):
                if i in [e[0] for e in escolhidas]:
                    continue
                ganho = len(cobertura[i] - cobertos)
                if ganho > ganho_melhor or (melhor is None and ganho > 0):
                    melhor, ganho_melhor = i, ganho
            if melhor is None or ganho_melhor == 0:
                break  # nenhuma candidata restante acrescenta cobertura: parar é honesto, repetir seria enfeite
            cobertos |= cobertura[melhor]
            escolhidas.append((melhor, ganho_melhor, len(cobertos)))
        alvo = _criar(cur, destino, "ordem bigint, candidata_fid bigint, demanda_coberta bigint, "
                                    "demanda_acumulada bigint, tempo_max_min double precision", "Point")
        linhas = [(ordem, candidatas[i]["fid"], ganho, acumulado, parametros["tempo_max_min"],
                   json.dumps({"type": "Point", "coordinates": [candidatas[i]["lon"], candidatas[i]["lat"]]}))
                  for ordem, (i, ganho, acumulado) in enumerate(escolhidas, start=1)]
        _inserir(cur, alvo, ["ordem", "candidata_fid", "demanda_coberta", "demanda_acumulada", "tempo_max_min"],
                 "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", linhas)
    ctx.log("INFO", f"localizar-alocar: {len(escolhidas)} de {p_alvo} instalações cobrem {len(cobertos)} de "
                    f"{len(demanda)} pontos de demanda em até {parametros['tempo_max_min']} min")
    ctx.progresso(75, "instalações escolhidas")
    return {"geometria": "Point", "srid": 4326,
            "campos": _campos(("ordem", "bigint", "ordem de escolha"), ("candidata_fid", "bigint", "fid da candidata"),
                              ("demanda_coberta", "bigint", "pontos que esta instalação acrescenta"),
                              ("demanda_acumulada", "bigint", "pontos cobertos até aqui"),
                              ("tempo_max_min", "double precision", "tempo de cobertura (min)")),
            "metodo": f"cobertura máxima por heurística gulosa (escolhe a candidata de maior ganho a cada passo; "
                      f"não é ótimo garantido) sobre a matriz /table; {_grafo()}"}
