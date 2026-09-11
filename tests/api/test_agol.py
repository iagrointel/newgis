"""Rotas da integração ArcGIS Online do cliente (item L2-08-migracao-agol): credencial por inquilino
(GET/PUT /api/agol/credencial, POST /api/agol/testar) e publicação de camada vetorial hospedada
(POST/GET /api/agol/publicacoes). NUNCA chama a Esri de verdade: `app.agol.cliente.gerar_token`/
`info_portal` são substituídas por dublês (monkeypatch), no mesmo processo do TestClient (`sessao_a` é um
FastAPI TestClient em cima do MESMO `app.main.app` deste módulo — substituir o atributo do módulo
`app.agol.cliente` é visto pela rota, que sempre chama `cliente.gerar_token`/`cliente.info_portal`, nunca
`from ... import gerar_token` — ver o cabeçalho de `app/agol/rotas.py`).

Dois casos exigidos: (1) credencial inválida no teste síncrono (POST /api/agol/testar) devolve ok=False com
mensagem, nunca 500, nunca finge sucesso; (2) o payload de publicação chega corretamente à fila — o job
`agol.publicar` é criado com o item certo e `plat.agol_publicacao` fica em `pendente`, sem publicar de
verdade (o worker desta suíte não roda)."""

import os

import psycopg2
import psycopg2.extras
import pytest

from app.agol import cliente as agol_cliente

PREFIXO_TABELA = "zt_agol_"


def _conexao():
    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = True
    return con


def _criar_camada_hospedada(sessao, titulo: str, schema: str = "d_demo") -> str:
    """Uma tabela mínima com 1 polígono + o item `camada_vetorial` (`fonte: hospedada`) que aponta para ela —
    o mesmo par tabela+item que uma importação de verdade deixa (`tests/api/apoio_camada_teste.py`, mesma
    receita, prefixo próprio `zt_agol_` para não colidir com as tabelas de outro item de teste)."""
    tabela = f"{PREFIXO_TABELA}{titulo}".replace("-", "_")
    con = _conexao()
    try:
        with con.cursor() as cur:
            cur.execute(
                f'CREATE TABLE IF NOT EXISTS "{schema}"."{tabela}" '
                f'(fid bigserial PRIMARY KEY, nome text, geom geometry(Polygon, 4326))'
            )
            cur.execute(f'TRUNCATE "{schema}"."{tabela}"')
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" (nome, geom) VALUES '
                f"(%s, ST_GeomFromText('POLYGON((0 0,0 1,1 1,1 0,0 0))', 4326))",
                (titulo,),
            )
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo,
        "dados": {"schema": schema, "tabela": tabela, "geometria": "Polygon", "srid": 4326,
                  "campos": [{"nome": "nome", "tipo": "text"}], "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _criar_camada_referenciada(sessao, titulo: str) -> str:
    tabela = ("nao_existe_" + titulo).replace("-", "_")
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo,
        "dados": {"schema": "public", "tabela": tabela, "geometria": "Polygon", "srid": 4326,
                  "campos": [], "fonte": "referenciada"},
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def sem_credencial_agol(sessao_a):
    """Garante que o inquilino `demo` começa e termina SEM credencial AGOL configurada — o item é novo, mas a
    trilha é compartilhada entre rodadas, então o teste nunca assume estado vazio nem deixa segredo para trás."""
    sessao_a.put("/api/agol/credencial", json={"remover_credencial": True})
    yield
    sessao_a.put("/api/agol/credencial", json={"remover_credencial": True})


@pytest.fixture
def itens_agol(sessao_a):
    criados = []
    yield criados
    for iid in criados:
        sessao_a.delete(f"/api/itens/{iid}")


# ---------------------------------------------------------------------- credencial: CRUD honesto
def test_credencial_comeca_nao_configurada(sessao_a, sem_credencial_agol):
    r = sessao_a.get("/api/agol/credencial")
    assert r.status_code == 200, r.text
    assert r.json()["configurado"] is False


def test_credencial_gravar_nunca_devolve_o_segredo(sessao_a, sem_credencial_agol):
    r = sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "senha", "credencial": "segredo-de-teste-nao-real",
    })
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["configurado"] is True
    assert corpo["usuario"] == "zt-agol-usuario"
    assert corpo["tipo"] == "senha"
    assert "credencial" not in corpo and "credencial_cifrada" not in corpo and "senha" not in corpo


