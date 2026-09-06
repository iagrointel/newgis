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
    job_b: dict = field(default_factory=dict)  # job pendente de B (L0-05; agendado para 2099, nunca roda)
    agenda_b: dict = field(default_factory=dict)  # agenda de B (L0-05)
    item_b: dict = field(default_factory=dict)  # L0-03: item de B (mapa privado do admin de B)
    pasta_b: dict = field(default_factory=dict)  # L0-03: pasta de B
    link_b: dict = field(default_factory=dict)  # L0-03: link por token de B (token em claro só aqui)
    categoria_b: dict = field(default_factory=dict)  # L0-03: categoria de B
    fonte_acervo: str = ""  # L6-01-a: fonte do acervo com licença escrita (compartilhada, não é de A nem de B)

    @property
    def marcas_de_b(self) -> list[str]:
        """Strings que só existem em B: se aparecerem numa resposta de A, houve vazamento."""
        marcas = [self.usuario_b["login"], self.grupo_b["nome"], self.papel_b["nome"], self.token_b["prefixo"], "demo2"]
        if self.item_b:
            marcas += [self.item_b["titulo"], self.pasta_b["nome"]]
        return marcas


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
    # L0-05: um job pendente e uma agenda em B, alvos das 17 rotas de /api/jobs e /api/agendas
    r = sessao_b.post("/api/jobs", json=JOB_PENDENTE)
    assert r.status_code == 201, r.text
    job_b = r.json()
    r = sessao_b.post("/api/agendas", json={**AGENDA_BASE, "nome": f"{PREFIXO}agenda-{sufixo}"})
    assert r.status_code == 201, r.text
    agenda_b = r.json()
    # L0-03: item, pasta, link e categoria de B, alvos das rotas do catálogo
    r = sessao_b.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO}item-{sufixo}",
                                          "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    item_b = r.json()
    r = sessao_b.post("/api/pastas", json={"nome": f"{PREFIXO}pasta-{sufixo}"})
    assert r.status_code == 201, r.text
    pasta_b = r.json()
    r = sessao_b.post(f"/api/itens/{item_b['id']}/links", json={"nome": f"{PREFIXO}link"})
    assert r.status_code == 201, r.text
    link_b = r.json()
    arvore = sessao_b.get("/api/categorias").json()["arvore"]
    r = sessao_b.put("/api/categorias", json={"arvore": [_no_categoria(n) for n in arvore]
                                               + [{"nome": f"{PREFIXO}cat-{sufixo}", "filhas": []}]})
    assert r.status_code == 200, r.text
    categoria_b = r.json()["arvore"][-1]
    # L6-01-a: acervo é registro compartilhado (não pertence a A nem a B); só precisa de UMA fonte com licença
    # escrita (regra D17) para os casos de GET/POST — qualquer sessão vê a mesma lista.
    r = sessao_a.get("/api/acervo?limite=1")
    assert r.status_code == 200, r.text
    fonte_acervo = r.json()["itens"][0]["fonte_id"]
    return Preparacao(sessao_b, sessao_a, ids, inquilino_b, usuario_b, grupo_b, papel_b, token_b, sessao_b_id,
                      job_b=job_b, agenda_b=agenda_b, item_b=item_b, pasta_b=pasta_b, link_b=link_b,
                      categoria_b=categoria_b, fonte_acervo=fonte_acervo)


def _no_categoria(no: dict) -> dict:
    return {"id": no["id"], "nome": no["nome"], "codigo": no.get("codigo"),
            "filhas": [_no_categoria(f) for f in no.get("filhas", [])]}


