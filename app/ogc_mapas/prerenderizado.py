"""WMTS pré-renderizado (item L2-04-i): a camada vira um arquivo PMTiles RASTER no bucket do inquilino,
e o `GetTile` passa a ler uma FAIXA de bytes desse arquivo em vez de consultar o banco e desenhar.

Por que PMTiles e não milhões de arquivos: um objeto só, endereçável por `Range`, é o formato que a
casa já usa para o mapa-base (L2-01-a) e o que o S3/Garage serve melhor — `app/objetos.ler_intervalo`
existe justamente para isso. O diretório raiz do arquivo é lido uma vez e fica em cache no processo;
cada tile custa então UMA leitura de faixa.

O arquivo é gerado pelo job `wmts.publicar` (app/ogc_mapas/tarefas.py), com a faixa de zoom declarada
por quem publica. Fora dessa faixa o WMTS continua desenhando ao vivo.
"""

from __future__ import annotations

import io
import time

from pmtiles.tile import Compression, TileType, deserialize_directory, deserialize_header, find_tile, zxy_to_tileid
from pmtiles.writer import Writer

from app import objetos
from app.ogc_mapas import matrizes

CLASSE = "wmts"
# cabeçalho + diretório raiz de um PMTiles cabem folgados em 512 KiB (o writer escreve o raiz no início)
BYTES_CABECALHO = 512 * 1024
_cache_dir: dict[str, tuple[dict, list, float]] = {}
TTL_CACHE_S = 300


def descricao(cur, item_id: str) -> dict | None:
    """A linha de `plat.wmts_publicacao` (RLS), ou None quando a camada não foi publicada."""
    cur.execute(
        "SELECT item_id::text, chave, estilo, z_min, z_max, tiles, bytes, feicoes, duracao_ms, gerado_em "
        "FROM plat.wmts_publicacao WHERE item_id = %s::uuid", (item_id,))
    r = cur.fetchone()
    return dict(r) if r else None


def _diretorio(chave: str):
    """(cabeçalho, entradas do diretório raiz) com cache curto no processo."""
    agora = time.monotonic()
    guardado = _cache_dir.get(chave)
    if guardado and agora - guardado[2] < TTL_CACHE_S:
        return guardado[0], guardado[1]
    inicio = objetos.ler_intervalo(chave, 0, BYTES_CABECALHO - 1)
    cab = deserialize_header(inicio[:127])
    d0 = cab["root_offset"]
    d1 = d0 + cab["root_length"]
    bruto = inicio[d0:d1] if d1 <= len(inicio) else objetos.ler_intervalo(chave, d0, d1 - 1)
    # `deserialize_directory` já descomprime o diretório sozinho (o formato manda gzip aqui); passar o
    # buffer descomprimido faz a biblioteca tentar descomprimir de novo e quebrar
    raiz = deserialize_directory(bruto)
    _cache_dir[chave] = (cab, raiz, agora)
    return cab, raiz


def _descomprimir(dados: bytes, compressao) -> bytes:
    if compressao == Compression.GZIP:
        import gzip

        return gzip.decompress(dados)
    return dados


def esquecer(chave: str) -> None:
    _cache_dir.pop(chave, None)


def ler_tile(cur, item_id: str, z: int, x: int, y: int) -> bytes | None:
    """Bytes PNG do tile pré-renderizado, ou None quando a camada não foi publicada, o zoom está fora
    da faixa publicada ou o tile não existe no arquivo (área sem feição)."""
    pub = descricao(cur, item_id)
    if not pub or not (pub["z_min"] <= z <= pub["z_max"]):
        return None
    chave = pub["chave"]
    try:
        cab, raiz = _diretorio(chave)
    except Exception:  # noqa: BLE001 - arquivo sumiu/ilegível: cai para o desenho ao vivo, nunca 500
        esquecer(chave)
        return None
    alvo = zxy_to_tileid(z, x, y)
    entrada = find_tile(raiz, alvo)
    if entrada is None:
        return None
    # diretório de folha: a entrada aponta para outro diretório, não para o tile
    if getattr(entrada, "run_length", 1) == 0:
        d0 = cab["leaf_directory_offset"] + entrada.offset
        bruto = objetos.ler_intervalo(chave, d0, d0 + entrada.length - 1)
        folha = deserialize_directory(bruto)
        entrada = find_tile(folha, alvo)
        if entrada is None or getattr(entrada, "run_length", 1) == 0:
            return None
    t0 = cab["tile_data_offset"] + entrada.offset
    dados = objetos.ler_intervalo(chave, t0, t0 + entrada.length - 1)
    return _descomprimir(dados, cab["tile_compression"])


