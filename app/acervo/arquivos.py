"""Camadas de ARQUIVO do acervo da casa (item L6-01-i-raster-e-arquivos): o acervo não é só tabela. Os arquivos
registrados em `acervo.camada_arquivo` (com sha256, medido 08/09/2026: 321 linhas, 3,6 GB, 18 raster .tif e 303
vetoriais) entram no catálogo do inquilino como camada raster (servida por ladrilho com token, item L1-02) ou
camada vetorial (ingestão única para PostGIS), com a MESMA ficha de procedência da fonte.

Três regras que este módulo faz valer, todas antes de tocar o catálogo:
1. **sha256 conferido**: o arquivo é lido em fluxo e o hash comparado com o do registro; divergiu, a exposição é
   RECUSADA (`hash_divergente`) e nada é criado — a refutação do item ("adversário altera 1 byte") morre aqui.
2. **guardrail de disco (D21)**: arquivo acima de `ACERVO_ARQUIVO_BYTES_MAX` (2 GB, o mesmo teto de raster do
   L1-01) é recusado com `arquivo_grande_demais`; a soma do que um inquilino expõe de uma vez tem teto próprio.
3. **licença (D17)**: fonte sem licença escrita não impede a casa de usar o próprio acervo, mas o item nasce
   PRIVADO e marcado `uso_restrito`; publicar ou compartilhar esse item é recusado na rota de compartilhamento.
   Medido em 08/09/2026: NENHUMA das 27 fontes de arquivo tem licença escrita — é o estado real, não um exemplo.

O caminho do registro é relativo a `PLAT_ACERVO_ARQUIVOS_RAIZ`; sem essa configuração a instalação simplesmente
não tem acervo de arquivo (lista vazia, nunca erro). O caminho é resolvido e conferido contra a raiz (nunca sai
dela, nem por `..` nem por symlink)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from app import limites
from app.erros import ErroAPI
from app.settings import settings

EXTENSOES_RASTER = frozenset({"tif", "tiff", "vrt"})
EXTENSOES_VETOR = frozenset({"geojson", "json", "gpkg", "shp", "parquet", "fgb", "gml", "kml", "csv", "zip"})
LEITURA_BLOCO = 1024 * 1024


class ArquivoRecusado(ErroAPI):
    """422 com código nomeado: `hash_divergente`, `arquivo_ausente`, `arquivo_grande_demais`,
    `extensao_nao_suportada`, `fora_da_raiz`."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(422, codigo, mensagem, detalhe)


@dataclass(frozen=True)
class Arquivo:
    caminho: str          # relativo à raiz, como está no registro
    absoluto: Path
    tipo: str             # raster | vetor
    extensao: str
    bytes_registro: int | None
    sha256_registro: str


def raiz() -> Path | None:
    bruto = (settings.PLAT_ACERVO_ARQUIVOS_RAIZ or "").strip()
    if not bruto:
        return None
    return Path(bruto).resolve()


def configurado() -> bool:
    r = raiz()
    return r is not None and r.is_dir()


def tipo_de(caminho: str) -> str:
    ext = extensao_de(caminho)
    if ext in EXTENSOES_RASTER:
        return "raster"
    return "vetor"


def extensao_de(caminho: str) -> str:
    return caminho.rsplit(".", 1)[-1].lower() if "." in caminho else ""


def resolver(caminho: str) -> Path:
    """Caminho absoluto DENTRO da raiz. `..`, caminho absoluto e symlink que sai da raiz são recusados —
    o caminho vem de uma tabela que a casa escreve, mas a rota o recebe do cliente."""
    base = raiz()
    if base is None:
        raise ArquivoRecusado("acervo_sem_raiz", "esta instalação não tem raiz de arquivos do acervo configurada")
    if not caminho or caminho.startswith("/") or "\x00" in caminho:
        raise ArquivoRecusado("fora_da_raiz", "caminho inválido no acervo de arquivo", {"caminho": caminho[:200]})
    alvo = (base / caminho).resolve()
    if alvo != base and base not in alvo.parents:
        raise ArquivoRecusado("fora_da_raiz", "caminho fora da raiz do acervo", {"caminho": caminho[:200]})
    return alvo


def sha256_do_arquivo(caminho: Path) -> str:
    """Hash em fluxo: um arquivo de gigabytes nunca passa inteiro pela memória do worker."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(LEITURA_BLOCO):
            h.update(bloco)
    return h.hexdigest()


def conferir(registro: dict) -> Arquivo:
    """Confere existência, tamanho e SHA256 do arquivo contra o registro do acervo. Levanta `ArquivoRecusado`
    com código nomeado; devolve o `Arquivo` pronto para ingerir quando tudo bate."""
    caminho = registro["caminho"]
    ext = extensao_de(caminho)
    if ext not in EXTENSOES_RASTER and ext not in EXTENSOES_VETOR:
        raise ArquivoRecusado("extensao_nao_suportada", f"extensão {ext!r} não é ingerida por esta rota",
                              {"caminho": caminho, "extensao": ext})
    alvo = resolver(caminho)
    if not alvo.is_file():
        raise ArquivoRecusado("arquivo_ausente", "o arquivo do registro não está no disco desta instalação",
                              {"caminho": caminho})
    tamanho = alvo.stat().st_size
    if tamanho > limites.ACERVO_ARQUIVO_BYTES_MAX:
        raise ArquivoRecusado(
            "arquivo_grande_demais",
            f"arquivo de {tamanho} bytes acima do teto de {limites.ACERVO_ARQUIVO_BYTES_MAX} "
            "(guardrail de disco; exige decisão do dono)",
            {"caminho": caminho, "bytes": tamanho, "teto": limites.ACERVO_ARQUIVO_BYTES_MAX},
        )
    esperado = (registro.get("sha256") or "").strip().lower()
    if not esperado:
        raise ArquivoRecusado("sem_hash_no_registro", "o registro do acervo não tem sha256 para este arquivo",
                              {"caminho": caminho})
    obtido = sha256_do_arquivo(alvo)
    if obtido != esperado:
        raise ArquivoRecusado(
            "hash_divergente",
            "o arquivo mudou desde o registro do acervo (sha256 diferente): exposição recusada",
            {"caminho": caminho, "sha256_registro": esperado, "sha256_arquivo": obtido},
        )
    return Arquivo(caminho=caminho, absoluto=alvo, tipo=tipo_de(caminho), extensao=ext,
                   bytes_registro=registro.get("bytes"), sha256_registro=esperado)


def relativo(absoluto: Path) -> str:
    base = raiz()
    return os.path.relpath(str(absoluto), str(base)) if base else str(absoluto)
