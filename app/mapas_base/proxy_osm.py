"""Proxy raster do OSM (fonte 2 da galeria, item L2-01-e-mapas-base): a política de uso de
`tile.openstreetmap.org` (https://operations.osmfoundation.org/policies/tiles/) proíbe uso pesado sem cache
nem identificação do cliente — por isso ninguém aponta o navegador direto para lá; tudo passa por aqui.

Defesa contra SSRF É a ausência de escolha: esta rota nunca lê host de parâmetro nenhum (query, corpo,
cabeçalho) — só z/x/y, já validados como inteiros dentro da faixa do slippy-map. O host de saída vem sempre
de `limites.MAPA_BASE_OSM_HOSTS` (round-robin determinístico por ladrilho, do jeito que qualquer cliente de
mapa espalha carga pelos 3 subdomínios). Ainda assim a busca sai pelo caminho seguro comum da casa
(`app.conexao.seguranca.buscar_seguro`, o mesmo do L6-02) — defesa em profundidade contra DNS rebinding e
redirecionamento, mesmo que o host já seja fixo por construção.

Cache em disco simples (arquivo = ladrilho, sem banco): `var/cache/mapa_base_osm/<z>/<x>/<y>.png`, teto de
`limites.MAPA_BASE_OSM_CACHE_BYTES_MAX` — ao estourar, apaga os arquivos mais antigos (mtime) até caber (disco
da casa a 98 %, ver CLAUDE.md D27)."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import Response

from app import limites
from app.conexao import seguranca
from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "var" / "cache" / "mapa_base_osm"


class ErroLadrilhoInvalido(ErroAPI):
    def __init__(self, campo: str, mensagem: str):
        super().__init__(422, "validacao", mensagem, {"campo": campo})


def validar_zxy(z: int, x: int, y: int) -> None:
    if not (0 <= z <= limites.MAPA_BASE_ZOOM_MAX):
        raise ErroLadrilhoInvalido("z", f"z tem de estar entre 0 e {limites.MAPA_BASE_ZOOM_MAX}")
    lado = 2**z
    if not (0 <= x < lado):
        raise ErroLadrilhoInvalido("x", f"x tem de estar entre 0 e {lado - 1} no zoom {z}")
    if not (0 <= y < lado):
        raise ErroLadrilhoInvalido("y", f"y tem de estar entre 0 e {lado - 1} no zoom {z}")


def _host_do_ladrilho(z: int, x: int, y: int) -> str:
    """Round-robin determinístico pelos 3 subdomínios oficiais — nunca um valor de fora da lista."""
    hosts = limites.MAPA_BASE_OSM_HOSTS
    return hosts[(x + y) % len(hosts)]


def _caminho_cache(z: int, x: int, y: int) -> Path:
    return CACHE_DIR / str(z) / str(x) / f"{y}.png"


def _tamanho_cache_bytes() -> int:
    if not CACHE_DIR.exists():
        return 0
    return sum(p.stat().st_size for p in CACHE_DIR.rglob("*.png") if p.is_file())


def _abrir_espaco(bytes_necessarios: int) -> None:
    """Apaga os `.png` mais antigos (mtime) até que `bytes_necessarios` caiba no teto configurado."""
    teto = limites.MAPA_BASE_OSM_CACHE_BYTES_MAX
    if not CACHE_DIR.exists():
        return
    usado = _tamanho_cache_bytes()
    if usado + bytes_necessarios <= teto:
        return
    arquivos = sorted((p for p in CACHE_DIR.rglob("*.png") if p.is_file()), key=lambda p: p.stat().st_mtime)
    for p in arquivos:
        if usado + bytes_necessarios <= teto:
            break
        usado -= p.stat().st_size
        p.unlink(missing_ok=True)


def buscar_ladrilho(z: int, x: int, y: int) -> tuple[bytes, bool]:
    """Devolve (bytes_png, veio_do_cache). Nunca levanta por falha do upstream — vira ErroAPI 502/504, nomeado,
    para a rota decidir o corpo da resposta; SSRF é impossível aqui porque o host nunca vem de fora."""
    validar_zxy(z, x, y)
    caminho = _caminho_cache(z, x, y)
    if caminho.exists():
        return caminho.read_bytes(), True

    host = _host_do_ladrilho(z, x, y)
    url = f"https://{host}/{z}/{x}/{y}.png"
    resultado = seguranca.buscar_seguro(
        url,
        metodo="GET",
        timeout_conectar=limites.MAPA_BASE_OSM_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.MAPA_BASE_OSM_LER_TIMEOUT_S,
        max_bytes=limites.MAPA_BASE_OSM_RESPOSTA_MAX_BYTES,
        cabecalhos={"User-Agent": limites.MAPA_BASE_OSM_USER_AGENT},
        guardar_corpo=True,
    )
    if not resultado.ok or not resultado.corpo:
        raise ErroAPI(
            502, "upstream_osm_falhou", f"tile.openstreetmap.org não respondeu: {resultado.mensagem}",
            {"z": z, "x": x, "y": y, "host": host},
        )
    corpo = resultado.corpo
    try:
        _abrir_espaco(len(corpo))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_suffix(f".tmp{time.monotonic_ns()}")
        tmp.write_bytes(corpo)
        tmp.replace(caminho)  # troca atômica: dois pedidos concorrentes nunca leem arquivo pela metade
    except OSError:
        pass  # disco cheio/indisponível: serve o ladrilho mesmo sem cachear (melhor que 500)
    return corpo, False


def resposta_ladrilho(z: int, x: int, y: int) -> Response:
    corpo, veio_do_cache = buscar_ladrilho(z, x, y)
    return Response(
        content=corpo,
        media_type="image/png",
        headers={"X-Cache": "HIT" if veio_do_cache else "MISS", "Cache-Control": "public, max-age=86400"},
    )
