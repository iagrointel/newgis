"""O resultado de um traçado como TABELA, AGREGAÇÃO, ARQUIVO e CAMADA (item L4-02-f-resultados-e-exportacao).

O traçado já devolve a lista de elementos e a geometria agregada (`tracado.py`, `direcao.py`, `lacos.py`,
`config_tracado.py`). Este módulo não traça nada: ele pega essa lista e a transforma no que o portão do item
pede — a linha de tabela com id, tipo, grupo, terminal e comprimento; as agregações por tipo de ativo e por
nível de tensão; o arquivo em CSV, GeoJSON ou GeoPackage; e a camada salva no catálogo com procedência.

NÍVEL DE TENSÃO é o TIER declarado no pacote de ativos (`plat.rede_tier`: subtransmissão, média tensão,
baixa tensão, com a ordem), nunca um número deduzido do nome do grupo. Elemento cujo tipo não chegou até
aqui com tier fica em `nivel = null` e é contado numa linha própria — o resultado diz o que não sabe.

COMPRIMENTO é `ST_Length` sobre a geografia da feição-trecho (metros no elipsoide), e só existe para
elemento de linha; terminal de dispositivo é ponto e sai com comprimento nulo, nunca zero."""

import csv
import io
import json

from app.rede_utilidades import geopacote

COLUNAS_TABELA = ("id", "tipo", "grupo", "terminal", "comprimento_m", "nivel")
FORMATOS = ("csv", "geojson", "gpkg")
MEDIA_TYPE = {
    "csv": "text/csv; charset=utf-8",
    "geojson": "application/geo+json",
    "gpkg": "application/geopackage+sqlite3",
}
EXTENSAO = {"csv": "csv", "geojson": "geojson", "gpkg": "gpkg"}


def _niveis(cur, rede_id: str, tipo_ids: set) -> dict:
    """{tipo_id: {codigo, nome, ordem}} do tier de cada tipo de ativo presente no resultado."""
    tipo_ids = [t for t in tipo_ids if t]
    if not tipo_ids:
        return {}
    cur.execute(
        "SELECT t.id, ti.codigo, ti.nome, ti.ordem FROM plat.rede_tipo t "
        "JOIN plat.rede_tier ti ON ti.id = t.tier_id "
        "WHERE t.rede_id = %s::uuid AND t.id = ANY(%s::uuid[])",
        (rede_id, tipo_ids),
    )
    return {str(r["id"]): {"codigo": r["codigo"], "nome": r["nome"], "ordem": r["ordem"]}
            for r in cur.fetchall()}


def _geometrias(cur, rede_id: str, feicao_ids: list, com_geometria: bool) -> dict:
    """{feicao_id: {geojson, wkb, comprimento_m}} para as feições do resultado (ponto e linha na mesma volta;
    comprimento só na linha). `com_geometria=False` não traz o GeoJSON nem o WKB: o painel de agregações só
    precisa do comprimento, e carregar a geometria de todo elemento a cada traçado seria pagar a exportação
    sem exportar."""
    if not feicao_ids:
        return {}
    saida = {}
    geo = "ST_AsGeoJSON(geom)" if com_geometria else "NULL::text"
    wkb = "ST_AsBinary(geom)" if com_geometria else "NULL::bytea"
    cur.execute(
        f"SELECT id, {geo} AS gj, {wkb} AS wkb, NULL::float8 AS comprimento_m "
        "FROM plat.rede_feicao_ponto WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) "
        "UNION ALL "
        f"SELECT id, {geo}, {wkb}, ST_Length(geom::geography) "
        "FROM plat.rede_feicao_linha WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
        (rede_id, feicao_ids, rede_id, feicao_ids),
    )
    for r in cur.fetchall():
        saida[str(r["id"])] = {
            "geojson": json.loads(r["gj"]) if r["gj"] else None,
            "wkb": bytes(r["wkb"]) if r["wkb"] is not None else None,
            "comprimento_m": round(float(r["comprimento_m"]), 3) if r["comprimento_m"] is not None else None,
        }
    return saida


