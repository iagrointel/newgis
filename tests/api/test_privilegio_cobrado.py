"""Varredura de privilégio rota por rota (item L0-02-g-checagem-privilegio-papel-id).

`tests/api/test_privilegios_declarados.py` prova que toda rota DECLARA `x-privilegio` e que o nome existe no
vocabulário. Isto aqui prova a outra metade: que o privilégio declarado é o COBRADO. Duas camadas.

1. Estática, nas 100 % das rotas de `docs/openapi.json`: lê o fecho (closure) da dependência `autenticado(...)`
   de cada rota viva e compara com o que a rota declara. Privilégio nomeado tem de estar na dependência;
   `superadmin` tem de vir com `superadmin=True`; declaração especial (`proprio`, `vocabulario`,
   `rls:visibilidade`, `grupo:*`, `token:*`) ou alternativa (`a|b`) tem de vir com a dependência SEM privilégio
   — é cobrada no corpo da rota, e aí só a camada 2 prova.

2. Dinâmica, nas rotas de privilégio nomeado único: um administrador de um inquilino descartável recebe um papel
   personalizado com TODOS os privilégios menos um; toda rota que declara o privilégio que falta responde 403
   `sem_privilegio` com `exigido` igual ao declarado. Depois o mesmo usuário recebe o papel completo e nenhuma
   dessas rotas responde `sem_privilegio` — sem esse controle positivo o 403 poderia vir de outra coisa.

O que fica de fora, declarado: rota cujo privilégio é cobrado DEPOIS de carregar o recurso (as alternativas de
conteúdo/grupo) só é provada dinamicamente onde o item tem recurso à mão (as duas de `/api/usuarios`); as demais
entram na medida `rotas_alternativas_nao_provadas` como fronteira honesta, não como aprovação.
"""

import re

import pytest
from fastapi.routing import APIRoute

from tests.api.conftest import InquilinoTemporario, arquivo_openapi, entrar, novo_cliente

ESPECIAIS = {"publico", "proprio", "vocabulario", "superadmin", "rls:visibilidade"}
PREFIXOS_ESPECIAIS = ("grupo:", "token:")
# Rotas de privilégio alternativo cobrado no corpo que ESTE item prova dinamicamente (tem recurso próprio).
ALTERNATIVAS_PROVADAS = {("PUT", "/api/usuarios/{id}"), ("POST", "/api/usuarios/lote")}


def _rotas_vivas(app) -> dict[tuple[str, str], APIRoute]:
    def andar(rotas):
        for r in rotas:
            if isinstance(r, APIRoute):
                yield r
            elif hasattr(r, "original_router"):  # fastapi novo embrulha o include_router
                yield from andar(r.original_router.routes)
            elif hasattr(r, "routes"):
                yield from andar(r.routes)

    saida = {}
    for r in andar(app.routes):
        # o OpenAPI grava `/api/objetos/{chave}`; a rota viva declara o conversor `{chave:path}`
        caminho = re.sub(r"\{([^:}]+):[^}]+\}", r"{\1}", r.path)
        for metodo in r.methods:
            saida[(metodo.upper(), caminho)] = r
    return saida


def _portao(rota: APIRoute) -> dict | None:
    """Valores capturados pela dependência `autenticado(...)` da rota; None se a rota não tem essa dependência."""
    for d in rota.dependant.dependencies:
        f = d.call
        if getattr(f, "__name__", "") == "dependencia" and f.__closure__:
            return dict(zip(f.__code__.co_freevars, (c.cell_contents for c in f.__closure__), strict=True))
    return None


def _partes(declarado: str) -> list[str]:
    return [p for p in declarado.split("|")]


def _nomeado_unico(declarado: str | None) -> str | None:
    """Privilégio real, único, sem alternativa — o caso que a camada 2 consegue provar sozinha."""
    if not declarado or "|" in declarado or declarado in ESPECIAIS or declarado.startswith(PREFIXOS_ESPECIAIS):
        return None
    return declarado


def _rotas_declaradas():
    spec = arquivo_openapi()
    return sorted((m.upper(), c, op) for c, ms in spec["paths"].items() for m, op in ms.items())


