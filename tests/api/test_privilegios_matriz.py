"""Refutação do item L0-07-b-papeis-privilegios: chama TODA rota do OpenAPI vivo que declara um privilégio
comum (nome de `plat.privilegio`, sozinho ou em composição "a|b") com um usuário que PROVADAMENTE não tem
esse privilégio, e exige 403 `sem_privilegio` em todas. É o que o adversário pediria: nenhuma rota escapa.

Fora do escopo deste teste (mecanismo diferente, já coberto pelas suítes do próprio domínio): `grupo:*` e
`token:*` (papel dentro de um grupo/token, não privilégio do inquilino), `rls:visibilidade` (visibilidade de
linha, não checagem de privilégio), `proprio`/`publico`/`vocabulario`/`superadmin` (auto-referência ou rota
aberta) — a mesma lista `VALORES_ESPECIAIS` de `test_privilegios_declarados.py`.

Estratégia: dois usuários `admin` com papel personalizado que restringe a UM privilégio cada (`tokens.gerar`
e `membros.ver`) — a interseção perfil×papel (ADR 0002 seção 3.2, `plat.privilegios_de`) faz o efetivo ser
exatamente esse único nome. Qualquer outro privilégio do vocabulário falta a pelo menos um dos dois, então um
dos dois serve de "usuário sem X" para todo X do vocabulário. O corpo de cada chamada é construído a partir do
esquema OpenAPI (todo campo, obrigatório ou não, com um valor plausível) para não cair num 422 de validação
antes de a checagem de privilégio (que roda primeiro: seção 5 do ADR — dependência resolvida antes do corpo)
ter a chance de responder 403."""

import re
import secrets

import pytest

VALORES_ESPECIAIS = {"publico", "proprio", "vocabulario", "superadmin", "rls:visibilidade"}
SEM_PRIVILEGIO = {"/saude", "/api/versao"}
UUID_NULO = "00000000-0000-0000-0000-000000000000"


def _parte_e_privilegio_puro(parte: str) -> bool:
    return (
        parte not in VALORES_ESPECIAIS
        and not parte.startswith("grupo:")
        and not parte.startswith("token:")
        and not parte.startswith("rls:")
    )


def _rota_testavel(op: dict) -> list[str] | None:
    """Devolve a lista de privilégios (>=1, é OR) de uma rota testável por este arquivo, ou None se a rota usa
    mecanismo especial (fora de escopo, ver docstring)."""
    valor = op.get("x-privilegio")
    if not valor:
        return None
    partes = valor.split("|")
    if not all(_parte_e_privilegio_puro(p) for p in partes):
        return None
    return partes


def _resolver(schema: dict, spec: dict) -> dict:
    if "$ref" in schema:
        nome = schema["$ref"].rsplit("/", 1)[-1]
        return spec["components"]["schemas"][nome]
    if "allOf" in schema:  # um único $ref envolto em allOf (comum quando o campo tem descrição própria)
        base: dict = {}
        for parte in schema["allOf"]:
            base.update(_resolver(parte, spec))
        return {**base, **{k: v for k, v in schema.items() if k != "allOf"}}
    return schema


def _valor_dummy(schema: dict, spec: dict, profundidade: int = 0):
    s = _resolver(schema, spec)
    if profundidade > 4:
        return None
    if "enum" in s:
        return s["enum"][0]
    if "const" in s:
        return s["const"]
    tipo = s.get("type")
    if tipo is None and "anyOf" in s:
        for alt in s["anyOf"]:
            alt_r = _resolver(alt, spec)
            if alt_r.get("type") != "null":
                return _valor_dummy(alt, spec, profundidade + 1)
        return None
    if tipo == "object" or (tipo is None and "properties" in s):
        propriedades = s.get("properties", {})
        return {nome: _valor_dummy(sub, spec, profundidade + 1) for nome, sub in propriedades.items()}
    if tipo == "array":
        minimo = s.get("minItems", 0)
        item = _valor_dummy(s.get("items", {"type": "string"}), spec, profundidade + 1)
        return [item] * max(minimo, 1 if minimo else 0)
    if tipo == "integer":
        minimo = s.get("minimum", s.get("exclusiveMinimum", 0))
        return max(int(minimo) + (1 if "exclusiveMinimum" in s else 0), 1)
    if tipo == "number":
        return 1.0
    if tipo == "boolean":
        return True
    if tipo == "string":
        formato = s.get("format")
        padrao = s.get("pattern")
        if formato == "uuid":
            return UUID_NULO
        if padrao:
            valor = _valor_de_padrao(padrao)
            if valor is not None:
                return valor
        minimo = s.get("minLength", 1)
        return "x" * max(minimo, 1)
    return "x"


