"""Item HARD-01-varredura-de-seguranca-continua (docs/SEGURANCA.md seção 9; scripts/varredura_seguranca.py).

Cobre o portão sem depender do estado do repositório no instante do teste: as ferramentas de análise entram por
dublê (`monkeypatch`) — exceto a refutação do item, que roda o gitleaks DE VERDADE contra um repositório git
temporário com segredos aleatórios plantados num commit (a refutação: "segredo plantado num commit é barrado").
Nenhum teste aqui toca banco, rede ou produção."""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import string
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import varredura_seguranca as vs  # noqa: E402 — módulo em scripts/, fora do pacote app

HOJE = dt.date(2026, 9, 7)


def _excecao(**campos) -> dict:
    base = {"ferramenta": "bandit", "id": "B310", "motivo": "url fixa", "prazo": "2026-12-06",
            "registrado_em": "2026-09-07", "quem": "teste"}
    return {**base, **campos}


# ---------------------------------------------------------------- exceções: prazo, alvo, campos obrigatórios
def test_excecao_viva_casa_ferramenta_id_e_arquivo_por_glob():
    achado = {"ferramenta": "bandit", "id": "B310", "arquivo": "scripts/segredo_rotacionar.py"}
    assert vs.excecao_viva(achado, [_excecao(arquivo="scripts/*.py")], hoje=HOJE) is not None
    assert vs.excecao_viva(achado, [_excecao(arquivo="app/*.py")], hoje=HOJE) is None
    assert vs.excecao_viva(achado, [_excecao(id="B608")], hoje=HOJE) is None
    assert vs.excecao_viva(achado, [_excecao(ferramenta="trivy")], hoje=HOJE) is None


def test_excecao_vencida_some_sozinha_e_volta_a_bloquear():
    achado = {"ferramenta": "trivy", "id": "DS-0002", "arquivo": "deploy/Dockerfile.worker"}
    exc = _excecao(ferramenta="trivy", id="DS-0002", prazo="2026-09-06")
    assert vs.excecao_viva(achado, [exc], hoje=dt.date(2026, 9, 6)) is not None  # no dia do prazo ainda vale
    assert vs.excecao_viva(achado, [exc], hoje=dt.date(2026, 9, 7)) is None  # um dia depois, não


def test_excecao_por_pacote_so_casa_o_pacote_declarado():
    achado = {"ferramenta": "npm", "id": "GHSA-xxxx", "pacote": "maplibre-gl"}
    assert vs.excecao_viva(achado, [_excecao(ferramenta="npm", id="GHSA-xxxx", pacote="maplibre-gl")], hoje=HOJE)
    assert vs.excecao_viva(achado, [_excecao(ferramenta="npm", id="GHSA-xxxx", pacote="pmtiles")], hoje=HOJE) is None


@pytest.mark.parametrize("faltando", ["prazo", "motivo", "quem", "registrado_em", "id"])
def test_lista_de_excecoes_sem_prazo_ou_responsavel_reprova_a_varredura(tmp_path, faltando):
    exc = _excecao()
    exc.pop(faltando)
    arq = tmp_path / "excecoes.json"
    arq.write_text(json.dumps({"excecoes": [exc]}), encoding="utf-8")
    with pytest.raises(vs.ErroVarredura, match=faltando):
        vs.carregar_excecoes(arq)


def test_lista_de_excecoes_com_ferramenta_desconhecida_reprova(tmp_path):
    arq = tmp_path / "excecoes.json"
    arq.write_text(json.dumps({"excecoes": [_excecao(ferramenta="safety")]}), encoding="utf-8")
    with pytest.raises(vs.ErroVarredura, match="desconhecida"):
        vs.carregar_excecoes(arq)


def test_lista_versionada_de_excecoes_e_valida_e_toda_entrada_tem_prazo_no_futuro_ou_marcada():
    """A lista real do repositório: carrega sem erro; e nenhuma exceção fica vencida sem ninguém ver — a varredura
    imprime as vencidas, mas este teste garante que o arquivo versionado não acumula lixo por mais de 30 dias."""
    excecoes = vs.carregar_excecoes(ROOT / "docs" / "excecoes_seguranca.json")
    velhas = [e for e in excecoes if (dt.date.today() - dt.date.fromisoformat(e["prazo"])).days > 30]
    assert velhas == [], f"exceções vencidas há mais de 30 dias — apagar ou renovar: {velhas}"


