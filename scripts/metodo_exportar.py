#!/usr/bin/env python3
"""Exportação do método do motor AMC: documento JSON canônico + relatório em PDF (item
L3-01-i-exportacao-metodo).

Entrada (arquivo JSON ou stdin):

    {
      "nome": "nome do método",
      "modelo": {"fatores": [...], "pesos": {...}, "vetos": {...},
                 "combinador": "...", "politica_ausente": "...", "gama": 0.5},
      "camadas": [{"fator": "...", "nome": "...", "sha256": "..."}, ...],
      "entrada": {"matriz": [[...], ...]},
      "resultado": {...}          // opcional: Resultado.como_dicionario() da combinação
    }

Saída, em --saida <diretório>:
    <slug>.metodo.json     — o documento canônico (formato plat/amc_metodo, com sha256)
    <slug>.relatorio.pdf   — o relatório gerado DESTE documento (páginas = seções)

O script imprime na saída padrão o caminho dos dois arquivos e o sha256 do documento.
"""

import argparse
import datetime
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.amc import metodo, relatorio  # noqa: E402


def _slug(nome: str) -> str:
    """Nome em nome de arquivo: sem acento, minúsculo, só letra, número e hífen."""
    plano = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-") or "metodo"


def main() -> int:
    p = argparse.ArgumentParser(description="exporta o método do motor AMC em JSON canônico e PDF")
    p.add_argument("entrada", help="arquivo JSON com nome, modelo, camadas, entrada e resultado opcional")
    p.add_argument("--saida", required=True, help="diretório de saída")
    a = p.parse_args()

    bruto = json.loads(pathlib.Path(a.entrada).read_text(encoding="utf-8"))
    gerado_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    documento = metodo.metodo_canonico(
        nome=bruto["nome"],
        modelo=bruto["modelo"],
        camadas=bruto.get("camadas"),
        transformacoes=bruto.get("transformacoes"),
        entrada=bruto.get("entrada"),
        resultado=bruto.get("resultado"),
        gerado_em=gerado_em,
    )
    saida = pathlib.Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    slug = _slug(documento["nome"])
    caminho_json = saida / f"{slug}.metodo.json"
    caminho_pdf = saida / f"{slug}.relatorio.pdf"
    caminho_json.write_text(json.dumps(documento, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    relatorio.gerar_pdf(documento, caminho_pdf)
    print(caminho_json)
    print(caminho_pdf)
    print(documento["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
