"""Camada mínima de varredura de conteúdo em upload (item L7-03-b-antivirus-anexos; docs/SEGURANCA.md §8): cobre
o caminho de `POST /api/arquivos` (L0-11-arquivos-objetos) e o de `POST /api/itens/{id}/miniatura` (L0-03-catalogo)
— hoje os dois aceitavam qualquer byte sob o `Content-Type` que o cliente escolhesse, sem conferir se o CONTEÚDO
bate com o que foi declarado (a extensão/`Content-Type` é escolha do remetente; os bytes não).

**Por que não é ClamAV ainda (D21, decisão registrada em `laco/estado.json`)**: MEDIDO em 06/09/2026 antes de
instalar, `df -h /` = 12-13 GiB livres num disco a 98% e `free -h` = 323 MiB livres de RAM com o swap (8 GiB)
CHEIO. O daemon `clamd` propriamente dito é pequeno (pacote ~1 MB), mas a base de assinaturas do `freshclam`
carregada em RAM pelo `clamd` fica na casa de 1,3-1,5 GiB residente — nesta janela, com 323 MiB livres, isso quase
certamente devolveria a máquina para o mesmo incidente de OOM já registrado na casa (`reference_oom-derrubou-
postgres`). Por isso esta passagem instala a camada mínima abaixo (assinatura mágica via `libmagic`, já presente
no dpkg desta máquina como `python3-magic`, RAM desprezível) e deixa o gancho pronto: `escanear_cabecalho()` é a
ÚNICA função que os chamadores conhecem; trocar para ClamAV depois é implementar um `Motor` novo com a mesma
assinatura e trocar o motor ativo em `MOTOR_ATIVO`, sem tocar `app/objetos.py` nem as rotas.

O que a varredura faz: identifica o tipo REAL do arquivo pelos primeiros bytes (assinatura mágica, a mesma
técnica do comando `file`/`libmagic` — não a extensão do nome, que o cliente escolhe livremente) e recusa quando
o tipo detectado não é compatível com a família esperada do `Content-Type` que o cliente declarou (ex.: declarado
`image/jpeg`, bytes de verdade são um script de shell → `text/x-shellscript` não está na família {image/jpeg}).
Isso já cobre o polyglot óbvio do portão: um arquivo com assinatura de imagem que também é reconhecido como
HTML/script continua batendo a checagem porque o tipo QUE O MAGIC RECONHECE PRIMEIRO já não é o da família
declarada.

**Por que NÃO existe também um denylist "tipo perigoso, seja qual for o declarado"** (script/executável recusado
mesmo sob `application/octet-stream`, que não tem família fixa): MEDIDO nesta máquina antes de escrever a regra
— `libmagic` classifica ~0,9% (18/2000, `python3 -c` descartado) de bytes PURAMENTE ALEATÓRIOS como algo
diferente de `application/octet-stream` (inclusive `application/x-dosexec` por coincidência de assinatura), o
que tornaria qualquer upload binário genérico (`os.urandom` nos testes de `tests/api/test_arquivos.py`, e
qualquer CAD/binário proprietário real do cliente) uma reprovação aleatória e reproduzível só às vezes — o
oposto de P5 (reprodutível) e de P3 (suíte sempre verde). Por isso o `Content-Type` genérico não é escaneado por
assinatura nesta camada: é exatamente onde um motor de conteúdo de verdade (ClamAV) faria a diferença — decisão
que fica para depois de D21."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import magic

CABECALHO_BYTES = 8192  # libmagic precisa só do início; nunca lê o arquivo inteiro para decidir o tipo

# --- família de tipo real aceitável por Content-Type declarado (mesmas chaves de app/objetos.EXTENSOES).
# `None` = sem família fixa (declarado genérico, ex. application/octet-stream): a checagem de assinatura não
# se aplica (ver a justificativa MEDIDA no docstring do módulo) — passa sem exame de conteúdo nesta camada.
TIPOS_PERMITIDOS: dict[str, frozenset[str] | None] = {
    "image/png": frozenset({"image/png"}),
    "image/jpeg": frozenset({"image/jpeg"}),
    "image/gif": frozenset({"image/gif"}),
    "image/tiff": frozenset({"image/tiff"}),
    "image/webp": frozenset({"image/webp"}),
    "application/json": frozenset({"application/json", "text/plain"}),
    "application/geo+json": frozenset({"application/json", "text/plain"}),
    "text/csv": frozenset({"text/csv", "text/plain"}),
    "application/pdf": frozenset({"application/pdf"}),
    "application/zip": frozenset({"application/zip"}),
    "application/vnd.google-earth.kmz": frozenset({"application/zip"}),  # kmz é um zip por dentro
    "application/octet-stream": None,
}


@dataclass(frozen=True)
class Resultado:
    permitido: bool
    motivo: str | None
    tipo_detectado: str
    motor: str


class Motor(Protocol):
    """Interface que qualquer motor de varredura implementa (o gancho para trocar por ClamAV, D21)."""

    nome: str

    def escanear(self, cabecalho: bytes, content_type_declarado: str) -> Resultado: ...


class MotorAssinaturaBasica:
    """Motor mínimo desta passagem: bytes mágicos + família declarada × detectada (sem daemon, sem RAM extra)."""

    nome = "assinatura_basica"

    def __init__(self) -> None:
        self._magic = magic.Magic(mime=True)

    def escanear(self, cabecalho: bytes, content_type_declarado: str) -> Resultado:
        if not cabecalho:
            return Resultado(False, "conteúdo vazio", "vazio", self.nome)
        tipo_real = self._magic.from_buffer(cabecalho[:CABECALHO_BYTES]).split(";")[0].strip()
        declarado = (content_type_declarado or "application/octet-stream").split(";")[0].strip().lower()
        familia = TIPOS_PERMITIDOS.get(declarado, None)
        if familia is not None and tipo_real not in familia:
            return Resultado(
                False,
                f"conteúdo real ({tipo_real}) não bate com o Content-Type declarado ({declarado})",
                tipo_real,
                self.nome,
            )
        return Resultado(True, None, tipo_real, self.nome)


MOTOR_ATIVO: Motor = MotorAssinaturaBasica()


class ConteudoRecusado(ValueError):
    """Levantada por `escanear_cabecalho()` quando o motor ativo recusa — quem chama decide o código HTTP
    (415 na maioria das rotas, mesmo padrão de `objetos.CotaExcedida` → 413)."""

    def __init__(self, resultado: Resultado) -> None:
        super().__init__(resultado.motivo)
        self.resultado = resultado


def escanear_cabecalho(cabecalho: bytes, content_type_declarado: str) -> Resultado:
    """Levanta `ConteudoRecusado` quando o motor ativo recusa; devolve o `Resultado` (sempre `permitido=True`
    quando não levanta) quando aceita — assim o chamador que só quer o efeito colateral (recusar) não precisa
    conferir `.permitido` toda vez, e quem quer registrar o tipo detectado no evento ainda tem o valor."""
    r = MOTOR_ATIVO.escanear(cabecalho, content_type_declarado)
    if not r.permitido:
        raise ConteudoRecusado(r)
    return r
