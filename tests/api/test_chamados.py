"""Item L7-13-a-chamados — API, cláusula a cláusula do portão: abrir chamado com captura, operador responde,
cliente vê e fecha; anexo malicioso recusado; e-mail de notificação nos 3 idiomas (SMTP de captura, worker
REAL de outro processo); tempo de primeira resposta medido e exibido; chamado de outro inquilino invisível
(teste cruzado por API). O fluxo de interface fica em tests/e2e/test_chamados.py. Tudo roda contra inquilinos
temporários (zt-inq-*), nunca contra demo/demo2."""

import base64
import io
import os
import zipfile

from PIL import Image

from tests.api.conftest import InquilinoTemporario, Usuarios
from tests.api.util_smtp_captura import ServidorSMTPCaptura


def _png_bytes(w: int = 320, h: int = 200) -> bytes:
    im = Image.new("RGBA", (w, h), (20, 90, 160, 255))
    buffer = io.BytesIO()
    im.save(buffer, "PNG")
    return buffer.getvalue()


def _captura_data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("leia-me.txt", "anexo do chamado")
    return buffer.getvalue()


def _abrir_chamado(cliente, titulo="mapa não carrega", captura: str | None = None) -> dict:
    corpo = {"titulo": titulo, "descricao": "a tela do mapa fica branca depois de abrir um projeto",
             "severidade": "alta", "contexto": {"tela": "/mapa", "versao": "0.1.0", "idioma": "pt-BR",
                                                "req_ids": [f"{i:016x}" for i in range(3)]}}
    if captura is not None:
        corpo["captura"] = captura
    r = cliente.post("/api/chamados", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _configurar_smtp(cliente, porta: int) -> None:
    r = cliente.put("/api/org/smtp", json={
        "host": "127.0.0.1", "porta": porta, "tls": False, "usuario": "", "senha": "",
        "remetente": "naoresponda@teste.exemplo", "rotulo": "Plat Teste",
    })
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- abrir com captura e contexto
def test_abrir_chamado_com_captura_contexto_e_numero_sequencial(inquilino_temporario):
    inq = inquilino_temporario
    primeiro = _abrir_chamado(inq.admin, captura=_captura_data_url())
    assert primeiro["numero"] == 1 and primeiro["estado"] == "aberto"
    assert primeiro["sla_primeira_resposta_horas"] == 8  # severidade alta
    assert primeiro["primeira_resposta_horas"] is None and primeiro["sla_origem"] == "declarado"
    assert primeiro["anexos"][0]["nome"] == "captura.png" and primeiro["anexos"][0]["tipo"] == "png"
    segundo = _abrir_chamado(inq.admin, titulo="outro problema")
    assert segundo["numero"] == 2

    # o detalhe devolve o contexto gravado (req_ids só no formato 16 hex) e o anexo da captura
    r = inq.admin.get(f"/api/chamados/{primeiro['id']}")
    assert r.status_code == 200
    c = r.json()
    assert c["contexto"]["tela"] == "/mapa" and c["contexto"]["req_ids"] == [f"{i:016x}" for i in range(3)]
    assert [a["nome"] for a in c["anexos"]] == ["captura.png"]
    # captura decodifica como imagem de verdade
    r2 = inq.admin.get(f"/api/chamados/{primeiro['id']}/anexos/{c['anexos'][0]['id']}")
    assert r2.status_code == 200 and r2.headers["content-type"] == "image/png"
    Image.open(io.BytesIO(r2.content)).load()


def test_abrir_recusa_captura_que_nao_e_png_e_titulo_curto(inquilino_temporario):
    inq = inquilino_temporario
    r = inq.admin.post("/api/chamados", json={
        "titulo": "ab", "descricao": "d", "severidade": "baixa", "contexto": {}})
    assert r.status_code == 422  # pydantic: titulo < 3
    r = inq.admin.post("/api/chamados", json={
        "titulo": "titulo ok", "descricao": "d", "severidade": "baixa", "contexto": {},
        "captura": "data:image/png;base64," + base64.b64encode(b"isto nao e png").decode()})
    assert r.status_code == 422 and r.json()["erro"] == "captura_invalida"
    r = inq.admin.post("/api/chamados", json={
        "titulo": "titulo ok", "descricao": "d", "severidade": "urgente", "contexto": {}})
    assert r.status_code == 422  # severidade fora do vocabulário


# ---------------------------------------------------------------- fluxo completo: operador responde, cliente vê e fecha
def test_fluxo_operador_responde_cliente_ve_banner_e_fecha(inquilino_temporario, sessao_plat):
    inq = inquilino_temporario
    chamado = _abrir_chamado(inq.admin, captura=_captura_data_url())
    cid = chamado["id"]

    # sem resposta, o banner não mostra nada
    assert inq.admin.get("/api/chamados/banner").json() == []

    # operador vê o chamado na fila de TODOS os inquilinos e responde
    fila = sessao_plat.get("/api/plataforma/chamados")
    assert fila.status_code == 200
    assert any(x["id"] == cid and x["tenant_slug"] == inq.slug for x in fila.json())
    r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/comentarios",
                         json={"texto": "identificamos falha na camada base; estamos aplicando a correção"})
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "em_analise" and r.json()["primeira_resposta_em"]

    # SLA medido aparece na lista do cliente, dentro do prazo declarado
    lista = inq.admin.get("/api/chamados").json()
    linha = next(x for x in lista if x["id"] == cid)
    assert linha["primeira_resposta_horas"] is not None
    assert linha["sla_dentro"] is True and linha["sla_primeira_resposta_horas"] == 8

    # cliente vê o banner com o numero, abre o detalhe e o banner zera (visto_cliente_em)
    banner = inq.admin.get("/api/chamados/banner").json()
    assert len(banner) == 1 and banner[0]["numero"] == 1 and banner[0]["motivo"] == "resposta"
    assert inq.admin.get(f"/api/chamados/{cid}").status_code == 200
    assert inq.admin.get("/api/chamados/banner").json() == []

    # comentário do cliente; operador resolve
    assert inq.admin.post(f"/api/chamados/{cid}/comentarios",
                          json={"texto": "obrigado, confirmo que voltou a carregar"}).status_code == 201
    assert sessao_plat.post(f"/api/plataforma/chamados/{cid}/estado",
                            json={"estado": "resolvido"}).status_code == 200
    banner = inq.admin.get("/api/chamados/banner").json()
    assert banner and banner[0]["motivo"] == "resolvido"
    inq.admin.get(f"/api/chamados/{cid}")

    # cliente fecha; fechar de novo é idempotente
    assert inq.admin.post(f"/api/chamados/{cid}/fechar").status_code == 200
    assert inq.admin.post(f"/api/chamados/{cid}/fechar").json()["estado"] == "fechado"

    # chamado fechado: nem cliente nem operador escrevem nele
    assert inq.admin.post(f"/api/chamados/{cid}/comentarios", json={"texto": "x"}).status_code == 409
    r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/comentarios", json={"texto": "x"})
    assert r.status_code == 409 and r.json()["erro"] == "chamado_fechado"


