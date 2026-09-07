"""CSV de regras nas colunas da Esri (item L4-03-a-regras-de-conectividade, `app/rede_utilidades/regras_csv.py`;
ADR docs/adr/20260906T2058-regras-de-conectividade.md). Cláusula do portão provada aqui: "CSV de regras
exportado e reimportado dá o mesmo conjunto". Corpo é `text/csv`, não JSON: sob CSRF de sessão (ADR 0002
§5.3) toda escrita não-JSON recebe 415 antes do privilégio (mesma regra de `POST /api/arquivos`, ADR 0006) —
por isso a importação aqui SEMPRE passa por token de serviço, nunca pela sessão do navegador."""

import json

import pytest

from app.rede_utilidades import instalados
from tests.api.conftest import PREFIXO_TESTE, com_token


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


@pytest.fixture
def token_admin(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tok-regras",
                                            "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture
def rede_eletrica(sessao_a, limpar_redes, request):
    r = sessao_a.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-csv-{request.node.name[:40]}",
                                          "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar_redes.append(rid)
    assert sessao_a.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                          headers={"Content-Type": "application/json"}).status_code == 201
    return rid


# ------------------------------------------------------------------------------------------------ round-trip

def test_exportar_e_reimportar_da_o_mesmo_conjunto_de_regras(sessao_a, cliente, token_admin, rede_eletrica):
    original = sessao_a.get(f"/api/rede/{rede_eletrica}/regras").json()
    assert original["total"] >= 40  # o pacote elétrico inteiro

    csv1 = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv")
    assert csv1.status_code == 200
    assert csv1.headers["content-type"].startswith("text/csv")
    bruto1 = csv1.content

    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=bruto1, headers={"Content-Type": "text/csv"})
    assert r.status_code == 201, r.text
    assert r.json()["total"] == original["total"]

    csv2 = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv")
    assert csv2.content == bruto1, "reexportar depois de reimportar não deu o mesmo arquivo byte a byte"

    depois = sessao_a.get(f"/api/rede/{rede_eletrica}/regras").json()
    conjunto_antes = {json.dumps(x, sort_keys=True) for x in _chave_csv(original["itens"])}
    conjunto_depois = {json.dumps(x, sort_keys=True) for x in _chave_csv(depois["itens"])}
    assert conjunto_antes == conjunto_depois
    # a `descricao` (só existe no pacote JSON, não é uma das 13 colunas da Esri) FICA para trás na
    # importação por CSV — fronteira honesta do formato, não bug: nenhuma regra do conjunto reimportado
    # tem descrição, porque o CSV nunca carregou uma para reconstruir.
    assert all(r.get("descricao") is None for r in depois["itens"])
    assert any(r.get("descricao") for r in original["itens"])  # o pacote original TINHA descrição


def _chave_csv(itens):
    """As regras trocam de uuid na substituição (é um DELETE+INSERT) e a `descricao` não é uma das 13
    colunas da Esri (fica para trás na importação por CSV, fronteira do formato) — o CONJUNTO que o
    round-trip promete é tipo/de/para/via/terminais, a mesma chave que `regras_csv.exportar` usa."""
    saida = []
    for r in itens:
        r = dict(r)
        r.pop("id", None)
        r.pop("descricao", None)
        saida.append(r)
    return saida


def test_csv_com_menos_regras_substitui_o_conjunto_nao_acrescenta(sessao_a, cliente, token_admin, rede_eletrica):
    """A diferença documentada no ADR: a ferramenta da Esri ACRESCENTA, esta SUBSTITUI."""
    bruto = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv").content
    linhas = bruto.decode("utf-8").splitlines()
    reduzido = "\n".join(linhas[:1] + linhas[1:6]).encode("utf-8")  # cabeçalho + 5 regras só

    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=reduzido, headers={"Content-Type": "text/csv"})
    assert r.status_code == 201, r.text
    assert r.json()["total"] == 5

    depois = sessao_a.get(f"/api/rede/{rede_eletrica}/regras").json()
    assert depois["total"] == 5


