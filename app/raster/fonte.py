"""De onde uma ferramenta raster LÊ (item L2-05-e).

Toda ferramenta desta linha abre o COG do inquilino onde ele já está — no armazenamento de objetos —
por caminho virtual do GDAL (`/vsis3/<balde>/<objeto>`, a forma da casa para o que a documentação do
GDAL chama de sistema de arquivos virtual: `/vsicurl` para HTTP público, `/vsis3` para S3). A leitura é
por faixa de bytes: o cabeçalho e só os blocos pedidos descem pela rede. Nenhuma ferramenta baixa o
arquivo inteiro nem o carrega em memória.

Duas formas de ler o mesmo objeto, porque as duas são necessárias:

* dentro do processo (rasterio): `abrir(origem)` devolve o dataset dentro de um `rasterio.Env` com a
  sessão S3 só-leitura do balde do inquilino. Reusa `app.imagens.tiles.env_gdal`/`sessao_s3` — a
  afinação de leitura remota de COG já estava escrita ali (item L1-02) e não se duplica;
* em subprocesso (gdalwarp, gdaldem, gdal_contour…): `ambiente(origens)` devolve o ambiente com as
  variáveis `AWS_*` que o GDAL do neto precisa. A credencial é a só-leitura do balde do inquilino, a
  mesma que o motor de ladrilho usa, e nunca sai em log nem em resposta.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field

import rasterio

from app import objetos
from app.imagens import tiles
from app.settings import settings


@dataclass(frozen=True)
class Origem:
    """Um raster legível: caminho GDAL (`/vsis3/...` ou caminho local do diretório de trabalho), opções
    de ambiente e a sessão S3 quando o caminho é remoto."""

    caminho: str
    opcoes: dict = field(default_factory=dict)
    remoto: bool = True

    @property
    def sessao(self):
        return tiles.sessao_s3(self.opcoes) if self.remoto else None


def da_chave(chave: str) -> Origem:
    """Origem de leitura de um objeto do armazenamento (a chave vem do asset STAC do item)."""
    caminho, opcoes = objetos.fonte_gdal(chave)
    tiles.preparar_ambiente_s3(settings.PLAT_GARAGE_URL or "")
    return Origem(caminho, opcoes, True)


def do_arquivo(caminho) -> Origem:
    """Origem de leitura de um arquivo do diretório de trabalho do job (produto intermediário)."""
    return Origem(str(caminho), {}, False)


@contextmanager
def abrir(origem: Origem):
    """Dataset rasterio aberto no ambiente certo. Só o cabeçalho desce ao abrir; cada `read(window=...)`
    puxa os blocos daquela janela."""
    with rasterio.Env(session=origem.sessao, **tiles.env_gdal()):
        with rasterio.open(origem.caminho) as ds:
            yield ds


def ambiente(*origens: Origem) -> dict:
    """Ambiente de um subprocesso GDAL que leia estas origens (`os.environ` + credencial + afinação).
    Origens de baldes diferentes não se misturam: o GDAL só guarda um par de chaves por processo, então
    origens remotas de credenciais distintas levantam erro em vez de ler com a credencial errada."""
    env = dict(os.environ)
    env.update({
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_CACHEMAX": "128",
        "GDAL_NUM_THREADS": "1",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": str(64 * 1024 * 1024),
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    })
    credencial = None
    for o in origens:
        if not o.remoto:
            continue
        atual = (o.opcoes.get("AWS_ACCESS_KEY_ID"), o.opcoes.get("AWS_S3_ENDPOINT"))
        if credencial is not None and atual != credencial:
            raise ValueError("origens remotas de baldes diferentes na mesma execução")
        credencial = atual
        env.update({k: str(v) for k, v in o.opcoes.items()})
    return env


__all__ = ["Origem", "abrir", "ambiente", "da_chave", "do_arquivo"]
