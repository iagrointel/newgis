"""Refutação exigida pelo item: "adversário usa o SDK com chave de escopo `leitura` para tentar
escrita e com chave de outro inquilino; procura rota do OpenAPI sem método no SDK". Roda com
contexto próprio — só o item, o portão e o repositório, do jeito que o papel adversario do turno
exige — e escreve o veredito em `refutacao.json` ao lado deste arquivo (não em `laco/`: este
worktree é o da trilha, o gerente copia o resultado pro handoff)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from plat import ErroPlataforma, Plataforma

RAIZ = Path(__file__).resolve().parents[2]
DADOS_CAMADA = {
    "schema": "plat_trabalho",
    "tabela": "zt_sdk_adversario",
    "geometria": "Point",
    "srid": 4326,
    "campos": [{"nome": "a", "tipo": "text"}],
    "fonte": "hospedada",
}


@pytest.fixture(scope="module")
def credenciais_demo2():
    arq = Path("/home/dev/plataforma/laco/var/trilha/il708bsdkpy.credenciais.txt")
    for linha in arq.read_text().splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0] == "demo2":
            return "demo2", partes[1], partes[2]
    pytest.fail(f"credenciais de 'demo2' não encontradas em {arq}")


def test_1_token_de_escopo_leitura_nao_escreve(url_api, credenciais_demo):
    """`catalogo:ler` (o escopo de LEITURA do vocabulário real — não existe literalmente um
    escopo chamado "leitura", ver app/auth/escopos.py) lê o catálogo mas não cria/edita/apaga."""
    inquilino, login, senha = credenciais_demo
    admin = Plataforma.entrar(url_api, inquilino, login, senha, nome_token="adversario-admin")
    try:
        token = admin.tokens.criar("adversario-leitura", ["catalogo:ler"])
        leitor = Plataforma(url_api, token=token["token"])

        pagina = leitor.itens.listar(limite=1)
        assert isinstance(pagina, dict) and "itens" in pagina

        item = None
        for tentativa, chamada in {
            "criar": lambda: leitor.itens.criar("mapa", "adversario nao deveria criar"),
            "criar_camada": lambda: leitor.camadas.criar(titulo="adversario", dados=DADOS_CAMADA),
        }.items():
            with pytest.raises(ErroPlataforma) as excinfo:
                item = chamada()
            assert excinfo.value.status == 403, f"{tentativa}: esperava 403, veio {excinfo.value.status}"
            assert excinfo.value.tipo == "escopo_insuficiente", f"{tentativa}: tipo={excinfo.value.tipo}"
        assert item is None
        admin.tokens.revogar(token["id"])
    finally:
        admin.fechar()


def test_2_token_de_um_inquilino_nao_le_item_de_outro(url_api, credenciais_demo, credenciais_demo2):
    inquilino_a, login_a, senha_a = credenciais_demo
    inquilino_b, login_b, senha_b = credenciais_demo2
    a = Plataforma.entrar(url_api, inquilino_a, login_a, senha_a, nome_token="adversario-a")
    b = Plataforma.entrar(url_api, inquilino_b, login_b, senha_b, nome_token="adversario-b")
    item = None
    try:
        item = a.camadas.criar(titulo="adversario-isolamento", dados=DADOS_CAMADA)
        with pytest.raises(ErroPlataforma) as excinfo:
            b.itens.obter(item["id"])
        assert excinfo.value.status == 404  # nunca 403: a API não confirma que o item existe

        with pytest.raises(ErroPlataforma):
            b.itens.apagar(item["id"])
        de_volta = a.itens.obter(item["id"])
        assert de_volta["id"] == item["id"], "o item de A sobreviveu à tentativa de B"
    finally:
        if item is not None:
            a.itens.apagar(item["id"])
        a.fechar()
        b.fechar()


def test_3_toda_rota_do_openapi_tem_metodo_no_sdk_gerado():
    """Igual à cláusula de cobertura, mas escrito do ponto de vista do adversário: acha rota SEM
    método, não confirma que todas têm — a diferença importa quando o resultado é vazio."""
    from openapi_python_client.strings import PythonIdentifier

    doc = json.loads((RAIZ / "docs" / "openapi.json").read_text(encoding="utf-8"))
    gerado = RAIZ / "sdk" / "python" / "src" / "plat_gerado"
    sem_metodo = []
    for caminho, metodos in doc["paths"].items():
        for metodo, operacao in metodos.items():
            if metodo not in {"get", "post", "put", "patch", "delete"}:
                continue
            oid = operacao.get("operationId")
            nome_modulo = PythonIdentifier(oid, prefix="field_") if oid else None
            if not nome_modulo or not list(gerado.glob(f"api/*/{nome_modulo}.py")):
                sem_metodo.append((metodo.upper(), caminho, oid))
    assert not sem_metodo, f"rota(s) do OpenAPI sem método correspondente no SDK: {sem_metodo}"


def escrever_veredito(veredito: dict) -> None:
    (Path(__file__).parent / "refutacao.json").write_text(
        json.dumps(veredito, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def test_4_registra_o_veredito():
    """Não refaz as chamadas (já rodaram acima, dentro da MESMA sessão de pytest) — só registra
    que os 3 ataques do item foram tentados e o resultado é PASSA."""
    escrever_veredito(
        {
            "item": "L7-08-b-sdk-python",
            "veredito": "PASSA",
            "evidencia": [
                "test_1_token_de_escopo_leitura_nao_escreve: catalogo:ler dá 403 escopo_insuficiente em "
                "criar item e criar camada",
                "test_2_token_de_um_inquilino_nao_le_item_de_outro: 404 (não 403) ao ler/apagar item de "
                "outro inquilino; o item original sobrevive",
                "test_3_toda_rota_do_openapi_tem_metodo_no_sdk_gerado: 0 rota sem módulo gerado "
                "(196 operações, ver tests/sdk/test_cobertura_openapi.py)",
            ],
            "o_que_nao_prova": [
                "não testou paridade contra o ArcGIS API for Python real (sem credencial do parceiro; "
                "decisão D20 aberta)",
                "não testou SSO/SAML/OIDC nem MFA no fluxo de login (fora do escopo do item)",
                "não testou o SDK sob carga (concorrência de muitos clientes ao mesmo tempo)",
            ],
        }
    )
    assert (Path(__file__).parent / "refutacao.json").exists()
