"""A tabela de paridade com o Arcade (seção 10 de `docs/EXPRESSAO.md`) não pode voltar a mentir.

O ataque adversarial de 06/09/2026 (`laco/handoffs/T3/L2-10-c-ADVERSARIO.md`, seção 6) conferiu 17
linhas marcadas `feito` contra a documentação oficial e achou 6 erradas: a tabela era texto solto,
sem nada que a prendesse ao código. Este arquivo é a trava. Três regras, todas lidas dos arquivos:

1. toda linha `feito` tem de ter VETOR DE TESTE da nossa função (`tests/expressoes/vetores*.json`) —
   uma linha que promete comportamento idêntico sem um caso medido é promessa, não paridade;
2. a contagem escrita no cabeçalho de cada categoria e no parágrafo de abertura tem de bater com as
   linhas contadas na própria tabela;
3. `docs/PARIDADE.md` (a tabela por CATEGORIA que o resto do repositório cita) tem de repetir as
   mesmas contagens de `docs/EXPRESSAO.md` — as duas divergirem já foi defeito uma vez.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DOC = RAIZ / "docs" / "EXPRESSAO.md"
PARIDADE = RAIZ / "docs" / "PARIDADE.md"

sys.path.insert(0, str(RAIZ))
from app.expressao.avaliador_py import TABELA_FUNCOES  # noqa: E402

ESTADOS = {"feito", "parcial", "fora"}


def _secao_10() -> str:
    return DOC.read_text(encoding="utf-8").split("## 10. Paridade")[1].split("## 11.")[0]


def _linhas() -> list[tuple[str, str, str, str]]:
    """(categoria, nome no Arcade, nosso, estado) de cada linha de função da seção 10."""
    linhas = []
    categoria = ""
    for linha in _secao_10().splitlines():
        if linha.startswith("### "):
            categoria = linha[4:].strip()
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) >= 3 and campos[2] in ESTADOS:
            linhas.append((categoria, campos[0], campos[1], campos[2]))
    return linhas


def _entradas_dos_vetores() -> str:
    texto = []
    for arquivo in ("vetores.json", "vetores_convergencia.json"):
        for vetor in json.loads((RAIZ / "tests" / "expressoes" / arquivo).read_text(encoding="utf-8")):
            texto.append(vetor["entrada"])
    return "\n".join(texto)


def test_toda_linha_feito_tem_vetor_de_teste_da_nossa_funcao():
    entradas = _entradas_dos_vetores()
    sem_vetor = []
    for _categoria, arcade, nosso, estado in _linhas():
        if estado != "feito":
            continue
        nomes = [n for n in re.findall(r"`([A-Za-z]+)[`(]", nosso) if n in TABELA_FUNCOES]
        assert nomes, f"linha `feito` sem função nossa identificável: {arcade} → {nosso}"
        for nome in nomes:
            if f"{nome}(" not in entradas:
                sem_vetor.append(f"{arcade} → {nome}")
    assert not sem_vetor, f"linha marcada `feito` sem vetor de teste: {sem_vetor}"


def test_contagem_do_cabecalho_de_cada_categoria_bate_com_as_linhas():
    contado: Counter = Counter()
    for categoria, _arcade, _nosso, estado in _linhas():
        contado[(categoria, estado)] += 1
    categorias = {c for c, _a, _n, _e in _linhas()}
    assert len(categorias) == 7, categorias
    for categoria in categorias:
        m = re.search(r"\((\d+) feito · (\d+) parcial · (\d+) fora\)", categoria)
        assert m, f"cabeçalho de categoria sem contagem: {categoria}"
        escrito = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        real = tuple(contado[(categoria, e)] for e in ("feito", "parcial", "fora"))
        assert escrito == real, f"{categoria}: escrito {escrito}, contado {real}"


def test_total_escrito_na_abertura_bate_com_as_linhas():
    contado = Counter(estado for _c, _a, _n, estado in _linhas())
    m = re.search(r"\*\*(\d+) feito · (\d+) parcial · (\d+) fora\*\* de (\d+)", _secao_10())
    assert m, "parágrafo de abertura da seção 10 sem o total"
    assert (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (
        contado["feito"],
        contado["parcial"],
        contado["fora"],
    )
    assert int(m.group(4)) == sum(contado.values())


def test_paridade_md_repete_as_mesmas_contagens():
    texto = PARIDADE.read_text(encoding="utf-8")
    contado: Counter = Counter()
    for categoria, _arcade, _nosso, estado in _linhas():
        contado[(categoria.split(" (")[0], estado)] += 1
    for categoria in {c.split(" (")[0] for c, _a, _n, _e in _linhas()}:
        real = tuple(contado[(categoria, e)] for e in ("feito", "parcial", "fora"))
        alvo = f"parcial ({real[0]} feito · {real[1]} parcial · {real[2]} fora)"
        assert alvo in texto, f"docs/PARIDADE.md não traz a contagem de {categoria}: esperado {alvo}"
    total = Counter(estado for _c, _a, _n, estado in _linhas())
    assert (
        f"{total['feito']} feito · {total['parcial']} parcial · {total['fora']} fora de {sum(total.values())}"
        in texto
    )


def test_nenhuma_linha_feito_declara_diferenca_na_propria_observacao():
    """A regra que o adversário aplicou à mão: se a observação da linha escreve uma diferença contra o
    Arcade, a linha não é `feito`. Palavras que denunciam diferença na observação."""
    denuncia = re.compile(r"\b(o Arcade|no Arcade|não|nunca|sem|só|apenas|em vez)\b", re.I)
    ruins = [
        f"{arcade} → {nosso}"
        for categoria, arcade, nosso, estado in _linhas()
        if estado == "feito" and denuncia.search(_observacao(arcade, categoria))
    ]
    assert not ruins, f"linha `feito` cuja observação já declara diferença: {ruins}"


def _observacao(arcade: str, categoria: str) -> str:
    atual = ""
    for linha in _secao_10().splitlines():
        if linha.startswith("### "):
            atual = linha[4:].strip()
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) >= 4 and campos[2] in ESTADOS and campos[0] == arcade and atual == categoria:
            return campos[3]
    return ""
