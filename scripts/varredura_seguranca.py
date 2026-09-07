"""Varredura de segurança contínua (item HARD-01-varredura-de-seguranca-continua; docs/SEGURANCA.md seção 9).

Um só comando (`make seguranca`) roda, na ordem, e junta num relatório único:

  bandit     análise estática do Python que roda (app/, scripts/, db/, docs/*.py; alvo em pyproject [tool.bandit])
  pip-audit  CVE conhecido em requirements.txt — delega a scripts/varredura_dependencias.py (item L7-03-f), que
             já aplica docs/excecoes_cve.json; aqui só se recolhe o resultado
  npm        `npm audit` sobre as bibliotecas de web/vendor/VERSOES.txt (não há package.json no repositório:
             gera-se um em var/seguranca/npm a partir da coluna de origem do VERSOES.txt, com a versão exata)
  gitleaks   segredo no HISTÓRICO inteiro do git (todos os ramos), regras padrão + .gitleaks.toml
  trivy      má configuração em deploy/ (Dockerfile.worker, docker-compose) e, quando a imagem plat-worker:local
             existir nesta máquina, CVE nas camadas dela
  zap        (só com --com-zap) baseline do OWASP ZAP — spider + regras passivas, nunca varredura ativa — contra
             uma instância que ESTE script sobe (uvicorn + nginx com deploy/nginx.conf renderizado, ambiente da
             trilha corrente) numa porta livre de 8800-8899, e derruba pelo PID ao fim. Nunca contra produção.

Política de bloqueio (uma linha por ferramenta, também impressa no relatório):
  bandit    HIGH em qualquer confiança, ou MEDIUM com confiança HIGH → bloqueia; MEDIUM com confiança menor →
            "revisão" (sai no relatório, não bloqueia; é a lista do adversário); LOW → informativo
  pip-audit crítica/alta/desconhecida sem exceção viva → bloqueia (regra do L7-03-f)
  npm       critical/high → bloqueia; moderate/low → informativo
  gitleaks  todo achado bloqueia
  trivy     CRITICAL/HIGH → bloqueia; MEDIUM → revisão
  zap       High/Medium → bloqueia; Low/Informational → informativo
Um achado que bloqueia só deixa de bloquear com uma exceção VIVA em docs/excecoes_seguranca.json (ferramenta,
id, arquivo/pacote opcionais, motivo, prazo, registrado_em, quem). Prazo vencido = a exceção some sozinha.
Uma exceção sem prazo, sem motivo ou sem responsável reprova a varredura inteira (código 2).

Saídas: 0 = nada bloqueia · 1 = há achado bloqueante sem exceção viva · 2 = uma ferramenta não rodou
(binário ausente, rede fora, JSON ilegível) — nunca vira "0 achado" em silêncio.

Relatórios: var/seguranca/ultima_varredura.json (completo, gitignorado) sempre; com --gravar também
tests/medidas/HARD-01-seguranca.json (resumo versionado) e a seção gerada de docs/SEGURANCA.md (entre os
marcadores); --check-doc reprova se a seção versionada não bate com o que o resumo + a lista de exceções +
as versões fixadas renderizam (mesmo desenho de docs/gerar_limites.py --check).
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

CACHE_FERRAMENTAS = Path(
    os.environ.get("PLAT_FERRAMENTAS_DIR")
    or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "plat" / "ferramentas"
)
VAR = RAIZ / "var" / "seguranca"
LISTA_BINARIOS = RAIZ / "deploy" / "ferramentas_binarias.txt"
EXCECOES = RAIZ / "docs" / "excecoes_seguranca.json"
MEDIDA = RAIZ / "tests" / "medidas" / "HARD-01-seguranca.json"
DOC = RAIZ / "docs" / "SEGURANCA.md"
MARCA_INICIO = "<!-- inicio: gerado por scripts/varredura_seguranca.py — não editar à mão -->"
MARCA_FIM = "<!-- fim: gerado por scripts/varredura_seguranca.py -->"

FERRAMENTAS_PADRAO = ("bandit", "pip-audit", "npm", "gitleaks", "trivy")
TODAS = FERRAMENTAS_PADRAO + ("zap",)
PORTAS_ZAP = range(8800, 8900)  # faixa deste item (ver brief: 8800-8899 são do líder de endurecimento)

POLITICA = {
    "bandit": "HIGH (qualquer confiança) ou MEDIUM com confiança HIGH bloqueia; MEDIUM com confiança menor = revisão; "
              "LOW = informativo",
    "pip-audit": "crítica/alta/desconhecida sem exceção em docs/excecoes_cve.json bloqueia (regra do item L7-03-f)",
    "npm": "critical/high bloqueia; moderate/low = informativo",
    "gitleaks": "todo achado bloqueia (regras padrão + .gitleaks.toml)",
    "trivy": "CRITICAL/HIGH bloqueia; MEDIUM = revisão; imagem só quando plat-worker:local existe na máquina",
    "zap": "High/Medium bloqueia; Low/Informational = informativo; só regras passivas, nunca varredura ativa",
}


class ErroVarredura(RuntimeError):
    """Uma ferramenta não rodou ou a configuração está inválida — código 2, nunca "0 achado"."""


# ---------------------------------------------------------------- utilitários
def _sh(cmd: list[str], *, timeout: int = 600, env: dict | None = None,
        cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except FileNotFoundError as e:
        raise ErroVarredura(f"binário ausente: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise ErroVarredura(f"{cmd[0]} não respondeu em {timeout} s") from e


def _json_de(texto: str, origem: str) -> Any:
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErroVarredura(f"{origem} não devolveu JSON: {texto[-400:]}") from e


def binarios_fixados(lista: Path = LISTA_BINARIOS) -> dict[str, dict]:
    """deploy/ferramentas_binarias.txt → {nome: {versao, url, sha256, caminho}}."""
    if not lista.exists():
        raise ErroVarredura(f"{lista} não existe")
    out = {}
    for linha in lista.read_text(encoding="utf-8").splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        partes = linha.split()
        if len(partes) != 5:
            raise ErroVarredura(f"linha inválida em {lista.name}: {linha!r}")
        out[partes[0]] = {"versao": partes[1], "url": partes[2], "sha256": partes[3], "caminho": partes[4]}
    return out


def binario(nome: str) -> str:
    exe = CACHE_FERRAMENTAS / "bin" / nome
    if not exe.exists():
        raise ErroVarredura(f"{nome} não instalada em {exe} (rode: bash scripts/ferramentas_seguranca.sh {nome})")
    return str(exe)


def carga_da_maquina() -> dict:
    try:
        carga = os.getloadavg()[0]
    except OSError:
        carga = None
    livre = None
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable:"):
                livre = round(int(linha.split()[1]) / 1048576, 1)
    except OSError:
        pass
    return {"carga_1min": carga, "ram_livre_gb": livre}


# ---------------------------------------------------------------- exceções (docs/excecoes_seguranca.json)
CAMPOS_OBRIGATORIOS = ("ferramenta", "id", "motivo", "prazo", "registrado_em", "quem")


def carregar_excecoes(caminho: Path = EXCECOES) -> list[dict]:
    if not caminho.exists():
        return []
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    excecoes = doc.get("excecoes", [])
    for i, exc in enumerate(excecoes):
        faltam = [c for c in CAMPOS_OBRIGATORIOS if not exc.get(c)]
        if faltam:
            raise ErroVarredura(
                f"exceção {i} em {caminho.name} sem {', '.join(faltam)} — toda exceção tem prazo e responsável")
        if exc["ferramenta"] not in TODAS:
            raise ErroVarredura(f"exceção {i} em {caminho.name}: ferramenta desconhecida {exc['ferramenta']!r}")
        try:
            dt.date.fromisoformat(exc["prazo"])
            dt.date.fromisoformat(exc["registrado_em"])
        except ValueError as e:
            raise ErroVarredura(f"exceção {i} em {caminho.name}: data inválida ({e})") from e
    return excecoes


def excecao_viva(achado: dict, excecoes: list[dict], *, hoje: dt.date | None = None) -> dict | None:
    """Primeira exceção que casa (ferramenta + id + arquivo/pacote quando declarados) e ainda não venceu."""
    hoje = hoje or dt.date.today()
    for exc in excecoes:
        if exc["ferramenta"] != achado["ferramenta"] or exc["id"] != achado["id"]:
            continue
        if exc.get("arquivo") and not fnmatch.fnmatch(achado.get("arquivo") or "", exc["arquivo"]):
            continue
        if exc.get("pacote") and exc["pacote"] != achado.get("pacote"):
            continue
        if dt.date.fromisoformat(exc["prazo"]) < hoje:
            continue  # vencida: some sozinha
        return exc
    return None


def _achado(ferramenta: str, id_: str, severidade: str, titulo: str, *, bloqueia_por_politica: bool,
            revisao: bool = False, **extra: Any) -> dict:
    return {
        "ferramenta": ferramenta, "id": id_, "severidade": severidade, "titulo": titulo[:200],
        "bloqueia_por_politica": bloqueia_por_politica, "revisao": revisao, **extra,
    }


# ---------------------------------------------------------------- bandit
def rodar_bandit(raiz: Path = RAIZ) -> tuple[list[dict], str]:
    exe = raiz / "venv" / "bin" / "bandit"
    if not exe.exists():
        raise ErroVarredura("bandit não está na venv (requirements.txt fixa bandit; pip install -r requirements.txt)")
    alvos = [p for p in ("app", "scripts", "db", "docs") if (raiz / p).exists()]
    r = _sh([str(exe), "-c", str(raiz / "pyproject.toml"), "-r", *alvos, "-f", "json", "-q", "--exit-zero"], cwd=raiz)
    if r.returncode != 0:
        raise ErroVarredura(f"bandit saiu com {r.returncode}: {r.stderr[-800:]}")
    dados = _json_de(r.stdout, "bandit")
    achados = []
    for it in dados.get("results", []):
        sev, conf = it["issue_severity"], it["issue_confidence"]
        bloqueia = sev == "HIGH" or (sev == "MEDIUM" and conf == "HIGH")
        revisao = sev == "MEDIUM" and not bloqueia
        arquivo = it["filename"].removeprefix("./")
        if os.path.isabs(arquivo):
            arquivo = os.path.relpath(arquivo, raiz)
        achados.append(_achado(
            "bandit", it["test_id"], {"HIGH": "alta", "MEDIUM": "media", "LOW": "baixa"}[sev], it["issue_text"],
            bloqueia_por_politica=bloqueia, revisao=revisao, confianca=conf.lower(), arquivo=arquivo,
            linha=it["line_number"], cwe=(it.get("issue_cwe") or {}).get("id"),
        ))
    versao = _sh([str(exe), "--version"]).stdout.split()[1] if _sh([str(exe), "--version"]).stdout else "?"
    return achados, versao


# ---------------------------------------------------------------- pip-audit (delega ao item L7-03-f)
def rodar_pip_audit(raiz: Path = RAIZ) -> tuple[list[dict], str]:
    import varredura_dependencias as vd

    resultado = vd.avaliar(raiz / "requirements.txt", raiz / "docs" / "excecoes_cve.json",
                           executavel=str(raiz / "venv" / "bin" / "pip-audit"))
    achados = []
    for a in resultado["achados"]:
        grave = a["severidade"] in vd.GRAVES or a["severidade"] == "desconhecida"
        achados.append(_achado(
            "pip-audit", a["id"], a["severidade"], f"{a['pacote']}=={a['versao']} fix={a['fix_versions'] or '?'}",
            bloqueia_por_politica=grave, pacote=a["pacote"], versao=a["versao"], aliases=a["aliases"],
            excecao_cve=a["excecao"],
        ))
    r = _sh([str(raiz / "venv" / "bin" / "pip-audit"), "--version"])
    return achados, (r.stdout.split()[-1] if r.stdout else "?")


# ---------------------------------------------------------------- npm audit sobre web/vendor/VERSOES.txt
def pacotes_npm_do_vendor(versoes: Path) -> dict[str, str]:
    """Nome npm → versão exata, lido da coluna de origem (URL do registry) de web/vendor/VERSOES.txt; maplibre-gl
    vem do GitHub e é mapeado pelo nome do arquivo. Fontes (.woff2) não são pacote npm e ficam de fora."""
    deps: dict[str, str] = {}
    for linha in versoes.read_text(encoding="utf-8").splitlines():
        if not linha.strip() or linha.startswith("#"):
            continue
        partes = linha.split(None, 4)
        if len(partes) < 5:
            continue
        nome, versao, _sha, _lic, origem = partes
        m = re.search(r"registry\.npmjs\.org/((?:@[^/]+/)?[^/]+)/-/", origem)
        if m:
            deps[m.group(1)] = versao
        elif nome.startswith("maplibre-gl"):
            deps["maplibre-gl"] = versao
    return deps


def rodar_npm(raiz: Path = RAIZ) -> tuple[list[dict], str]:
    npm = shutil.which("npm")
    if not npm:
        raise ErroVarredura("npm não encontrado no PATH (dpkg npm)")
    versoes = raiz / "web" / "vendor" / "VERSOES.txt"
    if not versoes.exists():
        raise ErroVarredura(f"{versoes} não existe")
    deps = pacotes_npm_do_vendor(versoes)
    pasta = raiz / "var" / "seguranca" / "npm"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "package.json").write_text(json.dumps(
        {"name": "plat-web-vendor", "version": "0.0.0", "private": True, "dependencies": deps}, indent=1),
        encoding="utf-8")
    r = _sh([npm, "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund", "--silent"],
            cwd=pasta, timeout=300)
    if r.returncode != 0:
        raise ErroVarredura(f"npm install --package-lock-only falhou (rede?): {r.stderr[-800:]}")
    r = _sh([npm, "audit", "--json"], cwd=pasta, timeout=300)
    dados = _json_de(r.stdout, "npm audit")  # sai 1 quando há vulnerabilidade; o JSON vem do mesmo jeito
    if "error" in dados:
        raise ErroVarredura(f"npm audit: {dados['error']}")
    achados = []
    for nome, v in dados.get("vulnerabilities", {}).items():
        sev = v.get("severity", "info")
        for via in v.get("via", []):
            if not isinstance(via, dict):
                continue  # referência a outro pacote já listado
            achados.append(_achado(
                "npm", via.get("url", "").rsplit("/", 1)[-1] or via.get("name", nome), sev, via.get("title", ""),
                bloqueia_por_politica=sev in ("critical", "high"), pacote=nome, versao=via.get("range", ""),
                direto=bool(v.get("isDirect")),
            ))
    return achados, (_sh([npm, "-v"]).stdout.strip() or "?")


# ---------------------------------------------------------------- gitleaks (histórico inteiro)
def rodar_gitleaks(alvo: Path = RAIZ, *, config: Path | None = None, raiz: Path = RAIZ) -> tuple[list[dict], str]:
    exe = binario("gitleaks")
    config = config or (raiz / ".gitleaks.toml")
    relatorio = raiz / "var" / "seguranca" / "gitleaks.json"
    relatorio.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "git", "--no-banner", "--redact=90", "--exit-code", "0", "--report-format", "json",
           "--report-path", str(relatorio)]
    if config.exists():
        cmd += ["--config", str(config)]
    cmd.append(str(alvo))
    r = _sh(cmd, timeout=900)
    if r.returncode != 0:
        raise ErroVarredura(f"gitleaks saiu com {r.returncode}: {r.stderr[-800:]}")
    dados = json.loads(relatorio.read_text(encoding="utf-8") or "[]")
    achados = [
        _achado("gitleaks", a["RuleID"], "alta", a.get("Description", ""), bloqueia_por_politica=True,
                arquivo=a["File"], linha=a["StartLine"], commit=a.get("Commit", "")[:12],
                impressao=a.get("Fingerprint", ""), trecho=a.get("Match", "")[:60])
        for a in dados
    ]
    return achados, _sh([exe, "version"]).stdout.strip()


# ---------------------------------------------------------------- trivy (deploy/ e imagem, quando existe)
def rodar_trivy(raiz: Path = RAIZ, *, imagem: str = "plat-worker:local") -> tuple[list[dict], str, dict]:
    exe = binario("trivy")
    cache = raiz / "var" / "cache" / "trivy"
    cache.mkdir(parents=True, exist_ok=True)
    base = [exe, "--cache-dir", str(cache), "--quiet"]
    achados = []
    r = _sh(base + ["config", "--format", "json", str(raiz / "deploy")], timeout=600)
    if r.returncode != 0:
        raise ErroVarredura(f"trivy config saiu com {r.returncode}: {r.stderr[-800:]}")
    for res in _json_de(r.stdout, "trivy config").get("Results") or []:
        for m in res.get("Misconfigurations") or []:
            sev = m["Severity"]
            achados.append(_achado(
                "trivy", m["ID"], sev.lower(), m["Title"], bloqueia_por_politica=sev in ("CRITICAL", "HIGH"),
                revisao=sev == "MEDIUM", arquivo=f"deploy/{res['Target']}",
                linha=(m.get("CauseMetadata") or {}).get("StartLine"),
            ))
    docker = shutil.which("docker")
    imagem_presente = bool(docker) and _sh([docker, "image", "inspect", imagem], timeout=60).returncode == 0
    detalhe = {"imagem": imagem, "imagem_presente": imagem_presente}
    if imagem_presente:
        r = _sh(base + ["image", "--format", "json", "--scanners", "vuln", imagem], timeout=900)
        if r.returncode != 0:
            raise ErroVarredura(f"trivy image saiu com {r.returncode}: {r.stderr[-800:]}")
        for res in _json_de(r.stdout, "trivy image").get("Results") or []:
            for v in res.get("Vulnerabilities") or []:
                sev = v.get("Severity", "UNKNOWN")
                achados.append(_achado(
                    "trivy", v["VulnerabilityID"], sev.lower(), v.get("Title", ""),
                    bloqueia_por_politica=sev in ("CRITICAL", "HIGH"), revisao=sev == "MEDIUM",
                    pacote=v.get("PkgName"), versao=v.get("InstalledVersion"), arquivo=res.get("Target"),
                ))
    versao = _sh([exe, "--version"]).stdout.splitlines()[0].split()[-1]
    return achados, versao, detalhe


# ---------------------------------------------------------------- ZAP baseline (instância própria)
def porta_livre(faixa=PORTAS_ZAP, *, quantas: int = 1) -> list[int]:
    """Portas da faixa que NÃO estão escutando agora (ss -ltnH) e que aceitam bind — incidente 06/09: alocador
    que só evita as próprias portas fez uma trilha medir a aplicação da outra."""
    ocupadas = set()
    r = _sh(["ss", "-ltnH"], timeout=30)
    for linha in r.stdout.splitlines():
        m = re.search(r":(\d+)\s", linha)
        if m:
            ocupadas.add(int(m.group(1)))
    livres = []
    for p in faixa:
        if p in ocupadas:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                continue
        livres.append(p)
        if len(livres) == quantas:
            return livres
    raise ErroVarredura(f"sem {quantas} porta(s) livre(s) em {faixa.start}-{faixa.stop - 1}")


def _esperar_http(url: str, *, segundos: int = 40) -> None:
    import urllib.request

    fim = time.time() + segundos
    while time.time() < fim:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # nosec B310 — URL http://127.0.0.1 montada aqui
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise ErroVarredura(f"{url} não respondeu 200 em {segundos} s")


def renderizar_nginx(raiz: Path, pasta: Path, porta_nginx: int, porta_api: int) -> Path:
    """deploy/nginx.conf (bloco server, modelo do install.sh) → configuração completa que roda como usuário
    comum: listen em 127.0.0.1, sem TLS/HSTS (não há certificado local), caminhos temporários dentro de pasta."""
    modelo = (raiz / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    server = (modelo.replace("server_name DOMINIO;", f"listen 127.0.0.1:{porta_nginx}; server_name 127.0.0.1;")
              .replace("APP_DIR", str(raiz)).replace("PORTA", str(porta_api)))
    server = "\n".join(li for li in server.splitlines() if "Strict-Transport-Security" not in li)
    if server.count("{") > server.count("}"):
        server += "\n}\n"  # o modelo termina sem a chave final (o install.sh acrescenta as linhas do certbot)
    (pasta / "server.conf").write_text(server, encoding="utf-8")
    for d in ("tmp_body", "tmp_proxy", "tmp_fcgi", "tmp_uwsgi", "tmp_scgi"):
        (pasta / d).mkdir(exist_ok=True)
    conf = pasta / "nginx.conf"
    conf.write_text(
        f"pid {pasta}/nginx.pid;\nerror_log {pasta}/error.log warn;\ndaemon off;\n"
        "events {{ worker_connections 64; }}\n"
        "http {{\n  include /etc/nginx/mime.types;\n  access_log off;\n"
        f"  client_body_temp_path {pasta}/tmp_body;\n  proxy_temp_path {pasta}/tmp_proxy;\n"
        f"  fastcgi_temp_path {pasta}/tmp_fcgi;\n  uwsgi_temp_path {pasta}/tmp_uwsgi;\n"
        f"  scgi_temp_path {pasta}/tmp_scgi;\n"
        "  limit_req_zone $binary_remote_addr zone=plat_login:1m rate=10r/m;\n"
        f"  include {pasta}/server.conf;\n}}\n".replace("{{", "{").replace("}}", "}"),
        encoding="utf-8",
    )
    return conf


def _credencial_demo(caminho: str | None) -> tuple[str, str, str] | None:
    """Primeira linha `slug login senha` do arquivo de credenciais da trilha (PLAT_CREDENCIAIS_ARQUIVO) cujo slug
    seja demo — admin sem 2FA obrigatório; nunca a de plataforma (superadmin, 2FA)."""
    if not caminho or not Path(caminho).exists():
        return None
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[0] == "demo":
            return partes[0], partes[1], partes[2]
    return None


def plano_zap(url: str, pasta: Path, *, credencial: tuple[str, str, str] | None) -> Path:
    """Plano do Automation Framework: sementes de URL (a interface é uma página única — o spider sozinho acha
    pouco), login opcional no inquilino demo (o estado HTTP global guarda o cookie de sessão para o spider e
    para as sementes autenticadas), spider limitado, espera das regras passivas, relatório JSON tradicional."""
    sementes = ["/", "/static/index.html", "/static/app.js", "/saude", "/api/versao", "/api/docs",
                "/api/openapi.json", "/api/eu", "/api/itens?limite=5", "/api/usuarios?limite=5", "/api/grupos?limite=5",
                "/api/tokens", "/api/log?limite=5", "/robots.txt"]
    pedidos = ""
    if credencial:
        slug, login, senha = credencial
        corpo = json.dumps({"inquilino": slug, "login": login, "senha": senha})
        pedidos += (f"      - url: {url}/api/login\n        method: POST\n"
                    f"        headers: [\"Content-Type: application/json\"]\n"
                    f"        data: '{corpo}'\n")
    for s in sementes:
        pedidos += f"      - url: {url}{s}\n        method: GET\n"
    plano = f"""env:
  contexts:
    - name: plat
      urls: ["{url}"]
      includePaths: ["{url}.*"]
  parameters:
    failOnError: true
    failOnWarning: false
    progressToStdout: false
