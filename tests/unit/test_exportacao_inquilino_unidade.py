"""Testes de unidade do motor da exportação completa do inquilino (item L0-06-d-exportar-inquilino), sem
banco nem worker: sha256/manifesto, GeoPackage vazio válido e o JSON Schema publicado."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

from app.exportacao_inquilino import motor

ROOT = Path(__file__).resolve().parents[2]
ESQUEMA = json.loads((ROOT / "docs" / "esquemas" / "exportacao_inquilino.schema.json").read_text(encoding="utf-8"))


def test_sha256_arquivo_muda_com_um_byte(tmp_path):
    a = tmp_path / "a.bin"
    a.write_bytes(b"conteudo de teste" * 1000)
    h1 = motor.sha256_arquivo(a)
    dados = bytearray(a.read_bytes())
    dados[0] ^= 0xFF
    a.write_bytes(bytes(dados))
    h2 = motor.sha256_arquivo(a)
    assert h1 != h2
    assert len(h1) == 64


def test_manifesto_confere_sha256_e_bytes(tmp_path):
    a = tmp_path / "x.txt"
    a.write_text("um dois tres", encoding="utf-8")
    b = tmp_path / "catalogo.json"
    b.write_text('{"itens": []}', encoding="utf-8")
    manifesto = motor.montar_manifesto({"x.txt": a, "catalogo.json": b}, motor.sha256_bytes(b.read_bytes()))
    assert manifesto["componentes"]["x.txt"]["sha256"] == motor.sha256_arquivo(a)
    assert manifesto["componentes"]["x.txt"]["bytes"] == a.stat().st_size
    assert manifesto["componentes"]["catalogo.json"]["sha256_conteudo"] == manifesto["componentes"]["catalogo.json"]["sha256"]


def test_gpkg_vazio_e_valido_com_zero_camadas(tmp_path):
    """Catálogo sem camada hospedada: `gerar_gpkg` nunca chama o ogr2ogr contra o banco (cur não usado) e
    ainda assim devolve um GeoPackage válido que o `ogrinfo` reabre com zero camadas."""
    catalogo = {"itens": [{"id": "x", "tipo": "arquivo", "dados": {}}]}
    destino = tmp_path / "dados.gpkg"
    n = motor.gerar_gpkg(cur=None, tenant_id=1, catalogo=catalogo, destino=destino)
    assert n == 0
    assert destino.exists()
    r = subprocess.run(["ogrinfo", "-so", str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    camadas = [ln for ln in r.stdout.splitlines() if ln.strip() and ln[0].isdigit() and ":" in ln]
    assert camadas == []


def test_empacotar_junta_os_quatro_componentes(tmp_path):
    import zipfile

    componentes = {}
    for nome in ("dados.gpkg", "catalogo.json", "arquivos.zip", "manifesto.json"):
        caminho = tmp_path / nome
        caminho.write_bytes(nome.encode("utf-8"))
        componentes[nome] = caminho
    destino = tmp_path / "pacote.zip"
    motor.empacotar(destino, componentes)
    with zipfile.ZipFile(destino) as z:
        assert set(z.namelist()) == set(componentes)


def test_catalogo_minimo_valida_contra_o_esquema_publicado():
    catalogo = {
        "versao_esquema": 1, "tenant_id": 1, "itens": [], "pastas": [], "grupos": [],
        "compartilhamentos": [], "relacoes": [], "usuarios": [
            {"id": 1, "login": "admin", "nome": "Admin", "perfil": "admin"}
        ],
    }
    jsonschema.validate(catalogo, ESQUEMA)


def test_esquema_recusa_usuario_com_hash_de_senha():
    catalogo = {
        "versao_esquema": 1, "tenant_id": 1, "itens": [], "pastas": [], "grupos": [],
        "compartilhamentos": [], "relacoes": [], "usuarios": [
            {"id": 1, "login": "admin", "nome": "Admin", "perfil": "admin", "senha_hash": "x"}
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(catalogo, ESQUEMA)
