"""Camada de varredura de conteúdo em upload (item L7-03-b-antivirus-anexos; docs/SEGURANCA.md §8): cobre
o caminho de `POST /api/arquivos` (L0-11-arquivos-objetos) e o de `POST /api/itens/{id}/miniatura`
(L0-03-catalogo) — os dois aceitavam qualquer byte sob o `Content-Type` que o cliente escolhesse, sem conferir
se o CONTEÚDO bate com o que foi declarado (a extensão/`Content-Type` é escolha do remetente; os bytes não).

**Estado desta camada em 06/09/2026**: a primeira versão comparava só "família declarada × tipo devolvido pelo
`libmagic`" e foi REFUTADA por adversário independente (laço, handoff T3, achados 22-25): (a) um arquivo que
COMEÇA com assinatura de imagem válida e carrega script depois recebia do `libmagic` exatamente a família
declarada, então passava; (b) `Content-Type` fora da tabela devolvia `None` (= "sem família fixa") e isso
significava "não examinar", ou seja, quem escolhia se a varredura rodava era o remetente; (c) só os primeiros
8 KiB eram olhados; (d) zip/kmz não era aberto. Esta versão fecha os quatro, sem ClamAV (§8.1 de
docs/SEGURANCA.md e D21) e sem nenhuma regra que dependa de sorte.

Ordem das checagens (a primeira que recusar decide, e a mensagem diz qual foi):

1. **família declarada × tipo real** (o que já existia): declarado `image/jpeg` com bytes de script → recusa.
2. **lista de NEGAÇÃO determinística, que vale para QUALQUER `Content-Type` declarado** — inclusive genérico
   (`application/octet-stream`), vazio e desconhecido: shebang no início, assinatura de executável CONFERIDA À
   MÃO e tipo real de script/HTML quando os bytes são texto de verdade. Tipo declarado fora da tabela deixou
   de ser "não examinar" e passou a ser o rigor máximo: sem família para comparar, valem todas as outras
   checagens.
3. **carga executável no CORPO INTEIRO** (não só no cabeçalho): busca de padrão literal (`<script`, `<?php`,
   `#!/bin/`, ...) em tudo que o chamador entregar, com emenda entre blocos no caminho multipart
   (`escanear_continuacao`). É o que pega o polyglot "imagem válida + script colado depois" e a carga além
   dos 8 KiB.
4. **integridade estrutural de imagem**: PNG termina no chunk `IEND`, JPEG no marcador `FFD9`, GIF no byte
   `0x3B`. Byte depois do fim declarado do formato = recusa. Só há veredito quando o fim é POSITIVAMENTE
   identificado: arquivo truncado/não reconhecido não é acusado por esta regra (as outras continuam valendo).
5. **contêiner composto**: zip/kmz é aberto na lista de entradas; entrada com extensão de script/executável,
   ou cujo conteúdo comece com shebang, recusa o pacote inteiro.

**Por que a lista de negação NÃO confia no rótulo do `libmagic` para binário** (a armadilha que já derrubou a
primeira versão da regra): MEDIDO nesta máquina, `libmagic` classifica ~0,9% (18/2000) de bytes PURAMENTE
ALEATÓRIOS como algo diferente de `application/octet-stream`, às vezes `application/x-dosexec`. Recusar pelo
rótulo faria o upload binário legítimo (`os.urandom` da própria suíte, CAD e dado proprietário do cliente)
reprovar às vezes — o oposto de P5 (reprodutível). Por isso:

* família de EXECUTÁVEL só é recusada quando a assinatura mágica real está no início dos bytes (`\\x7fELF`,
  `MZ` **com o cabeçalho `PE\\0\\0` no deslocamento que o próprio arquivo declara em 0x3C**, Mach-O, Wasm,
  Dalvik) — leitura determinística, não palpite;
* família de SCRIPT/HTML só é recusada quando os bytes são texto de verdade (`_e_texto`: sem byte nulo e
  decodificável em UTF-8, ou 99% de caractere ASCII imprimível) — 4 KiB aleatórios não passam nessa porta;
* todo padrão da busca de carga tem 5 bytes ou mais, para que a chance de aparecer por acaso em conteúdo
  aleatório seja desprezível (o padrão mais curto, `<?php`, tem probabilidade da ordem de 3e-8 por amostra de
  4 KiB; o teste `test_binario_generico_aleatorio_nunca_e_recusado_por_assinatura` roda 200 amostras).

**Por que não é ClamAV ainda (D21)**: MEDIDO em 06/09/2026, `df -h /` = 12-13 GiB livres num disco a 98% e
`free -h` = 323 MiB livres com o swap (8 GiB) cheio; o `clamd` mantém a base de assinaturas (1,3-1,5 GiB)
residente em RAM e repetiria o incidente de OOM já registrado na casa. O gancho continua pronto:
`escanear_cabecalho()` é a única função que os chamadores conhecem, e trocar de motor é implementar um `Motor`
novo com a mesma assinatura e apontar `MOTOR_ATIVO`.

**Limite honesto do que é varrido**: a varredura só enxerga o que o chamador entrega. `POST /api/arquivos`
entrega o corpo inteiro quando ele cabe em uma parte (até `limites.ARQUIVO_BUFFER_UNICO_BYTES`, 8 MiB) e, acima
disso, entrega parte por parte (8 MiB de cada vez, com emenda de `CAUDA_BYTES` entre elas) — nenhum arquivo é
carregado inteiro em RAM. As checagens 1, 2, 4 e 5 valem sobre a PRIMEIRA parte (é onde estão cabeçalho e, no
zip, o diretório central quando o pacote cabe numa parte só); a checagem 3 vale sobre o corpo inteiro."""