jobs:
  - type: passiveScan-config
    parameters:
      maxAlertsPerRule: 20
      scanOnlyInScope: true
  - type: requestor
    parameters:
      user: ""
    requests:
{pedidos}  - type: spider
    parameters:
      context: plat
      maxDuration: 2
      maxDepth: 5
  - type: passiveScan-wait
    parameters:
      maxDuration: 3
  - type: report
    parameters:
      template: traditional-json
      reportDir: {pasta}
      reportFile: zap_baseline
"""
    arq = pasta / "zap_plano.yaml"
    arq.write_text(plano, encoding="utf-8")
    return arq


def rodar_zap(raiz: Path = RAIZ, *, url: str | None = None,
              credenciais: str | None = None) -> tuple[list[dict], str, dict]:
    """Sem `url`, sobe uvicorn (app.main:app, ambiente do processo = trilha corrente) + nginx renderizado de
    deploy/nginx.conf, roda o ZAP em modo comando e derruba os dois pelo PID. Recusa rodar se PLAT_SCHEMA for
    `plat` (produção)."""
    exe = binario("zap")
    pasta = raiz / "var" / "seguranca" / "zap"
    pasta.mkdir(parents=True, exist_ok=True)
    processos: list[subprocess.Popen] = []
    detalhe: dict[str, Any] = {"url": url, "instancia_propria": url is None, "autenticado": False}
    try:
        if url is None:
            if os.environ.get("PLAT_SCHEMA", "plat") == "plat":
                raise ErroVarredura("recusado: PLAT_SCHEMA=plat (produção). Rode com o ambiente de uma trilha.")
            porta_api, porta_nginx = porta_livre(quantas=2)
            log_api = open(pasta / "api.log", "w")
            processos.append(subprocess.Popen(
                [str(raiz / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                 "--port", str(porta_api)], cwd=raiz, stdout=log_api, stderr=subprocess.STDOUT, start_new_session=True))
            (pasta / "api.pid").write_text(str(processos[-1].pid))
            _esperar_http(f"http://127.0.0.1:{porta_api}/saude")
            conf = renderizar_nginx(raiz, pasta, porta_nginx, porta_api)
            nginx = shutil.which("nginx")
            if not nginx:
                raise ErroVarredura("nginx não encontrado no PATH")
            processos.append(subprocess.Popen([nginx, "-c", str(conf)], stdout=open(pasta / "nginx.out", "w"),
                                              stderr=subprocess.STDOUT, start_new_session=True))
            (pasta / "nginx.pid.proprio").write_text(str(processos[-1].pid))
            url = f"http://127.0.0.1:{porta_nginx}"
            _esperar_http(f"{url}/saude")
            detalhe.update(url=url, porta_api=porta_api, porta_nginx=porta_nginx)
        credencial = _credencial_demo(credenciais or os.environ.get("PLAT_CREDENCIAIS_ARQUIVO"))
        detalhe["autenticado"] = credencial is not None
        plano = plano_zap(url, pasta, credencial=credencial)
        (porta_zap,) = porta_livre(quantas=1)
        casa = pasta / "home"
        (casa / ".ZAP").mkdir(parents=True, exist_ok=True)
        (casa / ".ZAP" / ".ZAP_JVM.properties").write_text("-Xmx1024m\n")
        env = {**os.environ, "HOME": str(casa)}
        for arq in (pasta / "zap_baseline.json",):
            arq.unlink(missing_ok=True)
        r = _sh([exe, "-cmd", "-silent", "-host", "127.0.0.1", "-port", str(porta_zap), "-dir", str(pasta / "zap_home"),
                 "-config", "connection.httpStateEnabled=true", "-autorun", str(plano)], timeout=900, env=env)
        (pasta / "zap.out").write_text(r.stdout + r.stderr, encoding="utf-8")
        if "Automation plan succeeded" not in r.stdout or not (pasta / "zap_baseline.json").exists():
            raise ErroVarredura(f"ZAP não completou o plano (ver {pasta / 'zap.out'}): {r.stdout[-600:]}")
    finally:
        (pasta / "zap_plano.yaml").unlink(missing_ok=True)  # contém a senha do admin de teste da trilha
        for p in reversed(processos):
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    dados = json.loads((pasta / "zap_baseline.json").read_text(encoding="utf-8"))
    # o relatório tradicional repete o mesmo alerta sob dois nós `site` (host com e sem porta — medido com 2.17.0), e
    # uma regra pode disparar sub-alertas de nome diferente (10055: "script-src unsafe-inline" × "style-src
    # unsafe-inline"): junta por (regra, nome do alerta), com a lista de instâncias de cada um
    risco = {"3": "alta", "2": "media", "1": "baixa", "0": "info"}
    por_regra: dict[tuple[str, str], dict] = {}
    for site in dados.get("site", []):
        for a in site.get("alerts", []):
            reg = por_regra.setdefault((str(a["pluginid"]), a["alert"]), {"alerta": a, "uris": set()})
            reg["uris"].update(i["uri"].replace(url, "") or "/" for i in a.get("instances", []))
    achados = []
    for (pluginid, nome), reg in sorted(por_regra.items()):
        a, uris = reg["alerta"], sorted(reg["uris"])
        sev = risco.get(str(a.get("riskcode")), "info")
        achados.append(_achado(
            "zap", pluginid, sev, nome, bloqueia_por_politica=sev in ("alta", "media"),
            arquivo=uris[0] if uris else "", instancias=uris[:8], quantidade=len(uris),
            confianca=str(a.get("confidence", "")),
        ))
    detalhe["regras_disparadas"] = len(por_regra)
    return achados, str(dados.get("@version", "?")), detalhe


# ---------------------------------------------------------------- laço principal
def avaliar(ferramentas: tuple[str, ...], *, raiz: Path = RAIZ, excecoes_caminho: Path = EXCECOES,
            zap_url: str | None = None, zap_credenciais: str | None = None, hoje: dt.date | None = None) -> dict:
    excecoes = carregar_excecoes(excecoes_caminho)
    fixados = binarios_fixados(raiz / "deploy" / "ferramentas_binarias.txt")
    resultado: dict[str, Any] = {
        "medido_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "git_sha": _sh(["git", "rev-parse", "--short", "HEAD"], cwd=raiz).stdout.strip(),
        **carga_da_maquina(), "ferramentas": {}, "achados": [], "reprovado": False, "politica": POLITICA,
    }
    for nome in ferramentas:
        t0 = time.time()
        detalhe: dict = {}
        if nome == "bandit":
            achados, versao = rodar_bandit(raiz)
        elif nome == "pip-audit":
            achados, versao = rodar_pip_audit(raiz)
        elif nome == "npm":
            achados, versao = rodar_npm(raiz)
        elif nome == "gitleaks":
            achados, versao = rodar_gitleaks(raiz, raiz=raiz)
        elif nome == "trivy":
            achados, versao, detalhe = rodar_trivy(raiz)
        elif nome == "zap":
            achados, versao, detalhe = rodar_zap(raiz, url=zap_url, credenciais=zap_credenciais)
        else:
            raise ErroVarredura(f"ferramenta desconhecida: {nome}")
        if nome in fixados and fixados[nome]["versao"] not in versao:
            raise ErroVarredura(f"{nome} instalada é {versao!r}, a lista fixa {fixados[nome]['versao']} "
                                "(rode scripts/ferramentas_seguranca.sh)")
        contagem = {"achados": len(achados), "bloqueantes": 0, "com_excecao": 0, "revisao": 0, "informativos": 0}
        for a in achados:
            if nome == "pip-audit":
                a["excecao"] = a.pop("excecao_cve", None)
                a["bloqueia"] = a["bloqueia_por_politica"] and a["excecao"] is None
            else:
                a["excecao"] = excecao_viva(a, excecoes, hoje=hoje) if a["bloqueia_por_politica"] else None
                a["bloqueia"] = a["bloqueia_por_politica"] and a["excecao"] is None
            if a["bloqueia"]:
                contagem["bloqueantes"] += 1
            elif a["excecao"]:
                contagem["com_excecao"] += 1
            elif a.get("revisao"):
                contagem["revisao"] += 1
            else:
                contagem["informativos"] += 1
        resultado["ferramentas"][nome] = {"versao": versao, "duracao_s": round(time.time() - t0, 1),
                                          **contagem, **detalhe}
        resultado["achados"].extend(achados)
        resultado["reprovado"] = resultado["reprovado"] or contagem["bloqueantes"] > 0
    resultado["excecoes"] = excecoes
    data = hoje or dt.date.today()
    resultado["excecoes_vencidas"] = [e for e in excecoes if dt.date.fromisoformat(e["prazo"]) < data]
    return resultado


# ---------------------------------------------------------------- relatório versionado (medida + seção do doc)
def _alvo(a: dict) -> str:
    return f"{a['ferramenta']} {a['id']} {a.get('arquivo') or a.get('pacote') or ''}"


def resumo_para_medida(resultado: dict) -> dict:
    """O que fica versionado em tests/medidas/HARD-01-seguranca.json: contagens por ferramenta, os achados que
    bloqueiam ou estão em revisão (arquivo + id, nunca o trecho do segredo), carga da máquina ao medir."""
    return {
        "item": "HARD-01-varredura-de-seguranca-continua",
        "medido_em": resultado["medido_em"], "git_sha": resultado["git_sha"],
        "carga_1min": resultado["carga_1min"], "ram_livre_gb": resultado["ram_livre_gb"],
        "reprovado": resultado["reprovado"],
        "ferramentas": resultado["ferramentas"],
        "revisao": sorted(
            f"{_alvo(a)}:{a.get('linha') or ''}".rstrip(":")
            for a in resultado["achados"] if a.get("revisao") and not a["bloqueia"]
        ),
        "bloqueantes": sorted(_alvo(a) for a in resultado["achados"] if a["bloqueia"]),
        "com_excecao": sorted(_alvo(a) for a in resultado["achados"] if a.get("excecao")),
    }


def renderizar_secao(medida: dict, excecoes: list[dict], fixados: dict[str, dict], *,
                     hoje: dt.date | None = None) -> str:
    hoje = hoje or dt.date.today()
    linhas = [MARCA_INICIO, "", "### 9.1 Última varredura registrada", "",
              f"Registrada em {medida['medido_em']} (commit `{medida['git_sha']}`, carga 1 min {medida['carga_1min']}, "
              f"RAM livre {medida['ram_livre_gb']} GB) por `make seguranca-gravar`. Resultado: "
              f"**{'REPROVADA' if medida['reprovado'] else 'verde'}**.", "",
              "| ferramenta | versão | achados | bloqueiam | com exceção | revisão | informativos | duração |",
              "|---|---|---|---|---|---|---|---|"]
    for nome, f in medida["ferramentas"].items():
        linhas.append(f"| {nome} | {f['versao']} | {f['achados']} | {f['bloqueantes']} | {f['com_excecao']} | "
                      f"{f['revisao']} | {f['informativos']} | {f['duracao_s']} s |")
    if "trivy" in medida["ferramentas"]:
        t = medida["ferramentas"]["trivy"]
        linhas.append("")
        estado = ("presente — camadas varridas" if t.get("imagem_presente")
                  else "ausente nesta máquina — só deploy/ (Dockerfile e compose) foi varrido")
        linhas.append(f"trivy: imagem `{t.get('imagem')}` {estado}.")
    if "zap" in medida["ferramentas"]:
        z = medida["ferramentas"]["zap"]
        linhas.append("")
        inst = "própria (uvicorn + nginx renderizado de deploy/nginx.conf)" if z.get("instancia_propria") else "externa"
        linhas.append(f"zap: instância {inst}, {'com' if z.get('autenticado') else 'sem'} sessão autenticada no "
                      "inquilino demo; só regras passivas.")
    linhas += ["", "### 9.2 Política de bloqueio", "", "| ferramenta | regra |", "|---|---|"]
    for nome, regra in POLITICA.items():
        linhas.append(f"| {nome} | {regra} |")
    linhas += ["", "### 9.3 Exceções vivas (docs/excecoes_seguranca.json)", ""]
    if excecoes:
        linhas += ["| ferramenta | id | alvo | motivo | prazo | dias | registrada | quem |",
                   "|---|---|---|---|---|---|---|---|"]
        for e in excecoes:
            dias = (dt.date.fromisoformat(e["prazo"]) - hoje).days
            alvo = e.get("arquivo") or e.get("pacote") or "—"
            linhas.append(f"| {e['ferramenta']} | {e['id']} | `{alvo}` | {e['motivo']} | {e['prazo']} | "
                          f"{'VENCIDA' if dias < 0 else dias} | {e['registrado_em']} | {e['quem']} |")
    else:
        linhas.append("Nenhuma.")
    linhas += ["", "### 9.4 Achados em revisão (não bloqueiam; lista de trabalho do adversário, item HARD-03)", ""]
    linhas += [f"- `{r}`" for r in medida.get("revisao", [])] or ["Nenhum."]
    if medida.get("bloqueantes"):
        linhas += ["", "### 9.5 Achados bloqueantes na última varredura registrada", ""]
        linhas += [f"- `{b}`" for b in medida["bloqueantes"]]
    linhas += ["", "### 9.6 Ferramentas binárias fixadas (deploy/ferramentas_binarias.txt)", "",
               "| ferramenta | versão | sha256 do pacote |", "|---|---|---|"]
    for nome, f in fixados.items():
        linhas.append(f"| {nome} | {f['versao']} | `{f['sha256'][:16]}…` |")
    linhas += ["", MARCA_FIM]
    return "\n".join(linhas) + "\n"


def _substituir_secao(texto: str, secao: str) -> str:
    i, j = texto.find(MARCA_INICIO), texto.find(MARCA_FIM)
    if i < 0 or j < 0:
        raise ErroVarredura(f"{DOC.name} sem os marcadores da seção gerada ({MARCA_INICIO[:30]}…)")
    return texto[:i] + secao + texto[j + len(MARCA_FIM) + 1:]


def secao_atual(texto: str) -> str:
    i, j = texto.find(MARCA_INICIO), texto.find(MARCA_FIM)
    if i < 0 or j < 0:
        raise ErroVarredura(f"{DOC.name} sem os marcadores da seção gerada")
    return texto[i:j + len(MARCA_FIM)] + "\n"


def gravar(resultado: dict, *, medida_caminho: Path = MEDIDA, doc_caminho: Path = DOC,
           hoje: dt.date | None = None) -> None:
    medida = resumo_para_medida(resultado)
    medida_caminho.parent.mkdir(parents=True, exist_ok=True)
    medida_caminho.write_text(json.dumps(medida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    secao = renderizar_secao(medida, resultado["excecoes"], binarios_fixados(), hoje=hoje)
    doc_caminho.write_text(_substituir_secao(doc_caminho.read_text(encoding="utf-8"), secao), encoding="utf-8")


def conferir_doc(*, medida_caminho: Path = MEDIDA, doc_caminho: Path = DOC,
                 excecoes_caminho: Path = EXCECOES) -> list[str]:
    """Diferenças entre a seção versionada e o que medida + exceções + lista de binários renderizam hoje. A coluna
    "dias" é relativa: por isso o cotejo ignora esse campo (mesma tabela renderizada em dias diferentes)."""
    if not medida_caminho.exists():
        return [f"{medida_caminho} não existe — rode `make seguranca-gravar`"]
    medida = json.loads(medida_caminho.read_text(encoding="utf-8"))
    esperado = renderizar_secao(medida, carregar_excecoes(excecoes_caminho), binarios_fixados())
    atual = secao_atual(doc_caminho.read_text(encoding="utf-8"))
    normal = lambda s: re.sub(r"\| (-?\d+|VENCIDA) \| (\d{4}-\d{2}-\d{2}) \|", "| dias | \\2 |", s)  # noqa: E731
    if normal(esperado) == normal(atual):
        return []
    import difflib

    dif = difflib.unified_diff(normal(atual).splitlines(), normal(esperado).splitlines(), "SEGURANCA.md", "esperado",
                               lineterm="", n=1)
    return list(dif)[:40]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ferramentas", default=",".join(FERRAMENTAS_PADRAO),
                   help=f"lista separada por vírgula entre {', '.join(TODAS)}")
    p.add_argument("--com-zap", action="store_true",
                   help="acrescenta o baseline do ZAP (sobe instância própria da trilha corrente)")
    p.add_argument("--zap-url", default=None, help="baseline contra esta URL já no ar em vez de subir uma instância")
    p.add_argument("--zap-credenciais", default=None,
                   help="arquivo `slug login senha` (padrão: PLAT_CREDENCIAIS_ARQUIVO)")
    p.add_argument("--json", type=Path, default=VAR / "ultima_varredura.json")
    p.add_argument("--gravar", action="store_true",
                   help="atualiza tests/medidas/HARD-01-seguranca.json e a seção gerada de docs/SEGURANCA.md")
    p.add_argument("--check-doc", action="store_true",
                   help="só confere a seção gerada contra a medida versionada (sem rodar nada)")
    p.add_argument("--sem-instalar", action="store_true", help="não chama scripts/ferramentas_seguranca.sh antes")
    args = p.parse_args(argv)

    if args.check_doc:
        try:
            dif = conferir_doc()
        except ErroVarredura as e:
            print(f"varredura_seguranca: {e}", file=sys.stderr)
            return 2
        if dif:
            print("varredura_seguranca: docs/SEGURANCA.md seção 9 diverge da medida/lista de exceções — "
                  "rode `make seguranca-gravar`:", file=sys.stderr)
            print("\n".join(dif), file=sys.stderr)
            return 1
        print("varredura_seguranca: seção gerada de docs/SEGURANCA.md confere")
        return 0

    ferramentas = tuple(f.strip() for f in args.ferramentas.split(",") if f.strip())
    if args.com_zap and "zap" not in ferramentas:
        ferramentas += ("zap",)
    desconhecidas = [f for f in ferramentas if f not in TODAS]
    if desconhecidas:
        print(f"varredura_seguranca: ferramenta desconhecida {desconhecidas}", file=sys.stderr)
        return 2
    if not args.sem_instalar and any(f in ("gitleaks", "trivy", "zap") for f in ferramentas):
        binarias = [f for f in ferramentas if f in ("gitleaks", "trivy", "zap")]
        r = subprocess.run(["bash", str(RAIZ / "scripts" / "ferramentas_seguranca.sh"), *binarias],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"varredura_seguranca: instalação das ferramentas falhou: {r.stderr[-800:]}", file=sys.stderr)
            return 2
    try:
        resultado = avaliar(ferramentas, zap_url=args.zap_url, zap_credenciais=args.zap_credenciais)
    except ErroVarredura as e:
        print(f"varredura_seguranca: {e}", file=sys.stderr)
        return 2

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    for nome, f in resultado["ferramentas"].items():
        print(f"[{nome:>9}] {f['versao']:<10} achados={f['achados']:<4} bloqueiam={f['bloqueantes']:<3} "
              f"excecao={f['com_excecao']:<3} revisao={f['revisao']:<3} info={f['informativos']:<4} {f['duracao_s']} s")
    for a in resultado["achados"]:
        if a["bloqueia"]:
            alvo = a.get("arquivo") or a.get("pacote") or ""
            print(f"  BLOQUEIA {a['ferramenta']} {a['id']} [{a['severidade']}] {alvo}:{a.get('linha') or ''} "
                  f"{a['titulo'][:90]}")
    for e in resultado["excecoes_vencidas"]:
        print(f"  exceção VENCIDA (já não vale): {e['ferramenta']} {e['id']} "
              f"{e.get('arquivo') or e.get('pacote') or ''} prazo {e['prazo']}")
    if args.gravar:
        try:
            gravar(resultado)
        except ErroVarredura as e:
            print(f"varredura_seguranca: {e}", file=sys.stderr)
            return 2
        print(f"varredura_seguranca: gravado {MEDIDA.relative_to(RAIZ)} e a seção 9 de {DOC.relative_to(RAIZ)}")
    if resultado["reprovado"]:
        print("varredura_seguranca: achado bloqueante sem exceção viva em docs/excecoes_seguranca.json — corrija ou "
              "registre uma exceção com prazo e responsável", file=sys.stderr)
        return 1
    print("varredura_seguranca: nenhum achado bloqueante sem exceção — ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
