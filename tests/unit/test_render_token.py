"""Token interno de curta duração do motor de render (item L2-12-a-motor-render-servidor), cláusula do portão:
"token interno expira em ≤ 60 s e não serve fora do host". Puro, sem banco, sem playwright."""

import time

from app.render import token as render_token


def test_token_recem_gerado_e_valido():
    tok = render_token.gerar(30)
    assert render_token.validar(tok)


def test_token_expira_apos_o_prazo():
    tok = render_token.gerar(1)
    assert render_token.validar(tok)
    time.sleep(1.2)
    assert not render_token.validar(tok)


def test_prazo_pedido_e_sempre_cortado_a_60s():
    """A cláusula do portão é um TETO: mesmo pedindo um prazo maior, o token que sai nunca vale mais de 60 s."""
    antes = int(time.time())
    tok = render_token.gerar(3600)
    exp = int(tok.split(".")[0])
    assert exp - antes <= 60


def test_token_adulterado_e_recusado():
    tok = render_token.gerar(30)
    exp, nonce, assinatura = tok.split(".")
    adulterado = f"{exp}.{nonce}.{'0' * len(assinatura)}"
    assert not render_token.validar(adulterado)


def test_token_com_exp_trocado_e_recusado():
    tok = render_token.gerar(30)
    exp, nonce, assinatura = tok.split(".")
    trocado = f"{int(exp) + 3600}.{nonce}.{assinatura}"
    assert not render_token.validar(trocado)


def test_token_mal_formado_e_recusado():
    assert not render_token.validar("")
    assert not render_token.validar("qualquer-coisa")
    assert not render_token.validar("1.2.3.4")


def test_host_interno_aceita_loopback_e_recusa_qualquer_outro():
    assert render_token.host_e_interno("127.0.0.1")
    assert render_token.host_e_interno("::1")
    assert render_token.host_e_interno("localhost")
    assert not render_token.host_e_interno("10.0.0.5")
    assert not render_token.host_e_interno(None)
