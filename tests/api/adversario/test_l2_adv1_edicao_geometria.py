"""Adversário de linha L2 (parte 1), item `L2-03-b-ferramentas-geometria`.

Achado: `POST /api/camadas/{id}/feicoes/unir` e `POST /api/camadas/{id}/feicoes/dividir` (as duas operações
centrais do portão — "unir 3 feições = ST_Union direto", "dividir polígono em 2 partes: soma das áreas =
área original") devolvem 404 no `wt/uniao` de hoje, embora:

1. o frontend chame exatamente essas URLs (`web/js/mapa/edicao.js::_dividirNoPonto`/`unirSelecionadas`);
2. o `docs/openapi.json` COMMITADO documente as duas rotas;
3. `app/edicao/combinar.py` (funções `unir`/`dividir`) exista, importe limpo e tenha lógica real de
   `ST_Union`/`ST_Split`;
4. exista até um teste oficial e específico para elas (`tests/api/test_edicao_dividir_unir.py`) — que
   FALHA (visto ao vivo nesta rodada: `assert 404 == 200`, `assert 404 == 422`, `assert 404 == 409` em toda
   a suíte, porque nenhum handler responde no caminho).

Causa raiz (achada por `git log`/`git show`, não suposição): o commit `9b347a2c8` (07/09, item
`L2-03-edicao`) acrescentou 8 rotas em `app/edicao/rotas.py` — `GET .../feicoes/{globalid}`, histórico,
restaurar, 4 rotas de anexo, `unir` e `dividir`. Alguma fusão posterior (não identificada por sha exato,
mas confirmada pelo próprio changelog do commit `087ab16f0`, 16/09: "a rota HTTP nunca foi restaurada
depois que a fusão perdeu o commit original") **perdeu** essas rotas de `app/edicao/rotas.py` — o arquivo
vivo em `wt/uniao` hoje só tem `/api/camadas/{id}/edicoes` (L2-03-a) e `/api/camadas/{id}/lote` (L2-03-f).
`087ab16f0` restaurou SÓ a rota de `/lote` (o achado daquele turno era especificamente L2-03-f) — as 8
rotas de `9b347a2c8` (que cobrem L2-03-b inteiro, mais L2-03-d e L2-03-e, já refutados por outro
adversário como "artefato ausente em master") continuam perdidas. Mesmo arquivo, mesma fusão, mesmo
padrão: quando um item vizinho tromba com a perda e conserta só a PRÓPRIA rota, os outros itens que
perderam rota no MESMO evento continuam quebrados em silêncio até alguém rodar o teste deles.

Reprodução mínima ao vivo (rodada nesta sessão, trilha `uniao`):
  set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
  bash /home/dev/plataforma/laco/roda_teste.sh tests/api/test_edicao_dividir_unir.py -q -rxX
  -> toda a suíte falha com `assert 404 == <200|409|422>` em `.../feicoes/unir` e `.../feicoes/dividir`.
"""

from __future__ import annotations

import pytest

from tests.api.test_edicao_transacional import _admin_usuario_id, fabrica  # noqa: F401
from tests.api.test_rls import ids_por_slug


def _linha(coords):
    return {"type": "LineString", "coordinates": coords}


@pytest.fixture
def camada_linha_adv(fabrica, conexao_plat_app):  # noqa: F811
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, _dados = fabrica.criar(
        "demo", ids["demo"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="LineString",
    )
    return item_id


def _adicionar(sessao, camada_id, geometria, nome="x"):
    r = sessao.post(
        f"/api/camadas/{camada_id}/edicoes",
        json={"adicionar": [{"atributos": {"nome": nome}, "geometria": geometria}], "atualizar": [], "apagar": []},
    )
    assert r.status_code == 200, r.text
    return r.json()["adicionar"][0]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-03-b-ferramentas-geometria CAI: POST /api/camadas/{id}/feicoes/unir devolve 404 (rota ausente "
        "de app/edicao/rotas.py em wt/uniao — perdida numa fusão depois do commit 9b347a2c8; ver docstring "
        "do módulo e tests/api/test_edicao_dividir_unir.py, que falha inteiro pelo mesmo motivo). O código de "
        "app/edicao/combinar.py::unir existe e nunca é chamado por nenhum router."
    ),
)
def test_l2_03b_unir_duas_linhas_conectadas(sessao_a, camada_linha_adv):
    a = _adicionar(sessao_a, camada_linha_adv, _linha([[-46.60, -23.50], [-46.55, -23.50]]), nome="trecho-a")
    b = _adicionar(sessao_a, camada_linha_adv, _linha([[-46.55, -23.50], [-46.50, -23.50]]), nome="trecho-b")
    r = sessao_a.post(
        f"/api/camadas/{camada_linha_adv}/feicoes/unir",
        json={"ids": [a["id"], b["id"]], "versoes": {a["id"]: a["versao"], b["id"]: b["versao"]}},
    )
    assert r.status_code == 200, r.text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-03-b-ferramentas-geometria CAI: POST /api/camadas/{id}/feicoes/dividir devolve 404 pelo mesmo "
        "motivo de test_l2_03b_unir_duas_linhas_conectadas (rota perdida de app/edicao/rotas.py). O portão "
        "exige explicitamente 'dividir linha/polígono ... soma das áreas = área original' e a operação é "
        "inalcançável por HTTP hoje."
    ),
)
def test_l2_03b_dividir_linha_no_meio(sessao_a, camada_linha_adv):
    a = _adicionar(sessao_a, camada_linha_adv, _linha([[-46.60, -23.50], [-46.50, -23.50]]), nome="inteira")
    r = sessao_a.post(
        f"/api/camadas/{camada_linha_adv}/feicoes/dividir",
        json={"id": a["id"], "versao": a["versao"], "ponto": [-46.55, -23.50]},
    )
    assert r.status_code == 200, r.text
