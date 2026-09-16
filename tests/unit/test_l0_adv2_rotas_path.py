"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-04-k-rota-formatos-encoberta`. Laudo
completo em `laco/handoffs/T9/linha-L0-laudo-adversario-2.md`. Puro (sem banco): a promessa quebrada é do
ALGORITMO da varredura, reproduzida com uma mini-app FastAPI descartável."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    strict=True,
    reason="L0-04-k: _cobre() (tests/unit/test_rotas_sombreamento.py) só compara caminhos com o MESMO número "
    "de segmentos. O convertor `path` do Starlette usa regex '.*' e casa qualquer número de segmentos "
    "(inclusive barra) — logo uma rota fixa de MAIS segmentos declarada depois de uma {x:path} no mesmo "
    "prefixo fica inalcançável e a varredura não vê o par (segmentos diferentes -> len(a)!=len(b) -> "
    "retorna False antes de olhar o convertor). É a MESMA classe de bug que motivou o item (rota fixa "
    "engolida por parametrizada), agora invisível para a ferramenta que deveria pegá-la sozinha. O app real "
    "já tem 5 rotas com {x:path} hoje (app/acervo/rotas_frescor.py, app/modelos3d/rotas.py, "
    "app/catalogo/rotas_compartilhamento.py, app/notebooks/rotas.py x2); nenhuma colide agora por cuidado "
    "manual na ordem de include_router (ver comentário em app/main.py linha 310), não por garantia da "
    "varredura — o cuidado manual é exatamente o que este item deveria ter tornado desnecessário.",
)
def test_varredura_de_sombreamento_detecta_parametro_path_multisegmento():
    """Reprodução mínima com o padrão real: uma rota `{a:path}` de 4 segmentos declarada ANTES de uma rota
    fixa de 5 segmentos no mesmo prefixo. Starlette engole a segunda; `_cobre`, importado sem alteração do
    próprio item, não vê o par."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tests.unit.test_rotas_sombreamento import _cobre, achatar_rotas

    app = FastAPI()

    @app.get("/api/x/{a:path}/fim")
    def rota_generica(a: str):
        return {"rota": "generica"}

    @app.get("/api/x/{b}/{c}/fim")
    def rota_fixa_dois_segmentos(b: str, c: str):
        return {"rota": "fixa_dois_segmentos", "b": b, "c": c}

    rotas = [(pos, caminho, metodos) for pos, (caminho, metodos) in enumerate(achatar_rotas(app.routes))]
    achados = []
    for pos_antes, caminho_antes, metodos_antes in rotas:
        for pos_depois, caminho_depois, metodos_depois in rotas:
            if pos_depois <= pos_antes or not (metodos_antes & metodos_depois):
                continue
            if _cobre(caminho_antes, caminho_depois):
                achados.append((caminho_antes, caminho_depois))

    cliente = TestClient(app)
    resposta = cliente.get("/api/x/foo/bar/fim")

    # a promessa do portão: a rota fixa responde pelo que ela é, e a varredura teria acusado o par ANTES
    # disso chegar a produção. Nenhuma das duas é verdade hoje.
    assert achados, "a varredura deveria ter achado o par {a:path} x {b}/{c} (segmentos diferentes) e não achou"
    assert resposta.json()["rota"] == "fixa_dois_segmentos", (
        f"'/api/x/{{b}}/{{c}}/fim' foi engolida por '/api/x/{{a:path}}/fim': resposta real = {resposta.json()}"
    )