def tabela(cur, rede_id: str, elementos: list[dict], com_geometria: bool = True) -> list[dict]:
    """A lista de elementos do traçado virada em linha de tabela, ordenada por (tipo, id, terminal) para que
    duas exportações do mesmo resultado saiam iguais byte a byte."""
    niveis = _niveis(cur, rede_id, {e.get("tipo_id") for e in elementos})
    geo = _geometrias(cur, rede_id, sorted({e["feicao_id"] for e in elementos}), com_geometria)
    linhas = []
    for e in elementos:
        nivel = niveis.get(e.get("tipo_id") or "")
        g = geo.get(e["feicao_id"], {})
        linhas.append({
            "id": e["feicao_id"],
            "tipo": e.get("tipo_chave"),
            "tipo_nome": e.get("tipo_nome"),
            "grupo": e.get("grupo"),
            "terminal": e.get("terminal"),
            "comprimento_m": g.get("comprimento_m") if e.get("terminal") is None else None,
            "nivel": (nivel or {}).get("codigo"),
            "nivel_nome": (nivel or {}).get("nome"),
            "nivel_ordem": (nivel or {}).get("ordem"),
            "geometria": g.get("geojson"),
            "wkb": g.get("wkb"),
        })
    linhas.sort(key=lambda x: (x["tipo"] or "", x["id"], -1 if x["terminal"] is None else x["terminal"]))
    return linhas


def agregar(linhas: list[dict]) -> dict:
    """Agregação por tipo de ativo e por nível de tensão: contagem e soma de comprimento em cada faixa. É a
    conta do painel lateral, e a soma das contagens de cada agregação é sempre o total do traçado."""
    por_tipo: dict = {}
    por_nivel: dict = {}
    for linha in linhas:
        chave_t = (linha["tipo"], linha["grupo"], linha["tipo_nome"])
        alvo = por_tipo.setdefault(chave_t, {"tipo": linha["tipo"], "tipo_nome": linha["tipo_nome"],
                                             "grupo": linha["grupo"], "contagem": 0, "comprimento_m": 0.0})
        alvo["contagem"] += 1
        alvo["comprimento_m"] += linha["comprimento_m"] or 0.0
        chave_n = (linha["nivel"], linha["nivel_nome"], linha["nivel_ordem"])
        alvo = por_nivel.setdefault(chave_n, {"nivel": linha["nivel"], "nivel_nome": linha["nivel_nome"],
                                              "ordem": linha["nivel_ordem"], "contagem": 0,
                                              "comprimento_m": 0.0})
        alvo["contagem"] += 1
        alvo["comprimento_m"] += linha["comprimento_m"] or 0.0
    for grupo in (por_tipo, por_nivel):
        for valor in grupo.values():
            valor["comprimento_m"] = round(valor["comprimento_m"], 3)
    return {
        "total": len(linhas),
        "comprimento_m": round(sum(x["comprimento_m"] or 0.0 for x in linhas), 3),
        "por_tipo": sorted(por_tipo.values(), key=lambda x: (-x["contagem"], x["tipo"] or "")),
        "por_nivel": sorted(por_nivel.values(),
                            key=lambda x: (x["ordem"] is None, x["ordem"] or 0, x["nivel"] or "")),
    }


def _csv(linhas: list[dict]) -> bytes:
    saida = io.StringIO(newline="")
    escritor = csv.writer(saida, lineterminator="\r\n")  # RFC 4180
    escritor.writerow(COLUNAS_TABELA)
    for linha in linhas:
        escritor.writerow([linha[coluna] if linha[coluna] is not None else "" for coluna in COLUNAS_TABELA])
    return saida.getvalue().encode("utf-8")


def _geojson(linhas: list[dict], propriedades_comuns: dict) -> bytes:
    colecao = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": linha["id"], "geometry": linha["geometria"],
             "properties": {coluna: linha[coluna] for coluna in COLUNAS_TABELA}}
            for linha in linhas
        ],
        "procedencia": propriedades_comuns,
    }
    return json.dumps(colecao, ensure_ascii=False, default=str).encode("utf-8")


def _gpkg(linhas: list[dict]) -> bytes:
    return geopacote.escrever(
        "tracado", list(COLUNAS_TABELA),
        [{coluna: linha[coluna] for coluna in COLUNAS_TABELA} for linha in linhas],
        [geopacote.envelope(linha["wkb"]) for linha in linhas],
        identificador="tracado",
    )


def exportar(linhas: list[dict], formato: str, procedencia: dict) -> bytes:
    """Os bytes do arquivo no formato pedido. Nenhum dos três perde elemento: a contagem de linhas do CSV, de
    feições do GeoJSON e de registros do GeoPackage é sempre `len(linhas)` (conferido no teste do item)."""
    if formato == "csv":
        return _csv(linhas)
    if formato == "geojson":
        return _geojson(linhas, procedencia)
    if formato == "gpkg":
        return _gpkg(linhas)
    raise ValueError(f"formato desconhecido: {formato}")
