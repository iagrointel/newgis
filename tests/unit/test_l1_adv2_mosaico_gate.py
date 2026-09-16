"""Adversário de linha L1 imagens (parte 2, turno 9) — itens `L1-07-mosaico-por-colecao-e-pegadas`
(ENTREGUE, commit b22329356) e `L1-08-regras-de-mosaico-e-selecao-de-pixel` (ENTREGUE, commit
1289cd598). Achados:

1. `L1-08`: a hipótese do item lista 5 regras de composição, entre elas "'mais recente sem nuvem'
   (ordem por data desc + máscara de nuvem por pixel do L1-09 antes de `first`)". O portão pede
   explicitamente essa regra testada "sobre 6 cenas reais [...] nunca devolve pixel marcado como
   nuvem no SCL (teste em 100 pixels)". `app/imagens/mosaico.py::SELECOES_PIXEL` só tem
   `{first, last, lowest, highest, mean, median, stdev}` — nenhuma variante ciente de nuvem/SCL
   existe no código, e não há um único teste com a palavra SCL em todo `tests/api/imagens/`.

2. `L1-08`: refutação exigida pelo próprio item — "cenas em CRS diferentes (UTM 22S e 23S) e confere
   alinhamento na borda de zona (≤ 1 px)" — não tem teste correspondente: o único arquivo com CRS
   misto (`tests/dados/raster/mosaico_crs_diferente.zip`) é usado por `test_formatos_entrada.py`
   para provar que a INGESTÃO em lote RECUSA um zip com CRS misto (item L1-01-f, cláusula 4) — o
   oposto do que a refutação de L1-08 pede (compor um mosaico com itens de CRS nativos diferentes e
   medir o desalinhamento na costura).

3. `L1-08`: `docs/PARIDADE.md` (datado 2026-09-10, mesmo dia do commit de fechamento) ainda registra
   a linha de paridade "regra de seleção de pixel" como "os outros 6 são o item irmão L1-08, não
   construído" / "fora (L1-08)" — documentação não atualizada depois do item ter sido fechado como
   ENTREGUE no mesmo dia; o portão pede "`docs/PARIDADE.md` com os 7 métodos Esri" (cada um marcado
   FEITO/FORA individualmente, com Seamline/Closest to Viewpoint como as únicas exceções) — a linha
   atual não cumpre isso.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_mosaico_gate.py -q -rxX`."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-08 CAI: app/imagens/mosaico.py::SELECOES_PIXEL nao tem nenhuma regra ciente de nuvem/SCL "
        "('mais recente sem nuvem' e uma das 5 regras da propria hipotese do item); nenhum teste em "
        "tests/api/imagens/ menciona SCL."
    ),
)
def test_regra_mais_recente_sem_nuvem_existe():
    from app.imagens import mosaico

    nomes_em_portugues = {"sem_nuvem", "mais_recente_sem_nuvem", "sem_nuvem_scl"}
    assert nomes_em_portugues & set(mosaico.SELECOES_PIXEL), (
        f"SELECOES_PIXEL = {sorted(mosaico.SELECOES_PIXEL)} nao tem variante ciente de nuvem/SCL"
    )

    achados = []
    for caminho in (ROOT / "tests" / "api" / "imagens").glob("*.py"):
        if "SCL" in caminho.read_text(encoding="utf-8", errors="ignore"):
            achados.append(caminho.name)
    assert achados, "nenhum teste em tests/api/imagens/ menciona SCL (mascara de nuvem por pixel)"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-08 CAI: refutacao exigida pelo item (cenas de CRS nativos diferentes, UTM 22S e 23S, num "
        "MESMO mosaico, alinhamento na costura <= 1px) nao tem teste. O unico arquivo com CRS misto "
        "(mosaico_crs_diferente.zip) e usado so para provar que a INGESTAO em lote RECUSA CRS misto "
        "(item L1-01-f), nao para medir alinhamento de mosaico composto."
    ),
)
def test_mosaico_com_crs_nativos_diferentes_tem_teste_de_alinhamento():
    alvo = ROOT / "tests" / "api" / "imagens" / "test_mosaico.py"
    apoio = ROOT / "tests" / "api" / "imagens" / "apoio_mosaico.py"
    texto = alvo.read_text(encoding="utf-8") + apoio.read_text(encoding="utf-8")
    marcas_utm = ("32722", "32723", "31982", "31983", "22S", "23S")
    assert any(m in texto for m in marcas_utm), (
        "nenhuma referência a duas zonas UTM distintas em test_mosaico.py/apoio_mosaico.py — a "
        "refutação de CRS misto num mosaico composto nunca foi tentada em código"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-08 CAI (documentacao): docs/PARIDADE.md:688 ainda diz que as regras de mosaicRule (exceto "
        "'first') sao 'o item irmao L1-08, nao construido' / 'fora (L1-08)', mas o proprio ledger deste "
        "brief marca L1-08 ENTREGUE (commit 1289cd598) no MESMO dia (2026-09-10) que a data registrada "
        "nesta linha do documento. O portao pede a tabela com os 7 metodos Esri marcados individualmente."
    ),
)
def test_paridade_md_reflete_l1_08_entregue():
    texto = (ROOT / "docs" / "PARIDADE.md").read_text(encoding="utf-8")
    linha = next(
        linha
        for linha in texto.splitlines()
        if "regra de seleção de pixel" in linha.lower() or "regra de selecao de pixel" in linha.lower()
    )
    assert "não construído" not in linha and "nao construido" not in linha, linha
    assert "fora (L1-08)" not in linha, linha
