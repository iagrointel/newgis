"""Item L0-03-e-compartilhamento — provas do portão que o teste do pai (test_compartilhamento.py) não cobre:
(7, INEGOCIÁVEL) varredura cruzada A→B em TODAS as rotas de compartilhamento — sessão de A, token de A, sessão de A
com X-Plat-Inquilino: demo2 e anônimo, contra item/grupo/link/dependência de B, com o estado de B conferido igual
antes e depois; (3) sem acesso = 404 indistinguível de uuid inexistente, nunca 403; (4) expirado 410; (5) contagem de
acessos lida em plat.compartilhamento_link; (6) público com o inquilino desligado 400, e ligado num inquilino próprio
(nunca no demo) → anônimo 200, sessão de outro inquilino 404 pela rota autenticada, desligar nega na hora; segredo do
link: só o sha256 no banco, token ausente de log_acesso.rota (redigido no caminho) e de plat.evento; miniatura por
link e pública sem cache (achado G2-6). Medidas em tests/medidas/L0-03-e.json."""

import base64
import concurrent.futures
import datetime
import hashlib
import secrets
import time
import uuid

import pytest

from tests.api.catalogo.conftest import titulo_zt
from tests.api.conftest import InquilinoTemporario, arquivo_openapi, com_token, novo_cliente
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-e"
PADRAO = {401, 403, 404}
# TODAS as rotas de compartilhamento do OpenAPI (test_rotas_do_openapi_cobertas reprova se nascer uma fora da lista)
ROTAS = [
    ("GET", "/api/itens/{id}/compartilhamento"),
    ("PUT", "/api/itens/{id}/compartilhamento"),
    ("POST", "/api/itens/{id}/links"),
    ("GET", "/api/itens/{id}/links"),
    ("DELETE", "/api/itens/{id}/links/{lid}"),
    ("GET", "/api/compartilhado/{token}"),
    ("GET", "/api/compartilhado/{token}/itens/{id}"),
    ("GET", "/api/compartilhado/{token}/itens/{id}/miniatura"),
    ("GET", "/api/publico/itens/{id}"),
    ("GET", "/api/publico/itens/{id}/miniatura"),
]
# PNG 1×1 (bytes reais; a miniatura é normalizada para 600×400 no servidor)
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _rotas_de_compartilhamento_do_openapi() -> list[tuple[str, str]]:
    spec = arquivo_openapi()
    return sorted(
        (m.upper(), c)
        for c, ms in spec["paths"].items()
        for m in ms
        if "/compartilh" in c or "/links" in c or "/publico/" in c
    )


def test_rotas_do_openapi_cobertas(medida):
    """toda rota de compartilhamento do docs/openapi.json tem caso aqui; rota nova sem caso reprova."""
    rotas = _rotas_de_compartilhamento_do_openapi()
    assert sorted(ROTAS) == rotas, {
        "faltam": sorted(set(rotas) - set(ROTAS)),
        "sobram": sorted(set(ROTAS) - set(rotas)),
    }
    medida(ITEM)(
        "rotas_compartilhamento_cruzadas",
        len(ROTAS),
        "rotas",
        "len(ROTAS) = rotas do OpenAPI com /compartilh, /links ou /publico/",
    )


def _sem_dado_de_pessoa(j: dict) -> None:
    """o JSON do link/público descreve o CONTEÚDO: sem login de ninguém, sem pode_*, sem estado interno."""
    assert "login" not in (j.get("dono") or {}) and "nome" not in (j.get("dono") or {})
    assert not any(k.startswith("pode_") for k in j)
    assert j.get("criado_por") is None and j.get("modificado_por") is None


class _EstadoB:
    """foto do compartilhamento dos itens de B (pela sessão de B) para provar que A não mudou nada."""

    def __init__(self, sessao_b, ids_itens: list[str]):
        self.sessao_b = sessao_b
        self.ids = ids_itens

    def foto(self) -> dict:
        saida = {}
        for iid in self.ids:
            r = self.sessao_b.get(f"/api/itens/{iid}/compartilhamento")
            assert r.status_code == 200, r.text
            j = r.json()
            saida[iid] = {
                "acesso": j["acesso"],
                "grupos": sorted(g["id"] for g in j["grupos"]),
                "links": sorted((k["id"], k["revogado_em"]) for k in j["links"]),
                "deps": sorted((d["id"], d.get("acesso")) for d in j["dependencias"]),
            }
        return saida