def gerar(cur, item_id: str, *, desenhar, z_min: int, z_max: int, caixa4326, estilo_nome: str = "padrao",
          usuario_id: int | None = None, job_id=None, progresso=None) -> dict:
    """Renderiza a faixa de zoom inteira e grava o PMTiles no bucket. `desenhar(z, x, y) -> bytes|None`
    é injetado (o job passa o pintor); devolve o resumo que vai para `plat.wmts_publicacao`."""
    t0 = time.monotonic()
    caixa3857 = _para_3857(caixa4326)
    buf = io.BytesIO()
    escritor = Writer(buf)
    total = 0
    vazios = 0
    planejados = sum(len(matrizes.tiles_da_caixa(caixa3857, z)) for z in range(z_min, z_max + 1))
    feitos = 0
    for z in range(z_min, z_max + 1):
        for (x, y) in sorted(matrizes.tiles_da_caixa(caixa3857, z), key=lambda t: zxy_to_tileid(z, t[0], t[1])):
            png = desenhar(z, x, y)
            feitos += 1
            if png is None:
                vazios += 1
            else:
                escritor.write_tile(zxy_to_tileid(z, x, y), png)
                total += 1
            if progresso and planejados and feitos % 200 == 0:
                progresso(min(95, int(90 * feitos / planejados)), f"z{z}: {feitos}/{planejados} tiles")
    cabecalho = {
        "tile_type": TileType.PNG,
        "tile_compression": Compression.NONE,
        "min_zoom": z_min, "max_zoom": z_max,
        "min_lon_e7": int(caixa4326[0] * 1e7), "min_lat_e7": int(caixa4326[1] * 1e7),
        "max_lon_e7": int(caixa4326[2] * 1e7), "max_lat_e7": int(caixa4326[3] * 1e7),
        "center_zoom": z_min,
        "center_lon_e7": int((caixa4326[0] + caixa4326[2]) / 2 * 1e7),
        "center_lat_e7": int((caixa4326[1] + caixa4326[3]) / 2 * 1e7),
    }
    escritor.finalize(cabecalho, {"nome": item_id, "estilo": estilo_nome, "gerador": "plat L2-04-i"})
    corpo = buf.getvalue()
    objeto = objetos.guardar(cur, CLASSE, corpo, "application/vnd.pmtiles", item_id=item_id,
                             usuario_id=usuario_id)
    duracao = int((time.monotonic() - t0) * 1000)
    cur.execute(
        "INSERT INTO plat.wmts_publicacao(item_id, tenant_id, chave, estilo, z_min, z_max, tiles, bytes, "
        "feicoes, duracao_ms, gerado_por, job_id) "
        "VALUES (%s::uuid, plat.tenant_atual(), %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s::uuid) "
        "ON CONFLICT (item_id) DO UPDATE SET chave = EXCLUDED.chave, estilo = EXCLUDED.estilo, "
        "z_min = EXCLUDED.z_min, z_max = EXCLUDED.z_max, tiles = EXCLUDED.tiles, bytes = EXCLUDED.bytes, "
        "duracao_ms = EXCLUDED.duracao_ms, gerado_em = now(), gerado_por = EXCLUDED.gerado_por, "
        "job_id = EXCLUDED.job_id",
        (item_id, objeto["chave"], estilo_nome, z_min, z_max, total, len(corpo), duracao, usuario_id,
         str(job_id) if job_id else None))
    esquecer(objeto["chave"])
    return {"chave": objeto["chave"], "tiles": total, "tiles_vazios": vazios, "bytes": len(corpo),
            "z_min": z_min, "z_max": z_max, "duracao_ms": duracao}


def _para_3857(caixa4326):
    import math

    def x(lon):
        return matrizes.RAIO * math.radians(max(-180.0, min(180.0, lon)))

    def y(lat):
        lat = max(-85.05112878, min(85.05112878, lat))
        return matrizes.RAIO * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    return (x(caixa4326[0]), y(caixa4326[1]), x(caixa4326[2]), y(caixa4326[3]))