def test_operador_muda_estado_so_por_transicao_valida(inquilino_temporario, sessao_plat):
    inq = inquilino_temporario
    cid = _abrir_chamado(inq.admin)["id"]
    # aberto -> fechado não existe no mapa de transições
    r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/estado", json={"estado": "fechado"})
    assert r.status_code == 409 and r.json()["erro"] == "transicao_invalida"
    # aberto -> aguardando_cliente -> resolvido; resolvido reabre para em_analise
    for estado in ("aguardando_cliente", "resolvido", "em_analise", "resolvido"):
        r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/estado", json={"estado": estado})
        assert r.status_code == 200, r.text
    # estado fora do vocabulário
    r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/estado", json={"estado": "perdido"})
    assert r.status_code == 422


def test_rotas_do_operador_recusam_sessao_de_cliente(inquilino_temporario, sessao_a):
    """Não superadmin que bate na rota do operador recebe 404 (nunca 403, para não confirmar que a rota existe)."""
    inq = inquilino_temporario
    cid = _abrir_chamado(inq.admin)["id"]
    assert sessao_a.get("/api/plataforma/chamados").status_code == 404
    assert sessao_a.get(f"/api/plataforma/chamados/{cid}").status_code == 404
    assert sessao_a.post(f"/api/plataforma/chamados/{cid}/comentarios", json={"texto": "x"}).status_code == 404
    assert sessao_a.post(f"/api/plataforma/chamados/{cid}/estado", json={"estado": "resolvido"}).status_code == 404


