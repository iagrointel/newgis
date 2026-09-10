"""Regras de alerta e roteamento (item L7-06-b-alertas): `deploy/alertas.yml`,
`deploy/alertmanager.yml`, `deploy/alertas_teste.yml` e `docs/RUNBOOKS/alertas.md`.

Estes testes não são sobre "o arquivo existe": eles exercitam as três coisas que o portão do item
exige e que dão para provar sem subir nada — que `amtool check-config` aprova a configuração de
produção, que TODA regra dispara num caso de `promtool test rules`, e que TODA regra tem seção no
runbook. A encenação de verdade (encher volume, derrubar alvo, atrasar backup) é
`deploy/alertas_homologacao.sh`, cujo resultado fica em `tests/medidas/L7-06-b-alertas.json`.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
ALERTAS = RAIZ / "deploy" / "alertas.yml"
ROTEAMENTO = RAIZ / "deploy" / "alertmanager.yml"
CASOS = RAIZ / "deploy" / "alertas_teste.yml"
RUNBOOK = RAIZ / "docs" / "RUNBOOKS" / "alertas.md"

SEVERIDADES = {"aviso", "critico"}
SERVICOS = {"disco", "ram", "fila", "api", "tiles", "tls", "backup", "replica", "processo", "monitor"}


def regras() -> list[dict]:
    doc = yaml.safe_load(ALERTAS.read_text(encoding="utf-8"))
    return [r for g in doc["groups"] for r in g["rules"]]


def nomes() -> list[str]:
    return [r["alert"] for r in regras()]


def test_toda_regra_tem_severidade_servico_e_runbook_no_vocabulario_declarado():
    for r in regras():
        rot = r.get("labels", {})
        assert rot.get("severidade") in SEVERIDADES, (r["alert"], rot.get("severidade"))
        assert rot.get("servico") in SERVICOS, (r["alert"], rot.get("servico"))
        # o rótulo runbook é a âncora no documento: minúsculas do próprio nome do alerta, sem inventar
        assert rot.get("runbook") == r["alert"].lower(), r["alert"]
        assert r.get("annotations", {}).get("resumo"), r["alert"]
        assert r.get("annotations", {}).get("detalhe"), r["alert"]


def test_as_regras_do_portao_existem_todas_pelo_nome():
    esperadas = {
        "DiscoQuaseCheio", "DiscoCritico", "RamDisponivelBaixa", "FilaComJobLongo",
        "TaxaDeErro5xxAlta", "TileP95Lento", "CertificadoPertoDeVencer", "BackupAtrasado",
        "DrillDoMesNaoExecutado", "ReplicaAtrasadaOuParada", "ReplicaSemMetrica",
        "ServicoDaPlataformaFora", "AlvoPrometheusCaido", "AlertmanagerFora",
        "PrometheusNaoConsegueFalarComAlertmanager", "Sentinela",
    }
    assert esperadas <= set(nomes()), esperadas - set(nomes())


def test_toda_regra_tem_caso_que_a_dispara_em_alertas_teste():
    """`promtool test rules` só reprova o que é declarado; uma regra sem caso passaria despercebida."""
    doc = yaml.safe_load(CASOS.read_text(encoding="utf-8"))
    com_alerta_esperado = {
        t["alertname"]
        for caso in doc["tests"]
        for t in caso.get("alert_rule_test", [])
        if t.get("exp_alerts")
    }
    assert set(nomes()) <= com_alerta_esperado, set(nomes()) - com_alerta_esperado


def test_runbook_liga_cada_alerta_a_uma_secao_propria():
    texto = RUNBOOK.read_text(encoding="utf-8")
    for r in regras():
        nome, ancora = r["alert"], r["labels"]["runbook"]
        assert f"\n## {nome}\n" in texto, f"sem seção `## {nome}` em docs/RUNBOOKS/alertas.md"
        assert f"`runbook: {ancora}`" in texto, f"seção de {nome} sem o rótulo `runbook: {ancora}`"
        # uma seção que só repete o alerta não é runbook: exige o que fazer e como confirmar
        corpo = texto.split(f"\n## {nome}\n", 1)[1].split("\n## ", 1)[0]
        assert "O que fazer" in corpo, nome
        assert "Como confirmar" in corpo, nome


def test_roteamento_so_aponta_para_receptores_que_existem():
    doc = yaml.safe_load(ROTEAMENTO.read_text(encoding="utf-8"))
    definidos = {r["name"] for r in doc["receivers"]}
    usados = {doc["route"]["receiver"]} | {r["receiver"] for r in doc["route"].get("routes", [])}
    assert usados <= definidos, usados - definidos
    assert definidos == usados, f"receptor definido e nunca usado: {definidos - usados}"


def test_toda_severidade_das_regras_tem_rota_no_alertmanager():
    doc = yaml.safe_load(ROTEAMENTO.read_text(encoding="utf-8"))
    casadas = set()
    for rota in doc["route"].get("routes", []):
        for m in rota.get("matchers", []):
            achado = re.match(r'severidade\s*=\s*"([a-z]+)"', m)
            if achado:
                casadas.add(achado.group(1))
    assert {r["labels"]["severidade"] for r in regras()} <= casadas


def test_nenhum_segredo_literal_no_arquivo_de_roteamento():
    """O repositório é público. Senha e credencial só por caminho de arquivo (`*_file`)."""
    texto = ROTEAMENTO.read_text(encoding="utf-8")
    proibido = re.compile(
        r"^\s*-?\s*(smtp_auth_password|auth_password|credentials|bearer_token|password|api_key)\s*:",
        re.M | re.I,
    )
    assert not proibido.search(texto), proibido.search(texto).group(0)
    for campo in ("credentials_file", "url_file"):
        for linha in texto.splitlines():
            if campo in linha and ":" in linha:
                caminho = linha.split(":", 1)[1].strip()
                assert caminho.startswith("/etc/plat/segredos/"), linha


@pytest.mark.skipif(not shutil.which("promtool"), reason="promtool não instalado nesta máquina")
def test_promtool_aprova_as_regras_e_todos_os_casos_passam():
    p = subprocess.run(["promtool", "check", "rules", str(ALERTAS)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    t = subprocess.run(["promtool", "test", "rules", CASOS.name], cwd=CASOS.parent,
                       capture_output=True, text=True)
    assert t.returncode == 0, t.stdout + t.stderr
    assert "SUCCESS" in t.stdout


@pytest.mark.skipif(not shutil.which("amtool"), reason="amtool não instalado nesta máquina")
def test_amtool_check_config_verde_na_configuracao_de_producao():
    p = subprocess.run(["amtool", "check-config", str(ROTEAMENTO)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "SUCCESS" in p.stdout
