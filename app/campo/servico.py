"""Núcleo do módulo campo (item L2-07-campo): fila de trabalho, roteiro do dia (ordem de visita + trajeto) e
visita com foto — portado de rs-coop/certaja/sig (`app/main.py` seções `filas`/`rotas`/`visitas`).

Mudança de desenho pela casa (multi-inquilino, ver cabeçalho da migração 20260910T2245_campo.sql): o ALVO não
é mais uma tabela própria com atributos do domínio elétrico — é a referência (camada_id, globalid) para uma
feição de uma camada vetorial HOSPEDADA do catálogo do inquilino. Toda leitura de geometria/atributo do alvo
passa por aqui, nunca por SQL solto nas rotas."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app import limites
from app.catalogo import comum
from app.erros import ErroAPI

_RE_SCHEMA = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
_RE_TABELA = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def camada_ou_404(cur, camada_id: str) -> tuple[dict, dict]:
    """Item de camada vetorial hospedada (única com tabela física própria a que o módulo campo pode ler
    feição por feição). A RLS de `plat.item` já isola por inquilino (404, nunca 403, para outro inquilino)."""
    r = comum.item_ou_404(cur, camada_id)
    if r["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    dados = r["dados"] or {}
    if dados.get("fonte") != "hospedada":
        raise ErroAPI(409, "camada_nao_suportada", "só camada vetorial hospedada pode virar fila de campo")
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not (isinstance(schema, str) and _RE_SCHEMA.match(schema) and isinstance(tabela, str)
            and _RE_TABELA.match(tabela)):
        raise ErroAPI(409, "camada_configuracao_invalida", "metadado de schema/tabela da camada inconsistente")
    return r, dados


def _tabela_sql(dados: dict) -> str:
    return f'"{dados["schema"]}"."{dados["tabela"]}"'


def feicao_ponto(cur, dados: dict, globalid: str) -> dict | None:
    """{globalid, lon, lat, titulo} — o centróide da feição em 4326 (o alvo pode ser ponto/linha/polígono; o
    roteiro sempre trabalha com um ponto de referência) e um rótulo curto para a tela (primeiro campo texto
    declarado da camada, ou o próprio globalid). `None` se a feição não existe mais na camada de origem."""
    if dados.get("geometria") in (None, "nenhuma"):
        raise ErroAPI(409, "camada_sem_geometria", "esta camada não tem geometria; não pode virar fila de campo")
    campos_texto = [
        c.get("nome") for c in (dados.get("campos") or [])
        if isinstance(c, dict) and c.get("nome") and c.get("tipo") in (None, "text")
    ]
    rotulo_campo = campos_texto[0] if campos_texto else None
    extra_sql = f', "{rotulo_campo}"::text AS __rotulo' if rotulo_campo else ""
    cur.execute(
        f"SELECT globalid, ST_X(ST_Centroid(ST_Transform(geom, 4326))) AS lon, "
        f"ST_Y(ST_Centroid(ST_Transform(geom, 4326))) AS lat{extra_sql} "
        f"FROM {_tabela_sql(dados)} WHERE globalid = %s",
        (globalid,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return {
        "globalid": str(r["globalid"]),
        "lon": r["lon"],
        "lat": r["lat"],
        "titulo": r.get("__rotulo") if rotulo_campo else None,
    }


def listar_globalids(cur, dados: dict, limite: int) -> list[dict]:
    """`[{globalid, titulo}]` das primeiras `limite` feições da camada — usado pela tela de criação de fila
    (escolher quais feições viram alvo) sem exigir um visualizador de mapa completo para isso."""
    campos_texto = [
        c.get("nome") for c in (dados.get("campos") or [])
        if isinstance(c, dict) and c.get("nome") and c.get("tipo") in (None, "text")
    ]
    rotulo_campo = campos_texto[0] if campos_texto else None
    extra_sql = f', "{rotulo_campo}"::text AS __rotulo' if rotulo_campo else ""
    cur.execute(f"SELECT globalid{extra_sql} FROM {_tabela_sql(dados)} ORDER BY fid LIMIT %s", (limite,))
    return [
        {"globalid": str(r["globalid"]), "titulo": (r.get("__rotulo") if rotulo_campo else None)}
        for r in cur.fetchall()
    ]


def feicoes_geojson(cur, dados: dict, globalids: list[str]) -> dict:
    """FeatureCollection com geometria+atributos das feições pedidas (mesma origem de dado de `feicao_ponto`,
    mas a geometria ORIGINAL, não o centróide) — usado pela camada de alvos no mapa."""
    if not globalids:
        return {"type": "FeatureCollection", "features": []}
    cur.execute(
        f"SELECT globalid, ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometria "
        f"FROM {_tabela_sql(dados)} WHERE globalid = ANY(%s::uuid[])",
        (globalids,),
    )
    feats = []
    for r in cur.fetchall():
        if r["geometria"] is None:
            continue
        feats.append({
            "type": "Feature", "id": str(r["globalid"]),
            "properties": {"globalid": str(r["globalid"])},
            "geometry": r["geometria"],
        })
    return {"type": "FeatureCollection", "features": feats}


# ---------------------------------------------------------------------- fila
def fila_criar(cur, auth, titulo: str, camada_id: str, globalids: list[str]) -> dict:
    item, dados = camada_ou_404(cur, camada_id)
    cur.execute(
        "INSERT INTO plat.campo_fila(tenant_id, titulo, camada_id, dono_id, criado_por) "
        "VALUES (%s, %s, %s::uuid, %s, %s) RETURNING id, titulo, camada_id, status, criado_em",
        (auth.tenant_id, " ".join(titulo.split()), camada_id, auth.usuario_id, auth.usuario_id),
    )
    fila = cur.fetchone()
    if globalids:
        adicionados, ignorados = fila_alvos_adicionar(cur, auth, str(fila["id"]), dados, globalids)
    else:
        adicionados, ignorados = 0, []
    return {
        "id": str(fila["id"]), "titulo": fila["titulo"], "camada_id": str(fila["camada_id"]),
        "status": fila["status"], "adicionados": adicionados, "ignorados": ignorados,
    }


def fila_ou_404(cur, fila_id: str) -> dict:
    cur.execute(
        "SELECT id, titulo, camada_id, status, dono_id, criado_em, atualizado_em FROM plat.campo_fila "
        "WHERE id = %s::uuid",
        (fila_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "fila_inexistente", "fila de trabalho inexistente")
    return r


def fila_alvos_adicionar(cur, auth, fila_id: str, dados_camada: dict, globalids: list[str]) -> tuple[int, list[str]]:
    """Acrescenta feições à fila NA ORDEM em que vieram (ordem = máximo atual + posição); ignora quem já
    está na fila (idempotente, ON CONFLICT DO NOTHING) e quem não existe mais na camada de origem."""
    cur.execute("SELECT coalesce(max(ordem), 0) AS o FROM plat.campo_alvo WHERE fila_id = %s::uuid", (fila_id,))
    ordem = cur.fetchone()["o"]
    adicionados = 0
    ignorados: list[str] = []
    vistos: set[str] = set()
    for gid in globalids:
        if gid in vistos:
            continue
        vistos.add(gid)
        feicao = feicao_ponto(cur, dados_camada, gid)
        if feicao is None:
            ignorados.append(gid)
            continue
        ordem += 1
        cur.execute(
            "INSERT INTO plat.campo_alvo(tenant_id, fila_id, globalid, ordem) VALUES (%s, %s::uuid, %s::uuid, %s) "
            "ON CONFLICT (fila_id, globalid) DO NOTHING",
            (auth.tenant_id, fila_id, gid, ordem),
        )
        adicionados += cur.rowcount
    cur.execute("UPDATE plat.campo_fila SET atualizado_em = now() WHERE id = %s::uuid", (fila_id,))
    return adicionados, ignorados


def fila_alvos_listar(cur, fila_id: str) -> list[dict]:
    cur.execute(
        "SELECT id, globalid, ordem, nota, status, criado_em FROM plat.campo_alvo "
        "WHERE fila_id = %s::uuid ORDER BY ordem",
        (fila_id,),
    )
    return cur.fetchall()


def fila_ordem_atualizar(cur, fila_id: str, alvo_ids: list[str]) -> int:
    n = 0
    for i, aid in enumerate(alvo_ids, 1):
        cur.execute(
            "UPDATE plat.campo_alvo SET ordem = %s WHERE id = %s::uuid AND fila_id = %s::uuid",
            (i, aid, fila_id),
        )
        n += cur.rowcount
    cur.execute("UPDATE plat.campo_fila SET atualizado_em = now() WHERE id = %s::uuid", (fila_id,))
    return n


def filas_listar(cur) -> list[dict]:
    cur.execute(
        "SELECT f.id, f.titulo, f.camada_id, f.status, f.criado_em, f.atualizado_em, "
        "(SELECT count(*) FROM plat.campo_alvo a WHERE a.fila_id = f.id) AS n_alvos, "
        "(SELECT count(*) FROM plat.campo_alvo a WHERE a.fila_id = f.id AND a.status <> 'pendente') AS n_visitados, "
        "(SELECT count(*) FROM plat.campo_roteiro r WHERE r.fila_id = f.id) AS n_roteiros "
        "FROM plat.campo_fila f ORDER BY f.criado_em DESC"
    )
    return cur.fetchall()


# ---------------------------------------------------------------------- roteiro (ordem de visita + trajeto)
def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _ordem_vizinho_2opt(pontos: list[tuple[float, float]]) -> list[int]:
    """Vizinho mais próximo + 2-opt (caminho aberto, origem fixa em pontos[0], fim livre) sobre distância em
    linha reta — mesmo algoritmo do sistema de origem (`_ordem_matriz`/`_ordem_reta`), sem motor de roteamento
    de verdade por trás (nenhum OSRM está ligado nesta instalação; ver docstring de `calcular`)."""
    n = len(pontos)
    if n <= 2:
        return list(range(1, n))
    d = [[_haversine_km(a, b) for b in pontos] for a in pontos]
    resto = set(range(1, n))
    ordem = [0]
    while resto:
        u = ordem[-1]
        v = min(resto, key=lambda j: d[u][j])
        ordem.append(v)
        resto.discard(v)

    def custo(o: list[int]) -> float:
        return sum(d[o[k]][o[k + 1]] for k in range(len(o) - 1))

    melhor = custo(ordem)
    melhorou = True
    while melhorou:
        melhorou = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = ordem[:i] + ordem[i:j + 1][::-1] + ordem[j + 1:]
                c = custo(cand)
                if c + 1e-9 < melhor:
                    ordem, melhor, melhorou = cand, c, True
    return ordem[1:]


def calcular_roteiro(origem: tuple[float, float], alvos: list[dict]) -> dict:
    """{km, minutos, geom (GeoJSON LineString), paradas: [{alvo, leg_km, leg_min}], motor, aviso}.

    Sem motor de roteamento por estrada ligado nesta instalação (o sistema de origem tenta OSRM primeiro e cai
    para linha reta quando ele falta — aqui nenhum OSRM está configurado para o inquilino da plataforma, então
    o caminho é sempre o de FALLBACK, com o mesmo aviso honesto que o original mostra quando o OSRM falha:
    tempo estimado a `limites.CAMPO_ROTA_VELOCIDADE_KMH`, nunca medido)."""
    pontos = [origem] + [(a["lon"], a["lat"]) for a in alvos]
    ordem = _ordem_vizinho_2opt(pontos)
    coords = [list(pontos[0])]
    paradas = []
    km_total = 0.0
    anterior = pontos[0]
    for i in ordem:
        d = _haversine_km(anterior, pontos[i])
        km_total += d
        anterior = pontos[i]
        coords.append(list(pontos[i]))
        paradas.append({"alvo": alvos[i - 1], "leg_km": d, "leg_min": d / limites.CAMPO_ROTA_VELOCIDADE_KMH * 60})
    return {
        "km": km_total, "minutos": km_total / limites.CAMPO_ROTA_VELOCIDADE_KMH * 60,
        "geom": {"type": "LineString", "coordinates": coords}, "paradas": paradas, "motor": "linha_reta",
        "aviso": (
            "sem motor de roteamento por estrada configurado nesta instalação; ordem por vizinho mais "
            f"próximo + 2-opt sobre linha reta, tempo estimado a {limites.CAMPO_ROTA_VELOCIDADE_KMH} km/h"
        ),
    }


def roteiro_criar(cur, auth, fila_id: str, origem: dict, titulo: str | None, alvo_ids: list[str],
                  maximo: int) -> dict:
    fila = fila_ou_404(cur, fila_id)
    if not alvo_ids:
        cur.execute(
            "SELECT id FROM plat.campo_alvo WHERE fila_id = %s::uuid AND status = 'pendente' "
            "ORDER BY ordem LIMIT %s",
            (fila_id, maximo),
        )
        alvo_ids = [str(r["id"]) for r in cur.fetchall()]
    if not alvo_ids:
        raise ErroAPI(422, "sem_alvo_pendente", "nenhum alvo pendente nesta fila para rotear")
    if len(alvo_ids) > limites.CAMPO_ROTEIRO_PARADAS_MAX:
        raise ErroAPI(422, "roteiro_grande", f"no máximo {limites.CAMPO_ROTEIRO_PARADAS_MAX} paradas por roteiro")
    _item, dados_camada = camada_ou_404(cur, str(fila["camada_id"]))
    cur.execute(
        "SELECT id, globalid FROM plat.campo_alvo WHERE id = ANY(%s::uuid[]) AND fila_id = %s::uuid",
        (alvo_ids, fila_id),
    )
    linhas = {str(r["id"]): r["globalid"] for r in cur.fetchall()}
    alvos_ordenados = [aid for aid in alvo_ids if aid in linhas]
    if not alvos_ordenados:
        raise ErroAPI(404, "alvo_inexistente", "nenhum dos alvos pedidos pertence a esta fila")
    alvos: list[dict] = []
    for aid in alvos_ordenados:
        f = feicao_ponto(cur, dados_camada, str(linhas[aid]))
        if f is not None:
            f["alvo_id"] = aid
            alvos.append(f)
    if not alvos:
        raise ErroAPI(409, "alvos_sem_geometria", "os alvos pedidos não têm mais feição correspondente na camada")
    origem_xy = (origem["lon"], origem["lat"])
    r = calcular_roteiro(origem_xy, alvos)
    nome = titulo or f"roteiro · {len(r['paradas'])} paradas"
    cur.execute(
        "INSERT INTO plat.campo_roteiro(tenant_id, fila_id, titulo, origem_lon, origem_lat, motor, "
        "distancia_m, duracao_s, geom, aviso, dono_id) VALUES "
        "(%s, %s::uuid, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s) "
        "RETURNING id, criado_em",
        (auth.tenant_id, fila_id, nome, origem_xy[0], origem_xy[1], r["motor"], r["km"] * 1000,
         r["minutos"] * 60, json.dumps(r["geom"]), r["aviso"], auth.usuario_id),
    )
    roteiro = cur.fetchone()
    roteiro_id = str(roteiro["id"])
    for k, p in enumerate(r["paradas"], 1):
        cur.execute(
            "INSERT INTO plat.campo_roteiro_parada(tenant_id, roteiro_id, alvo_id, ordem, trecho_m, trecho_s) "
            "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s)",
            (auth.tenant_id, roteiro_id, p["alvo"]["alvo_id"], k, p["leg_km"] * 1000, p["leg_min"] * 60),
        )
    return {
        "id": roteiro_id, "titulo": nome, "fila_id": fila_id, "motor": r["motor"], "distancia_m": r["km"] * 1000,
        "duracao_s": r["minutos"] * 60, "n_paradas": len(r["paradas"]), "aviso": r["aviso"],
        "criado_em": roteiro["criado_em"],
    }


def roteiro_ou_404(cur, roteiro_id: str) -> dict:
    cur.execute(
        "SELECT id, fila_id, titulo, origem_lon, origem_lat, motor, distancia_m, duracao_s, "
        "ST_AsGeoJSON(geom)::json AS geometria, aviso, criado_em FROM plat.campo_roteiro WHERE id = %s::uuid",
        (roteiro_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "roteiro_inexistente", "roteiro inexistente")
    return r


def roteiro_paradas(cur, roteiro_id: str) -> list[dict]:
    cur.execute(
        "SELECT p.ordem, p.trecho_m, p.trecho_s, p.alvo_id, a.globalid, a.status, a.nota, "
        "(SELECT v.id FROM plat.campo_visita v WHERE v.alvo_id = a.id ORDER BY v.recebido_em DESC LIMIT 1) "
        "AS visita_id "
        "FROM plat.campo_roteiro_parada p JOIN plat.campo_alvo a ON a.id = p.alvo_id "
        "WHERE p.roteiro_id = %s::uuid ORDER BY p.ordem",
        (roteiro_id,),
    )
    return cur.fetchall()


def roteiros_listar(cur, fila_id: str | None) -> list[dict]:
    where = "WHERE r.fila_id = %s::uuid" if fila_id else ""
    args = (fila_id,) if fila_id else ()
    cur.execute(
        f"SELECT r.id, r.fila_id, r.titulo, r.motor, r.distancia_m, r.duracao_s, r.criado_em, "
        f"(SELECT count(*) FROM plat.campo_roteiro_parada p WHERE p.roteiro_id = r.id) AS n_paradas "
        f"FROM plat.campo_roteiro r {where} ORDER BY r.criado_em DESC",
        args,
    )
    return cur.fetchall()


# ---------------------------------------------------------------------- visita
def visita_criar(cur, auth, corpo) -> tuple[dict, bool]:
    """(visita, criada_agora). `criada_agora=False` quando `cliente_uuid` já existia (sincronizar duas vezes
    devolve a MESMA visita, nunca cria uma segunda — refutação do item). `INSERT ... ON CONFLICT DO NOTHING`
    em vez de SELECT-depois-INSERT: os dois lados de uma corrida (duas sincronizações do mesmo `cliente_uuid`
    quase ao mesmo tempo) terminam a transação sem erro, nunca com `UniqueViolation` a abortar a transação da
    rota (que também grava a foto e o evento na mesma chamada, ver `rotas.py`)."""
    cur.execute(
        "INSERT INTO plat.campo_visita(tenant_id, cliente_uuid, fila_id, alvo_id, roteiro_id, camada_id, "
        "globalid, status, texto, usuario_id, lat, lon, gps_acc_m, capturado_em, dados) VALUES "
        "(%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, cliente_uuid) DO NOTHING RETURNING id",
        (auth.tenant_id, corpo.cliente_uuid, corpo.fila_id, corpo.alvo_id, corpo.roteiro_id, corpo.camada_id,
         corpo.globalid, corpo.status, corpo.texto, auth.usuario_id, corpo.lat, corpo.lon, corpo.gps_acc_m,
         corpo.capturado_em, comum.jsonb(corpo.dados)),
    )
    r = cur.fetchone()
    if r is not None:
        return visita_ou_404(cur, str(r["id"])), True
    cur.execute(
        "SELECT id FROM plat.campo_visita WHERE tenant_id = %s AND cliente_uuid = %s::uuid",
        (auth.tenant_id, corpo.cliente_uuid),
    )
    existente = cur.fetchone()
    return visita_ou_404(cur, str(existente["id"])), False


def visita_ou_404(cur, visita_id: str) -> dict:
    cur.execute(
        "SELECT v.id, v.cliente_uuid, v.fila_id, v.alvo_id, v.roteiro_id, v.camada_id, v.globalid, v.status, "
        "v.texto, v.usuario_id, u.login AS usuario_login, v.lat, v.lon, v.gps_acc_m, v.capturado_em, "
        "v.recebido_em, v.dados, "
        "(SELECT json_agg(json_build_object('id', f.id, 'sha256', f.sha256, 'bytes', f.bytes, "
        "'largura', f.largura, 'altura', f.altura, 'chave', f.chave) ORDER BY f.criado_em) "
        "FROM plat.campo_visita_foto f WHERE f.visita_id = v.id) AS fotos "
        "FROM plat.campo_visita v LEFT JOIN plat.usuario u ON u.id = v.usuario_id WHERE v.id = %s::uuid",
        (visita_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "visita_inexistente", "visita inexistente")
    return r


def visitas_listar(cur, *, fila_id: str | None = None, alvo_id: str | None = None,
                   roteiro_id: str | None = None, limite: int = 500) -> list[dict]:
    condicoes = ["true"]
    args: list[Any] = []
    if fila_id:
        condicoes.append("v.fila_id = %s::uuid")
        args.append(fila_id)
    if alvo_id:
        condicoes.append("v.alvo_id = %s::uuid")
        args.append(alvo_id)
    if roteiro_id:
        condicoes.append("v.roteiro_id = %s::uuid")
        args.append(roteiro_id)
    args.append(min(limite, 2000))
    cur.execute(
        f"SELECT v.id, v.fila_id, v.alvo_id, v.roteiro_id, v.camada_id, v.globalid, v.status, v.texto, "
        f"v.usuario_id, u.login AS usuario_login, v.lat, v.lon, v.capturado_em, v.recebido_em, "
        f"(SELECT count(*) FROM plat.campo_visita_foto f WHERE f.visita_id = v.id) AS n_fotos "
        f"FROM plat.campo_visita v LEFT JOIN plat.usuario u ON u.id = v.usuario_id "
        f"WHERE {' AND '.join(condicoes)} ORDER BY v.recebido_em DESC LIMIT %s",
        args,
    )
    return cur.fetchall()


def visita_foto_guardar(cur, auth, visita_id: str, png_ou_jpeg: bytes) -> dict:
    from app import objetos
    from app.campo import fotos

    visita_ou_404(cur, visita_id)
    normalizado = fotos.normalizar(png_ou_jpeg)
    o = objetos.guardar(cur, "campo_foto", normalizado["dados"], "image/jpeg", item_id=visita_id,
                        usuario_id=auth.usuario_id)
    cur.execute(
        "INSERT INTO plat.campo_visita_foto(tenant_id, visita_id, chave, sha256, bytes, largura, altura, "
        "criado_por) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (visita_id, sha256) DO UPDATE SET criado_em = now() RETURNING id",
        (auth.tenant_id, visita_id, o["chave"], o["sha256"], o["bytes"], normalizado["largura"],
         normalizado["altura"], auth.usuario_id),
    )
    foto_id = str(cur.fetchone()["id"])
    return {"id": foto_id, "sha256": o["sha256"], "bytes": o["bytes"], "largura": normalizado["largura"],
            "altura": normalizado["altura"], "chave": o["chave"]}


__all__ = [
    "camada_ou_404", "feicao_ponto", "feicoes_geojson", "fila_criar", "fila_ou_404", "fila_alvos_adicionar",
    "fila_alvos_listar", "fila_ordem_atualizar", "filas_listar", "calcular_roteiro", "roteiro_criar",
    "roteiro_ou_404", "roteiro_paradas", "roteiros_listar", "visita_criar", "visita_ou_404", "visitas_listar",
    "visita_foto_guardar",
]