from __future__ import annotations

import hashlib
import io
import re
import socket
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Protocol

import magic

from app import limites
from app.ingestao.formatos import ZipSuspeito, conferir_zip

CABECALHO_BYTES = 8192  # o bastante para o libmagic decidir o tipo; nunca lê o arquivo inteiro para isso
AMOSTRA_TEXTO_BYTES = 4096  # quanto `_e_texto` olha para decidir se os bytes são texto de verdade
CAUDA_BYTES = 32  # emenda entre blocos no caminho multipart (o padrão mais longo tem 14 bytes)
ZIP_ENTRADAS_MAX = 5000  # teto de entradas examinadas num zip/kmz (nunca varre pacote sem limite)
ZIP_BYTES_POR_ENTRADA = 512  # quanto se lê de cada entrada só para ver se começa com shebang

# --- família de tipo real aceitável por Content-Type declarado (mesmas chaves de app/objetos.EXTENSOES).
# `None` = sem família fixa (declarado genérico, `application/octet-stream`): a comparação declarado × detectado
# não se aplica, mas TODAS as outras checagens continuam valendo. Content-Type fora desta tabela (desconhecido,
# inventado ou vazio) recebe o mesmo tratamento do genérico — nunca "não examinar".
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

# --- tipo REAL que nunca é aceito, seja qual for o Content-Type declarado. Só vale quando os bytes são texto
# (`_e_texto`), porque é assim que a regra fica determinística diante de binário aleatório.
TIPOS_REAIS_DE_SCRIPT = frozenset({
    "text/x-shellscript", "application/x-shellscript", "text/x-sh", "application/x-sh",
    "text/x-perl", "application/x-perl", "text/x-python", "text/x-script.python", "application/x-python-code",
    "text/x-php", "application/x-php", "text/x-ruby", "application/x-ruby", "text/x-lua",
    "text/x-msdos-batch", "text/x-tcl", "application/x-csh", "text/x-awk", "text/x-nawk", "text/x-gawk",
    "text/html", "application/xhtml+xml", "image/svg+xml",
    "text/javascript", "application/javascript", "application/x-javascript", "text/vbscript",
})

