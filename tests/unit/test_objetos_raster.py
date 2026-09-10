"""Nome de objeto por conteúdo, recusa de travessia e tradução do erro do Garage (item L1-01-d-garage-por-inquilino;
ADR 0016). Tudo aqui é puro: nenhuma destas asserções toca o Garage nem o banco — o que precisa da instância viva
está em tests/api/test_garage_inquilino.py. A última função compara a expressão do caminho `/svc/<token>/cog/` que
a APLICAÇÃO usa com a que o NGINX usa (deploy/nginx.conf): se as duas divergirem, o nginx entrega um caminho que a
autorização não sabe ler."""

import hashlib
import re
from pathlib import Path

import pytest

from app import objetos_raster
from app.garage import CotaGarage, traduzir_erro_s3
from app.objetos import ChaveInvalida

ITEM = "L1-01-d-garage-por-inquilino"
SHA = hashlib.sha256(b"conteudo de teste").hexdigest()
RAIZ = Path(__file__).resolve().parents[2]


def test_objeto_e_nomeado_por_conteudo():
    """`<item_id>/<asset>_<sha8>.<ext>`: o sha8 sai do sha256 do conteúdo, então conteúdo diferente = chave
    diferente, e é por isso que nunca é preciso sobrescrever."""
    caminho = objetos_raster.objeto("01J8ZQ2K3M4N5P6Q7R8S9T0V1W", "cog", SHA, "tif")
    assert caminho == f"01J8ZQ2K3M4N5P6Q7R8S9T0V1W/cog_{SHA[:8]}.tif"
    outro = hashlib.sha256(b"outro conteudo").hexdigest()
    assert objetos_raster.objeto("01J8ZQ2K3M4N5P6Q7R8S9T0V1W", "cog", outro, "tif") != caminho


def test_chave_completa_e_partes_ida_e_volta():
    caminho = objetos_raster.objeto("item01", "miniatura", SHA, "png")
    chave = objetos_raster.chave("demo", caminho)
    assert chave == f"demo/item01/miniatura_{SHA[:8]}.png"
    p = objetos_raster.partes(chave)
    assert p == {"slug": "demo", "item_id": "item01", "asset": "miniatura", "sha8": SHA[:8], "ext": "png"}


@pytest.mark.parametrize(
    "item_id, asset, sha, ext",
    [
        ("..", "cog", SHA, "tif"),                      # travessia no item
        ("../../etc", "cog", SHA, "tif"),
        ("item01", "..", SHA, "tif"),                   # travessia no asset
        ("item01/..", "cog", SHA, "tif"),
        ("item01", "cog/../..", SHA, "tif"),
        ("item01", "COG", SHA, "tif"),                  # maiúscula no asset
        ("item01", "cog", "nao-e-sha", "tif"),
        ("item01", "cog", SHA[:63], "tif"),
        ("item01", "cog", SHA, "TIF"),
        ("item01", "cog", SHA, "extensao_grande_demais"),
    ],
)
def test_objeto_recusa_travessia_e_forma_errada(item_id, asset, sha, ext):
    with pytest.raises(ChaveInvalida):
        objetos_raster.objeto(item_id, asset, sha, ext)


@pytest.mark.parametrize(
    "chave",
    [
        "demo/../demo2/item01/cog_abcdef12.tif",
        "../demo/item01/cog_abcdef12.tif",
        "demo/item01/cog_abcdef12.tif/../..",
        "demo2/item01/cog_ABCDEF12.tif",   # sha8 tem de ser hex minúsculo
        "demo/item01/cog_abcdef12",        # sem extensão
        "item01/cog_abcdef12.tif",         # sem slug
    ],
)
def test_partes_recusa_chave_fora_do_padrao(chave):
    with pytest.raises(ChaveInvalida):
        objetos_raster.partes(chave)


