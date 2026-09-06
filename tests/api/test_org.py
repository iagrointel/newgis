"""Configurações da organização (item L0-07-a-configuracoes-org; ADR 0002 seção 11): GET/PUT /api/org só para
admin do inquilino (editor recebe 403); mudança de cota de armazenamento reflete em GET /api/arquivos na
próxima chamada, sem cache; nome/cor/idioma/mapa persistem; validação 422 nomeando o campo (cor sem #, idioma
fora da lista, entrada de auth fora do esquema, campo desconhecido); cota de usuários aplicada em
POST /api/usuarios; logotipo (POST/DELETE /api/org/logo) reaproveita o adaptador de arquivo do L0-11 — PNG/
JPEG normalizado para 300×300, acima de 1 MB e formato não suportado recusados; RLS garante que um inquilino
nunca lê nem altera a configuração de outro."""

import base64
import io
import secrets

import pytest
from PIL import Image

from tests.api.conftest import PREFIXO_TESTE


def _corpo(org: dict) -> dict:
    """Corpo de PUT /api/org que reproduz exatamente o que um GET devolveu (contrato full-replace, igual ao
    PUT /api/org/ldap): usar para restaurar o inquilino ao estado original no fim de cada teste."""
    return {
        "nome": org["nome"],
        "cor": org["cor"],
        "idioma_padrao": org["idioma_padrao"],
        "centro": org["mapa"]["centro"],
        "zoom": org["mapa"]["zoom"],
        "basemap": org["mapa"]["basemap"],
        "srid_padrao": org["mapa"]["srid_padrao"],
        "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"],
        "auth": dict(org["auth"]),
    }


def _png(largura=64, altura=64, cor=(30, 90, 200)) -> bytes:
    im = Image.new("RGB", (largura, altura), cor)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def test_ler_e_gravar_exige_org_configurar_editor_recebe_403(sessao_a, usuarios_a):
    r = sessao_a.get("/api/org")
    assert r.status_code == 200, r.text
    org = r.json()
    for chave in ("slug", "nome", "ativo", "cor", "logo", "idioma_padrao", "mapa", "armazenamento", "usuarios", "auth"):
        assert chave in org, chave
    assert org["slug"] == "demo"
    assert set(org["mapa"]) == {"centro", "zoom", "basemap", "srid_padrao"}
    assert set(org["armazenamento"]) == {"cota_bytes", "bytes_usados"}
    assert set(org["usuarios"]) == {"cota", "ativos"}
    assert org["auth"]["senha_min"] >= 8  # a MESMA política que /api/eu já expõe (subconjunto), aqui completa

    c_ed, _, _ = usuarios_a.sessao("editor")
    r_ed = c_ed.get("/api/org")
    assert r_ed.status_code == 403 and r_ed.json()["erro"] == "sem_privilegio"
    r_ed2 = c_ed.put("/api/org", json=_corpo(org))
    assert r_ed2.status_code == 403 and r_ed2.json()["erro"] == "sem_privilegio"
    # sem sessão nenhuma: 401, nunca 403 (contrato geral da API)
    assert sessao_a.get("/api/org").status_code == 200  # a própria sessao_a segue livre (sanidade do teste)


