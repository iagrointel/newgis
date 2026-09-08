"""Testes de unidade da exportação (item L0-04-h-exportar): reescrita do CSV, saneamento do erro do banco,
catálogo de formatos e — o que o gerente exigiu por escrito neste item — a PROVA de que um arquivo grande
nunca é montado inteiro em memória no envio ao armazenamento.

Nenhum deles precisa de banco, de Garage nem de rede: o cliente S3 é substituído por um espião que só anota
o tamanho de cada parte recebida. É de propósito — a pergunta "quanto de RAM isso usa" tem de ser respondida
com uma medição determinística (`tracemalloc`), não com a sorte do ambiente.
"""

from __future__ import annotations

import math
import tracemalloc

import pytest

from app import limites, objetos
from app.exportacao import csv_saida, erros
from app.exportacao.formatos import FORMATOS, obter


# ---------------------------------------------------------------- catálogo de formatos
def test_catalogo_de_formatos_com_extensao_e_tipo_unicos():
    """Eram 11 no L0-04-h; o L2-01-l acrescentou GeoJSON Sequence, File Geodatabase, MVT, PMTiles e o
    `pacote` de mapa. `reabre_com_ogrinfo` é o conjunto que o portão do L2-01-l chama de "os 12"."""
    assert len(FORMATOS) == 16, sorted(FORMATOS)
    assert sum(1 for f in FORMATOS.values() if f.reabre_com_ogrinfo) == 14
    assert sum(1 for f in FORMATOS.values()
               if f.reabre_com_ogrinfo and not f.tilado and f.nome != "pacote") == 12
    for nome, f in FORMATOS.items():
        assert f.nome == nome and f.extensao.startswith(".") and f.content_type
        assert "UTF-8" in f.codificacoes
    # todo tipo de conteúdo de formato tem extensão declarada no adaptador de objetos (senão o multipart
    # gravaria o objeto com a extensão errada — `parte_concluir` deriva a extensão daí)
    for f in FORMATOS.values():
        assert f.content_type in objetos.EXTENSOES, f.content_type


def test_formato_desconhecido_devolve_none():
    assert obter("shp") is None and obter("") is None and obter("GPKG").nome == "gpkg"


# ---------------------------------------------------------------- CSV brasileiro
def _csv(tmp_path, texto: str):
    caminho = tmp_path / "saida.csv"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_csv_padrao_nao_e_reescrito(tmp_path):
    caminho = _csv(tmp_path, "X,Y,nome\n-46.5,-23.4,ponto 1\n")
    r = csv_saida.reescrever(caminho)
    assert r["reescrito"] is False
    assert caminho.read_text(encoding="utf-8") == "X,Y,nome\n-46.5,-23.4,ponto 1\n"


def test_csv_com_virgula_decimal_troca_so_numero(tmp_path):
    caminho = _csv(tmp_path, "X,Y,nome,codigo\n-46.5,-23.4,rua 25.5 do lado,1.2.3\n")
    r = csv_saida.reescrever(caminho, separador=";", decimal=",", coluna_x="longitude", coluna_y="latitude")
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "longitude;latitude;nome;codigo"
    assert linhas[1] == "-46,5;-23,4;rua 25.5 do lado;1.2.3", linhas[1]
    assert r["trocas_decimais"] == 2 and r["linhas"] == 1


def test_csv_em_latin1_grava_na_codificacao_pedida(tmp_path):
    caminho = _csv(tmp_path, "X,Y,nome\n-46.5,-23.4,ação\n")
    csv_saida.reescrever(caminho, separador=";", decimal=",", codificacao="ISO-8859-1")
    bruto = caminho.read_bytes()
    assert "ação".encode("iso-8859-1") in bruto
    assert "ação".encode() not in bruto


def test_csv_com_separador_dentro_do_texto_sai_entre_aspas(tmp_path):
    caminho = _csv(tmp_path, 'X,Y,nome\n-46.5,-23.4,"praça; do centro"\n')
    csv_saida.reescrever(caminho, separador=";", decimal=",")
    linha = caminho.read_text(encoding="utf-8").splitlines()[1]
    assert linha == '-46,5;-23,4;"praça; do centro"', linha


# ---------------------------------------------------------------- erro do banco saneado
class ErroFalso(Exception):
    class diag:  # noqa: N801 — imita o objeto `diag` do psycopg2
        message_primary = ""
        sqlstate = "42883"


@pytest.mark.parametrize(
    "primaria,proibido",
    [
        ('operator does not exist: integer > text\nLINE 1: SELECT * FROM "d_zt-inq-ab12"."c_0123456789abcdef"',
         ["LINE 1", "c_0123456789abcdef", "d_zt-inq-ab12"]),
        ('relation "d_demo.c_deadbeefdeadbeef" does not exist', ["c_deadbeefdeadbeef"]),
        ("could not open file /var/lib/postgresql/16/main/base/1234", ["/var/lib/postgresql"]),
    ],
)
def test_erro_do_banco_perde_nome_interno_comando_e_caminho(primaria, proibido):
    e = ErroFalso()
    e.diag.message_primary = primaria
    mensagem, sqlstate = erros.sanear_erro_banco(e)
    assert mensagem
    for vazamento in proibido:
        assert vazamento not in mensagem, (vazamento, mensagem)
    assert len(mensagem) <= limites.EXPORTACAO_ERRO_BANCO_MAX
    assert sqlstate == "42883"


def test_excecao_sem_diagnostico_nao_devolve_o_texto_da_excecao():
    """`str(e)` do psycopg2 pode carregar o comando inteiro; sem `diag`, só a classe sai."""
    mensagem, sqlstate = erros.sanear_erro_banco(RuntimeError("SELECT senha_hash FROM plat.usuario"))
    assert "senha_hash" not in mensagem and "SELECT" not in mensagem
    assert "RuntimeError" in mensagem and sqlstate is None