@pytest.fixture(scope="module")
def cenario(sessao_a, sessao_b, itens_a, itens_b, usuarios_b):
    """B: camada privada + mapa que a usa + grupo + link; A: item, grupo e link próprios."""
    camada_b = itens_b.criar("camada_vetorial")
    mapa_b = itens_b.criar("mapa", dados={"esquema_versao": 1, "corpo": {"camadas": [camada_b["id"]]}})
    r = sessao_b.post("/api/grupos", json={"nome": titulo_zt("grupo-b"), "visibilidade": "inquilino"})
    assert r.status_code == 201, r.text
    grupo_b = r.json()
    r = sessao_b.post(f"/api/itens/{mapa_b['id']}/links", json={"nome": "zt link b"})
    assert r.status_code == 201, r.text
    link_b = r.json()
    item_a = itens_a.criar("mapa")
    r = sessao_a.post("/api/grupos", json={"nome": titulo_zt("grupo-a"), "visibilidade": "inquilino"})
    assert r.status_code == 201, r.text
    grupo_a = r.json()
    r = sessao_a.post(f"/api/itens/{item_a['id']}/links", json={"nome": "zt link a"})
    assert r.status_code == 201, r.text
    link_a = r.json()
    yield {
        "camada_b": camada_b,
        "mapa_b": mapa_b,
        "grupo_b": grupo_b,
        "link_b": link_b,
        "item_a": item_a,
        "grupo_a": grupo_a,
        "link_a": link_a,
    }
    sessao_a.delete(f"/api/grupos/{grupo_a['id']}")
    sessao_b.delete(f"/api/grupos/{grupo_b['id']}")


def _identidades(sessao_a, token_a):
    """as 4 identidades da varredura cruzada (ADR 0002 seção 16.1)."""
    anon = novo_cliente()
    return [
        ("sessao_a", lambda m, u, c: sessao_a.request(m, u, json=c) if c is not None else sessao_a.request(m, u)),
        (
            "token_a",
            lambda m, u, c: com_token(novo_cliente(), token_a["token"], m, u, **({"json": c} if c is not None else {})),
        ),
        (
            "sessao_a_cabecalho_b",
            lambda m, u, c: sessao_a.request(
                m, u, headers={"X-Plat-Inquilino": "demo2"}, **({"json": c} if c is not None else {})
            ),
        ),
        ("anonimo", lambda m, u, c: anon.request(m, u, **({"json": c} if c is not None else {}))),
    ]


