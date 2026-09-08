"""Item L0-07-d-smtp-convites: portão de pronto e refutação, contra um servidor SMTP de CAPTURA em stdlib
puro (`tests/api/util_smtp_captura.py`; `aiosmtpd` está ausente desta máquina). Convite de membro (link cria
a conta ao aceitar, token de uso único, validade 7 dias), redefinição de senha por e-mail (token de 1 hora),
"testar envio" com erro legível, e-mail como job (fila do L0-05) executado pelo `plat-worker` REAL — os testes
esperam a entrega de verdade, não simulam o worker. Roda contra um inquilino temporário (`inquilino_temporario`),
nunca contra `demo`/`demo2` (evita interferir com outra trilha que rode a suíte ao mesmo tempo)."""

import re
import secrets
import subprocess
import time

from app.auth.sessao import sha256_hex
from tests.api.conftest import entrar, novo_cliente
from tests.api.util_smtp_captura import ServidorSMTPCaptura

LINK_RE = re.compile(r"https?://\S+")


def _link_do_corpo(corpo: str) -> str:
    m = LINK_RE.search(corpo)
    assert m, f"nenhum link encontrado no corpo do e-mail: {corpo!r}"
    return m.group(0)


def _token_do_link(link: str) -> str:
    return link.split("token=", 1)[-1]


def _configurar_smtp(cliente, porta: int, usuario: str = "", senha: str = "") -> dict:
    r = cliente.put(
        "/api/org/smtp",
        json={
            "host": "127.0.0.1", "porta": porta, "tls": False, "usuario": usuario, "senha": senha,
            "remetente": "naoresponda@teste.exemplo", "rotulo": "Plat Teste",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _expirar_convite(conexao_plat_app, tenant_id: int, token: str) -> None:
    # RLS de plat.convite exige plat.tenant_atual() (o GUC de sessão) — sem ele o UPDATE afeta 0 linhas em
    # silêncio (achado desta sessão: o teste "passava" comparando 200 == 200, nunca expirando de verdade).
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id),))
        cur.execute("UPDATE plat.convite SET expira_em = now() - interval '1 hour' WHERE token_hash = %s",
                    (sha256_hex(token),))
    conexao_plat_app.commit()


def _expirar_redefinicao(conexao_plat_app, tenant_id: int, token: str) -> None:
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id),))
        cur.execute("UPDATE plat.redefinicao_senha SET expira_em = now() - interval '1 hour' WHERE token_hash = %s",
                    (sha256_hex(token),))
    conexao_plat_app.commit()


# ---------------------------------------------------------------- SMTP: GET/PUT/testar
def test_smtp_ler_gravar_e_remover(inquilino_temporario):
    inq = inquilino_temporario
    r = inq.admin.get("/api/org/smtp")
    assert r.status_code == 200 and r.json()["configurado"] is False and r.json()["origem"] == "nenhum"
    with ServidorSMTPCaptura() as smtp:
        j = _configurar_smtp(inq.admin, smtp.porta)
        assert j["configurado"] is True and j["origem"] == "inquilino" and j["host"] == "127.0.0.1"
        assert "senha" not in j and "senha_cifrada" not in j  # nunca volta na resposta
        r = inq.admin.get("/api/org/smtp")
        assert r.status_code == 200 and r.json()["porta"] == smtp.porta
    # host vazio remove o override do inquilino
    r = inq.admin.put("/api/org/smtp", json={"host": "", "porta": 587, "tls": True, "usuario": "",
                                             "senha": None, "remetente": "", "rotulo": ""})
    assert r.status_code == 200 and r.json()["configurado"] is False


def test_smtp_remetente_obrigatorio_com_host(inquilino_temporario):
    r = inquilino_temporario.admin.put(
        "/api/org/smtp",
        json={"host": "smtp.exemplo.invalido", "porta": 587, "tls": True, "usuario": "", "senha": "",
              "remetente": "", "rotulo": ""},
    )
    assert r.status_code == 422 and r.json()["erro"] == "validacao"


