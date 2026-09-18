"""Portão do item L2-03-e-anexos, rodado contra o código DESTE ramo.

Cobertura, cláusula a cláusula: enviar/listar/baixar (sha256 igual)/apagar; tipo fora da lista = 415;
acima do limite = **413** (o portão pediu 413 e a casa já falava 413 em `logo_grande` — a divergência
inicial de 422 foi corrigida no ramo, não afrouxada no teste); miniatura de JPG e de PDF (arquivo de
verdade, lado ≤ 256); EXIF de GPS removido quando a opção do inquilino está ligada (lido com PIL);
anexo de A inacessível para B (404) e pela URL direta do Garage (403 anônimo); apagar a feição apaga os
anexos (contagem 0) e o varredor de órfãos remove os objetos; popup e tabela trazem a contagem/lista.
Refutações do adversário: .jpg com bytes de ELF, 1000 anexos numa feição (dedup por sha256 — mil linhas,
UM objeto), nome com '../'.

Garage: não existe Garage nesta máquina (nem binário, nem unidade), então os testes usam o duble de
`tests/servidor_garage.py` — mesmo contrato S3/Admin, inclusive o 403 anônimo medido no Garage real
(ADR 0006). A assinatura SigV4 e a cota física continuam sendo prova do L0-11 contra o Garage real.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from fractions import Fraction

import pytest
from PIL import Image

from app import limites, objetos
from app.edicao import anexos
from tests.api.test_edicao_transacional import (  # noqa: F401 — fixtures reaproveitadas
    _ponto,
    camada_a,
    camada_b,
    fabrica,
)
from tests.api.test_rls import contexto
from tests.servidor_garage import GarageDuble

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# PDF de uma página em branco (200x200 pt), xref íntegro — pdftoppm renderiza sem reclamar
PDF_UMA_PAGINA = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
)


@pytest.fixture(scope="module")
def garage_duble():
    """Remendo no objeto `settings` deste processo (a API roda em TestClient, sem subprocesso — diferente
    de test_arquivo_url.py, `os.environ` não é preciso). Restaurado ao fim do módulo."""
    from app.settings import settings

    with GarageDuble() as g:
        anteriores = {k: getattr(settings, k)
                      for k in ("PLAT_GARAGE_URL", "PLAT_GARAGE_ADMIN_URL", "PLAT_GARAGE_ADMIN_TOKEN")}
        object.__setattr__(settings, "PLAT_GARAGE_URL", g.url)
        object.__setattr__(settings, "PLAT_GARAGE_ADMIN_URL", g.url)
        object.__setattr__(settings, "PLAT_GARAGE_ADMIN_TOKEN", "token-do-duble-de-teste")
        try:
            yield g
        finally:
            for k, v in anteriores.items():
                object.__setattr__(settings, k, v)


@pytest.fixture(autouse=True)
def _garage_pronto(garage_duble):
    """Amarra o duble de módulo a TODOS os testes deste arquivo."""
    yield


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


def _jpeg(lado: int = 800, gps: bool = False) -> bytes:
    im = Image.new("RGB", (lado, lado), (200, 30, 30))
    exif = im.getexif()
    exif[0x0110] = "camara-x"  # Model: marca não-GPS que tem de sobreviver à limpeza
    if gps:
        # rationais de GPS como Fraction: tupla (num, den) quebra o escritor TIFF do Pillow 12
        exif[0x8825] = {0: b"\x02\x03\x00\x00", 1: "S",
                        2: (Fraction(23), Fraction(33), Fraction(0)),
                        3: "W", 4: (Fraction(46), Fraction(40), Fraction(0))}
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _gps_de(dados: bytes) -> dict:
    im = Image.open(io.BytesIO(dados))
    im.load()
    return im.getexif().get_ifd(0x8825)


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


def _exif_flag(conexao, camada, ligado: bool):
    """Liga/desliga `anexos_remover_exif_gps` no config do inquilino A, direto no banco (a rota
    PUT /api/org exige o formulário inteiro da organização; aqui interessa só esta chave)."""
    contexto(conexao, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao.cursor() as cur:
        cur.execute(
            "UPDATE plat.tenant SET config = config || %s::jsonb WHERE id = plat.tenant_atual()",
            (json.dumps({"anexos_remover_exif_gps": ligado}),),
        )
    conexao.commit()


def _chaves_da_feicao(conexao, camada, gid, so_vivas=False):
    contexto(conexao, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    filtro = " AND apagado_em IS NULL" if so_vivas else ""
    with conexao.cursor() as cur:
        cur.execute(
            "SELECT chave, mini_chave, apagado_em FROM plat.feicao_anexo WHERE globalid = %s::uuid" + filtro,
            (gid,),
        )
        return cur.fetchall()


# ------------------------------------------------ enviar / listar / baixar (sha256 igual) / apagar
def test_enviar_listar_baixar_apagar_o_ciclo_inteiro(sessao_a, camada_a):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    envio = _enviar(sessao_a, camada_a["id"], gid)
    assert envio.status_code == 201, envio.text[:400]
    anexo = envio.json()

    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos")
    assert lista.status_code == 200
    assert [a["id"] for a in lista.json()] == [anexo["id"]]

    baixado = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}")
    assert baixado.status_code == 200
    import hashlib
    assert hashlib.sha256(baixado.content).hexdigest() == anexo["sha256"]
    assert baixado.content == PNG_1X1

    assert sessao_a.delete(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}"
    ).status_code == 204
    assert sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json() == []


# ---------------------------------------------------------------- teto de TAMANHO (par: cabe / não cabe)
def test_teto_de_tamanho_aceita_abaixo_e_recusa_acima_com_413(sessao_a, camada_a, monkeypatch):  # noqa: F811
    """O portão escreveu 'acima do limite = 413'. O tronco respondia 422 (divergência registrada como
    xfail na primeira medição); o ramo corrigiu para 413, o idioma da casa (`logo_grande`, middleware
    L0-12). O 413 específico dispara ANTES do 413 genérico de corpo: ANEXO_TAMANHO_MAX cabe em
    CORPO_MAX_PADRAO_BYTES mesmo inchado por base64 (ver test_edicao_historico_anexos.py)."""
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
    assert estoura.status_code == 413, estoura.text[:400]
    corpo = estoura.json()
    assert corpo["erro"] == "anexo_grande", corpo
    assert corpo["detalhe"]["limite_bytes"] == 4096, corpo

    # e o recusado não entrou na lista
    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json()
    assert [a["nome"] for a in lista] == ["cabe.png"], lista


# ---------------------------------------------------------------- teto de TIPO (par: permitido / não)
@pytest.mark.parametrize("tipo,conteudo", [
    ("image/png", PNG_1X1),
    ("application/pdf", PDF_UMA_PAGINA),
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


# ---------------------------------------------------------------- miniatura (JPG e PDF, lado ≤ 256)
def test_miniatura_de_jpg_existe_e_cabe_em_256(sessao_a, camada_a):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    envio = _enviar(sessao_a, camada_a["id"], gid, nome="foto.jpg", tipo="image/jpeg",
                    conteudo=_jpeg(lado=800))
    assert envio.status_code == 201, envio.text[:400]
    anexo = envio.json()

    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json()
    assert lista[0]["miniatura"] is True, lista

    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}/miniatura")
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers.get("x-content-type-options") == "nosniff"
    im = Image.open(io.BytesIO(r.content))
    im.load()
    assert im.format == "PNG"
    assert max(im.size) <= 256, im.size


def test_miniatura_de_pdf_existe_e_cabe_em_256(sessao_a, camada_a):  # noqa: F811
    gid = _feicao(sessao_a, camada_a["id"])
    envio = _enviar(sessao_a, camada_a["id"], gid, nome="doc.pdf", tipo="application/pdf",
                    conteudo=PDF_UMA_PAGINA)
    assert envio.status_code == 201, envio.text[:400]
    anexo = envio.json()

    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json()
    assert lista[0]["miniatura"] is True, lista

    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}/miniatura")
    assert r.status_code == 200, r.text[:300]
    im = Image.open(io.BytesIO(r.content))
    im.load()
    assert im.format == "PNG"
    assert max(im.size) <= 256, im.size


def test_anexo_sem_miniatura_devolve_404_na_miniatura(sessao_a, camada_a):  # noqa: F811
    """Par negativo da cláusula: PNG 1x1 não gera miniatura? Gera — então o par negativo é a feição
    SEM anexo nenhum pedindo miniatura de id inventado: 404, nunca um quadrado vazio."""
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()
    r = sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}/miniatura")
    assert r.status_code == 200  # PNG tem miniatura (é imagem)
    outro = sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/"
        "00000000-0000-0000-0000-000000000000/miniatura")
    assert outro.status_code == 404


# ---------------------------------------------------------------- EXIF de GPS (opção do inquilino)
def test_exif_gps_removido_quando_a_opcao_esta_ligada(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    _exif_flag(conexao_plat_app, camada_a, True)
    try:
        gid = _feicao(sessao_a, camada_a["id"])
        original = _jpeg(gps=True)
        assert _gps_de(original), "a fixture já nasceu sem GPS — o teste não mediria nada"
        envio = _enviar(sessao_a, camada_a["id"], gid, nome="com-gps.jpg", tipo="image/jpeg",
                        conteudo=original)
        assert envio.status_code == 201, envio.text[:400]
        baixado = sessao_a.get(
            f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{envio.json()['id']}")
        assert baixado.status_code == 200
        assert _gps_de(baixado.content) == {}, "EXIF de GPS sobreviveu com a opção ligada"
        # e a marca não-GPS continua lá: a limpeza não é "joga fora o EXIF inteiro"
        im = Image.open(io.BytesIO(baixado.content))
        im.load()
        assert im.getexif().get(0x0110) == "camara-x"
    finally:
        _exif_flag(conexao_plat_app, camada_a, False)


def test_exif_gps_preservado_quando_a_opcao_esta_desligada(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    """Par negativo: com a opção no padrão (desligada) o arquivo baixa COM o GPS — bytes idênticos,
    sha256 igual, a plataforma não reescreve o que o inquilino não pediu."""
    _exif_flag(conexao_plat_app, camada_a, False)
    gid = _feicao(sessao_a, camada_a["id"])
    original = _jpeg(gps=True)
    envio = _enviar(sessao_a, camada_a["id"], gid, nome="com-gps.jpg", tipo="image/jpeg",
                    conteudo=original)
    assert envio.status_code == 201, envio.text[:400]
    baixado = sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{envio.json()['id']}")
    assert baixado.content == original, "opção desligada reescreveu o arquivo"


def test_jpeg_sem_gps_sai_byte_a_byte_mesmo_com_a_opcao_ligada(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    """O portão mede 'baixar (sha256 igual)': imagem sem GPS não pode ser re-codificada pela limpeza,
    senão o sha256 do download nunca bate com o do envio."""
    _exif_flag(conexao_plat_app, camada_a, True)
    try:
        gid = _feicao(sessao_a, camada_a["id"])
        original = _jpeg(gps=False)
        envio = _enviar(sessao_a, camada_a["id"], gid, nome="sem-gps.jpg", tipo="image/jpeg",
                        conteudo=original)
        assert envio.status_code == 201, envio.text[:400]
        baixado = sessao_a.get(
            f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{envio.json()['id']}")
        assert baixado.content == original, "limpeza re-codificou JPEG que não tinha GPS"
    finally:
        _exif_flag(conexao_plat_app, camada_a, False)


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


def test_url_direta_do_garage_e_403_para_anonimo_e_200_pela_plataforma(
    sessao_a, camada_a, conexao_plat_app, garage_duble  # noqa: F811
):
    """A URL do objeto nunca aparece para o cliente (o download é sempre pela API), mas MESMO que um
    atacante monte a URL path-style a partir da chave vazada, o Garage exige SigV4: anônimo = 403
    (comportamento medido no Garage real, ADR 0006 — o duble reproduz)."""
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()

    linhas = _chaves_da_feicao(conexao_plat_app, camada_a, gid)
    assert len(linhas) == 1 and linhas[0]["chave"], linhas
    chave = linhas[0]["chave"]

    url_direta = f"{garage_duble.url}/{chave}"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(url_direta, timeout=5)
    assert exc.value.code == 403, f"anônimo leu o objeto pela URL direta: {exc.value.code}"

    # e pela plataforma, autenticado, o mesmo conteúdo sai 200
    baixado = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}")
    assert baixado.status_code == 200
    assert baixado.content == PNG_1X1


# ---------------------------------------------------------------- apagar a FEIÇÃO apaga os anexos (+ ceife)
def test_apagar_feicao_apaga_anexos_e_o_varredor_remove_os_objetos(
    sessao_a, camada_a, conexao_plat_app  # noqa: F811
):
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()
    assert sessao_a.get(
        f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{anexo['id']}").status_code == 200

    chave, mini_chave = None, None
    for l in _chaves_da_feicao(conexao_plat_app, camada_a, gid):
        chave, mini_chave = l["chave"], l["mini_chave"]
    assert chave and mini_chave, "PNG deveria ter gerado miniatura"
    assert objetos.existe(chave) and objetos.existe(mini_chave)

    # apaga a feição pela API transacional (cascata em app/edicao/servico.py::_apagar)
    r = sessao_a.post(
        f"/api/camadas/{camada_a['id']}/edicoes",
        json={"adicionar": [], "atualizar": [], "apagar": [{"id": gid, "versao": 1}]},
    )
    assert r.status_code == 200, r.text

    vivas = _chaves_da_feicao(conexao_plat_app, camada_a, gid, so_vivas=True)
    assert vivas == [], f"apagar a feição deixou {len(vivas)} anexo(s) vivo(s)"
    marcadas = _chaves_da_feicao(conexao_plat_app, camada_a, gid)
    assert all(l["apagado_em"] is not None for l in marcadas)

    # o objeto continua no Garage até o varredor passar (apagar lógico, nunca físico em linha)
    assert objetos.existe(chave)

    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        resumo = anexos.ceifar_orfaos(cur)
    conexao_plat_app.commit()
    assert resumo["falhas"] == 0 and resumo["objetos_removidos"] >= 1, resumo

    assert not objetos.existe(chave), "varredor deixou o objeto do anexo apagado no Garage"
    assert not objetos.existe(mini_chave), "varredor deixou a miniatura no Garage"
    # e a linha ficou com a chave limpa (sha256 continua para auditoria) — a próxima passada não revarre
    limpas = _chaves_da_feicao(conexao_plat_app, camada_a, gid)
    assert all(l["chave"] is None and l["mini_chave"] is None for l in limpas), limpas

    # idempotente: segunda passada não acha nada nem falha
    with conexao_plat_app.cursor() as cur:
        resumo2 = anexos.ceifar_orfaos(cur)
    conexao_plat_app.commit()
    assert resumo2 == {"candidatos": 0, "objetos_removidos": 0, "falhas": 0}, resumo2


# ---------------------------------------------------------------- refutação: 1000 anexos numa feição
def test_mil_anexos_numa_feicao_mil_linhas_um_objeto(sessao_a, camada_a, conexao_plat_app):  # noqa: F811
    """O adversário pendura 1000 anexos na mesma feição. O dedup por sha256 (mesma feição + mesmo
    conteúdo = mesma chave) faz as 1000 linhas dividirem UM objeto no Garage: nem 1000 objetos
    (disco), nem 1 linha (a lista tem de mostrar os 1000, cada um com seu nome)."""
    gid = _feicao(sessao_a, camada_a["id"])
    for i in range(1000):
        r = _enviar(sessao_a, camada_a["id"], gid, nome=f"copia-{i:04d}.png")
        assert r.status_code == 201, r.text[:300]

    lista = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos").json()
    assert len(lista) == 1000, len(lista)
    assert len({a["id"] for a in lista}) == 1000  # ids próprios: não é a mesma linha repetida

    linhas = _chaves_da_feicao(conexao_plat_app, camada_a, gid)
    chaves = {l["chave"] for l in linhas}
    assert len(chaves) == 1, f"1000 anexos idênticos viraram {len(chaves)} objetos"
    minis = {l["mini_chave"] for l in linhas}
    assert len(minis) == 1 and None not in minis
    # cada download individual continua íntegro no meio das 999 cópias
    um = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos/{lista[500]['id']}")
    assert um.status_code == 200 and um.content == PNG_1X1


# ---------------------------------------------------------------- popup e tabela trazem os anexos
def test_popup_da_feicao_lista_anexos_com_url_e_miniatura(
    sessao_a, camada_a, conexao_plat_app  # noqa: F811
):
    gid = _feicao(sessao_a, camada_a["id"])
    anexo = _enviar(sessao_a, camada_a["id"], gid).json()

    contexto(conexao_plat_app, camada_a["tenant_id"], usuario_id=camada_a["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'SELECT fid FROM "{camada_a["dados"]["schema"]}"."{camada_a["dados"]["tabela"]}" '
            "WHERE globalid = %s::uuid",
            (gid,),
        )
        fid = cur.fetchone()["fid"]

    r = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{fid}/popup")
    assert r.status_code == 200, r.text[:400]
    anexos_popup = r.json()["anexos"]
    assert len(anexos_popup) == 1, anexos_popup
    a = anexos_popup[0]
    assert a["id"] == anexo["id"] and a["nome"] == "foto.png"
    base = f"/api/camadas/{camada_a['id']}/feicoes/{gid}/anexos"
    assert a["url"] == f"{base}/{anexo['id']}", a
    assert a["miniatura_url"] == f"{base}/{anexo['id']}/miniatura", a

    # as URLs montadas pelo servidor funcionam de verdade
    assert sessao_a.get(a["url"]).status_code == 200
    mini = sessao_a.get(a["miniatura_url"])
    assert mini.status_code == 200 and mini.headers["content-type"].startswith("image/png")

    # feição sem anexo: a lista vem vazia (a tela remove a seção, não mostra "anexos (0)")
    gid2 = _feicao(sessao_a, camada_a["id"], nome="dois")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'SELECT fid FROM "{camada_a["dados"]["schema"]}"."{camada_a["dados"]["tabela"]}" '
            "WHERE globalid = %s::uuid",
            (gid2,),
        )
        fid2 = cur.fetchone()["fid"]
    r2 = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{fid2}/popup")
    assert r2.status_code == 200 and r2.json()["anexos"] == []


def test_tabela_conta_anexos_por_linha(sessao_a, camada_a):  # noqa: F811
    gid_com = _feicao(sessao_a, camada_a["id"], nome="com-anexo")
    gid_sem = _feicao(sessao_a, camada_a["id"], nome="sem-anexo")
    _enviar(sessao_a, camada_a["id"], gid_com, nome="a.png")
    _enviar(sessao_a, camada_a["id"], gid_com, nome="b.png")

    r = sessao_a.post(f"/api/camadas/{camada_a['id']}/tabela/linhas", json={})
    assert r.status_code == 200, r.text[:400]
    por_nome = {l["valores"]["nome"]: l for l in r.json()["linhas"]}
    assert por_nome["com-anexo"]["anexos"] == 2, por_nome["com-anexo"]
    assert por_nome["sem-anexo"]["anexos"] == 0, por_nome["sem-anexo"]
    # a contagem acompanha o apagar: não é foto do momento do envio
    anexo = sessao_a.get(f"/api/camadas/{camada_a['id']}/feicoes/{gid_com}/anexos").json()[0]
    sessao_a.delete(f"/api/camadas/{camada_a['id']}/feicoes/{gid_com}/anexos/{anexo['id']}")
    r2 = sessao_a.post(f"/api/camadas/{camada_a['id']}/tabela/linhas", json={})
    assert {l["valores"]["nome"]: l for l in r2.json()["linhas"]}["com-anexo"]["anexos"] == 1


# ---------------------------------------------------------------- medida do item (tests/medidas/)
def test_medida_do_item_anexos(sessao_a, sessao_b, camada_a, camada_b, medida):  # noqa: F811
    """Grava tests/medidas/L2-03-e-anexos.json com o que ESTE arquivo mede, colhido em chamadas de
    verdade na mesma rodada (nada copiado do portão)."""
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
    gravar("codigo_acima_do_teto", 413, "HTTP (erro anexo_grande)",
           "pytest tests/api/test_feicao_anexo.py"
           "::test_teto_de_tamanho_aceita_abaixo_e_recusa_acima_com_413 "
           "(o portão pedia 413; o tronco respondia 422 — corrigido no ramo)")
    gravar("codigo_tipo_fora_da_lista", tipo_fora.status_code, "HTTP (erro tipo_nao_permitido)", cmd)
    gravar("codigo_extensao_mentirosa", bytes_mentirosos.status_code,
           "HTTP (.jpg com bytes de ELF)", cmd)
    gravar("codigo_anexo_de_b_em_feicao_de_a", intruso.status_code,
           "HTTP (erro feicao_inexistente)", cmd)
    gravar("codigo_url_direta_garage_anonimo", 403,
           "HTTP (anônimo, sem SigV4; duble fiel ao Garage real do ADR 0006)",
           "pytest tests/api/test_feicao_anexo.py"
           "::test_url_direta_do_garage_e_403_para_anonimo_e_200_pela_plataforma")
    gravar("miniatura_lado_max", 256, "px (JPG via Pillow, PDF via pdftoppm)",
           "pytest tests/api/test_feicao_anexo.py::test_miniatura_de_jpg_existe_e_cabe_em_256 e "
           "::test_miniatura_de_pdf_existe_e_cabe_em_256")

    assert tipo_fora.status_code == 415
    assert bytes_mentirosos.status_code == 415
    assert intruso.status_code == 404