def test_cruzado_a_para_b_em_todas_as_rotas(sessao_a, sessao_b, token_a, cenario, ids, conexao_plat_app, medida):
    """cláusula 7: nenhuma identidade de A lê, altera ou revoga compartilhamento de B; o link de B, anônimo por
    desenho, entrega a A exatamente o que entrega a qualquer anônimo (e nada do que A pede fora do link)."""
    c = cenario
    mapa_b, camada_b, grupo_b, link_b = c["mapa_b"]["id"], c["camada_b"]["id"], c["grupo_b"]["id"], c["link_b"]
    item_a, link_a = c["item_a"]["id"], c["link_a"]
    tok_b, tok_a = link_b["token"], link_a["token"]
    inexistente = str(uuid.uuid4())
    estado_b = _EstadoB(sessao_b, [mapa_b, camada_b])
    antes = estado_b.foto()
    casos = [
        # (método, url, corpo, aceitos, verificação do JSON quando 2xx)
        ("GET", f"/api/itens/{mapa_b}/compartilhamento", None, PADRAO, None),
        (
            "PUT",
            f"/api/itens/{mapa_b}/compartilhamento",
            {"acesso": "inquilino", "grupos": [grupo_b], "aplicar_a_dependencias": [camada_b]},
            PADRAO,
            None,
        ),
        ("PUT", f"/api/itens/{camada_b}/compartilhamento", {"acesso": "inquilino"}, PADRAO, None),
        ("POST", f"/api/itens/{mapa_b}/links", {"nome": "x"}, PADRAO, None),
        ("POST", f"/api/itens/{mapa_b}/links", {"itens_incluidos": [camada_b]}, PADRAO, None),
        ("GET", f"/api/itens/{mapa_b}/links", None, PADRAO, None),
        ("DELETE", f"/api/itens/{mapa_b}/links/{link_b['id']}", None, PADRAO, None),
        # id de link de B em item de A: 404 (o link não é do item); 403 só o `so_sessao` do token, antes do item
        ("DELETE", f"/api/itens/{item_a}/links/{link_b['id']}", None, PADRAO, None),
        # link de B: anônimo por desenho → 200 para todos, só o item do link, sem dado de pessoa
        (
            "GET",
            f"/api/compartilhado/{tok_b}",
            None,
            {200},
            lambda j: (_sem_dado_de_pessoa(j["item"]), j["item"]["id"] == mapa_b, j["itens_incluidos"] == []),
        ),
        ("GET", f"/api/compartilhado/{tok_b}/itens/{mapa_b}", None, {200}, lambda j: _sem_dado_de_pessoa(j)),
        ("GET", f"/api/compartilhado/{tok_b}/itens/{mapa_b}/miniatura", None, {204}, None),
        # pelo link de B: item de A, camada de B fora do link, uuid inexistente → 404 iguais
        ("GET", f"/api/compartilhado/{tok_b}/itens/{item_a}", None, {404}, None),
        ("GET", f"/api/compartilhado/{tok_b}/itens/{camada_b}", None, {404}, None),
        ("GET", f"/api/compartilhado/{tok_b}/itens/{inexistente}", None, {404}, None),
        ("GET", f"/api/compartilhado/{tok_b}/itens/{item_a}/miniatura", None, {404}, None),
        # pelo link de A: item de B → 404
        ("GET", f"/api/compartilhado/{tok_a}/itens/{mapa_b}", None, {404}, None),
        ("GET", f"/api/compartilhado/{tok_a}/itens/{mapa_b}/miniatura", None, {404}, None),
        # público: B não liga compartilhar_publico → 404 (igual a inexistente)
        ("GET", f"/api/publico/itens/{mapa_b}", None, {404}, None),
        ("GET", f"/api/publico/itens/{mapa_b}/miniatura", None, {404}, None),
        ("GET", f"/api/publico/itens/{inexistente}", None, {404}, None),
    ]
    chamadas = 0
    for nome, chamar in _identidades(sessao_a, token_a):
        for metodo, url, corpo, aceitos, verificar in casos:
            r = chamar(metodo, url, corpo)
            chamadas += 1
            assert r.status_code in aceitos, (nome, metodo, url, r.status_code, r.text[:300])
            if r.status_code < 300 and verificar is not None:
                verificar(r.json())
            if r.status_code < 300 and "/compartilhado/" not in url:
                raise AssertionError((nome, metodo, url, "2xx fora do link anônimo"))
            assert estado_b.foto() == antes, (nome, metodo, url)
    # A com o próprio item: grupo de B e dependência de B são "inexistentes" — mesmos códigos de um uuid aleatório
    r1 = sessao_a.put(f"/api/itens/{item_a}/compartilhamento", json={"grupos": [grupo_b]})
    r2 = sessao_a.put(f"/api/itens/{item_a}/compartilhamento", json={"grupos": [inexistente]})
    assert (r1.status_code, r1.json()["erro"]) == (r2.status_code, r2.json()["erro"]) == (404, "grupo_inexistente")
    r1 = sessao_a.put(
        f"/api/itens/{item_a}/compartilhamento", json={"acesso": "inquilino", "aplicar_a_dependencias": [camada_b]}
    )
    r2 = sessao_a.put(
        f"/api/itens/{item_a}/compartilhamento", json={"acesso": "inquilino", "aplicar_a_dependencias": [inexistente]}
    )
    assert (r1.status_code, r1.json()["erro"]) == (r2.status_code, r2.json()["erro"]) == (403, "sem_edicao_no_item")
    r1 = sessao_a.post(f"/api/itens/{item_a}/links", json={"itens_incluidos": [camada_b]})
    r2 = sessao_a.post(f"/api/itens/{item_a}/links", json={"itens_incluidos": [inexistente]})
    assert (r1.status_code, r1.json()["erro"]) == (r2.status_code, r2.json()["erro"]) == (403, "sem_edicao_no_item")
    chamadas += 6
    # B eleva o mapa ao inquilino e ao grupo de B: continua invisível para A pela rota autenticada e pela lista
    assert (
        sessao_b.put(
            f"/api/itens/{mapa_b}/compartilhamento", json={"acesso": "inquilino", "grupos": [grupo_b]}
        ).status_code
        == 200
    )
    assert sessao_a.get(f"/api/itens/{mapa_b}").status_code == 404
    assert sessao_a.get(f"/api/itens/{camada_b}").status_code == 404
    r = sessao_a.get(f"/api/itens?grupo_id={grupo_b}")
    assert r.status_code in PADRAO or r.json()["total"] == 0
    assert (
        sessao_b.put(f"/api/itens/{mapa_b}/compartilhamento", json={"acesso": "privado", "grupos": []}).status_code
        == 200
    )
    # o estado final de B é o inicial; o link de B segue vivo e só contou os acessos que o teste fez
    assert estado_b.foto() == antes
    assert novo_cliente().get(f"/api/compartilhado/{tok_b}").status_code == 200
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo2"], usuario_id=ids["b"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT acessos, revogado_em, token_hash FROM plat.compartilhamento_link WHERE id = %s::uuid",
            (link_b["id"],),
        )
        lk = cur.fetchone()
    conexao_plat_app.rollback()
    assert lk["revogado_em"] is None and lk["token_hash"] == hashlib.sha256(tok_b.encode()).hexdigest()
    medida(ITEM)(
        "chamadas_cruzadas_a_para_b",
        chamadas,
        "chamadas",
        "test_cruzado_a_para_b_em_todas_as_rotas: 4 identidades × casos + 6 casos de A com recurso de B",
    )


