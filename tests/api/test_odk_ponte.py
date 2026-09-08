"""Ponte com o ODK Central pela API (item L2-07-e-odk-central-ponte), contra o dublê HTTP de
`tests/odk_central_duble.py` (o Central de verdade não está instalado nesta máquina — ADR do item).

Portão do item, cláusula por cláusula:
  C1 formulário publicado aparece no Central          -> test_publica_e_o_formulario_aparece_no_central
  C2 20 envios com foto viram 20 feições com anexo    -> test_vinte_envios_com_foto_viram_vinte_feicoes
     (sha256 conferido)                                  e test_sha256_do_anexo_bate_com_o_que_veio_do_central
  C3 job repetido não duplica (instanceID)            -> test_sincronizar_de_novo_nao_duplica
  C4 Entities viram lista em cascata                  -> test_entidades_viram_lista_com_colunas_de_filtro
  C5 erro de credencial aparece na tela de conexões   -> test_credencial_recusada_marca_a_saude_da_conexao
Refutação: SSRF (test_conexao_para_host_interno_e_recusada), instanceID repetido (C3) e envio malformado
(test_envio_sem_instance_id_e_envio_que_viola_restricao_ficam_registrados_com_motivo)."""

import base64
import hashlib
from pathlib import Path

import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug
from tests.odk_central_duble import URL_BASE, CentralDuble, instalar

XLSFORM = Path(__file__).resolve().parents[1] / "coleta" / "xlsforms" / "campo_odk.xlsx"
PROJETO = 7


@pytest.fixture
def duble(monkeypatch) -> CentralDuble:
    d = CentralDuble(projeto=PROJETO)
    instalar(monkeypatch, d)
    return d


@pytest.fixture
def limpeza(conexao_plat_app, sessao_a):
    """Apaga camadas, formulários e conexões `zt` criados aqui (a ponte e os envios caem por CASCADE)."""
    conexoes: list[str] = []
    yield conexoes
    for cid in conexoes:
        sessao_a.delete(f"/api/conexoes/{cid}")
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT id, tipo, dados FROM plat.item WHERE titulo LIKE %s AND tipo IN ('formulario', "
                    "'camada_vetorial')", (f"{PREFIXO_TESTE} %",))
        for r in cur.fetchall():
            d = r["dados"] or {}
            if r["tipo"] == "camada_vetorial" and d.get("schema") and d.get("tabela"):
                cur.execute(f'DROP TABLE IF EXISTS "{d["schema"]}"."{d["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.item WHERE id = %s", (r["id"],))
    conexao_plat_app.commit()


def _b64_xlsform() -> str:
    return base64.b64encode(XLSFORM.read_bytes()).decode("ascii")


def _conexao(sessao, limpeza, duble, sufixo="odk", url=URL_BASE, credencial=None):
    r = sessao.post("/api/conexoes", json={
        "tipo": "odk_central", "nome": f"{PREFIXO_TESTE}-central-{sufixo}", "url": url,
        "credencial": credencial if credencial is not None else duble.token,
    })
    assert r.status_code == 201, r.text
    limpeza.append(r.json()["id"])
    return r.json()


def _formulario(sessao):
    r = sessao.post("/api/formularios/xlsform", json={
        "nome": "campo_odk.xlsx", "conteudo": _b64_xlsform(), "titulo": f"{PREFIXO_TESTE} campo odk"})
    assert r.status_code == 201, r.text
    return r.json()


def _ponte(sessao, conexao, formulario, projeto=PROJETO, conteudo=None):
    return sessao.post("/api/odk/pontes", json={
        "conexao": conexao["id"], "formulario": formulario["id"], "projeto": projeto,
        "conteudo": conteudo if conteudo is not None else _b64_xlsform()})


def _preparar(sessao, limpeza, duble):
    conexao = _conexao(sessao, limpeza, duble)
    formulario = _formulario(sessao)
    r = _ponte(sessao, conexao, formulario)
    assert r.status_code == 201, r.text
    return conexao, formulario, r.json()


def _linhas(con, camada_dados: dict) -> list[dict]:
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin = cur.fetchone()["usuario_id"]
    contexto(con, ids["demo"], usuario_id=admin, login="admin")
    with con.cursor() as cur:
        cur.execute(f'SELECT * FROM "{camada_dados["schema"]}"."{camada_dados["tabela"]}" ORDER BY fid')
        return cur.fetchall()


def _camada(sessao, item_id: str) -> dict:
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()["dados"]


# --------------------------------------------------------------------------------------- C1
def test_publica_e_o_formulario_aparece_no_central(sessao_a, duble, limpeza):
    conexao, formulario, ponte = _preparar(sessao_a, limpeza, duble)
    assert ponte["xml_form_id"] == "campo_odk" and ponte["projeto"] == PROJETO
    assert ponte["versao"] == "2026090701" and ponte["publicado_em"]
    # a planilha chegou inteira ao Central, com o content-type de XLSForm
    assert duble.corpo_publicado == XLSFORM.read_bytes()
    assert "campo_odk" in duble.formularios
    # e o Central, perguntado de novo pela nossa rota, confirma o formulário publicado
    r = sessao_a.get(f"/api/odk/pontes/{ponte['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["central"]["xmlFormId"] == "campo_odk"
    assert r.json()["envios"] == {"aplicados": 0, "recusados": 0}
    assert any(p["id"] == ponte["id"] for p in sessao_a.get("/api/odk/pontes").json()["itens"])


def test_planilha_diferente_do_formulario_e_recusada(sessao_a, duble, limpeza):
    conexao = _conexao(sessao_a, limpeza, duble)
    formulario = _formulario(sessao_a)
    outra = base64.b64encode((XLSFORM.parent / "basico.xlsx").read_bytes()).decode("ascii")
    r = _ponte(sessao_a, conexao, formulario, conteudo=outra)
    assert r.status_code == 422 and r.json()["erro"] == "xlsform_diferente"
    assert duble.formularios == {}  # nada foi publicado no Central


def test_conexao_de_outro_tipo_nao_serve_de_ponte(sessao_a, duble, limpeza):
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "ogc_api", "nome": f"{PREFIXO_TESTE}-nao-odk", "url": URL_BASE})
    assert r.status_code == 201, r.text
    limpeza.append(r.json()["id"])
    formulario = _formulario(sessao_a)
    resp = _ponte(sessao_a, r.json(), formulario)
    assert resp.status_code == 422 and resp.json()["erro"] == "conexao_nao_e_odk"


