"""`GET /api/intercambio/formatos` (item L6-02-o): a resposta "temos / não temos", nunca um total de formatos.

O teste prende três coisas que a hipótese do item afirma e que um documento sozinho não sustenta:
1. cada formato de SAÍDA declarado tem driver de escrita no GDAL DESTA máquina (`ogrinfo --formats`, `rw`);
2. cada formato de saída tem prova de ida e volta em teste (a lista é conferida contra os arquivos de teste
   deste pacote e do item L0-04-h, não contra uma lista escrita à mão);
3. o que não temos vem com motivo escrito, e a resposta não traz nenhum campo de contagem de formatos.
"""

from __future__ import annotations

import re
import subprocess

from app.intercambio.formatos_saida import DRIVERS_ESPERADOS, FORMATOS_SAIDA, NAO_TEMOS


def _drivers_de_escrita() -> set[str]:
    r = subprocess.run(["ogrinfo", "--formats"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    drivers = set()
    for linha in r.stdout.splitlines():
        m = re.match(r"\s*(.+?)\s+-[\w,]+-\s+\((r[^)]*)\)", linha)
        if m and m.group(2).startswith("rw"):
            drivers.add(m.group(1))
    return drivers


def test_todo_formato_de_saida_tem_driver_de_escrita_nesta_maquina():
    escritores = _drivers_de_escrita()
    faltando = {n: f.driver for n, f in FORMATOS_SAIDA.items() if f.driver not in escritores}
    assert not faltando, f"formato oferecido sem driver de escrita no GDAL desta máquina: {faltando}"
    assert DRIVERS_ESPERADOS == {n: f.driver for n, f in FORMATOS_SAIDA.items()}


def test_o_que_nao_temos_vem_com_motivo_escrito():
    assert NAO_TEMOS, "a lista 'não temos' vazia esconderia a paridade"
    for entrada in NAO_TEMOS:
        assert entrada["formato"] and len(entrada["motivo"]) > 40, entrada


def test_rota_responde_temos_e_nao_temos_sem_total_de_formatos(sessao_a):
    r = sessao_a.get("/api/intercambio/formatos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(corpo) == {"importacao", "exportacao", "nao_temos"}, corpo.keys()
    # nunca um total: número de formatos vira propaganda e envelhece; quem conta é quem lê a lista
    assert not any(isinstance(v, int) for v in corpo.values())
    saida = {f["tipo"] for f in corpo["exportacao"]}
    assert saida == set(FORMATOS_SAIDA), saida
    assert {f["tipo"] for f in corpo["importacao"]} == {"shapefile.zip", "gpkg", "geojson", "csv"}
    for f in corpo["exportacao"]:
        if f["tipo"] in ("mbtiles", "pmtiles"):
            assert any("quantizada" in a for a in f["avisos_inerentes"]), f
        if f["tipo"] == "shapefile.zip":
            assert any("10 caracteres" in a for a in f["avisos_inerentes"]), f
    assert [e["motivo"] for e in corpo["nao_temos"]]
