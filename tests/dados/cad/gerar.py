#!/usr/bin/env python3
"""Gera os arquivos CAD de teste do item L0-04-e. Roda com o venv do repositório (`venv/bin/python
tests/dados/cad/gerar.py`) e grava DXF determinístico (sem GUID nem carimbo de tempo) ao lado. O DWG R2000 sai
do `dxf2dwg` do LibreDWG; o DWG R2018 NÃO pode ser gerado (o LibreDWG só escreve até r2004) e vem do corpus,
com procedência em PROVENIENCIA.md.

Conteúdo, um arquivo por cláusula do portão de pronto:
* `blocos.dxf` — bloco simples, bloco ANINHADO (bloco dentro de bloco) e INSERT com atributo;
* `polilinhas.dxf` — LWPOLYLINE fechada e aberta (2D) e POLYLINE 3D com Z;
* `textos.dxf` — TEXT, MTEXT, DIMENSION (cota) e HATCH (hachura);
* `camada_longa.dxf` — nome de camada com 200 caracteres, acento e espaço;
* `polegada.dxf` — $INSUNITS = 0 (unidade não declarada): a escala tem de ser PERGUNTADA;
* `milhao.dxf` — muitas entidades, para o teto de feições (o número vem do argumento `--entidades`);
* `binario.dxf` — DXF BINÁRIO (sentinela "AutoCAD Binary DXF"), que o driver DXF do GDAL não lê.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import ezdxf

AQUI = Path(__file__).resolve().parent
CAMADA_LONGA = ("EIXO_DE_ARRUAMENTO_PROJETADO_COM_MEIO_FIO_E_SARJETA_REVISAO_" * 4)[:190] + " ÁGUA PLUVIAL"


def _determinista(doc) -> None:
    for k, v in (("$FINGERPRINTGUID", "{00000000-0000-0000-0000-000000000000}"),
                 ("$VERSIONGUID", "{00000000-0000-0000-0000-000000000000}"),
                 ("$TDCREATE", 0.0), ("$TDUCREATE", 0.0), ("$TDUPDATE", 0.0), ("$TDUUPDATE", 0.0),
                 ("$TDINDWG", 0.0), ("$TDUSRTIMER", 0.0)):
        try:
            doc.header[k] = v
        except Exception:  # noqa: BLE001 — cabeçalho opcional; ausência não invalida o arquivo
            pass


def _gravar(doc, nome: str) -> Path:
    alvo = AQUI / nome
    doc.saveas(alvo)
    txt = alvo.read_text(encoding="utf-8", errors="replace")
    txt = re.sub(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}",
                 "{00000000-0000-0000-0000-000000000000}", txt)
    txt = re.sub(r"(\d+\.\d+\.\d+) @ \d{4}-\d{2}-\d{2}T[0-9:.+]+", r"\1", txt)
    alvo.write_text(txt, encoding="utf-8")
    print(nome, alvo.stat().st_size, "bytes")
    return alvo


def blocos() -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    _determinista(doc)
    interno = doc.blocks.new(name="POSTE")
    interno.add_circle((0, 0), radius=0.3, dxfattribs={"layer": "MOBILIARIO"})
    interno.add_line((0, 0), (0, 6), dxfattribs={"layer": "MOBILIARIO"})
    externo = doc.blocks.new(name="CONJUNTO_ILUMINACAO")   # bloco ANINHADO: contém o POSTE
    externo.add_blockref("POSTE", (0, 0))
    externo.add_blockref("POSTE", (12, 0))
    externo.add_lwpolyline([(0, 0), (12, 0)], dxfattribs={"layer": "MOBILIARIO"})
    doc.layers.add("MOBILIARIO", color=3)
    doc.layers.add("HIDRANTE", color=1)
    msp = doc.modelspace()
    for i in range(4):
        msp.add_blockref("CONJUNTO_ILUMINACAO", (i * 30.0, 0.0), dxfattribs={"layer": "MOBILIARIO"})
    for i in range(3):
        msp.add_blockref("POSTE", (i * 40.0, 25.0), dxfattribs={"layer": "HIDRANTE"})
    _gravar(doc, "blocos.dxf")


def polilinhas() -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    _determinista(doc)
    doc.layers.add("QUADRA", color=5)
    doc.layers.add("TALUDE_3D", color=8)
    msp = doc.modelspace()
    for i in range(5):
        x = i * 50.0
        msp.add_lwpolyline([(x, 0), (x + 40, 0), (x + 40, 30), (x, 30)], close=True, dxfattribs={"layer": "QUADRA"})
    for i in range(3):
        msp.add_lwpolyline([(0, i * 10.0), (200, i * 10.0)], close=False, dxfattribs={"layer": "QUADRA"})
    for i in range(4):
        pontos = [(j * 25.0, i * 12.0, 700.0 + i * 3 + j * 1.5) for j in range(6)]
        msp.add_polyline3d(pontos, dxfattribs={"layer": "TALUDE_3D"})
    _gravar(doc, "polilinhas.dxf")


def textos() -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    _determinista(doc)
    for nome, cor in (("ROTULO", 7), ("COTA", 2), ("HACHURA", 4)):
        doc.layers.add(nome, color=cor)
    msp = doc.modelspace()
    for i in range(6):
        msp.add_text(f"LOTE-{i + 1:03d}", height=1.5,
                     dxfattribs={"layer": "ROTULO", "insert": (i * 12.0, 5.0)})
    for i in range(3):
        texto = msp.add_mtext(f"QUADRA {i + 1}\nÁREA 1.234,56 m²", dxfattribs={"layer": "ROTULO"})
        texto.set_location((i * 30.0, 20.0))
    for i in range(4):
        cota = msp.add_linear_dim(base=(0, -4 - i * 3), p1=(i * 10.0, 0), p2=(i * 10.0 + 9.0, 0),
                                  dxfattribs={"layer": "COTA"})
        cota.render()
    for i in range(3):
        h = msp.add_hatch(color=4, dxfattribs={"layer": "HACHURA"})
        h.paths.add_polyline_path(
            [(i * 20.0, 40.0), (i * 20.0 + 15, 40.0), (i * 20.0 + 15, 52.0), (i * 20.0, 52.0)], is_closed=True)
    _gravar(doc, "textos.dxf")


def camada_longa() -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    _determinista(doc)
    doc.layers.add(CAMADA_LONGA, color=6)
    doc.layers.add("0-CURTA", color=1)
    msp = doc.modelspace()
    for i in range(7):
        msp.add_lwpolyline([(i * 10.0, 0), (i * 10.0 + 8, 0), (i * 10.0 + 8, 6), (i * 10.0, 6)],
                           close=True, dxfattribs={"layer": CAMADA_LONGA})
    for i in range(2):
        msp.add_point((i * 3.0, 3.0), dxfattribs={"layer": "0-CURTA"})
    _gravar(doc, "camada_longa.dxf")


def polegada() -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 0  # unidade NÃO declarada; o desenho está em polegadas
    _determinista(doc)
    doc.layers.add("PECA", color=1)
    msp = doc.modelspace()
    for i in range(5):
        msp.add_lwpolyline([(i * 4.0, 0), (i * 4.0 + 3.5, 0), (i * 4.0 + 3.5, 2.25), (i * 4.0, 2.25)],
                           close=True, dxfattribs={"layer": "PECA"})
    _gravar(doc, "polegada.dxf")


def milhao(n: int) -> None:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    _determinista(doc)
    doc.layers.add("MASSA", color=1)
    msp = doc.modelspace()
    for i in range(n):
        msp.add_point((i % 2000, i // 2000), dxfattribs={"layer": "MASSA"})
    _gravar(doc, "milhao.dxf")


def binario() -> None:
    """DXF BINÁRIO de verdade: sentinela de 22 bytes + os pares (código, valor) em binário. Só precisa ser
    reconhecível como DXF binário — o driver do GDAL não lê este formato e a recusa tem de dizer isso."""
    import struct

    corpo = bytearray(b"AutoCAD Binary DXF\r\n\x1a\x00")

    def par_texto(codigo: int, valor: str) -> None:
        corpo.extend(struct.pack("<h", codigo))
        corpo.extend(valor.encode("ascii"))
        corpo.append(0)

    par_texto(0, "SECTION")
    par_texto(2, "ENTITIES")
    for i in range(20):
        par_texto(0, "POINT")
        par_texto(8, "MASSA")
        for codigo, v in ((10, float(i)), (20, 0.0), (30, 0.0)):
            corpo.extend(struct.pack("<h", codigo))
            corpo.extend(struct.pack("<d", v))
    par_texto(0, "ENDSEC")
    par_texto(0, "EOF")
    alvo = AQUI / "binario.dxf"
    alvo.write_bytes(bytes(corpo))
    print("binario.dxf", alvo.stat().st_size, "bytes")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--entidades", type=int, default=0, help="gera milhao.dxf com N entidades (0 = não gera)")
    a = p.parse_args()
    blocos()
    polilinhas()
    textos()
    camada_longa()
    polegada()
    binario()
    if a.entidades:
        milhao(a.entidades)
    return 0


if __name__ == "__main__":
    sys.exit(main())