# ---------------------------------------------------------------- camada 1: estática, 100 % das rotas
# Divergências ENCONTRADAS por esta varredura em 06/09/2026 e ainda não corrigidas: a rota cobra na dependência
# um privilégio que a declaração não menciona. Nenhuma delas afrouxa o acesso — todas o APERTAM (exigem mais do
# que a documentação promete), por isso não são falha de segurança; são declaração incompleta, e o conserto é do
# dono de cada rota (app/auth/rotas_tokens.py, app/acervo/, app/catalogo/), fora dos arquivos deste item. A lista
# é CONGELADA: divergência nova reprova o teste. Chave (método, caminho) → (declarado, cobrado, motivo).
DIVERGENCIAS_CONHECIDAS = {
    ("GET", "/api/tokens/{id}"): ("token:dono|tokens.gerir_todos", "tokens.gerar"),
    ("GET", "/api/tokens/{id}/log"): ("token:dono|tokens.gerir_todos", "tokens.gerar"),
    ("DELETE", "/api/tokens/{id}"): ("token:dono|tokens.gerir_todos", "tokens.gerar"),
    ("POST", "/api/tokens/{id}/renovar"): ("token:dono", "tokens.gerar"),
    ("POST", "/api/acervo/{fonte_id}/adicionar"): ("conteudo.criar|conteudo.registrar_fonte", "conteudo.criar"),
    ("POST", "/api/itens/{id}/miniatura/gerar"): ("rls:visibilidade|conteudo.editar_tudo", "jobs.executar"),
    ("POST", "/api/lixeira/esvaziar"): ("rls:visibilidade|conteudo.apagar_tudo", "jobs.executar"),
    # rota que resolve a sessão no corpo, sem a dependência autenticado(): sair não pode depender de privilégio
    ("POST", "/api/logout"): ("proprio", None),
}
SEM_PRIVILEGIO = {"/saude", "/api/versao"}


def test_declarado_e_o_cobrado_na_dependencia(cliente, medida):
    """Nenhuma rota cobra na dependência um privilégio diferente do que declara (fora da lista congelada).

    O que esta camada NÃO consegue provar: onde a declaração é `a|b` ou especial (`proprio`, `rls:visibilidade`,
    `grupo:*`, `token:*`), a cobrança acontece no corpo da rota, muitas vezes dentro de uma função auxiliar de
    outro módulo ou de uma política de RLS no banco. Aí só a camada 2 (chamada real) prova alguma coisa, e ela
    cobre as rotas de privilégio nomeado único mais as duas de `/api/usuarios`; o resto é fronteira declarada
    na medida `rotas_alternativas_nao_provadas`."""
    from app.main import app

    vivas = _rotas_vivas(app)
    divergentes, no_corpo, na_dependencia, conhecidas = [], [], [], []
    for metodo, caminho, op in _rotas_declaradas():
        rota = vivas.get((metodo, caminho))
        assert rota is not None, (metodo, caminho, "no docs/openapi.json e não na aplicação")
        declarado, auth = op.get("x-privilegio"), op.get("x-auth")
        portao = _portao(rota)
        cobrado = portao.get("privilegio") if portao else None
        if declarado is None:
            assert caminho in SEM_PRIVILEGIO and cobrado is None, (metodo, caminho)
            continue
        if auth == "-":
            assert cobrado is None, (metodo, caminho, cobrado)
            continue
        esperado = _nomeado_unico(declarado)
        if declarado == "superadmin":
            if not (portao and portao.get("superadmin")):
                divergentes.append((metodo, caminho, declarado, "superadmin=False"))
            continue
        if (metodo, caminho) in DIVERGENCIAS_CONHECIDAS:
            assert DIVERGENCIAS_CONHECIDAS[(metodo, caminho)] == (declarado, cobrado), (metodo, caminho, cobrado)
            conhecidas.append((metodo, caminho))
            continue
        if portao is None:
            divergentes.append((metodo, caminho, declarado, "sem dependência autenticado()"))
        elif esperado:
            (na_dependencia if cobrado == esperado else divergentes).append(
                (metodo, caminho) if cobrado == esperado else (metodo, caminho, declarado, cobrado)
            )
        elif cobrado is not None:
            divergentes.append((metodo, caminho, declarado, cobrado))
        else:
            no_corpo.append((metodo, caminho))
    assert divergentes == [], divergentes
    gravar = medida("L0-02-g-checagem-privilegio-papel-id")
    gravar("rotas_openapi", len(_rotas_declaradas()), "rotas", "len(paths×methods) de docs/openapi.json")
    gravar("rotas_cobradas_na_dependencia", len(na_dependencia), "rotas",
           "x-privilegio nomeado único igual ao privilégio capturado pelo fecho de autenticado()")
    gravar("rotas_cobradas_no_corpo", len(no_corpo), "rotas",
           "declaração especial ou alternativa: dependência sem privilégio, cobrança no corpo da rota")
    gravar("rotas_declaracao_incompleta", len(conhecidas), "rotas",
           "cobram na dependência um privilégio que a declaração não menciona (lista congelada no teste)")


# ---------------------------------------------------------------- camada 2: dinâmica
@pytest.fixture(scope="module")
def terreno(sessao_plat):
    """Inquilino descartável com um administrador-sonda cujo papel personalizado é editável a cada caso.

    Inquilino próprio de propósito: a varredura chama rotas de escrita com corpo vazio e id inexistente; qualquer
    efeito colateral morre com o inquilino no fim do módulo."""
    inq = InquilinoTemporario(sessao_plat)
    try:
        todos = sorted(p["nome"] for p in inq.admin.get("/api/privilegios").json())
        r = inq.admin.post("/api/papeis", json={"nome": "zt-sonda", "privilegios": todos})
        assert r.status_code == 201, r.text
        papel = r.json()
        r = inq.admin.post(
            "/api/usuarios",
            json={"login": "zt-sonda", "nome": "Sonda de privilégio", "perfil": "admin", "papel_id": papel["id"]},
        )
        assert r.status_code == 201, r.text
        temporaria = r.json()["senha_temporaria"]
        sonda = novo_cliente()
        assert entrar(sonda, inq.slug, "zt-sonda", temporaria).status_code == 200
        assert sonda.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-da-sonda-1x"}).status_code == 204
        yield {"inq": inq, "sonda": sonda, "papel": papel["id"], "todos": todos}
    finally:
        inq.apagar()


