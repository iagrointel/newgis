"""Ataque adversarial ao item L7-16-assinatura-pacote (turno 3, grupo G6).

Refutação literal do item: "adversário monta pacote assinado com chave própria e tenta instalar; tenta
substituir a chave pública embutida via variável de ambiente ou arquivo de configuração".

Estado em 15/09/2026: os dois achados graves (1: quem assina virava confiável sozinho; 3: `.sig` não
amarrava identidade do pacote) estão CONSERTADOS — os testes correspondentes tiveram a marca
`xfail(strict=True)` removida (o motivo original fica como comentário acima de cada um) e
`test_pacote_forjado_e_recusado_e_legitimo_e_aceito_no_caminho_padrao`, no fim deste arquivo, é a prova
positiva do portão de pronto ("o pacote forjado é recusado, o legítimo é aceito") pelo caminho PADRÃO,
sem xfail. Dois testes continuam `xfail(strict=True)`: `test_variavel_de_ambiente_...` contradiz o
controle `test_o_que_aguentou_um_byte_alterado_e_recusado` (mesma chamada, resultado oposto esperado —
ver `laco/handoffs/T3/G6-CONSERTO-seguranca.md` §"Os 14 xfail que continuam"; a garantia real de
produção está em `tests/unit/test_release_seguranca.py::test_em_producao_a_variavel_de_ambiente_nao_
troca_a_lista`) e `test_artefatos_prometidos_pela_hipotese_existem` registra que `scripts/empacotar.sh`
da HIPÓTESE do item nunca foi construído (decisão deliberada: um script só para satisfazer a checagem
seria placeholder)."""

import json
import tarfile
from pathlib import Path

import pytest

from tests.adversario_raiz.apoio_g6 import RAIZ, rodar

ITEM = "L7-16-assinatura-pacote"


def _pacote(tmp_path: Path, nome="plat-9.9.9.tar.gz", conteudo=b"carga do atacante\n") -> Path:
    alvo = tmp_path / "carga.txt"
    alvo.write_bytes(conteudo)
    pacote = tmp_path / nome
    with tarfile.open(pacote, "w:gz") as t:
        t.add(alvo, arcname="carga.txt")
    return pacote


# CONSERTADO em 15/09/2026 (marca xfail(strict=True) removida; motivo original mantido como registro):
# L7-16: assinar_pacote.sh grava a PRÓPRIA chave pública nova em deploy/chaves_publicas_release.txt
# (o mesmo arquivo que verificar_pacote.sh consulta). Quem assina passa a ser confiável por construção:
# um pacote assinado com chave de terceiro é ACEITO pelo caminho padrão, sem nenhuma variável de ambiente.
# Conserto: separar o arquivo de confiança do produto do arquivo que a ferramenta de assinatura escreve
# (scripts/plat_assinatura.py::registrar_chave_publica só escreve com a lista vazia, âncora inicial).
def test_assinar_nao_pode_tornar_a_propria_chave_confiavel(tmp_path):
    pacote = _pacote(tmp_path)
    confiaveis = RAIZ / "deploy" / "chaves_publicas_release.txt"
    antes = confiaveis.read_text(encoding="utf-8")
    try:
        cod, _, _ = rodar(
            ["bash", "scripts/assinar_pacote.sh", str(pacote)], env={"HOME": str(tmp_path / "casa")}
        )
        assert cod == 0
        depois = confiaveis.read_text(encoding="utf-8")
        assert depois == antes, "a ferramenta de assinatura alterou o arquivo de confiança do produto"
        cod_v, _, _ = rodar(["bash", "scripts/verificar_pacote.sh", str(pacote)])
        assert cod_v != 0, "pacote assinado com chave de terceiro foi aceito pelo caminho padrão"
    finally:
        confiaveis.write_text(antes, encoding="utf-8")