# ---------------------------------------------------------------- política por ferramenta (via avaliar com dublês)
def _dubles(monkeypatch, **por_ferramenta):
    """Substitui cada `rodar_<ferramenta>` por um dublê que devolve os achados dados (já no formato normalizado)."""
    for nome, achados in por_ferramenta.items():
        if nome == "trivy":
            monkeypatch.setattr(vs, "rodar_trivy",
                                lambda raiz=None, a=achados: (a, "0.74.0", {"imagem_presente": False}))
        elif nome == "zap":
            monkeypatch.setattr(vs, "rodar_zap", lambda raiz=None, a=achados, **k: (a, "2.17.0", {}))
        else:
            fn = {"bandit": "rodar_bandit", "pip-audit": "rodar_pip_audit", "npm": "rodar_npm",
                  "gitleaks": "rodar_gitleaks"}[nome]
            monkeypatch.setattr(vs, fn, lambda *a_, a=achados, **k: (a, "9.9.9"))
    monkeypatch.setattr(vs, "binarios_fixados", lambda *a, **k: {})


def test_bandit_medium_com_confianca_alta_bloqueia_e_medium_media_vai_para_revisao(monkeypatch, tmp_path):
    alto = vs._achado("bandit", "B314", "media", "xml", bloqueia_por_politica=True, arquivo="app/x.py", linha=1)
    revis = vs._achado("bandit", "B608", "media", "sql", bloqueia_por_politica=False, revisao=True, arquivo="app/y.py",
                       linha=2)
    baixo = vs._achado("bandit", "B101", "baixa", "assert", bloqueia_por_politica=False, arquivo="app/z.py", linha=3)
    _dubles(monkeypatch, bandit=[alto, revis, baixo])
    excecoes = tmp_path / "e.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    r = vs.avaliar(("bandit",), excecoes_caminho=excecoes, hoje=HOJE)
    assert r["reprovado"] is True
    assert r["ferramentas"]["bandit"] == {
        "versao": "9.9.9", "duracao_s": r["ferramentas"]["bandit"]["duracao_s"],
        "achados": 3, "bloqueantes": 1, "com_excecao": 0, "revisao": 1, "informativos": 1,
    }
    excecoes.write_text(json.dumps({"excecoes": [_excecao(id="B314", arquivo="app/x.py")]}), encoding="utf-8")
    r = vs.avaliar(("bandit",), excecoes_caminho=excecoes, hoje=HOJE)
    assert r["reprovado"] is False and r["ferramentas"]["bandit"]["com_excecao"] == 1


def test_gitleaks_todo_achado_bloqueia_mesmo_sem_severidade(monkeypatch, tmp_path):
    a = vs._achado("gitleaks", "generic-api-key", "alta", "segredo", bloqueia_por_politica=True, arquivo="x.py",
                   linha=1)
    _dubles(monkeypatch, gitleaks=[a])
    excecoes = tmp_path / "e.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    assert vs.avaliar(("gitleaks",), excecoes_caminho=excecoes, hoje=HOJE)["reprovado"] is True


def test_pip_audit_usa_a_excecao_do_l7_03f_nao_a_lista_nova(monkeypatch, tmp_path):
    """pip-audit delega ao item L7-03-f: a exceção que vale é docs/excecoes_cve.json (vem no achado como excecao_cve);
    uma entrada em docs/excecoes_seguranca.json para pip-audit é ignorada de propósito."""
    com_cve = vs._achado("pip-audit", "GHSA-1", "alta", "x", bloqueia_por_politica=True, pacote="p", versao="1",
                         aliases=[], excecao_cve={"cve": "GHSA-1", "pacote": "p", "prazo": "2099-01-01"})
    sem_cve = vs._achado("pip-audit", "GHSA-2", "alta", "y", bloqueia_por_politica=True, pacote="q", versao="1",
                         aliases=[], excecao_cve=None)
    _dubles(monkeypatch, **{"pip-audit": [com_cve, sem_cve]})
    excecoes = tmp_path / "e.json"
    excecoes.write_text(json.dumps({"excecoes": [_excecao(ferramenta="pip-audit", id="GHSA-2", pacote="q")]}),
                        encoding="utf-8")
    r = vs.avaliar(("pip-audit",), excecoes_caminho=excecoes, hoje=HOJE)
    assert r["ferramentas"]["pip-audit"]["com_excecao"] == 1 and r["ferramentas"]["pip-audit"]["bloqueantes"] == 1


