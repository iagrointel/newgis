"""Decisão do item L0-12 (docs/CONTRATO_API.md seção "Versionamento", ADR 0001 seção 12): a API NÃO leva
versão na URL (nunca `/api/v1/...`); mudança incompatível vira rota nova com outro nome, e o `docs/openapi.json`
comitado é o contrato — não um número de versão. Este teste é o que torna a decisão viva: se algum dia uma
trilha acrescentar um prefixo `/v<n>/` a uma rota (o padrão mais comum de versionamento de URL, e o oposto do
que este documento decidiu), o teste falha aqui, no código, não só na prosa do documento."""

import json
import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SEGMENTO_DE_VERSAO = re.compile(r"(^|/)v\d+(/|$)", re.IGNORECASE)


def _rotas_da_aplicacao_viva() -> list[str]:
    return [r.path for r in app.routes if hasattr(r, "path")]


def test_nenhuma_rota_viva_leva_segmento_de_versao_na_url():
    rotas = _rotas_da_aplicacao_viva()
    assert rotas, "app.routes vazio — o teste não provaria nada"
    com_versao = [r for r in rotas if SEGMENTO_DE_VERSAO.search(r)]
    assert not com_versao, f"rota com versão na URL, contra a decisão de docs/CONTRATO_API.md: {com_versao}"


def test_openapi_comitado_tambem_nao_leva_versao_na_url():
    """O mesmo teste contra o contrato comitado (docs/openapi.json): se a aplicação viva e o arquivo comitado
    divergirem aqui, `make openapi` está pendente — outro jeito de o documento vivo não bater com o código."""
    spec = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    caminhos = list(spec["paths"])
    com_versao = [c for c in caminhos if SEGMENTO_DE_VERSAO.search(c)]
    assert not com_versao, f"rota versionada em docs/openapi.json: {com_versao}"