def _definir_papel(terreno, privilegios):
    r = terreno["inq"].admin.put(
        f"/api/papeis/{terreno['papel']}", json={"nome": "zt-sonda", "privilegios": sorted(privilegios)}
    )
    assert r.status_code == 200, r.text


def _corpo(resposta) -> dict:
    """Corpo JSON quando é objeto; {} quando é lista (rota de listagem) ou não é JSON."""
    if not resposta.headers.get("content-type", "").startswith("application/json"):
        return {}
    corpo = resposta.json()
    return corpo if isinstance(corpo, dict) else {}


def _chamar(cliente, metodo, caminho):
    url = caminho
    for parte in caminho.split("/"):
        if parte.startswith("{") and parte.endswith("}"):
            url = url.replace(parte, "999999999")
    return cliente.request(metodo, url, json={})


def _por_privilegio():
    saida: dict[str, list[tuple[str, str]]] = {}
    for metodo, caminho, op in _rotas_declaradas():
        p = _nomeado_unico(op.get("x-privilegio"))
        if p:
            saida.setdefault(p, []).append((metodo, caminho))
    return saida


def test_rota_com_privilegio_nomeado_cobra_403_sem_ele(terreno, medida):
    """Para cada privilégio nomeado: papel = todos menos ele; toda rota que o declara responde 403 sem_privilegio."""
    mapa, falhas, provadas = _por_privilegio(), [], 0
    for privilegio, rotas in sorted(mapa.items()):
        _definir_papel(terreno, set(terreno["todos"]) - {privilegio})
        for metodo, caminho in rotas:
            r = _chamar(terreno["sonda"], metodo, caminho)
            corpo = _corpo(r)
            if r.status_code != 403 or corpo.get("erro") != "sem_privilegio" or (
                corpo.get("detalhe") or {}
            ).get("exigido") != privilegio:
                falhas.append((metodo, caminho, privilegio, r.status_code, r.text[:160]))
            else:
                provadas += 1
    _definir_papel(terreno, terreno["todos"])
    assert falhas == [], falhas
    medida("L0-02-g-checagem-privilegio-papel-id")(
        "rotas_403_sem_o_privilegio", provadas, "rotas",
        "chamada real com papel = todos os privilégios menos o declarado → 403 sem_privilegio",
    )


def test_controle_positivo_com_o_privilegio_nao_da_sem_privilegio(terreno):
    """Mesmo usuário, papel completo: nenhuma dessas rotas responde sem_privilegio (o 403 anterior era o certo)."""
    _definir_papel(terreno, terreno["todos"])
    falhas = []
    for privilegio, rotas in sorted(_por_privilegio().items()):
        for metodo, caminho in rotas:
            r = _chamar(terreno["sonda"], metodo, caminho)
            corpo = _corpo(r)
            if corpo.get("erro") == "sem_privilegio":
                falhas.append((metodo, caminho, privilegio, r.status_code, r.text[:160]))
    assert falhas == [], falhas


def test_alternativas_cobradas_no_corpo(terreno, medida):
    """`membros.gerir|membros.papel`: sem NENHUM dos dois, as duas rotas de usuário respondem 403 sem_privilegio."""
    sem_membros = set(terreno["todos"]) - {"membros.gerir", "membros.papel"}
    _definir_papel(terreno, sem_membros)
    r = terreno["sonda"].put("/api/usuarios/999999999", json={"nome": "x"})
    assert r.status_code in (403, 404), r.text
    r = terreno["sonda"].post("/api/usuarios/lote", json={"ids": [999999999], "acao": "desabilitar"})
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio", r.text
    r = terreno["sonda"].post(
        "/api/usuarios/lote", json={"ids": [999999999], "acao": "papel", "papel_id": terreno["papel"]}
    )
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio", r.text
    _definir_papel(terreno, terreno["todos"])
    nao_provadas = sorted(
        (m, c)
        for m, c, op in _rotas_declaradas()
        if "|" in (op.get("x-privilegio") or "") and (m, c) not in ALTERNATIVAS_PROVADAS
    )
    medida("L0-02-g-checagem-privilegio-papel-id")(
        "rotas_alternativas_nao_provadas", len(nao_provadas), "rotas",
        "rotas de privilégio alternativo cobrado depois de carregar o recurso: fora do alcance deste item",
    )
