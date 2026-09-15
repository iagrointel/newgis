"""Item L7-03-f-dependencias-cve-log-correcoes (docs/SEGURANCA.md seção 7.6; scripts/varredura_cve.py +
app/jobs/seguranca.py + db/migracoes/20260915T2252_vulnerabilidade.sql + docs/gerar_correcoes.py).

Duas partes: (1) `rodar()` puro — pip-audit e npm dublados por monkeypatch, sem rede e sem venv com pip-audit
instalado (mesmo espírito de `tests/unit/test_varredura_dependencias.py`, que continua sendo a fonte de
verdade da severidade/CVSS — nada disso é reimplementado aqui); (2) o ciclo completo em banco, na trilha
corrente (`app.db.db()`, mesma receita de `tests/unit/test_db_contexto.py`): um achado sintético vira linha
ABERTA em `plat.vulnerabilidade` e ganha `resolvida_em` quando some de uma varredura para a próxima — mas só
se a fonte dele rodou com sucesso na rodada (uma fonte "sem rede" não pode fechar achado por ausência de
dado). `docs/gerar_correcoes.py` é conferido à parte, com dados fixos (determinístico, sem depender do que a
trilha tem agora)."""

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "docs"))

import gerar_correcoes as gc  # noqa: E402 — módulo em docs/, fora do pacote app
import varredura_cve as vc  # noqa: E402 — módulo em scripts/, fora do pacote app
import varredura_dependencias as vd  # noqa: E402
import varredura_seguranca as vs  # noqa: E402

from app import db  # noqa: E402


# ---------------------------------------------------------------- rodar() puro (sem rede, sem banco)
def test_rodar_normaliza_achado_de_pip_audit(monkeypatch):
    monkeypatch.setattr(vd, "avaliar", lambda *a, **k: {
        "requirements": "x", "reprovado": True,
        "achados": [{"pacote": "pacote-x", "versao": "0.1", "id": "PYSEC-1", "aliases": [], "severidade": "alta",
                     "fix_versions": ["9.9"], "origem_severidade": "cvss", "excecao": None, "bloqueia": True}],
    })
    monkeypatch.setattr(vs, "rodar_npm", lambda *a, **k: ([], "9.9.9"))
    r = vc.rodar()
    assert r["rc"] == 0 and r["fontes_ok"] == ["pip-audit", "npm-audit"]
    assert r["achados"] == [{"fonte": "pip-audit", "pacote": "pacote-x", "versao": "0.1", "id_cve": "PYSEC-1",
                             "gravidade": "alta", "corrigido_em_versao": "9.9"}]


def test_rodar_traduz_achado_de_npm(monkeypatch):
    monkeypatch.setattr(vd, "avaliar", lambda *a, **k: {"achados": [], "reprovado": False, "requirements": "x"})
    monkeypatch.setattr(vs, "rodar_npm", lambda *a, **k: (
        [{"ferramenta": "npm", "id": "GHSA-x", "severidade": "critical", "titulo": "t", "pacote": "p",
          "versao": "1.0", "bloqueia_por_politica": True, "revisao": False}], "10.0.0"))
    r = vc.rodar()
    assert r["achados"] == [{"fonte": "npm-audit", "pacote": "p", "versao": "1.0", "id_cve": "GHSA-x",
                             "gravidade": "critica", "corrigido_em_versao": None}]


@pytest.mark.parametrize("severidade_npm,esperada", [
    ("critical", "critica"), ("high", "alta"), ("moderate", "media"), ("low", "baixa"), ("info", "baixa"),
    ("algo-novo-que-o-npm-inventou", "desconhecida"),
])
def test_gravidade_de_npm_cobre_o_vocabulario_conhecido_e_tem_fallback_seguro(severidade_npm, esperada):
    # achado real (medido 15/09/2026 contra web/vendor/VERSOES.txt): npm fala inglês, o CHECK da migração
    # 20260915T2252 só aceita o vocabulário de scripts/varredura_dependencias.py — sem esta tradução o INSERT
    # reprova com CheckViolation (bug pego rodando scripts/varredura_cve.py de verdade, não em teste).
    assert vc._gravidade_de_npm(severidade_npm) == esperada


