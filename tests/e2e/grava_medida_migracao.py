#!/usr/bin/env python3
"""Escreve tests/medidas/L0-14-b-migracao-folha.json a partir do que foi MEDIDO.

    venv/bin/python tests/e2e/grava_medida_migracao.py

Nenhum numero e digitado: cada medida sai dos vereditos de leva em tests/e2e/migracao_saida/, do manifesto
tests/e2e/telas_migracao.json, do inventario de capturas e da varredura do proprio repositorio (a mesma
contagem que a catraca TELAS_NA_FOLHA_ANTIGA usa em tests/unit/test_estilo_tokens.py)."""

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AQUI = RAIZ / "tests" / "e2e"
SAIDA = AQUI / "migracao_saida"
MEDIDA = RAIZ / "tests" / "medidas" / "L0-14-b-migracao-folha.json"


def telas_na_folha_antiga() -> list[str]:
    fora = []
    for p in sorted((RAIZ / "web").rglob("*.html")):
        if "/static/style.css" in p.read_text(encoding="utf-8"):
            fora.append(str(p.relative_to(RAIZ)))
    return fora


def main() -> None:
    manifesto = json.loads((AQUI / "telas_migracao.json").read_text(encoding="utf-8"))["telas"]
    vereditos = {}
    for p in sorted(SAIDA.glob("leva*_veredito.json")):
        v = json.loads(p.read_text(encoding="utf-8"))
        vereditos[v["leva"]] = v
    migradas = [t for t in manifesto if t.get("estado") == "migrada"]
    deixadas = [t for t in manifesto if t.get("estado") == "deixada_para_tras"]
    antigas = telas_na_folha_antiga()
    catraca = int(re.search(r"^TELAS_NA_FOLHA_ANTIGA = (\d+)",
                            (RAIZ / "tests" / "unit" / "test_estilo_tokens.py").read_text(encoding="utf-8"),
                            re.M).group(1))
    inventario = (AQUI / "capturas" / "INVENTARIO_MIG.txt")
    n_capturas = sum(1 for linha in inventario.read_text(encoding="utf-8").splitlines() if not linha.startswith("#")) if inventario.exists() else 0

    contraste = {"antes": 0, "depois": 0, "novas": 0, "herdadas": 0, "resolvidas": 0}
    axe_novas = 0
    arvores_iguais = 0
    arvores_totais = 0
    elementos = 0
    for v in vereditos.values():
        for t in v["telas"].values():
            arvores_totais += 1
            arvores_iguais += 1 if t.get("estrutura_igual") else 0
            elementos += t.get("elementos") or 0
            for tema in t.get("temas", {}).values():
                contraste["antes"] += tema["contraste_antes"]
                contraste["depois"] += tema["contraste_depois"]
                contraste["novas"] += len(tema["contraste_novas"])
                contraste["herdadas"] += len(tema["contraste_herdadas"])
                contraste["resolvidas"] += len(tema["contraste_resolvidas"])
                axe_novas += len(tema["axe_novas"])

    sha = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short=12", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    doc = {
        "item": "L0-14-b-migracao-folha",
        "medidas": {
            "telas_migradas_neste_ramo": {
                "valor": len(migradas), "unidade": "telas",
                "comando": "tests/e2e/telas_migracao.json, campo estado=migrada (o mesmo manifesto que o e2e percorre)",
            },
            "telas_ainda_na_folha_antiga": {
                "valor": len(antigas), "unidade": "telas",
                "comando": "grep '/static/style.css' em web/**/*.html; e a MESMA contagem de tests/unit/test_estilo_tokens.py::test_e_catraca_da_migracao_de_folha_nao_pode_crescer",
            },
            "catraca_no_codigo": {
                "valor": catraca, "unidade": "telas",
                "comando": "TELAS_NA_FOLHA_ANTIGA em tests/unit/test_estilo_tokens.py (o teste reprova se a contagem real for diferente, para cima ou para baixo)",
            },
            "telas_deixadas_para_tras": {
                "valor": len(deixadas), "unidade": "telas",
                "comando": "tests/e2e/telas_migracao.json, campo estado=deixada_para_tras, com o motivo no campo `motivo`: "
                           + ("; ".join(f"{t['nome']}: {t.get('motivo', 'sem motivo escrito')}" for t in deixadas) or "nenhuma"),
            },
            "arvore_identica_antes_e_depois": {
                "valor": f"{arvores_iguais} de {arvores_totais}", "unidade": "telas",
                "comando": "tests/e2e/compara_migracao.py: impressao digital tag#id.classe de cada elemento, em ordem de documento, nas duas fases. Troca de folha nao mexe em estrutura",
            },
            "elementos_conferidos": {
                "valor": elementos, "unidade": "elementos de DOM",
                "comando": "soma dos elementos da impressao digital das telas medidas (tema escuro)",
            },
            "violacoes_de_contraste_antes": {
                "valor": contraste["antes"], "unidade": "nos abaixo de 4,5:1 (3:1 texto grande)",
                "comando": "tests/e2e/test_migracao_folha.py com o JS_CONTRASTE do L0-14, nos dois temas, na instancia ANTES da migracao",
            },
            "violacoes_de_contraste_depois": {
                "valor": contraste["depois"], "unidade": "nos abaixo de 4,5:1 (3:1 texto grande)",
                "comando": "mesma varredura na instancia DEPOIS da migracao",
            },
            "violacoes_de_contraste_introduzidas": {
                "valor": contraste["novas"], "unidade": "nos",
                "comando": "violacao que existe depois e nao existia antes (chave seletor|texto). E este o alvo do item: zero",
            },
            "violacoes_de_contraste_herdadas": {
                "valor": contraste["herdadas"], "unidade": "nos",
                "comando": "ja existiam na folha antiga e continuam: nao sao regressao desta migracao, ficam registradas",
            },
            "violacoes_de_contraste_resolvidas": {
                "valor": contraste["resolvidas"], "unidade": "nos",
                "comando": "existiam na folha antiga e sumiram com a folha nova",
            },
            "violacoes_de_axe_introduzidas": {
                "valor": axe_novas, "unidade": "regras",
                "comando": "axe-core 4.12.1 (color-contrast, aria-allowed-attr, button-name, link-name, label) pelo apoio_axe, antes e depois; conta regra que aparece so no depois",
            },
            "capturas_no_inventario": {
                "valor": n_capturas, "unidade": "PNG",
                "comando": "tests/e2e/capturas/INVENTARIO_MIG.txt (sha256 e bytes de cada uma). As PNG nao entram no git; o que fica versionado e o inventario e o script que regenera",
            },
        },
        "levas": {str(k): {"telas": sorted(v["telas"]), "reprovas": v["reprovas"]} for k, v in sorted(vereditos.items())},
        "gerado_em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "assinado_por": "construtor (migracao da folha antiga web/style.css; continuacao do item L0-14-identidade-visual, ramo wt/telas)",
        "maquina": "chromium do PLAYWRIGHT (~/.cache/ms-playwright), 1280x800, locale pt-BR, dois temas. NUNCA conter memoria com `ulimit -v` (o Chromium morre com SIGTRAP: enderecamento virtual nao e memoria) - o teto vai em systemd-run --scope -p MemoryMax=. Base de dados: schema de TRILHA plat_ttelas (laco/trilha_ambiente.sh telas), nunca o schema `plat` de producao.",
        "capturas": "tests/e2e/capturas/MIG_<tela>_{antes,depois}_{escuro,claro}.png, regeneraveis por `bash tests/e2e/regerar_capturas_migracao.sh <leva>`",
    }
    MEDIDA.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("escrito:", MEDIDA.relative_to(RAIZ))
    for k, v in doc["medidas"].items():
        print(f"  {k}: {v['valor']} {v['unidade']}")


if __name__ == "__main__":
    main()
