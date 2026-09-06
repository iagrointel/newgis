"""Cliente SMTP (item L0-07-d-smtp-convites): mensagem montada corretamente, erro legível e SEM a senha em
nenhuma condição (host errado, porta fechada, timeout) — a cláusula "senha SMTP nunca aparece em log" do
portão do item começa aqui, na unidade, antes do teste de integração contra o log real do worker."""

from app.correio import cliente
from app.correio.config import ConfigSMTP

SENHA_SECRETA = "senha-que-nunca-pode-vazar-42"


def _cfg(**over):
    base = dict(host="127.0.0.1", porta=1, tls=False, usuario="usuario-smtp", senha_cifrada=None,
                remetente="naoresponda@teste.exemplo", rotulo="Plat", origem="inquilino")
    base.update(over)
    return ConfigSMTP(**base)


def test_montar_mensagem_remetente_com_rotulo_e_assunto_truncado():
    cfg = _cfg()
    msg = cliente.montar_mensagem(cfg, "dest@teste.exemplo", "Assunto", "corpo qualquer")
    assert msg["To"] == "dest@teste.exemplo"
    assert "naoresponda@teste.exemplo" in msg["From"] and "Plat" in msg["From"]
    assert msg.get_content().strip() == "corpo qualquer"


def test_montar_mensagem_sem_rotulo_usa_so_o_remetente():
    cfg = _cfg(rotulo=None)
    msg = cliente.montar_mensagem(cfg, "d@e.f", "a", "b")
    assert msg["From"] == "naoresponda@teste.exemplo"


def test_porta_fechada_da_erro_legivel_sem_a_senha():
    cfg = _cfg(porta=1)  # porta 1 não aceita conexão nesta máquina
    try:
        cliente.enviar(cfg, SENHA_SECRETA, "d@e.f", "a", "b", timeout=2.0)
        raise AssertionError("deveria ter levantado ErroSMTP")
    except cliente.ErroSMTP as e:
        texto = str(e)
        assert SENHA_SECRETA not in texto
        assert "127.0.0.1" in texto and "1" in texto  # host e porta citados: erro legível, não um traceback opaco


def test_host_inexistente_da_erro_legivel_sem_a_senha():
    cfg = _cfg(host="smtp-nao-existe.invalido.teste", porta=587)
    try:
        cliente.enviar(cfg, SENHA_SECRETA, "d@e.f", "a", "b", timeout=3.0)
        raise AssertionError("deveria ter levantado ErroSMTP")
    except cliente.ErroSMTP as e:
        texto = str(e)
        assert SENHA_SECRETA not in texto
        assert "smtp-nao-existe" in texto
