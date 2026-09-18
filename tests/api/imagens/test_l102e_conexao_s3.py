"""Item L1-02-e, "Porta 2": endpoint S3 só-leitura por inquilino para o ArcGIS Pro e para o GDAL.

O portão do item pede, verbatim: "endpoint S3 compatível por inquilino (`s3.<dominio>` -> Garage, chave
só-leitura própria) ... `AWS_S3_ENDPOINT` + chave do inquilino: `gdalinfo /vsis3/<balde>/...` abre;
chave do inquilino A não abre balde do B", mais o documento `docs/PRO_CONEXAO.md`.

A rota (`GET /api/imagens/conexao-s3`, app/imagens/rotas_imagens.py) existia sem nenhum teste. Este
arquivo é o par que o portão exige: a porta legítima ABRE e a porta cruzada NÃO ABRE, medidas contra o
Garage de verdade, com a credencial que a rota entrega — não com uma credencial montada aqui.

Uma recusa medida sozinha não provaria nada: uma chave quebrada também recusaria tudo. Por isso cada
recusa aqui anda ao lado da leitura legítima que usa a MESMA chave.
"""

from __future__ import annotations

import secrets

import pytest

from app.garage import ClienteS3, ErroGarage


def _conexao(sessao):
    r = sessao.get("/api/imagens/conexao-s3")
    assert r.status_code == 200, r.text
    return r.json(), r


def _cliente_s3(conexao) -> ClienteS3:
    """O cliente que o ArcGIS Pro/GDAL montaria a partir da resposta: endpoint, chave, região."""
    return ClienteS3(conexao["endpoint"], conexao["access_key_id"],
                     conexao["secret_access_key"], conexao["regiao"])


@pytest.fixture(scope="module")
def conexao_a(sessao_a):
    return _conexao(sessao_a)[0]


@pytest.fixture(scope="module")
def conexao_b(sessao_b):
    return _conexao(sessao_b)[0]


def test_a_rota_entrega_a_credencial_somente_leitura_do_proprio_balde(sessao_a):
    corpo, resposta = _conexao(sessao_a)
    for campo in ("endpoint", "endpoint_sem_esquema", "regiao", "balde", "access_key_id",
                  "secret_access_key", "estilo_endereco", "exemplo_gdal"):
        assert corpo.get(campo), f"a resposta não traz `{campo}`, que o .acs do ArcGIS Pro exige"
    assert corpo["modo"] == "somente_leitura"
    assert corpo["estilo_endereco"] == "path", "o Garage fala S3 com o balde no CAMINHO"
    assert corpo["exemplo_gdal"].startswith(f"/vsis3/{corpo['balde']}/")
    # a credencial não pode ficar em cache de navegador nem de proxy
    assert "no-store" in (resposta.headers.get("cache-control") or "")


# A leitura é medida por GET/HEAD, e não por LIST, de propósito: é o que `/vsis3/` faz. O GDAL abre um
# COG com HEAD (tamanho) e uma sequência de GET com Range; não precisa de `s3:ListBucket`. `ClienteS3.listar`
# tem um defeito PRÓPRIO de assinatura, achado aqui em 18/09/2026 e fora deste item: falha com 403 "Invalid
# signature" para as DUAS chaves, a de leitura e a de escrita, contra o próprio balde — logo não é permissão.
@pytest.fixture(scope="module")
def objeto_semeado(conexao_a, tenant_id_a):
    """Um objeto real no balde de A, posto pela chave de ESCRITA interna da aplicação (a que nunca sai
    por rota nenhuma), para que a chave só-leitura entregue pela rota tenha o que ler."""
    from app import db, objetos as mod_objetos

    ctx = db.Contexto(tenant_id=tenant_id_a, usuario_id=0, login="teste")
    chave = f"zt-l102e-{secrets.token_hex(6)}.bin"
    conteudo = b"COG-FALSO-" + secrets.token_hex(8).encode()
    with db.db(ctx) as cur:
        bucket = mod_objetos.garantir_bucket(cur, tenant_id_a, "demo")
    cliente_rw = mod_objetos._cliente(bucket, ro=False)
    cliente_rw.put(conexao_a["balde"], chave, conteudo)
    yield {"chave": chave, "conteudo": conteudo}
    cliente_rw.delete(conexao_a["balde"], chave)


def test_par_positivo_a_chave_do_proprio_inquilino_abre_o_proprio_balde(conexao_a, objeto_semeado):
    """PAR de `test_par_negativo_...`: a MESMA chave, no PRÓPRIO balde, lê os bytes de verdade —
    o equivalente ao `gdalinfo /vsis3/<balde>/<objeto>` que o portão pede."""
    s3 = _cliente_s3(conexao_a)
    assert s3.head(conexao_a["balde"], objeto_semeado["chave"]) is not None
    assert s3.get(conexao_a["balde"], objeto_semeado["chave"]) == objeto_semeado["conteudo"]


def test_par_negativo_a_chave_do_inquilino_a_nao_abre_o_balde_do_b(conexao_a, conexao_b, objeto_semeado):
    """A cláusula literal do portão. Mesmo endpoint, mesma assinatura, credencial de A, balde de B."""
    assert conexao_a["balde"] != conexao_b["balde"], "os dois inquilinos têm de ter baldes diferentes"
    s3_a = _cliente_s3(conexao_a)
    with pytest.raises(ErroGarage):
        s3_a.get(conexao_b["balde"], objeto_semeado["chave"])


def test_a_credencial_entregue_e_mesmo_so_leitura(conexao_a):
    """`somente_leitura` não é um rótulo: a mesma chave que lê tem de FALHAR ao escrever."""
    s3 = _cliente_s3(conexao_a)
    with pytest.raises(ErroGarage):
        s3.put(conexao_a["balde"], f"zt-l102e-{secrets.token_hex(4)}.txt", b"nao deveria entrar")


def test_a_rota_nao_aceita_token_de_servico(sessao_a):
    """Trava deliberada: um token de serviço (tiles/imagens) não vira escada para o balde inteiro."""
    r = sessao_a.post("/api/tokens", json={"nome": f"zt-l102e-{secrets.token_hex(4)}",
                                           "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app, base_url="http://testserver") as c:
            resp = c.get("/api/imagens/conexao-s3", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (401, 403), (
            f"token de serviço não pode obter credencial de armazenamento; devolveu {resp.status_code}")
    finally:
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")


def test_o_segredo_nao_vai_para_o_registro_de_evento(sessao_a, conexao_plat_app, tenant_id_a):
    """O corpo carrega o segredo; o log, nunca."""
    from tests.api.test_rls import contexto

    corpo, _ = _conexao(sessao_a)
    segredo = corpo["secret_access_key"]
    contexto(conexao_plat_app, tenant_id_a, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.evento "
            "WHERE tipo = 'imagens/conexao-s3' AND propriedades::text LIKE %s",
            (f"%{segredo}%",),
        )
        assert cur.fetchone()["n"] == 0, "o segredo da credencial apareceu no registro de evento"