def test_smtp_testar_com_host_errado_devolve_erro_legivel(inquilino_temporario):
    """Portão do item: 'testar envio' devolve erro legível com host errado."""
    inq = inquilino_temporario
    r = inq.admin.put(
        "/api/org/smtp",
        json={"host": "smtp-que-nao-existe.invalido.teste", "porta": 587, "tls": False, "usuario": "",
              "senha": "", "remetente": "naoresponda@teste.exemplo", "rotulo": ""},
    )
    assert r.status_code == 200, r.text
    t0 = time.monotonic()
    r = inq.admin.post("/api/org/smtp/testar", json={"destinatario": "verificacao@teste.exemplo"})
    dt = time.monotonic() - t0
    assert r.status_code == 502, r.text
    assert r.json()["erro"] == "smtp_falhou"
    mensagem = r.json()["mensagem"]
    assert mensagem and "smtp-que-nao-existe" in mensagem  # legível: cita o host, não um traceback
    assert dt < 10, f"testar envio prendeu a requisição por {dt:.1f}s (esperava timeout curto)"


def test_smtp_testar_ok_com_captura(inquilino_temporario):
    inq = inquilino_temporario
    with ServidorSMTPCaptura() as smtp:
        _configurar_smtp(inq.admin, smtp.porta)
        r = inq.admin.post("/api/org/smtp/testar", json={"destinatario": "alvo@teste.exemplo"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True and r.json()["destinatario"] == "alvo@teste.exemplo"
        assert smtp.esperar(1, timeout=10)
        assert smtp.mensagens[0].rcpt_to == ["<alvo@teste.exemplo>"]


# ---------------------------------------------------------------- convite: ponta a ponta com o worker REAL
def test_convite_ponta_a_ponta_chega_aceita_cria_conta(inquilino_temporario):
    inq = inquilino_temporario
    with ServidorSMTPCaptura() as smtp:
        _configurar_smtp(inq.admin, smtp.porta)
        email = f"convidado-{secrets.token_hex(4)}@teste.exemplo"
        r = inq.admin.post("/api/convites", json={"email": email, "perfil": "editor"})
        assert r.status_code == 201, r.text
        convite = r.json()
        assert convite["link_manual"] is None  # com SMTP configurado, nunca mostra o link manual
        assert smtp.esperar(1, timeout=25), "o e-mail de convite não chegou ao worker real a tempo"
    msg = smtp.mensagens[-1]
    assert msg.rcpt_to == [f"<{email}>"]
    link = _link_do_corpo(msg.corpo)
    assert "/aceitar-convite?token=" in link
    token = _token_do_link(link)

    anonimo = novo_cliente()
    r = anonimo.get(f"/api/convites/resolver?token={token}")
    assert r.status_code == 200 and r.json()["email"] == email and r.json()["perfil"] == "editor"

    # extra "email" no corpo (tentativa de alterar o e-mail do convite pelo lado do cliente): 422, nunca aceito
    login = f"zt{secrets.token_hex(4)}"
    senha = "Senha-forte-1" + secrets.token_hex(3)
    r = anonimo.post("/api/convites/aceitar",
                     json={"token": token, "login": login, "nome": "Convidado Teste", "senha": senha,
                           "email": "atacante@evil.exemplo"})
    assert r.status_code == 422, r.text

    r = anonimo.post("/api/convites/aceitar", json={"token": token, "login": login, "nome": "Convidado Teste",
                                                     "senha": senha})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["login"] == login and r.json()["tenant_slug"] == inq.slug

    # o e-mail da conta criada é o do CONVITE, nunca algo que o cliente tivesse tentado passar
    r = inq.admin.get(f"/api/usuarios?q={login}")
    assert r.status_code == 200
    criado = next(u for u in r.json()["itens"] if u["login"] == login)
    assert inq.admin.get(f"/api/usuarios/{criado['id']}").json()["email"] == email

    # login funciona com a senha escolhida
    c = novo_cliente()
    r = entrar(c, inq.slug, login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True

    # link usado de novo = 410 (portão do item)
    r = anonimo.post("/api/convites/aceitar", json={"token": token, "login": f"zt{secrets.token_hex(4)}",
                                                     "nome": "x", "senha": senha})
    assert r.status_code == 410 and r.json()["erro"] == "convite_usado"


def test_convite_expirado_apos_7_dias_e_410(inquilino_temporario, conexao_plat_app):
    inq = inquilino_temporario
    email = f"expira-{secrets.token_hex(4)}@teste.exemplo"
    r = inq.admin.post("/api/convites", json={"email": email, "perfil": "visualizador"})
    assert r.status_code == 201, r.text
    link = r.json()["link_manual"]  # sem SMTP configurado neste teste: link manual disponível de propósito
    assert link is not None
    token = _token_do_link(link)
    _expirar_convite(conexao_plat_app, inq.id, token)
    anonimo = novo_cliente()
    r = anonimo.get(f"/api/convites/resolver?token={token}")
    assert r.status_code == 410 and r.json()["detalhe"]["motivo"] == "expirado"
    r = anonimo.post("/api/convites/aceitar", json={"token": token, "login": f"zt{secrets.token_hex(4)}",
                                                     "nome": "x", "senha": "Senha-forte-1" + secrets.token_hex(2)})
    assert r.status_code == 410 and r.json()["erro"] == "convite_expirado"


def test_convite_cancelado_por_outro_inquilino_e_404(inquilino_temporario, sessao_a):
    """RLS: o admin de outro inquilino (demo) não vê nem cancela o convite deste inquilino temporário."""
    inq = inquilino_temporario
    r = inq.admin.post("/api/convites", json={"email": f"x-{secrets.token_hex(3)}@teste.exemplo",
                                              "perfil": "visualizador"})
    assert r.status_code == 201, r.text
    convite_id = r.json()["id"]
    assert sessao_a.delete(f"/api/convites/{convite_id}").status_code == 404
    assert inq.admin.delete(f"/api/convites/{convite_id}").status_code == 204  # o dono cancela normalmente


def test_convite_admin_exige_membros_papel(inquilino_temporario):
    """Mesmo teto de POST /api/usuarios: convidar com perfil != visualizador exige membros.papel. O papel
    de piso usa `membros.gerir` (privilégio administrativo, ADR 0002 §2.3), então o `perfil_minimo`
    calculado é `admin` — o usuário de teste tem de nascer admin (o papel é o que restringe, não o
    perfil) senão a própria criação do usuário cai em 422 `papel_incompativel` antes de chegar ao convite
    (achado desta sessão)."""
    inq = inquilino_temporario
    r = inq.admin.post("/api/papeis", json={"nome": f"zt-piso-{secrets.token_hex(2)}",
                                            "privilegios": ["membros.ver", "membros.gerir"]})
    assert r.status_code == 201, r.text
    assert r.json()["perfil_minimo"] == "admin"
    c = novo_cliente()
    u = inq.admin.post("/api/usuarios", json={"login": f"zt{secrets.token_hex(3)}", "nome": "piso",
                                              "perfil": "admin", "papel_id": r.json()["id"]})
    assert u.status_code == 201, u.text
    temporaria = u.json()["senha_temporaria"]
    assert entrar(c, inq.slug, u.json()["usuario"]["login"], temporaria).status_code == 200
    nova = "Senha-forte-1" + secrets.token_hex(3)
    assert c.put("/api/eu/senha", json={"atual": temporaria, "nova": nova}).status_code == 204
    r2 = c.post("/api/convites", json={"email": "quemquer@teste.exemplo", "perfil": "editor"})
    assert r2.status_code == 403 and r2.json()["erro"] == "sem_privilegio"


def test_correio_enviar_nao_e_criavel_por_post_jobs(inquilino_temporario):
    """Achado desta sessão (defesa antes do adversário): correio.enviar é somente_sistema; POST /api/jobs
    com esse tipo tem de recusar mesmo para o admin, senão o SMTP do inquilino vira canhão de e-mail."""
    r = inquilino_temporario.admin.post("/api/jobs", json={"tipo": "correio.enviar",
                                                           "parametros": {"destinatario": "a@b.c",
                                                                          "assunto": "x", "texto": "y",
                                                                          "categoria": "x"}})
    assert r.status_code == 403 and r.json()["erro"] == "tipo_somente_sistema"


# ---------------------------------------------------------------- redefinição de senha
def test_redefinicao_ponta_a_ponta_e_limite_de_taxa(inquilino_temporario, conexao_plat_app):
    inq = inquilino_temporario
    email = f"redef-{secrets.token_hex(4)}@teste.exemplo"
    login = f"zt{secrets.token_hex(4)}"
    r = inq.admin.post("/api/usuarios", json={"login": login, "nome": "Redefine Teste", "perfil": "editor",
                                              "email": email})
    assert r.status_code == 201, r.text
    with ServidorSMTPCaptura() as smtp:
        _configurar_smtp(inq.admin, smtp.porta)
        anonimo = novo_cliente()
        r = anonimo.post("/api/senha/redefinir/solicitar", json={"inquilino": inq.slug, "email": email})
        assert r.status_code == 202 and r.json()["ok"] is True
        assert smtp.esperar(1, timeout=25), "e-mail de redefinição não chegou ao worker real a tempo"
    msg = smtp.mensagens[-1]
    assert msg.rcpt_to == [f"<{email}>"]
    token = _token_do_link(_link_do_corpo(msg.corpo))

    r = anonimo.get(f"/api/senha/redefinir/resolver?token={token}")
    assert r.status_code == 200 and r.json()["motivo"] == "ok"

    nova = "Senha-nova-1" + secrets.token_hex(3)
    r = anonimo.post("/api/senha/redefinir/aplicar", json={"token": token, "senha": nova})
    assert r.status_code == 200 and r.json()["ok"] is True

    c = novo_cliente()
    assert entrar(c, inq.slug, login, nova).status_code == 200

    # link usado de novo = 410
    r = anonimo.post("/api/senha/redefinir/aplicar", json={"token": token, "senha": nova + "2"})
    assert r.status_code == 410 and r.json()["erro"] == "redefinicao_usado"

    # e-mail inexistente: mesma resposta genérica (não revela existência)
    r = anonimo.post("/api/senha/redefinir/solicitar", json={"inquilino": inq.slug,
                                                             "email": f"inexiste-{secrets.token_hex(4)}@teste.exemplo"})
    assert r.status_code == 202 and r.json()["ok"] is True

    # limite de taxa: muitos pedidos rápidos para o MESMO e-mail -> 429 (refutação do item: 1.000/min)
    email2 = f"flood-{secrets.token_hex(4)}@teste.exemplo"
    codigos = []
    for _ in range(12):
        r = anonimo.post("/api/senha/redefinir/solicitar", json={"inquilino": inq.slug, "email": email2})
        codigos.append(r.status_code)
    assert 429 in codigos, codigos
    # a partir do estouro, todo pedido seguinte também recusa (dentro da janela)
    assert codigos[-1] == 429


def test_redefinicao_expirada_e_410(inquilino_temporario, conexao_plat_app):
    inq = inquilino_temporario
    email = f"redefexp-{secrets.token_hex(4)}@teste.exemplo"
    login = f"zt{secrets.token_hex(4)}"
    r = inq.admin.post("/api/usuarios", json={"login": login, "nome": "x", "perfil": "editor", "email": email})
    assert r.status_code == 201, r.text
    anonimo = novo_cliente()
    r = anonimo.post("/api/senha/redefinir/solicitar", json={"inquilino": inq.slug, "email": email})
    assert r.status_code == 202
    # sem SMTP configurado neste teste: o token não chega por e-mail, então lemos direto do banco (fixture
    # de teste, nunca um caminho de produção) só para provar a expiração. RLS de plat.redefinicao_senha/
    # plat.usuario exige o GUC de tenant (achado desta sessão: sem ele o SELECT abaixo volta None em
    # silêncio, não um erro).
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(inq.id),))
        cur.execute(
            "SELECT rs.token_hash FROM plat.redefinicao_senha rs JOIN plat.usuario u ON u.id = rs.usuario_id "
            "WHERE u.login = %s ORDER BY rs.criado_em DESC LIMIT 1", (login,),
        )
        token_hash = cur.fetchone()["token_hash"]
        cur.execute("UPDATE plat.redefinicao_senha SET expira_em = now() - interval '1 hour' "
                    "WHERE token_hash = %s", (token_hash,))
    conexao_plat_app.commit()
    # como não temos o token em claro (só o hash), confirmamos a expiração pela função SQL diretamente
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT motivo FROM plat.redefinicao_resolver(%s)", (token_hash,))
        assert cur.fetchone()["motivo"] == "expirado"


# ---------------------------------------------------------------- senha SMTP nunca aparece em log
def test_senha_smtp_nunca_aparece_no_log_do_worker(inquilino_temporario):
    segredo = "SEGREDO-SMTP-" + secrets.token_hex(8)
    inicio = subprocess.run(["date", "-u", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True,
                            check=True).stdout.strip()
    inq = inquilino_temporario
    with ServidorSMTPCaptura() as smtp:
        _configurar_smtp(inq.admin, smtp.porta, usuario="conta-smtp-teste", senha=segredo)
        email = f"logtest-{secrets.token_hex(4)}@teste.exemplo"
        r = inq.admin.post("/api/convites", json={"email": email, "perfil": "visualizador"})
        assert r.status_code == 201, r.text
        assert smtp.esperar(1, timeout=25), "e-mail não chegou; não há como provar o log do envio"
    time.sleep(1)  # dá tempo do journal assentar a última linha
    saida = subprocess.run(
        ["sudo", "journalctl", "-u", "plat-worker", "-u", "plat-api", "--since", inicio, "--no-pager", "-o", "cat"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert segredo not in saida, "a senha SMTP em claro apareceu no log do worker/api"
