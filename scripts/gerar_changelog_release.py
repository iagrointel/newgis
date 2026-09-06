"""Gera o rascunho de changelog de uma versão (formato keep-a-changelog, https://keepachangelog.com/) a partir
do `git log` desde a última etiqueta (item L7-15-processo-release, chamado por `scripts/preparar_release.sh`).
Classificação em Adicionado/Alterado/Corrigido/Segurança é HEURÍSTICA por palavra-chave na primeira linha do
commit — esta casa não tem convenção de commit estruturado (commits são em português, prosa livre descrevendo
o item do laço); o que a heurística não reconhecer cai em Alterado. É rascunho: revisão humana antes de colar
em CHANGELOG.md (checklist de `docs/RELEASE.md`) — este script nunca edita CHANGELOG.md sozinho."""

import argparse
import datetime
import subprocess
from pathlib import Path

PALAVRAS = {
    "Segurança": ("cve", "segurança", "vulnerabilidade", "segredo vazado", "vazamento"),
    "Corrigido": ("corrige", "conserta", "corrigido", "regressão", "ajusta", "bug"),
    "Adicionado": ("adiciona", "cria ", "criado", "novo ", "nova ", "implementa", "acrescenta"),
}
SECOES_ORDEM = ("Adicionado", "Alterado", "Corrigido", "Segurança")


def classificar(msg: str) -> str:
    m = msg.lower()
    for secao, chaves in PALAVRAS.items():
        if any(c in m for c in chaves):
            return secao
    return "Alterado"


def gerar(repo: Path, versao: str, intervalo: str) -> str:
    saida = subprocess.run(
        ["git", "-C", str(repo), "log", "--pretty=%H\x1f%s", intervalo],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    secoes: dict[str, list[str]] = {s: [] for s in SECOES_ORDEM}
    for linha in saida.splitlines():
        if not linha.strip():
            continue
        sha, _, msg = linha.partition("\x1f")
        secoes[classificar(msg)].append(f"- {msg} ({sha[:7]})")
    hoje = datetime.date.today().isoformat()
    partes = [f"## [{versao}] - {hoje}\n\n"]
    algo = False
    for secao in SECOES_ORDEM:
        if secoes[secao]:
            algo = True
            partes.append(f"### {secao}\n")
            partes.extend(x + "\n" for x in secoes[secao])
            partes.append("\n")
    if not algo:
        partes.append("### Alterado\n- (sem commits novos desde a última etiqueta)\n\n")
    return "".join(partes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--versao", required=True)
    ap.add_argument("--range", dest="intervalo", required=True)
    ap.add_argument("--saida", required=True)
    args = ap.parse_args()
    texto = gerar(Path(args.repo), args.versao, args.intervalo)
    Path(args.saida).write_text(texto, encoding="utf-8")
    print(texto, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
