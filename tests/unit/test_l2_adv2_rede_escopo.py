"""Adversário de linha L2 (parte 2), item `L2-11-c-rota-matriz-isocrona` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Este é o item mais inflado dos 30 sob ataque nesta rodada. O portão (LITERAL) exige, entre outras
cláusulas: matriz 1.000×1.000 em tempo medido; isócrona com ≥95% de acerto contra 200 pontos
amostrados; "pgRouting instalado (`SELECT pgr_version()`) e `drivingDistance` ... confere com
Dijkstra independente (networkx) em 20 origens"; e "QGIS/JS consomem o NAServer" (Esri-compatível). A
hipótese promete ainda perfis carro/bicicleta/pé, `/mais-proximo` e `/ajuste-de-trajeto` (map
matching).

O próprio handoff do turno que fechou o item (`laco/handoffs/T3/L2-11-c-rota.md`) já avisa, na
abertura: "pgRouting, `/mais-proximo`, `/ajuste-de-trajeto`, perfis pé/bicicleta, NAServer
Esri-compatível, UI no mapa e os testes de escala do portão completo (1.000×1.000, 200 pontos
amostrados) FICAM PARA A CONTINUAÇÃO DO ITEM." E a "última nota do ledger" deste item, no brief do
gerente, é literalmente vazia (`—`) — nenhuma medida foi resumida porque não havia o que resumir.

Conferido em código nesta rodada: `app/rede/rotas.py` só tem `perfil: Literal["carro"]` (nenhum
outro valor é sequer aceito pelo Pydantic); nenhum módulo do repositório contém `pgr_version`,
`pgr_drivingDistance` ou `pgr_alphaShape`; nenhum arquivo contém `NAServer`, `solveServiceArea` ou
`solveClosestFacility`; não existem rotas `/mais-proximo` nem `/ajuste-de-trajeto` (ou `/match`) em
`app/rede/`. Cinco cláusulas/promessas distintas do mesmo item, zero delas presente — não é uma
lacuna pontual, é o item inteiro reduzido a "OSRM carro sobre um recorte de 1,6 MB de Guarulhos com
rota/matriz/isócrona básicos", marcado ENTREGUE do mesmo jeito que os itens que de fato cobrem o
próprio portão.

ATUALIZAÇÃO 18/09/2026 (construção wt/l211croc2be): as cinco lacunas foram fechadas — os três perfis
são aceitos (Literal["carro","bicicleta","pe"], um grafo OSRM por perfil), `app/rede/pgr.py` usa
pgr_version/pgr_drivingDistance/pgr_alphaShape sobre a rede demo `plat.rota_pgr_demo`,
`app/rede/naserver.py` serve NAServer Route/ServiceArea/ClosestFacility/ODCostMatrix, e existem
/api/mais-proximo e /api/ajuste-de-trajeto. O xfail(strict) virou XPASS e por isso o marcador saiu:
este arquivo passa a ser o teste PERMANENTE do escopo, não mais a prova da lacuna."""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app"


def _grep_app(padrao: str) -> bool:
    saida = subprocess.run(
        ["grep", "-rlE", padrao, str(APP)], capture_output=True, text=True
    )
    return bool(saida.stdout.strip())


def test_pgrouting_naserver_perfis_e_rotas_auxiliares_existem():
    from app.rede import rotas as rede_rotas

    perfis_aceitos = set()
    for nome in ("PedidoRota", "PedidoMatriz", "PedidoIsocrona"):
        modelo = getattr(rede_rotas, nome, None)
        if modelo is not None:
            campo = modelo.model_fields.get("perfil")
            if campo is not None:
                literais = getattr(campo.annotation, "__args__", ())
                perfis_aceitos.update(literais)

    tem_pgrouting = _grep_app("pgr_version|pgr_drivingDistance|pgr_alphaShape")
    tem_naserver = _grep_app("NAServer|solveServiceArea|solveClosestFacility")
    caminhos_rotas = {r.path for r in rede_rotas.router.routes}
    tem_mais_proximo = any("mais-proximo" in p or "mais_proximo" in p for p in caminhos_rotas)
    tem_ajuste_trajeto = any("ajuste-de-trajeto" in p or "match" in p for p in caminhos_rotas)

    assert {"carro", "bicicleta", "pe"}.issubset(perfis_aceitos), perfis_aceitos
    assert tem_pgrouting, "nenhuma chamada pgr_* encontrada em app/"
    assert tem_naserver, "nenhuma rota NAServer/solveServiceArea/solveClosestFacility encontrada"
    assert tem_mais_proximo, caminhos_rotas
    assert tem_ajuste_trajeto, caminhos_rotas
