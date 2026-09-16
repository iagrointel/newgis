"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achados sobre `L0-13-dado-demonstracao`. Laudo completo
em `laco/handoffs/T9/linha-L0-laudo-adversario-2.md`.

Dois achados independentes, ambos determinísticos (não dependem do estado da trilha):

1. `tests/api/test_dado_demo.py::_nomes_proibidos()` extrai a lista de nomes proibidos com
   `re.search(r"\\(([^)]*)\\)", padrao).group(1)` — o PRIMEIRO grupo entre parênteses do arquivo
   `laco/nomes_proibidos.regex`. Esse arquivo hoje começa com a flag inline `(?i)` (case-insensitive) antes
   do grupo de nomes: `(?i)\\b(cbre|fgr|certel|...)\\b`. O primeiro parêntese do arquivo é o da PRÓPRIA flag,
   então `_nomes_proibidos()` devolve `["?i"]` em vez da lista real de 20+ nomes de cliente/parceiro. A
   cláusula 3 do portão ("nenhum nome de cliente, parceiro ou piloto ... grep = 0") está, agora, testando a
   string literal "?i" — não testando NENHUM nome de cliente real. `tests/api/test_dado_demo.py::test_nenhum_nome_de_cliente_parceiro_ou_piloto`
   já falha hoje (por coincidência: a sequência de bytes "?i" aparece dentro de dois arquivos binários do
   conjunto — `demonstracao_3_camadas.gpkg` e `municipios_ap_rr.zip`), mas por um motivo que não tem nada a
   ver com o que o portão promete verificar: mesmo corrigindo esse falso positivo, o teste continuaria sem
   testar "cbre", "novaterra", "fgr" etc.

2. `docs/DADO_DEMO.md` (o arquivo que a cláusula 2 do portão exige, "cada arquivo tem linha ... com fonte,
   URL, licença e data de acesso") foi TOMADO por outro item (`L2-01-e-mapas-base`, commit `35d00a434`) e hoje
   só documenta a galeria de mapas base (OSM/Sentinel) — zero menção a qualquer um dos arquivos reais do
   conjunto de demonstração (`municipios_ac.zip`, `rodovias_federais_ac.geojson`,
   `estacoes_inmet_norte.csv`, `demonstracao_3_camadas.gpkg`, `planta_exemplo.dxf`, etc., 11 arquivos em
   `dados_demo/catalogo.json`). `tests/api/test_dado_demo.py::test_cada_arquivo_tem_fonte_endereco_licenca_e_data_de_acesso_no_documento`
   já falha hoje com a lista completa dos 11 arquivos "sem bloco no documento"."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.xfail(
    strict=True,
    reason="L0-13: _nomes_proibidos() (tests/api/test_dado_demo.py) extrai o PRIMEIRO grupo entre "
    "parênteses de laco/nomes_proibidos.regex, que hoje começa com a flag inline '(?i)' — o grupo "
    "extraído é '?i', não a lista real de nomes de cliente/parceiro. A cláusula 'nenhum nome de cliente, "
    "parceiro ou piloto' não testa nenhum nome de verdade desde que a flag foi acrescentada ao arquivo.",
)
def test_nomes_proibidos_extraidos_pelo_teste_incluem_nomes_de_cliente_reais():
    import sys

    caminho = str(ROOT / "tests" / "api")
    sys.path.insert(0, caminho)
    try:
        from test_dado_demo import _nomes_proibidos  # type: ignore
    finally:
        sys.path.remove(caminho)

    nomes = _nomes_proibidos()
    esperados = {"cbre", "fgr", "novaterra", "sicredi"}
    assert esperados & set(nomes), (
        f"_nomes_proibidos() devolveu {nomes!r} — nenhum nome de cliente real está sendo verificado"
    )


@pytest.mark.xfail(
    strict=True,
    reason="L0-13: docs/DADO_DEMO.md foi tomado por L2-01-e-mapas-base (commit 35d00a434) e hoje só "
    "documenta a galeria de mapas base (OSM/Sentinel); zero linha sobre qualquer arquivo real do conjunto "
    "de demonstração do item (dados_demo/catalogo.json). A cláusula 'cada arquivo tem linha no documento' "
    "está sem cumprimento para os 11 arquivos reais.",
)
def test_docs_dado_demo_documenta_os_arquivos_reais_do_conjunto():
    catalogo = json.loads((ROOT / "dados_demo" / "catalogo.json").read_text(encoding="utf-8"))
    doc = (ROOT / "docs" / "DADO_DEMO.md").read_text(encoding="utf-8")
    arquivos = sorted({it["arquivo"] for it in catalogo["itens"]})
    assert arquivos, "catálogo de demonstração vazio — nada para conferir"
    sem_bloco = [a for a in arquivos if not re.search(re.escape(a), doc)]
    assert not sem_bloco, f"arquivos do conjunto de demonstração sem bloco em docs/DADO_DEMO.md: {sem_bloco}"
