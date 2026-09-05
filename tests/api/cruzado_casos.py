"""Casos da varredura cruzada A→B (ADR 0002 seção 16.1). Para CADA (método, caminho) do docs/openapi.json há um
caso que aponta um recurso do inquilino B (demo2) e diz o que A (demo) pode receber. Regra: o padrão aceito é
{401, 403, 404}; rota que age só sobre o próprio chamador (`proprio=True`) admite o seu 2xx, desde que a resposta
não carregue dado de B (`verificar`) e B fique intacto (digest antes/depois, em test_cruzado.py). Rota sem caso =
o teste falha (cobertura 100 % é cláusula)."""

import secrets
from dataclasses import dataclass, field
from typing import Any, Callable

PREFIXO = "zt-cruzado-"
PADRAO = frozenset({401, 403, 404})


@dataclass
class Caso:
    url: Callable[[Any], str]
    corpo: Callable[[Any], Any] = lambda p: None
    aceita: frozenset = PADRAO  # além de 401/403/404, o que A pode receber na chamada por sessão
    proprio: bool = False  # a rota age só sobre o chamador: o 2xx é admitido, com verificação
    publico: bool = False  # sem autenticação: as 4 chamadas recebem o mesmo conjunto
    descartavel: bool = False  # a chamada por sessão usa um cliente novo (logout derrubaria a sessão da suíte)
    verificar: Callable[[Any, Any], None] = lambda p, j: None  # (preparacao, json) → levanta se houver dado de B
    limpar: Callable[[Any, Any], None] = lambda p, j: None  # desfaz o que a chamada 2xx criou em A
    marcas: list = field(default_factory=list)


@dataclass
class Preparacao:
    """Recursos criados em B (demo2) antes da varredura; tudo é apagado no fim."""

    sessao_b: Any
    sessao_a: Any
    ids: dict
    inquilino_b: int
    usuario_b: dict
    grupo_b: dict
    papel_b: dict
    token_b: dict
    sessao_b_id: str
    criados_em_a: list = field(default_factory=list)

    @property
    def marcas_de_b(self) -> list[str]:
        """Strings que só existem em B: se aparecerem numa resposta de A, houve vazamento."""
        return [self.usuario_b["login"], self.grupo_b["nome"], self.papel_b["nome"], self.token_b["prefixo"], "demo2"]


