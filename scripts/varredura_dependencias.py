"""Varredura de dependência com CVE conhecido (item L7-03-f-dependencias-cve-log-correcoes; docs/SEGURANCA.md
seção 7). Roda `pip-audit` (PyPA, Apache-2.0, mantido ativamente — ver justificativa na seção 7 do doc; a
alternativa `safety` foi descartada porque a versão atual exige conta/login para o banco de vulnerabilidade
completo, o que quebraria `make seguranca-deps` numa máquina sem credencial) contra um `requirements.txt`, então
classifica cada achado por severidade (crítica/alta/média/baixa/desconhecida) consultando o registro OSV.dev do
próprio id — MEDIDO 06/09/2026: o registro por id `PYSEC-*` não traz rótulo pronto (`database_specific` nulo),
mas o *alias* `GHSA-*` do mesmo id traz (`database_specific.severity`); quando só há o vetor CVSS (sem rótulo),
a nota v3.1 é calculada aqui (fórmula oficial FIRST) e mapeada High/Medium/Low.

Sai != 0 (reprova `make seguranca-deps`) quando há achado crítico OU alto sem exceção viva em
`docs/excecoes_cve.json` (uma exceção tem `cve`, `pacote`, `motivo`, `prazo` — expira sozinha: `prazo` no
passado deixa de valer e volta a reprovar). Achado de severidade desconhecida (rede fora, ou OSV sem CVSS e sem
GHSA) é tratado como alto por padrão-seguro (nunca passa em silêncio) — documentado na seção 7."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
CACHE_DIR = RAIZ / "var" / "cache" / "osv"
OSV_URL = "https://api.osv.dev/v1/vulns/{}"
TIMEOUT_S = 8

SEVERIDADES = ("critica", "alta", "media", "baixa")
GRAVES = {"critica", "alta"}
ROTULO_OSV_PARA_SEVERIDADE = {
    "CRITICAL": "critica",
    "HIGH": "alta",
    "MODERATE": "media",
    "MEDIUM": "media",
    "LOW": "baixa",
}


class ErroVarredura(RuntimeError):
    """pip-audit não rodou (binário ausente, requirements.txt ilegível, etc.) — nunca vira "0 achado"."""


# ---------------------------------------------------------------- CVSS v3.1 base score (fórmula oficial FIRST)
_PESO_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_PESO_AC = {"L": 0.77, "H": 0.44}
_PESO_UI = {"N": 0.85, "R": 0.62}
_PESO_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}


def _peso_pr(valor: str, escopo_mudou: bool) -> float:
    if valor == "N":
        return 0.85
    if valor == "L":
        return 0.68 if escopo_mudou else 0.62
    if valor == "H":
        return 0.50 if escopo_mudou else 0.27
    raise ValueError(f"PR inválido: {valor}")


def cvss_v3_nota(vetor: str) -> float:
    """"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L" → nota base (0.0-10.0), arredondada para cima em 1 casa
    (regra oficial "roundup"). Levanta ValueError se o vetor não tiver os 8 componentes esperados."""
    campos = dict(p.split(":", 1) for p in vetor.split("/") if ":" in p)
    escopo_mudou = campos.get("S") == "C"
    c, i, a = _PESO_CIA[campos["C"]], _PESO_CIA[campos["I"]], _PESO_CIA[campos["A"]]
    iss = 1 - ((1 - c) * (1 - i) * (1 - a))
    impacto = (7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15) if escopo_mudou else 6.42 * iss
    explorabilidade = (
        8.22 * _PESO_AV[campos["AV"]] * _PESO_AC[campos["AC"]] * _peso_pr(campos["PR"], escopo_mudou)
        * _PESO_UI[campos["UI"]]
    )
    if impacto <= 0:
        return 0.0
    bruta = min(1.08 * (impacto + explorabilidade), 10) if escopo_mudou else min(impacto + explorabilidade, 10)
    # roundup CVSS: 1 casa decimal, sempre para cima
    return int(bruta * 10 + 0.9999999) / 10 if bruta * 10 != int(bruta * 10) else bruta


def _severidade_da_nota(nota: float) -> str:
    if nota >= 9.0:
        return "critica"
    if nota >= 7.0:
        return "alta"
    if nota >= 4.0:
        return "media"
    if nota > 0.0:
        return "baixa"
    return "baixa"


# ---------------------------------------------------------------- OSV.dev (severidade por id, com cache local)
def _osv_registro(vuln_id: str, *, offline: bool = False) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    arq = CACHE_DIR / f"{vuln_id}.json"
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    if offline:
        return None
    try:
        with urllib.request.urlopen(OSV_URL.format(vuln_id), timeout=TIMEOUT_S) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados


def severidade_de(vuln_id: str, aliases: list[str], *, offline: bool = False) -> tuple[str, str]:
    """(severidade, origem) — tenta o rótulo pronto (o próprio id, depois cada alias GHSA-*), senão calcula o
    vetor CVSS do próprio id; "desconhecida" se nada disso resolver (padrão-seguro: chamador trata como alta)."""
    for candidato in [vuln_id, *[a for a in aliases if a.startswith("GHSA-")]]:
        reg = _osv_registro(candidato, offline=offline)
        if reg is None:
            continue
        rotulo = (reg.get("database_specific") or {}).get("severity")
        if rotulo in ROTULO_OSV_PARA_SEVERIDADE:
            return ROTULO_OSV_PARA_SEVERIDADE[rotulo], f"rotulo:{candidato}"
        for s in reg.get("severity") or []:
            if s.get("type", "").startswith("CVSS"):
                try:
                    nota = cvss_v3_nota(s["score"])
                except (KeyError, ValueError):
                    continue
                return _severidade_da_nota(nota), f"cvss:{candidato}={nota}"
    return "desconhecida", "sem_dado"


# ---------------------------------------------------------------- pip-audit
def rodar_pip_audit(requirements: Path, *, executavel: str | None = None) -> list[dict]:
    if not requirements.exists():
        raise ErroVarredura(f"{requirements} não existe")
    binario = executavel or str(RAIZ / "venv" / "bin" / "pip-audit")
    try:
        r = subprocess.run(
            [binario, "-r", str(requirements), "--format", "json", "--progress-spinner", "off"],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError as e:
        raise ErroVarredura(f"pip-audit não encontrado em {binario} (pip install pip-audit na venv)") from e
    except subprocess.TimeoutExpired as e:
        raise ErroVarredura("pip-audit não respondeu em 180 s") from e
    if r.returncode not in (0, 1):  # 0 = sem achado, 1 = achado(s); qualquer outro = falha do próprio pip-audit
        raise ErroVarredura(f"pip-audit saiu com {r.returncode}: {r.stderr[-2000:]}")
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ErroVarredura(f"pip-audit não devolveu JSON: {r.stdout[-500:]}") from e
    achados = []
    vistos: set[tuple[str, str, str]] = set()
    for dep in payload.get("dependencies", []):
        for v in dep.get("vulns", []):
            chave = (dep["name"], dep["version"], v["id"])
            if chave in vistos:  # pip-audit por vezes traz o MESMO id duplicado (fontes PyPI+OSV combinadas)
                continue
            vistos.add(chave)
            achados.append(
                {
                    "pacote": dep["name"],
                    "versao": dep["version"],
                    "id": v["id"],
                    "aliases": v.get("aliases", []),
                    "fix_versions": v.get("fix_versions", []),
                }
            )
    return achados


# ---------------------------------------------------------------- exceções (docs/excecoes_cve.json)
def carregar_excecoes(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    return doc.get("excecoes", [])


def excecao_viva(achado: dict, excecoes: list[dict], *, hoje: dt.date | None = None) -> dict | None:
    hoje = hoje or dt.date.today()
    ids = {achado["id"], *achado.get("aliases", [])}
    for exc in excecoes:
        if exc.get("cve") not in ids or exc.get("pacote") != achado["pacote"]:
            continue
        prazo = exc.get("prazo")
        if prazo and dt.date.fromisoformat(prazo) < hoje:
            continue  # expirada: some sozinha, sem editar nada
        return exc
    return None


# ---------------------------------------------------------------- laço principal
def avaliar(
    requirements: Path,
    excecoes_caminho: Path,
    *,
    executavel: str | None = None,
    offline_severidade: bool = False,
) -> dict[str, Any]:
    achados = rodar_pip_audit(requirements, executavel=executavel)
    excecoes = carregar_excecoes(excecoes_caminho)
    linhas = []
    reprovado = False
    for a in achados:
        severidade, origem = severidade_de(a["id"], a["aliases"], offline=offline_severidade)
        grave = severidade in GRAVES or severidade == "desconhecida"
        exc = excecao_viva(a, excecoes) if grave else None
        bloqueia = grave and exc is None
        reprovado = reprovado or bloqueia
        linha = {**a, "severidade": severidade, "origem_severidade": origem, "excecao": exc, "bloqueia": bloqueia}
        linhas.append(linha)
    return {"requirements": str(requirements), "achados": linhas, "reprovado": reprovado}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--requirements", type=Path, default=RAIZ / "requirements.txt")
    p.add_argument("--excecoes", type=Path, default=RAIZ / "docs" / "excecoes_cve.json")
    p.add_argument("--json", type=Path, help="grava o relatório completo aqui (além de imprimir o resumo)")
    p.add_argument("--pip-audit", dest="executavel", default=None)
    args = p.parse_args(argv)

    try:
        resultado = avaliar(args.requirements, args.excecoes, executavel=args.executavel)
    except ErroVarredura as e:
        print(f"varredura_dependencias: {e}", file=sys.stderr)
        return 2

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")

    if not resultado["achados"]:
        print(f"varredura_dependencias: 0 CVE conhecido em {args.requirements.name}")
        return 0

    for a in resultado["achados"]:
        marca = "BLOQUEIA" if a["bloqueia"] else ("excecao" if a["excecao"] else "ok")
        print(
            f"[{a['severidade']:>11}] {a['pacote']}=={a['versao']}  {a['id']}  fix={a['fix_versions'] or '?'}  "
            f"({a['origem_severidade']})  {marca}"
        )
    if resultado["reprovado"]:
        print(
            "varredura_dependencias: CVE crítico/alto (ou de severidade desconhecida) sem exceção viva em "
            f"{args.excecoes} — documente uma exceção com prazo ou corrija a versão", file=sys.stderr,
        )
        return 1
    print("varredura_dependencias: nenhum achado grave sem exceção — ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