def desfazer(p: Preparacao) -> None:
    for metodo, url in reversed(p.criados_em_a):
        p.sessao_a.request(metodo, url)
    if p.job_b:
        p.sessao_b.post(f"/api/jobs/{p.job_b['id']}/cancelar")
    if p.categoria_b:
        arvore = p.sessao_b.get("/api/categorias").json()["arvore"]
        restante = [_no_categoria(n) for n in arvore if n["id"] != p.categoria_b["id"]]
        p.sessao_b.put("/api/categorias", json={"arvore": restante})
    if p.item_b:
        p.sessao_b.put(f"/api/itens/{p.item_b['id']}", json={"protegido": False})
        p.sessao_b.delete(f"/api/itens/{p.item_b['id']}?cascata=true")
    if p.pasta_b:
        p.sessao_b.delete(f"/api/pastas/{p.pasta_b['id']}")
    if p.agenda_b:
        p.sessao_b.delete(f"/api/agendas/{p.agenda_b['id']}")
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


def _apagar_arquivo(p: Preparacao, j: Any) -> None:
    """POST /api/arquivos devolve sha256, não id: apaga pela mesma classe usada no upload (limites.py)."""
    if isinstance(j, dict) and j.get("sha256"):
        r = p.sessao_a.delete(f"/api/arquivos/{j['sha256']}")
        assert r.status_code in (204, 404), r.text


JOB_PENDENTE = {"tipo": "prova.progresso", "parametros": {"duracao_s": 0, "passos": 1},
                "agendado_para": "2099-01-01T00:00:00Z"}  # fica pendente: nunca ocupa o worker
AGENDA_BASE = {"tipo": "prova.progresso", "parametros": {"duracao_s": 0, "passos": 1}, "cron": "0 3 1 1 *"}


def _cancelar_criado(p: Preparacao, j: Any) -> None:
    """Job criado em A pela chamada 2xx: cancelado logo depois (202) para não sobrar pendente."""
    if isinstance(j, dict) and j.get("id") is not None:
        r = p.sessao_a.post(f"/api/jobs/{j['id']}/cancelar")
        assert r.status_code in (202, 404, 409), r.text