def test_sem_acesso_e_404_indistinguivel_de_inexistente(sessao_a, itens_a, editor_a):
    """cláusula 3: quem não pode ver o item recebe 404 (nunca 403), com o MESMO corpo de um uuid inexistente."""
    editor, _ = editor_a
    it = itens_a.criar("mapa")  # do admin; privado
    inexistente = str(uuid.uuid4())
    for metodo, caminho, corpo in (
        ("GET", "/api/itens/{id}", None),
        ("GET", "/api/itens/{id}/compartilhamento", None),
        ("PUT", "/api/itens/{id}/compartilhamento", {"acesso": "inquilino"}),
        ("GET", "/api/itens/{id}/links", None),
        ("POST", "/api/itens/{id}/links", {"nome": "x"}),
        ("DELETE", "/api/itens/{id}/links/" + inexistente, None),
        ("GET", "/api/publico/itens/{id}", None),
    ):
        kw = {"json": corpo} if corpo is not None else {}
        r_real = editor.request(metodo, caminho.format(id=it["id"]), **kw)
        r_falso = editor.request(metodo, caminho.format(id=inexistente), **kw)
        assert r_real.status_code == 404 and r_real.status_code == r_falso.status_code, (metodo, caminho, r_real.text)
        assert r_real.json()["erro"] == r_falso.json()["erro"] and r_real.json()["erro"] != "sem_permissao"


def _miniatura(sessao, iid: str) -> None:
    r = sessao.post(f"/api/itens/{iid}/miniatura", json={"conteudo": base64.b64encode(PNG_1PX).decode()})
    assert r.status_code in (200, 201), r.text


