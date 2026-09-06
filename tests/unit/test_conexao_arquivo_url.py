"""Item L6-02-h — arquivo por URL: reconhecimento de formato pelos bytes, requisição condicional (ETag/
Last-Modified), recusa de endereço interno em toda forma, credencial que não atravessa host, e a refutação do
item (CSV com latitude e longitude trocadas).

Os testes que tocam a rede sobem um servidor de prova no ENDEREÇO PÚBLICO desta máquina (tests/
servidor_arquivo.py) — a defesa de SSRF fica inteira e a busca é de verdade; nunca `localhost`, que seria (e é)
recusado."""

from __future__ import annotations

import json

import pytest

from app import limites
from app.conexao import arquivo_url, seguranca
from tests.servidor_arquivo import ServidorArquivos

CSV_VIRGULA = (
    "nome;lat;lon;area_ha\n"
    "Talhao A;-15,7942;-47,8822;120,5\n"
    "Talhao B;-23,5505;-46,6333;89,25\n"
).encode("utf-8")

CSV_TROCADO = (
    "nome,lat,lon\n"
    "Ponto A,-47.8822,-15.7942\n"
    "Ponto B,-146.6333,-23.5505\n"
).encode("utf-8")

GEOJSON = json.dumps({
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "properties": {"nome": "a"},
                  "geometry": {"type": "Point", "coordinates": [-47.88, -15.79]}}],
}).encode("utf-8")

KML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>t</name>'
    "<Placemark><name>a</name><Point><coordinates>-47.88,-15.79</coordinates></Point></Placemark>"
    "</Document></kml>"
).encode("utf-8")

GPX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<gpx version="1.1" creator="teste" xmlns="http://www.topografix.com/GPX/1/1">'
    '<wpt lat="-15.79" lon="-47.88"><name>a</name></wpt></gpx>'
).encode("utf-8")

GEORSS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0" xmlns:georss="http://www.georss.org/georss"><channel><title>t</title>'
    "<item><title>a</title><georss:point>-15.79 -47.88</georss:point></item></channel></rss>"
).encode("utf-8")


def kmz(conteudo: bytes = KML) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", conteudo)
    return buf.getvalue()


# ---------------------------------------------------------------- formato pelos bytes
@pytest.mark.parametrize(
    ("dados", "esperado"),
    [(CSV_VIRGULA, "csv"), (GEOJSON, "geojson"), (KML, "kml"), (kmz(), "kmz"), (GPX, "gpx"), (GEORSS, "georss")],
)
def test_formato_reconhecido_pelos_bytes(dados, esperado):
    assert arquivo_url.detectar_formato(dados) == esperado


def test_extensao_mentirosa_nao_muda_o_formato():
    """A URL diz `.csv`, o Content-Type diz `text/csv`, mas os bytes são GeoJSON: vale o conteúdo."""
    assert arquivo_url.detectar_formato(GEOJSON, "text/csv", "http://exemplo.invalido/dados.csv") == "geojson"


@pytest.mark.parametrize(
    ("dados", "pedaco_da_mensagem"),
    [
        (b"", "corpo vazio"),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "binário"),
        (b'{"type": "Coisa", "a": 1}', "não é GeoJSON"),
        (b'<?xml version="1.0"?><rss version="2.0"><channel><item><title>a</title></item></channel></rss>',
         "sem geometria GeoRSS"),
    ],
)
def test_formato_desconhecido_e_recusado(dados, pedaco_da_mensagem):
    with pytest.raises(arquivo_url.ArquivoRecusado, match=pedaco_da_mensagem):
        arquivo_url.detectar_formato(dados)


def test_kml_grande_demais_e_recusado_com_o_teto_medido():
    """O teto dos formatos XML é menor que o geral porque o GDAL lê o documento inteiro na memória (a medição
    está em app/limites.py). Um KML acima dele é recusado ANTES de virar subprocesso."""
    enorme = KML.replace(b"</Document>", b"<!--" + b"x" * limites.CONEXAO_ARQUIVO_XML_MAX_BYTES + b"--></Document>")
    with pytest.raises(arquivo_url.ArquivoRecusado, match="teto"):
        arquivo_url.analisar(enorme)


# ---------------------------------------------------------------- CSV: vírgula decimal e a refutação do item
def test_csv_com_virgula_decimal_e_ponto_e_virgula_reconhecido():
    from app.ingestao import csv_normalizar

    r = csv_normalizar.normalizar_bytes(CSV_VIRGULA)
    assert r.separador_origem == ";"
    assert r.decimal_origem == ","
    assert r.coordenadas == {"x": "lon", "y": "lat"}
    assert "-15.7942,-47.8822" in r.texto  # vírgula decimal virou ponto no CSV canônico
    assert arquivo_url.detectar_formato(CSV_VIRGULA) == "csv"
    arquivo_url.conferir_faixa_coordenada(CSV_VIRGULA)  # dentro da faixa: não levanta


