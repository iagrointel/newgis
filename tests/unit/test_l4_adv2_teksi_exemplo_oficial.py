"""Adversário da linha L4 rede de utilidades (rodada 2) — item L4-05-e-gas-e-esgoto.

O portão (LITERAL) exige: "importação do esquema TEKSI (GeoPackage de exemplo do projeto) mapeada".
"GeoPackage de exemplo do projeto" só pode se referir ao arquivo de amostra publicado pelo próprio
projeto TEKSI (https://teksi.github.io/wastewater/) — não a um arquivo que a própria casa fabrica para
imitar o esquema que ela mesma entendeu.

O que existe hoje: `tests/dados/gerar_esgoto.py::escrever_geopackage` monta um `.gpkg` SINTÉTICO do
zero (SQLite + WKB escritos à mão, ver `app/rede_utilidades/teksi.py`), e é esse arquivo sintético —
nunca um arquivo do projeto TEKSI — que `tests/api/test_rede_gas_esgoto.py::test_importa_geopackage_teksi_com_as_200_feicoes`
usa. Não há, em lugar nenhum do repositório, um `.gpkg` (nem um link/hash para um) que venha do
projeto TEKSI de verdade. A própria última nota do ledger do item já admite isso em texto ("TEKSI e
paridade ficam parciais (colunas lidas do datamodel, nao de dado real)"), mas o item está registrado
como ENTREGUE, não parcial, e o portão não carrega a ressalva.

Isso não é "o importador está errado" (o leitor de GeoPackage — envelope binário + WKB — é código real
e testado, ver app/rede_utilidades/teksi.py); é "a cláusula específica do portão sobre a AMOSTRA OFICIAL
nunca foi tentada", no mesmo padrão do achado #4 da rodada 2 do adversário de L2 (cláusula do portão
nomeada, sem teste correspondente porque a coisa nunca foi buscada)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _arquivos_gpkg() -> list[Path]:
    return list(ROOT.rglob("*.gpkg"))


@pytest.mark.xfail(strict=True, reason=(
    "achado adversário L4 rodada 2 (item L4-05-e-gas-e-esgoto): o portão pede a importação mapeada "
    "contra o 'GeoPackage de exemplo do projeto' TEKSI; o único .gpkg usado nos testes "
    "(tests/dados/gerar_esgoto.py) é fabricado pela própria casa para imitar o datamodel, nunca um "
    "arquivo de amostra real do projeto TEKSI — self-admitido no ledger ('colunas lidas do datamodel, "
    "nao de dado real') mas o item está ENTREGUE, sem essa ressalva no portão"
))
def test_existe_geopackage_de_exemplo_real_do_projeto_teksi_no_repositorio():
    candidatos = [p for p in _arquivos_gpkg() if "sintetic" not in p.name.lower()]
    # o único .gpkg do repo hoje é o de demonstração genérica de outra frente (dados_demo/); nenhum vem
    # do projeto TEKSI, e o importador nunca correu contra um arquivo de origem externa ao próprio teste
    teksi_oficial = [p for p in candidatos if "teksi" in p.name.lower() or "wastewater" in p.name.lower()]
    assert teksi_oficial, (
        f"nenhum GeoPackage de exemplo do projeto TEKSI encontrado no repositório (candidatos vistos: "
        f"{[str(p.relative_to(ROOT)) for p in candidatos]}); a importação só foi provada contra um "
        f"arquivo sintético que a própria casa gerou"
    )