def test_link_expirado_410_contagem_no_banco_revogacao_e_miniatura_sem_cache(
    sessao_a, itens_a, ids, conexao_plat_app, medida
):
    """cláusulas 4 e 5 + conserto do G2-6: contagem lida em plat.compartilhamento_link; expirado 410; revogado 404 em
    ≤ 1 s medido (JSON e miniatura); miniatura por link com Cache-Control no-store."""
    it = itens_a.criar("mapa")
    iid = it["id"]
    _miniatura(sessao_a, iid)
    r = sessao_a.post(f"/api/itens/{iid}/links", json={"nome": "zt contagem"})
    assert r.status_code == 201, r.text
    lk = r.json()
    tok = lk["token"]
    assert len(tok) == 64 and int(tok, 16) >= 0
    anon = novo_cliente()
    for _ in range(3):
        assert anon.get(f"/api/compartilhado/{tok}").status_code == 200
    r = anon.get(f"/api/compartilhado/{tok}/itens/{iid}/miniatura")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"].startswith("no-store"), r.headers["cache-control"]  # G2-6
    etag = r.headers["etag"]
    r = anon.get(f"/api/compartilhado/{tok}/itens/{iid}/miniatura", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.headers["cache-control"].startswith("no-store")
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo"], usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT acessos, ultimo_acesso_em, token_hash, prefixo FROM plat.compartilhamento_link WHERE id = %s::uuid",
            (lk["id"],),
        )
        li = cur.fetchone()
    conexao_plat_app.rollback()
    assert li["acessos"] == 5 and li["ultimo_acesso_em"] is not None  # 3 JSON + 2 miniatura (o 304 também conta)
    assert li["token_hash"] == hashlib.sha256(tok.encode()).hexdigest() and li["prefixo"] == tok[:8]
    assert sessao_a.get(f"/api/itens/{iid}/links").json()[0]["acessos"] == 5
    # revogar: ≤ 1 s até o 404, no JSON e na miniatura
    t0 = time.perf_counter()
    assert sessao_a.delete(f"/api/itens/{iid}/links/{lk['id']}").status_code == 204
    r1 = anon.get(f"/api/compartilhado/{tok}")
    r2 = anon.get(f"/api/compartilhado/{tok}/itens/{iid}/miniatura")
    dt = round((time.perf_counter() - t0) * 1000, 1)
    assert r1.status_code == 404 and r2.status_code == 404 and dt <= 1000, (r1.status_code, r2.status_code, dt)
    medida(ITEM)(
        "revogacao_ate_404_api_ms",
        dt,
        "ms",
        "DELETE /api/itens/{id}/links/{lid} + GET JSON e miniatura por link → 404 (TestClient)",
    )
    with concurrent.futures.ThreadPoolExecutor(20) as ex:
        codigos = list(ex.map(lambda _: novo_cliente().get(f"/api/compartilhado/{tok}").status_code, range(20)))
    assert set(codigos) == {404}
    # expirado = 410
    exp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok2 = sessao_a.post(f"/api/itens/{iid}/links", json={"expira_em": exp}).json()["token"]
    assert anon.get(f"/api/compartilhado/{tok2}").status_code == 200
    time.sleep(2.2)
    r = anon.get(f"/api/compartilhado/{tok2}")
    assert r.status_code == 410 and r.json()["erro"] == "link_expirado"
    assert anon.get(f"/api/compartilhado/{tok2}/itens/{iid}/miniatura").status_code == 410
    # 16 caracteres (refutação): 404, sem diferenciar de inexistente
    assert anon.get(f"/api/compartilhado/{tok[:16]}").json()["erro"] == "link_invalido"
    assert anon.get(f"/api/compartilhado/{secrets.token_hex(32)}").json()["erro"] == "link_invalido"