G = "/api/grupos/{id}"
J = "/api/jobs/{job_id}"
AG = "/api/agendas/{agenda_id}"
U = "/api/usuarios/{id}"
T = "/api/tokens/{id}"
IT = "/api/itens/{id}"  # L0-03
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
    ("DELETE", "/api/plataforma/inquilinos/{id}"): Caso(lambda p: f"/api/plataforma/inquilinos/{p.inquilino_b}"),
    ("POST", "/api/plataforma/inquilinos/{id}/reativar"): Caso(
        lambda p: f"/api/plataforma/inquilinos/{p.inquilino_b}/reativar"
    ),
    # ---- L0-05 fila de jobs: leituras e criação agem só no chamador (RLS + filtro de dono); alvos de B = 404
    ("GET", "/api/jobs"): Caso(
        lambda p: "/api/jobs?limite=5", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("GET", "/api/jobs/resumo"): Caso(
        lambda p: "/api/jobs/resumo", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("GET", "/api/jobs/tipos"): Caso(
        lambda p: "/api/jobs/tipos", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("POST", "/api/jobs"): Caso(
        lambda p: "/api/jobs", lambda p: JOB_PENDENTE, proprio=True, aceita=frozenset({201}), verificar=_so_a,
        limpar=_cancelar_criado,
    ),
    ("GET", J): Caso(lambda p: f"/api/jobs/{p.job_b['id']}"),
    ("POST", J + "/cancelar"): Caso(lambda p: f"/api/jobs/{p.job_b['id']}/cancelar"),
    ("POST", J + "/repetir"): Caso(
        lambda p: f"/api/jobs/{p.job_b['id']}/repetir", lambda p: {"parametros": {"passos": 2}}
    ),
    ("GET", J + "/log"): Caso(lambda p: f"/api/jobs/{p.job_b['id']}/log"),
    ("GET", J + "/eventos"): Caso(lambda p: f"/api/jobs/{p.job_b['id']}/eventos"),
    ("GET", "/api/agendas"): Caso(
        lambda p: "/api/agendas", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("POST", "/api/agendas"): Caso(
        lambda p: "/api/agendas",
        lambda p: {**AGENDA_BASE, "nome": f"{PREFIXO}agenda-a-{secrets.token_hex(3)}"},
        proprio=True,
        aceita=frozenset({201}),
        verificar=_so_a,
        limpar=_apagar_criado(("DELETE", "/api/agendas/{id}")),
    ),
    ("GET", AG): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}"),
    ("PUT", AG): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}", lambda p: {"nome": "invadido"}),
    ("DELETE", AG): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}"),
    ("POST", AG + "/pausar"): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}/pausar"),
    ("POST", AG + "/retomar"): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}/retomar"),
    ("POST", AG + "/rodar-agora"): Caso(lambda p: f"/api/agendas/{p.agenda_b['id']}/rodar-agora"),
    # ---- L0-03 catálogo: alvos de B = 404 (não 403: não confirma existência); leituras de lista agem só no chamador
    ("GET", "/api/tipos-item"): Caso(lambda p: "/api/tipos-item", proprio=True, aceita=frozenset({200}),
                                     verificar=_sem_marca),
    # ---- L6-01-a acervo da casa: registro compartilhado (não é de A nem de B); só fonte com licença escrita
    # aparece (regra D17); "adicionar" cria item SÓ no inquilino do chamador (mesma trava do resto do catálogo)
    ("GET", "/api/acervo"): Caso(lambda p: "/api/acervo?limite=5", proprio=True, aceita=frozenset({200}),
                                 verificar=_sem_marca),
    ("GET", "/api/acervo/{fonte_id}"): Caso(lambda p: f"/api/acervo/{p.fonte_acervo}", proprio=True,
                                            aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/acervo/{fonte_id}/adicionar"): Caso(
        lambda p: f"/api/acervo/{p.fonte_acervo}/adicionar", proprio=True, aceita=frozenset({201}),
        verificar=_sem_marca, limpar=_apagar_criado(("DELETE", "/api/itens/{id}")),
    ),
    ("GET", "/api/itens"): Caso(lambda p: f"/api/itens?q=id:{p.item_b['id']}", proprio=True, aceita=frozenset({200}),
                                verificar=lambda p, j: [_sem_marca(p, j), _zero(j)]),
    ("GET", "/api/itens/facetas"): Caso(lambda p: f"/api/itens/facetas?q=id:{p.item_b['id']}", proprio=True,
                                        aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/api/itens/tags"): Caso(lambda p: f"/api/itens/tags?q={PREFIXO}", proprio=True, aceita=frozenset({200}),
                                     verificar=_sem_marca),
    ("POST", "/api/itens"): Caso(
        lambda p: "/api/itens",
        lambda p: {"tipo": "mapa", "titulo": f"{PREFIXO}novo", "pasta_id": p.pasta_b["id"],
                   "dados": {"esquema_versao": 1, "corpo": {}}},
    ),
    ("POST", "/api/itens/lote"): Caso(
        lambda p: "/api/itens/lote", lambda p: {"ids": [p.item_b["id"]], "acao": "proteger"}, proprio=True,
        aceita=frozenset({200}), verificar=lambda p, j: _lote_itens_recusado(p, j),
    ),
    ("POST", "/api/itens/transferir"): Caso(
        lambda p: "/api/itens/transferir",
        lambda p: {"ids": [p.item_b["id"]], "novo_dono_id": p.ids["a"]["id"], "simular": True},
    ),
    ("GET", IT): Caso(lambda p: f"/api/itens/{p.item_b['id']}"),
    ("PUT", IT): Caso(lambda p: f"/api/itens/{p.item_b['id']}", lambda p: {"titulo": "invadido"}),
    ("PATCH", IT): Caso(lambda p: f"/api/itens/{p.item_b['id']}", lambda p: {"titulo": "invadido"}),
    ("DELETE", IT): Caso(lambda p: f"/api/itens/{p.item_b['id']}"),
    ("POST", IT + "/mover"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/mover", lambda p: {"pasta_id": None}),
    ("GET", IT + "/miniatura"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/miniatura"),
    ("POST", IT + "/miniatura"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/miniatura",
                                      lambda p: {"conteudo": "AAAA"}),
    ("POST", IT + "/miniatura/gerar"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/miniatura/gerar"),
    ("DELETE", IT + "/miniatura"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/miniatura"),
    ("GET", IT + "/versoes"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/versoes"),
    ("GET", IT + "/versoes/{n}"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/versoes/1"),
    ("POST", IT + "/versoes/{n}/restaurar"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/versoes/1/restaurar",
                                                  lambda p: {}),
    ("POST", IT + "/versoes/{n}/publicar"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/versoes/1/publicar"),
    ("GET", IT + "/usado-por"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/usado-por"),
    ("GET", IT + "/criado-a-partir-de"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/criado-a-partir-de"),
    ("GET", IT + "/ordem-de-exclusao"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/ordem-de-exclusao"),
    ("PUT", IT + "/relacoes"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/relacoes", lambda p: {"relacoes": []}),
    ("GET", IT + "/compartilhamento"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/compartilhamento"),
    ("PUT", IT + "/compartilhamento"): Caso(
        lambda p: f"/api/itens/{p.item_b['id']}/compartilhamento",
        lambda p: {"acesso": "inquilino", "grupos": [p.grupo_b["id"]]},
    ),
    ("POST", IT + "/links"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/links", lambda p: {"nome": "x"}),
    ("GET", IT + "/links"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/links"),
    ("DELETE", IT + "/links/{lid}"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/links/{p.link_b['id']}"),
    # link é anônimo por desenho: a sessão de A não ganha nada além do link (o item vem sem dono.login e sem pode_*)
    ("GET", "/api/compartilhado/{token}"): Caso(
        lambda p: f"/api/compartilhado/{p.link_b['token']}", publico=True, aceita=frozenset({200}),
        verificar=lambda p, j: _link_so_o_item(p, j),
    ),
    ("GET", "/api/compartilhado/{token}/itens/{id}"): Caso(
        lambda p: f"/api/compartilhado/{p.link_b['token']}/itens/{p.item_b['id']}", publico=True,
        aceita=frozenset({200}),
        verificar=lambda p, j: _link_so_o_item(p, {"item": j}),
    ),
    ("GET", "/api/compartilhado/{token}/itens/{id}/miniatura"): Caso(
        lambda p: f"/api/compartilhado/{p.link_b['token']}/itens/{p.item_b['id']}/miniatura", publico=True,
        aceita=frozenset({204}),
    ),
    # público: o inquilino B não liga compartilhar_publico → 404 sempre
    ("GET", "/api/publico/itens/{id}"): Caso(lambda p: f"/api/publico/itens/{p.item_b['id']}", publico=True),
    ("GET", "/api/publico/itens/{id}/miniatura"): Caso(lambda p: f"/api/publico/itens/{p.item_b['id']}/miniatura",
                                                       publico=True),
    ("GET", "/api/objetos/{chave}"): Caso(
        lambda p: f"/api/objetos/miniatura/{p.item_b['id']}/{'0' * 64}.png?ate=1&assinatura=x", publico=True
    ),
    # pastas, categorias, favoritos, lixeira
    ("GET", "/api/pastas"): Caso(lambda p: f"/api/pastas?pai_id={p.pasta_b['id']}", proprio=True,
                                 aceita=frozenset({200}), verificar=lambda p, j: [_sem_marca(p, j), _vazio(j)]),
    ("GET", "/api/pastas/arvore"): Caso(lambda p: "/api/pastas/arvore", proprio=True, aceita=frozenset({200}),
                                        verificar=_sem_marca),
    ("POST", "/api/pastas"): Caso(lambda p: "/api/pastas",
                                  lambda p: {"nome": f"{PREFIXO}nova", "pai_id": p.pasta_b["id"]}),
    ("PUT", "/api/pastas/{id}"): Caso(lambda p: f"/api/pastas/{p.pasta_b['id']}", lambda p: {"nome": "invadida"}),
    ("DELETE", "/api/pastas/{id}"): Caso(lambda p: f"/api/pastas/{p.pasta_b['id']}"),
    ("GET", "/api/categorias"): Caso(lambda p: "/api/categorias", proprio=True, aceita=frozenset({200}),
                                     verificar=_sem_marca),
    ("PUT", "/api/categorias"): Caso(
        lambda p: "/api/categorias",
        lambda p: {"arvore": [{"id": p.categoria_b["id"], "nome": "invadida", "filhas": []}]},
    ),
    ("POST", "/api/categorias/importar"): Caso(
        lambda p: "/api/categorias/importar", lambda p: {"modelo": "iso19115"}, proprio=True, aceita=frozenset({200}),
        verificar=_sem_marca,
    ),
    ("GET", "/api/favoritos"): Caso(lambda p: f"/api/favoritos?q=id:{p.item_b['id']}", proprio=True,
                                    aceita=frozenset({200}), verificar=lambda p, j: [_sem_marca(p, j), _zero(j)]),
    ("PUT", "/api/favoritos/{item_id}"): Caso(lambda p: f"/api/favoritos/{p.item_b['id']}"),
    ("DELETE", "/api/favoritos/{item_id}"): Caso(lambda p: f"/api/favoritos/{p.item_b['id']}", proprio=True,
                                                 aceita=frozenset({204})),
    ("GET", "/api/lixeira"): Caso(lambda p: f"/api/lixeira?q=id:{p.item_b['id']}", proprio=True,
                                  aceita=frozenset({200}), verificar=lambda p, j: [_sem_marca(p, j), _zero(j)]),
    ("POST", "/api/lixeira/{id}/restaurar"): Caso(lambda p: f"/api/lixeira/{p.item_b['id']}/restaurar"),
    ("POST", "/api/lixeira/esvaziar"): Caso(
        lambda p: "/api/lixeira/esvaziar", lambda p: {"ids": [p.item_b["id"]]}, proprio=True, aceita=frozenset({202}),
        verificar=_sem_marca, limpar=lambda p, j: p.sessao_a.post(f"/api/jobs/{j['job_id']}/cancelar"),
    ),
    # ---- arquivos/objetos (L0-11): a rota nunca recebe id de inquilino na URL (o bucket vem do auth.tenant_id),
    # então "o recurso de B" para GET/DELETE por sha256 é qualquer sha256 que A também não tem — 404 garantido
    # sem precisar upar nada como B (a suíte própria do item, tests/api/test_arquivos.py, prova o isolamento com
    # objeto REAL dos dois lados). POST/GET/_varredura agem só sobre o inquilino do chamador (proprio=True).
    ("POST", "/api/arquivos"): Caso(
        lambda p: "/api/arquivos", lambda p: {"conteudo": "zt-cruzado"}, proprio=True, aceita=frozenset({201}),
        verificar=_sem_marca, limpar=_apagar_arquivo,
    ),
    ("GET", "/api/arquivos"): Caso(lambda p: "/api/arquivos", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("GET", "/api/arquivos/_varredura"): Caso(lambda p: "/api/arquivos/_varredura", proprio=True,
                                               aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/api/arquivos/{sha256}"): Caso(lambda p: f"/api/arquivos/{'0' * 64}?classe=zt_cruzado"),
    ("DELETE", "/api/arquivos/{sha256}"): Caso(lambda p: f"/api/arquivos/{'0' * 64}?classe=zt_cruzado"),
}


def _zero(j: Any) -> None:
    assert j["total"] == 0 and j["itens"] == [], "A vê linhas de log/evento de um usuário de B"


def _vazio(j: Any) -> None:
    assert j == [], "A vê pastas de B"


def _lote_itens_recusado(p: Preparacao, j: Any) -> None:
    assert j["feitos"] == 0 and [x["erro"] for x in j["recusados"]] == ["item_inexistente"], j


def _link_so_o_item(p: Preparacao, j: Any) -> None:
    """Pelo link vê-se só o item incluído: sem login do dono, sem pode_*, sem slug do inquilino, sem outras marcas."""
    item = j["item"]
    assert "login" not in item["dono"] and "pode_editar" not in item and item["id"] == p.item_b["id"]
    for marca in (p.usuario_b["login"], p.grupo_b["nome"], p.papel_b["nome"], p.token_b["prefixo"], "demo2"):
        assert marca not in str(j), marca
