"""Item L7-03-f-dependencias-cve-log-correcoes (docs/SEGURANCA.md seção 7; scripts/varredura_dependencias.py).
Cobre a cláusula do portão sem depender de rede nem do estado real do `requirements.txt` no instante do teste
(o que o CVE de verdade da hora é fica só no teste de integração, marcado `lento`, no fim do arquivo): a CVE
"sintética" aqui é `rodar_pip_audit` trocado por um dublê (`monkeypatch`), exatamente como o portão pede
("pacote antigo colocado de propósito") sem precisar instalar um pacote vulnerável de verdade na venv."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import varredura_dependencias as vd  # noqa: E402 — módulo em scripts/, fora do pacote app


# ---------------------------------------------------------------- CVSS v3.1 (fórmula oficial FIRST)
def test_cvss_vetor_baixo_impacto_bate_com_o_rotulo_ghsa_moderado():
    # PYSEC-2026-215/GHSA-65pc-fj4g-8rjx (idna, MEDIDO 06/09/2026 no OSV.dev): rótulo pronto = "MODERATE".
    nota = vd.cvss_v3_nota("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L")
    assert nota == 5.3
    assert vd._severidade_da_nota(nota) == "media"


def test_cvss_vetor_critico_com_mudanca_de_escopo():
    # CVE-2021-44228 (Log4Shell) publicado com nota 10.0 pelo NVD para este vetor exato.
    nota = vd.cvss_v3_nota("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H")
    assert nota == 10.0
    assert vd._severidade_da_nota(nota) == "critica"


def test_cvss_vetor_alto_sem_mudanca_de_escopo():
    nota = vd.cvss_v3_nota("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    assert nota == 9.8
    assert vd._severidade_da_nota(nota) == "critica"


# ---------------------------------------------------------------- severidade_de (com OSV dublê em disco)
def test_severidade_de_usa_rotulo_pronto_do_alias_ghsa(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path)
    (tmp_path / "GHSA-xxxx.json").write_text(
        json.dumps({"database_specific": {"severity": "HIGH"}}), encoding="utf-8"
    )
    (tmp_path / "PYSEC-0001.json").write_text(json.dumps({}), encoding="utf-8")  # id em si não traz nada
    severidade, origem = vd.severidade_de("PYSEC-0001", ["GHSA-xxxx"], offline=True)
    assert severidade == "alta"
    assert origem == "rotulo:GHSA-xxxx"


def test_severidade_de_sem_qualquer_dado_e_desconhecida(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path)
    severidade, _ = vd.severidade_de("PYSEC-9999", [], offline=True)
    assert severidade == "desconhecida"


# ---------------------------------------------------------------- exceções (docs/excecoes_cve.json)
def test_excecao_expirada_nao_vale_mais():
    achado = {"id": "PYSEC-0001", "aliases": [], "pacote": "pacote-x"}
    excecoes = [{"cve": "PYSEC-0001", "pacote": "pacote-x", "prazo": "2020-01-01"}]
    assert vd.excecao_viva(achado, excecoes, hoje=__import__("datetime").date(2026, 9, 6)) is None


def test_excecao_viva_dentro_do_prazo():
    achado = {"id": "PYSEC-0001", "aliases": ["CVE-2026-1"], "pacote": "pacote-x"}
    excecoes = [{"cve": "CVE-2026-1", "pacote": "pacote-x", "prazo": "2099-01-01"}]
    exc = vd.excecao_viva(achado, excecoes, hoje=__import__("datetime").date(2026, 9, 6))
    assert exc is not None and exc["cve"] == "CVE-2026-1"


def test_excecao_nao_casa_pacote_errado():
    achado = {"id": "PYSEC-0001", "aliases": [], "pacote": "pacote-x"}
    excecoes = [{"cve": "PYSEC-0001", "pacote": "outro-pacote", "prazo": "2099-01-01"}]
    assert vd.excecao_viva(achado, excecoes) is None


# ---------------------------------------------------------------- avaliar() fim-a-fim, pip-audit dublado
def _dublar_pip_audit(monkeypatch, achados: list[dict]) -> None:
    monkeypatch.setattr(vd, "rodar_pip_audit", lambda *a, **k: achados)


def test_avaliar_reprova_cve_alto_sem_excecao(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path / "osv")
    _dublar_pip_audit(
        monkeypatch,
        [{"pacote": "pacote-velho", "versao": "0.1", "id": "PYSEC-ALTO", "aliases": [], "fix_versions": ["9.9"]}],
    )
    (tmp_path / "osv").mkdir()
    (tmp_path / "osv" / "PYSEC-ALTO.json").write_text(
        json.dumps({"database_specific": {"severity": "HIGH"}}), encoding="utf-8"
    )
    excecoes = tmp_path / "excecoes.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    r = vd.avaliar(tmp_path / "requirements.txt", excecoes, offline_severidade=True)
    assert r["reprovado"] is True
    assert r["achados"][0]["severidade"] == "alta"
    assert r["achados"][0]["bloqueia"] is True


def test_avaliar_passa_com_excecao_documentada_e_viva(tmp_path, monkeypatch):
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path / "osv")
    _dublar_pip_audit(
        monkeypatch,
        [{"pacote": "pacote-velho", "versao": "0.1", "id": "PYSEC-ALTO", "aliases": [], "fix_versions": ["9.9"]}],
    )
    (tmp_path / "osv").mkdir()
    (tmp_path / "osv" / "PYSEC-ALTO.json").write_text(
        json.dumps({"database_specific": {"severity": "HIGH"}}), encoding="utf-8"
    )
    excecoes = tmp_path / "excecoes.json"
    excecoes.write_text(
        json.dumps({"excecoes": [{"cve": "PYSEC-ALTO", "pacote": "pacote-velho", "motivo": "sem fix ainda",
                                    "prazo": "2099-01-01"}]}),
        encoding="utf-8",
    )
    r = vd.avaliar(tmp_path / "requirements.txt", excecoes, offline_severidade=True)
    assert r["reprovado"] is False
    assert r["achados"][0]["excecao"]["motivo"] == "sem fix ainda"


def test_avaliar_some_do_log_quando_corrigido(tmp_path, monkeypatch):
    """"...e some quando corrigida" do portão: o mesmo pip-audit, agora sem o achado (pacote atualizado), não
    aparece mais — não é preciso apagar nada à mão."""
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path / "osv")
    _dublar_pip_audit(monkeypatch, [])
    excecoes = tmp_path / "excecoes.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    r = vd.avaliar(tmp_path / "requirements.txt", excecoes, offline_severidade=True)
    assert r["achados"] == []
    assert r["reprovado"] is False


def test_avaliar_trata_severidade_desconhecida_como_grave(tmp_path, monkeypatch):
    """Padrão-seguro documentado na seção 7: sem CVSS e sem rótulo (rede fora ou OSV sem dado), o achado
    bloqueia como se fosse alto — nunca passa em silêncio."""
    monkeypatch.setattr(vd, "CACHE_DIR", tmp_path / "osv")
    _dublar_pip_audit(
        monkeypatch,
        [{"pacote": "pacote-obscuro", "versao": "1.0", "id": "PYSEC-SEMDADO", "aliases": [], "fix_versions": []}],
    )
    excecoes = tmp_path / "excecoes.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    r = vd.avaliar(tmp_path / "requirements.txt", excecoes, offline_severidade=True)
    assert r["achados"][0]["severidade"] == "desconhecida"
    assert r["reprovado"] is True


# ---------------------------------------------------------------- integração real (rede + venv), marcado lento
@pytest.mark.lento
def test_pip_audit_real_roda_contra_o_requirements_do_repo():
    r = vd.avaliar(ROOT / "requirements.txt", ROOT / "docs" / "excecoes_cve.json")
    assert isinstance(r["achados"], list)  # não afirma "0 CVE": só que o comando roda e devolve algo estruturado
