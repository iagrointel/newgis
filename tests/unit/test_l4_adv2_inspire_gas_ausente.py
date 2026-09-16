"""Adversário da linha L4 rede de utilidades (rodada 2) — item L4-01-h-alinhamento-inspire-gnm.

O portão (LITERAL) pede: "documento de mapeamento campo-a-campo pacote-de-ativos -> classes INSPIRE
GNM ... para os domínios já cobertos (elétrica, água, gás); exportador que gera GML conforme o esquema
oficial INSPIRE ... para 1 rede de teste; validado contra o schema oficial (XSD) sem erro" — os TRÊS
domínios são nomeados de propósito (o pacote gas-br já existe desde L4-05-e, então "já cobertos"
inclui gás).

O que existe em `app/rede_utilidades/inspire_gnm.py` (`MAPEAMENTO_GNM`) e em
`tests/unit/test_inspire_gnm.py`: só "eletrica" e "agua". Não há entrada "gas" no dicionário de
mapeamento, nenhuma `rede_teste_gas()`, e nenhum teste que exporte GML de uma rede de gás. A própria
última nota do ledger do item admite isso em texto ("gás fica de fora por falta de pacote-fonte
(L4-01-a)") — mas essa desculpa não se sustenta mais: o pacote `gas-br` existe e está registrado como
ENTREGUE desde o item L4-05-e-gas-e-esgoto (commit e1844305), que é anterior a este item na mesma
linha. O item L4-01-h está registrado como ENTREGUE, sem qualificação, cobrindo só 2 dos 3 domínios que
o próprio portão nomeia."""

import json
from pathlib import Path

import pytest

from app.rede_utilidades import inspire_gnm

ROOT = Path(__file__).resolve().parents[2]
PACOTE_GAS = ROOT / "app" / "rede_utilidades" / "pacotes" / "gas-br.json"


def test_pacote_fonte_de_gas_ja_existe_quando_o_item_inspire_foi_fechado():
    """Confirma que a desculpa do ledger ('gás fica de fora por falta de pacote-fonte') não é mais
    verdadeira: o arquivo do pacote gas-br já existe no repositório."""
    assert PACOTE_GAS.exists(), "pré-condição do achado mudou: gas-br.json não existe mais"
    doc = json.loads(PACOTE_GAS.read_text(encoding="utf-8"))
    assert doc.get("tipos"), "gas-br.json existe mas está vazio — a desculpa do ledger seria válida"


@pytest.mark.xfail(strict=True, reason=(
    "achado adversário L4 rodada 2 (item L4-01-h-alinhamento-inspire-gnm): o portão nomeia os 3 "
    "dominios 'ja cobertos' (eletrica, agua, gas) mas app/rede_utilidades/inspire_gnm.py.MAPEAMENTO_GNM só "
    "tem eletrica e agua; gas-br.json ja existe (item L4-05-e, anterior nesta mesma linha) e nao foi "
    "usado para fechar a lacuna que o proprio ledger do item admite"
))
def test_mapeamento_inspire_gnm_cobre_o_dominio_gas():
    assert "gas" in inspire_gnm.MAPEAMENTO_GNM, (
        f"domínios mapeados hoje: {sorted(inspire_gnm.MAPEAMENTO_GNM)}; o portão pede elétrica, água E gás"
    )
