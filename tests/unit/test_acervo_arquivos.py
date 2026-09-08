"""Guardas do acervo de ARQUIVO (item L6-01-i-raster-e-arquivos, `app/acervo/arquivos.py`), sem banco: conferência
de sha256 antes de ingerir (a refutação do item vive aqui: 1 byte alterado = recusa), teto de tamanho por arquivo
(guardrail de disco D21), caminho preso à raiz configurada e classificação raster × vetor."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from app import limites
from app import settings as mod_settings
from app.acervo import arquivos as arq


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    """Raiz de acervo própria do teste (nunca a da casa: o teste altera bytes de propósito)."""
    monkeypatch.setattr(arq, "settings", dataclasses.replace(mod_settings.settings,
                                                             PLAT_ACERVO_ARQUIVOS_RAIZ=str(tmp_path)))
    return tmp_path


def _criar(raiz, rel: str, conteudo: bytes) -> dict:
    alvo = raiz / rel
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(conteudo)
    return {"caminho": rel, "sha256": hashlib.sha256(conteudo).hexdigest(), "bytes": len(conteudo)}


def test_conferir_aceita_quando_o_hash_bate(raiz):
    reg = _criar(raiz, "camada/pontos.geojson", b'{"type":"FeatureCollection","features":[]}')
    a = arq.conferir(reg)
    assert a.tipo == "vetor" and a.extensao == "geojson" and a.sha256_registro == reg["sha256"]
    assert a.absoluto == (raiz / "camada/pontos.geojson")


# refutação do item: adversário altera 1 byte do arquivo da fixture
def test_um_byte_alterado_recusa_por_hash(raiz):
    reg = _criar(raiz, "camada/dem.tif", b"II*\x00" + b"\x01" * 4096)
    assert arq.conferir(reg).tipo == "raster"  # antes de mexer, passa
    alvo = raiz / "camada/dem.tif"
    dados = bytearray(alvo.read_bytes())
    dados[2048] ^= 0x01  # UM bit de UM byte, no meio do arquivo; o tamanho não muda
    alvo.write_bytes(bytes(dados))
    assert alvo.stat().st_size == reg["bytes"]
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.conferir(reg)
    assert e.value.erro == "hash_divergente" and e.value.status_code == 422
    assert e.value.detalhe["sha256_registro"] == reg["sha256"]
    assert e.value.detalhe["sha256_arquivo"] != reg["sha256"]
    assert e.value.detalhe["sha256_arquivo"] == hashlib.sha256(alvo.read_bytes()).hexdigest()


def test_arquivo_ausente_e_registro_sem_hash(raiz):
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.conferir({"caminho": "nao/existe.geojson", "sha256": "a" * 64})
    assert e.value.erro == "arquivo_ausente"
    reg = _criar(raiz, "x.geojson", b"{}")
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.conferir({**reg, "sha256": None})
    assert e.value.erro == "sem_hash_no_registro"


def test_teto_de_tamanho_e_extensao(raiz, monkeypatch):
    reg = _criar(raiz, "grande.geojson", b"x" * 5000)
    monkeypatch.setattr(limites, "ACERVO_ARQUIVO_BYTES_MAX", 1000)
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.conferir(reg)
    assert e.value.erro == "arquivo_grande_demais" and e.value.detalhe["teto"] == 1000
    monkeypatch.setattr(limites, "ACERVO_ARQUIVO_BYTES_MAX", 2 * 1024 * 1024 * 1024)
    reg = _criar(raiz, "planilha.xlsx", b"x")
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.conferir(reg)
    assert e.value.erro == "extensao_nao_suportada"


def test_caminho_nunca_sai_da_raiz(raiz):
    (raiz / "dentro").mkdir()
    for ruim in ("../../etc/passwd", "/etc/passwd", "dentro/../../fora.geojson"):
        with pytest.raises(arq.ArquivoRecusado) as e:
            arq.resolver(ruim)
        assert e.value.erro == "fora_da_raiz", ruim
    assert arq.resolver("dentro/ok.geojson") == raiz / "dentro" / "ok.geojson"


def test_sem_raiz_configurada_nao_e_erro_de_servidor(monkeypatch):
    monkeypatch.setattr(arq, "settings", dataclasses.replace(mod_settings.settings, PLAT_ACERVO_ARQUIVOS_RAIZ=None))
    assert arq.configurado() is False and arq.raiz() is None
    with pytest.raises(arq.ArquivoRecusado) as e:
        arq.resolver("qualquer.tif")
    assert e.value.erro == "acervo_sem_raiz"


def test_classificacao_raster_x_vetor():
    for r in ("a.tif", "b.TIFF", "c/d.vrt"):
        assert arq.tipo_de(r) == "raster", r
    for v in ("a.geojson", "b.gpkg", "c.shp", "d.parquet", "e.csv"):
        assert arq.tipo_de(v) == "vetor", v


def test_hash_em_fluxo_nao_carrega_o_arquivo_inteiro(raiz, monkeypatch):
    """Arquivo de gigabytes nunca passa inteiro pela memória: a leitura é por blocos de 1 MiB."""
    reg = _criar(raiz, "grandinho.tif", b"II*\x00" + b"ab" * (3 * 1024 * 1024))
    blocos = {"n": 0}
    original = arq.LEITURA_BLOCO
    real_open = open

    def contar(caminho, modo="rb", *a, **k):
        f = real_open(caminho, modo, *a, **k)
        leitura = f.read

        def read(n=-1):
            if n == original:
                blocos["n"] += 1
            return leitura(n)

        f.read = read
        return f

    monkeypatch.setattr("builtins.open", contar)
    assert arq.sha256_do_arquivo(raiz / "grandinho.tif") == reg["sha256"]
    assert blocos["n"] >= 6  # 6 MiB lidos em blocos de 1 MiB
