"""Cláusula "números no MANUAL saem de tests/medidas" (item L3-16-desempenho-escala).

A seção 22 do MANUAL.md fala em números de desempenho e de escala. Este teste lê os dois arquivos e
exige que TODO número dessa seção exista, com o mesmo valor, em `tests/medidas/L3-16-desempenho-escala.json`
ou em `app/limites.py`. Assim ninguém digita um número de desempenho à mão nem deixa o texto envelhecer
depois de uma medição nova: mexeu no número, o teste reprova até o MANUAL acompanhar.

A regra é literal: cada número em **negrito** da seção 22 tem de casar. O negrito é a marcação que o texto
já usa para os valores medidos, e é o que separa um número afirmado de uma referência de item ou de seção."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import limites

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "MANUAL.md"
MEDIDAS = ROOT / "tests" / "medidas" / "L3-16-desempenho-escala.json"
SECAO = "## 22. Escala do motor multicritério"


def _secao22() -> str:
    texto = MANUAL.read_text(encoding="utf-8")
    assert SECAO in texto, "MANUAL.md sem a seção 22 do item L3-16"
    corpo = texto.split(SECAO, 1)[1]
    return corpo.split("\n## ", 1)[0]


def _numeros(texto: str) -> list[float]:
    """Números em negrito da seção, na notação do texto em português (milhar com ponto, decimal com vírgula)."""
    saida = []
    for trecho in re.findall(r"\*\*(.+?)\*\*", texto, flags=re.S):
        for bruto in re.findall(r"\d[\d.]*(?:,\d+)?", trecho):
            saida.append(float(bruto.replace(".", "").replace(",", ".")))
    return saida


def _permitidos() -> dict[float, str]:
    medidas = json.loads(MEDIDAS.read_text(encoding="utf-8"))["medidas"]
    permitidos = {}
    for nome, m in medidas.items():
        if m["valor"] is None:
            continue
        permitidos[float(m["valor"])] = f"tests/medidas/L3-16-desempenho-escala.json::{nome}"
        if m["unidade"] == "s":                       # o texto também cita o mesmo tempo em horas e em minutos
            permitidos[round(float(m["valor"]) / 3600, 0)] = f"{nome} em horas"
            permitidos[round(float(m["valor"]) / 60, 0)] = f"{nome} em minutos"
        if m["unidade"] == "ms":
            permitidos[round(float(m["valor"]) / 1000, 4)] = f"{nome} em segundos"
    for nome in ("AMC_COMBINAR_NAVEGADOR_MAX", "AMC_BLOCO_UNIDADES", "AMC_EXTRACAO_MEMORIA_MB",
                 "AMC_EXTRACAO_TIMEOUT_S", "AMC_EXTRACAO_US_POR_UNIDADE_FATOR", "AMC_UNIDADES_MAX"):
        valor = float(getattr(limites, nome))
        permitidos[valor] = f"app/limites.py::{nome}"
        permitidos[round(valor / 1024, 0)] = f"{nome} em GB"          # 4096 MB citado como 4 GB
        permitidos[round(valor / 60, 0)] = f"{nome} em minutos"       # 1800 s citado como 30 min
        permitidos[round(valor / 1_000_000, 0)] = f"{nome} em milhões"
    permitidos[15.0] = "número de fatores do portão do item"
    permitidos[20.0] = "1.000.000 / AMC_BLOCO_UNIDADES = 20 blocos"
    permitidos[22.0] = "número da própria seção do MANUAL"
    return permitidos


def test_todo_numero_em_negrito_da_secao_22_do_manual_vem_das_medidas_ou_dos_limites():
    permitidos = _permitidos()
    faltando = [n for n in _numeros(_secao22()) if n not in permitidos]
    assert not faltando, (
        f"números na seção 22 do MANUAL que não existem em tests/medidas nem em app/limites.py: {faltando}. "
        "Todo número de desempenho do MANUAL tem de sair de uma medida gravada, nunca ser digitado à mão."
    )


def test_a_secao_22_cita_de_fato_as_medidas_principais():
    """A guarda acima só reprova número INVENTADO; esta reprova número que SUMIU do texto."""
    secao = _secao22()
    medidas = json.loads(MEDIDAS.read_text(encoding="utf-8"))["medidas"]
    obrigatorias = ("recombinacao_1000000x15_servidor_s", "pico_ram_recombinacao_1mi_em_blocos_mb",
                    "extracao_por_unidade_por_fator_us", "extracao_1mi_x15_projetado_s",
                    "extracao_unidades_max_em_30min_com_15_fatores", "combinacao_navegador_50000x15_ms")
    numeros = _numeros(secao)
    ausentes = [n for n in obrigatorias if medidas[n]["valor"] is None or float(medidas[n]["valor"]) not in numeros]
    assert not ausentes, f"medidas que o MANUAL deveria citar e não cita: {ausentes}"


@pytest.mark.parametrize("frase", [
    "unidades_demais_para_o_navegador",
    "prazo_projetado_estourado",
    "L3-01-c2-extracao-em-lote",
])
def test_a_secao_22_nomeia_o_erro_e_o_item_que_continua_o_trabalho(frase):
    assert frase in _secao22()