@pytest.mark.xfail(
    strict=True,
    reason="L7-16 (refutação literal do item): PLAT_CHAVES_CONFIAVEIS troca a lista de chaves confiáveis por "
    "um arquivo do atacante, e verificar_pacote.sh aceita. A 'chave pública embutida no código' não existe: "
    "é um arquivo de texto cujo caminho vem do ambiente.",
)
def test_variavel_de_ambiente_nao_pode_substituir_a_lista_de_chaves(tmp_path):
    pacote = _pacote(tmp_path)
    priv = tmp_path / "atacante.pem"
    confiaveis_falso = tmp_path / "confiaveis_do_atacante.txt"
    rodar(
        [
            "venv/bin/python",
            "scripts/plat_assinatura.py",
            "gerar-chave",
            "--chave-privada",
            str(priv),
            "--confiaveis",
            str(confiaveis_falso),
        ]
    )
    rodar(
        [
            "venv/bin/python",
            "scripts/plat_assinatura.py",
            "assinar",
            str(pacote),
            "--chave-privada",
            str(priv),
            "--saida",
            str(pacote) + ".sig",
        ]
    )
    cod, saida, _ = rodar(
        ["bash", "scripts/verificar_pacote.sh", str(pacote)],
        env={"PLAT_CHAVES_CONFIAVEIS": str(confiaveis_falso)},
    )
    assert cod != 0, f"chave do atacante aceita por variável de ambiente: {saida}"


# CONSERTADO em 15/09/2026 (marca xfail(strict=True) removida; motivo original mantido como registro):
# L7-16: os campos 'arquivo' e 'tamanho_bytes' do .sig ficavam FORA do que a assinatura cobria (Ed25519
# assinava só os bytes do pacote). O .sig não amarrava nome, versão, data nem validade — não havia como
# recusar repetição (replay) nem regressão de versão. Conserto: assina-se uma DECLARAÇÃO canônica (nome,
# tamanho, sha256, versão, data) e `cmd_verificar` recusa (saída 2) qualquer campo fora do formato
# assinado — inclusive um "arquivo"/"tamanho_bytes" solto no nível de cima, exatamente o que este teste
# tenta colar. Ver scripts/plat_assinatura.py::cmd_verificar, lista `campos_conhecidos`.
def test_sig_precisa_amarrar_nome_e_tamanho_do_pacote(tmp_path):
    pacote = _pacote(tmp_path)
    priv = tmp_path / "chave.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    rodar(
        ["venv/bin/python", "scripts/plat_assinatura.py", "gerar-chave", "--chave-privada", str(priv),
         "--confiaveis", str(confiaveis)]
    )
    sig = Path(str(pacote) + ".sig")
    rodar(
        ["venv/bin/python", "scripts/plat_assinatura.py", "assinar", str(pacote), "--chave-privada", str(priv),
         "--saida", str(sig)]
    )
    info = json.loads(sig.read_text(encoding="utf-8"))
    info["arquivo"] = "plat-0.0.1-inofensivo.tar.gz"
    info["tamanho_bytes"] = 1
    sig.write_text(json.dumps(info), encoding="utf-8")
    cod, _, _ = rodar(
        ["bash", "scripts/verificar_pacote.sh", str(pacote)], env={"PLAT_CHAVES_CONFIAVEIS": str(confiaveis)}
    )
    assert cod != 0, "o .sig com nome e tamanho mentirosos foi aceito: esses campos não são assinados"


@pytest.mark.xfail(
    strict=True,
    reason="L7-16 (hipótese do item): prometia scripts/empacotar.sh gerando plat-X.Y.Z.tar.zst + "
    "MANIFESTO.sha256 + MANIFESTO.sig e o comando `plat verificar-pacote`. Nenhum dos quatro existe.",
)
def test_artefatos_prometidos_pela_hipotese_existem():
    faltando = [
        n
        for n in ("scripts/empacotar.sh",)
        if not (RAIZ / n).exists()
    ]
    assert not faltando, f"artefatos da hipótese ausentes: {faltando}"


def test_o_que_aguentou_um_byte_alterado_e_recusado(tmp_path):
    """Não é refutação: a conta Ed25519 em si está correta. Fica registrado para não ser desfeito."""
    pacote = _pacote(tmp_path)
    priv = tmp_path / "chave.pem"
    confiaveis = tmp_path / "confiaveis.txt"
    rodar(["venv/bin/python", "scripts/plat_assinatura.py", "gerar-chave", "--chave-privada", str(priv),
           "--confiaveis", str(confiaveis)])
    rodar(["venv/bin/python", "scripts/plat_assinatura.py", "assinar", str(pacote), "--chave-privada", str(priv),
           "--saida", str(pacote) + ".sig"])
    amb = {"PLAT_CHAVES_CONFIAVEIS": str(confiaveis)}
    assert rodar(["bash", "scripts/verificar_pacote.sh", str(pacote)], env=amb)[0] == 0
    dados = bytearray(pacote.read_bytes())
    dados[-1] ^= 0xFF
    pacote.write_bytes(bytes(dados))
    assert rodar(["bash", "scripts/verificar_pacote.sh", str(pacote)], env=amb)[0] == 4


