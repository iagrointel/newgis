"""Casos da varredura cruzada A→B (ADR 0002 seção 16.1). Para CADA (método, caminho) do docs/openapi.json há um
caso que aponta um recurso do inquilino B (demo2) e diz o que A (demo) pode receber. Regra: o padrão aceito é
{401, 403, 404}; rota que age só sobre o próprio chamador (`proprio=True`) admite o seu 2xx, desde que a resposta
não carregue dado de B (`verificar`) e B fique intacto (digest antes/depois, em test_cruzado.py). Rota sem caso =
o teste falha (cobertura 100 % é cláusula)."""

import json
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable

from app.rede_utilidades import instalados

PREFIXO = "zt-cruzado-"
# L6-02-a: dado aberto federal (IBGE), nunca nome de cliente/parceiro; passa pela defesa de SSRF na criação
URL_CONEXAO_TESTE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"
# L3-19-multiescala: polígono pequeno dentro da cobertura SIRGAS 2000 UTM (zona 23S), perto de São Paulo
AREA_MULTIESCALA_TESTE = {
    "type": "Polygon",
    "coordinates": [[[-46.61, -23.51], [-46.59, -23.51], [-46.59, -23.49], [-46.61, -23.49], [-46.61, -23.51]]],
}
PADRAO = frozenset({401, 403, 404})
UUID_NULO = "00000000-0000-0000-0000-000000000000"  # id que não é de A nem de B: 404 garantido pela RLS/dono


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
    conexao_b: dict = field(default_factory=dict)  # L6-02-a: conexão externa de B
    rede_b: dict = field(default_factory=dict)  # L4-01-a: rede de utilidades de B, com pacote de ativos importado
    convite_b: dict = field(default_factory=dict)  # L0-07-d: convite pendente de B
    conjunto_b: dict = field(default_factory=dict)  # L3-19-multiescala: área de estudo de B
    fator_b: dict = field(default_factory=dict)  # L3-19-multiescala: fator de B
    execucao_b: dict = field(default_factory=dict)  # L3-19-multiescala: execução macro de B (sobre conjunto_b)

    @property
    def marcas_de_b(self) -> list[str]:
        """Strings que só existem em B: se aparecerem numa resposta de A, houve vazamento."""
        marcas = [self.usuario_b["login"], self.grupo_b["nome"], self.papel_b["nome"], self.token_b["prefixo"], "demo2"]
        if self.item_b:
            marcas += [self.item_b["titulo"], self.pasta_b["nome"]]
        if self.conexao_b:
            marcas.append(self.conexao_b["nome"])
        if self.rede_b:
            marcas.append(self.rede_b["nome"])
        if self.convite_b:
            marcas.append(self.convite_b["email"])
        if self.conjunto_b:
            marcas += [self.conjunto_b["nome"], self.fator_b["nome"]]
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
    # L0-07-d: convite pendente de B, alvo das rotas de /api/convites (resolver/aceitar são por TOKEN secreto,
    # não por id — usar o token real de B mutaria B ao aceitar, então essas duas usam token forjado, não este)
    r = sessao_b.post("/api/convites", json={"email": f"{PREFIXO}convite-{sufixo}@teste.exemplo", "perfil": "editor"})
    assert r.status_code == 201, r.text
    convite_b = r.json()
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
    # L6-02-a: conexão externa de B, alvo das rotas de /api/conexoes (URL pública real — passa pela defesa de
    # SSRF na criação; dado aberto federal, nunca nome de cliente/parceiro)
    r = sessao_b.post(
        "/api/conexoes",
        json={"tipo": "ogc_api", "nome": f"{PREFIXO}conexao-{sufixo}", "url": URL_CONEXAO_TESTE},
    )
    assert r.status_code == 201, r.text
    conexao_b = r.json()
    # L4-01-a: rede de utilidades de B com o pacote de ativos JÁ importado — é o alvo das rotas /api/rede/{rede_id}
    # (inclusive a exportação, que é onde um vazamento de esquema apareceria)
    r = sessao_b.post("/api/rede", json={"nome": f"{PREFIXO}rede-{sufixo}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rede_b = r.json()
    r = sessao_b.post(f"/api/rede/{rede_b['id']}/pacote", content=instalados.bruto("agua-epanet"),
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    # L3-19-multiescala: conjunto + fator + execução macro de B (sem amostra: 0 aprovadas, mas a execução
    # existe de verdade para os casos GET/POST cross-tenant de /execucoes e /execucoes/{id}/micro)
    r = sessao_b.post("/api/multiescala/conjuntos",
                      json={"nome": f"{PREFIXO}conjunto-{sufixo}", "area": AREA_MULTIESCALA_TESTE})
    assert r.status_code == 201, r.text
    conjunto_b = r.json()
    r = sessao_b.post("/api/multiescala/fatores",
                      json={"nome": f"{PREFIXO}fator-{sufixo}", "resolucao_fonte_m": 100.0, "papel": "atrai"})
    assert r.status_code == 201, r.text
    fator_b = r.json()
    r = sessao_b.post(f"/api/multiescala/conjuntos/{conjunto_b['id']}/macro", json={
        "resolucao_m": 1000.0, "fatores": [{"fator_id": fator_b["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r.status_code == 201, r.text
    execucao_b = r.json()
    return Preparacao(sessao_b, sessao_a, ids, inquilino_b, usuario_b, grupo_b, papel_b, token_b, sessao_b_id,
                      job_b=job_b, agenda_b=agenda_b, item_b=item_b, pasta_b=pasta_b, link_b=link_b,
                      categoria_b=categoria_b, fonte_acervo=fonte_acervo, conexao_b=conexao_b,
                      convite_b=convite_b, rede_b=rede_b,
                      conjunto_b=conjunto_b, fator_b=fator_b, execucao_b=execucao_b)


def _no_categoria(no: dict) -> dict:
    return {"id": no["id"], "nome": no["nome"], "codigo": no.get("codigo"),
            "filhas": [_no_categoria(f) for f in no.get("filhas", [])]}


def desfazer(p: Preparacao) -> None:
    for metodo, url in reversed(p.criados_em_a):
        p.sessao_a.request(metodo, url)
    if p.convite_b:
        p.sessao_b.delete(f"/api/convites/{p.convite_b['id']}")
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
    if p.rede_b:
        p.sessao_b.delete(f"/api/rede/{p.rede_b['id']}")
    if p.conexao_b:
        p.sessao_b.delete(f"/api/conexoes/{p.conexao_b['id']}")
    if p.conjunto_b:
        p.sessao_b.delete(f"/api/multiescala/conjuntos/{p.conjunto_b['id']}")  # cascata apaga a execução também
        p.sessao_b.delete(f"/api/multiescala/fatores/{p.fator_b['id']}")
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


# ---- L0-07-a-configuracoes-org
_PNG_1X1_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def _corpo_org_atual(p: Preparacao) -> dict:
    """PUT /api/org é full-replace (mesmo contrato do PUT /api/org/ldap): eco do último GET de A, sem
    mudar nada — a varredura cruzada só precisa provar que a rota não enxerga nem altera B."""
    org = p.sessao_a.get("/api/org").json()
    return {
        "nome": org["nome"], "cor": org["cor"], "idioma_padrao": org["idioma_padrao"],
        "centro": org["mapa"]["centro"], "zoom": org["mapa"]["zoom"], "basemap": org["mapa"]["basemap"],
        "srid_padrao": org["mapa"]["srid_padrao"], "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"], "auth": dict(org["auth"]),
    }


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
    # ---- L0-02-g-perfil-usuario: foto de perfil, mesmo padrão do POST/DELETE /api/org/logo acima
    ("POST", "/api/eu/foto"): Caso(
        lambda p: "/api/eu/foto",
        lambda p: {"conteudo": _PNG_1X1_B64},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
        limpar=lambda p, j: p.sessao_a.delete("/api/eu/foto"),
    ),
    ("DELETE", "/api/eu/foto"): Caso(
        lambda p: "/api/eu/foto", proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
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
    # ---- L5-05 documento de construtor: vocabulário do tipo (mesmo esquema para A e B, não é dado de inquilino)
    ("GET", "/api/esquemas"): Caso(lambda p: "/api/esquemas", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("GET", "/api/esquemas/{tipo}"): Caso(lambda p: "/api/esquemas/app", proprio=True, aceita=frozenset({200}),
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
    # ---- L6-02-a modelo de conexão externa: conexão é do INQUILINO (tenant_id + RLS), diferente do acervo
    # acima; GET/POST agem só sobre o próprio chamador (o POST usa o MESMO nome de B para provar que a
    # unicidade de nome é por inquilino, não global); GET/PATCH/DELETE/testar por id de B são cross-tenant puro
    ("GET", "/api/conexoes"): Caso(lambda p: "/api/conexoes", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("POST", "/api/conexoes"): Caso(
        lambda p: "/api/conexoes",
        lambda p: {"tipo": "ogc_api", "nome": p.conexao_b["nome"], "url": URL_CONEXAO_TESTE},
        proprio=True, aceita=frozenset({201}), verificar=lambda p, j: None,  # mesmo nome de B: prova que a
        # unicidade é por inquilino (não global) — por isso não checa _sem_marca (o nome É de propósito igual)
        limpar=_apagar_criado(("DELETE", "/api/conexoes/{id}")),
    ),
    ("GET", "/api/conexoes/{id}"): Caso(lambda p: f"/api/conexoes/{p.conexao_b['id']}"),
    ("PATCH", "/api/conexoes/{id}"): Caso(
        lambda p: f"/api/conexoes/{p.conexao_b['id']}", lambda p: {"nome": f"{PREFIXO}invadida"}
    ),
    ("DELETE", "/api/conexoes/{id}"): Caso(lambda p: f"/api/conexoes/{p.conexao_b['id']}"),
    ("POST", "/api/conexoes/{id}/testar"): Caso(lambda p: f"/api/conexoes/{p.conexao_b['id']}/testar"),
    # L6-02-l/L6-05: mesma regra (conexão de B é cross-tenant puro para A) — nenhuma das duas cria nada em A
    # quando o alvo é de B (a rota lê a conexão pelo RLS de _carregar ANTES de qualquer efeito colateral).
    ("GET", "/api/conexoes/{id}/saude-historico"): Caso(lambda p: f"/api/conexoes/{p.conexao_b['id']}/saude-historico"),
    ("POST", "/api/conexoes/{id}/publicar"): Caso(lambda p: f"/api/conexoes/{p.conexao_b['id']}/publicar"),
    # L6-02-c (conector WFS/OGC API): os três casos de leitura do modo referenciado saíram daqui porque as
    # rotas não existem nesta árvore (o ramo do conector ainda não entrou); caso sem rota reprova a cobertura
    # do cruzado. Voltam com o ramo que traz as rotas.
    # ---- L3-19-multiescala: conjunto/fator/execução são do INQUILINO (tenant_id + RLS, mesma classe da
    # conexão acima, não do registro compartilhado do acervo); GET/POST/DELETE de lista agem só sobre o
    # próprio chamador, GET/DELETE/POST por id de B são cross-tenant puro (404, a RLS nunca deixa ver a linha).
    ("GET", "/api/multiescala/conjuntos"): Caso(lambda p: "/api/multiescala/conjuntos", proprio=True,
                                                aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/multiescala/conjuntos"): Caso(
        lambda p: "/api/multiescala/conjuntos",
        lambda p: {"nome": f"{PREFIXO}conjunto-a-{secrets.token_hex(3)}", "area": AREA_MULTIESCALA_TESTE},
        proprio=True, aceita=frozenset({201}), verificar=_sem_marca,
        limpar=_apagar_criado(("DELETE", "/api/multiescala/conjuntos/{id}")),
    ),
    ("GET", "/api/multiescala/conjuntos/{id}"): Caso(lambda p: f"/api/multiescala/conjuntos/{p.conjunto_b['id']}"),
    ("DELETE", "/api/multiescala/conjuntos/{id}"): Caso(lambda p: f"/api/multiescala/conjuntos/{p.conjunto_b['id']}"),
    ("POST", "/api/multiescala/conjuntos/{id}/macro"): Caso(
        lambda p: f"/api/multiescala/conjuntos/{p.conjunto_b['id']}/macro",
        lambda p: {"resolucao_m": 1000.0, "fatores": [{"fator_id": p.fator_b["id"], "peso": 1.0}],
                   "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0},
    ),
    ("GET", "/api/multiescala/fatores"): Caso(lambda p: "/api/multiescala/fatores", proprio=True,
                                              aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/multiescala/fatores"): Caso(
        lambda p: "/api/multiescala/fatores",
        lambda p: {"nome": f"{PREFIXO}fator-a-{secrets.token_hex(3)}", "resolucao_fonte_m": 100.0, "papel": "atrai"},
        proprio=True, aceita=frozenset({201}), verificar=_sem_marca,
        limpar=_apagar_criado(("DELETE", "/api/multiescala/fatores/{id}")),
    ),
    ("GET", "/api/multiescala/fatores/{id}"): Caso(lambda p: f"/api/multiescala/fatores/{p.fator_b['id']}"),
    ("DELETE", "/api/multiescala/fatores/{id}"): Caso(lambda p: f"/api/multiescala/fatores/{p.fator_b['id']}"),
    ("POST", "/api/multiescala/fatores/{id}/amostras"): Caso(
        lambda p: f"/api/multiescala/fatores/{p.fator_b['id']}/amostras",
        lambda p: {"amostras": [{"lon": -46.60, "lat": -23.50, "valor": 1.0}]},
    ),
    ("GET", "/api/multiescala/execucoes"): Caso(lambda p: "/api/multiescala/execucoes", proprio=True,
                                                aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/api/multiescala/execucoes/{id}"): Caso(lambda p: f"/api/multiescala/execucoes/{p.execucao_b['id']}"),
    ("POST", "/api/multiescala/execucoes/{id}/micro"): Caso(
        lambda p: f"/api/multiescala/execucoes/{p.execucao_b['id']}/micro",
        lambda p: {"resolucao_m": 100.0, "fatores": [{"fator_id": p.fator_b["id"], "peso": 1.0}],
                   "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0},
    ),
    # L6-02-c (conector WFS/OGC API): os três casos de /api/conexoes/{id}/colecoes* saíram daqui porque as
    # ROTAS não existem nesta árvore — elas vêm do ramo do conector, que ainda não entrou em master, e caso
    # de rota inexistente reprova o teste de cobertura tanto quanto rota sem caso. Voltam junto com as rotas.
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
    ("GET", IT + "/integridade"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/integridade"),
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
    # ---- L2-11-c rede de rota: cálculo sobre dado aberto (OSM, recorte de teste), não é de A nem de B —
    # mesmo par (perfil carro, ponto na área de teste de Guarulhos) sempre dá a mesma resposta pública
    ("POST", "/api/rota"): Caso(
        lambda p: "/api/rota",
        lambda p: {"origem": [-46.5330, -23.4628], "destino": [-46.4730, -23.4356], "perfil": "carro"},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/api/matriz"): Caso(
        lambda p: "/api/matriz",
        lambda p: {"origens": [[-46.5330, -23.4628]], "destinos": [[-46.4730, -23.4356]], "perfil": "carro"},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/api/isocrona"): Caso(
        lambda p: "/api/isocrona",
        lambda p: {"ponto": [-46.5330, -23.4628], "minutos": 10, "perfil": "carro"},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    # ---- LDAP/Active Directory (L0-08-d): login é público (mesmo padrão de /api/login); a configuração do
    # provedor age só sobre o inquilino do chamador (proprio), nunca sobre B
    ("POST", "/api/login/ldap"): Caso(
        lambda p: "/api/login/ldap",
        lambda p: {"inquilino": "demo2", "login": p.usuario_b["login"], "senha": "Senha-errada-1"},
        publico=True,
    ),
    ("GET", "/api/org/ldap"): Caso(lambda p: "/api/org/ldap", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("PUT", "/api/org/ldap"): Caso(
        lambda p: "/api/org/ldap",
        lambda p: {"habilitado": False},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
        limpar=lambda p, j: p.sessao_a.put("/api/org/ldap", json={"habilitado": False}),
    ),
    ("POST", "/api/org/ldap/importar"): Caso(
        lambda p: "/api/org/ldap/importar",
        lambda p: {"grupo_dn": "cn=inexistente,dc=zz", "atributo_membro": "memberOf", "atributo_login": "uid",
                   "perfil": "visualizador"},
        # sem provedor configurado (ou desabilitado pela suíte de LDAP, que sempre desliga no fim) → 409;
        # se por acaso ficou habilitado apontando para um glauth de teste já derrubado → 503; nunca um 2xx
        # aqui (não há credencial de bind válida contra nenhum diretório real neste teste)
        proprio=True, aceita=frozenset({409, 503}),
    ),
    # ---- configurações da organização (L0-07-a-configuracoes-org): igual ao /api/org/ldap acima, a rota
    # nunca recebe id de inquilino na URL — age só sobre `plat.tenant_atual()` (proprio). O corpo do PUT
    # ecoa exatamente o que o próprio GET de A acabou de devolver (full-replace sem mudar nada de verdade),
    # então não precisa de `limpar`; o logotipo enviado É apagado no fim (1×1 PNG, não é dado de B).
    # ---- rede de utilidades (L4-01-a-pacote-de-ativos): o catálogo /api/rede/pacotes vem com a instalação e
    # não é de inquilino nenhum (proprio); tudo em /api/rede/{rede_id} aponta a rede de B e tem de dar 404.
    ("GET", "/api/rede"): Caso(lambda p: "/api/rede", proprio=True, aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/rede"): Caso(
        lambda p: "/api/rede",
        lambda p: {"nome": f"{PREFIXO}rede-a-{secrets.token_hex(4)}", "disciplina": "eletrica"},
        proprio=True, aceita=frozenset({201}), verificar=_sem_marca,
        limpar=_apagar_criado(("DELETE", "/api/rede/{id}")),
    ),
    ("GET", "/api/rede/pacotes"): Caso(
        lambda p: "/api/rede/pacotes", proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("GET", "/api/rede/pacotes/{codigo}"): Caso(
        lambda p: "/api/rede/pacotes/agua-epanet", proprio=True, aceita=frozenset({200}),
    ),
    ("GET", "/api/rede/{rede_id}"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}"),
    ("DELETE", "/api/rede/{rede_id}"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}"),
    ("GET", "/api/rede/{rede_id}/pacote"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/pacote"),
    # o corpo é um pacote VÁLIDO de propósito: a rota valida o pacote antes de tocar o banco (decisão do
    # item L4-01-a, para não segurar o laço de eventos), então um corpo inválido responderia 422 e a
    # varredura nunca chegaria a provar o que interessa — que a rede de OUTRO inquilino dá 404.
    ("POST", "/api/rede/{rede_id}/pacote"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/pacote",
        lambda p: json.loads(instalados.bruto("agua-epanet")),
    ),
    # L4-01-c: importação BDGD por job — a rede de B não pode ser alvo de A (o job nem é criado)
    ("POST", "/api/rede/{rede_id}/importar-bdgd"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/importar-bdgd",
        lambda p: {"caminho": "inexistente.gdb"},
    ),
    # ---- L4-01-b / L4-02-a / L4-18: as rotas de feição, topologia, traçado e rede simples vieram nos
    # ramos-base desta família e ainda não tinham caso cruzado. Todas apontam a rede de B: a resposta tem de
    # ser 404 (a rede nem é vista) antes de qualquer trabalho. `/api/rede/simples` aponta uma CAMADA que não
    # é de A — o id nulo garante 404 sem depender de recurso de B.
    # ---- L4-01-b topologia e feições da rede de utilidades, L4-18 rede simples: todas apontam a rede de B
    # e têm de dar 404 (a rede de B nem é vista). O corpo é o mínimo que passa pela validação de forma, para
    # que a resposta venha da autorização e não de um 422 de esquema.
    ("GET", "/api/rede/{rede_id}/feicoes/pontos"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/pontos"),
    ("GET", "/api/rede/{rede_id}/feicoes/linhas"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/linhas"),
    ("POST", "/api/rede/{rede_id}/feicoes/pontos"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/pontos",
        lambda p: {"grupo": "trecho", "tipo_codigo": 1, "lon": 0.0, "lat": 0.0}),
    ("POST", "/api/rede/{rede_id}/feicoes/linhas"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/linhas",
        lambda p: {"grupo": "trecho", "tipo_codigo": 1, "coordenadas": [[0.0, 0.0], [0.001, 0.0]]}),
    ("POST", "/api/rede/{rede_id}/feicoes/pontos/applyEdits"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/pontos/applyEdits", lambda p: {"deletes": []}),
    ("POST", "/api/rede/{rede_id}/feicoes/linhas/applyEdits"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/feicoes/linhas/applyEdits", lambda p: {"deletes": []}),
    ("POST", "/api/rede/{rede_id}/topologia/habilitar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/topologia/habilitar", lambda p: {}),
    ("GET", "/api/rede/{rede_id}/topologia"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/topologia"),
    ("GET", "/api/rede/{rede_id}/topologia/nos"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/topologia/nos"),
    ("GET", "/api/rede/{rede_id}/topologia/arestas"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/topologia/arestas"),
    ("GET", "/api/rede/{rede_id}/topologia/diagnostico"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/topologia/diagnostico"),
    ("GET", "/api/rede/{rede_id}/topologia/areas-sujas"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/topologia/areas-sujas"),
    ("GET", "/api/rede/{rede_id}/topologia/alcance"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/topologia/alcance?no={UUID_NULO}"),
    ("POST", "/api/rede/{rede_id}/tracar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/tracar",
        lambda p: {"tipo": "conectado", "pontos_partida": [{"lon": 0.0, "lat": 0.0}]}),
    # criar rede simples não endereça a rede de B: aponta CAMADA por id, e o id que não é de ninguém tem de
    # dar 404 igual (a resposta não pode depender de existir camada em outro inquilino)
    ("POST", "/api/rede/simples"): Caso(
        lambda p: "/api/rede/simples",
        lambda p: {"nome": f"{PREFIXO}simples-{secrets.token_hex(4)}", "disciplina": "agua",
                   "camada_linha_id": UUID_NULO}),
    ("GET", "/api/rede/{rede_id}/simples"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/simples"),
    ("POST", "/api/rede/{rede_id}/promover"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/promover", lambda p: {}),
    # ---- L4-02-e configuração de traçado: tudo endereça a rede de B e tem de dar 404 de REDE (a rede nem é
    # vista); o id de configuração é forjado, e mesmo trocar o 404 de rede por 404 de configuração vazaria
    # a existência da rede do outro inquilino.
    ("POST", "/api/rede/{rede_id}/config_tracado"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/config_tracado",
        lambda p: {"codigo": f"zt-cfg-{secrets.token_hex(3)}", "nome": "zt", "tipo": "conectado",
                   "config": {}},
    ),
    ("GET", "/api/rede/{rede_id}/config_tracado"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/config_tracado"),
    ("GET", "/api/rede/{rede_id}/config_tracado/{config_id}"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/config_tracado/{UUID_NULO}"),
    ("PUT", "/api/rede/{rede_id}/config_tracado/{config_id}"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/config_tracado/{UUID_NULO}",
        lambda p: {"codigo": f"zt-cfg-{secrets.token_hex(3)}", "nome": "zt", "tipo": "conectado",
                   "config": {}},
    ),
    ("DELETE", "/api/rede/{rede_id}/config_tracado/{config_id}"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/config_tracado/{UUID_NULO}"),
    # ---- L4-04-a controlador de subrede e tiers: tudo em /api/rede/{rede_id} aponta a rede de B e tem de
    # dar 404 (a rede nem é vista). O id de controlador/subrede é forjado: se a rede fosse alcançável, a
    # resposta mudaria de 404 de rede para 404 de controlador — e mesmo isso vazaria a existência da rede.
    ("POST", "/api/rede/{rede_id}/controlador"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/controlador",
        lambda p: {"feicao_id": "00000000-0000-4000-8000-000000000001", "subrede": "zt", "tier": "unico"},
    ),
    ("GET", "/api/rede/{rede_id}/controladores"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/controladores"),
    ("GET", "/api/rede/{rede_id}/controlador/{controlador_id}"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/controlador/00000000-0000-4000-8000-000000000001"),
    ("DELETE", "/api/rede/{rede_id}/controlador/{controlador_id}"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/controlador/00000000-0000-4000-8000-000000000001"),
    ("GET", "/api/rede/{rede_id}/subredes"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/subredes"),
    ("POST", "/api/rede/{rede_id}/subredes/{subrede_id}/atualizar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subredes/00000000-0000-4000-8000-000000000001/atualizar",
        lambda p: {},
    ),
    ("GET", "/api/rede/{rede_id}/tiers"): Caso(lambda p: f"/api/rede/{p.rede_b['id']}/tiers"),
    # ---- L4-04-b atualizar e exportar subrede: as quatro rotas novas apontam a rede de B e têm de dar 404
    # antes de qualquer trabalho — a de atualizar em lote nem chega a enfileirar job, a de exportar nem chega
    # a procurar a subrede pelo nome.
    ("POST", "/api/rede/{rede_id}/subredes/atualizar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subredes/atualizar", lambda p: {}),
    ("PUT", "/api/rede/{rede_id}/tier/{codigo}/propagadores"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/tier/media_tensao/propagadores",
        lambda p: {"propagadores": []}),
    ("GET", "/api/rede/{rede_id}/subredes/conferencia"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subredes/conferencia"),
    ("GET", "/api/rede/{rede_id}/subrede/{nome}/exportar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subrede/zt-inexistente/exportar"),
    # ---- L4-04-c sumário por subrede: as duas rotas apontam a rede de B e têm de dar 404 (a rede nem é
    # vista); o CSV segue a mesma rota, com formato=csv, e por isso não tem caso separado.
    ("GET", "/api/rede/{rede_id}/subredes/resumos"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subredes/resumos"),
    ("POST", "/api/rede/{rede_id}/subredes/resumos/calcular"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/subredes/resumos/calcular", lambda p: {}),
    ("POST", "/api/rede/{rede_id}/controladores/importar"): Caso(
        lambda p: f"/api/rede/{p.rede_b['id']}/controladores/importar", lambda p: {}),
    ("GET", "/api/org"): Caso(lambda p: "/api/org", proprio=True, aceita=frozenset({200}), verificar=_sem_marca),
    ("PUT", "/api/org"): Caso(
        lambda p: "/api/org", _corpo_org_atual, proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/api/org/logo"): Caso(
        lambda p: "/api/org/logo",
        lambda p: {"conteudo": _PNG_1X1_B64},
        proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
        limpar=lambda p, j: p.sessao_a.delete("/api/org/logo"),
    ),
    ("DELETE", "/api/org/logo"): Caso(
        lambda p: "/api/org/logo", proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    # ---- L0-07-d convite de membro por e-mail (ADR 0013): GET/POST/DELETE agem só sobre o inquilino do
    # chamador (a tabela é por tenant_id, igual a papéis/tokens); POST usa o MESMO e-mail do convite de B de
    # propósito, para provar que a unicidade de convite pendente é por inquilino, não global (mesmo padrão de
    # POST /api/tokens e POST /api/conexoes acima) — por isso não checa _sem_marca. resolver/aceitar são
    # públicos e endereçados só pelo TOKEN secreto do link (nunca por id de inquilino): usar o token real de B
    # aceitaria de fato o convite e mutaria B (violaria o digest antes/depois por DESENHO da funcionalidade,
    # não por falha de isolamento) — o caso usa um token forjado, que dá sempre 410 `convite_invalido`
    # independente de quem chama, provando que não há atalho por sessão/cabeçalho/token de A.
    ("GET", "/api/convites"): Caso(lambda p: "/api/convites", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("POST", "/api/convites"): Caso(
        lambda p: "/api/convites",
        lambda p: {"email": p.convite_b["email"], "perfil": "editor"},
        proprio=True, aceita=frozenset({201}), verificar=lambda p, j: None,
        limpar=_apagar_criado(("DELETE", "/api/convites/{id}")),
    ),
    ("DELETE", "/api/convites/{id}"): Caso(lambda p: f"/api/convites/{p.convite_b['id']}"),
    ("GET", "/api/convites/resolver"): Caso(
        lambda p: "/api/convites/resolver?token=zt-cruzado-token-forjado-nunca-emitido",
        publico=True, aceita=frozenset({410}),
    ),
    ("POST", "/api/convites/aceitar"): Caso(
        lambda p: "/api/convites/aceitar",
        lambda p: {"token": "zt-cruzado-token-forjado-nunca-emitido", "login": f"{PREFIXO}invasor",
                   "nome": "invasor", "senha": "Senha-Forte-123!"},
        publico=True, aceita=frozenset({410}),
    ),
    # ---- L0-07-d redefinição de senha por e-mail: as três rotas são públicas e por TOKEN/e-mail, nunca por
    # id de inquilino; `solicitar` SEMPRE responde {"ok": true} (nunca revela se o e-mail existe, ADR 0002
    # seção 6.3), então usar o e-mail de um usuário de B não prova nem desprova nada — e não muda B (sem SMTP
    # configurado na trilha não sai fila nenhuma). resolver/aplicar com token forjado dão sempre 410, mesmo
    # padrão do convite acima.
    # o mesmo e-mail se repete nas 4 chamadas da varredura (mesmo caso, sessão/token/cabeçalho/sem-auth): a
    # 2ª em diante esbarra no limite de taxa por inquilino+e-mail (`REDEFINICAO_MAX_JANELA`, ADR 0002 seção
    # 6.3) e dá 429 — esperado, não vazamento; aceito ao lado do 202 da 1ª chamada.
    ("POST", "/api/senha/redefinir/solicitar"): Caso(
        lambda p: "/api/senha/redefinir/solicitar",
        lambda p: {"inquilino": "demo2", "email": f"{PREFIXO}naoexiste@teste.exemplo"},
        publico=True, aceita=frozenset({202, 429}), verificar=_sem_marca,
    ),
    ("GET", "/api/senha/redefinir/resolver"): Caso(
        lambda p: "/api/senha/redefinir/resolver?token=zt-cruzado-token-forjado-nunca-emitido",
        publico=True, aceita=frozenset({410}),
    ),
    ("POST", "/api/senha/redefinir/aplicar"): Caso(
        lambda p: "/api/senha/redefinir/aplicar",
        lambda p: {"token": "zt-cruzado-token-forjado-nunca-emitido", "senha": "Senha-Forte-123!"},
        publico=True, aceita=frozenset({410}),
    ),
    # ---- L0-07-a SMTP por inquilino (ADR 0013): mesmo padrão do /api/org/ldap acima — a rota nunca recebe id
    # de inquilino, age só sobre `plat.tenant_atual()`. PUT com corpo vazio é o caminho idempotente que só
    # remove o override do PRÓPRIO inquilino (host="" -> `config - 'smtp'`), nunca mexe em B. `testar` sem SMTP
    # configurado na trilha dá 422 `smtp_nao_configurado` antes de qualquer tentativa de envio real.
    ("GET", "/api/org/smtp"): Caso(lambda p: "/api/org/smtp", proprio=True, aceita=frozenset({200}),
                                   verificar=_sem_marca),
    ("PUT", "/api/org/smtp"): Caso(
        lambda p: "/api/org/smtp", lambda p: {}, proprio=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/api/org/smtp/testar"): Caso(
        lambda p: "/api/org/smtp/testar", lambda p: {}, proprio=True, aceita=frozenset({200, 422, 502}),
        verificar=_sem_marca,
    ),
    # ---- L0-04-a upload retomável (ADR 0005): sob TOKEN de serviço; a rota nunca recebe id de inquilino —
    # `_carregar` filtra por `usuario_id == auth.usuario_id` (nem sequer por tenant: outro usuário do MESMO
    # inquilino já toma 404), então qualquer id que não seja do chamador (o de B incluso) é 404 garantido sem
    # precisar upar nada como B. `iniciar`/`tipos` agem só sobre o chamador (proprio); `iniciar` não é limpo
    # explicitamente (abortar exige token, que `limpar` não tem acesso aqui) — o upload nascido fica
    # 'iniciado' e expira sozinho (PLAT_UPLOAD_EXPIRA_HORAS), sem custo de armazenamento (Garage só recebe
    # bytes na primeira parte, que este caso nunca envia).
    # `tipos_aceitos` não declara `auth` nenhum (achado desta verificação: a metadado openapi diz "S/T", mas
    # o handler não chama `autenticado()`) — vocabulário estático, sem dado de inquilino, correto ficar aberto.
    ("GET", "/api/uploads/tipos"): Caso(lambda p: "/api/uploads/tipos", publico=True, aceita=frozenset({200}),
                                        verificar=_sem_marca),
    ("POST", "/api/uploads"): Caso(
        lambda p: "/api/uploads",
        lambda p: {"nome": f"{PREFIXO}upload.geojson", "bytes": 10, "tipo_declarado": "geojson"},
        proprio=True, aceita=frozenset({201}), verificar=_sem_marca,
    ),
    ("GET", "/api/uploads/{id}"): Caso(lambda p: f"/api/uploads/{UUID_NULO}"),
    ("PUT", "/api/uploads/{id}/partes/{n}"): Caso(lambda p: f"/api/uploads/{UUID_NULO}/partes/1"),
    ("POST", "/api/uploads/{id}/concluir"): Caso(lambda p: f"/api/uploads/{UUID_NULO}/concluir", lambda p: {}),
    ("DELETE", "/api/uploads/{id}"): Caso(lambda p: f"/api/uploads/{UUID_NULO}"),
    # ---- L0-04-b/c/d ingestão vetorial (ADR 0005 seção 16): `_carregar` filtra por RLS de tenant_id + dono
    # (com exceção de jobs.gerir_todos), igual ao padrão de jobs/agendas — id de B (ou qualquer id que não seja
    # do chamador) é 404 `importacao_inexistente` garantido. `criar` referencia o item-arquivo de B (existe,
    # mas não é tipo 'arquivo' nem do inquilino de A) para cair no mesmo 404 sem upar nada de verdade.
    ("GET", "/api/importacoes"): Caso(lambda p: "/api/importacoes", proprio=True, aceita=frozenset({200}),
                                      verificar=_sem_marca),
    ("GET", "/api/importacoes/formatos"): Caso(lambda p: "/api/importacoes/formatos", proprio=True,
                                               aceita=frozenset({200}), verificar=_sem_marca),
    ("POST", "/api/importacoes"): Caso(
        lambda p: "/api/importacoes", lambda p: {"arquivo_id": p.item_b["id"], "formato": "geojson"}
    ),
    ("GET", "/api/importacoes/{id}"): Caso(lambda p: f"/api/importacoes/{UUID_NULO}"),
    ("PUT", "/api/importacoes/{id}/confirmar"): Caso(
        lambda p: f"/api/importacoes/{UUID_NULO}/confirmar", lambda p: {}
    ),
    ("DELETE", "/api/importacoes/{id}"): Caso(lambda p: f"/api/importacoes/{UUID_NULO}"),
    # ---- L0-09 catálogo externo OGC API Records: mesma RLS de `plat.item` de `GET /api/itens` — a coleção
    # única ("catalogo") é o inquilino do chamador; item de B por id é 404 (`item_ou_404`); listar com filtro
    # `q=id:<item de B>` dá lista vazia (mesmo padrão de `GET /api/itens` acima).
    ("GET", "/ogc/records"): Caso(lambda p: "/ogc/records", proprio=True, aceita=frozenset({200}),
                                  verificar=_sem_marca),
    ("GET", "/ogc/records/conformance"): Caso(lambda p: "/ogc/records/conformance", proprio=True,
                                              aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/ogc/records/collections"): Caso(lambda p: "/ogc/records/collections", proprio=True,
                                              aceita=frozenset({200}), verificar=_sem_marca),
    ("GET", "/ogc/records/collections/{colecao_id}"): Caso(
        lambda p: "/ogc/records/collections/catalogo", proprio=True, aceita=frozenset({200}), verificar=_sem_marca
    ),
    ("GET", "/ogc/records/collections/{colecao_id}/items"): Caso(
        lambda p: f"/ogc/records/collections/catalogo/items?q=id:{p.item_b['id']}",
        proprio=True, aceita=frozenset({200}), verificar=lambda p, j: [_sem_marca(p, j), _ogc_zero(j)],
    ),
    ("GET", "/ogc/records/collections/{colecao_id}/items/{item_id}"): Caso(
        lambda p: f"/ogc/records/collections/catalogo/items/{p.item_b['id']}"
    ),
    # ---- L0-09 metadado ISO 19139 do item: mesmo `item_ou_404` + RLS de `IT` acima.
    ("GET", IT + "/metadado.xml"): Caso(lambda p: f"/api/itens/{p.item_b['id']}/metadado.xml"),
    # ---- L2-11-b geocodificador próprio (dado aberto CNEFE/IBGE, sem tabela de inquilino, mesmo padrão de
    # /api/rota-/api/matriz-/api/isocrona acima): 422 é resposta de NEGÓCIO (UF/logradouro não instalado
    # nesta trilha), não vazamento — aceito ao lado de 200.
    ("POST", "/api/geocodificar"): Caso(
        lambda p: "/api/geocodificar", lambda p: {"endereco": "Avenida Paulista, São Paulo - SP"},
        proprio=True, aceita=frozenset({200, 422}), verificar=_sem_marca,
    ),
    ("POST", "/api/reverso"): Caso(
        lambda p: "/api/reverso", lambda p: {"lon": -46.6333, "lat": -23.5505},
        proprio=True, aceita=frozenset({200, 422}), verificar=_sem_marca,
    ),
    ("GET", "/api/sugerir"): Caso(lambda p: "/api/sugerir?q=Avenida+Paulista", proprio=True,
                                  aceita=frozenset({200}), verificar=_sem_marca),
    # ---- L2-11-b GeocodeServer compatível Esri (mesmo motor/dado aberto acima, protocolo REST do ArcGIS):
    # o descritor não checa autenticação nenhuma (metadado do locator, igual ao capabilities de um serviço
    # publicado). As demais chamam `_autenticar()` (rotas_esri.py), que tenta sessão/token PRÓPRIO — não a
    # dependência `autenticado()` padrão do resto da API — e por isso NUNCA passa pelo `_resolver_leitura_
    # superadmin` que rejeita `X-Plat-Inquilino` de quem não é operador da plataforma (achado desta
    # verificação): o cabeçalho é simplesmente ignorado, a chamada roda no tenant de quem autenticou de
    # verdade. Sem risco (dado nacional do CNEFE, sem tabela de inquilino), mas o comportamento real é
    # `publico=True` nesta varredura, não `proprio=True` — marcar `proprio` aqui exigiria 401/403/404 na
    # perna do cabeçalho, que a rota não devolve.
    ("GET", "/rest/services/Geocodificador/GeocodeServer"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer", publico=True, aceita=frozenset({200}),
        verificar=_sem_marca,
    ),
    ("POST", "/rest/services/Geocodificador/GeocodeServer"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer", lambda p: {}, publico=True,
        aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("GET", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"
                  "?address=Avenida+Paulista&city=Sao+Paulo&region=SP",
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"
                  "?address=Avenida+Paulista&city=Sao+Paulo&region=SP",
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("GET", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/reverseGeocode?location=-46.6333,-23.5505",
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/reverseGeocode?location=-46.6333,-23.5505",
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("GET", "/rest/services/Geocodificador/GeocodeServer/suggest"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/suggest?text=Avenida+Paulista",
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"): Caso(
        lambda p: "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses",
        lambda p: {"addresses": {"records": [{"attributes": {"OBJECTID": 1,
                                                              "SingleLine": "Avenida Paulista, Sao Paulo - SP"}}]}},
        publico=True, aceita=frozenset({200}), verificar=_sem_marca,
    ),
}


def _zero(j: Any) -> None:
    assert j["total"] == 0 and j["itens"] == [], "A vê linhas de log/evento de um usuário de B"


def _vazio(j: Any) -> None:
    assert j == [], "A vê pastas de B"


def _ogc_zero(j: Any) -> None:
    # a resposta vem com media_type "application/geo+json" (rotas_ogc.py), então `test_cruzado._chamar`
    # (que só faz `.json()` quando o content-type começa com "application/json") entrega texto cru aqui —
    # decodifica antes de indexar.
    import json as _json

    corpo = _json.loads(j) if isinstance(j, str) else j
    assert corpo["numberMatched"] == 0 and corpo["features"] == [], "A vê registro OGC de item de B"


def _lote_itens_recusado(p: Preparacao, j: Any) -> None:
    assert j["feitos"] == 0 and [x["erro"] for x in j["recusados"]] == ["item_inexistente"], j


def _link_so_o_item(p: Preparacao, j: Any) -> None:
    """Pelo link vê-se só o item incluído: sem login do dono, sem pode_*, sem slug do inquilino, sem outras marcas."""
    item = j["item"]
    assert "login" not in item["dono"] and "pode_editar" not in item and item["id"] == p.item_b["id"]
    for marca in (p.usuario_b["login"], p.grupo_b["nome"], p.papel_b["nome"], p.token_b["prefixo"], "demo2"):
        assert marca not in str(j), marca