def preparar(sessao_a, sessao_b, sessao_plat, ids) -> Preparacao:
    sufixo = secrets.token_hex(3)
    r = sessao_b.post(
        "/api/usuarios", json={"login": f"{PREFIXO}{sufixo}", "nome": f"{PREFIXO}usuario-{sufixo}", "perfil": "editor"}
    )
    assert r.status_code == 201, r.text
    usuario_b = r.json()["usuario"]
    r = sessao_b.post(
        "/api/grupos", json={"nome": f"{PREFIXO}grupo-{sufixo}", "visibilidade": "inquilino", "entrada": "pedido"}
    )
    assert r.status_code == 201, r.text
    grupo_b = r.json()
    assert (
        sessao_b.post(f"/api/grupos/{grupo_b['id']}/membros", json={"usuario_id": usuario_b["id"]}).status_code == 201
    )
    r = sessao_b.post("/api/papeis", json={"nome": f"{PREFIXO}papel-{sufixo}", "privilegios": ["conteudo.criar"]})
    assert r.status_code == 201, r.text
    papel_b = r.json()
    r = sessao_b.post("/api/tokens", json={"nome": f"{PREFIXO}token-{sufixo}", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    token_b = r.json()
    sessao_b_id = next(s["id"] for s in sessao_b.get("/api/eu/sessoes").json() if s["atual"])
    inquilino_b = next(t["id"] for t in sessao_plat.get("/api/plataforma/inquilinos").json() if t["slug"] == "demo2")
    return Preparacao(sessao_b, sessao_a, ids, inquilino_b, usuario_b, grupo_b, papel_b, token_b, sessao_b_id)


def desfazer(p: Preparacao) -> None:
    for metodo, url in reversed(p.criados_em_a):
        p.sessao_a.request(metodo, url)
    p.sessao_b.delete(f"/api/grupos/{p.grupo_b['id']}")
    p.sessao_b.delete(f"/api/tokens/{p.token_b['id']}")
    p.sessao_b.delete(f"/api/papeis/{p.papel_b['id']}")
    p.sessao_b.delete(f"/api/usuarios/{p.usuario_b['id']}")


def _sem_marca(p: Preparacao, j: Any) -> None:
    texto = str(j)
    for marca in p.marcas_de_b:
        assert marca not in texto, f"resposta de A carrega dado de B: {marca}"


def _so_a(p: Preparacao, j: Any) -> None:
    _sem_marca(p, j)
    if isinstance(j, dict) and "inquilino" in j:
        assert j["inquilino"]["slug"] == "demo"


def _lote_recusado(p: Preparacao, j: Any) -> None:
    assert j["alterados"] == 0 and [x["erro"] for x in j["recusados"]] == ["usuario_inexistente"], j


def _apagar_criado(metodo_url):
    """Rota de criação que age só em A: o recurso criado é apagado logo após a chamada (a chamada seguinte, por
    token, cria o mesmo nome de novo e não pode colidir)."""

    def limpar(p: Preparacao, j: Any) -> None:
        if isinstance(j, dict) and j.get("id") is not None:
            r = p.sessao_a.request(metodo_url[0], metodo_url[1].format(id=j["id"]))
            assert r.status_code in (204, 404), r.text

    return limpar


G = "/api/grupos/{id}"
U = "/api/usuarios/{id}"
T = "/api/tokens/{id}"
CASOS: dict[tuple[str, str], Caso] = {
    # ---- públicas (o caso prova que não devolvem dado de inquilino além do nome do próprio inquilino)
    ("GET", "/saude"): Caso(lambda p: "/saude", publico=True, aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/api/versao"): Caso(lambda p: "/api/versao", publico=True, aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/api/login/provedores"): Caso(
        lambda p: "/api/login/provedores?inquilino=demo2",
        publico=True,
        aceita=frozenset({200}),
        verificar=lambda p, j: [
            _sem_marca(p, {k: v for k, v in j.items() if k != "inquilino"}),
            (lambda: (_ for _ in ()).throw(AssertionError(j)))() if set(j["inquilino"]) != {"slug", "nome"} else None,
        ],
    ),
    ("POST", "/api/login"): Caso(
        lambda p: "/api/login",
        lambda p: {"inquilino": "demo2", "login": p.usuario_b["login"], "senha": "Senha-errada-1"},
        publico=True,
    ),
    ("POST", "/api/login/2fa"): Caso(
        lambda p: "/api/login/2fa",
        lambda p: {"desafio": "f" * 64, "codigo": "000000"},
        publico=True,
        aceita=frozenset({401, 410}),
    ),
    ("POST", "/api/logout"): Caso(lambda p: "/api/logout", publico=True, aceita=frozenset({204}), descartavel=True),
    # ---- /api/eu: age só sobre o chamador
    ("GET", "/api/eu"): Caso(lambda p: "/api/eu", proprio=True, aceita=frozenset({200}), verificar=_so_a),
    ("PUT", "/api/eu"): Caso(
        lambda p: "/api/eu",
        lambda p: {"nome": p.usuario_b["nome"]},
        proprio=True,
        aceita=frozenset({200}),
        verificar=lambda p, j: _so_a(p, {k: v for k, v in j.items() if k != "nome"}),
        limpar=lambda p, j: p.sessao_a.put("/api/eu", json={"nome": p.ids["a"]["nome"]}),
    ),
    ("PUT", "/api/eu/senha"): Caso(lambda p: "/api/eu/senha", lambda p: {"atual": "errada", "nova": "Xx-12345678"}),
    ("GET", "/api/eu/sessoes"): Caso(
        lambda p: "/api/eu/sessoes", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("DELETE", "/api/eu/sessoes"): Caso(lambda p: "/api/eu/sessoes?outras=0", aceita=frozenset({400})),
    ("DELETE", "/api/eu/sessoes/{id}"): Caso(lambda p: f"/api/eu/sessoes/{p.sessao_b_id}"),
    ("POST", "/api/eu/2fa/iniciar"): Caso(
        lambda p: "/api/eu/2fa/iniciar", lambda p: {}, proprio=True, aceita=frozenset({200, 409}), verificar=_sem_marca
    ),
    ("POST", "/api/eu/2fa/confirmar"): Caso(
        lambda p: "/api/eu/2fa/confirmar", lambda p: {"codigo": "000000"}, aceita=frozenset({401, 409})
    ),
    ("POST", "/api/eu/2fa/desativar"): Caso(
        lambda p: "/api/eu/2fa/desativar", lambda p: {"senha": "x", "codigo": "000000"}, aceita=frozenset({401, 409})
    ),
    ("POST", "/api/eu/2fa/codigos"): Caso(
        lambda p: "/api/eu/2fa/codigos", lambda p: {"senha": "x"}, aceita=frozenset({401, 409})
    ),
    ("GET", "/api/eu/convites"): Caso(
        lambda p: "/api/eu/convites", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    # ---- vocabulário e papéis
    ("GET", "/api/privilegios"): Caso(
        lambda p: "/api/privilegios", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("GET", "/api/papeis"): Caso(lambda p: "/api/papeis", proprio=True, aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/papeis"): Caso(
        lambda p: "/api/papeis",
        lambda p: {"nome": p.papel_b["nome"], "privilegios": ["conteudo.criar"]},
        proprio=True,
        aceita=frozenset({201}),
        verificar=lambda p, j: None,
        limpar=_apagar_criado(("DELETE", "/api/papeis/{id}")),
    ),
    ("PUT", "/api/papeis/{id}"): Caso(
        lambda p: f"/api/papeis/{p.papel_b['id']}", lambda p: {"nome": "x", "privilegios": ["conteudo.criar"]}
    ),
    ("DELETE", "/api/papeis/{id}"): Caso(lambda p: f"/api/papeis/{p.papel_b['id']}"),
    # ---- usuários
    ("GET", "/api/usuarios"): Caso(
        lambda p: f"/api/usuarios?q={PREFIXO}", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("POST", "/api/usuarios"): Caso(
        lambda p: "/api/usuarios",
        lambda p: {"login": f"{PREFIXO}novo", "nome": "x", "perfil": "editor", "papel_id": p.papel_b["id"]},
    ),
    ("POST", "/api/usuarios/lote"): Caso(
        lambda p: "/api/usuarios/lote",
        lambda p: {"ids": [p.usuario_b["id"]], "acao": "desabilitar"},
        proprio=True,
        aceita=frozenset({200}),
        verificar=_lote_recusado,
    ),
    ("GET", U): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}"),
    ("PUT", U): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}", lambda p: {"nome": "invadido"}),
    ("DELETE", U): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}"),
    ("POST", U + "/senha"): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}/senha"),
    ("POST", U + "/2fa/desativar"): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}/2fa/desativar"),
    ("POST", U + "/desbloquear"): Caso(lambda p: f"/api/usuarios/{p.usuario_b['id']}/desbloquear"),
    # ---- grupos
    ("GET", "/api/grupos"): Caso(
        lambda p: f"/api/grupos?q={PREFIXO}", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("POST", "/api/grupos"): Caso(
        lambda p: "/api/grupos",
        lambda p: {"nome": p.grupo_b["nome"]},
        proprio=True,
        aceita=frozenset({201}),
        verificar=lambda p, j: None,
        limpar=_apagar_criado(("DELETE", "/api/grupos/{id}")),
    ),
    ("GET", G): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}"),
    ("PUT", G): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}", lambda p: {"nome": "invadido"}),
    ("DELETE", G): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}"),
    ("GET", G + "/membros"): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}/membros"),
    ("POST", G + "/membros"): Caso(
        lambda p: f"/api/grupos/{p.grupo_b['id']}/membros", lambda p: {"usuario_id": p.ids["a"]["id"]}
    ),
    ("POST", G + "/entrar"): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}/entrar"),
    ("POST", G + "/aceitar"): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}/aceitar"),
    ("POST", G + "/recusar"): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}/recusar"),
    ("POST", G + "/membros/{uid}/aprovar"): Caso(
        lambda p: f"/api/grupos/{p.grupo_b['id']}/membros/{p.usuario_b['id']}/aprovar"
    ),
    ("PUT", G + "/membros/{uid}"): Caso(
        lambda p: f"/api/grupos/{p.grupo_b['id']}/membros/{p.usuario_b['id']}", lambda p: {"papel": "gerente"}
    ),
    ("DELETE", G + "/membros/{uid}"): Caso(lambda p: f"/api/grupos/{p.grupo_b['id']}/membros/{p.usuario_b['id']}"),
    # ---- tokens (S: sob token = 403 so_sessao)
    ("GET", "/api/tokens"): Caso(
        lambda p: "/api/tokens?todos=1", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("POST", "/api/tokens"): Caso(
        lambda p: "/api/tokens",
        lambda p: {"nome": p.token_b["prefixo"], "escopos": ["catalogo:ler"]},
        proprio=True,
        aceita=frozenset({201}),
        verificar=lambda p, j: None,
        limpar=_apagar_criado(("DELETE", "/api/tokens/{id}")),
    ),
    ("GET", T): Caso(lambda p: f"/api/tokens/{p.token_b['id']}"),
    ("DELETE", T): Caso(lambda p: f"/api/tokens/{p.token_b['id']}"),
    ("POST", T + "/renovar"): Caso(lambda p: f"/api/tokens/{p.token_b['id']}/renovar"),
    ("GET", T + "/log"): Caso(lambda p: f"/api/tokens/{p.token_b['id']}/log"),
    # ---- log e eventos
    ("GET", "/api/log"): Caso(
        lambda p: f"/api/log?usuario_id={p.usuario_b['id']}&limite=50",
        proprio=True,
        aceita=frozenset({200}),
        verificar=lambda p, j: [_sem_marca(p, j), _zero(j)],
    ),
    ("GET", "/api/eventos"): Caso(
        lambda p: f"/api/eventos?ator_id={p.usuario_b['id']}&limite=50",
        proprio=True,
        aceita=frozenset({200}),
        verificar=lambda p, j: [_sem_marca(p, j), _zero(j)],
    ),
    # ---- plataforma: 404 para quem não é superadmin
    ("GET", "/api/plataforma/inquilinos"): Caso(lambda p: "/api/plataforma/inquilinos"),
    ("POST", "/api/plataforma/inquilinos"): Caso(
        lambda p: "/api/plataforma/inquilinos",
        lambda p: {"slug": "zt-invasao", "nome": "x", "admin_login": "a", "admin_nome": "A"},
    ),
    ("POST", "/api/plataforma/inquilinos/{id}/suspender"): Caso(
        lambda p: f"/api/plataforma/inquilinos/{p.inquilino_b}/suspender"
    ),
    ("POST", "/api/plataforma/inquilinos/{id}/reativar"): Caso(
        lambda p: f"/api/plataforma/inquilinos/{p.inquilino_b}/reativar"
    ),
}


def _zero(j: Any) -> None:
    assert j["total"] == 0 and j["itens"] == [], "A vê linhas de log/evento de um usuário de B"
