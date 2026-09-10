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

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Protocol

import magic

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
    `.permitido` toda vez, e quem quer registrar o tipo detectado no evento ainda tem o valor."""
    r = MOTOR_ATIVO.escanear(cabecalho, content_type_declarado)
    if not r.permitido:
        raise ConteudoRecusado(r)
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