def test_zap_media_bloqueia_baixa_e_info_nao(monkeypatch, tmp_path):
    med = vs._achado("zap", "10038", "media", "CSP", bloqueia_por_politica=True, arquivo="/", instancias=["/"])
    bai = vs._achado("zap", "10096", "baixa", "timestamp", bloqueia_por_politica=False, arquivo="/x", instancias=["/x"])
    inf = vs._achado("zap", "10109", "info", "spa", bloqueia_por_politica=False, arquivo="/y", instancias=["/y"])
    _dubles(monkeypatch, zap=[med, bai, inf])
    excecoes = tmp_path / "e.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    r = vs.avaliar(("zap",), excecoes_caminho=excecoes, hoje=HOJE)
    assert r["reprovado"] is True and r["ferramentas"]["zap"]["informativos"] == 2


def test_versao_instalada_diferente_da_fixada_reprova(monkeypatch, tmp_path):
    _dubles(monkeypatch, gitleaks=[])
    monkeypatch.setattr(vs, "binarios_fixados",
                        lambda *a, **k: {"gitleaks": {"versao": "8.30.1", "url": "", "sha256": "", "caminho": ""}})
    excecoes = tmp_path / "e.json"
    excecoes.write_text(json.dumps({"excecoes": []}), encoding="utf-8")
    with pytest.raises(vs.ErroVarredura, match="8.30.1"):
        vs.avaliar(("gitleaks",), excecoes_caminho=excecoes, hoje=HOJE)


# ---------------------------------------------------------------- npm: pacotes lidos de web/vendor/VERSOES.txt
def test_pacotes_npm_saem_da_coluna_de_origem_do_versoes_txt(tmp_path):
    v = tmp_path / "VERSOES.txt"
    v.write_text(
        "# cabeçalho\n"
        "maplibre-gl-4.7.1.js   4.7.1  abc  BSD-3-Clause  https://github.com/maplibre/maplibre-gl-js/releases/tag/v4.7.1\n"
        "dompurify-3.4.14.js  3.4.14  abc  Apache-2.0  https://registry.npmjs.org/dompurify/-/dompurify-3.4.14.tgz\n"
        "ibm-plex-sans-3.201.woff2  3.201  abc  OFL-1.1  https://raw.githubusercontent.com/google/fonts/main/ofl/x/OFL.txt\n"
        "escopo.js  1.0.0  abc  MIT  https://registry.npmjs.org/@org/escopo/-/escopo-1.0.0.tgz\n",
        encoding="utf-8",
    )
    assert vs.pacotes_npm_do_vendor(v) == {"maplibre-gl": "4.7.1", "dompurify": "3.4.14", "@org/escopo": "1.0.0"}


def test_versoes_txt_real_gera_os_quatro_pacotes_npm_da_interface():
    deps = vs.pacotes_npm_do_vendor(ROOT / "web" / "vendor" / "VERSOES.txt")
    assert {"maplibre-gl", "swagger-ui-dist", "dompurify", "pmtiles"} <= set(deps)
    assert all(d.count(".") == 2 for d in deps.values()), deps  # versão exata, nunca faixa


# ---------------------------------------------------------------- lista de binários fixados
def test_lista_de_binarios_fixados_tem_sha256_e_versao_por_ferramenta():
    fixados = vs.binarios_fixados()
    assert {"gitleaks", "trivy", "zap"} <= set(fixados)
    for nome, f in fixados.items():
        assert len(f["sha256"]) == 64 and all(c in "0123456789abcdef" for c in f["sha256"]), nome
        assert f["url"].startswith("https://github.com/"), nome


