"""Escrow do inquilino inteiro (cláusula 3 do portão do item L6-02-o: 'export do inquilino com 20 camadas em
tempo medido'). Reusa `plat.camada_preparar` via `semear_camada` (mesma fixture de L0-04-h-exportar) para
criar 20 camadas pequenas no MESMO inquilino, pede a exportação tipo='inquilino' e confere o GeoPackage +
o manifesto JSON."""

from __future__ import annotations

import json
import time
import zipfile

from tests.api.intercambio.conftest import baixar_intercambio, exportar_intercambio


def test_escrow_do_inquilino_com_20_camadas_em_tempo_medido(inquilino_ic, camadas_20, worker_intercambio,
                                                             tmp_path, medida):
    cliente = inquilino_ic.admin
    inicio = time.monotonic()
    final = exportar_intercambio(cliente, {"tipo": "inquilino"}, timeout=300)
    segundos = round(time.monotonic() - inicio, 2)
    assert final["estado"] == "concluida", final
    relatorio = final["relatorio"]
    assert relatorio["camadas"] >= 20, relatorio
    assert relatorio["feicoes"] >= 20 * 100, relatorio

    caminho = baixar_intercambio(cliente, final["id"], tmp_path / "escrow.zip")
    with zipfile.ZipFile(caminho) as zf:
        nomes = zf.namelist()
        assert "escrow.gpkg" in nomes and "manifesto.json" in nomes, nomes
        manifesto = json.loads(zf.read("manifesto.json"))
        zf.extract("escrow.gpkg", tmp_path)

    assert len(manifesto["camadas"]) >= 20, manifesto["camadas"]
    assert manifesto["feicoes_total"] == relatorio["feicoes"]
    assert manifesto["gpkg"]["sha256"] == relatorio["sha256_gpkg"]

    import hashlib

    gpkg_path = tmp_path / "escrow.gpkg"
    sha_real = hashlib.sha256(gpkg_path.read_bytes()).hexdigest()
    assert sha_real == manifesto["gpkg"]["sha256"], "sha256 do manifesto não bate com o arquivo baixado"

    import subprocess

    r = subprocess.run(["ogrinfo", "-so", str(gpkg_path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    camadas_no_gpkg = [ln for ln in r.stdout.splitlines() if ln.strip() and ln.strip()[0].isdigit()]
    assert len(camadas_no_gpkg) >= 20, r.stdout

    medida("L6-02-o-importacao-exportacao-formatos")(
        "escrow_20_camadas_segundos", segundos, "s (pedido -> arquivo pronto, 20 camadas x 100 feições)",
        "tests/api/intercambio/test_escrow_inquilino.py::"
        "test_escrow_do_inquilino_com_20_camadas_em_tempo_medido",
    )


def test_escrow_sem_camada_e_recusado(sessao_plat, worker_intercambio):
    from tests.api.exportacao.conftest import InquilinoDeExportacao
    from tests.api.intercambio.conftest import esperar_intercambio

    inq = InquilinoDeExportacao(sessao_plat)
    try:
        r = inq.admin.post("/api/intercambio/exportacoes", json={"tipo": "inquilino"})
        assert r.status_code == 202, r.text
        final = esperar_intercambio(inq.admin, r.json()["exportacao_id"], timeout=60)
        assert final["estado"] == "falhou", final
        assert "camada vetorial" in (final["erro"] or ""), final
    finally:
        inq.apagar()
