"""Disco de trabalho do upload grande (item L1-01-e; ADR 20260908T1600 seção 2): o corpo de uma parte chega
em fluxo, é gravado num arquivo temporário e só depois vai ao Garage a partir desse arquivo. Duas
consequências, e são o motivo deste módulo existir:

1. o pico de memória do processo que recebe não cresce com o tamanho do arquivo (é `UPLOAD_PEDACO_BYTES`
   por requisição em curso, não a parte inteira);
2. o disco de trabalho vira recurso finito e precisa de porteiro — `exigir_espaco` recusa ANTES de começar
   a escrever, com mensagem que diz quanto falta, em vez de encher o disco da máquina e derrubar o resto.

O diretório é `PLAT_JOBS_DIR/uploads` quando a variável existe (mesma raiz que o `dir_trabalho` dos jobs do
ADR 0003 usa), senão `var/uploads` na raiz da instalação. `var/` está no `.gitignore`."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import uuid
from collections.abc import AsyncIterable
from pathlib import Path

from app import limites
from app.erros import ErroAPI
from app.settings import ROOT
from app.settings import obter as _config


def diretorio() -> Path:
    """Disco de trabalho, criado na primeira chamada (0700: o conteúdo é dado de inquilino em trânsito)."""
    cfg = _config()
    base = Path(cfg.PLAT_JOBS_DIR) if cfg.PLAT_JOBS_DIR else ROOT / "var"
    d = base / "uploads"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def livre_bytes(caminho: Path | None = None) -> int:
    """Bytes livres do sistema de arquivos do disco de trabalho (`df` do POSIX, via os.statvfs)."""
    return shutil.disk_usage(caminho or diretorio()).free


def exigir_espaco(bytes_necessarios: int) -> None:
    """Recusa com 507 quando o disco de trabalho não tem `bytes_necessarios` MAIS a folga mínima da
    instalação (`UPLOAD_DISCO_LIVRE_MIN_BYTES`). A folga existe para que o upload não seja o processo que
    enche o disco: o último byte livre da máquina não é do upload."""
    livre = livre_bytes()
    preciso = int(bytes_necessarios) + limites.UPLOAD_DISCO_LIVRE_MIN_BYTES
    if livre < preciso:
        raise ErroAPI(
            507,
            "disco_de_trabalho_cheio",
            f"disco de trabalho com {livre} bytes livres; este envio precisa de {bytes_necessarios} bytes "
            f"mais a folga mínima de {limites.UPLOAD_DISCO_LIVRE_MIN_BYTES} bytes desta instalação. "
            "Libere espaço ou aguarde os envios em curso terminarem.",
            {
                "livre_bytes": livre,
                "necessario_bytes": preciso,
                "folga_minima_bytes": limites.UPLOAD_DISCO_LIVRE_MIN_BYTES,
            },
        )


@contextlib.contextmanager
def arquivo_temporario(prefixo: str = "parte"):
    """Caminho temporário no disco de trabalho, apagado ao sair — inclusive quando a rota levanta erro."""
    caminho = diretorio() / f"{prefixo}-{uuid.uuid4().hex}.tmp"
    try:
        yield caminho
    finally:
        with contextlib.suppress(FileNotFoundError):
            caminho.unlink()


async def gravar_em_fluxo(pedacos: AsyncIterable[bytes], caminho: Path, maximo_bytes: int) -> tuple[int, str, bytes]:
    """Escreve `pedacos` (o fluxo do corpo da requisição) em `caminho` sem nunca manter mais que um pedaço em
    memória. Devolve `(bytes_gravados, sha256, inicio)` — `inicio` são os primeiros
    `UPLOAD_CABECALHO_INICIO_BYTES`, com que a validação de tipo começa sem esperar a última parte.

    Para de ler assim que o total passa de `maximo_bytes`: quem declara Content-Length pequeno e manda corpo
    grande é recusado sem antes gravar o corpo inteiro no disco. O total devolvido nesse caso é maior que
    `maximo_bytes` de propósito, para a rota poder dizer o que aconteceu."""
    h = hashlib.sha256()
    total = 0
    inicio = bytearray()
    limite_inicio = limites.UPLOAD_CABECALHO_INICIO_BYTES
    with open(caminho, "wb") as saida:
        os.chmod(caminho, 0o600)
        async for pedaco in pedacos:
            if not pedaco:
                continue
            total += len(pedaco)
            h.update(pedaco)
            saida.write(pedaco)
            if len(inicio) < limite_inicio:
                inicio += pedaco[: limite_inicio - len(inicio)]
            if total > maximo_bytes:
                break
    return total, h.hexdigest(), bytes(inicio)
