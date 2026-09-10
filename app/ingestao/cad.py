"""Leitura de arquivo CAD de terceiro — DXF e DWG (item L0-04-e).

Duas metades, como no ADR 0015 (validação raster) e pelo mesmo motivo: **o arquivo é do cliente**.

* o **pai** (este módulo, no processo do worker) só olha bytes com `open()` puro: assinatura de formato, versão
  do DWG, e a seção HEADER do DXF (unidade, codepage, extensão) com leitura LIMITADA a `HEADER_MAX`. Nunca abre
  o arquivo com GDAL nem com ezdxf;
* o **filho** é o `ogrinfo`/`ogr2ogr`/`dwg2dxf`, lançado por `app.ingestao.isolamento.executar`: seccomp que
  fecha `socket(AF_INET/AF_INET6)`, `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_NOFILE`/`RLIMIT_CORE=0`, relógio de parede
  com `killpg`, ambiente do GDAL sem driver HTTP, sem PROJ na rede, sem varredura de diretório e sem PAM.

Decisões MEDIDAS nesta máquina (GDAL 3.8.4, `tests/medidas/L0-04-e-formatos-cad.json`):

* **bloco aninhado não precisa de ezdxf.** O driver DXF do GDAL resolve bloco dentro de bloco: um INSERT de
  `CONJUNTO_ILUMINACAO`, que por sua vez insere dois `POSTE`, sai como uma `GEOMETRYCOLLECTION` com toda a
  geometria já transladada. Logo `ezdxf` fica FORA da aplicação (entra só no gerador de arquivo de teste,
  `tests/dados/cad/gerar.py`), como a hipótese do item admitia.
* **`DXF_INLINE_BLOCKS` e `DXF_ENCODING` são opção de CONFIGURAÇÃO (`--config`), não de abertura (`-oo`).**
  Medido: com `-oo DXF_ENCODING=UTF-8` o nome de camada acentuado continua saindo trocado; com
  `--config DXF_ENCODING UTF-8` sai certo.
* **DXF mente sobre a própria codificação.** O arquivo de teste declara `$DWGCODEPAGE ANSI_1252` no cabeçalho e
  grava os nomes de camada em UTF-8. Por isso a codificação é DECIDIDA pelos bytes (se a parte não-ASCII do
  arquivo é UTF-8 válida, é UTF-8) e o cabeçalho vira segunda opinião, registrada na proposta.
* **DXF binário o GDAL não lê.** É recusado pela sentinela de 22 bytes, com mensagem própria — não como
  "arquivo corrompido".

O que NÃO se faz aqui: assumir CRS. DXF quase nunca traz projeção; sem resposta do usuário a importação fica
`pendente` (mesma regra do ADR 0015 seção 4). A conversão de coordenada de desenho para coordenada de terreno
por 2-4 pontos de controle está em `app/ingestao/georreferencia.py`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.ingestao import isolamento

VERSAO = 1

HEADER_MAX = 2 * 1024 * 1024      # a seção HEADER do DXF fica no começo; lemos no máximo isto para achá-la
ENTIDADES_MAX = 2_000_000         # teto de entidades por arquivo (o adversário manda 2 milhões)
CAMADAS_MAX = 5_000               # nº de camadas distintas no desenho
TAMANHO_MAX = 2 * 1024 * 1024 * 1024
SENTINELA_BINARIO = b"AutoCAD Binary DXF\r\n\x1a\x00"
CONVERSOR_PADRAO = "/opt/plat/libredwg/bin/dwg2dxf"
CONVERSOR_LIB_PADRAO = "/opt/plat/libredwg/lib"

# cabeçalho do DWG (6 bytes) → versão comercial. Fonte: formato público do DWG, o mesmo mapa do LibreDWG.
VERSOES_DWG = {
    "AC1.40": "R1.4", "AC1.50": "R2.05", "AC2.10": "R2.10", "AC1002": "R2.5", "AC1003": "R2.6",
    "AC1004": "R9", "AC1006": "R10", "AC1009": "R11/R12", "AC1012": "R13", "AC1014": "R14",
    "AC1015": "R2000", "AC1018": "R2004", "AC1021": "R2007", "AC1024": "R2010", "AC1027": "R2013",
    "AC1032": "R2018",
}
# $ACADVER do DXF → versão comercial
VERSOES_DXF = {"AC1006": "R10", "AC1009": "R11/R12", "AC1012": "R13", "AC1014": "R14", "AC1015": "R2000",
               "AC1018": "R2004", "AC1021": "R2007", "AC1024": "R2010", "AC1027": "R2013", "AC1032": "R2018"}

# $INSUNITS (código 70 do cabeçalho) → (nome, metros por unidade). 0 = não declarada: PERGUNTAR.
UNIDADES = {
    0: ("não declarada", None), 1: ("polegada", 0.0254), 2: ("pé", 0.3048), 3: ("milha", 1609.344),
    4: ("milímetro", 0.001), 5: ("centímetro", 0.01), 6: ("metro", 1.0), 7: ("quilômetro", 1000.0),
    8: ("micropolegada", 0.0000000254), 9: ("mil (milésimo de polegada)", 0.0000254), 10: ("jarda", 0.9144),
    11: ("ångström", 1e-10), 12: ("nanômetro", 1e-9), 13: ("micrômetro", 1e-6), 14: ("decímetro", 0.1),
    15: ("decâmetro", 10.0), 16: ("hectômetro", 100.0), 17: ("gigâmetro", 1e9),
    18: ("unidade astronômica", 1.495978707e11),
    19: ("ano-luz", 9.4607304725808e15), 20: ("parsec", 3.0856775814913673e16),
}

# nome da subclasse do GDAL → família que a tela mostra separada (cotas, textos e hachuras separados)
_FAMILIAS = (
    ("cotas", ("AcDbDimension", "AcDbAlignedDimension", "AcDbRotatedDimension", "AcDb2LineAngularDimension",
               "AcDb3PointAngularDimension", "AcDbDiametricDimension", "AcDbRadialDimension",
               "AcDbOrdinateDimension", "AcDbArcDimension")),
    ("textos", ("AcDbText", "AcDbMText", "AcDbAttribute", "AcDbAttributeDefinition")),
    ("hachuras", ("AcDbHatch",)),
    ("blocos", ("AcDbBlockReference", "AcDbMInsertBlock")),
)


class ArquivoRecusado(ValueError):
    """Defeito do arquivo enviado, com mensagem pronta para o usuário (português, sem caminho absoluto)."""


@dataclass
class Relatorio:
    """Resultado da leitura. `estado` segue o vocabulário do ADR 0015: recusado (defeito), pendente (falta
    resposta do usuário) ou aceito."""

    estado: str = "aceito"
    formato: str = ""
    versao: str | None = None
    unidade: dict = field(default_factory=dict)
    codificacao: dict = field(default_factory=dict)
    camadas: list = field(default_factory=list)
    totais: dict = field(default_factory=dict)
    blocos: list = field(default_factory=list)
    tipos_geometria: dict = field(default_factory=dict)
    extensao: list | None = None
    problemas: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    conversao: dict | None = None
    isolamento: dict = field(default_factory=dict)
    caminho_dxf: str | None = None

    def json(self) -> dict:
        d = dict(self.__dict__)
        d["versao_leitor"] = VERSAO
        d.pop("caminho_dxf", None)
        return d


# ========================================================================================= assinatura
def sem_caminho(texto: str) -> str:
    """Troca caminho absoluto por nome de arquivo: o usuário vê `planta.dxf`, nunca o diretório do worker.
    Mesma regra do ADR 0015 seção 7."""
    return re.sub(r"(?:/[\w.\-+@]+){2,}", lambda m: os.path.basename(m.group(0)), texto or "")


def assinatura(dados: bytes) -> str:
    """`dxf`, `dxf_binario`, `dwg` ou `desconhecido`, decidido pelos BYTES (nunca pela extensão)."""
    if dados.startswith(SENTINELA_BINARIO):
        return "dxf_binario"
    if len(dados) >= 6 and dados[:2] == b"AC" and dados[:6].decode("latin-1", "replace") in VERSOES_DWG:
        return "dwg"
    inicio = dados[:4096].lstrip(b"\r\n\t ")
    if re.match(rb"^0\s*[\r\n]+\s*SECTION", inicio) or re.search(rb"[\r\n]\s*999\s*[\r\n]", dados[:4096]):
        return "dxf"
    if b"SECTION" in dados[:4096] and b"HEADER" in dados[:8192]:
        return "dxf"
    return "desconhecido"


def versao_dwg(dados: bytes) -> tuple[str, str]:
    """(cabeçalho de 6 bytes, versão comercial). Versão desconhecida devolve o cabeçalho literal."""
    cab = dados[:6].decode("latin-1", "replace")
    return cab, VERSOES_DWG.get(cab, "desconhecida")


# ========================================================================================= cabeçalho DXF
_RE_VAR = re.compile(r"^\s*9\s*\r?\n\s*(\$[A-Z0-9_]+)\s*\r?\n", re.M)


def cabecalho_dxf(caminho: str | os.PathLike) -> dict:
    """Lê `$ACADVER`, `$DWGCODEPAGE`, `$INSUNITS`, `$EXTMIN`/`$EXTMAX` da seção HEADER, com leitura limitada a
    `HEADER_MAX` bytes do começo do arquivo. Não usa GDAL: é texto, e a seção HEADER é a primeira do DXF."""
    with open(caminho, "rb") as fh:
        bruto = fh.read(HEADER_MAX)
    utf8_valido = True
    try:
        bruto.decode("utf-8")
    except UnicodeDecodeError:
        utf8_valido = False
    texto = bruto.decode("utf-8" if utf8_valido else "cp1252", "replace")
    fim = texto.find("ENDSEC")
    corpo = texto[: fim if fim > 0 else len(texto)]
    valores: dict[str, list[str]] = {}
    for m in _RE_VAR.finditer(corpo):
        nome = m.group(1)
        resto = corpo[m.end():].splitlines()
        # cada variável é uma sequência (código, valor); guardamos os valores até a próxima variável (código 9)
        vals, i = [], 0
        while i + 1 < len(resto) and resto[i].strip() != "9" and len(vals) < 8:
            vals.append(resto[i + 1].strip())
            i += 2
        valores[nome] = vals
    def num(nome, indice=0):
        try:
            return float(valores[nome][indice])
        except (KeyError, IndexError, ValueError):
            return None
    insunits = num("$INSUNITS")
    extmin = [num("$EXTMIN", 0), num("$EXTMIN", 1)]
    extmax = [num("$EXTMAX", 0), num("$EXTMAX", 1)]
    return {
        "acadver": (valores.get("$ACADVER") or [None])[0],
        "codepage": (valores.get("$DWGCODEPAGE") or [None])[0],
        "insunits": int(insunits) if insunits is not None else None,
        "utf8_valido": utf8_valido,
        "extmin": extmin if all(v is not None for v in extmin) else None,
        "extmax": extmax if all(v is not None for v in extmax) else None,
        "bytes_lidos": len(bruto),
        "truncado": len(bruto) >= HEADER_MAX,
    }


def _codificacao(cab: dict) -> dict:
    """A codificação é DECIDIDA pelos bytes; o `$DWGCODEPAGE` do cabeçalho é segunda opinião. Medido: arquivo
    que declara ANSI_1252 e grava UTF-8 existe e é comum (o gerador do ezdxf faz isso)."""
    declarada = (cab.get("codepage") or "").upper()
    mapa = {"ANSI_1252": "CP1252", "ANSI_1251": "CP1251", "ANSI_1250": "CP1250", "ANSI_874": "CP874",
            "UTF-8": "UTF-8", "UTF8": "UTF-8", "ANSI_936": "CP936", "ANSI_932": "CP932"}
    do_cabecalho = mapa.get(declarada)
    if cab.get("utf8_valido"):
        return {"origem": "bytes", "valor": "UTF-8", "declarada": declarada or None, "perguntar": False,
                "aviso": (f"o cabeçalho declara {declarada} mas os bytes do arquivo são UTF-8 válido; "
                          f"vale o que está no arquivo") if do_cabecalho and do_cabecalho != "UTF-8" else None}
    return {"origem": "cabecalho" if do_cabecalho else "suposicao", "valor": do_cabecalho or "CP1252",
            "declarada": declarada or None, "perguntar": not do_cabecalho, "aviso": None}


# ========================================================================================= cotas no texto
# O driver DXF do GDAL DECOMPÕE a entidade DIMENSION nas linhas e no texto que a desenham: nenhuma feição sai
# com `SubClasses` contendo `AcDbDimension` (MEDIDO: arquivo com 4 DIMENSION sai como 12 AcDbLine + 4 AcDbMText).
# Logo a cota não pode ser contada pelo GDAL. Ela é contada no TEXTO do DXF, que é uma sequência de pares
# (código, valor): código 0 abre a entidade, código 8 dá a camada. Leitura em fluxo, com teto de bytes.
_ENTIDADES_INTERESSE = {"DIMENSION": "cotas", "INSERT": "blocos", "HATCH": "hachuras",
                        "TEXT": "textos", "MTEXT": "textos", "ATTRIB": "textos"}
TEXTO_MAX = 512 * 1024 * 1024


def contar_entidades_no_texto(caminho: str | os.PathLike, codificacao: str = "UTF-8") -> dict:
    """{camada: {familia: n}} lido do texto do DXF, mais `_truncado` quando o teto de bytes foi atingido.
    Só as famílias que o GDAL não devolve fielmente; serve de segunda contagem para as outras."""
    saida: dict[str, dict[str, int]] = {}
    lidos = 0
    truncado = False
    dentro = False
    esperando = None
    with open(caminho, "rb") as fh:
        anterior = None
        for linha_bytes in fh:
            lidos += len(linha_bytes)
            if lidos > TEXTO_MAX:
                truncado = True
                break
            linha = linha_bytes.decode(codificacao, "replace").strip()
            if anterior is None:
                anterior = linha
                continue
            codigo, valor, anterior = anterior, linha, None
            if codigo == "2" and valor == "ENTITIES":
                dentro = True
                continue
            if not dentro:
                continue
            if codigo == "0":
                if valor == "ENDSEC":
                    dentro = False
                esperando = _ENTIDADES_INTERESSE.get(valor)
            elif codigo == "8" and esperando:
                camada = valor or "(sem camada)"
                saida.setdefault(camada, {})[esperando] = saida.setdefault(camada, {}).get(esperando, 0) + 1
                esperando = None
    saida["_truncado"] = truncado  # type: ignore[assignment]
    return saida


# ========================================================================================= DWG → DXF
def conversor() -> str | None:
    """Caminho do `dwg2dxf` (LibreDWG, GPL-3, processo separado — nunca ligado à aplicação). Ordem: variável
    `PLAT_DWG2DXF`, depois `/opt/plat/libredwg/bin/dwg2dxf`, depois o PATH."""
    do_ambiente = os.environ.get("PLAT_DWG2DXF")
    if do_ambiente and os.path.exists(do_ambiente):
        return do_ambiente
    if os.path.exists(CONVERSOR_PADRAO):
        return CONVERSOR_PADRAO
    return shutil.which("dwg2dxf")


def versao_conversor() -> str | None:
    exe = conversor()
    if not exe:
        return None
    r = isolamento.executar([exe, "--version"], raiz=os.path.dirname(exe) or "/", timeout_s=20,
                            ambiente_extra=_ambiente_conversor())
    linhas = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return linhas[0] if linhas else None


def _ambiente_conversor() -> dict[str, str]:
    lib = os.environ.get("PLAT_LIBREDWG_LIB") or CONVERSOR_LIB_PADRAO
    if os.path.isdir(lib):
        anterior = os.environ.get("LD_LIBRARY_PATH", "")
        return {"LD_LIBRARY_PATH": f"{lib}:{anterior}" if anterior else lib}
    return {}


def converter_dwg(caminho: str | os.PathLike, dir_trabalho: str | os.PathLike) -> tuple[str, dict]:
    """DWG → DXF pelo LibreDWG, em processo isolado. Devolve (caminho do DXF, registro da conversão).
    Levanta `ArquivoRecusado` com a VERSÃO do arquivo na mensagem quando o conversor não lê — é a cláusula do
    portão: quem enviou um R2018 precisa saber que o problema é a versão, não o arquivo dele."""
    caminho = Path(isolamento.caminho_dentro(caminho, dir_trabalho))
    with open(caminho, "rb") as fh:
        cabecalho = fh.read(6)
    marca, versao = versao_dwg(cabecalho)
    exe = conversor()
    if not exe:
        raise ArquivoRecusado(
            f"o arquivo é um DWG na versão {versao} ({marca}) e esta instalação não tem o conversor LibreDWG "
            f"(dwg2dxf) instalado; converta para DXF antes de enviar ou instale o conversor")
    alvo = Path(dir_trabalho) / (caminho.stem + "_convertido.dxf")
    r = isolamento.executar([exe, "-y", "-o", str(alvo), str(caminho)], raiz=dir_trabalho,
                            ambiente_extra=_ambiente_conversor())
    versao_exe = None
    linhas_erro = [ln.strip() for ln in (r.stderr or "").splitlines() if ln.strip()]
    registro = {"conversor": os.path.basename(exe), "versao_arquivo": versao, "marca": marca,
                "codigo": r.codigo, "tempo_s": r.tempo_s, "ram_pico_kb": r.ram_pico_kb, "morte": r.morte,
                "bytes_dxf": alvo.stat().st_size if alvo.exists() else 0,
                "avisos": [sem_caminho(ln)[:200] for ln in linhas_erro[:5]]}
    if not r.ok or registro["bytes_dxf"] == 0:
        detalhe = sem_caminho(r.ultima_linha_erro()) or (r.morte or f"código {r.codigo}")
        raise ArquivoRecusado(
            f"o arquivo é um DWG na versão {versao} ({marca}) e o conversor LibreDWG não conseguiu lê-lo: "
            f"{detalhe[:200]}")
    versao_exe = versao_conversor()
    registro["versao_conversor"] = versao_exe
    return str(alvo), registro


# ========================================================================================= contagem
def _sql_contagem(campo_bloco: bool) -> str:
    familias = []
    for nome, subclasses in _FAMILIAS:
        cond = " OR ".join(f"SubClasses LIKE '%{s}%'" for s in subclasses)
        familias.append(f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) AS {nome}")
    extra = ", COUNT(DISTINCT BlockName) AS blocos_distintos" if campo_bloco else ""
    return ("SELECT Layer AS camada, COUNT(*) AS entidades, " + ", ".join(familias) + extra +
            " FROM entities GROUP BY Layer ORDER BY Layer")


def _ler_jsonl(caminho: Path) -> list[dict]:
    saida = []
    with open(caminho, encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                try:
                    saida.append(json.loads(linha).get("properties") or {})
                except ValueError:
                    continue
    return saida


def _config(inline_blocos: bool, codificacao: str) -> list[str]:
    """`DXF_INLINE_BLOCKS` e `DXF_ENCODING` são opção de CONFIGURAÇÃO do GDAL, não de abertura — medido."""
    return ["--config", "DXF_INLINE_BLOCKS", "TRUE" if inline_blocos else "FALSE",
            "--config", "DXF_ENCODING", codificacao]


def contar_por_camada(caminho_dxf: str, dir_trabalho: str | os.PathLike, *, inline_blocos: bool = False,
                      codificacao: str = "UTF-8", timeout_s: int = isolamento.TIMEOUT_S) -> list[dict]:
    """Contagem por camada do DXF, pelo próprio GDAL (`ogr2ogr` + dialeto SQLITE), em processo isolado. É esta
    a contagem que a proposta mostra e que o teste compara com o `ogrinfo`."""
    caminho_dxf = isolamento.caminho_dentro(caminho_dxf, dir_trabalho)
    alvo = Path(dir_trabalho) / "contagem_camadas.jsonl"
    if alvo.exists():
        alvo.unlink()
    argv = ["ogr2ogr", "-f", "GeoJSONSeq", str(alvo), caminho_dxf, *_config(inline_blocos, codificacao),
            "-dialect", "SQLITE", "-sql", _sql_contagem(campo_bloco=not inline_blocos)]
    r = isolamento.executar(argv, raiz=dir_trabalho, timeout_s=timeout_s)
    if not r.ok or not alvo.exists():
        detalhe = sem_caminho(r.ultima_linha_erro()) or (r.morte or f"código {r.codigo}")
        raise ArquivoRecusado(f"o GDAL não conseguiu ler as camadas do desenho: {detalhe[:200]}")
    linhas = _ler_jsonl(alvo)
    camadas = []
    for p in linhas:
        camadas.append({
            "nome": p.get("camada") if p.get("camada") not in (None, "") else "(sem camada)",
            "entidades": int(p.get("entidades") or 0),
            "cotas": int(p.get("cotas") or 0), "textos": int(p.get("textos") or 0),
            "hachuras": int(p.get("hachuras") or 0), "blocos": int(p.get("blocos") or 0),
            "blocos_distintos": int(p.get("blocos_distintos") or 0),
        })
    return camadas


# GeometryType() do dialeto SQLITE devolve o nome em maiúsculas ("LINESTRING", "POINT Z"); o resolvedor de
# geometria da ingestão (app/ingestao/geometria.py) fala em "LineString"/"Point". A tradução é aqui, uma vez.
_TIPOS_OGR = {"POINT": "Point", "MULTIPOINT": "MultiPoint", "LINESTRING": "LineString",
              "MULTILINESTRING": "MultiLineString", "POLYGON": "Polygon", "MULTIPOLYGON": "MultiPolygon",
              "GEOMETRYCOLLECTION": "GeometryCollection"}


def contar_tipos_geometria(caminho_dxf: str, dir_trabalho: str | os.PathLike, *, inline_blocos: bool = False,
                           codificacao: str = "UTF-8") -> dict[str, int]:
    """{tipo de geometria: nº de feições}, com o sufixo Z preservado. Existe porque a varredura genérica da
    ingestão usa `GROUP BY` no dialeto OGRSQL, e o OGR SQL não tem `GROUP BY` — devolve vazio em silêncio, e a
    proposta ficaria sem saber que geometria o desenho tem."""
    caminho_dxf = isolamento.caminho_dentro(caminho_dxf, dir_trabalho)
    alvo = Path(dir_trabalho) / "tipos_geometria.jsonl"
    if alvo.exists():
        alvo.unlink()
    argv = ["ogr2ogr", "-f", "GeoJSONSeq", str(alvo), caminho_dxf, *_config(inline_blocos, codificacao),
            "-dialect", "SQLITE",
            "-sql", "SELECT GeometryType(geometry) AS t, COUNT(*) AS n FROM entities GROUP BY GeometryType(geometry)"]
    r = isolamento.executar(argv, raiz=dir_trabalho)
    if not r.ok or not alvo.exists():
        return {}
    saida: dict[str, int] = {}
    for p in _ler_jsonl(alvo):
        bruto = (p.get("t") or "NULL").strip()
        base, sufixo = (bruto.split(" ", 1) + [""])[:2]
        nome = _TIPOS_OGR.get(base.upper())
        chave = "NULL" if nome is None else (nome + (" " + sufixo if sufixo else ""))
        saida[chave] = saida.get(chave, 0) + int(p.get("n") or 0)
    return saida


def listar_blocos(caminho_dxf: str, dir_trabalho: str | os.PathLike, *, codificacao: str = "UTF-8") -> list[dict]:
    """Definições de bloco do desenho (camada `blocks` do GDAL, que só existe com `DXF_INLINE_BLOCKS=FALSE`)."""
    caminho_dxf = isolamento.caminho_dentro(caminho_dxf, dir_trabalho)
    alvo = Path(dir_trabalho) / "blocos.jsonl"
    if alvo.exists():
        alvo.unlink()
    argv = ["ogr2ogr", "-f", "GeoJSONSeq", str(alvo), caminho_dxf, *_config(False, codificacao),
            "-dialect", "SQLITE",
            "-sql", "SELECT Block AS bloco, COUNT(*) AS entidades FROM blocks GROUP BY Block ORDER BY Block"]
    r = isolamento.executar(argv, raiz=dir_trabalho)
    if not r.ok or not alvo.exists():
        return []
    return [{"nome": p.get("bloco") or "(anônimo)", "entidades": int(p.get("entidades") or 0)}
            for p in _ler_jsonl(alvo)]


# ========================================================================================= inspeção
def inspecionar(caminho: str | os.PathLike, dir_trabalho: str | os.PathLike, *, formato: str,
                respostas: dict | None = None, medir_isolamento: bool = False) -> Relatorio:
    """Leitura completa de um DXF ou DWG. Nunca levanta por defeito do arquivo: devolve `Relatorio` com
    `estado='recusado'` e a causa em português. `respostas` traz o que só o usuário sabe: `unidade`,
    `crs`, `codificacao`, `blocos` ('ponto' ou 'explodido')."""
    respostas = respostas or {}
    rel = Relatorio(formato=formato)
    dir_trabalho = Path(dir_trabalho)
    try:
        caminho = Path(isolamento.caminho_dentro(caminho, dir_trabalho))
    except isolamento.CaminhoRecusado as e:
        rel.estado = "recusado"
        rel.problemas.append(str(e))
        return rel
    tamanho = caminho.stat().st_size
    if tamanho == 0:
        rel.estado = "recusado"
        rel.problemas.append("o arquivo está vazio")
        return rel
    if tamanho > TAMANHO_MAX:
        rel.estado = "recusado"
        rel.problemas.append(f"o arquivo tem {tamanho // (1024 * 1024)} MB; o máximo é "
                             f"{TAMANHO_MAX // (1024 * 1024)} MB")
        return rel
    with open(caminho, "rb") as fh:
        cabecalho_bytes = fh.read(64)
    tipo = assinatura(cabecalho_bytes)

    try:
        if tipo == "dxf_binario":
            raise ArquivoRecusado(
                "o arquivo é um DXF BINÁRIO (sentinela 'AutoCAD Binary DXF'), formato que o leitor de DXF do "
                "GDAL não abre; grave o desenho como DXF de texto (ASCII) e envie de novo")
        if formato == "dwg":
            if tipo != "dwg":
                raise ArquivoRecusado("o arquivo foi declarado como DWG, mas os bytes iniciais não são de um DWG")
            caminho_dxf, registro = converter_dwg(caminho, dir_trabalho)
            rel.conversao = registro
            rel.versao = registro["versao_arquivo"]
        elif formato == "dxf":
            if tipo == "dwg":
                _marca, versao = versao_dwg(cabecalho_bytes)
                raise ArquivoRecusado(f"o arquivo foi declarado como DXF, mas é um DWG na versão {versao}; "
                                      f"declare o tipo DWG no envio")
            if tipo != "dxf":
                raise ArquivoRecusado("o arquivo não é um DXF: os bytes iniciais não trazem a seção do formato")
            caminho_dxf = str(caminho)
        else:
            raise ArquivoRecusado(f"formato não tratado por este leitor: {formato}")

        cab = cabecalho_dxf(caminho_dxf)
        if formato == "dxf":
            rel.versao = VERSOES_DXF.get(cab.get("acadver") or "", cab.get("acadver"))
        rel.codificacao = _codificacao(cab)
        if respostas.get("codificacao"):
            rel.codificacao = {**rel.codificacao, "origem": "usuario", "valor": str(respostas["codificacao"]),
                               "perguntar": False}
        if rel.codificacao.get("aviso"):
            rel.avisos.append(rel.codificacao["aviso"])

        codigo = cab.get("insunits")
        nome_unidade, metros = UNIDADES.get(codigo if codigo is not None else 0, ("desconhecida", None))
        resposta_unidade = respostas.get("unidade")
        if resposta_unidade is not None:
            nome_resp, metros_resp = UNIDADES.get(int(resposta_unidade), ("desconhecida", None))
            rel.unidade = {"origem": "usuario", "codigo": int(resposta_unidade), "nome": nome_resp,
                           "metros_por_unidade": metros_resp, "perguntar": False}
        elif metros is None:
            rel.unidade = {"origem": "cabecalho", "codigo": codigo, "nome": nome_unidade,
                           "metros_por_unidade": None, "perguntar": True}
            rel.pendencias.append(
                "o desenho não declara a unidade ($INSUNITS = 0): informe se a escala é metro, centímetro, "
                "milímetro ou polegada — sem isso a área e a distância saem erradas")
        else:
            rel.unidade = {"origem": "cabecalho", "codigo": codigo, "nome": nome_unidade,
                           "metros_por_unidade": metros, "perguntar": False}

        inline = str(respostas.get("blocos") or "ponto") == "explodido"
        rel.camadas = contar_por_camada(caminho_dxf, dir_trabalho, inline_blocos=inline,
                                        codificacao=rel.codificacao["valor"])
        no_texto = contar_entidades_no_texto(caminho_dxf, rel.codificacao["valor"])
        truncou = bool(no_texto.pop("_truncado", False))
        for c in rel.camadas:
            c["cotas"] = int((no_texto.get(c["nome"]) or {}).get("cotas", 0))
        for nome_camada, familias in no_texto.items():
            if familias.get("cotas") and not any(c["nome"] == nome_camada for c in rel.camadas):
                rel.camadas.append({"nome": nome_camada, "entidades": 0, "cotas": familias["cotas"],
                                    "textos": 0, "hachuras": 0, "blocos": 0, "blocos_distintos": 0})
        if truncou:
            rel.avisos.append(f"o desenho passa de {TEXTO_MAX // (1024 * 1024)} MB de texto; a contagem de cotas "
                              f"parou nesse ponto (as demais contagens são do GDAL e valem para o arquivo todo)")
        if not rel.camadas:
            raise ArquivoRecusado("o desenho não tem nenhuma entidade em espaço de modelo")
        if len(rel.camadas) > CAMADAS_MAX:
            raise ArquivoRecusado(f"o desenho tem {len(rel.camadas)} camadas; o máximo é {CAMADAS_MAX}")
        total = sum(c["entidades"] for c in rel.camadas)
        if total > ENTIDADES_MAX:
            raise ArquivoRecusado(
                f"o desenho tem {total} entidades; o máximo por arquivo é {ENTIDADES_MAX}. Divida o desenho por "
                f"camada ou por região e envie em partes")
        rel.totais = {
            "camadas": len(rel.camadas), "entidades": total,
            "cotas": sum(c["cotas"] for c in rel.camadas), "textos": sum(c["textos"] for c in rel.camadas),
            "hachuras": sum(c["hachuras"] for c in rel.camadas), "blocos": sum(c["blocos"] for c in rel.camadas),
            "blocos_modo": "explodido" if inline else "ponto",
        }
        rel.tipos_geometria = contar_tipos_geometria(caminho_dxf, dir_trabalho, inline_blocos=inline,
                                                     codificacao=rel.codificacao["valor"])
        if not inline:
            rel.blocos = listar_blocos(caminho_dxf, dir_trabalho, codificacao=rel.codificacao["valor"])
        if cab.get("extmin") and cab.get("extmax"):
            rel.extensao = [cab["extmin"][0], cab["extmin"][1], cab["extmax"][0], cab["extmax"][1]]
        rel.caminho_dxf = caminho_dxf

        # CRS: o DXF não carrega projeção. Só o usuário sabe — ou informando o EPSG do desenho, ou dando pontos
        # de controle para a georreferência (app/ingestao/georreferencia.py).
        if not respostas.get("crs") and not respostas.get("georreferencia"):
            rel.pendencias.append(
                "o desenho não traz sistema de coordenadas: informe o EPSG em que ele foi desenhado ou envie de "
                "2 a 4 pontos de controle (coordenada do desenho e coordenada de terreno) para georreferenciar")
        if medir_isolamento:
            rel.isolamento = isolamento.isolamento_declarado(dir_trabalho)
    except ArquivoRecusado as e:
        rel.estado = "recusado"
        rel.problemas.append(sem_caminho(str(e)))
        return rel
    except (OSError, ValueError) as e:  # rede final: nenhum defeito de arquivo sai como traceback (ADR 0015 §7)
        rel.estado = "recusado"
        rel.problemas.append(f"o arquivo não pôde ser interpretado ({sem_caminho(str(e))[:200]})")
        return rel
    rel.estado = "pendente" if rel.pendencias else "aceito"
    return rel