def _valor_de_padrao(padrao: str) -> str | None:
    """Um valor plausível para os `pattern` de fato usados no repositório (levantados com
    `grep -rhoP 'pattern=r?"[^"]*"' app/`); nenhuma tentativa de casar regex arbitrário — só o que existe hoje."""
    m = re.match(r"^\^\(([a-zA-Z0-9_|]+)\)\$$", padrao)  # ^(admin|editor|...)$ = enum disfarçado de pattern
    if m:
        return m.group(1).split("|")[0]
    m = re.match(r"^\^\[0-9a-f\]\{(\d+)\}\$$", padrao)  # sha256 etc.: ^[0-9a-f]{N}$
    if m:
        return "0" * int(m.group(1))
    if padrao == r"^#[0-9a-fA-F]{6}$":
        return "#000000"
    if padrao == r"^https?://":
        return "https://x.exemplo.invalido"
    return None


def _corpo_dummy(op: dict, spec: dict) -> dict | None:
    corpo = op.get("requestBody")
    if not corpo:
        return None
    esquema = corpo["content"]["application/json"]["schema"]
    return _valor_dummy(esquema, spec, 0)


def _caminho_concreto(caminho: str, op: dict, spec: dict, ids_reais: dict) -> str:
    """Path param concreto: um id INEXISTENTE serve para toda rota cuja checagem de privilégio é a própria
    dependência `autenticado(privilegio)` (roda antes de tocar o banco — ADR 0002 seção 5). Duas rotas checam
    o privilégio DEPOIS de carregar o recurso (`editar_usuario`, `alterar_compartilhamento`): para essas, um id
    inexistente devolveria 404 antes de a checagem rodar, o que não prova nem desprova o gate; `ids_reais` dá
    o id de um recurso de verdade só para essas exceções nomeadas (ver fixture `ids_reais`)."""
    concreto = caminho
    for p in op.get("parameters", []):
        if p.get("in") != "path":
            continue
        chave = (caminho, p["name"])
        if chave in ids_reais:
            valor = ids_reais[chave]
        else:
            esquema = _resolver(p.get("schema", {}), spec)
            if esquema.get("type") == "integer":
                valor = "999999999"
            elif esquema.get("format") == "uuid":
                valor = UUID_NULO
            else:
                valor = "x"
        concreto = concreto.replace("{" + p["name"] + "}", valor)
    return concreto


@pytest.fixture(scope="module")
def ids_reais(usuarios_a):
    """{(caminho, nome_do_parametro): valor} — só para `PUT /api/usuarios/{id}` (achado deste mesmo teste):
    `editar_usuario` carrega o usuário do banco ANTES de checar `membros.gerir|membros.papel` dentro da função
    (o privilégio não é parâmetro de `autenticado()`, é checado no corpo); com um id inexistente a rota devolve
    404 antes de a checagem ter a chance de responder 403, o que não prova nada sobre o gate de privilégio."""
    u, _ = usuarios_a.criar("visualizador")
    return {("/api/usuarios/{id}", "id"): str(u["id"])}


@pytest.fixture(scope="module")
def caller_por_privilegio(sessao_a, usuarios_a):
    """{privilegio: cliente} — só dois clientes de verdade (tokens.gerar / membros.ver); a função devolve o
    que NÃO tem o privilégio pedido."""
    r = sessao_a.post(
        "/api/papeis",
        json={
            "nome": f"zt-matriz-so-tokens-{secrets.token_hex(3)}",
            "descricao": "matriz de privilégios (só tokens.gerar)",
            "privilegios": ["tokens.gerar"],
        },
    )
    assert r.status_code == 201, r.text
    papel_tokens = r.json()
    r = sessao_a.post(
        "/api/papeis",
        json={
            "nome": f"zt-matriz-so-membros-{secrets.token_hex(3)}",
            "descricao": "matriz de privilégios (só membros.ver)",
            "privilegios": ["membros.ver"],
        },
    )
    assert r.status_code == 201, r.text
    papel_membros = r.json()
    c_tokens, _, _ = usuarios_a.sessao("admin", papel_id=papel_tokens["id"])
    c_membros, _, _ = usuarios_a.sessao("admin", papel_id=papel_membros["id"])
    assert set(c_tokens.get("/api/eu").json()["privilegios"]) == {"tokens.gerar"}
    assert set(c_membros.get("/api/eu").json()["privilegios"]) == {"membros.ver"}
    yield {"tokens.gerar": c_membros, "_outro": c_tokens}
    sessao_a.delete(f"/api/papeis/{papel_tokens['id']}")
    sessao_a.delete(f"/api/papeis/{papel_membros['id']}")


