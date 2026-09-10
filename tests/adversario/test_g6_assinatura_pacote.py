"""Ataque adversarial ao item L7-16-assinatura-pacote (turno 3, grupo G6).

Refutação literal do item: "adversário monta pacote assinado com chave própria e tenta instalar; tenta
substituir a chave pública embutida via variável de ambiente ou arquivo de configuração". As duas
passam. Todos os testes deste arquivo estão `xfail(strict=True)`: quando o produto for consertado eles
viram prova e a suíte acusa quem afrouxar de novo."""

import json
import tarfile
from pathlib import Path

import pytest

from tests.adversario.apoio_g6 import RAIZ, rodar

ITEM = "L7-16-assinatura-pacote"


def _pacote(tmp_path: Path, nome="plat-9.9.9.tar.gz", conteudo=b"carga do atacante\n") -> Path:
    alvo = tmp_path / "carga.txt"
    alvo.write_bytes(conteudo)
    pacote = tmp_path / nome
    with tarfile.open(pacote, "w:gz") as t:
        t.add(alvo, arcname="carga.txt")
    return pacote


# CONSERTADO em 06/09/2026 (turno 3, trilha `segur`): este teste era xfail(strict=True) e passou a
# PASSAR. A marca saiu; a asserção do adversário fica intacta. Motivo original registrado por ele:
# @pytest.mark.xfail(
#     strict=True,
#     reason="L7-16: assinar_pacote.sh grava a PRÓPRIA chave pública nova em deploy/chaves_publicas_release.txt "
#     "(o mesmo arquivo que verificar_pacote.sh consulta). Quem assina passa a ser confiável por construção: "
#     "um pacote assinado com chave de terceiro é ACEITO pelo caminho padrão, sem nenhuma variável de ambiente. "
#     "Conserto: separar o arquivo de confiança do produto do arquivo que a ferramenta de assinatura escreve.",
# )
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


# CONSERTADO em 06/09/2026 (turno 3, trilha `segur`): este teste era xfail(strict=True) e passou a
# PASSAR. A marca saiu; a asserção do adversário fica intacta. Motivo original registrado por ele:
# @pytest.mark.xfail(
#     strict=True,
#     reason="L7-16: os campos 'arquivo' e 'tamanho_bytes' do .sig ficam FORA do que a assinatura cobre "
#     "(Ed25519 assina só os bytes do pacote). O .sig não amarra nome, versão, data nem validade — não há "
#     "como recusar repetição (replay) nem regressão de versão. Conserto: assinar um manifesto que contenha "
#     "esses campos, não o arquivo cru.",
# )
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
