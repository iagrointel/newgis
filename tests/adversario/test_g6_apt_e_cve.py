"""Ataque adversarial aos itens L7-14-instalacoes-apt-desta-linha e
L7-03-f-dependencias-cve-log-correcoes (turno 3, grupo G6).

L7-14 está marcado "entregue" com portão literal ainda por escrever ("portão a fixar pelo arquiteto no
turno em que o item que a pediu entrar"). Um portão que nunca foi fixado não pode ter sido passado; e a
lista que o item chama de "fechada" não fecha o que install.sh precisa.

L7-03-f está "parcial": dos seis artefatos que o portão nomeia, existe um."""

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.adversario.apoio_g6 import RAIZ

ITEM_APT = "L7-14-instalacoes-apt-desta-linha"
ITEM_CVE = "L7-03-f-dependencias-cve-log-correcoes"

# comandos externos que install.sh chama e que não vêm com Ubuntu Server por padrão
PACOTES_DE_COMANDO = {
    "nginx": "nginx",
    "certbot": "certbot",
    "openssl": "openssl",
    "curl": "curl",
    "psql": "postgresql-client",
}


def _lista_apt() -> list[str]:
    linhas = (RAIZ / "deploy" / "pacotes_apt.txt").read_text(encoding="utf-8").splitlines()
    return [linha.split()[0] for linha in linhas if linha.strip() and not linha.strip().startswith("#")]


@pytest.mark.xfail(
    strict=True,
    reason="L7-14: deploy/pacotes_apt.txt se apresenta como 'lista fechada de pacotes apt que o plat já "
    "exige', mas install.sh chama nginx, certbot, openssl, curl e psql — nenhum na lista. Numa máquina "
    "limpa o instalador quebra no passo do nginx/certbot depois de já ter criado role, segredo e venv.",
)
def test_lista_apt_cobre_o_que_install_sh_exige():
    texto = (RAIZ / "install.sh").read_text(encoding="utf-8")
    lista = _lista_apt()
    faltando = sorted(
        pacote
        for comando, pacote in PACOTES_DE_COMANDO.items()
        if comando in texto and pacote not in lista
    )
    assert faltando == [], f"install.sh depende de pacotes fora da lista fechada: {faltando}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-14: o caminho 'pacote ausente -> apt-get install -y instala' nunca foi exercitado (o handoff "
    "admite: os 7 já estavam instalados). Sem uma prova em ambiente limpo, 'instalação idempotente' é "
    "leitura de código, não medição.",
)
def test_instalacao_de_pacote_ausente_foi_exercitada():
    medidas = RAIZ / "tests" / "medidas" / "L7-14-instalacoes-apt-desta-linha.json"
    assert medidas.exists(), "não há medida gravada do caminho de instalação de pacote ausente"


@pytest.mark.xfail(
    strict=True,
    reason="L7-03-f (portão): 'resultado vai para plat.vulnerabilidade e gera docs/CORRECOES.md'; 'timer roda "
    "e grava'; 'make check reprova com CVE alta sem exceção'; 'página /status mostra o último ciclo'. Nenhum "
    "dos quatro existe: sem tabela, sem docs/CORRECOES.md, sem *.timer, e seguranca-deps está fora de "
    "check/check-rapido por decisão explícita do próprio handoff.",
)
def test_artefatos_do_portao_de_cve_existem():
    faltando = []
    if not (RAIZ / "docs" / "CORRECOES.md").exists():
        faltando.append("docs/CORRECOES.md")
    if not list((RAIZ / "deploy").glob("*.timer")):
        faltando.append("timer systemd de varredura diária")
    makefile = (RAIZ / "Makefile").read_text(encoding="utf-8")
    linha_check = next((linha for linha in makefile.splitlines() if linha.startswith("check:")), "")
    if "seguranca-deps" not in linha_check:
        faltando.append("seguranca-deps dentro do alvo check")
    assert faltando == [], f"cláusulas do portão sem artefato: {faltando}"


@pytest.mark.xfail(
    strict=True,
    reason="L7-03-f (hipótese): a varredura devia cobrir osv-scanner, trivy e gitleaks além do pip-audit. "
    "Nenhum dos três está instalado nem é chamado por script algum — o repositório e as imagens do compose "
    "seguem sem varredura de segredo e de imagem.",
)
def test_ferramentas_de_varredura_da_hipotese_existem():
    faltando = [f for f in ("osv-scanner", "trivy", "gitleaks") if shutil.which(f) is None]
    assert faltando == [], f"ferramentas ausentes: {faltando}"


def test_o_que_aguentou_os_sete_pacotes_da_lista_estao_instalados():
    """Não é refutação: a cláusula que o item de fato exercita passa. Fica registrada."""
    for pacote in _lista_apt():
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pacote], capture_output=True, text=True, timeout=60
        )
        assert "install ok installed" in r.stdout, f"{pacote} não instalado"


def test_o_que_aguentou_reescritor_de_migracao_nao_deixa_plat_para_tras():
    """Não é refutação (L7-31): as 38 migrações atuais saem do reescritor sem nenhuma ocorrência de `plat`
    como schema. Fica registrado porque é a única barreira real e é frágil a migração nova."""
    import re

    padrao = re.compile(r"(?<!current_setting\(')(?<!set_config\(')\bplat\b")
    sobras = []
    for arquivo in sorted(Path(RAIZ / "db" / "migracoes").glob("*.sql")):
        r = subprocess.run(
            ["venv/bin/python", "db/reescrever_homolog.py", str(arquivo)],
            cwd=str(RAIZ), capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, r.stderr
        if padrao.search(r.stdout):
            sobras.append(arquivo.name)
    assert sobras == [], f"migrações com `plat` não reescrito: {sobras}"
