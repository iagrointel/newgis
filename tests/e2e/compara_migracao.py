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
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "migracao_saida"
CAPTURAS = AQUI / "capturas"
MANIFESTO = AQUI / "telas_migracao.json"


def _campo_do_manifesto(nome: str, campo: str) -> list[str]:
    for t in json.loads(MANIFESTO.read_text(encoding="utf-8"))["telas"]:
        if t["nome"] == nome:
            return list(t.get(campo) or [])
    return []


def _prefixos_de_id_gerado(nome: str) -> list[str]:
    """Prefixos de `id` que a propria tela sorteia a cada desenho.

    Declarados tela a tela no manifesto (`ids_gerados`), com o motivo escrito ao lado. O caso e /sig: a
    arvore de camadas da um id a cada no com `idCurto()` (web/js/camadas.js) e escreve `chk-<sorteado>`
    no <input> e no `for` do <label>. Sao 62 nos de 1.756 que mudam de nome entre dois desenhos da MESMA
    arvore, com ou sem troca de folha. Normalizado o sorteio, as duas fases batem elemento a elemento.
    """
    return _campo_do_manifesto(nome, "ids_gerados")


def _prefixos_de_estado_vivo(nome: str) -> list[str]:
    """Prefixos de classe que, NAQUELA tela, carregam estado vivo do servidor e nao desenho.

    Declarados um a um no manifesto (campo `classes_de_estado_vivo`), com o motivo escrito ao lado --
    nunca uma regra geral. A tela /status e o caso: a classe do <td> e
    `status-estado-<ok|degradado|erro|ausente>`, escrita por web/js/status.js a partir de GET /api/status,
    e as duas fases falam com DOIS processos diferentes, cada um com a sua saude. Sem isto a comparacao
    acusa como "arvore mudou" a diferenca entre dois servicos, que nenhuma folha de estilo produz nem
    conserta. O que fica medido continua sendo tag, id e o resto das classes.
    """
    return _campo_do_manifesto(nome, "classes_de_estado_vivo")


def _sem_volatil(estrutura, classes: list[str], ids: list[str]):
    if not estrutura or not (classes or ids):
        return estrutura
    fora = []
    for item in estrutura:
        for pre in classes:
            item = re.sub(rf"(?<=\.){re.escape(pre)}[A-Za-z0-9_-]*", pre + "<estado vivo>", item)
        for pre in ids:
            item = re.sub(rf"(?<=#){re.escape(pre)}[A-Za-z0-9_-]*", pre + "<gerado>", item)
        fora.append(item)
    return fora


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
        classes = _prefixos_de_estado_vivo(nome)
        ids = _prefixos_de_id_gerado(nome)
        if classes:
            t["classes_de_estado_vivo_ignoradas"] = classes
        if ids:
            t["ids_gerados_ignorados"] = ids
        ea_cmp = _sem_volatil(a.get("estrutura"), classes, ids)
        ed_cmp = _sem_volatil(d.get("estrutura"), classes, ids)
        iguais = ea_cmp == ed_cmp
        t["estrutura_igual"] = iguais
        t["elementos"] = len(d.get("estrutura") or [])
        if not iguais:
            ea, ed = ea_cmp or [], ed_cmp or []
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