def test_rodar_sem_rede_no_pip_audit_registra_rc_2_sem_travar(monkeypatch):
    def _falha(*a, **k):
        raise vd.ErroVarredura("pip-audit não respondeu em 180 s")

    monkeypatch.setattr(vd, "avaliar", _falha)
    monkeypatch.setattr(vs, "rodar_npm", lambda *a, **k: ([], "9.9.9"))
    r = vc.rodar()
    assert r["rc"] == 2
    assert "sem rede" in r["resumo"]
    assert "pip-audit" not in r["fontes_ok"]
    assert r["achados"] == []


def test_rodar_npm_ausente_nao_e_falha_de_rede_e_nao_derruba_o_rc_de_pip_audit(monkeypatch):
    """`npm` fora do PATH é um motivo diferente de "sem rede": pip-audit segue valendo (rc continua 0) e
    npm-audit só fica fora de `fontes_ok` — nunca fecha achado de npm por ausência de execução."""
    monkeypatch.setattr(vd, "avaliar", lambda *a, **k: {"achados": [], "reprovado": False, "requirements": "x"})

    def _sem_npm(*a, **k):
        raise vs.ErroVarredura("npm não encontrado no PATH (dpkg npm)")

    monkeypatch.setattr(vs, "rodar_npm", _sem_npm)
    r = vc.rodar()
    assert r["rc"] == 0
    assert "npm-audit" not in r["fontes_ok"]
    assert "indisponível" in r["resumo"]


def test_rodar_nunca_lanca_mesmo_com_as_duas_fontes_falhando(monkeypatch):
    monkeypatch.setattr(vd, "avaliar", lambda *a, **k: (_ for _ in ()).throw(vd.ErroVarredura("sem rede")))
    monkeypatch.setattr(vs, "rodar_npm", lambda *a, **k: (_ for _ in ()).throw(vs.ErroVarredura("timeout rede")))
    r = vc.rodar()
    assert r["rc"] == 2 and r["fontes_ok"] == [] and r["achados"] == []


# ---------------------------------------------------------------- ciclo completo em banco (trilha corrente)
def _achado(pacote: str, cve: str, fonte: str = "pip-audit") -> dict:
    return {"fonte": fonte, "pacote": pacote, "versao": "0.0.1", "id_cve": cve, "gravidade": "alta",
            "corrigido_em_versao": "9.9"}


def _registrar(cur, rc, duracao_ms, resumo, achados, fontes_ok):
    cur.execute("SELECT plat.varredura_cve_registrar(%s, %s, %s, %s::jsonb, %s) AS id",
                (rc, duracao_ms, resumo, json.dumps(achados), fontes_ok))
    return cur.fetchone()["id"]


@pytest.fixture(autouse=True)
def _limpar_varreduras_da_trilha_apos_o_teste():
    """`plat.varredura_cve`/`plat.vulnerabilidade` são log cumulativo da INSTALAÇÃO (nunca somem sozinhos,
    §7.6 de docs/SEGURANCA.md) — os testes acima chamam `plat.varredura_cve_registrar()` direto, na mesma
    trilha que `docs/CORRECOES.md` lê para valer. Sem limpeza, cada rodada da suíte deixaria "última
    varredura" e o log cheios de linhas de teste, poluindo o documento gerado para quem vier depois. Apaga só
    o que ESTE teste criou (id > watermark de antes dele rodar), nunca linha de fora."""
    with db.db() as cur:
        cur.execute("SELECT coalesce(max(id), 0) AS m FROM plat.varredura_cve")
        antes = cur.fetchone()["m"]
    yield
    with db.db() as cur:
        cur.execute("DELETE FROM plat.vulnerabilidade WHERE varredura_id > %s", (antes,))
        cur.execute("DELETE FROM plat.varredura_cve WHERE id > %s", (antes,))


@pytest.fixture
def achado_zt():
    """Pacote/CVE únicos por execução (prefixo zt-, mesma convenção de tests/api/conftest.py para dado
    sintético)."""
    pacote = f"zt-pacote-{uuid.uuid4().hex[:10]}"
    cve = f"ZT-CVE-{uuid.uuid4().hex[:10]}"
    return pacote, cve