def test_instalador_recusa_pacote_com_sha256_diferente(tmp_path):
    """scripts/ferramentas_seguranca.sh: pacote já no cache com sha diferente do fixado → sai 3 e apaga o pacote
    (o download é simulado com file:// para não bater na rede)."""
    conteudo = tmp_path / "conteudo"
    conteudo.mkdir()
    (conteudo / "falsa").write_text("#!/bin/sh\n", encoding="utf-8")
    pacote = tmp_path / "falso.tar.gz"
    subprocess.run(["tar", "-czf", str(pacote), "-C", str(conteudo), "falsa"], check=True)
    lista = tmp_path / "lista.txt"
    lista.write_text(f"falsa 1.0 file://{pacote} {'0' * 64} falsa\n", encoding="utf-8")
    cache = tmp_path / "cache"
    script = ROOT / "scripts" / "ferramentas_seguranca.sh"
    # o script lê a lista pelo caminho fixo deploy/ferramentas_binarias.txt: apontamos a raiz para uma cópia mínima
    raiz = tmp_path / "raiz"
    (raiz / "scripts").mkdir(parents=True)
    (raiz / "deploy").mkdir()
    (raiz / "scripts" / "ferramentas_seguranca.sh").write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    (raiz / "deploy" / "ferramentas_binarias.txt").write_text(lista.read_text(encoding="utf-8"), encoding="utf-8")
    r = subprocess.run(["bash", str(raiz / "scripts" / "ferramentas_seguranca.sh")], capture_output=True, text=True,
                       env={**os.environ, "PLAT_FERRAMENTAS_DIR": str(cache)})
    assert r.returncode == 3, r.stderr
    assert "NÃO confere" in r.stderr
    assert not list((cache / "pacotes").glob("*.tar.gz"))


# ---------------------------------------------------------------- refutação: segredo plantado num commit é barrado
def _gitleaks_disponivel() -> bool:
    return (vs.CACHE_FERRAMENTAS / "bin" / "gitleaks").exists()


def test_refutacao_segredo_plantado_num_commit_e_barrado(tmp_path):
    """gitleaks de verdade (versão fixada), com o .gitleaks.toml do repositório, contra um git temporário onde um
    commit traz 3 segredos ALEATÓRIOS (chave AWS, token do GitHub, chave genérica). Aleatórios de propósito: o
    conjunto padrão do gitleaks ignora valores com a palavra EXAMPLE, e um teste com AKIAIOSFODNN7EXAMPLE passava
    em falso (medido em 07/09/2026 ao escrever este teste)."""
    if not _gitleaks_disponivel():
        pytest.fail("gitleaks não instalada: rode `make ferramentas` (scripts/ferramentas_seguranca.sh) — "
                    "o item HARD-01 exige a varredura")
    r = "".join
    ch = string.ascii_letters + string.digits
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    conf = repo / "config.py"
    conf.write_text(
        f'AWS_ACCESS_KEY_ID = "AKIA{r(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))}"\n'
        f'GITHUB_TOKEN = "ghp_{r(secrets.choice(ch) for _ in range(36))}"\n'
        f'api_key = "{secrets.token_hex(24)}"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "config.py"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "planta"], cwd=repo,
                   check=True)
    # e um segundo commit que APAGA o arquivo: o segredo continua no histórico, e a varredura é do histórico
    conf.unlink()
    subprocess.run(["git", "rm", "-q", "config.py"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "apaga"], cwd=repo, check=True)

    achados, versao = vs.rodar_gitleaks(repo, config=ROOT / ".gitleaks.toml", raiz=ROOT)
    assert versao == vs.binarios_fixados()["gitleaks"]["versao"]
    regras = {a["id"] for a in achados}
    assert {"github-pat", "generic-api-key"} <= regras, achados
    assert all(a["bloqueia_por_politica"] for a in achados)
    assert all(a["arquivo"] == "config.py" for a in achados)
    # o trecho gravado no relatório vem REDIGIDO: o segredo inteiro nunca cai no JSON
    for a in achados:
        assert "…" in a["trecho"] or "..." in a["trecho"] or len(a["trecho"]) < 40, a["trecho"]


def test_o_gitleaks_toml_nao_esconde_segredo_de_verdade_por_nome_de_arquivo(tmp_path):
    """A lista de caminhos permitidos do .gitleaks.toml só cobre i18n, vendor e geradores do laço; um segredo em
    app/ ou tests/ continua sendo achado (o mesmo segredo plantado num arquivo de teste é barrado)."""
    if not _gitleaks_disponivel():
        pytest.fail("gitleaks não instalada: rode `make ferramentas`")
    repo = tmp_path / "repo"
    (repo / "tests" / "unit").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tests" / "unit" / "test_x.py").write_text(f'TOKEN = "ghp_{secrets.token_hex(18)}"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=repo, check=True)
    achados, _ = vs.rodar_gitleaks(repo, config=ROOT / ".gitleaks.toml", raiz=ROOT)
    assert any(a["id"] == "github-pat" for a in achados), achados


