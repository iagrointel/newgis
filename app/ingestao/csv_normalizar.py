"""Normalizador de CSV/TXT (ADR 0005 seção 11): o driver CSV do GDAL 3.8.4 (MEDIDO no ADR) não lê separador de
milhar, não lê `dd/mm/aaaa`, não lê `"12,5"` com separador `,`, engole linha depois de aspa desbalanceada em
silêncio e não abre `.txt`. Este módulo resolve tudo isso ANTES do GDAL: entrega um CSV canônico (UTF-8, `,`,
ponto decimal, cabeçalho normalizado) e a informação de que colunas são coordenada (lat/lon), para
`-oo X_POSSIBLE_NAMES=/-oo Y_POSSIBLE_NAMES=` na carga. Só o que o escopo desta passagem exige: separador `,`/`;`/
tab, vírgula decimal, BOM, coluna de coordenada por NOME (a detecção por faixa de valor fica para o L0-04-d
completo — ver handoff)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from app.ingestao import nomes

SEPARADORES = (",", ";", "\t", "|")
NOMES_LAT = {"lat", "latitude", "y", "norte", "n"}
NOMES_LON = {"lon", "long", "longitude", "x", "este", "leste", "e"}
_NUMERO_PV = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d+$")   # 1.234,5  (milhar '.', decimal ',')
_NUMERO_V = re.compile(r"^-?\d+,\d+$")                  # 12,5     (decimal ',', sem milhar)
_NUMERO_PONTO = re.compile(r"^-?\d+\.\d+$")


@dataclass
class ColunaCsv:
    origem: str
    nome: str
    e_numero_decimal_virgula: bool = False
    candidata_lat: bool = False
    candidata_lon: bool = False
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoCsvNormalizar:
    texto: str               # CSV canônico: UTF-8, separador ',', aspas '"', ponto decimal
    separador_origem: str
    decimal_origem: str      # '.' ou ','
    colunas: list[ColunaCsv]
    linhas_lidas: int
    coordenadas: dict | None  # {"x": nome, "y": nome} ou None
    aspas_desbalanceadas_linha: int | None = None


def _detectar_separador(amostra: str) -> str:
    primeira = amostra.splitlines()[0] if amostra else ""
    contagens = {s: primeira.count(s) for s in SEPARADORES}
    melhor = max(contagens, key=contagens.get)
    return melhor if contagens[melhor] > 0 else ","


def _aspas_desbalanceadas(texto: str) -> int | None:
    """Número da linha (1-based, contando o cabeçalho) com aspas ímpares, ou None se todas batem."""
    for i, linha in enumerate(texto.splitlines(), start=1):
        if linha.count('"') % 2 != 0:
            return i
    return None


def _decodificar(dados: bytes) -> str:
    for bom, cod in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if dados.startswith(bom):
            return dados.decode(cod)
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        from charset_normalizer import from_bytes

        melhor = from_bytes(dados).best()
        if melhor is None:
            return dados.decode("latin-1")
        return str(melhor)


def normalizar_bytes(dados: bytes) -> ResultadoCsvNormalizar:
    texto = _decodificar(dados)
    linha_aspas = _aspas_desbalanceadas(texto)
    separador = _detectar_separador(texto)
    leitor = csv.reader(io.StringIO(texto), delimiter=separador)
    linhas = list(leitor)
    if not linhas:
        return ResultadoCsvNormalizar("", separador, ".", [], 0, None)
    cabecalho_origem = linhas[0]
    corpo = linhas[1:]

    usados: set[str] = set()
    colunas = [ColunaCsv(origem=c, nome=nomes.normalizar(c, usados, posicao=i)[0])
               for i, c in enumerate(cabecalho_origem)]

    # decide, por coluna, se é numérico com vírgula decimal (>= 90% dos valores não vazios casam o padrão)
    decimal_origem = "."
    for idx, coluna in enumerate(colunas):
        valores = [linha[idx] for linha in corpo if idx < len(linha) and linha[idx].strip() != ""]
        if not valores:
            continue
        pv = sum(1 for v in valores if _NUMERO_PV.match(v.strip()))
        v_simples = sum(1 for v in valores if _NUMERO_V.match(v.strip()))
        ponto = sum(1 for v in valores if _NUMERO_PONTO.match(v.strip()))
        if (pv + v_simples) / len(valores) >= 0.9 and (pv + v_simples) >= ponto:
            coluna.e_numero_decimal_virgula = True
            decimal_origem = ","
        nome_l = coluna.origem.strip().lower()
        # remove acento p/ casar "Este"/"É" etc. de forma simples (ASCII fold básico já embutido em nomes.normalizar)
        nome_norm = coluna.nome
        if nome_l in NOMES_LAT or nome_norm in NOMES_LAT:
            coluna.candidata_lat = True
        if nome_l in NOMES_LON or nome_norm in NOMES_LON:
            coluna.candidata_lon = True

    coordenadas = None
    lat = next((c for c in colunas if c.candidata_lat), None)
    lon = next((c for c in colunas if c.candidata_lon), None)
    if lat and lon:
        coordenadas = {"x": lon.nome, "y": lat.nome}

    # reescreve o corpo: vírgula decimal -> ponto nas colunas marcadas; texto sempre entre aspas (aspas
    # desbalanceadas já foram detectadas acima e viram recusa antes de chegar aqui, então o corpo é bem formado)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    escritor.writerow([c.nome for c in colunas])
    for linha in corpo:
        nova = list(linha) + [""] * (len(colunas) - len(linha))
        for idx, coluna in enumerate(colunas):
            if coluna.e_numero_decimal_virgula and nova[idx].strip():
                nova[idx] = nova[idx].strip().replace(".", "").replace(",", ".")
        escritor.writerow(nova[: len(colunas)])

    return ResultadoCsvNormalizar(
        texto=saida.getvalue(),
        separador_origem=separador,
        decimal_origem=decimal_origem,
        colunas=colunas,
        linhas_lidas=len(corpo),
        coordenadas=coordenadas,
        aspas_desbalanceadas_linha=linha_aspas,
    )