def test_refutacao_csv_com_lat_lon_trocadas_e_recusado():
    """Refutação do item: `lon > 90` na coluna de latitude. A plataforma RECUSA e diz que as colunas parecem
    trocadas; nunca troca sozinha (trocar inventaria dado que ninguém pediu)."""
    with pytest.raises(arquivo_url.ArquivoRecusado) as e:
        arquivo_url.conferir_faixa_coordenada(CSV_TROCADO)
    assert "latitude" in str(e.value)
    assert "-146.6333" in str(e.value)   # o valor que denuncia a troca: não cabe numa latitude
    assert "trocadas" in str(e.value)


def test_fronteira_honesta_troca_indetectavel_quando_os_dois_valores_cabem_nas_duas_faixas():
    """Limite declarado deste mecanismo: se latitude e longitude estão trocadas mas as DUAS ficam dentro de
    -90..90 (ex.: lat -47,88 / lon -15,79), nenhuma faixa é violada e o arquivo passa. Não existe sinal no dado
    para distinguir isso de um arquivo correto — a conferência de faixa pega a troca só quando ela produz um
    valor impossível. Documentado aqui para ninguém prometer mais do que o mecanismo faz."""
    dados = b"nome,lat,lon\nA,-47.88,-15.79\n"
    arquivo_url.conferir_faixa_coordenada(dados)  # não levanta: e isso é uma limitação, não um acerto


def test_csv_com_longitude_fora_da_faixa_tambem_e_recusado():
    dados = b"nome,lat,lon\nA,-15.79,-247.88\n"
    with pytest.raises(arquivo_url.ArquivoRecusado, match="longitude"):
        arquivo_url.conferir_faixa_coordenada(dados)


def test_csv_sem_coluna_de_coordenada_nao_e_recusado():
    """Sem lat/lon não há faixa a conferir — a tabela sem geometria segue para a ingestão."""
    arquivo_url.conferir_faixa_coordenada(b"nome,valor\nA,10\nB,20\n")


# ---------------------------------------------------------------- requisição condicional
def test_condicionais_montados_do_que_foi_guardado():
    assert arquivo_url.condicionais(None, None) == {}
    assert arquivo_url.condicionais('"abc"', None) == {"If-None-Match": '"abc"'}
    assert arquivo_url.condicionais(None, "Wed, 03 Sep 2026 10:00:00 GMT") == {
        "If-Modified-Since": "Wed, 03 Sep 2026 10:00:00 GMT"
    }


def test_baixa_guarda_etag_e_o_segundo_pedido_recebe_304():
    with ServidorArquivos() as s:
        s.publicar("/pontos.geojson", GEOJSON, content_type="application/geo+json",
                   last_modified="Wed, 03 Sep 2026 10:00:00 GMT")
        url = s.url("/pontos.geojson")
        primeiro = arquivo_url.baixar(url)
        assert primeiro.ok and not primeiro.nao_modificado
        assert primeiro.status == 200
        assert primeiro.etag and primeiro.sha256
        assert primeiro.content_type == "application/geo+json"

        segundo = arquivo_url.baixar(url, etag=primeiro.etag, last_modified=primeiro.last_modified)
        assert segundo.ok and segundo.nao_modificado
        assert segundo.status == 304
        assert segundo.dados == b""
        assert s.recursos["/pontos.geojson"].pedidos[-1]["if-none-match"] == primeiro.etag


def test_servidor_que_ignora_o_condicional_devolve_o_mesmo_sha256():
    """Segunda linha de defesa: servidor mal-educado responde 200 com o mesmo corpo. Quem decide não recarregar
    é o sha256 (o job compara com o da carga anterior)."""
    with ServidorArquivos() as s:
        s.publicar("/teimoso.geojson", GEOJSON, ignorar_condicional=True)
        url = s.url("/teimoso.geojson")
        a = arquivo_url.baixar(url)
        b = arquivo_url.baixar(url, etag=a.etag)
        assert b.status == 200 and not b.nao_modificado
        assert b.sha256 == a.sha256


def test_conteudo_novo_muda_o_sha256_e_o_etag():
    with ServidorArquivos() as s:
        recurso = s.publicar("/muda.geojson", GEOJSON)
        url = s.url("/muda.geojson")
        a = arquivo_url.baixar(url)
        recurso.corpo = GEOJSON.replace(b'"a"', b'"b"')
        b = arquivo_url.baixar(url, etag=a.etag)
        assert b.status == 200 and b.sha256 != a.sha256 and b.etag != a.etag


# ---------------------------------------------------------------- endereço interno recusado (3 formas)
@pytest.mark.parametrize(
    ("url", "motivo"),
    [
        ("http://127.0.0.1:8163/dados.csv", "loopback"),
        ("http://[::1]/dados.csv", "loopback"),
        ("http://10.0.0.5/dados.csv", "privado"),
        ("http://192.168.1.10/dados.csv", "privado"),
        ("http://169.254.169.254/latest/meta-data/", "link_local"),
        ("http://100.64.0.1/dados.csv", "privado"),
        ("file:///etc/passwd", "esquema_nao_permitido"),
    ],
)
def test_endereco_interno_recusado_na_entrada(url, motivo):
    r = arquivo_url.baixar(url)
    assert r.ok is False
    assert r.mensagem.startswith("url_insegura:")
    assert motivo in r.mensagem


