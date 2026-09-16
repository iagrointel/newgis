"""Adversário de linha L5 builder (parte 2) — item L5-31-construtor-de-camada-esquema.

Achado (hipótese transversal desta rodada: normalização de nome sem estado compartilhado entre as
MUDANÇAS do mesmo pedido): `app/catalogo/camada_esquema.py::_avaliar_mudanca` normaliza o nome de um campo
novo assim: `nome, motivo_nome = normalizar(m.novo_campo.nome, set())` — o segundo argumento é um `set()`
NOVO a cada chamada. `_plano()` chama `_avaliar_mudanca` uma vez por mudança da lista, então duas mudanças
`adicionar_campo` no MESMO `PlanoEntrada` nunca se veem: se os dois nomes de origem normalizam para o
MESMO identificador (ex.: "Área" e "área", os dois viram "area"), a checagem de "já existe uma coluna
chamada" só olha o banco (que ainda não tem NENHUM dos dois enquanto o plano só avalia) — as duas entram
como `aplicavel: true` com o MESMO `coluna_normalizada`.

Isso quebra as DUAS promessas do item ao mesmo tempo:
1. `POST /api/camadas/{id}/esquema/plano` ("o plano mostrado antes de aplicar") mente: diz que as duas
   mudanças são aplicáveis quando aplicar as duas é impossível.
2. `PUT /api/camadas/{id}/esquema` ("migração destrutiva... é recusada com mensagem", i.e. o item promete
   que o que não pode ser aplicado é recusado educadamente) na verdade estoura com
   `psycopg2.errors.DuplicateColumn: column "area" of relation "..." already exists` sem tratamento —
   500 cru, não um 422 nomeando o campo.

Reproduzido ao vivo nesta rodada (trilha `uniao`): a chamada teve de ser interrompida com Ctrl-C porque o
TestClient reencaminha a exceção do psycopg2 sem capturá-la — exatamente o "nunca 500" que o item promete
evitar (a refutação exigida do item fala de "nome reservado/acento" na CRIAÇÃO, já testada e aprovada; esta
é a MESMA função de normalização, na migração de esquema, sem o mesmo cuidado).

Este teste evita depender do 500 batendo through o TestClient (frágil de capturar em xfail): confere direto
que o PLANO reporta a colisão como aplicável duas vezes (já basta para provar que "o plano mostrado antes de
aplicar" está errado) e, com fixture separada, que a aplicação real do PUT quebra com erro de banco cru."""

import pytest
from psycopg2 import errors as pg_errors

from tests.api.catalogo.test_camada_esquema import FabricaCamada

ITEM = "L5-31-construtor-de-camada-esquema"


@pytest.fixture
def camada_a(sessao_a, env):
    f = FabricaCamada(sessao_a, env)
    yield f
    f.limpar()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-31: app/catalogo/camada_esquema.py::_avaliar_mudanca chama normalizar(nome, set()) com um "
        "set() novo por mudança — duas mudanças 'adicionar_campo' no mesmo plano cujos nomes normalizam "
        "para o mesmo identificador ('Área' e 'área' -> 'area') são as DUAS relatadas como aplicavel=true "
        "com o mesmo coluna_normalizada; o plano não avisa da colisão entre si mesmo"
    ),
)
def test_plano_de_esquema_nao_detecta_colisao_entre_duas_mudancas_do_mesmo_pedido(sessao_a, camada_a):
    r = camada_a.criar()
    assert r.status_code == 201, r.text
    item_id = r.json()["item_id"]

    corpo = {
        "mudancas": [
            {"tipo": "adicionar_campo", "novo_campo": {"nome": "Área", "tipo": "double precision"}},
            {"tipo": "adicionar_campo", "novo_campo": {"nome": "área", "tipo": "double precision"}},
        ]
    }
    r = sessao_a.post(f"/api/camadas/{item_id}/esquema/plano", json=corpo)
    assert r.status_code == 200, r.text
    plano = r.json()["plano"]
    assert len(plano) == 2
    nomes_normalizados = [p.get("coluna_normalizada") for p in plano]
    # portão do item: um plano correto não pode dizer que as DUAS mudanças são aplicáveis quando aplicar as
    # duas colide na mesma coluna nova — ou avisa da colisão, ou marca a segunda como não aplicável.
    if nomes_normalizados[0] == nomes_normalizados[1]:
        assert not (plano[0]["aplicavel"] and plano[1]["aplicavel"]), (
            "as duas mudanças normalizam para a mesma coluna "
            f"({nomes_normalizados[0]!r}) e o plano marcou as DUAS como aplicavel=true: "
            f"{plano}"
        )


@pytest.mark.xfail(
    strict=True,
    raises=pg_errors.DuplicateColumn,
    reason=(
        "L5-31: PUT /api/camadas/{id}/esquema aplica as duas mudanças 'adicionar_campo' colididas (ver "
        "teste irmão sobre o plano) sem tratar o erro do banco — psycopg2.errors.DuplicateColumn atravessa "
        "a rota sem virar 422 'recusado com mensagem', ao contrário do que o item promete para qualquer "
        "mudança que não possa ser aplicada"
    ),
)
def test_aplicar_esquema_com_colisao_de_nome_estoura_erro_de_banco_cru(sessao_a, camada_a):
    r = camada_a.criar()
    assert r.status_code == 201, r.text
    item_id = r.json()["item_id"]

    corpo = {
        "mudancas": [
            {"tipo": "adicionar_campo", "novo_campo": {"nome": "Área", "tipo": "double precision"}},
            {"tipo": "adicionar_campo", "novo_campo": {"nome": "área", "tipo": "double precision"}},
        ]
    }
    # a rota deveria devolver 422 'coluna já usada pela outra mudança do mesmo pedido', nunca deixar o
    # psycopg2.errors.DuplicateColumn atravessar cru até o chamador.
    sessao_a.put(f"/api/camadas/{item_id}/esquema", json=corpo)
