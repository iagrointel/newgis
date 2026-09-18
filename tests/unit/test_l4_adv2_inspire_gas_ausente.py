"""Adversário da linha L4 rede de utilidades (rodada 2) — item L4-01-h-alinhamento-inspire-gnm.

O portão (LITERAL) pede: "documento de mapeamento campo-a-campo pacote-de-ativos -> classes INSPIRE
GNM ... para os domínios já cobertos (elétrica, água, gás); exportador que gera GML conforme o esquema
oficial INSPIRE ... para 1 rede de teste; validado contra o schema oficial (XSD) sem erro" — os TRÊS
domínios são nomeados de propósito (o pacote gas-br já existe desde L4-05-e, então "já cobertos"
inclui gás).

O que existia em `app/rede_utilidades/inspire_gnm.py` (`MAPEAMENTO_GNM`) e em
`tests/unit/test_inspire_gnm.py`: só "eletrica" e "agua". Não havia entrada "gas" no dicionário de
mapeamento, nenhuma `rede_teste_gas()`, e nenhum teste que exporte GML de uma rede de gás.

RESOLVIDO nesta rodada (L4-01-h, tentativa 3): o mapeamento ganhou o domínio "gas" (nó ->
us-net-common:Appurtenance, tubulacao_de_gas -> UtilityLink), o exportador ganhou
`rede_teste_gas_br()` com grupos reais do pacote gas-br, e `tests/unit/test_inspire_gnm.py` valida
o GML de gás contra o XSD oficial us-net-common. Este arquivo ficou como guarda de regressão do
achado (o xfail foi removido porque a lacuna fechou)."""

import json
from pathlib import Path

from app.rede_utilidades import inspire_gnm

ROOT = Path(__file__).resolve().parents[2]
PACOTE_GAS = ROOT / "app" / "rede_utilidades" / "pacotes" / "gas-br.json"


def test_pacote_fonte_de_gas_ja_existe_quando_o_item_inspire_foi_fechado():
    """Confirma que a desculpa do ledger ('gás fica de fora por falta de pacote-fonte') não é mais
    verdadeira: o arquivo do pacote gas-br já existe no repositório."""
    assert PACOTE_GAS.exists(), "pré-condição do achado mudou: gas-br.json não existe mais"
    doc = json.loads(PACOTE_GAS.read_text(encoding="utf-8"))
    assert doc.get("tipos"), "gas-br.json existe mas está vazio — a desculpa do ledger seria válida"


def test_mapeamento_inspire_gnm_cobre_o_dominio_gas():
    assert "gas" in inspire_gnm.MAPEAMENTO_GNM, (
        f"domínios mapeados hoje: {sorted(inspire_gnm.MAPEAMENTO_GNM)}; o portão pede elétrica, água E gás"
    )
