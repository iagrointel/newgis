"""Unidade do núcleo puro do backup lógico (item L0-06-a): seleção da retenção (o 15º diário e o 9º semanal
saem; semanal não come a vaga dos diários; agrupamento por schema), nome de arquivo, manifesto por inquilino
e a checagem de espaço que falha ANTES de escrever."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.backup import nucleo


def _linha(i: int, esquema: str, semanal: bool, dias_atras: float) -> dict:
    return {"id": i, "esquema": esquema, "semanal": semanal,
            "criado_em": datetime(2026, 9, 6, tzinfo=UTC) - timedelta(days=dias_atras)}


def test_decimo_quinto_diario_sai():
    linhas = [_linha(i, "d_demo2", False, i) for i in range(1, 16)]  # 15 diários; id maior = mais velho
    apagar = nucleo.selecao_retencao(linhas, manter_diarios=14, manter_semanais=8)
    assert apagar == [15]  # o mais velho (id 15, 15 dias atrás) é o 15º


def test_nono_semanal_sai():
    linhas = [_linha(i, "d_demo2", True, 7 * i) for i in range(1, 10)]  # 9 semanais; id maior = mais velho
    apagar = nucleo.selecao_retencao(linhas, manter_diarios=14, manter_semanais=8)
    assert apagar == [9]


def test_semanal_nao_come_vaga_de_diario():
    linhas = ([_linha(100 + i, "d_demo2", False, i) for i in range(1, 15)]
              + [_linha(200 + i, "d_demo2", True, 7 * i) for i in range(1, 9)])
    apagar = nucleo.selecao_retencao(linhas)
    assert apagar == []  # 14 diários + 8 semanais é exatamente o teto


def test_retencao_e_por_schema():
    linhas = ([_linha(i, "d_demo", False, i) for i in range(1, 16)]
              + [_linha(100 + i, "d_demo2", False, i) for i in range(1, 3)])
    apagar = nucleo.selecao_retencao(linhas, manter_diarios=14)
    assert apagar == [15]  # só o d_demo transborda; d_demo2 tem 2 e fica inteiro


def test_ordem_de_entrada_nao_importa():
    novos = [_linha(i, "plat", False, i) for i in range(20)]
    invertidos = list(reversed(novos))
    assert nucleo.selecao_retencao(novos, manter_diarios=14) == \
        nucleo.selecao_retencao(invertidos, manter_diarios=14)


def test_nome_arquivo():
    nome = nucleo.nome_arquivo("d_demo2", datetime(2026, 9, 6, 21, 30, 5, tzinfo=UTC))
    assert nome == "d_demo2_20260906_213005.dump"


def test_e_semanal_so_domingo():
    domingo = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)   # 06/09/2026 é domingo
    segunda = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    assert nucleo.e_semanal(domingo) is True
    assert nucleo.e_semanal(segunda) is False


def test_manifesto_tem_chave_sha_e_bytes_ordenados():
    doc = json.loads(nucleo.manifesto_inquilino("demo2", [
        {"chave": "demo2/b.dump", "sha256": "b" * 64, "bytes": 2},
        {"chave": "demo2/a.dump", "sha256": "a" * 64, "bytes": 1},
    ], datetime(2026, 9, 6, tzinfo=UTC)))
    assert doc["inquilino"] == "demo2"
    assert [o["chave"] for o in doc["objetos"]] == ["demo2/a.dump", "demo2/b.dump"]
    assert doc["objetos"][0]["sha256"] == "a" * 64
    assert doc["objetos"][0]["bytes"] == 1


def test_espaco_falha_antes_de_escrever(tmp_path, monkeypatch):
    monkeypatch.setattr(nucleo, "espaco_livre_bytes", lambda c: 5 * 1_000_000_000)
    with pytest.raises(nucleo.EspacoInsuficiente) as exc:
        nucleo.conferir_espaco(tmp_path, 10)
    assert "5.0 GB" in str(exc.value) and "10.0 GB" in str(exc.value)


def test_espaco_suficiente_devolve_livre(tmp_path, monkeypatch):
    monkeypatch.setattr(nucleo, "espaco_livre_bytes", lambda c: 35 * 1_000_000_000)
    assert nucleo.conferir_espaco(tmp_path, 10) == 35 * 1_000_000_000


def test_sha256_arquivo_confere(tmp_path):
    import hashlib

    p = tmp_path / "x.dump"
    p.write_bytes(b"conteudo" * 1000)
    assert nucleo.sha256_arquivo(p) == hashlib.sha256(b"conteudo" * 1000).hexdigest()


def test_sha256_acusa_1_byte_corrompido(tmp_path):
    p = tmp_path / "x.dump"
    p.write_bytes(b"a" * 4096)
    antes = nucleo.sha256_arquivo(p)
    with open(p, "r+b") as f:
        f.seek(100)
        f.write(b"b")
    assert nucleo.sha256_arquivo(p) != antes