# --- assinatura mágica de executável conferida À MÃO no início dos bytes (determinístico; o rótulo do libmagic
# não basta, ver o docstring do módulo)
_MACH_O = (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")

# --- extensão de entrada que nunca pode viajar dentro de um zip/kmz aceito por esta camada
EXTENSOES_EXECUTAVEIS_EM_ZIP = frozenset({
    "sh", "bash", "zsh", "ksh", "csh", "command", "run",
    "php", "phtml", "php5", "py", "pyc", "pyo", "pl", "pm", "rb", "lua", "tcl", "awk",
    "exe", "dll", "so", "dylib", "bat", "cmd", "com", "scr", "msi", "msp", "jar", "apk",
    "vbs", "vbe", "js", "jse", "wsf", "wsh", "ps1", "psm1", "reg", "hta", "cpl", "deb", "rpm",
})

# --- carga executável procurada no CORPO INTEIRO. Todo padrão tem 5 bytes ou mais de propósito: com menos, a
# chance de aparecer por acaso em conteúdo binário legítimo deixa de ser desprezível e o teste vira sorteio.
CARGA = re.compile(rb"<script|<iframe|<\?php|<!doctype\s+html|#!/bin/|#!/usr/", re.IGNORECASE)


@dataclass(frozen=True)
class Resultado:
    permitido: bool
    motivo: str | None
    tipo_detectado: str
    motor: str
    virus: str | None = None  # nome da assinatura quando o antivírus recusa (item L7-03-a)


class Motor(Protocol):
    """Interface que qualquer motor de varredura implementa (o gancho para trocar por ClamAV, D21)."""

    nome: str

    def escanear(self, corpo: bytes, content_type_declarado: str) -> Resultado: ...


# ---------------------------------------------------------------- checagens determinísticas (funções puras)
def _e_texto(dados: bytes) -> bool:
    """Os bytes são texto de verdade? Porta de determinismo das regras de script/HTML: 4 KiB aleatórios têm byte
    nulo com probabilidade praticamente 1, não decodificam em UTF-8 e só ~38% deles são ASCII imprimível."""
    amostra = dados[:AMOSTRA_TEXTO_BYTES]
    if not amostra or b"\x00" in amostra:
        return False
    for corte in range(4):  # o corte da amostra pode cair no meio de um caractere multibyte
        fim = len(amostra) - corte
        if fim <= 0:
            break
        try:
            amostra[:fim].decode("utf-8")
            return True
        except UnicodeDecodeError:
            continue
    imprimiveis = sum(1 for c in amostra if c in (9, 10, 13) or 32 <= c <= 126)
    return imprimiveis >= len(amostra) * 0.99


def _shebang(dados: bytes) -> bool:
    """`#!` seguido de um caminho ASCII plausível na primeira linha (nunca só os dois bytes `#!`, que aparecem
    por acaso em 1 de cada 65 mil blocos aleatórios)."""
    if dados[:2] != b"#!":
        return False
    linha = dados[2 : 2 + 128].split(b"\n", 1)[0].strip()
    return len(linha) >= 4 and linha.startswith(b"/") and all(32 <= c <= 126 for c in linha)


def _assinatura_executavel(dados: bytes) -> str | None:
    """Nome da família de executável quando a assinatura mágica REAL está no início dos bytes; `None` se não."""
    if dados[:4] == b"\x7fELF":
        return "executável ELF"
    if dados[:4] in _MACH_O:
        return "executável Mach-O"
    if dados[:4] == b"\xca\xfe\xba\xbe":
        return "binário universal Mach-O / classe Java"
    if dados[:4] == b"\x00asm":
        return "módulo WebAssembly"
    if dados[:4] == b"dex\n":
        return "executável Dalvik"
    if dados[:2] == b"MZ" and len(dados) >= 0x40:
        # DOS/Windows: o próprio arquivo diz em 0x3C onde começa o cabeçalho PE. Exigir o `PE\0\0` ali torna a
        # checagem determinística (dois bytes `MZ` sozinhos aparecem por acaso em binário aleatório).
        deslocamento = int.from_bytes(dados[0x3C:0x40], "little")
        if 0 < deslocamento <= len(dados) - 4 and dados[deslocamento : deslocamento + 4] == b"PE\x00\x00":
            return "executável PE (Windows)"
    return None


def _pula_subblocos(dados: bytes, pos: int) -> int | None:
    """GIF: cadeia de sub-blocos `<tamanho><dados>` terminada por um byte 0. `None` = acabou antes do fim."""
    while pos < len(dados):
        n = dados[pos]
        if n == 0:
            return pos + 1
        pos += 1 + n
    return None


def _fim_gif(dados: bytes) -> int | None:
    if dados[:6] not in (b"GIF87a", b"GIF89a") or len(dados) < 13:
        return None
    flags = dados[10]
    pos = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    while pos < len(dados):
        bloco = dados[pos]
        if bloco == 0x3B:  # trailer: fim do GIF
            return pos + 1
        if bloco == 0x21:  # bloco de extensão: rótulo + sub-blocos
            seguinte = _pula_subblocos(dados, pos + 2)
        elif bloco == 0x2C:  # descritor de imagem
            if pos + 10 > len(dados):
                return None
            flags_locais = dados[pos + 9]
            inicio = pos + 10 + (3 * 2 ** ((flags_locais & 7) + 1) if flags_locais & 0x80 else 0)
            seguinte = _pula_subblocos(dados, inicio + 1)  # +1 = tamanho mínimo do código LZW
        else:
            return None
        if seguinte is None:
            return None
        pos = seguinte
    return None


def _fim_png(dados: bytes) -> int | None:
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    while pos + 8 <= len(dados):
        tamanho = int.from_bytes(dados[pos : pos + 4], "big")
        tipo = dados[pos + 4 : pos + 8]
        if not tipo.isalpha():
            return None  # estrutura não reconhecida: esta regra não dá veredito
        fim = pos + 12 + tamanho
        if fim > len(dados):
            return None  # truncado
        if tipo == b"IEND":
            return fim
        pos = fim
    return None


def _fim_jpeg(dados: bytes) -> int | None:
    if dados[:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos + 1 < len(dados):
        if dados[pos] != 0xFF:
            return None
        marcador = dados[pos + 1]
        if marcador == 0xFF:  # preenchimento entre marcadores
            pos += 1
            continue
        if marcador == 0xD9:  # EOI: fim do JPEG
            return pos + 2
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD8:  # marcadores sem carga
            pos += 2
            continue
        if pos + 4 > len(dados):
            return None
        tamanho = int.from_bytes(dados[pos + 2 : pos + 4], "big")
        if tamanho < 2:
            return None
        pos += 2 + tamanho
        if marcador == 0xDA:  # SOS: dado comprimido até o próximo marcador que não seja RST nem `FF00`
            while True:  # `find` salta de 0xFF em 0xFF: varrer byte a byte em Python custaria segundos num JPEG
                indice = dados.find(b"\xff", pos)
                if indice == -1 or indice + 1 >= len(dados):
                    return None
                seguinte = dados[indice + 1]
                if seguinte != 0x00 and not (0xD0 <= seguinte <= 0xD7):
                    pos = indice
                    break
                pos = indice + 2
    return None


def _sobra_depois_da_imagem(dados: bytes) -> str | None:
    """Motivo da recusa quando existe byte DEPOIS do fim positivamente identificado do formato de imagem."""
    for rotulo, fim in (("PNG", _fim_png(dados)), ("JPEG", _fim_jpeg(dados)), ("GIF", _fim_gif(dados))):
        if fim is not None and fim < len(dados):
            return (
                f"imagem {rotulo} com {len(dados) - fim} byte(s) depois do fim do formato (arquivo disfarçado: "
                f"a imagem termina no deslocamento {fim} e o arquivo continua)"
            )
    return None


def _entrada_perigosa_no_zip(dados: bytes) -> str | None:
    """Abre a lista de entradas do zip/kmz e devolve o motivo quando alguma é script/executável."""
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for nome in z.namelist()[:ZIP_ENTRADAS_MAX]:
                base = nome.rsplit("/", 1)[-1].lower()
                extensao = base.rsplit(".", 1)[-1] if "." in base else ""
                if extensao in EXTENSOES_EXECUTAVEIS_EM_ZIP:
                    return f"o pacote contém a entrada '{nome}', de extensão executável/script (.{extensao})"
                info = z.getinfo(nome)
                if info.is_dir() or info.file_size == 0:
                    continue
                with z.open(nome) as f:
                    inicio = f.read(ZIP_BYTES_POR_ENTRADA)
                if _shebang(inicio):
                    return f"o pacote contém a entrada '{nome}', cujo conteúdo começa com shebang (#!)"
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, ValueError, EOFError):
        # zip truncado (1ª parte de um envio grande), cifrado ou fora do padrão: esta regra não dá veredito;
        # as outras checagens já rodaram sobre os mesmos bytes
        return None
    return None


# ---------------------------------------------------------------- motor
class MotorAssinaturaBasica:
    """Motor desta passagem: assinatura mágica + família declarada × detectada + lista de negação determinística
    + integridade estrutural de imagem + lista de entradas do zip (sem daemon, sem RAM extra)."""

    nome = "assinatura_basica"

    def __init__(self) -> None:
        self._magic = magic.Magic(mime=True)

    def escanear(self, corpo: bytes, content_type_declarado: str) -> Resultado:
        if not corpo:
            return Resultado(False, "conteúdo vazio", "vazio", self.nome)
        tipo_real = self._magic.from_buffer(corpo[:CABECALHO_BYTES]).split(";")[0].strip()
        declarado = (content_type_declarado or "application/octet-stream").split(";")[0].strip().lower()

        # 1. família declarada × tipo real (só quando o declarado tem família fixa nesta instalação)
        familia = TIPOS_PERMITIDOS.get(declarado)
        if familia is not None and tipo_real not in familia:
            return self._recusa(
                f"conteúdo real ({tipo_real}) não bate com o Content-Type declarado ({declarado})", tipo_real
            )

        # 2. lista de negação: vale para QUALQUER declarado, inclusive genérico, vazio e desconhecido
        if _shebang(corpo):
            return self._recusa("conteúdo é um script (começa com shebang #!)", tipo_real)
        familia_executavel = _assinatura_executavel(corpo)
        if familia_executavel is not None:
            return self._recusa(f"conteúdo é um {familia_executavel} (assinatura mágica no início)", tipo_real)
        if tipo_real in TIPOS_REAIS_DE_SCRIPT and _e_texto(corpo):
            return self._recusa(f"conteúdo é de um tipo executável em navegador ou máquina ({tipo_real})", tipo_real)

        # 3. carga executável em qualquer ponto do corpo entregue
        achado = CARGA.search(corpo)
        if achado is not None:
            return self._recusa(
                f"carga executável embutida no conteúdo (padrão {achado.group(0)!r} no deslocamento "
                f"{achado.start()})",
                tipo_real,
            )

        # 4. imagem com byte depois do fim do formato (o polyglot "imagem válida + script colado")
        sobra = _sobra_depois_da_imagem(corpo)
        if sobra is not None:
            return self._recusa(sobra, tipo_real)

        # 5. contêiner composto: lista de entradas do zip/kmz
        if tipo_real == "application/zip":
            entrada = _entrada_perigosa_no_zip(corpo)
            if entrada is not None:
                return self._recusa(entrada, tipo_real)

        return Resultado(True, None, tipo_real, self.nome)

    def _recusa(self, motivo: str, tipo_real: str) -> Resultado:
        return Resultado(False, motivo, tipo_real, self.nome)


MOTOR_ATIVO: Motor = MotorAssinaturaBasica()


class ClamdIndisponivel(RuntimeError):
    """clamd configurado (PLAT_CLAMD) mas fora do ar: o upload é RECUSADO (nunca passa sem varrer)."""


class MotorClamd:
    """Antivírus ClamAV por `clamd` (item L7-03-a-antivirus-upload): protocolo INSTREAM sobre socket unix ou
    TCP, biblioteca padrão só (nenhuma dependência nova). Manda até `limites.CLAMD_MAX_BYTES` (o
    StreamMaxLength padrão do daemon); resposta `stream: OK` aceita, `stream: <assinatura> FOUND` recusa com o
    nome da assinatura. OPCIONAL na instalação (custa ~1,3 GiB de RAM de assinaturas; D21 — o appliance desta
    máquina não cabe): só entra na cadeia quando `PLAT_CLAMD` está definido — e aí clamd fora do ar recusa o
    upload em vez de deixar passar."""

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

    def escanear(self, corpo: bytes, content_type_declarado: str) -> Resultado:
        dados = corpo[: limites.CLAMD_MAX_BYTES]
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
    """`MotorClamd` quando `PLAT_CLAMD` está definido; senão `None` (só a assinatura básica acima)."""
    endereco = endereco_clamd()
    return MotorClamd(endereco) if endereco else None


class ConteudoRecusado(ValueError):
    """Levantada por `escanear_cabecalho()`/`escanear_continuacao()` quando o motor ativo recusa; quem chama
    decide o código HTTP (415 nas rotas de upload, mesmo padrão de `objetos.CotaExcedida` → 413)."""

    def __init__(self, resultado: Resultado) -> None:
        super().__init__(resultado.motivo)
        self.resultado = resultado


def escanear_cabecalho(cabecalho: bytes, content_type_declarado: str) -> Resultado:
    """Varre o primeiro bloco entregue pelo chamador (o corpo inteiro, quando ele cabe numa parte só). Levanta
    `ConteudoRecusado` quando o motor ativo recusa; devolve o `Resultado` (sempre `permitido=True` quando não
    levanta) quando aceita — assim o chamador que só quer o efeito colateral (recusar) não precisa conferir
    `.permitido` toda vez, e quem quer registrar o tipo detectado no evento ainda tem o valor. Quando `PLAT_CLAMD`
    está configurado (item L7-03-a-antivirus-upload), o antivírus roda DEPOIS da assinatura básica passar — nunca
    substitui a checagem determinística acima, só soma outra: `clamd` fora do ar recusa (nunca "passa sem varrer")."""
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


def escanear_continuacao(bloco: bytes, cauda_anterior: bytes = b"") -> bytes:
    """Varre um bloco SEGUINTE do mesmo envio (caminho multipart): só a busca de carga executável, porque
    cabeçalho, assinatura e estrutura já foram decididos na primeira parte. `cauda_anterior` são os últimos
    `CAUDA_BYTES` do bloco anterior, para que um padrão partido na emenda entre partes não escape. Devolve a
    cauda deste bloco, para a chamada seguinte; levanta `ConteudoRecusado` quando encontra carga."""
    achado = CARGA.search(cauda_anterior + bloco)
    if achado is not None:
        raise ConteudoRecusado(
            Resultado(
                False,
                f"carga executável embutida no conteúdo, depois do início do arquivo (padrão "
                f"{achado.group(0)!r})",
                "corpo_alem_do_cabecalho",
                MOTOR_ATIVO.nome,
            )
        )
    return bloco[-CAUDA_BYTES:]


def cauda(bloco: bytes) -> bytes:
    """Últimos `CAUDA_BYTES` de um bloco já varrido, para emendar com o próximo (ver `escanear_continuacao`)."""
    return bloco[-CAUDA_BYTES:]


# --------------------------------------------------------------------------- pipeline único (item
# L7-03-a-antivirus-upload; docs/SEGURANCA.md §9): política de Content-Type e teto DECLARADA por classe de
# upload, conferida ANTES de ler o corpo (`POST /api/arquivos?classe=`), e pós-processamento do que só se decide
# com o arquivo inteiro (SVG sanitizado, zip-bomba). A checagem "bytes provam o tipo" acima (`escanear_cabecalho`,
# item L7-03-b) continua valendo sempre — a política aqui é a CAMADA DE CIMA, que restringe quais tipos cada
# classe aceita e corta o teto de tamanho por classe (`limites.ANEXO_BYTES_MAX`/`IMAGEM_UPLOAD_BYTES_MAX`).
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
    # `tipos` vazio = SEM lista de rota: quem decide é só a assinatura básica do §8 (`escanear_cabecalho`),
    # exatamente como já era antes deste item — `application/octet-stream`, `text/plain` ou qualquer
    # Content-Type sem família fixa em `TIPOS_PERMITIDOS` passa para o byte-scan em vez de recusar de cara.
    # Restringir "objeto" a `TIPOS_PERMITIDOS` quebrava todo chamador de L0-11 que manda binário/texto
    # genérico sob uma classe própria (`tests/api/test_arquivos.py`, `test_arquivos_entrega.py`) — a lista
    # fixa é só para as classes NOVAS abaixo, desenhadas para um uso mais estreito de propósito.
    "objeto": Politica("objeto", frozenset(), limites.ARQUIVO_BYTES_MAX,
                       "arquivo bruto do inquilino: sem lista de tipos por rota, decide tudo a assinatura "
                       "básica do §8 (qualquer Content-Type, inclusive binário genérico)", _IMAGENS),
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
    """Content-Type declarado fora da lista da classe → `ConteudoRecusado` antes de ler um byte do corpo.
    `p.tipos` vazio (classe `objeto`) = sem lista nesta camada, o byte-scan do §8 decide sozinho."""
    p = politica(classe)
    if not p.tipos:
        return p
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
