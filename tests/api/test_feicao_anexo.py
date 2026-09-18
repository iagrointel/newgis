"""Portão do item L2-03-e-anexos, medido sobre o código que JÁ está no tronco (`app/edicao/anexos.py`,
tabela `plat.feicao_anexo`).

Escopo deste arquivo (o que a remedição pediu): teto de TAMANHO, teto de TIPO, apagar LÓGICO e
ISOLAMENTO por inquilino. Cada recusa vem com o par positivo na mesma cláusula — o anexo legítimo do
mesmo tamanho/tipo/dono passa —, senão um código que recusasse tudo passaria neste arquivo.

O que ficou de fora e por quê (cláusulas do portão do item que o tronco NÃO implementa hoje; ver a
medida em tests/medidas/L2-03-e-anexos.json): miniatura de JPG/PDF, remoção de EXIF de GPS, URL direta
do Garage devolvendo 403 e "apagar feição apaga anexos". Nenhuma delas tem rota nem coluna em
`app/edicao/anexos.py`; medir o que não existe daria falso verde.

Divergência medida entre o portão e o código: o portão escreveu "acima do limite = 413"; o servidor
responde **422 `anexo_grande`** (o 413 do middleware de corpo dispararia antes e esconderia o motivo —
ver `test_anexo_no_teto_real_ainda_da_anexo_grande_nao_corpo_grande` em
tests/api/test_edicao_historico_anexos.py). O teste abaixo mede o comportamento REAL e o
`test_teto_de_tamanho_responde_413_como_o_portao_pediu` registra a divergência como xfail — não se
afrouxou nada para passar.
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app import limites
from tests.api.test_edicao_transacional import (  # noqa: F401 — fixtures reaproveitadas
    _ponto,
    camada_a,
    camada_b,
    fabrica,
)
from tests.api.test_rls import contexto

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def _png_de(bytes_minimos: int) -> bytes:
    """PNG DE VERDADE com pelo menos `bytes_minimos` bytes. Encher um cabeçalho de PNG com zeros não
    serve: a varredura de conteúdo (`app/varredura_conteudo.py`) lê o arquivo, vê `application/
    octet-stream` e devolve 415 antes de o teto de tamanho ser avaliado (medido 17/09). Ruído
    aleatório não comprime, então o tamanho cresce com o lado da imagem."""
    import random

    lado = 8
    while True:
        img = Image.frombytes("RGB", (lado, lado),
                              bytes(random.randrange(256) for _ in range(lado * lado * 3)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        if buf.tell() >= bytes_minimos or lado > 512:
            return buf.getvalue()
        lado *= 2


def _feicao(sessao, camada_id, nome="um"):
    r = sessao.post(
        f"/api/camadas/{camada_id}/edicoes",
        json={"adicionar": [{"atributos": {"nome": nome, "categoria": "A"}, "geometria": _ponto()}]},
    )
    assert r.status_code == 200, r.text
    return r.json()["adicionar"][0]["id"]


def _enviar(sessao, camada_id, gid, nome="foto.png", tipo="image/png", conteudo=PNG_1X1):
    return sessao.post(
        f"/api/camadas/{camada_id}/feicoes/{gid}/anexos",
        json={"nome": nome, "content_type": tipo, "conteudo": _b64(conteudo)},
    )


# ---------------------------------------------------------------- teto de TAMANHO (par: cabe / não cabe)
def test_teto_de_tamanho_aceita_abaixo_e_recusa_acima(sessao_a, camada_a, monkeypatch):  # noqa: F811
    monkeypatch.setattr(limites, "ANEXO_TAMANHO_MAX", 4096)
    gid = _feicao(sessao_a, camada_a["id"])

    pequeno = _png_de(0)
    assert len(pequeno) <= 4096, len(pequeno)
    cabe = _enviar(sessao_a, camada_a["id"], gid, nome="cabe.png", conteudo=pequeno)
    assert cabe.status_code == 201, cabe.text[:400]
    assert cabe.json()["bytes"] == len(pequeno)

    grande = _png_de(4097)
    assert len(grande) > 4096, len(grande)
    estoura = _enviar(sessao_a, camada_a["id"], gid, nome="estoura.png", conteudo=grande)
    assert estoura.status_code == 422, estoura.text[:400]
    corpo = estoura.json()
    assert corpo["erro"] == "anexo_grande", corpo
    assert corpo["detalhe"]["limite_bytes"] == 4096, corpo

    # e o recusado não entrou na lista
    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json()
    assert [a["nome"] for a in lista] == ["cabe.png"], lista


@pytest.mark.xfail(
    strict=True,
    reason="o portão do item escreveu 'acima do limite = 413'; o servidor responde 422 anexo_grande "
           "(decisão anterior, registrada em test_edicao_historico_anexos.py: o 413 do teto de corpo "
           "dispararia antes e esconderia o motivo). Divergência registrada, não corrigida aqui.",
)
def test_teto_de_tamanho_responde_413_como_o_portao_pediu(sessao_a, camada_a, monkeypatch):  # noqa: F811
    monkeypatch.setattr(limites, "ANEXO_TAMANHO_MAX", 4096)
    gid = _feicao(sessao_a, camada_a["id"])
    r = _enviar(sessao_a, camada_a["id"], gid, nome="estoura.png", conteudo=_png_de(4097))
    assert r.status_code == 413, r.status_code


# ---------------------------------------------------------------- teto de TIPO (par: permitido / não)
@pytest.mark.parametrize("tipo,conteudo", [
    ("image/png", PNG_1X1),
    ("application/pdf", b"%PDF-1.4\n%\xc3\xa4\n1 0 obj\n<<>>\nendobj\n"),
])
def test_tipo_permitido_entra(sessao_a, camada_a, tipo, conteudo):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    r = _enviar(sessao_a, camada_a["id"], gid, nome=f"arquivo.{tipo.split('/')[1]}",
                tipo=tipo, conteudo=conteudo)
    assert r.status_code == 201, r.text[:400]
    assert r.json()["content_type"] == tipo


@pytest.mark.parametrize("tipo", ["application/javascript", "text/html", "application/octet-stream"])
def test_tipo_fora_da_lista_e_recusado_com_a_lista_na_resposta(sessao_a, camada_a, tipo):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    r = _enviar(sessao_a, camada_a["id"], gid, nome="x.bin", tipo=tipo, conteudo=b"qualquer coisa")
    assert r.status_code == 415, r.text[:400]
    corpo = r.json()
    assert corpo["erro"] == "tipo_nao_permitido"
    assert sorted(corpo["detalhe"]["tipos_permitidos"]) == sorted(limites.ANEXO_TIPOS_PERMITIDOS)


def test_extensao_jpg_com_conteudo_executavel_e_recusada_pelos_bytes(sessao_a, camada_a):  # noqa: F811
    """Refutação do item: a extensão e o content_type declaram JPEG, o conteúdo é um ELF."""
    gid = _feicao(sessao_a, camada_a["id"])
    elf = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64
    r = _enviar(sessao_a, camada_a["id"], gid, nome="inocente.jpg", tipo="image/jpeg", conteudo=elf)
    assert r.status_code == 415, r.text[:400]
    assert r.json()["erro"] == "conteudo_recusado", r.json()


def test_nome_com_caminho_nunca_vira_caminho(sessao_a, camada_a):  # noqa: F811
    """Refutação do item: nome com '../'. O nome é rótulo guardado em coluna, nunca caminho de arquivo —
    a chave do objeto é derivada do sha256 (`app/objetos.py`). Mede-se que o nome não escapa para a chave."""
    gid = _feicao(sessao_a, camada_a["id"])
    r = _enviar(sessao_a, camada_a["id"], gid, nome="../../etc/passwd.png")
    assert r.status_code == 201, r.text[:400]
    anexo = r.json()
    baixado = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}")
    assert baixado.status_code == 200
    assert baixado.content == PNG_1X1
    disposicao = baixado.headers.get("content-disposition", "")
    assert "../" not in disposicao, disposicao
    assert baixado.headers.get("x-content-type-options") == "nosniff"


# ---------------------------------------------------------------- apagar LÓGICO
def test_apagar_e_logico_a_linha_fica_marcada_e_o_download_para(
    sessao_a, camada_a, conexao_plat_app  # noqa: F811
):
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()
    url = f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}"

    assert sessao_a.get(url).status_code == 200  # par positivo: antes de apagar, baixa

    r = sessao_a.delete(url)
    assert r.status_code == 204, r.text[:300]
    assert sessao_a.get(url).status_code == 404
    assert sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json() == []

    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT apagado_em, sha256 FROM plat.feicao_anexo WHERE id = %s::uuid", (anexo["id"],)
        )
        linha = cur.fetchone()
    assert linha is not None, "apagar removeu a linha: isto é apagar FÍSICO, não lógico"
    assert linha["apagado_em"] is not None
    assert linha["sha256"] == anexo["sha256"]


def test_apagar_duas_vezes_o_mesmo_anexo_e_404_na_segunda(sessao_a, camada_a):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()
    url = f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}"
    assert sessao_a.delete(url).status_code == 204
    assert sessao_a.delete(url).status_code == 404


# ---------------------------------------------------------------- isolamento por inquilino
def test_inquilino_b_nao_le_nem_apaga_anexo_de_a(sessao_a, sessao_b, camada_a, camada_b):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()

    # par positivo: o dono lê o próprio anexo
    assert sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}"
    ).status_code == 200

    # pela camada de A (id que B não enxerga) e pela camada do próprio B (id de feição alheio)
    for camada_id in (camada_a["id"], camada_b["id"]):
        assert sessao_b.get(
            f"/api/camadas/{camada_id}/feicoes/{gid}/anexos/{anexo['id']}"
        ).status_code == 404
        assert sessao_b.get(f"/api/camadas/{camada_id}/feicoes/{gid}/anexos").status_code == 404 or \
            sessao_b.get(f"/api/camadas/{camada_id}/feicoes/{gid}/anexos").json() == []
        assert sessao_b.delete(
            f"/api/camadas/{camada_id}/feicoes/{gid}/anexos/{anexo['id']}"
        ).status_code == 404

    # e o anexo continua lá para o dono depois das tentativas de B
    assert sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}"
    ).status_code == 200


def test_anexo_de_a_invisivel_para_b_no_proprio_banco(
    sessao_a, camada_a, camada_b, conexao_plat_app  # noqa: F811
):
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()

    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.feicao_anexo WHERE id = %s::uuid", (anexo["id"],))
        assert cur.fetchone()["n"] == 1

    contexto(conexao_plat_app, camada_b["tenant_id"], usuario_id=camada_b["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.feicao_anexo WHERE id = %s::uuid", (anexo["id"],))
        assert cur.fetchone()["n"] == 0, "RLS deixou o inquilino B ver o anexo de A"


def test_b_nao_envia_anexo_para_feicao_de_a(sessao_b, camada_a, camada_b, sessao_a):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    r = _enviar(sessao_b, camada_b["id"], gid, nome="intruso.png")
    assert r.status_code == 404, r.text[:300]
    assert r.json()["erro"] == "feicao_inexistente"


# ---------------------------------------------------------------- medida do item (tests/medidas/)
def test_medida_do_item_anexos(sessao_a, sessao_b, camada_a, camada_b, medida):  # noqa: F811
    """Grava tests/medidas/L2-03-e-anexos.json com o que ESTE arquivo mede: os tetos declarados pelo
    tronco e os códigos REAIS de cada recusa, colhidos em chamadas de verdade na mesma rodada (nada
    copiado do portão: o portão pedia 413 e o servidor responde 422, ver o xfail acima)."""
    gid = _feicao(sessao_a, camada_a["id"])
    tipo_fora = _enviar(sessao_a, camada_a["id"], gid, nome="x.bin",
                        tipo="application/octet-stream", conteudo=b"qualquer coisa")
    bytes_mentirosos = _enviar(sessao_a, camada_a["id"], gid, nome="inocente.jpg", tipo="image/jpeg",
                               conteudo=b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)
    intruso = _enviar(sessao_b, camada_b["id"], gid, nome="intruso.png")

    gravar = medida("L2-03-e-anexos")
    cmd = "pytest tests/api/test_feicao_anexo.py::test_medida_do_item_anexos"
    gravar("teto_tamanho_bytes", limites.ANEXO_TAMANHO_MAX, "bytes (padrão da instalação)",
           "app/limites.py::ANEXO_TAMANHO_MAX, lido na mesma rodada")
    gravar("tipos_permitidos", sorted(limites.ANEXO_TIPOS_PERMITIDOS), "lista",
           "app/limites.py::ANEXO_TIPOS_PERMITIDOS, lido na mesma rodada")
    gravar("codigo_acima_do_teto", 422, "HTTP (erro anexo_grande)",
           "pytest tests/api/test_feicao_anexo.py::test_teto_de_tamanho_aceita_abaixo_e_recusa_acima "
           "(o portão pedia 413; divergência registrada em xfail estrito)")
    gravar("codigo_tipo_fora_da_lista", tipo_fora.status_code, "HTTP (erro tipo_nao_permitido)", cmd)
    gravar("codigo_extensao_mentirosa", bytes_mentirosos.status_code,
           "HTTP (.jpg com bytes de ELF)", cmd)
    gravar("codigo_anexo_de_b_em_feicao_de_a", intruso.status_code,
           "HTTP (erro feicao_inexistente)", cmd)
    gravar("clausulas_do_portao_sem_codigo_em_master",
           ["miniatura de JPG/PDF", "remoção de EXIF GPS", "URL direta do Garage = 403",
            "apagar feição apaga anexos", "e2e do popup com captura"],
           "cláusulas", "app/edicao/anexos.py não tem rota nem coluna para nenhuma delas (17/09)")

    assert tipo_fora.status_code == 415
    assert bytes_mentirosos.status_code == 415
    assert intruso.status_code == 404
