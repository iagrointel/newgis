#!/usr/bin/env python3
"""O que master TINHA e a fusão PERDEU.

Nesta casa, oito entregas foram recuperadas numa só noite (18/09/2026) e nenhuma era trabalho novo:
era trabalho que existia em `master` e que uma fusão apagou. O item ficava marcado "refutado: artefato
ausente em master" e parecia coisa por construir. É um defeito do PROCESSO DE JUNÇÃO, não da
construção, e passava despercebido porque `git merge` só reclama de CONFLITO — e o caso perigoso não
conflita: um lado simplesmente vence, calado.

A assinatura é precisa e dá para medir. Com base A (ancestral comum), master M e ramo B:

  - master acrescentou uma linha depois que o ramo nasceu   (linha em M, não em A)
  - o ramo nunca tocou naquele trecho                        (linha não aparece em B)
  - e a fusão não tem a linha                                (não está no resultado)

Então a fusão perdeu trabalho de master. Isso NÃO é o mesmo que "o ramo removeu de propósito": se o
ramo removeu, a linha aparece como remoção no diff A→B, e o script não acusa.

Uso:
    python3 scripts/fusao_confere.py <ramo>            # confere ANTES de juntar (usa merge-tree)
    python3 scripts/fusao_confere.py <ramo> --apos     # confere DEPOIS (HEAD é a fusão)

Sai 0 quando nada se perdeu, 1 quando perdeu (e lista arquivo por arquivo), 2 em erro de uso.
"""

from __future__ import annotations

import subprocess
import sys


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def linhas_add(a: str, b: str, caminho: str) -> set[str]:
    """Linhas que b ACRESCENTA em relação a a, naquele arquivo (sem o '+' e sem vazias)."""
    saida = git("diff", "--unified=0", f"{a}..{b}", "--", caminho)
    return {l[1:].strip() for l in saida.splitlines()
            if l.startswith("+") and not l.startswith("+++") and l[1:].strip()}


def conteudo(rev: str, caminho: str) -> str:
    r = subprocess.run(["git", "show", f"{rev}:{caminho}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ramo = sys.argv[1]
    apos = "--apos" in sys.argv

    if apos:
        fusao = "HEAD"
        master = "HEAD^1"   # primeiro pai de um merge --no-ff é master
        base = git("merge-base", master, ramo).strip()
    else:
        master = "HEAD"
        base = git("merge-base", master, ramo).strip()
        fusao = None  # sem fusão ainda: comparamos contra o que o merge-tree produziria

    tocados = [l for l in git("diff", "--name-only", f"{base}..{ramo}").splitlines() if l]
    perdas: dict[str, list[str]] = {}

    for caminho in tocados:
        de_master = linhas_add(base, master, caminho)
        if not de_master:
            continue
        do_ramo = conteudo(ramo, caminho)
        if fusao is not None:
            resultado = conteudo(fusao, caminho)
        else:
            # sem a fusão feita, o pior caso é o ramo vencer inteiro: é exatamente o caso que já
            # aconteceu oito vezes. Conferir contra o conteúdo do ramo responde "se vencer, o que cai?"
            resultado = do_ramo
        sumiram = [l for l in de_master if l not in resultado and l not in do_ramo]
        if sumiram:
            perdas[caminho] = sumiram

    if not perdas:
        print(f"[fusao] nada que master tinha se perde em {ramo} (base {base[:9]})")
        return 0

    print(f"[fusao] ATENCAO: {len(perdas)} arquivo(s) perdem linhas que master TINHA e o ramo nunca tocou:")
    for caminho, linhas in sorted(perdas.items()):
        print(f"  {caminho}: {len(linhas)} linha(s)")
        for l in linhas[:5]:
            print(f"      - {l[:120]}")
        if len(linhas) > 5:
            print(f"      ... e mais {len(linhas) - 5}")
    print("[fusao] Isto NAO e conflito — o git nao reclamaria. Confira uma a uma antes de juntar:")
    print("[fusao] cada linha acima ou volta para a fusao, ou tem de haver razao escrita para sair.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