def test_pacote_forjado_e_recusado_e_legitimo_e_aceito_no_caminho_padrao(tmp_path):
    """Prova POSITIVA do conserto do achado 1/2 (não é xfail; é o portão de pronto do item: 'o pacote
    forjado é recusado, o legítimo é aceito' pelo caminho PADRÃO).

    Parte 1 — forjado: um atacante qualquer gera a própria chave, assina um pacote com ela, e tenta
    passar pelo caminho padrão de produção (`PLAT_AMBIENTE=producao`, sem `PLAT_CHAVES_CONFIAVEIS`,
    sem `APP_DIR`, contra a lista de confiança REAL do repositório em `deploy/chaves_publicas_release.txt`
    — a mesma que a hipótese do item chama de 'chave pública embutida no código'). Tem de ser recusado.

    Parte 2 — legítimo: uma chave que ESTA instalação de teste confia (registrada como âncora numa lista
    de confiança isolada, pelo mesmo mecanismo que popula `deploy/chaves_publicas_release.txt` numa
    instalação nova — nunca a chave privada real de produção, que fica fora do repositório de propósito)
    assina outro pacote; a verificação contra essa lista isolada tem de aceitar.
    """
    # -- forjado: caminho padrão de produção, lista de confiança real do produto --
    pacote_forjado = _pacote(tmp_path, nome="plat-9.9.9-forjado.tar.gz")
    priv_atacante = tmp_path / "atacante.pem"
    confiaveis_do_atacante = tmp_path / "confiaveis_do_atacante.txt"
    rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "gerar-chave",
            "--chave-privada", str(priv_atacante), "--confiaveis", str(confiaveis_do_atacante),
        ]
    )
    rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "assinar", str(pacote_forjado),
            "--chave-privada", str(priv_atacante), "--saida", str(pacote_forjado) + ".sig",
        ]
    )
    cod_forjado, saida_forjado, erro_forjado = rodar(
        ["bash", "scripts/verificar_pacote.sh", str(pacote_forjado)], env={"PLAT_AMBIENTE": "producao"}
    )
    assert cod_forjado == 3, (
        f"pacote forjado (chave de atacante, fora da lista de confiança do produto) foi aceito pelo "
        f"caminho padrão de produção: saida={cod_forjado} stdout={saida_forjado!r} stderr={erro_forjado!r}"
    )
    assert "não é confiável" in erro_forjado

    # -- legítimo: chave confiável desta instalação, lista isolada (nunca deploy/chaves_publicas_release.txt) --
    pacote_legitimo = _pacote(tmp_path, nome="plat-9.9.9-legitimo.tar.gz")
    priv_legitima = tmp_path / "legitima.pem"
    lista_isolada = tmp_path / "confiaveis_isolada.txt"
    rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "gerar-chave",
            "--chave-privada", str(priv_legitima), "--confiaveis", str(lista_isolada),
        ]
    )
    assert lista_isolada.exists() and lista_isolada.read_text(encoding="utf-8").strip(), (
        "a chave legítima não foi registrada como âncora na lista isolada"
    )
    rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "assinar", str(pacote_legitimo),
            "--chave-privada", str(priv_legitima), "--saida", str(pacote_legitimo) + ".sig",
        ]
    )
    cod_legitimo, saida_legitimo, erro_legitimo = rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "verificar", str(pacote_legitimo),
            "--assinatura", str(pacote_legitimo) + ".sig", "--confiaveis", str(lista_isolada),
        ]
    )
    assert cod_legitimo == 0, (
        f"pacote legítimo (chave confiável desta instalação) foi recusado: saida={cod_legitimo} "
        f"stdout={saida_legitimo!r} stderr={erro_legitimo!r}"
    )

    # -- e o forjado não vira legítimo só por trocar de lista sem ser o dono dela: a chave do atacante
    # continua fora da lista isolada também --
    cod_cruzado, _, erro_cruzado = rodar(
        [
            "venv/bin/python", "scripts/plat_assinatura.py", "verificar", str(pacote_forjado),
            "--assinatura", str(pacote_forjado) + ".sig", "--confiaveis", str(lista_isolada),
        ]
    )
    assert cod_cruzado == 3, f"chave do atacante foi aceita pela lista isolada também: {erro_cruzado}"
