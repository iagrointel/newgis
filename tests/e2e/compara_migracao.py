#!/usr/bin/env python3
"""Veredito de uma leva da migracao de folha: compara as duas fases gravadas por test_migracao_folha.py.

    venv/bin/python tests/e2e/compara_migracao.py <leva>

Reprova (saida 1) quando:
  - a impressao digital da ARVORE mudou entre antes e depois (migracao de folha nao mexe em estrutura);
  - a tela montava antes (body[data-pronto=1]) e deixou de montar depois;
  - apareceu violacao de contraste ou violacao de axe que nao existia antes.
Violacao que JA existia antes fica registrada como herdada: nao e regressao desta migracao.

Escreve tests/e2e/migracao_saida/leva<N>_veredito.json e o inventario com bytes e sha256 das capturas em
tests/e2e/capturas/INVENTARIO_MIG.txt (as PNG nao entram no git; o que fica versionado e o inventario)."""

import hashlib
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "migracao_saida"
CAPTURAS = AQUI / "capturas"


def _chave_contraste(v: dict) -> str:
    return f"{v['sel']}|{v['texto']}"


def _chave_axe(v: dict) -> str:
    return f"{v['regra']}|{v['impacto']}"


def comparar(leva: int) -> dict:
    antes = json.loads((SAIDA / f"leva{leva}_antes.json").read_text(encoding="utf-8"))
    depois = json.loads((SAIDA / f"leva{leva}_depois.json").read_text(encoding="utf-8"))
    veredito: dict = {"leva": leva, "telas": {}, "reprovas": []}
    for nome, d in depois.items():
        a = antes.get(nome)
        t: dict = {"rota": d["rota"], "montou_antes": a and a["montou"], "montou_depois": d["montou"]}
        if a is None:
            veredito["reprovas"].append(f"{nome}: sem a fase 'antes'")
            veredito["telas"][nome] = t
            continue
        if a["montou"] and not d["montou"]:
            veredito["reprovas"].append(f"{nome}: montava antes e nao monta depois")
        iguais = a.get("estrutura") == d.get("estrutura")
        t["estrutura_igual"] = iguais
        t["elementos"] = len(d.get("estrutura") or [])
        if not iguais:
            ea, ed = a.get("estrutura") or [], d.get("estrutura") or []
            difs = [f"{i}: {x!r} -> {y!r}" for i, (x, y) in enumerate(zip(ea, ed)) if x != y][:5]
            if len(ea) != len(ed):
                difs.append(f"tamanho {len(ea)} -> {len(ed)}")
            t["diferencas_de_estrutura"] = difs
            veredito["reprovas"].append(f"{nome}: a arvore mudou ({'; '.join(difs)})")
        t["temas"] = {}
        for tema in ("escuro", "claro"):
            ta, td = a["temas"][tema], d["temas"][tema]
            ca = {_chave_contraste(v) for v in ta["violacoes_contraste"]}
            cd = {_chave_contraste(v) for v in td["violacoes_contraste"]}
            aa = {_chave_axe(v) for v in ta["axe"]}
            ad = {_chave_axe(v) for v in td["axe"]}
            novas_c, novas_a = sorted(cd - ca), sorted(ad - aa)
            t["temas"][tema] = {
                "nos_medidos_antes": ta["nos_medidos"], "nos_medidos_depois": td["nos_medidos"],
                "contraste_antes": len(ca), "contraste_depois": len(cd),
                "contraste_novas": novas_c, "contraste_herdadas": sorted(ca & cd),
                "contraste_resolvidas": sorted(ca - cd),
                "axe_antes": sorted(aa), "axe_depois": sorted(ad), "axe_novas": novas_a,
            }
            if novas_c:
                veredito["reprovas"].append(f"{nome} [{tema}]: violacao de contraste nova: {novas_c}")
            if novas_a:
                veredito["reprovas"].append(f"{nome} [{tema}]: violacao de axe nova: {novas_a}")
        veredito["telas"][nome] = t
    return veredito


def inventario() -> list[str]:
    linhas = []
    for p in sorted(CAPTURAS.glob("MIG_*.png")):
        linhas.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.stat().st_size:9d}  {p.name}")
    return linhas


def main() -> int:
    leva = int(sys.argv[1])
    v = comparar(leva)
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / f"leva{leva}_veredito.json").write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    linhas = inventario()
    (CAPTURAS / "INVENTARIO_MIG.txt").write_text(
        "# capturas da migracao de folha (tests/e2e/test_migracao_folha.py). sha256  bytes  arquivo\n"
        + "\n".join(linhas) + "\n", encoding="utf-8")
    for nome, t in v["telas"].items():
        esc = t.get("temas", {}).get("escuro", {})
        print(f"{nome:28s} arvore={'igual' if t.get('estrutura_igual') else 'MUDOU'} "
              f"elementos={t.get('elementos')} contraste {esc.get('contraste_antes')}->{esc.get('contraste_depois')} "
              f"montou={t['montou_antes']}->{t['montou_depois']}")
    print(f"\ncapturas no inventario: {len(linhas)}")
    if v["reprovas"]:
        print("\nREPROVAS:")
        for r in v["reprovas"]:
            print(" -", r)
        return 1
    print("\nleva aprovada: mesma arvore, nenhuma violacao nova.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