def test_gravar_altera_nome_cor_idioma_mapa_e_cota_reflete_em_arquivos(sessao_a):
    original = sessao_a.get("/api/org").json()
    try:
        novo_nome = f"{PREFIXO_TESTE}-org-{secrets.token_hex(3)}"
        nova_cota = original["armazenamento"]["cota_bytes"] + 111 * 1024 * 1024
        corpo = _corpo(original)
        corpo.update(
            nome=novo_nome, cor="#112233", idioma_padrao="pt-BR", centro=[-46.63, -23.55], zoom=11,
            basemap="osm", srid_padrao=4326, cota_bytes=nova_cota,
        )
        r = sessao_a.put("/api/org", json=corpo)
        assert r.status_code == 200, r.text
        atualizado = r.json()
        assert atualizado["nome"] == novo_nome
        assert atualizado["cor"] == "#112233"
        assert atualizado["mapa"] == {"centro": [-46.63, -23.55], "zoom": 11, "basemap": "osm", "srid_padrao": 4326}
        assert atualizado["armazenamento"]["cota_bytes"] == nova_cota
        # reflexo imediato em /api/arquivos (mesma coluna plat.tenant.cota_bytes, lida ao vivo — sem cache,
        # sem reinício de processo: é o portão do item)
        r_arq = sessao_a.get("/api/arquivos")
        assert r_arq.status_code == 200 and r_arq.json()["cota_bytes"] == nova_cota
        # GET seguinte (nova requisição, novo Auth resolvido do zero) confirma que persistiu no banco
        assert sessao_a.get("/api/org").json()["nome"] == novo_nome
    finally:
        r = sessao_a.put("/api/org", json=_corpo(original))
        assert r.status_code == 200, r.text
        assert sessao_a.get("/api/arquivos").json()["cota_bytes"] == original["armazenamento"]["cota_bytes"]


def test_validacoes_422_cor_idioma_auth_e_campo_desconhecido(sessao_a):
    original = sessao_a.get("/api/org").json()
    base = _corpo(original)

    sem_hash = dict(base, cor="112233")
    r = sessao_a.put("/api/org", json=sem_hash)
    assert r.status_code == 422 and r.json()["erro"] == "validacao"

    idioma_ruim = dict(base, idioma_padrao="en-US")
    r = sessao_a.put("/api/org", json=idioma_ruim)
    assert r.status_code == 422 and r.json()["erro"] == "validacao" and "idioma_padrao" in r.json()["mensagem"]

    auth_ruim = dict(base, auth={**base["auth"], "senha_min": 4})  # abaixo do mínimo (8) do esquema
    r = sessao_a.put("/api/org", json=auth_ruim)
    assert r.status_code == 422 and r.json()["erro"] == "validacao"
    assert any(d.get("campo") == "senha_min" for d in r.json()["detalhe"])

    auth_chave_desconhecida = dict(base, auth={**base["auth"], "chave_que_nao_existe": 1})
    r = sessao_a.put("/api/org", json=auth_chave_desconhecida)
    assert r.status_code == 422

    centro_ruim = dict(base, centro=[999, 999])
    r = sessao_a.put("/api/org", json=centro_ruim)
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "centro"

    extra = dict(base, tenant_id=999999)  # extra="forbid": nunca dá para mirar outro inquilino por campo extra
    r = sessao_a.put("/api/org", json=extra)
    assert r.status_code == 422

    nome_grande = dict(base, nome="x" * 56)  # ORG_NOME_MAX = 55
    r = sessao_a.put("/api/org", json=nome_grande)
    assert r.status_code == 422

    # nenhuma das tentativas inválidas mudou o estado
    assert sessao_a.get("/api/org").json()["nome"] == original["nome"]


def test_isolamento_entre_inquilinos(sessao_a, sessao_b):
    org_a = sessao_a.get("/api/org").json()
    org_b = sessao_b.get("/api/org").json()
    assert org_a["slug"] != org_b["slug"]
    try:
        corpo_a = _corpo(org_a)
        corpo_a["nome"] = f"{PREFIXO_TESTE}-a-{secrets.token_hex(3)}"
        assert sessao_a.put("/api/org", json=corpo_a).status_code == 200
        # o PUT de A nunca alcança B (RLS: WHERE id = plat.tenant_atual()); B não tem "id" para mirar em A
        assert sessao_b.get("/api/org").json()["nome"] == org_b["nome"]
        assert sessao_a.get("/api/org").json()["nome"] == corpo_a["nome"]
    finally:
        sessao_a.put("/api/org", json=_corpo(org_a))


