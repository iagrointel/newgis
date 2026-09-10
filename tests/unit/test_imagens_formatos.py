"""Item L1-01-f-formatos-de-entrada: a tabela canônica (`app.imagens.formatos`) e a prova de assinatura
(`app.raster.validacao.conferir_assinatura`) contra os binários commitados em `tests/dados/raster/`.

O portão pede: cada formato listado tem um arquivo aberto de teste; ECW/MrSID recusam com a mensagem exata;
a lista que a rota devolve é a MESMA tabela (cláusula 5, testada em tests/api/imagens/test_formatos_entrada.py).
Aqui são os invariantes baratos (sem subprocesso, sem banco): estrutura da tabela, mensagens exatas e o
(formato, problema) de assinatura de cada arquivo de teste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.imagens import formatos
from app.raster.validacao import conferir_assinatura

DADOS = Path(__file__).resolve().parents[1] / "dados" / "raster"

# o que o gerador de dados produz para cada formato da tabela (caminho relativo a tests/dados/raster)
ARQUIVO_POR_CHAVE = {
    "geotiff": "geotiff_sintetico.tif",
    "jpeg2000": "jpeg2000_sintetico.jp2",
    "erdas_img": "erdas_sintetico.img",
    "ascii_grid": "ascii_grid_sintetico.asc",
    "netcdf": "netcdf_sintetico.nc",
    "grib": "grib_sintetico.grb2",
}


def test_tabela_cobre_12_aceitos_e_4_recusados_com_extensoes():
    assert set(formatos.FORMATOS) == {
        "geotiff", "jpeg2000", "erdas_img", "envi", "ascii_grid", "png", "jpeg", "netcdf", "grib",
        "zarr", "kmz", "zip",
    }
    assert set(formatos.RECUSADOS) == {"ecw", "mrsid", "geopdf", "hdf5"}
    for f in formatos.FORMATOS.values():
        assert f.extensoes and all(e.startswith(".") for e in f.extensoes), f.chave
        assert f.rotulo and f.driver and f.georreferencia, f.chave
    for r in formatos.RECUSADOS.values():
        assert r.extensoes and r.rotulo and r.mensagem, r.chave


@pytest.mark.parametrize(("chave", "arquivo"), sorted(ARQUIVO_POR_CHAVE.items()))
def test_cada_formato_tem_binario_de_teste_com_a_assinatura_certa(chave, arquivo):
    """Cláusula 1 (base de dados): todo formato aceito da tabela tem um arquivo aberto em
    tests/dados/raster/ e os primeiros bytes provam que ele É daquele formato (extensão declara,
    bytes provam — a mesma conferência que a validação faz na chegada)."""
    caminho = DADOS / arquivo
    assert caminho.is_file(), f"formato {chave} sem binário de teste ({arquivo})"
    assert caminho.stat().st_size <= 20 * 1024 * 1024, "limite do portão: 20 MB por arquivo de teste"
    nome, problema = conferir_assinatura(caminho)
    assert problema is None, (arquivo, problema)
    assert nome == formatos.FORMATOS[chave].rotulo, (arquivo, nome)


def test_ecw_e_mrsid_recusam_com_a_mensagem_exata_da_tabela():
    """Cláusula 2: a recusa é a mensagem da tabela, ANTES da recusa genérica de extensão — e vale
    inclusive para um conteúdo que seria um GeoTIFF legítimo (os arquivos .ecw/.sid de teste são cópias
    de bytes de GeoTIFF: prova que a recusa é pela tabela de formatos, não por conteúdo corrompido)."""
    for chave, arquivo in (("ecw", "proprietario.ecw"), ("mrsid", "proprietario.sid")):
        recusado = formatos.recusado_por_extensao(Path(arquivo).suffix)
        assert recusado is not None and recusado.chave == chave
        nome, problema = conferir_assinatura(DADOS / arquivo)
        assert nome == "" and problema == recusado.mensagem, (arquivo, problema)
        assert "SDK proprietário" in problema and "Converta o arquivo" in problema


def test_recusa_por_conteudo_que_nao_corresponde_a_extensao():
    """TIFF renomeado .jp2: a extensão declara JP2, os bytes provam TIFF — a mensagem diz o que o
    conteúdo É, não um genérico 'arquivo inválido'."""
    nome, problema = conferir_assinatura(DADOS / "proprietario.ecw")  # cópia de TIFF com extensão de ECW
    assert problema is not None
    conferir = DADOS / "geotiff_sintetico.tif"
    conferir.with_suffix(".jp2").write_bytes(conferir.read_bytes())
    try:
        nome_jp2, problema_jp2 = conferir_assinatura(conferir.with_suffix(".jp2"))
        assert nome_jp2 == formatos.FORMATOS["jpeg2000"].rotulo
        assert problema_jp2 is not None and "TIFF" in problema_jp2 and "JPEG 2000" in problema_jp2, problema_jp2
    finally:
        conferir.with_suffix(".jp2").unlink()


def test_extensoes_de_fora_nao_passam():
    nome, problema = conferir_assinatura(DADOS / "geotiff_sintetico.tif")
    assert nome and problema is None
    # extensão que não está na tabela: recusa genérica lista os aceitos
    estranho = DADOS / "ascii_grid_sintetico.asc"
    nome, problema = conferir_assinatura(estranho.with_suffix(".xyz"))
    estranho.with_suffix(".xyz").unlink(missing_ok=True)
    assert nome == "" and problema is not None and "não é um formato raster aceito" in problema


def test_extensoes_em_zip_e_sidecars_cobrem_os_formatos_aceitos():
    esperado = {".tif", ".tiff", ".jp2", ".img", ".dat", ".bin", ".asc", ".png", ".jpg", ".jpeg",
                ".nc", ".grb", ".grb2"}
    assert set(formatos.EXTENSOES_RASTER_EM_ZIP) == esperado
    # contêineres nunca entram como cena de mosaico
    assert not ({"zip", "kmz", "zarr"} & {formatos.por_extensao(e).chave
                                          for e in formatos.EXTENSOES_RASTER_EM_ZIP})
    assert {".hdr", ".pgw", ".jgw", ".wld", ".prj", ".rrd"} <= set(formatos.SIDECARES_EM_ZIP)


def test_lista_da_tabela_e_o_que_a_rota_devolve():
    """O contrato com a rota `/api/imagens/formatos` (cláusula 5 começa aqui): aceitos com
    georreferência/observação, recusados com a mensagem; chaves únicas na lista inteira."""
    itens = formatos.lista()
    chaves = [i["chave"] for i in itens]
    assert len(chaves) == len(set(chaves))
    aceitos = [i for i in itens if i["aceito"]]
    recusados = [i for i in itens if not i["aceito"]]
    assert len(aceitos) == len(formatos.FORMATOS) and len(recusados) == len(formatos.RECUSADOS)
    assert all("georreferencia" in i and "observacao" in i for i in aceitos)
    assert all("mensagem" in i for i in recusados)
    # aceitos primeiro, ordem da tabela (a tela desenha nesta ordem)
    assert itens[: len(aceitos)] == aceitos