def _sem(caller_por_privilegio, privilegios: list[str]):
    """Cliente que não tem NENHUM dos privilégios da lista (a rota aceita qualquer um = OR)."""
    if "tokens.gerar" in privilegios:
        return caller_por_privilegio["tokens.gerar"]
    return caller_por_privilegio["_outro"]


# PUT /api/itens/{id}/compartilhamento: `aplicar_compartilhamento` (app/catalogo/rotas_compartilhamento.py) chama
# `exigir_edicao` ANTES de checar compartilhar.*  — quem não é dono do item (nem tem conteudo.editar_tudo) toma
# 404/403 de VISIBILIDADE, não o 403 do privilégio declarado; o "usuário sem privilégio nenhum" deste arquivo
# nunca chega lá porque não é dono de nada. `test_compartilhamento_exige_privilegio_mesmo_sendo_dono` prova o
# gate de verdade: dono do item, sem compartilhar.inquilino, tentando compartilhar.
EXCECOES_VISIBILIDADE_PRIMEIRO = {("PUT", "/api/itens/{id}/compartilhamento")}


def test_toda_rota_de_privilegio_puro_devolve_403_sem_o_privilegio(cliente, caller_por_privilegio, ids_reais):
    spec = cliente.get("/api/openapi.json").json()
    testadas, ignoradas = [], []
    for caminho, metodos in spec["paths"].items():
        if caminho in SEM_PRIVILEGIO:
            continue
        for metodo, op in metodos.items():
            privilegios = _rota_testavel(op)
            if privilegios is None:
                ignoradas.append((metodo.upper(), caminho))
                continue
            if (metodo.upper(), caminho) in EXCECOES_VISIBILIDADE_PRIMEIRO:
                continue
            c = _sem(caller_por_privilegio, privilegios)
            alvo = _caminho_concreto(caminho, op, spec, ids_reais)
            corpo = _corpo_dummy(op, spec)
            kwargs = {"json": corpo} if corpo is not None else {}
            r = c.request(metodo.upper(), alvo, **kwargs)
            testadas.append((metodo.upper(), caminho, privilegios, r.status_code, r.text[:200]))
    falhas = [(m, c, p, s, t) for (m, c, p, s, t) in testadas if s != 403]
    assert not falhas, "\n".join(f"{m} {c} privilegio={p} -> {s} {t}" for m, c, p, s, t in falhas)
    assert len(testadas) >= 30, len(testadas)  # sentinela: se cair muito, a extração parou de achar rota


def test_compartilhamento_exige_privilegio_mesmo_sendo_dono(sessao_a, usuarios_a):
    """A exceção documentada acima, provada à parte: dono do item (por isso passa da checagem de visibilidade/
    edição), mas sem compartilhar.inquilino nem compartilhar.publico — tentar tornar o item visível ao
    inquilino tem de dar 403 pelo privilégio, não pelos 404/403 de dono."""
    r = sessao_a.post(
        "/api/papeis",
        json={"nome": f"zt-matriz-so-criar-{secrets.token_hex(3)}", "privilegios": ["conteudo.criar"]},
    )
    assert r.status_code == 201, r.text
    papel = r.json()
    c, usuario, _ = usuarios_a.sessao("editor", papel_id=papel["id"])
    assert set(c.get("/api/eu").json()["privilegios"]) == {"conteudo.criar"}
    r = c.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": "zt-matriz item do dono", "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    try:
        r = c.put(f"/api/itens/{item_id}/compartilhamento", json={"acesso": "inquilino"})
        assert r.status_code == 403 and r.json()["erro"] == "sem_permissao", r.text
        assert r.json()["detalhe"]["exigido"] == "compartilhar.inquilino"
    finally:
        # transfere ANTES de apagar o usuário temporário: `_itens_do_dono` (rotas_usuarios.py) não distingue
        # item na lixeira de item vivo — apagar o usuário com o item ainda em seu nome (mesmo soft-apagado)
        # bloqueia com 409 possui_itens (achado deste teste; DELETE /api/itens só move para a lixeira, não apaga
        # a linha — ver docstring de app/catalogo/rotas_lixeira.py).
        admin_id = sessao_a.get("/api/eu").json()["id"]
        sessao_a.post("/api/itens/transferir", json={"ids": [item_id], "novo_dono_id": admin_id, "simular": False})
        sessao_a.delete(f"/api/itens/{item_id}")
        sessao_a.delete(f"/api/usuarios/{usuario['id']}")
        usuarios_a.criados.remove(usuario["id"])
        sessao_a.delete(f"/api/papeis/{papel['id']}")
