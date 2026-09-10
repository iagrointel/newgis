"""Glifos de fonte (PBF) para o estilo MapLibre — item L2-02-e-simbolos-sprites-glifos.

Ao contrário do sprite (app/simbolos/sprite.py), a fonte embutida NUNCA muda em runtime (não há upload
de fonte pelo inquilino), então a limitação do Martin de só ler o catálogo na subida não atrapalha aqui:
um Martin de verdade, apontado para `web/vendor/` (as .ttf; VERSOES.txt tem o sha256/licença de cada
arquivo — Martin ignora, sem erro, os .js/.css/.woff2 vizinhos, medido em 07/09), serve
`/font/{fontstack}/{inicio}-{fim}.pbf` no formato SDF que o MapLibre espera.

Produção: `PLAT_MARTIN_SIMBOLOS_URL` aponta para o Martin dedicado (`deploy/martin_simbolos.yaml` +
`deploy/plat-martin-simbolos.service`, a instalar junto do deploy — não sobe sozinho, ninguém reinicia
serviço de produção a partir desta trilha). Sem essa variável (dev/teste), este módulo sobe um Martin
PRÓPRIO, efêmero, na primeira chamada, numa porta livre escolhida na hora — mata-lo é responsabilidade do
processo que o subiu (`encerrar()`, usado pelos testes)."""
from __future__ import annotations

import atexit
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx

from app.erros import ErroAPI
from app.settings import settings

ROOT = Path(__file__).resolve().parents[2]
DIR_FONTES = ROOT / "web" / "vendor"
MARTIN_BIN = "/usr/local/bin/martin"
_TIMEOUT = httpx.Timeout(connect=1.0, read=5.0, write=2.0, pool=2.0)

_trava = threading.Lock()
_processo: subprocess.Popen | None = None
_url_efemera: str | None = None


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _subir_martin_efemero() -> str:
    global _processo, _url_efemera
    with _trava:
        if _url_efemera is not None:
            return _url_efemera
        porta = _porta_livre()
        _processo = subprocess.Popen(
            [MARTIN_BIN, "--font", str(DIR_FONTES), "--listen-addresses", f"127.0.0.1:{porta}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{porta}"
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite:
            try:
                r = httpx.get(f"{url}/catalog", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        _url_efemera = url
        atexit.register(encerrar)
        return url


def encerrar() -> None:
    global _processo, _url_efemera
    with _trava:
        if _processo is not None:
            _processo.terminate()
            try:
                _processo.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _processo.kill()
            _processo = None
        _url_efemera = None


def _url_base() -> str:
    return settings.PLAT_MARTIN_SIMBOLOS_URL or _subir_martin_efemero()


def glifos_pbf(fontstack: str, inicio: int, fim: int) -> bytes:
    url = f"{_url_base()}/font/{fontstack}/{inicio}-{fim}.pbf"
    try:
        # o Martin devolve 301 para a grafia canônica do fontstack antes de servir o .pbf (medido em 07/09
        # com curl -L); sem seguir o redirecionamento o pedido nunca chega ao conteúdo de verdade.
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as e:
        raise ErroAPI(502, "fontes_indisponivel", "servidor de glifos indisponível") from e
    if r.status_code == 404:
        raise ErroAPI(404, "fonte_nao_encontrada", f"fonte {fontstack!r} não embutida nesta plataforma")
    if r.status_code != 200:
        raise ErroAPI(502, "fontes_indisponivel", f"servidor de glifos devolveu {r.status_code}")
    return r.content
