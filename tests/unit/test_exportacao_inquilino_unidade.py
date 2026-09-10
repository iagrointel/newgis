"""Testes de unidade do motor da exportação completa do inquilino (item L0-06-d-exportar-inquilino), sem
banco nem worker: sha256/manifesto, GeoPackage vazio válido e o JSON Schema publicado."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

from app.exportacao_inquilino import metadado, motor

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
    cat = manifesto["componentes"]["catalogo.json"]
    assert cat["sha256_conteudo"] == cat["sha256"]


def test_gpkg_vazio_e_valido_com_zero_camadas(tmp_path):
    """Catálogo sem camada hospedada: `gerar_gpkg` nunca chama o ogr2ogr contra o banco (cur não usado) e
    ainda assim devolve um GeoPackage válido que o `ogrinfo` reabre com zero camadas."""
    catalogo = {"itens": [{"id": "x", "tipo": "arquivo", "dados": {}}], "relacoes": []}
    destino = tmp_path / "dados.gpkg"
    escritas = motor.gerar_gpkg(cur=None, tenant_id=1, catalogo=catalogo, destino=destino)
    assert escritas == []
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


def test_metadado_grava_cartao_e_estilo_nas_tabelas_da_norma(tmp_path):
    """Hipótese do item: "estilo em JSON e metadado como tabelas gpkg_metadata". Aqui sem PostGIS: um
    GeoPackage feito de um GeoJSON pequeno, as duas linhas gravadas e lidas de volta pelo leitor."""
    import subprocess

    origem = tmp_path / "p.geojson"
    origem.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"n":1},'
        '"geometry":{"type":"Point","coordinates":[-46.5,-23.5]}}]}', encoding="utf-8"
    )
    gpkg = tmp_path / "dados.gpkg"
    r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(gpkg), str(origem), "-nln", "c_abc"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    camada = {"id": "11111111-1111-1111-1111-111111111111", "tipo": "camada_vetorial",
              "titulo": "zt camada", "resumo": "resumo", "descricao": None, "tags": ["zt"],
              "acesso": "privado", "origem": "hospedado", "criado_em": None, "modificado_em": None}
    estilo = {"id": "22222222-2222-2222-2222-222222222222", "tipo": "estilo", "titulo": "zt estilo",
              "dados": {"version": 8, "layers": [{"id": "l", "type": "circle"}]}}
    catalogo = {"itens": [camada, estilo],
                "relacoes": [{"origem": estilo["id"], "destino": camada["id"], "tipo": "estilo",
                              "posicao": 0}]}
    assert metadado.gravar(gpkg, [("c_abc", camada)], catalogo) == 2

    lidas = metadado.ler(gpkg)
    assert [ln["tabela"] for ln in lidas] == ["c_abc", "c_abc"]
    assert all(ln["mime_type"] == "application/json" for ln in lidas)
    cartao = next(ln for ln in lidas if ln["uri"] == metadado.URI_ITEM)["documento"]
    assert cartao["id"] == camada["id"] and cartao["titulo"] == "zt camada"
    simbologia = next(ln for ln in lidas if ln["uri"] == metadado.URI_ESTILO)["documento"]
    assert simbologia["version"] == 8

    # o ogrinfo continua reabrindo o arquivo (as tabelas da extensão não o corromperam)
    rr = subprocess.run(["ogrinfo", "-so", str(gpkg), "c_abc"], capture_output=True, text=True)
    assert rr.returncode == 0, rr.stderr


def test_metadado_de_gpkg_sem_a_extensao_le_vazio(tmp_path):
    import subprocess

    origem = tmp_path / "q.geojson"
    origem.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    gpkg = tmp_path / "sem.gpkg"
    subprocess.run(["ogr2ogr", "-f", "GPKG", str(gpkg), str(origem), "-nln", "v"],
                   capture_output=True, text=True)
    assert metadado.ler(gpkg) == []


def test_estimativa_soma_camada_arquivo_e_catalogo():
    """`estimar_bytes` sem banco: um cursor de mentira devolve o tamanho da tabela e o resto vem do catálogo.
    (Com banco de verdade quem cobre é o teste de API.)"""

    class CursorDeTamanho:
        def execute(self, sql, args=None):
            self._linha = {"n": 5 * 1024 * 1024}

        def fetchone(self):
            return self._linha

    catalogo = {"itens": [
        {"id": "a", "tipo": "camada_vetorial", "titulo": "c", "tamanho_bytes": 0,
         "dados": {"fonte": "hospedada", "schema": "d_zt", "tabela": "t"}},
        {"id": "b", "tipo": "arquivo", "titulo": "f", "tamanho_bytes": 1000,
         "dados": {"chave": "zt/1.bin"}},
    ]}
    e = motor.estimar_bytes(CursorDeTamanho(), catalogo)
    assert e["n_camadas"] == 1 and e["n_arquivos"] == 1 and e["n_itens"] == 2
    assert e["bytes_camadas"] == 5 * 1024 * 1024
    assert e["bytes_arquivos"] == 1000
    assert e["bytes_catalogo"] == 2 * 4096
    assert e["bytes"] == e["bytes_camadas"] + e["bytes_arquivos"] + e["bytes_catalogo"]
