"""Gerador do roteiro de demonstração (item L7-29-roteiro-demonstração).

O texto do roteiro é do cronista, em docs/DEMO.md. A lista "o que a demonstração não faz ainda" NÃO é
escrita à mão: é GERADA da seção "Fronteira: o que o produto NÃO faz ainda" de laco/PAINEL.md (que o
gerente regenera de laco/estado.json). Entre os marcadores

    <!-- gerado de laco/PAINEL.md:inicio -->
    ...
    <!-- gerado de laco/PAINEL.md:fim -->

nada é editado à mão; --preencher regrava o bloco e --validar reprova o arquivo se o bloco commitado
divergir da regeneração (mesmo contrato do manual: divergiu, regenere e commit).

O validador também cumpre as cláusulas estruturais do portão: cada passo declara duração, "o que
dizer", "não prometer" e o e2e que o percorre; os tempos declarados somam 30; a versão de 10 minutos
existe, soma no máximo 10 e só cita passos declarados; o texto obedece à regra de escrita de 03/09
(sem metáfora da lista, sem exclamação, sem "você recebe").

Uso:
    venv/bin/python docs/gerar_demo.py --validar      # estrutura + bloco commitado == regenerado
    venv/bin/python docs/gerar_demo.py --preencher    # regrava o bloco a partir de laco/PAINEL.md
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "docs" / "DEMO.md"
PAINEL = RAIZ / "laco" / "PAINEL.md"

M_INICIO = "<!-- gerado de laco/PAINEL.md:inicio -->"
M_FIM = "<!-- gerado de laco/PAINEL.md:fim -->"

RE_PASSO = re.compile(r"^## Passo (\d+) — (.+?) \((\d+) min\)\s*$", re.M)
RE_VERSAO10 = re.compile(r"^## Versão de 10 minutos\s*$", re.M)
RE_LINHA10 = re.compile(r"^- Passo (\d+) \((\d+) min\)", re.M)
TEMPO_TOTAL_MIN = 30
TEMPO_VERSAO10_MIN = 10

# regra de escrita para cliente (03/09): zero metáfora e zero gíria; tom sereno, sem exclamação;
# nunca "você recebe". Lista fechada, com a palavra que a regra proíbe e o motivo ao lado.
PALAVRAS_PROIBIDAS = {
    "maquiagem": "metáfora (regra 2)",
    "acolchoado": "metáfora (regra 2)",
    "diamante": "metáfora (regra 2)",
    "viaja": "gíria de medidor (regra 2)",
    "esquenta": "gíria (regra 2; usar 'passou da potência nominal')",
    "acender": "gíria (regra 2; usar 'aumento de radiância noturna')",
    "impressionante": "superlativo (regra 6)",
    "incrível": "superlativo (regra 6)",
    "robusto": "elogio ao próprio método (regra 6)",
    "você recebe": "enquadramento de entrega proibido pelo dono",
}
RE_EXCLAMACAO = re.compile(r"[!¡]")


def fronteira_do_painel() -> str:
    """Corpo da seção '## Fronteira: o que o produto NÃO faz ainda' de laco/PAINEL.md, verbatim."""
    texto = PAINEL.read_text(encoding="utf-8")
    m = re.search(r"^## Fronteira: o que o produto NÃO faz ainda\s*$", texto, re.M)
    if not m:
        raise SystemExit("laco/PAINEL.md sem a seção 'Fronteira: o que o produto NÃO faz ainda' (regenere o painel)")
    resto = texto[m.end():]
    proxima = re.search(r"^## ", resto, re.M)
    if not proxima:
        raise SystemExit("laco/PAINEL.md: seção Fronteira sem seção seguinte (painel truncado?)")
    return resto[: proxima.start()].strip("\n")


def bloco_gerado() -> str:
    agora = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    cabecalho = (
        "## O que a demonstração não faz ainda\n\n"
        f"Gerado de laco/PAINEL.md (seção Fronteira) em {agora}. "
        "Não editar entre os marcadores: rode `venv/bin/python docs/gerar_demo.py --preencher` "
        "depois de regenerar o painel.\n\n"
    )
    return cabecalho + fronteira_do_painel().strip() + "\n"


def bloco_commitado(demo: str) -> str | None:
    ini = demo.find(M_INICIO)
    fim = demo.find(M_FIM)
    if ini == -1 or fim == -1 or fim < ini:
        return None
    return demo[ini + len(M_INICIO): fim].strip("\n")


def preencher() -> Path:
    demo = DEMO.read_text(encoding="utf-8")
    if bloco_commitado(demo) is None:
        raise SystemExit(f"{os.path.relpath(DEMO, RAIZ)} sem os marcadores {M_INICIO!r} / {M_FIM!r}")
    novo = demo[: demo.find(M_INICIO) + len(M_INICIO)] + "\n" + bloco_gerado() + "\n" + demo[demo.find(M_FIM):]
    DEMO.write_text(novo, encoding="utf-8")
    return DEMO


def parse_passos(demo: str) -> dict[int, dict]:
    """{n: {titulo, minutos, dizer, nao_prometer, e2e}} lido das seções '## Passo N — ...'."""
    cortes = [(m.start(), m.group(1), m.group(2), int(m.group(3))) for m in RE_PASSO.finditer(demo)]
    fim_passos = RE_VERSAO10.search(demo)
    passos: dict[int, dict] = {}
    for i, (pos, numero, titulo, minutos) in enumerate(cortes):
        fim = cortes[i + 1][0] if i + 1 < len(cortes) else (fim_passos.start() if fim_passos else len(demo))
        secao = demo[pos:fim]
        dizer = re.search(r"^- o que dizer: (.+)$", secao, re.M)
        nao = re.search(r"^- não prometer: (.+)$", secao, re.M)
        e2e = re.search(r"^- e2e: (.+)$", secao, re.M)
        passos[int(numero)] = {
            "titulo": titulo.strip(),
            "minutos": minutos,
            "dizer": dizer.group(1).strip() if dizer else None,
            "nao_prometer": nao.group(1).strip() if nao else None,
            "e2e": e2e.group(1).strip() if e2e else None,
        }
    return passos


def parse_versao10(demo: str) -> list[tuple[int, int]]:
    ini = RE_VERSAO10.search(demo)
    if not ini:
        return []
    fim = demo.find(M_INICIO, ini.end())
    corpo = demo[ini.end(): fim if fim != -1 else len(demo)]
    return [(int(a), int(b)) for a, b in RE_LINHA10.findall(corpo)]


def validar_regra_de_escrita(texto: str) -> list[str]:
    """violations da regra de escrita que a máquina consegue ver: palavras da lista, exclamação."""
    achados = []
    for termo, motivo in PALAVRAS_PROIBIDAS.items():
        if re.search(rf"\b{re.escape(termo)}\b", texto, re.I):
            achados.append(f"{termo!r}: {motivo}")
    corpo = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)  # marcadores não são texto de leitor
    if RE_EXCLAMACAO.search(corpo):
        achados.append("exclamação no texto (regra 6: tom sereno)")
    return achados


def validar() -> None:
    demo = DEMO.read_text(encoding="utf-8")
    passos = parse_passos(demo)
    if not passos:
        raise SystemExit("nenhum '## Passo N — título (X min)' em docs/DEMO.md")
    numeros = sorted(passos)
    if numeros != list(range(1, len(numeros) + 1)):
        raise SystemExit(f"números de passo descontínuos: {numeros}")
    soma = sum(p["minutos"] for p in passos.values())
    if soma > TEMPO_TOTAL_MIN:
        raise SystemExit(f"tempos declarados somam {soma} min; o roteiro promete no máximo {TEMPO_TOTAL_MIN}")
    for n, p in sorted(passos.items()):
        faltam = [c for c in ("dizer", "nao_prometer", "e2e") if not p[c]]
        if faltam:
            raise SystemExit(f"passo {n} ({p['titulo']}) sem {faltam}")
        if not (RAIZ / p["e2e"]).is_file():
            raise SystemExit(f"passo {n}: e2e {p['e2e']} não existe")
    versao10 = parse_versao10(demo)
    if not versao10:
        raise SystemExit("docs/DEMO.md sem '## Versão de 10 minutos'")
    soma10 = sum(m for _, m in versao10)
    if soma10 > TEMPO_VERSAO10_MIN:
        raise SystemExit(f"versão de 10 minutos soma {soma10} min")
    desconhecidos = [n for n, _ in versao10 if n not in passos]
    if desconhecidos:
        raise SystemExit(f"versão de 10 minutos cita passos que não existem: {desconhecidos}")
    ordem = [n for n, _ in versao10]
    if ordem != sorted(ordem):
        raise SystemExit("versão de 10 minutos fora da ordem dos passos")
    violacoes = validar_regra_de_escrita(re.sub(M_INICIO + ".*?" + M_FIM, " ", demo, flags=re.S))
    if violacoes:
        raise SystemExit("regra de escrita de 03/09 violada em docs/DEMO.md: " + "; ".join(violacoes))
    commitado = bloco_commitado(demo)
    if commitado is None:
        raise SystemExit("docs/DEMO.md sem os marcadores do bloco gerado")
    gerado = bloco_gerado().strip("\n")
    if commitado != gerado:
        raise SystemExit(
            "docs/DEMO.md: bloco 'não faz ainda' diverge de laco/PAINEL.md; "
            "rode venv/bin/python docs/gerar_demo.py --preencher e commit"
        )
    _validar_painel_nao_esta_velho()
    print(f"roteiro válido: {len(passos)} passos, {soma} min declarados; versão de 10 min com {len(versao10)} passos")


# 17/09/2026: existem DUAS cópias do laço — a viva em /home/dev/plataforma/laco (o gerente trabalha nela)
# e esta, rastreada no git. Em 16/09 a rastreada estava congelada no turno 3 e este gerador leu dela, o que
# fez o roteiro AFIRMAR que L1 e L4 inteiras não existiam, com código, tela e rota no mesmo tronco. Negar
# funcionalidade que existe é pior para uma demonstração do que omitir. A trava abaixo compara o placar do
# painel lido com o do estado VIVO; divergiu, reprova e diz o que rodar. Se o laço vivo não estiver nesta
# máquina (instalação de cliente, appliance), não há o que comparar e a trava se cala.
LACO_VIVO = Path("/home/dev/plataforma/laco/estado.json")


def _validar_painel_nao_esta_velho() -> None:
    if not LACO_VIVO.is_file() or not PAINEL.is_file():
        return
    import json

    try:
        vivo = json.loads(LACO_VIVO.read_text(encoding="utf-8")).get("placar") or {}
    except Exception:
        return
    painel = PAINEL.read_text(encoding="utf-8")
    for chave, rotulo in (("entregues", "entregue"), ("refutados", "refutado"), ("pendentes", "pendente")):
        n = vivo.get(chave)
        if n is None:
            continue
        if not re.search(rf"^\|\s*{rotulo}\s*\|\s*{n}\s*\|", painel, re.M):
            raise SystemExit(
                f"laco/PAINEL.md está velho: o estado vivo diz {rotulo}={n} e o painel não. "
                "Regenere com `python3 /home/dev/plataforma/laco/gera_painel.py`, copie o PAINEL.md "
                "para enterprise/laco/ e rode `--preencher` de novo. "
                "Roteiro gerado de painel velho NEGA funcionalidade que existe."
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validar", action="store_true", help="estrutura + bloco gerado atual")
    parser.add_argument("--preencher", action="store_true", help="regrava o bloco a partir de laco/PAINEL.md")
    opcoes = parser.parse_args()
    sys.path.insert(0, str(RAIZ))
    if opcoes.preencher:
        print(f"bloco regravado em {os.path.relpath(preencher(), RAIZ)}")
        return
    validar()


if __name__ == "__main__":
    main()