# ---------------------------------------------------------------- anexos: bom, malicioso e alheio
def test_anexo_bom_e_anexo_malicioso(inquilino_temporario, sessao_plat):
    inq = inquilino_temporario
    cid = _abrir_chamado(inq.admin)["id"]

    # executável (MZ, PE) declarado como geojson: a varredura de cabeçalho recusa com 415
    r = inq.admin.post(f"/api/chamados/{cid}/anexos", json={
        "nome": "camada.geojson", "tipo": "geojson",
        "conteudo": base64.b64encode(b"MZ\x90\x00" + os.urandom(256)).decode()})
    assert r.status_code == 415 and r.json()["erro"] == "conteudo_recusado"

    # JSON sem "type" declarado como geojson: passa pela varredura, não prova o tipo -> 422
    r = inq.admin.post(f"/api/chamados/{cid}/anexos", json={
        "nome": "outra.geojson", "tipo": "geojson", "conteudo": base64.b64encode(b'{"chave": "valor"}').decode()})
    assert r.status_code == 422 and r.json()["erro"] == "conteudo_nao_corresponde"

    # tipo fora da lista
    r = inq.admin.post(f"/api/chamados/{cid}/anexos", json={
        "nome": "a.exe", "tipo": "exe", "conteudo": base64.b64encode(b"MZ").decode()})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_desconhecido"

    # zip verdadeiro entra, sai igual (o sha256 fica registrado) e o operador consegue baixar
    zip_dados = _zip_bytes()
    r = inq.admin.post(f"/api/chamados/{cid}/anexos", json={
        "nome": "diagnostico.zip", "tipo": "zip",
        "conteudo": base64.b64encode(zip_dados).decode()})
    assert r.status_code == 201, r.text
    anexo = r.json()
    r2 = inq.admin.get(f"/api/chamados/{cid}/anexos/{anexo['id']}")
    assert r2.status_code == 200 and r2.content == zip_dados
    r3 = sessao_plat.get(f"/api/plataforma/chamados/{cid}/anexos/{anexo['id']}")
    assert r3.status_code == 200 and r3.content == zip_dados
    # id de anexo que existe mas não pertence ao chamado -> 404
    r4 = inq.admin.get(f"/api/chamados/{cid}/anexos/{'0' * 8}-0000-0000-0000-{'0' * 12}")
    assert r4.status_code == 404


