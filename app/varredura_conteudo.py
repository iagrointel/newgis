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

import hashlib
import socket
import struct
from dataclasses import dataclass, field
from typing import Protocol

import magic

from app import limites
from app.ingestao.formatos import ZipSuspeito, conferir_zip

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
    # L7-03-a: tipos do pipeline único de upload (anexo). Texto/XML: libmagic devolve text/plain, text/xml ou
    # application/xml conforme o começo do arquivo — as três famílias são texto sem executável por dentro; o SVG
    # ainda passa pelo sanitizador (app/svg_seguro.py) e o HTML nunca é servido inline (rotas_arquivos.ler).
    "image/svg+xml": frozenset({"image/svg+xml", "text/xml", "application/xml", "text/plain", "text/html"}),
    # text/plain: texto nunca é executado e sai como attachment+nosniff; binário genérico declarado como texto é
    # aceito de propósito (os testes do L0-11 mandam bytes aleatórios como text/plain) — o antivírus, quando
    # ligado, é quem olha por dentro
    "text/plain": frozenset({"text/plain", "text/csv", "application/octet-stream"}),
    "text/html": frozenset({"text/html", "text/plain", "text/xml"}),
    "application/vnd.google-earth.kml+xml": frozenset({"text/xml", "application/xml", "text/plain"}),
}


@dataclass(frozen=True)
class Resultado:
    permitido: bool
    motivo: str | None
    tipo_detectado: str
    motor: str
    virus: str | None = None  # nome da assinatura quando o antivírus recusa (L7-03-a)


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


class ClamdIndisponivel(RuntimeError):
    """clamd configurado (PLAT_CLAMD) mas fora do ar: o upload é RECUSADO (nunca passa sem varrer)."""


class MotorClamd:
    """Antivírus ClamAV por `clamd` (item L7-03-a): protocolo INSTREAM sobre socket unix ou TCP, biblioteca
    padrão só (nenhuma dependência nova). Manda até `limites.CLAMD_MAX_BYTES` (o StreamMaxLength padrão do
    daemon); resposta `stream: OK` aceita, `stream: <assinatura> FOUND` recusa com o nome da assinatura.
    OPCIONAL na instalação (custa ~1,3 GiB de RAM de assinaturas; o appliance pode não ter): só entra na cadeia
    quando `PLAT_CLAMD` está definido — e aí clamd fora do ar recusa o upload em vez de deixar passar."""

    nome = "clamd"

    def __init__(self, endereco: str) -> None:
        self.endereco = endereco

    def _conectar(self) -> socket.socket:
        if self.endereco.startswith("/"):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(limites.CLAMD_TIMEOUT_S)
            s.connect(self.endereco)
            return s
        host, _, porta = self.endereco.rpartition(":")
        return socket.create_connection((host or "127.0.0.1", int(porta or 3310)), timeout=limites.CLAMD_TIMEOUT_S)

    def escanear(self, cabecalho: bytes, content_type_declarado: str) -> Resultado:
        dados = cabecalho[: limites.CLAMD_MAX_BYTES]
        try:
            with self._conectar() as s:
                s.sendall(b"zINSTREAM\0")
                for i in range(0, len(dados), 65536):
                    pedaco = dados[i : i + 65536]
                    s.sendall(struct.pack(">I", len(pedaco)) + pedaco)
                s.sendall(struct.pack(">I", 0))
                resposta = b""
                while not resposta.endswith(b"\0") and len(resposta) < 4096:
                    lido = s.recv(4096)
                    if not lido:
                        break
                    resposta += lido
        except OSError as e:
            raise ClamdIndisponivel(f"clamd em {self.endereco} não respondeu: {type(e).__name__}") from e
        texto = resposta.rstrip(b"\0").decode("utf-8", errors="replace").strip()
        if texto.endswith(" FOUND"):
            assinatura = texto.split(":", 1)[-1].strip()[: -len(" FOUND")].strip()
            return Resultado(False, f"antivírus recusou: {assinatura}", "malware", self.nome, virus=assinatura)
        if texto.endswith(" OK"):
            return Resultado(True, None, "sem ameaça conhecida", self.nome)
        raise ClamdIndisponivel(f"clamd respondeu algo inesperado: {texto[:80]!r}")


def endereco_clamd() -> str | None:
    """`PLAT_CLAMD` das configurações (função, não constante: as configurações são congeladas e o teste troca
    esta função por um clamd de teste em socket unix)."""
    from app.settings import settings

    return getattr(settings, "PLAT_CLAMD", None)


def motor_antivirus() -> Motor | None:
    """`MotorClamd` quando `PLAT_CLAMD` está definido; senão `None` (só a assinatura básica)."""
    endereco = endereco_clamd()
    return MotorClamd(endereco) if endereco else None


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
    av = motor_antivirus()
    if av is not None:
        try:
            ra = av.escanear(cabecalho, content_type_declarado)
        except ClamdIndisponivel as e:
            raise ConteudoRecusado(Resultado(False, str(e), r.tipo_detectado, av.nome)) from e
        if not ra.permitido:
            raise ConteudoRecusado(Resultado(False, ra.motivo, r.tipo_detectado, av.nome, virus=ra.virus))
    return r


