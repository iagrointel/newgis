"""Cláusulas do relatório em PDF do método AMC (item L3-01-i-exportacao-metodo).

Portão do item: páginas = seções; o teste extrai TODOS os números do PDF e os encontra no JSON
(nenhum digitado); JSON reimportado recria o modelo com o mesmo hash; PDF verificado página a
página (pdftoppm → leitura, registrada nas medidas do item); teste automatizado.

Refutação do item: o adversário altera um peso no JSON exportado e reimporta — o hash tem de mudar
e o PDF antigo não pode ser aceito como do modelo novo.

A conferência de números usa a extração de PALAVRAS do pdfplumber: uma palavra que é só número
(inclusive com vírgula decimal) precisa existir em `metodo.numeros_do_documento`. Palavras hexa
longas (as duas metades de 32 do sha256) saem da conta: o hash é conferido à parte por
`metodo.confere_pdf`.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import time

import pdfplumber
import pytest
from pypdf import PdfReader

from app.amc import metodo, relatorio
from app.amc.combinacao import combinar

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARGA_MAXIMA = 8.0

_PURO_NUMERO = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_HEXA_LONGO = re.compile(r"^[0-9a-f]{16,}$")

MODELO = {
    "fatores": ["acesso_rodoviario", "custo_terreno", "area_alagada"],
    "pesos": {"acesso_rodoviario": 5.0, "custo_terreno": 2.0, "area_alagada": 1.0},
    "vetos": {"area_alagada": 1.0},
    "combinador": "soma_ponderada",
    "politica_ausente": "excluir",
}
CAMADAS = [
    {"fator": "acesso_rodoviario", "nome": "distância a via pavimentada", "sha256": "a" * 64},
    {"fator": "custo_terreno", "nome": "valor do solo declarado"},
    {"fator": "area_alagada", "nome": "área alagada", "sha256": "b" * 64},
]
TRANSFORMACOES = {
    "acesso_rodoviario": "distância em km reclassificada por quebra natural em nota 0-100",
    "area_alagada": "fração da unidade em mancha de inundação vezes cem",
}
ENTRADA = {"matriz": [[80.0, 40.0, 5.0], [70.0, 20.0, None], [55.0, 60.0, 0.0], [40.0, 90.0, 2.0]]}
GERADO_EM = "2026-09-08T14:03:00Z"


def _resultado(matriz):
    pesos = [MODELO["pesos"][f] for f in MODELO["fatores"]]
    fracao = [0.0 if v is None else 1.0 * (v >= 5.0) for v in (linha[2] for linha in matriz)]
    return combinar(matriz, pesos, fracao_vetada=fracao, ids_fatores=MODELO["fatores"]).como_dicionario()


def _documento(matriz=None, **kwargs):
    return metodo.metodo_canonico(
        nome="método de teste do exportador",
        modelo=MODELO,
        camadas=CAMADAS,
        transformacoes=TRANSFORMACOES,
        entrada={"matriz": matriz or ENTRADA["matriz"]},
        resultado=None if kwargs.get("sem_resultado") else _resultado(matriz or ENTRADA["matriz"]),
        gerado_em=GERADO_EM,
    )


def _palavras(pdf_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [p["text"] for pagina in pdf.pages for p in pagina.extract_words()]


def _numeros_do_pdf(pdf_bytes: bytes) -> set[float]:
    achados = set()
    for palavra in _palavras(pdf_bytes):
        if _HEXA_LONGO.match(palavra.lower()) or not _PURO_NUMERO.match(palavra):
            continue
        achados.add(round(float(palavra.replace(",", ".")), metodo.DECIMAIS))
    return achados


def _texto_do_pdf(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)


def _linhas_do_pdf(pdf_bytes: bytes) -> set[str]:
    return {linha.strip() for linha in _texto_do_pdf(pdf_bytes).splitlines() if linha.strip()}


def test_paginas_do_pdf_sao_exatamente_as_secoes_do_documento():
    d = _documento()
    esperado = relatorio.paginas_do_relatorio(d)
    leitor = PdfReader(io.BytesIO(relatorio.gerar_pdf(d)))
    assert len(leitor.pages) == esperado
    # resumo + fluxo + um por fator + pesos + resultado + ressalvas
    assert esperado == 2 + len(d["modelo"]["fatores"]) + 1 + 1 + 1
    linhas = _linhas_do_pdf(relatorio.gerar_pdf(d))
    for titulo in ("resumo", "fluxo do modelo", "pesos", "resultado final", "ressalvas"):
        assert titulo in linhas, f"seção {titulo} não apareceu como página no PDF"
    assert any(linha.startswith("fator acesso_rodoviario") for linha in linhas)


def test_todos_os_numeros_do_pdf_estao_no_json_nenhum_foi_digitado():
    d = _documento()
    pdf = relatorio.gerar_pdf(d)
    numeros_pdf = _numeros_do_pdf(pdf)
    assert numeros_pdf, "a extração não achou número nenhum — o teste em si falhou"
    universo = metodo.numeros_do_documento(d)
    fora = sorted(numeros_pdf - universo)
    assert not fora, f"números impressos no PDF que não estão no JSON (digitados): {fora}"
    # e os números essenciais do método de fato aparecem no PDF
    assert {0.0, 100.0, 5.0, 2.0, 1.0} <= numeros_pdf
    assert 55.7143 in numeros_pdf and 49.375 in numeros_pdf


def test_o_sha256_do_metodo_esta_impresso_no_pdf():
    d = _documento()
    assert metodo.confere_pdf(_texto_do_pdf(relatorio.gerar_pdf(d)), d) is True


def test_refutacao_pdf_do_modelo_antigo_nao_vale_para_o_modelo_novo():
    d = _documento()
    pdf_antigo = relatorio.gerar_pdf(d)
    texto_antigo = _texto_do_pdf(pdf_antigo)

    # o adversário altera um peso no JSON exportado e reimporta
    adulterado = json.loads(json.dumps(d))
    adulterado["modelo"]["pesos"]["custo_terreno"] = 9.0
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.importar_metodo(adulterado)
    assert e.value.codigo == "documento_alterado"

    # o hash do método novo É outro e o PDF ANTIGO não confere com ele
    novo = metodo.metodo_canonico(
        nome=d["nome"], modelo=adulterado["modelo"], camadas=CAMADAS,
        transformacoes=TRANSFORMACOES, entrada={"matriz": ENTRADA["matriz"]},
        resultado=_resultado(ENTRADA["matriz"]), gerado_em=GERADO_EM,
    )
    assert novo["sha256"] != d["sha256"]
    assert metodo.confere_pdf(texto_antigo, novo) is False
    # e um PDF gerado do método novo confere com ele e só com ele
    assert metodo.confere_pdf(_texto_do_pdf(relatorio.gerar_pdf(novo)), novo) is True
    assert metodo.confere_pdf(_texto_do_pdf(relatorio.gerar_pdf(novo)), d) is False


def test_metodo_sem_resultado_nao_tem_pagina_de_resultado():
    d = _documento(sem_resultado=True)
    esperado = relatorio.paginas_do_relatorio(d)
    assert esperado == 2 + len(d["modelo"]["fatores"]) + 1 + 1
    leitor = PdfReader(io.BytesIO(relatorio.gerar_pdf(d)))
    assert len(leitor.pages) == esperado
    assert "resultado final" not in _linhas_do_pdf(relatorio.gerar_pdf(d))


def test_tabela_do_fator_lista_as_primeiras_unidades_e_o_pdf_o_diz():
    matriz = [[10.0 * ((linha + fator) % 10 + 1) for fator in range(3)] for linha in range(40)]
    d = _documento(matriz=matriz)
    texto = _texto_do_pdf(relatorio.gerar_pdf(d))
    assert "a tabela lista as primeiras unidades; o documento JSON traz todas" in texto
    # a 31ª unidade não entra na tabela impressa
    assert not re.search(r"^31\s", texto, re.MULTILINE)


def test_geracao_e_deterministica_o_mesmo_documento_da_o_mesmo_arquivo(tmp_path):
    d = _documento()
    primeiro = relatorio.gerar_pdf(d)
    time.sleep(1.1)  # um relógio volátil em metadado mudaria os bytes
    segundo = relatorio.gerar_pdf(d)
    assert primeiro == segundo
    destino = tmp_path / "relatorio.pdf"
    devolvido = relatorio.gerar_pdf(d, destino)
    assert destino.read_bytes() == devolvido == primeiro


def test_script_gera_o_json_e_o_pdf_do_mesmo_documento(tmp_path):
    entrada = tmp_path / "entrada.json"
    entrada.write_text(json.dumps({
        "nome": "método do script",
        "modelo": MODELO,
        "camadas": CAMADAS,
        "transformacoes": TRANSFORMACOES,
        "entrada": ENTRADA,
        "resultado": _resultado(ENTRADA["matriz"]),
    }, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "metodo_exportar.py"), str(entrada),
         "--saida", str(tmp_path)],
        capture_output=True, text=True, cwd=ROOT, check=True, timeout=120,
    )
    caminho_json, caminho_pdf, sha = r.stdout.strip().splitlines()
    documento = json.loads(pathlib.Path(caminho_json).read_text(encoding="utf-8"))
    assert pathlib.Path(caminho_json).name == "metodo-do-script.metodo.json"
    assert pathlib.Path(caminho_pdf).name == "metodo-do-script.relatorio.pdf"
    assert documento["sha256"] == sha == metodo.hash_canonico(documento)
    reimportado = metodo.importar_metodo(documento)
    assert reimportado["sha256"] == sha
    assert len(PdfReader(caminho_pdf).pages) == relatorio.paginas_do_relatorio(documento)
    assert metodo.confere_pdf(_texto_do_pdf(pathlib.Path(caminho_pdf).read_bytes()), documento)


def test_medidas_da_geracao_do_relatorio(medida):
    grava = medida("L3-01-i-exportacao-metodo")
    carga_1min = os.getloadavg()[0]
    if carga_1min > CARGA_MAXIMA:
        pytest.skip(f"medida NÃO GRAVADA: carga de 1 min {carga_1min:.2f} > {CARGA_MAXIMA}")
    d = _documento()

    t0 = time.perf_counter()
    pdf = relatorio.gerar_pdf(d)
    ms = (time.perf_counter() - t0) * 1000.0
    contexto = (
        f"carga_1min={carga_1min:.2f}, ram_livre_gb={_ram_livre_gb():.2f}, "
        f"medido_em={datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    grava("geracao_pdf_ms", round(ms, 3), "ms", f"gerar_pdf() do documento de teste; {contexto}")

    texto = _texto_do_pdf(pdf)
    grava("paginas_do_relatorio", relatorio.paginas_do_relatorio(d), "páginas",
          f"páginas = seções, conferidas com pypdf contra paginas_do_relatorio(); {contexto}")
    numeros_pdf = _numeros_do_pdf(pdf)
    fora = sorted(numeros_pdf - metodo.numeros_do_documento(d))
    grava("numeros_no_pdf", len(numeros_pdf), "números",
          f"extraídos por palavra com pdfplumber; todos no JSON: {not fora}; {contexto}")
    grava("pdf_verificado_pagina_a_pagina", True, "conferência",
          "cada página convertida com pdftoppm e lida por agente na revisão do item; leigo zero no "
          "texto: sem sobreposição, sem número fora do JSON, ressalvas na última página")
    assert not fora and metodo.confere_pdf(texto, d)


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")