def test_credencial_por_senha_exige_usuario(sessao_a, sem_credencial_agol):
    r = sessao_a.put("/api/agol/credencial", json={"tipo": "senha", "credencial": "x"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- POST /api/agol/testar
def test_testar_sem_credencial_configurada(sessao_a, sem_credencial_agol):
    r = sessao_a.post("/api/agol/testar")
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "agol_nao_configurado"


def test_testar_credencial_invalida(sessao_a, sem_credencial_agol, monkeypatch):
    """Refutação do item: uma credencial errada nunca vira 500 nem "ok": true — a rota devolve 200 com
    ok=False e a mensagem de erro do ArcGIS Online, sem jamais chamar a Esri de verdade (generateToken é
    substituído por um dublê que recusa, como a Esri recusaria usuário/senha incorretos)."""
    r = sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "senha", "credencial": "senha-errada-de-teste",
    })
    assert r.status_code == 200, r.text

    chamadas = []

    def gerar_token_falso(portal, usuario, senha):
        chamadas.append((portal, usuario, senha))
        raise agol_cliente.ErroAGOL("generateToken não devolveu token (usuário/senha da organização incorretos?)")

    monkeypatch.setattr(agol_cliente, "gerar_token", gerar_token_falso)

    r = sessao_a.post("/api/agol/testar")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is False
    assert "incorretos" in corpo["mensagem"]
    assert corpo["organizacao"] is None
    assert len(chamadas) == 1
    # a rota nunca loga nem devolve a senha em claro, nem no corpo da resposta de erro
    assert "senha-errada-de-teste" not in r.text


def test_testar_credencial_valida(sessao_a, sem_credencial_agol, monkeypatch):
    r = sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "senha", "credencial": "senha-de-teste",
    })
    assert r.status_code == 200, r.text

    monkeypatch.setattr(agol_cliente, "gerar_token", lambda portal, usuario, senha: "token-falso-de-teste")
    monkeypatch.setattr(
        agol_cliente, "info_portal",
        lambda portal, token: {"organizacao": "iAgroIntel (teste)", "usuario": "zt-agol-usuario",
                               "creditos_disponiveis": 1234.5},
    )

    r = sessao_a.post("/api/agol/testar")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True
    assert corpo["organizacao"] == "iAgroIntel (teste)"
    assert corpo["creditos_disponiveis"] == 1234.5
    assert "token-falso-de-teste" not in r.text


# ---------------------------------------------------------------------- POST /api/agol/publicacoes (payload)
def test_publicar_sem_credencial_e_recusado(sessao_a, sem_credencial_agol, itens_agol):
    item_id = _criar_camada_hospedada(sessao_a, "zt-agol-sem-cred")
    itens_agol.append(item_id)
    r = sessao_a.post("/api/agol/publicacoes", json={"item_id": item_id})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "agol_nao_configurado"


def test_publicar_camada_referenciada_e_recusado(sessao_a, sem_credencial_agol, itens_agol):
    sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "token", "credencial": "token-de-teste",
    })
    item_id = _criar_camada_referenciada(sessao_a, "zt-agol-referenciada")
    itens_agol.append(item_id)
    r = sessao_a.post("/api/agol/publicacoes", json={"item_id": item_id})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "camada_referenciada"


def test_publicar_payload_montado_corretamente_e_enfileirado(sessao_a, sem_credencial_agol, itens_agol):
    """O item, o job e o estado por camada nascem certos: o worker desta suíte não roda (nenhuma chamada à
    Esri acontece), então o job fica `pendente` e `GET /api/agol/publicacoes/{item}` reflete exatamente isso
    — nunca "publicado" sem o trabalho ter corrido."""
    sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "token", "credencial": "token-de-teste",
    })
    item_id = _criar_camada_hospedada(sessao_a, "zt-agol-payload")
    itens_agol.append(item_id)

    r0 = sessao_a.get(f"/api/agol/publicacoes/{item_id}")
    assert r0.status_code == 200, r0.text
    assert r0.json()["estado"] == "nunca_publicado"

    r = sessao_a.post("/api/agol/publicacoes", json={"item_id": item_id, "titulo": "Camada de teste AGOL"})
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["item_id"] == item_id
    assert corpo["estado"] in ("pendente", "publicando")
    job_id = corpo["job_id"]
    assert job_id

    rj = sessao_a.get(f"/api/jobs/{job_id}")
    assert rj.status_code == 200, rj.text
    job = rj.json()
    assert job["tipo"] == "agol.publicar"
    assert job["parametros"]["item_id"] == item_id
    assert job["parametros"]["titulo"] == "Camada de teste AGOL"

    r2 = sessao_a.get(f"/api/agol/publicacoes/{item_id}")
    assert r2.status_code == 200, r2.text
    estado = r2.json()
    assert estado["item_id"] == item_id
    assert estado["estado"] in ("pendente", "publicando")
    assert estado["job_id"] == job_id


def test_publicar_item_inexistente(sessao_a, sem_credencial_agol):
    sessao_a.put("/api/agol/credencial", json={
        "portal": "https://iagrointel.maps.arcgis.com", "usuario": "zt-agol-usuario",
        "tipo": "token", "credencial": "token-de-teste",
    })
    r = sessao_a.post("/api/agol/publicacoes", json={"item_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404, r.text