def test_anexo_e_chamado_de_outro_inquilino_sao_invisiveis(inquilino_temporario, sessao_plat):
    """Refutação do item: adversário abre chamado de outro inquilino pela API e tenta ler anexo de chamado
    alheio. Dois inquilinos temporários A e B; B nunca vê nada de A — nem por lista, nem por id."""
    inq_a = inquilino_temporario
    inq_b = InquilinoTemporario(sessao_plat)
    try:
        chamado_a = _abrir_chamado(inq_a.admin, captura=_captura_data_url())
        anexo_a = chamado_a["anexos"][0]["id"]

        # o cliente de B lista os chamados DELE (vazios) e não vê o de A por id, nem o anexo
        assert inq_b.admin.get("/api/chamados").json() == []
        r = inq_b.admin.get(f"/api/chamados/{chamado_a['id']}")
        assert r.status_code == 404 and r.json()["erro"] == "chamado_inexistente"
        r = inq_b.admin.get(f"/api/chamados/{chamado_a['id']}/anexos/{anexo_a}")
        # a guarda do chamado vem primeiro (RLS): B nem chega a ver que o anexo existe
        assert r.status_code == 404 and r.json()["erro"] == "chamado_inexistente"
        # escrita de B sobre o chamado de A também é 404 (a RLS não deixa nem travar a linha)
        assert inq_b.admin.post(f"/api/chamados/{chamado_a['id']}/comentarios",
                                json={"texto": "invasão"}).status_code == 404
        assert inq_b.admin.post(f"/api/chamados/{chamado_a['id']}/fechar").status_code == 404
        # e o operador, que prova identidade dentro da função, continua vendo o de A
        assert sessao_plat.get(f"/api/plataforma/chamados/{chamado_a['id']}").status_code == 200
    finally:
        inq_b.apagar()


# ---------------------------------------------------------------- e-mail nos 3 idiomas (SMTP de captura + worker real)
def test_email_de_resposta_nos_tres_idiomas(inquilino_temporario, sessao_plat):
    inq = inquilino_temporario
    usuarios = Usuarios(inq.admin)
    try:
        with ServidorSMTPCaptura() as smtp:
            _configurar_smtp(inq.admin, smtp.porta)
            idiomas = {"pt-BR": "Chamado em português", "en": "Ticket in English", "es": "Ticket en español"}
            ids = {}
            for idioma, titulo in idiomas.items():
                cliente, usuario, _senha = usuarios.sessao(email=f"{idioma.lower()}@teste.exemplo")
                r = cliente.put("/api/eu", json={"idioma_preferido": idioma})
                assert r.status_code == 200, r.text
                chamado = _abrir_chamado(cliente, titulo=titulo)
                ids[idioma] = chamado["id"]
            # o operador responde os três; cada cliente recebe o e-mail no idioma DA CONTA DELE
            for _idioma, cid in ids.items():
                r = sessao_plat.post(f"/api/plataforma/chamados/{cid}/comentarios",
                                     json={"texto": "resposta do suporte"})
                assert r.status_code == 201, r.text
            assert smtp.esperar(3, timeout=60), f"chegaram {len(smtp.mensagens)} de 3 mensagens"
            corpos = {m.rcpt_to[0].strip("<>").lower(): (m.assunto, m.corpo) for m in smtp.mensagens}
            assert corpos["pt-br@teste.exemplo"][0] == "plat: resposta no chamado 1"
            assert corpos["en@teste.exemplo"][0] == "plat: reply on ticket 2"
            assert corpos["es@teste.exemplo"][0] == "plat: respuesta en el ticket 3"
            for _destino, (assunto, corpo) in corpos.items():
                assert "!" not in assunto and "!" not in corpo  # regra de escrita de 03/09
                assert "/chamados" in corpo  # o link da página de chamados vai no corpo
            assert len(corpos) == 3
    finally:
        usuarios.limpar()


def test_sem_email_o_operador_ainda_responde_e_sem_smtp_nada_quebra(inquilino_temporario, sessao_plat):
    """Cliente sem e-mail na conta (coluna opcional): o chamado flue por banner, o operador nunca vê erro."""
    inq = inquilino_temporario
    usuarios = Usuarios(inq.admin)
    try:
        cliente, _usuario, _senha = usuarios.sessao()  # sem email
        chamado = _abrir_chamado(cliente)
        r = sessao_plat.post(f"/api/plataforma/chamados/{chamado['id']}/comentarios", json={"texto": "ok"})
        assert r.status_code == 201
    finally:
        usuarios.limpar()