# ---------------------------------------------------------------- arquivo grande: envio em partes
class ClienteEspiao:
    """Substitui o cliente S3: guarda só o TAMANHO de cada parte (nunca o conteúdo — guardar o conteúdo aqui
    inflaria a memória do próprio teste e falsearia a medição)."""

    def __init__(self):
        self.partes: list[int] = []
        self.puts: list[int] = []

    def head(self, *_a, **_k):
        return None

    def put(self, _bucket, _chave, dados, _tipo="application/octet-stream"):
        self.puts.append(len(dados))
        return "etag"

    def multipart_iniciar(self, *_a, **_k):
        return "upload-de-teste"

    def multipart_enviar_parte(self, _bucket, _chave, _upload, numero, dados):
        self.partes.append(len(dados))
        return f"etag-{numero}"

    def multipart_concluir(self, *_a, **_k):
        return None

    def get_stream(self, _bucket, _chave, pedaco_bytes=1024 * 1024):
        total = sum(self.partes)
        enviados = 0
        while enviados < total:
            n = min(pedaco_bytes, total - enviados)
            enviados += n
            yield b"\0" * n

    def copiar(self, *_a, **_k):
        return None

    def delete(self, *_a, **_k):
        return None


class CursorFalso:
    """Cursor mínimo: as consultas que `guardar_arquivo` faz no caminho de metadado não interessam aqui."""

    def __init__(self):
        self.comandos: list[str] = []

    def execute(self, sql, params=None):
        self.comandos.append(sql)

    def fetchone(self):
        return None


@pytest.fixture
def sem_garage(monkeypatch):
    espiao = ClienteEspiao()
    bucket = {"tenant_id": 1, "bucket_alias": "t-teste", "bucket_id": "b", "cota_bytes": 10 ** 12,
              "chave_rw_id": "k", "chave_rw_segredo": "s", "chave_ro_id": "k", "chave_ro_segredo": "s"}
    monkeypatch.setattr(objetos, "_cliente", lambda *_a, **_k: espiao)
    monkeypatch.setattr(objetos, "garantir_bucket", lambda *_a, **_k: bucket)
    monkeypatch.setattr(objetos, "_tenant_atual", lambda _cur: (1, "teste"))
    monkeypatch.setattr(objetos, "_linha_bucket", lambda *_a, **_k: bucket)
    monkeypatch.setattr(objetos, "_registrar_metadado", lambda *_a, **_k: None)
    monkeypatch.setattr(objetos, "_upload_linha", lambda *_a, **_k: {
        "tenant_id": 1, "classe": "exportacao", "referencia": None, "content_type": "application/geo+json",
        "chave_temp": "_tmp/teste"})
    monkeypatch.setattr(objetos, "_admin", lambda: type("A", (), {"info_bucket": lambda *_a: {"bytes": 0}})())
    return espiao


def test_arquivo_grande_sobe_em_partes_sem_ir_inteiro_para_a_memoria(tmp_path, sem_garage):
    """40 MiB de arquivo, parte de 8 MiB: 5 partes, e o pico de memória alocada pelo Python durante o envio
    fica abaixo de 3 partes. É a prova pedida no item: `guardar_arquivo` lê em blocos, nunca o arquivo todo
    (a casa já derrubou o Postgres uma vez com um processo que segurou tudo em RAM)."""
    tamanho = 40 * 1024 * 1024
    caminho = tmp_path / "grande.geojson"
    with caminho.open("wb") as f:
        for _ in range(tamanho // (1024 * 1024)):
            f.write(b"x" * (1024 * 1024))

    cur = CursorFalso()
    tracemalloc.start()
    antes = tracemalloc.get_traced_memory()[0]
    objetos.guardar_arquivo(cur, "exportacao", caminho, "application/geo+json", extensao=".geojson")
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    parte = limites.ARQUIVO_PARTE_BYTES
    assert sem_garage.partes, "nada foi enviado em partes"
    assert len(sem_garage.partes) == math.ceil(tamanho / parte), sem_garage.partes
    assert max(sem_garage.partes) <= parte
    assert sum(sem_garage.partes) == tamanho
    assert not sem_garage.puts, "arquivo grande não pode ir num PUT único"
    assert (pico - antes) < 3 * parte, f"pico de {pico - antes} bytes para um arquivo de {tamanho}"


def test_arquivo_pequeno_vai_num_put_unico(tmp_path, sem_garage):
    caminho = tmp_path / "pequeno.geojson"
    caminho.write_bytes(b"{}" * 1024)
    objetos.guardar_arquivo(CursorFalso(), "exportacao", caminho, "application/geo+json")
    assert len(sem_garage.puts) == 1 and not sem_garage.partes


def test_arquivo_vazio_e_recusado(tmp_path, sem_garage):
    caminho = tmp_path / "vazio.geojson"
    caminho.write_bytes(b"")
    with pytest.raises(ValueError, match="vazio"):
        objetos.guardar_arquivo(CursorFalso(), "exportacao", caminho, "application/geo+json")


def test_nome_de_arquivo_nunca_vira_caminho():
    from app.exportacao import motor

    assert motor.nome_arquivo_seguro("../../etc/passwd", ".gpkg") == "etc_passwd.gpkg"
    assert motor.nome_arquivo_seguro("", ".csv") == "exportacao.csv"
    assert motor.nome_arquivo_seguro("a" * 500, ".csv") == "a" * limites.EXPORTACAO_NOME_MAX + ".csv"
    assert "/" not in motor.nome_arquivo_seguro("pasta/arquivo", ".csv")
