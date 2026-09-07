"""Dupla-chave de `PLAT_SECRET` (item L7-19-segredos-e-certificados): `decifrar_com_rotacao` tenta o
valor ATUAL e cai para o ANTERIOR só se o atual falhar — nunca o contrário — e a mesma regra vale para a
verificação de HMAC de URL assinada em `app/objetos.py` (que não passa por `decifrar_com_rotacao`, é
comparação de assinatura, não decifragem, mas tem de sobreviver à rotação do mesmo jeito)."""

import dataclasses

import pytest

from app import objetos
from app.auth import totp
from app.seguranca_rotacao import decifrar_com_rotacao

ATUAL = "ab" * 32
ANTERIOR = "cd" * 32
TERCEIRO = "ef" * 32


def test_decifra_com_o_atual_quando_o_atual_funciona():
    segredo_totp = totp.gerar_segredo()
    armazenado = totp.cifrar(segredo_totp, ATUAL)
    assert decifrar_com_rotacao(totp.decifrar, armazenado, ATUAL, ANTERIOR) == segredo_totp


def test_cai_para_o_anterior_quando_o_atual_ja_mudou():
    """Simula o instante seguinte a uma rotação: o valor foi cifrado com o segredo que ACABOU de virar
    'anterior'; settings.PLAT_SECRET já é outro."""
    segredo_totp = totp.gerar_segredo()
    armazenado = totp.cifrar(segredo_totp, ANTERIOR)  # cifrado ANTES da rotação
    assert decifrar_com_rotacao(totp.decifrar, armazenado, ATUAL, ANTERIOR) == segredo_totp


def test_nunca_tenta_o_anterior_primeiro_o_atual_sempre_vence_quando_os_dois_decifrariam():
    """Se por algum motivo os dois decifrassem (não deveria acontecer: prefixo/AAD amarra a cifra a um
    segredo), o valor devolvido é sempre o do ATUAL — a ordem de tentativa é uma garantia, não um detalhe."""
    segredo_totp = totp.gerar_segredo()
    armazenado = totp.cifrar(segredo_totp, ATUAL)
    chamadas = []

    def decifrar_espiao(arm, seg):
        chamadas.append(seg)
        return totp.decifrar(arm, seg)

    decifrar_com_rotacao(decifrar_espiao, armazenado, ATUAL, ANTERIOR)
    assert chamadas == [ATUAL]  # nunca chegou a tentar o anterior


def test_sem_anterior_a_excecao_original_sobe():
    armazenado = totp.cifrar(totp.gerar_segredo(), TERCEIRO)
    with pytest.raises(Exception):  # noqa: B017 — a exceção real é InvalidTag do AEAD, não um tipo nosso
        decifrar_com_rotacao(totp.decifrar, armazenado, ATUAL, None)


def test_com_anterior_errado_tambem_a_excecao_sobe():
    armazenado = totp.cifrar(totp.gerar_segredo(), TERCEIRO)
    with pytest.raises(Exception):  # noqa: B017
        decifrar_com_rotacao(totp.decifrar, armazenado, ATUAL, ANTERIOR)


# ---------------------------------------------------------------- app/objetos.py: HMAC, não decifragem


def test_url_assinada_com_segredo_anterior_ainda_valida_durante_a_janela_de_rotacao(monkeypatch):
    """URL emitida ANTES da rotação (assinada com o que virou PLAT_SECRET_ANTERIOR) continua validando
    depois que settings.PLAT_SECRET já é outro — é a cláusula 'sessões abertas sobrevivem' do item."""
    url = objetos.url_assinada("demo/objeto/" + "a" * 64 + ".bin", 60, segredo=ANTERIOR)
    partes = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    ate = int(partes["ate"])
    assinatura = partes["assinatura"]
    chave = url.split("?", 1)[0].removeprefix("/api/objetos/")

    monkeypatch.setattr(
        objetos, "settings", dataclasses.replace(objetos.settings, PLAT_SECRET=ATUAL, PLAT_SECRET_ANTERIOR=ANTERIOR)
    )
    assert objetos.assinatura_valida(chave, ate, assinatura) is True


def test_url_assinada_sem_segredo_anterior_configurado_nao_valida_com_o_antigo(monkeypatch):
    url = objetos.url_assinada("demo/objeto/" + "a" * 64 + ".bin", 60, segredo=ANTERIOR)
    partes = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    ate = int(partes["ate"])
    assinatura = partes["assinatura"]
    chave = url.split("?", 1)[0].removeprefix("/api/objetos/")

    monkeypatch.setattr(
        objetos, "settings", dataclasses.replace(objetos.settings, PLAT_SECRET=ATUAL, PLAT_SECRET_ANTERIOR=None)
    )
    assert objetos.assinatura_valida(chave, ate, assinatura) is False


def test_url_assinada_com_o_atual_valida_mesmo_havendo_um_anterior_configurado(monkeypatch):
    url = objetos.url_assinada("demo/objeto/" + "a" * 64 + ".bin", 60, segredo=ATUAL)
    partes = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    ate = int(partes["ate"])
    assinatura = partes["assinatura"]
    chave = url.split("?", 1)[0].removeprefix("/api/objetos/")

    monkeypatch.setattr(
        objetos, "settings", dataclasses.replace(objetos.settings, PLAT_SECRET=ATUAL, PLAT_SECRET_ANTERIOR=ANTERIOR)
    )
    assert objetos.assinatura_valida(chave, ate, assinatura) is True


def test_terceiro_segredo_nao_valida_nem_com_anterior_configurado(monkeypatch):
    """Rotação de verdade: o valor de DUAS trocas atrás não é nem atual nem anterior — a URL emitida
    naquela época já devia ter expirado dentro das 24h da janela; não há uma terceira chave."""
    url = objetos.url_assinada("demo/objeto/" + "a" * 64 + ".bin", 60, segredo=TERCEIRO)
    partes = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    ate = int(partes["ate"])
    assinatura = partes["assinatura"]
    chave = url.split("?", 1)[0].removeprefix("/api/objetos/")

    monkeypatch.setattr(
        objetos, "settings", dataclasses.replace(objetos.settings, PLAT_SECRET=ATUAL, PLAT_SECRET_ANTERIOR=ANTERIOR)
    )
    assert objetos.assinatura_valida(chave, ate, assinatura) is False