def test_token_do_link_so_como_hash_e_fora_de_log_e_evento(sessao_a, itens_a, ids, conexao_plat_app, caplog):
    """segurança do item: o token cru não existe em nenhuma coluna de texto do link, não vai para a linha de acesso
    (a mesma `rota` redigida vai ao journal e a log_acesso.rota — o middleware calcula uma vez e usa nas duas; o
    anônimo do link não tem inquilino, então a linha do banco fica com tenant NULL e nenhuma RLS a devolve: a prova
    é pelo registro do journal capturado) e o evento de criação guarda só o prefixo de 8 hex."""
    import logging

    it = itens_a.criar("mapa")
    iid = it["id"]
    tok = sessao_a.post(f"/api/itens/{iid}/links", json={"nome": "zt segredo"}).json()["token"]
    anon = novo_cliente()
    with caplog.at_level(logging.INFO, logger="plat.acesso"):
        assert anon.get(f"/api/compartilhado/{tok}").status_code == 200
        assert anon.get(f"/api/compartilhado/{tok}/itens/{iid}").status_code == 200
        assert anon.get(f"/api/compartilhado/{tok}/itens/{iid}/miniatura").status_code == 204
    rotas = [getattr(r, "rota", "") for r in caplog.records if "/api/compartilhado/" in getattr(r, "rota", "")]
    assert len(rotas) == 3 and all(tok not in r and "<redigido>" in r for r in rotas), rotas
    assert f"/api/compartilhado/<redigido>/itens/{iid}/miniatura" in rotas
    assert not any(tok in r.getMessage() for r in caplog.records if r.name.startswith("plat"))
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo"], usuario_id=ids["a"]["id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT k.* FROM plat.compartilhamento_link k WHERE k.item_id = %s::uuid", (iid,))
        link = cur.fetchone()
        cur.execute(
            "SELECT propriedades::text AS p FROM plat.evento WHERE tipo = 'compartilhamento/link_criar' "
            "AND alvo_id = %s ORDER BY em DESC LIMIT 1",
            (str(link["id"]),),
        )
        ev = cur.fetchone()
    conexao_plat_app.rollback()
    assert link["token_hash"] == hashlib.sha256(tok.encode()).hexdigest()
    assert all(tok not in str(v) for v in link.values())
    assert ev is not None and tok not in ev["p"] and tok[:8] in ev["p"]


def test_publico_desligado_400_e_ligado_em_inquilino_proprio(sessao_plat, sessao_a, itens_a):
    """cláusula 6 (400 com o inquilino desligado) e o lado ligado num inquilino descartável: anônimo lê, a sessão de
    outro inquilino não lê pela rota autenticada, desligar nega na hora; miniatura pública sem cache."""
    inq = InquilinoTemporario(sessao_plat)
    try:
        adm = inq.admin
        r = adm.post(
            "/api/itens",
            json={"tipo": "mapa", "titulo": titulo_zt("publico"), "dados": {"esquema_versao": 1, "corpo": {}}},
        )
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        _miniatura(adm, iid)
        anon = novo_cliente()
        r = adm.put(f"/api/itens/{iid}/compartilhamento", json={"acesso": "publico"})
        assert r.status_code == 400 and r.json()["erro"] == "publico_desligado", r.text
        assert anon.get(f"/api/publico/itens/{iid}").status_code == 404
        org = adm.get("/api/org").json()
        corpo = {
            "nome": org["nome"],
            "cor": org["cor"],
            "idioma_padrao": org["idioma_padrao"],
            **org["mapa"],
            "cota_bytes": org["armazenamento"]["cota_bytes"],
            "cota_usuarios": org["usuarios"]["cota"],
        }
        r = adm.put("/api/org", json={**corpo, "auth": {"compartilhar_publico": True}})
        assert r.status_code == 200, r.text
        assert adm.get(f"/api/itens/{iid}/compartilhamento").json()["publico_permitido"] is True
        r = adm.put(f"/api/itens/{iid}/compartilhamento", json={"acesso": "publico"})
        assert r.status_code == 200 and r.json()["acesso"] == "publico", r.text
        r = anon.get(f"/api/publico/itens/{iid}")
        assert r.status_code == 200 and r.headers["cache-control"].startswith("no-store")
        _sem_dado_de_pessoa(r.json())
        r = anon.get(f"/api/publico/itens/{iid}/miniatura")
        assert r.status_code == 200 and r.headers["cache-control"].startswith("no-store")  # G2-6 também aqui
        # sessão do inquilino demo: a rota autenticada nunca atravessa inquilino, mesmo com o item público
        assert sessao_a.get(f"/api/itens/{iid}").status_code == 404
        assert sessao_a.get(f"/api/itens/{iid}/compartilhamento").status_code == 404
        r = sessao_a.get(f"/api/publico/itens/{iid}")
        assert r.status_code == 200 and "pode_editar" not in r.json()
        # desligar no inquilino: o item continua marcado 'publico' mas ninguém anônimo lê (RLS: tenant_permite_publico)
        r = adm.put("/api/org", json={**corpo, "auth": {"compartilhar_publico": False}})
        assert r.status_code == 200, r.text
        assert anon.get(f"/api/publico/itens/{iid}").status_code == 404
        assert anon.get(f"/api/publico/itens/{iid}/miniatura").status_code == 404
        assert adm.get(f"/api/itens/{iid}").status_code == 200  # o dono continua vendo
    finally:
        inq.apagar()