def test_caminho_web_exige_token_no_padrao():
    chave = f"demo/item01/cog_{SHA[:8]}.tif"
    token = "plat_" + "a" * 40
    assert objetos_raster.caminho_web(token, chave) == f"/svc/{token}/cog/{chave}"
    for ruim in ("", "abc", "plat_curto", "plat_" + "a" * 200, "Bearer plat_" + "a" * 40):
        with pytest.raises(ChaveInvalida):
            objetos_raster.caminho_web(ruim, chave)


# ---------------------------------------------------------------- tradução da recusa do Garage
def test_traduz_cota_de_bytes_para_portugues():
    corpo = (
        "<?xml version='1.0'?><Error><Code>AccessDenied</Code>"
        "<Message>Bucket size quota is reached, maximum size for this bucket: 500</Message></Error>"
    )
    codigo, msg, cota = traduzir_erro_s3(403, corpo)
    assert codigo == "AccessDenied"
    assert isinstance(cota, CotaGarage) and cota.tipo == "bytes" and cota.limite == 500
    assert "cota de armazenamento" in msg and "500 bytes" in msg
    assert not re.search(r"[a-z]+ quota", msg), "a mensagem que chega à API tem de estar em português"


def test_traduz_cota_de_objetos_para_portugues():
    corpo = (
        "<?xml version='1.0'?><Error><Code>AccessDenied</Code>"
        "<Message>Object quota is reached, maximum objects for this bucket: 3</Message></Error>"
    )
    _codigo, msg, cota = traduzir_erro_s3(403, corpo)
    assert isinstance(cota, CotaGarage) and cota.tipo == "objetos" and cota.limite == 3
    assert "cota de objetos" in msg and "3 objetos" in msg


def test_traduz_chave_sem_permissao_sem_confundir_com_cota():
    corpo = "<Error><Code>AccessDenied</Code><Message>Operation is not allowed for this key.</Message></Error>"
    _codigo, msg, cota = traduzir_erro_s3(403, corpo)
    assert cota is None, "falta de permissão não é cota: quem chama não pode tratar as duas do mesmo jeito"
    assert "não tem permissão" in msg


# ---------------------------------------------------------------- aplicação × nginx: a mesma expressão
def _regex_do_nginx() -> re.Pattern:
    """Extrai do deploy/nginx.conf a expressão do `location ~ "^/svc/.../cog/..."` e a converte para a sintaxe do
    Python (`(?<n>` do PCRE do nginx vira `(?P<n>`)."""
    conf = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    m = re.search(r'location\s+~\s+"(\^/svc/.+?)"\s*\{', conf, re.S)
    assert m, "o bloco /svc/<token>/cog/ sumiu de deploy/nginx.conf"
    return re.compile(m.group(1).replace("(?<", "(?P<"))


CAMINHOS = [
    ("/svc/plat_" + "a" * 40 + "/cog/demo/item01/cog_abcdef12.tif", True),
    ("/svc/plat_" + "a" * 40 + "/cog/demo2/01J8ZQ2K3M/miniatura_00112233.png", True),
    ("/svc/plat_" + "a" * 40 + "/cog/demo/../demo2/item01/cog_abcdef12.tif", False),
    ("/svc/plat_" + "a" * 40 + "/cog/demo/item01/cog_ABCDEF12.tif", False),
    ("/svc/nao_e_token/cog/demo/item01/cog_abcdef12.tif", False),
    ("/svc/plat_curto/cog/demo/item01/cog_abcdef12.tif", False),
    ("/svc/plat_" + "a" * 40 + "/cog/demo/item01/cog_abcdef12.tif/extra", False),
    ("/svc/plat_" + "a" * 40 + "/cog/demo/item01", False),
]


@pytest.mark.parametrize("uri, aceita", CAMINHOS)
def test_expressao_do_cog_igual_na_aplicacao_e_no_nginx(uri, aceita):
    from app.rotas_arquivos import COG_URI

    nginx = _regex_do_nginx()
    assert bool(COG_URI.match(uri)) is aceita
    assert bool(nginx.match(uri)) is aceita, "nginx e aplicação divergiram na forma do caminho do COG"