def test_cota_usuarios_exposta_e_aplicada_em_criar_usuario(sessao_a):
    original = sessao_a.get("/api/org").json()
    ativos = original["usuarios"]["ativos"]
    corpo = _corpo(original)
    corpo["cota_usuarios"] = ativos  # sem vaga para mais um
    assert sessao_a.put("/api/org", json=corpo).status_code == 200
    try:
        assert sessao_a.get("/api/org").json()["usuarios"]["cota"] == ativos
        r = sessao_a.post(
            "/api/usuarios",
            json={"login": f"{PREFIXO_TESTE}{secrets.token_hex(4)}", "nome": "x", "perfil": "visualizador"},
        )
        assert r.status_code == 413 and r.json()["erro"] == "cota_usuarios"
    finally:
        corpo["cota_usuarios"] = original["usuarios"]["cota"]
        assert sessao_a.put("/api/org", json=corpo).status_code == 200
    # cota restaurada: criar de novo funciona (limpo pelo usuarios_a de outro teste não se aplica aqui —
    # criação e limpeza manuais deste teste específico)
    r2 = sessao_a.post(
        "/api/usuarios", json={"login": f"{PREFIXO_TESTE}{secrets.token_hex(4)}", "nome": "x", "perfil": "visualizador"}
    )
    assert r2.status_code == 201, r2.text
    sessao_a.delete(f"/api/usuarios/{r2.json()['usuario']['id']}")


def test_logo_enviar_ler_e_remover(sessao_a):
    original = sessao_a.get("/api/org").json()
    assert original["logo"] is None or isinstance(original["logo"], str)
    try:
        r = sessao_a.post("/api/org/logo", json={"conteudo": _b64(_png())})
        assert r.status_code == 200, r.text
        sha = r.json()["logo"]
        assert len(sha) == 64
        assert sessao_a.get("/api/org").json()["logo"] == sha
        r_obj = sessao_a.get(f"/api/arquivos/{sha}?classe=org_logo")
        assert r_obj.status_code == 200 and r_obj.headers["content-type"] == "image/png"
        im = Image.open(io.BytesIO(r_obj.content))
        assert im.size == (300, 300) and im.format == "PNG"

        # formato não suportado
        r_fmt = sessao_a.post("/api/org/logo", json={"conteudo": _b64(b"nao e uma imagem")})
        assert r_fmt.status_code == 415

        # acima de 1 MiB: recusado ANTES de decodificar como imagem — 413 da rota, ou 422 se o próprio
        # pydantic já cortar pelo `max_length` em base64 antes de chegar lá (mesmo caso de
        # tests/api/catalogo/test_miniatura.py::test_recusas_de_tamanho_formato_e_bomba)
        grande = _b64(b"\x00" * (1024 * 1024 + 1024))
        r_grande = sessao_a.post("/api/org/logo", json={"conteudo": grande})
        assert r_grande.status_code in (413, 422), r_grande.status_code
        if r_grande.status_code == 413:
            assert r_grande.json()["erro"] == "logo_grande"

        r_del = sessao_a.delete("/api/org/logo")
        assert r_del.status_code == 200 and r_del.json()["logo"] is None
        assert sessao_a.get("/api/org").json()["logo"] is None
    finally:
        if original["logo"]:
            # inquilino já tinha logo antes do teste (não deveria, mas por segurança devolve o valor antigo)
            corpo = _corpo(original)
            sessao_a.put("/api/org", json=corpo)
        else:
            sessao_a.delete("/api/org/logo")


@pytest.mark.parametrize("perfil", ["editor", "visualizador", "campo"])
def test_logo_exige_org_configurar(usuarios_a, perfil):
    c, _, _ = usuarios_a.sessao(perfil)
    assert c.post("/api/org/logo", json={"conteudo": _b64(_png())}).status_code == 403
    assert c.delete("/api/org/logo").status_code == 403
