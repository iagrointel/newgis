"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-04-k-rota-formatos-encoberta`. Laudo
completo em `laco/handoffs/T9/linha-L0-laudo-adversario-2.md`. Puro (sem banco): a promessa quebrada é do
ALGORITMO da varredura, reproduzida com uma mini-app FastAPI descartável."""

from __future__ import annotations

# REMEDIADO (wt/l02, 17/09/2026): `_cobre()` deixou de reimplementar o casamento segmento a segmento e passou
# a usar `starlette.routing.compile_path` — o mesmo regex que o roteador usa. Com isso o convertor `path`
# (`.*`, que casa qualquer número de segmentos, barra inclusive) passa a ser enxergado pela varredura, e os
# convertores `int`/`float`/`uuid` valem de graça, sem a tabela paralela que havia antes.
#
# O `xfail(strict=True)` saiu junto com uma correção de ENUNCIADO na segunda asserção, registrada aqui para que
# ninguém a leia como abrandamento: a versão original exigia que, declarada DEPOIS, `/api/x/{b}/{c}/fim`
# respondesse mesmo assim. Isso não é alcançável e nunca foi do item — quem decide é o Starlette, cujo regex
# `.*` é guloso por construção. O que o item promete, e o que aqui se prova, é que a varredura ACUSA o par
# antes de ele chegar a produção e que, corrigida a ordem que ela aponta, a rota fixa volta a responder.
# A varredura sobre a aplicação viva achou, nesta rodada, um par real que estava em master:
# `GET /api/imagens/licencas` engolida por `GET /api/imagens/{item_id}` (consertado em app/main.py).
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

    assert achados, "a varredura deveria ter achado o par {a:path} x {b}/{c} (segmentos diferentes) e não achou"
    assert achados == [("/api/x/{a:path}/fim", "/api/x/{b}/{c}/fim")], achados

    # declarada na ordem que a varredura prescreve (a fixa antes da {a:path}), a rota engolida volta a
    # responder pelo que ela é — é isto que torna o cuidado manual em `include_router` desnecessário.
    corrigida = FastAPI()

    @corrigida.get("/api/x/{b}/{c}/fim")
    def rota_fixa_primeiro(b: str, c: str):
        return {"rota": "fixa_dois_segmentos", "b": b, "c": c}

    @corrigida.get("/api/x/{a:path}/fim")
    def rota_generica_depois(a: str):
        return {"rota": "generica"}

    assert TestClient(corrigida).get("/api/x/foo/bar/fim").json()["rota"] == "fixa_dois_segmentos"