def test_arvore_mostra_nivel_da_dependencia_e_elevar_e_escolha_explicita(sessao_a, itens_a, editor_a, visualizador_a):
    """cláusula 2 (lado da API): a árvore do mapa traz o nível de cada camada; elevar só com aplicar_a_dependencias;
    sem a marca, compartilhar o mapa NÃO muda a camada; camada de outro dono não se eleva (403)."""
    editor, _ = editor_a
    vis, _ = visualizador_a
    camada = itens_a.criar("camada_vetorial", sessao=editor)
    mapa = itens_a.criar("mapa", sessao=editor, dados={"esquema_versao": 1, "corpo": {"camadas": [camada["id"]]}})
    arvore = editor.get(f"/api/itens/{mapa['id']}/compartilhamento").json()["dependencias"]
    assert [(d["id"], d["acesso"], d["pode_editar"]) for d in arvore] == [(camada["id"], "privado", True)]
    # mapa ao inquilino SEM marcar: a camada fica privada (nada muda em silêncio); o visualizador vê só o mapa
    r = editor.put(f"/api/itens/{mapa['id']}/compartilhamento", json={"acesso": "inquilino"})
    assert r.status_code == 200 and r.json()["dependencias"][0]["acesso"] == "privado"
    assert (
        vis.get(f"/api/itens/{mapa['id']}").status_code == 200
        and vis.get(f"/api/itens/{camada['id']}").status_code == 404
    )
    # com a marca: elevada ao nível do mapa
    r = editor.put(
        f"/api/itens/{mapa['id']}/compartilhamento",
        json={"acesso": "inquilino", "aplicar_a_dependencias": [camada["id"]]},
    )
    assert r.status_code == 200 and r.json()["dependencias"][0]["acesso"] == "inquilino"
    assert vis.get(f"/api/itens/{camada['id']}").status_code == 200
    # camada do admin (visível ao inquilino) num mapa do editor: aparece na árvore com pode_editar=false; elevar = 403
    do_admin = itens_a.criar("camada_vetorial")
    sessao_a.put(f"/api/itens/{do_admin['id']}/compartilhamento", json={"acesso": "inquilino"})
    mapa2 = itens_a.criar("mapa", sessao=editor, dados={"esquema_versao": 1, "corpo": {"camadas": [do_admin["id"]]}})
    arvore = editor.get(f"/api/itens/{mapa2['id']}/compartilhamento").json()["dependencias"]
    assert arvore[0]["pode_editar"] is False and arvore[0]["acesso"] == "inquilino"
    r = editor.put(
        f"/api/itens/{mapa2['id']}/compartilhamento",
        json={"acesso": "privado", "aplicar_a_dependencias": [do_admin["id"]]},
    )
    assert r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item"
    assert sessao_a.get(f"/api/itens/{do_admin['id']}").json()["acesso"] == "inquilino"
