"""Texto canônico da licença (app/acervo/licenca.py, item L6-01-e-assinatura-e-uso): o MESMO texto vai à
lista, ao aceite gravado e ao LICENCA.txt do pacote — estas provas não tocam banco nem rede."""

from datetime import UTC, datetime

from app.acervo.licenca import atribuicao, ficha_licenca, obrigacao, sha256_texto, texto_licenca

LIC = {
    "fonte_id": "openstreetmap",
    "tipo": "ODbL",
    "url_licenca": "https://www.openstreetmap.org/copyright",
    "http_status": 200,
    "evidencia": "Open Data Commons Open Database License (ODbL)",
    "verificado_em": datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
}
FONTE = {"nome": "OpenStreetMap", "orgao": "OpenStreetMap Foundation"}


def test_texto_tem_tudo_que_o_aviso_exige():
    texto = texto_licenca(LIC, FONTE)
    assert "Licença: ODbL" in texto
    assert "https://www.openstreetmap.org/copyright" in texto
    assert "HTTP 200" in texto and "2026-09-06" in texto
    assert '"Open Data Commons Open Database License (ODbL)"' in texto  # trecho literal, entre aspas
    assert "Atribuição exigida: Dados de OpenStreetMap (OpenStreetMap Foundation), licença ODbL." in texto
    assert "compartilhamento pela mesma licença (share-alike)" in texto  # ODbL: atribuição E share-alike
    assert texto.endswith("\n")


def test_texto_sem_ficha_nao_inventa_nome():
    """Fonte fora da ficha (sem licença escrita no registro da casa): o texto cai para o fonte_id."""
    texto = texto_licenca(LIC, None)
    assert "Fonte: openstreetmap" in texto
    assert "OpenStreetMap Foundation" not in texto


def test_obrigacoes_por_tipo_e_fallback_honesto():
    assert "share-alike" in obrigacao("ODbL") and "share-alike" in obrigacao("CC-BY-SA")
    assert "atribuição" in obrigacao("CC-BY")
    assert "domínio público" in obrigacao("CC0")
    # tipo fora do mapa não ganha frase inventada: cai no termo genérico do endereço verificado
    assert obrigacao("tipo-inexistente") == "vale o termo publicado no endereço verificado abaixo"


def test_atribuicao_prefere_nome_e_orgao_quando_existem():
    assert atribuicao("openstreetmap", "OpenStreetMap", None, "ODbL") == "Dados de OpenStreetMap, licença ODbL."
    assert atribuicao("openstreetmap", None, None, "ODbL") == "Dados de openstreetmap, licença ODbL."


def test_sha_do_texto_e_estavel_e_sensivel_ao_conteudo():
    a = sha256_texto("mesmo texto")
    assert a == sha256_texto("mesmo texto") and a != sha256_texto("outro texto")
    assert len(a) == 64


def test_ficha_licenca_sem_linha_curada_e_none():
    """Sem linha em plat.acervo_licenca não existe ficha — o chamador recusa a operação (regra D17)."""

    class CurVazio:
        def execute(self, *a):
            pass

        def fetchone(self):
            return None

    assert ficha_licenca(CurVazio(), "qualquer") is None