def test_achado_sintetico_vira_linha_aberta_e_some_quando_a_fonte_o_corrige(achado_zt):
    """A refutação do item: "CVE sintética (pacote antigo colocado de propósito) aparece no log ... e some
    quando corrigida" — direto na função que o job/script chamam, sem esperar o timer diário."""
    pacote, cve = achado_zt
    with db.db() as cur:
        v1 = _registrar(cur, 0, 10, "teste: 1 achado(s)", [_achado(pacote, cve)], ["pip-audit"])
        cur.execute("SELECT gravidade, corrigido_em_versao, resolvida_em, varredura_id FROM plat.vulnerabilidade "
                    "WHERE pacote = %s AND id_cve = %s", (pacote, cve))
        linha = cur.fetchone()
        assert linha["gravidade"] == "alta" and linha["corrigido_em_versao"] == "9.9"
        assert linha["resolvida_em"] is None and linha["varredura_id"] == v1

        # segunda varredura: o pacote foi corrigido, o achado não aparece mais
        v2 = _registrar(cur, 0, 10, "teste: 0 achado(s)", [], ["pip-audit"])
        cur.execute("SELECT resolvida_em FROM plat.vulnerabilidade WHERE pacote = %s AND id_cve = %s",
                    (pacote, cve))
        assert cur.fetchone()["resolvida_em"] is not None
    assert v1 != v2


def test_fonte_que_nao_rodou_nao_fecha_achado_por_ausencia(achado_zt):
    """"sem rede" não é "corrigido": p_fontes_ok vazio não fecha achado nenhum, mesmo que a lista de achados
    desta rodada esteja vazia."""
    pacote, cve = achado_zt
    with db.db() as cur:
        _registrar(cur, 0, 10, "teste", [_achado(pacote, cve)], ["pip-audit"])
        _registrar(cur, 2, 5, "pip-audit: falhou (sem rede)", [], [])  # fontes_ok vazio
        cur.execute("SELECT resolvida_em FROM plat.vulnerabilidade WHERE pacote = %s AND id_cve = %s",
                    (pacote, cve))
        assert cur.fetchone()["resolvida_em"] is None


def test_achado_reaberto_depois_de_resolvido_cria_novo_historico_sem_duas_linhas_abertas(achado_zt):
    """Regressão: o mesmo pacote/CVE volta a aparecer depois de já ter sido marcado resolvido. O índice único
    parcial só protege a linha ABERTA (`WHERE resolvida_em IS NULL`) — o histórico ganha uma linha nova por
    episódio de vez que reabre (nunca apaga a anterior, é o log de correções completo), mas nunca deixa duas
    linhas abertas ao mesmo tempo para o mesmo achado."""
    pacote, cve = achado_zt
    with db.db() as cur:
        _registrar(cur, 0, 10, "1", [_achado(pacote, cve)], ["pip-audit"])
        _registrar(cur, 0, 10, "2", [], ["pip-audit"])  # resolve
        _registrar(cur, 0, 10, "3", [_achado(pacote, cve)], ["pip-audit"])  # volta (regressão de versão)
        cur.execute("SELECT resolvida_em FROM plat.vulnerabilidade WHERE pacote = %s AND id_cve = %s ORDER BY id",
                    (pacote, cve))
        linhas = cur.fetchall()
    assert len(linhas) == 2, "histórico: uma linha resolvida do primeiro episódio + uma reaberta do segundo"
    assert sum(1 for r in linhas if r["resolvida_em"] is None) == 1  # nunca duas abertas ao mesmo tempo


def test_sem_rede_fica_registrado_com_rc_diferente_de_zero_e_status_le_isso_como_falha():
    """"sem rede -> varredura registrada com rc != 0 e status mostra 'última varredura falhou'": grava uma
    execução com rc=2 (nenhum achado — nunca "0 CVE" fingido) e confere plat.status_vulnerabilidades(), que é
    exatamente o que app/status.py::_do_banco consulta para o bloco `vulnerabilidades` de /api/status."""
    with db.db() as cur:
        _registrar(cur, 2, 42, "pip-audit: falhou (sem rede); npm-audit: indisponível (sem rede)", [], [])
        cur.execute("SELECT * FROM plat.status_vulnerabilidades()")
        v = cur.fetchone()
    assert v["ultimo_rc"] == 2
    # mesma expressão de app/status.py::_do_banco (bloco "vulnerabilidades"."estado")
    estado = "nunca_rodou" if v["ultima_em"] is None else ("ok" if not v["ultimo_rc"] else "falhou")
    assert estado == "falhou"