# --------------------------------------------------------------------------------------- C2
def test_vinte_envios_com_foto_viram_vinte_feicoes(sessao_a, duble, limpeza, conexao_plat_app):
    _conexao_e_ponte = _preparar(sessao_a, limpeza, duble)
    _conexao, formulario, ponte = _conexao_e_ponte
    duble.semear_envios(20)
    r = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar")
    assert r.status_code == 200, r.text
    rel = r.json()
    assert (rel["lidos"], rel["aplicados"], rel["repetidos"], rel["recusados"]) == (20, 20, 0, [])
    assert rel["anexos"] == 20

    camada = _camada(sessao_a, formulario["documento"]["camada_destino"])
    linhas = _linhas(conexao_plat_app, camada)
    assert len(linhas) == 20
    assert {li["ponto"] for li in linhas} == {f"P-{i:03d}" for i in range(20)}
    assert all(li["geom"] is not None for li in linhas)          # geopoint do OData virou geometria
    assert sorted(li["arvores"] for li in linhas) == list(range(20))
    assert all(li["coleta_dispositivo"] == "odk-central" for li in linhas)
    # repetição: 2 amostras por envio na camada filha
    filha_id = formulario["documento"]["camadas_filhas"]["amostras"]
    filhas = _linhas(conexao_plat_app, _camada(sessao_a, filha_id))
    assert len(filhas) == 40

    v = sessao_a.get(f"/api/odk/pontes/{ponte['id']}").json()
    assert v["envios"] == {"aplicados": 20, "recusados": 0}


def test_sha256_do_anexo_bate_com_o_que_veio_do_central(sessao_a, duble, limpeza, conexao_plat_app):
    _c, formulario, ponte = _preparar(sessao_a, limpeza, duble)
    duble.semear_envios(3)
    assert sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()["anexos"] == 3
    camada = _camada(sessao_a, formulario["documento"]["camada_destino"])
    esperados = {hashlib.sha256(b).hexdigest() for b in duble.anexos.values()}
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome, sha256, content_type FROM plat.feicao_anexo WHERE schema_dado = %s "
                    "AND tabela_dado = %s AND apagado_em IS NULL", (camada["schema"], camada["tabela"]))
        gravados = cur.fetchall()
    assert len(gravados) == 3
    assert {g["sha256"] for g in gravados} == esperados
    assert {g["content_type"] for g in gravados} == {"image/png"}
    assert {g["nome"] for g in gravados} == {f"foto-{i:03d}.png" for i in range(3)}


# --------------------------------------------------------------------------------------- C3
def test_sincronizar_de_novo_nao_duplica(sessao_a, duble, limpeza, conexao_plat_app):
    _c, formulario, ponte = _preparar(sessao_a, limpeza, duble)
    duble.semear_envios(20)
    primeira = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    segunda = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    terceira = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    assert primeira["aplicados"] == 20
    assert (segunda["aplicados"], segunda["repetidos"]) == (0, 20)
    assert (terceira["aplicados"], terceira["repetidos"]) == (0, 20)
    camada = _camada(sessao_a, formulario["documento"]["camada_destino"])
    assert len(_linhas(conexao_plat_app, camada)) == 20      # nem uma feição a mais

    # envio NOVO no Central entra; os 20 antigos continuam sendo repetição
    duble.semear_envios(1, prefixo="uuid:zt-odk-novo-")
    quarta = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    assert (quarta["lidos"], quarta["aplicados"], quarta["repetidos"]) == (21, 1, 20)
    assert len(_linhas(conexao_plat_app, camada)) == 21