@pytest.mark.parametrize("nome", ["localtest.me", "10.0.0.1.nip.io"])
def test_nome_que_resolve_para_a_rede_local_e_recusado(nome):
    """Nome de DNS PÚBLICO que resolve para endereço interno (localtest.me -> 127.0.0.1; 10.0.0.1.nip.io ->
    10.0.0.1). É a forma clássica de furar lista de host: o validador não olha o nome, olha o IP resolvido."""
    r = arquivo_url.baixar(f"http://{nome}/dados.csv")
    if r.mensagem.startswith("url_insegura:dns_"):
        pytest.skip(f"{nome} não resolveu nesta rede (sem DNS externo); o caso interno já é coberto pelo IP literal")
    assert r.ok is False
    assert r.mensagem.startswith("url_insegura:ip_bloqueado:")


def test_redirecionamento_para_endereco_interno_e_recusado():
    """O primeiro salto é um host público de verdade (esta máquina); o segundo aponta para o metadado de nuvem.
    Aceitar o salto 0 e recusar o salto 1 é a prova de que o `Location` é revalidado do zero."""
    with ServidorArquivos() as s:
        s.publicar("/armadilha", b"", redireciona_para="http://169.254.169.254/latest/meta-data/")
        r = arquivo_url.baixar(s.url("/armadilha"))
        assert r.ok is False
        assert "ip_bloqueado:link_local:169.254.169.254" in r.mensagem


def test_redirecionamento_para_loopback_tambem_e_recusado():
    with ServidorArquivos() as s:
        s.publicar("/armadilha2", b"", redireciona_para="http://127.0.0.1:8163/segredo")
        r = arquivo_url.baixar(s.url("/armadilha2"))
        assert r.ok is False
        assert "ip_bloqueado:loopback" in r.mensagem


# ---------------------------------------------------------------- credencial não atravessa host
def test_credencial_nao_segue_para_outro_host_no_redirecionamento():
    """Achado do adversário do L6-02-a, consertado aqui: o `Authorization` da casa ia junto no redirecionamento
    para qualquer host. Agora o segundo host recebe a requisição SEM o cabeçalho."""
    with ServidorArquivos() as s, ServidorArquivos() as terceiro:
        terceiro.publicar("/coleta", GEOJSON)
        s.publicar("/vai-para-terceiro", b"", redireciona_para=terceiro.url("/coleta"))
        # os dois servidores estão no MESMO IP público, então "outro host" precisa de outra porta:
        # porta diferente já é outro serviço (o validador de origem confere esquema, host E porta).
        r = arquivo_url.baixar(s.url("/vai-para-terceiro"), credencial="segredo-da-casa")
        assert r.ok is True and r.status == 200
        assert "authorization" in s.recursos["/vai-para-terceiro"].pedidos[0]
        assert "authorization" not in terceiro.recursos["/coleta"].pedidos[0]


def test_credencial_segue_no_redirecionamento_para_o_mesmo_host_e_porta():
    with ServidorArquivos() as s:
        s.publicar("/final", GEOJSON)
        s.publicar("/inicio", b"", redireciona_para=s.url("/final"))
        r = arquivo_url.baixar(s.url("/inicio"), credencial="segredo-da-casa")
        assert r.ok is True
        assert s.recursos["/final"].pedidos[0].get("authorization") == "Bearer segredo-da-casa"


@pytest.mark.parametrize(
    ("anterior", "novo", "mesma"),
    [
        ("https://a.exemplo/x", "https://a.exemplo/y", True),
        ("https://a.exemplo/x", "https://A.EXEMPLO/y", True),
        ("https://a.exemplo/x", "http://a.exemplo/y", False),      # queda de https para http
        ("https://a.exemplo/x", "https://b.exemplo/y", False),
        ("https://a.exemplo/x", "https://a.exemplo:8443/y", False),  # porta diferente = outro serviço
        ("http://a.exemplo/x", "http://a.exemplo:80/y", True),      # porta padrão explícita é a mesma
    ],
)
def test_origem_de_confianca(anterior, novo, mesma):
    assert seguranca._mesma_origem_de_confianca(anterior, novo) is mesma


def test_cabecalhos_de_credencial_removidos_por_nome():
    entrada = {"Authorization": "Bearer x", "Cookie": "s=1", "X-Api-Key": "k", "Accept": "*/*"}
    saida = seguranca._sem_credencial_em_outro_host(entrada, "https://a.exemplo/", "https://b.exemplo/")
    assert saida == {"Accept": "*/*"}