def test_csv_com_tipo_de_regra_inexistente_e_recusado_com_a_linha(sessao_a, cliente, token_admin, rede_eletrica):
    csv = ("RULETYPE,FROMFEATURECLASS,FROMASSETGROUP,FROMASSETTYPE,FROMTERMINAL,TOFEATURECLASS,"
           "TOASSETGROUP,TOASSETTYPE,TOTERMINAL,VIAFEATURECLASS,VIAASSETGROUP,VIAASSETTYPE,VIATERMINAL\r\n"
           "Rede Neural Connectivity,transformador_de_distribuicao,transformador_de_distribuicao,1,alta,"
           "trecho_de_media_tensao,trecho_de_media_tensao,1,,,,,\r\n").encode("utf-8")
    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=csv, headers={"Content-Type": "text/csv"})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "csv_regras_invalido"
    problema = corpo["detalhe"][0] if isinstance(corpo.get("detalhe"), list) else corpo["detalhe"]
    assert problema["linha"] == 2 and problema["erro"] == "regra_tipo_inexistente"
    # substituição é transacional: a rejeição não mexeu no conjunto vigente
    assert sessao_a.get(f"/api/rede/{rede_eletrica}/regras").json()["total"] >= 40


def test_csv_com_grupo_inexistente_e_recusado(sessao_a, cliente, token_admin, rede_eletrica):
    csv = ("RULETYPE,FROMFEATURECLASS,FROMASSETGROUP,FROMASSETTYPE,FROMTERMINAL,TOFEATURECLASS,"
           "TOASSETGROUP,TOASSETTYPE,TOTERMINAL,VIAFEATURECLASS,VIAASSETGROUP,VIAASSETTYPE,VIATERMINAL\r\n"
           "Junction Edge Connectivity,fusao_nuclear,fusao_nuclear,1,alta,"
           "trecho_de_media_tensao,trecho_de_media_tensao,1,,,,,\r\n").encode("utf-8")
    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=csv, headers={"Content-Type": "text/csv"})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["erro"] == "grupo_inexistente"


def test_csv_com_assetgroup_divergente_de_featureclass_e_recusado(sessao_a, cliente, token_admin, rede_eletrica):
    csv = ("RULETYPE,FROMFEATURECLASS,FROMASSETGROUP,FROMASSETTYPE,FROMTERMINAL,TOFEATURECLASS,"
           "TOASSETGROUP,TOASSETTYPE,TOTERMINAL,VIAFEATURECLASS,VIAASSETGROUP,VIAASSETTYPE,VIATERMINAL\r\n"
           "Junction Edge Connectivity,transformador_de_distribuicao,poste_fantasma,1,alta,"
           "trecho_de_media_tensao,trecho_de_media_tensao,1,,,,,\r\n").encode("utf-8")
    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=csv, headers={"Content-Type": "text/csv"})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["erro"] == "grupo_divergente"


def test_csv_vazio_e_recusado(sessao_a, cliente, token_admin, rede_eletrica):
    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=b"", headers={"Content-Type": "text/csv"})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["erro"] == "vazio"


def test_csv_com_cabecalho_errado_e_recusado(sessao_a, cliente, token_admin, rede_eletrica):
    r = com_token(cliente, token_admin, "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                  content=b"UMA,DUAS,TRES\r\n", headers={"Content-Type": "text/csv"})
    assert r.status_code == 422, r.text
    assert r.json()["detalhe"][0]["erro"] == "cabecalho_invalido"


# --------------------------------------------------------------------------------- privilégio: só rede.administrar

def test_token_com_escopo_restrito_nao_importa_csv(sessao_a, cliente, rede_eletrica):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tok-restrito", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201
    tok = r.json()
    try:
        bruto = sessao_a.get(f"/api/rede/{rede_eletrica}/regras.csv").content
        resp = com_token(cliente, tok["token"], "POST", f"/api/rede/{rede_eletrica}/regras.csv",
                          content=bruto, headers={"Content-Type": "text/csv"})
        assert resp.status_code == 403, resp.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_leitura_do_csv_nao_exige_administrar_so_visibilidade(sessao_a, usuarios_a, rede_eletrica):
    visual, _, _ = usuarios_a.sessao("visualizador")
    assert visual.get(f"/api/rede/{rede_eletrica}/regras.csv").status_code == 200
    assert visual.get(f"/api/rede/{rede_eletrica}/regras").status_code == 200