# --------------------------------------------------------------------------------------- refutação
def test_envio_sem_instance_id_e_envio_que_viola_restricao_ficam_registrados_com_motivo(
        sessao_a, duble, limpeza, conexao_plat_app):
    _c, formulario, ponte = _preparar(sessao_a, limpeza, duble)
    duble.semear_envios(2)
    duble.envios[0].pop("__id")                                   # envio malformado: sem instanceID
    duble.envios[1]["detalhe"]["arvores"] = -5                    # viola a restrição do formulário
    duble.semear_envios(1, prefixo="uuid:zt-odk-bom-")            # um envio bom no meio da bagunça
    rel = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    assert rel["lidos"] == 3 and rel["aplicados"] == 1
    motivos = {r["erro"] for r in rel["recusados"]}
    assert motivos == {"envio_sem_instance_id", "resposta_invalida"}
    camada = _camada(sessao_a, formulario["documento"]["camada_destino"])
    assert len(_linhas(conexao_plat_app, camada)) == 1            # o bom entrou; nenhum recusado entrou

    # o recusado com instanceID fica GRAVADO com o motivo (nunca some em silêncio) e não é retentado como novo
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT instance_id, feicao_id, motivo FROM plat.odk_envio WHERE ponte_id = %s::uuid "
                    "ORDER BY instance_id", (ponte["id"],))
        gravados = cur.fetchall()
    recusado = [g for g in gravados if g["feicao_id"] is None]
    assert len(recusado) == 1 and recusado[0]["motivo"].startswith("resposta_invalida:")
    de_novo = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    assert de_novo["aplicados"] == 0 and de_novo["repetidos"] == 2


def test_conexao_para_host_interno_e_recusada(sessao_a, duble, limpeza):
    for url in ("http://127.0.0.1:8150/v1", "http://169.254.169.254/v1", "http://10.0.0.5/v1"):
        r = sessao_a.post("/api/conexoes", json={
            "tipo": "odk_central", "nome": f"{PREFIXO_TESTE}-interna", "url": url, "credencial": "x"})
        assert r.status_code == 422, r.text
        assert r.json()["erro"] == "url_insegura"


# --------------------------------------------------------------------------------------- C4
def test_entidades_viram_lista_com_colunas_de_filtro(sessao_a, duble, limpeza):
    _c, _f, ponte = _preparar(sessao_a, limpeza, duble)
    duble.semear_entidades("municipios", [
        ("ssa", "Salvador", {"estado": "ba", "regiao": "ne"}),
        ("ilh", "Ilhéus", {"estado": "ba", "regiao": "ne"}),
        ("spo", "São Paulo", {"estado": "sp", "regiao": "se"}),
    ])
    r = sessao_a.get(f"/api/odk/pontes/{ponte['id']}/entidades/municipios")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["lista"] == "municipios" and corpo["total"] == 3
    assert corpo["colunas"] == ["estado", "regiao"]
    da_bahia = [o["nome"] for o in corpo["opcoes"] if o["estado"] == "ba"]
    assert da_bahia == ["ssa", "ilh"]
    assert corpo["opcoes"][0]["rotulo"]["pt"] == "Salvador"
    assert sessao_a.get(f"/api/odk/pontes/{ponte['id']}/entidades/nao-existe").status_code == 502


# --------------------------------------------------------------------------------------- C5
def test_credencial_recusada_marca_a_saude_da_conexao(sessao_a, duble, limpeza):
    conexao, _f, ponte = _preparar(sessao_a, limpeza, duble)
    duble.token = "outro-token-o-central-girou-a-credencial"
    r = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar")
    assert r.status_code == 409 and r.json()["erro"] == "odk_credencial_recusada"
    visto = sessao_a.get(f"/api/conexoes/{conexao['id']}").json()
    assert visto["saude"] == "erro" and visto["saude_mensagem"] == "odk:credencial_recusada"
    assert visto["estado_saude"] == "fora" and visto["saude_verificada_em"]
    # o valor da credencial nunca aparece em resposta nenhuma (o nome do erro fala dela; o token, não)
    assert duble.token not in r.text and duble.token not in str(visto)
    assert "credencial_cifrada" not in str(visto) and visto["tem_credencial"] is True


def test_ponte_de_a_nao_aparece_para_b(sessao_a, sessao_b, duble, limpeza):
    _c, _f, ponte = _preparar(sessao_a, limpeza, duble)
    assert sessao_b.get(f"/api/odk/pontes/{ponte['id']}").status_code == 404
    assert sessao_b.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").status_code == 404
    assert all(p["id"] != ponte["id"] for p in sessao_b.get("/api/odk/pontes").json()["itens"])
