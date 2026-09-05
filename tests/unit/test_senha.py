from app.senha import ALGORITMO, gerar_hash, verificar


def test_hash_tem_formato_do_adr():
    h = gerar_hash("segredo-de-teste-1", iteracoes=1000)
    alg, it, salt, digest = h.split("$")
    assert alg == ALGORITMO and it == "1000" and len(salt) == 32 and len(digest) == 64


def test_verifica_certa_e_recusa_errada():
    h = gerar_hash("segredo-de-teste-1", iteracoes=1000)
    assert verificar("segredo-de-teste-1", h)
    assert not verificar("segredo-de-teste-2", h)
    assert not verificar("qualquer", "lixo")