def test_status_vulnerabilidades_sempre_devolve_exatamente_uma_linha():
    """Nunca "sem linha" — nem antes da primeira varredura da instalação (subconsultas escalares, não JOIN)."""
    with db.db() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.status_vulnerabilidades()")
        assert cur.fetchone()["n"] == 1


def test_status_vulnerabilidades_conta_so_as_abertas(achado_zt):
    pacote, cve = achado_zt
    with db.db() as cur:
        cur.execute("SELECT abertas FROM plat.status_vulnerabilidades()")
        antes = cur.fetchone()["abertas"]
        _registrar(cur, 0, 1, "teste", [_achado(pacote, cve)], ["pip-audit"])
        cur.execute("SELECT abertas FROM plat.status_vulnerabilidades()")
        depois_de_abrir = cur.fetchone()["abertas"]
        _registrar(cur, 0, 1, "teste", [], ["pip-audit"])
        cur.execute("SELECT abertas FROM plat.status_vulnerabilidades()")
        depois_de_resolver = cur.fetchone()["abertas"]
    assert depois_de_abrir == antes + 1
    assert depois_de_resolver == antes


# ---------------------------------------------------------------- docs/gerar_correcoes.py (determinístico)
_DADOS_FIXOS = [
    {"fonte": "pip-audit", "pacote": "pacote-x", "versao": "0.1", "id_cve": "PYSEC-1", "gravidade": "alta",
     "corrigido_em_versao": "9.9", "detectada_em": "2026-09-01T00:00:00Z", "resolvida_em": None},
    {"fonte": "npm-audit", "pacote": "pacote-y", "versao": "1.0", "id_cve": "GHSA-x", "gravidade": "critica",
     "corrigido_em_versao": None, "detectada_em": "2026-08-01T00:00:00Z", "resolvida_em": "2026-08-05T00:00:00Z"},
]
_ULTIMA_FIXA = {"quando": "2026-09-01T00:00:00Z", "rc": 0, "resumo": "ok", "fonte": "pip-audit+npm-audit"}


def test_gerar_correcoes_e_deterministico_com_dados_fixos(monkeypatch):
    monkeypatch.setattr(gc, "_ler_banco", lambda: (_DADOS_FIXOS, _ULTIMA_FIXA))
    a = gc.gerar_markdown()
    b = gc.gerar_markdown()
    assert a == b
    assert "`PYSEC-1`" in a and "`pacote-x`" in a and "alta" in a
    assert "2026-08-05 00:00" in a  # resolvida aparece formatada
    assert "2 achado(s)" in a and "1 aberto(s)" in a


def test_gerar_correcoes_cai_para_o_instantaneo_quando_banco_indisponivel(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_ler_banco", lambda: None)
    inst = tmp_path / "ultima_varredura_cve.json"
    inst.write_text(json.dumps({
        "quando": "2026-09-10T00:00:00Z", "rc": 0, "resumo": "ok",
        "achados": [{"fonte": "pip-audit", "pacote": "p", "versao": "1", "id_cve": "X", "gravidade": "baixa",
                    "corrigido_em_versao": None}],
    }), encoding="utf-8")
    monkeypatch.setattr(gc, "INSTANTANEO", inst)
    md = gc.gerar_markdown()
    assert "último instantâneo" in md and "`X`" in md and "banco indisponível" in md


def test_gerar_correcoes_sem_banco_e_sem_instantaneo_fica_vazio_mas_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_ler_banco", lambda: None)
    monkeypatch.setattr(gc, "INSTANTANEO", tmp_path / "nao-existe.json")
    md = gc.gerar_markdown()
    assert "0 achado(s)" in md and "_(vazio" in md