# --------------------------------------------------------------------------- pipeline único (L7-03-a)


@dataclass(frozen=True)
class Politica:
    """o que uma CLASSE de upload aceita: Content-Types (provados pelos bytes por `escanear_cabecalho`) e teto."""

    nome: str
    tipos: frozenset[str]
    max_bytes: int
    descricao: str = ""
    inline: frozenset[str] = field(default_factory=frozenset)  # tipos que podem ser servidos inline (imagens)


_IMAGENS = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"})
_ANEXO = _IMAGENS | frozenset({
    "application/pdf", "text/csv", "text/plain", "application/json", "application/geo+json", "application/zip",
    "application/vnd.google-earth.kmz", "application/vnd.google-earth.kml+xml", "text/html",
})
# Lista por rota/classe. Paridade: a Esri fecha por EXTENSÃO (`uploadFileExtensionAllowedList`: soe, sd, sde,
# odc, csv, txt, zshp, kmz, geodatabase); aqui a chave é o Content-Type declarado e os BYTES têm de bater.
# `objeto` (padrão de POST /api/arquivos) aceita tudo o que a assinatura básica conhece, inclusive o genérico
# `application/octet-stream` (binário do cliente: CAD, proprietário) — é a classe "arquivo bruto"; as classes
# de anexo e imagem são estreitas de propósito. Classe desconhecida cai em `objeto`.
POLITICAS: dict[str, Politica] = {
    "objeto": Politica("objeto", frozenset(TIPOS_PERMITIDOS), limites.ARQUIVO_BYTES_MAX,
                       "arquivo bruto do inquilino (qualquer tipo conhecido, inclusive binário genérico)", _IMAGENS),
    "anexo": Politica("anexo", _ANEXO, limites.ANEXO_BYTES_MAX,
                      "anexo de feição/item: documento, imagem, planilha, KML/KMZ; nunca executável", _IMAGENS),
    "foto_campo": Politica("foto_campo", frozenset({"image/jpeg", "image/png", "image/webp"}), limites.ANEXO_BYTES_MAX,
                           "foto de campo: só JPEG/PNG/WebP", _IMAGENS),
    "imagem": Politica("imagem", _IMAGENS, limites.IMAGEM_UPLOAD_BYTES_MAX,
                       "logotipo/miniatura/avatar enviados como arquivo", _IMAGENS),
    "csv": Politica("csv", frozenset({"text/csv", "text/plain"}), limites.ANEXO_BYTES_MAX, "tabela CSV/texto"),
}


def politica(classe: str) -> Politica:
    return POLITICAS.get(classe, POLITICAS["objeto"])


def conferir_tipo_na_rota(classe: str, content_type: str) -> Politica:
    """Content-Type declarado fora da lista da classe → `ConteudoRecusado` antes de ler um byte do corpo."""
    p = politica(classe)
    declarado = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if declarado not in p.tipos:
        raise ConteudoRecusado(Resultado(
            False, f"tipo {declarado} não permitido na classe {p.nome} (aceitos: {', '.join(sorted(p.tipos))})",
            "não lido", "politica_de_rota",
        ))
    return p


def pos_processar(dados: bytes, content_type: str) -> bytes:
    """Sobre o arquivo INTEIRO (só cabe quando ele coube no buffer único): SVG sai sanitizado (sem script,
    foreignObject, handlers, href externo); zip/kmz passam pelas regras de zip-bomba de `conferir_zip`
    (entradas, tamanho descomprimido, razão, caminho). Devolve os bytes a gravar (o SVG pode mudar)."""
    from app import svg_seguro

    declarado = (content_type or "").split(";")[0].strip().lower()
    if declarado == "image/svg+xml":
        try:
            return svg_seguro.sanitizar(dados)
        except svg_seguro.SVGInvalido as e:
            raise ConteudoRecusado(Resultado(False, str(e), "image/svg+xml", "svg_seguro")) from e
    if declarado in ("application/zip", "application/vnd.google-earth.kmz"):
        try:
            conferir_zip(dados)
        except ZipSuspeito as e:
            raise ConteudoRecusado(Resultado(False, f"zip suspeito: {e}", "application/zip", "zip_bomba")) from e
    return dados


def propriedades_da_recusa(e: ConteudoRecusado, classe: str, content_type: str, dados: bytes | None) -> dict:
    """o que vai para a trilha (`arquivos/conteudo_recusado` ou `arquivos/quarentena`): nunca o conteúdo."""
    r = e.resultado
    props = {
        "classe": classe, "content_type": content_type, "motor": r.motor, "motivo": r.motivo,
        "tipo_detectado": r.tipo_detectado, "bytes": len(dados) if dados is not None else None,
    }
    if r.virus:
        props["assinatura"] = r.virus
    if dados:
        props["sha256"] = hashlib.sha256(dados).hexdigest()
    return props


def tipo_do_evento(e: ConteudoRecusado) -> str:
    return "arquivos/quarentena" if e.resultado.virus else "arquivos/conteudo_recusado"