# ---------------------------------------------------------------- relatório versionado: render determinístico + check
def _medida_minima() -> dict:
    return {
        "item": "HARD-01-varredura-de-seguranca-continua", "medido_em": "2026-09-07T21:00+00:00", "git_sha": "abc1234",
        "carga_1min": 5.5, "ram_livre_gb": 7.0, "reprovado": False,
        "ferramentas": {"bandit": {"versao": "1.9.4", "duracao_s": 1.8, "achados": 3, "bloqueantes": 0,
                                   "com_excecao": 1,
                                   "revisao": 1, "informativos": 1}},
        "revisao": ["bandit B608 app/y.py:2"], "bloqueantes": [], "com_excecao": ["bandit B314 app/x.py"],
    }


def test_secao_gerada_e_deterministica_e_a_coluna_dias_nao_quebra_a_conferencia(tmp_path):
    fixados = {"gitleaks": {"versao": "8.30.1", "url": "u", "sha256": "f" * 64, "caminho": "gitleaks"}}
    excecoes = [_excecao()]
    a = vs.renderizar_secao(_medida_minima(), excecoes, fixados, hoje=HOJE)
    b = vs.renderizar_secao(_medida_minima(), excecoes, fixados, hoje=HOJE)
    assert a == b and a.startswith(vs.MARCA_INICIO) and a.rstrip().endswith(vs.MARCA_FIM)
    assert "| bandit | B310 | `—` | url fixa | 2026-12-06 | 90 | 2026-09-07 | teste |" in a
    doc = tmp_path / "SEGURANCA.md"
    doc.write_text("# S\n\n## 9\n\n" + a, encoding="utf-8")
    medida = tmp_path / "m.json"
    medida.write_text(json.dumps(_medida_minima()), encoding="utf-8")
    exc = tmp_path / "e.json"
    exc.write_text(json.dumps({"excecoes": excecoes}), encoding="utf-8")
    # renderizada 10 dias depois: a coluna "dias" muda (80), o resto não — a conferência ignora só essa coluna
    import unittest.mock as um

    with um.patch.object(vs, "binarios_fixados", lambda *a_, **k: fixados):
        assert vs.conferir_doc(medida_caminho=medida, doc_caminho=doc, excecoes_caminho=exc) == []
        exc.write_text(json.dumps({"excecoes": excecoes + [_excecao(id="B999")]}), encoding="utf-8")
        dif = vs.conferir_doc(medida_caminho=medida, doc_caminho=doc, excecoes_caminho=exc)
    assert dif and any("B999" in linha for linha in dif)


def test_resumo_versionado_nunca_carrega_o_trecho_do_segredo():
    r = {
        "medido_em": "x", "git_sha": "y", "carga_1min": 1, "ram_livre_gb": 1, "reprovado": True, "ferramentas": {},
        "achados": [vs._achado("gitleaks", "generic-api-key", "alta", "seg", bloqueia_por_politica=True, arquivo="a.py",
                               linha=3, trecho="api_key = abcd…", impressao="f") | {"bloqueia": True, "excecao": None}],
    }
    m = vs.resumo_para_medida(r)
    assert m["bloqueantes"] == ["gitleaks generic-api-key a.py"]
    assert "abcd" not in json.dumps(m)


def test_doc_versionado_confere_com_a_medida_versionada():
    """O que a fila roda (`make seguranca` → --check-doc): a seção 9 de docs/SEGURANCA.md bate com
    tests/medidas/HARD-01-seguranca.json + docs/excecoes_seguranca.json + deploy/ferramentas_binarias.txt."""
    assert vs.conferir_doc() == []


# ---------------------------------------------------------------- porta livre: nunca uma que já escuta
def test_porta_livre_pula_porta_que_ja_escuta():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        ocupada = s.getsockname()[1]
        livres = vs.porta_livre(range(ocupada, ocupada + 3), quantas=1)
    assert livres and livres[0] != ocupada


def test_nginx_renderizado_do_modelo_fecha_o_bloco_e_tira_hsts(tmp_path):
    conf = vs.renderizar_nginx(ROOT, tmp_path, 8899, 8898)
    server = (tmp_path / "server.conf").read_text(encoding="utf-8")
    assert server.count("{") == server.count("}")
    assert "Strict-Transport-Security" not in server and "listen 127.0.0.1:8899" in server
    assert "proxy_pass http://127.0.0.1:8898" in server
    assert "Content-Security-Policy" in server and "server_tokens off" in server
    assert conf.read_text(encoding="utf-8").count(str(tmp_path)) >= 7
