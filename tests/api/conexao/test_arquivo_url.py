"""Item L6-02-h, ponta a ponta: um arquivo servido numa URL pública vira camada de verdade (tabela PostGIS +
item de catálogo `camada_vetorial`), em 4 formatos, e a atualização agendada não recarrega o que não mudou.

Nada aqui é simulado: o arquivo é servido pelo endereço PÚBLICO desta máquina (tests/servidor_arquivo.py — a
defesa de SSRF continua ligada e recusaria `localhost`), o job roda num worker de verdade em subprocesso, o
`ogr2ogr` converte KML/GeoRSS/GPX e o `ogr2ogr` da ingestão do L0-04 cria a tabela.

O worker é próprio deste arquivo de teste (porta 18163) porque o tipo `conexoes.arquivo_sincronizar` só existe
neste ramo — a unidade `plat-worker` da máquina roda o código de `master` e não conhece o tipo."""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.jobs.conftest import WorkerExtra
from tests.servidor_arquivo import ServidorArquivos
from tests.unit.test_conexao_arquivo_url import CSV_TROCADO, CSV_VIRGULA, GEOJSON, GEORSS, GPX, KML, kmz

PORTA_WORKER = 18163
SUFIXO = uuid.uuid4().hex[:6]   # nome de conexão é único por inquilino: uma rodada não colide com a anterior
FORMATOS = {
    "csv": (CSV_VIRGULA, "text/csv", "dados.csv"),
    "geojson": (GEOJSON, "application/geo+json", "dados.geojson"),
    "kml": (KML, "application/vnd.google-earth.kml+xml", "dados.kml"),
    "kmz": (kmz(), "application/vnd.google-earth.kmz", "dados.kmz"),
    "georss": (GEORSS, "application/rss+xml", "dados.xml"),
    "gpx": (GPX, "application/gpx+xml", "dados.gpx"),
}


ITEM = "L6-02-h-csv-url-geojson-kml"
COMANDO = ("set -a; source laco/var/trilha/<t>.env; set +a; "
           "venv/bin/pytest tests/api/conexao/test_arquivo_url.py -q")


@pytest.fixture
def anota(medida):
    """Grava em tests/medidas/L6-02-h-csv-url-geojson-kml.json (só com PLAT_GRAVAR_MEDIDAS=1)."""
    gravar = medida(ITEM)

    def _anota(nome: str, valor):
        gravar(nome, valor, "json", COMANDO)

    return _anota


@pytest.fixture(scope="module")
def servidor():
    with ServidorArquivos() as s:
        yield s


@pytest.fixture(scope="module")
def worker(env):
    w = WorkerExtra(env, f"teste-l602h-{PORTA_WORKER}", processos=1, porta=PORTA_WORKER)
    yield w
    w.parar()


@pytest.fixture(scope="module")
def cliente_demo_modulo(env):
    """Cliente com cookie de sessão de `demo` (o mesmo mecanismo de tests/api/jobs/conftest.py, mas com
    escopo de módulo: o worker e o servidor de arquivos vivem por todo o módulo)."""
    from fastapi.testclient import TestClient

    from app.main import app
    from tests import jobs_sessao

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        token, _tenant, _usuario = jobs_sessao.criar_sessao(con, "demo", "admin")
    finally:
        con.close()
    with TestClient(app, cookies={jobs_sessao.COOKIE_SESSAO: token}) as c:
        yield c


class Fonte:
    """Cria a conexão `http`/`copiada`, a configura como arquivo por URL e sabe sincronizar esperando o job."""

    def __init__(self, cliente, url: str, nome: str):
        self.cliente = cliente
        r = cliente.post("/api/conexoes", json={
            "tipo": "http", "modo": "copiada", "nome": f"{PREFIXO_TESTE} {nome} {SUFIXO}", "url": url,
        })
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        r = cliente.put(f"/api/conexoes/{self.id}/arquivo", json={"intervalo_s": 900, "agendado": False})
        assert r.status_code == 200, r.text

    def sincronizar(self, timeout: float = 180) -> dict:
        r = self.cliente.post(f"/api/conexoes/{self.id}/arquivo/sincronizar")
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        fim = time.monotonic() + timeout
        ultimo = None
        while time.monotonic() < fim:
            j = self.cliente.get(f"/api/jobs/{job_id}")
            assert j.status_code == 200, j.text
            ultimo = j.json()
            if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
                return ultimo
            time.sleep(0.3)
        pytest.fail(f"job {job_id} não terminou em {timeout} s: {json.dumps(ultimo)[:600]}")

    def estado(self) -> dict:
        r = self.cliente.get(f"/api/conexoes/{self.id}/arquivo")
        assert r.status_code == 200, r.text
        return r.json()

    def apagar(self):
        self.cliente.delete(f"/api/conexoes/{self.id}")


@pytest.fixture
def fonte(cliente_demo_modulo, servidor, worker):
    criadas: list[Fonte] = []
    camadas: list[str] = []

    def _criar(caminho: str, corpo: bytes, nome: str, **kw) -> Fonte:
        servidor.publicar(caminho, corpo, **kw)
        f = Fonte(cliente_demo_modulo, servidor.url(caminho), nome)
        criadas.append(f)
        return f

    yield _criar
    for f in criadas:
        est = f.estado() if f else None
        if est and est.get("item_id"):
            camadas.append(est["item_id"])
        f.apagar()
    for item_id in camadas:
        cliente_demo_modulo.delete(f"/api/itens/{item_id}")


# ---------------------------------------------------------------- 4+ formatos viram camada
@pytest.mark.parametrize("formato", list(FORMATOS))
def test_formato_por_url_publica_vira_camada(formato, fonte, cliente_demo_modulo, anota):
    corpo, content_type, nome = FORMATOS[formato]
    f = fonte(f"/{formato}/{nome}", corpo, f"url {formato}", content_type=content_type)
    job = f.sincronizar()
    assert job["estado"] == "concluido", job.get("erro")
    resultado = job["resultado"]
    assert resultado["recarregou"] is True
    assert resultado["formato"] == formato
    assert resultado["feicoes"] >= 1

    est = f.estado()
    assert est["formato"] == formato
    assert est["ultimo_resultado"] == "carregada"
    assert est["sincronizacoes"] == 1 and est["recargas"] == 1
    assert est["etag"] and est["sha256"]

    # a camada existe no catálogo, com tabela e geometria de verdade
    r = cliente_demo_modulo.get(f"/api/itens/{est['item_id']}")
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tipo"] == "camada_vetorial"
    assert item["dados"]["estatisticas"]["feicoes"] == resultado["feicoes"]
    assert item["dados"]["srid"] in (4326, 4674)
    anota(f"camada_{formato}", {
        "formato": formato, "feicoes": resultado["feicoes"], "srid": item["dados"]["srid"],
        "bytes_baixados": resultado["bytes"], "item_id": est["item_id"],
    })


# ---------------------------------------------------------------- ETag: não recarrega o que não mudou
def test_atualizacao_agendada_com_etag_nao_recarrega_arquivo_inalterado(fonte, servidor, anota):
    """A cláusula do portão. Três passagens na MESMA URL:
    1. primeira carga (200, cria a camada);
    2. arquivo inalterado -> o servidor responde 304 e nada é recarregado;
    3. arquivo trocado -> 200 e a camada é recriada.
    `sincronizacoes` conta as três; `recargas` conta duas."""
    f = fonte("/agendado/dados.geojson", GEOJSON, "url agendada",
              content_type="application/geo+json", last_modified="Wed, 03 Sep 2026 10:00:00 GMT")

    primeira = f.sincronizar()
    assert primeira["estado"] == "concluido"
    assert primeira["resultado"]["recarregou"] is True
    est1 = f.estado()
    assert est1["sincronizacoes"] == 1 and est1["recargas"] == 1
    item_primeiro = est1["item_id"]

    segunda = f.sincronizar()
    assert segunda["estado"] == "concluido"
    assert segunda["resultado"] == {"recarregou": False, "motivo": "http_304", "status": 304}
    est2 = f.estado()
    assert est2["sincronizacoes"] == 2
    assert est2["recargas"] == 1, "recarregou um arquivo que o servidor disse não ter mudado"
    assert est2["ultimo_resultado"] == "nao_modificada"
    assert est2["item_id"] == item_primeiro, "a camada não pode ser trocada quando nada mudou"
    assert est2["sha256"] == est1["sha256"]
    pedidos = servidor.recursos["/agendado/dados.geojson"].pedidos
    assert pedidos[-1]["if-none-match"] == est1["etag"], "a segunda passagem não mandou o condicional"

    # agora o arquivo muda de verdade
    novo = json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"nome": "a"},
             "geometry": {"type": "Point", "coordinates": [-47.88, -15.79]}},
            {"type": "Feature", "properties": {"nome": "b"},
             "geometry": {"type": "Point", "coordinates": [-46.63, -23.55]}},
        ],
    }).encode("utf-8")
    servidor.recursos["/agendado/dados.geojson"].corpo = novo
    terceira = f.sincronizar()
    assert terceira["estado"] == "concluido"
    assert terceira["resultado"]["recarregou"] is True
    assert terceira["resultado"]["feicoes"] == 2
    est3 = f.estado()
    assert est3["sincronizacoes"] == 3 and est3["recargas"] == 2
    assert est3["item_id"] != item_primeiro
    anota("etag_nao_recarrega", {
        "passagens": est3["sincronizacoes"], "recargas": est3["recargas"],
        "resultado_da_passagem_sem_mudanca": est2["ultimo_resultado"],
        "status_da_passagem_sem_mudanca": segunda["resultado"]["status"],
    })


def test_servidor_que_ignora_o_condicional_tambem_nao_recarrega(fonte, anota):
    """Servidor que responde 200 mesmo com If-None-Match igual: quem segura a recarga é o sha256."""
    f = fonte("/teimoso/dados.geojson", GEOJSON, "url teimosa",
              content_type="application/geo+json", ignorar_condicional=True)
    assert f.sincronizar()["resultado"]["recarregou"] is True
    segunda = f.sincronizar()
    assert segunda["resultado"] == {"recarregou": False, "motivo": "sha256_igual", "status": 200}
    est = f.estado()
    assert est["sincronizacoes"] == 2 and est["recargas"] == 1
    anota("sha256_segura_recarga", {"status": 200, "recargas": est["recargas"]})


# ---------------------------------------------------------------- refutação do adversário
def test_refutacao_csv_com_lat_lon_trocadas_falha_com_motivo(fonte, anota):
    f = fonte("/trocado/dados.csv", CSV_TROCADO, "url csv trocado", content_type="text/csv")
    job = f.sincronizar()
    assert job["estado"] == "falhou"
    assert "latitude" in (job["erro"] or "")
    est = f.estado()
    assert est["ultimo_resultado"] == "falhou"
    assert est["recargas"] == 0
    assert est["item_id"] is None, "arquivo recusado não pode ter deixado camada para trás"
    anota("refutacao_lat_lon_trocadas", {"estado": job["estado"], "erro": job["erro"]})


@pytest.mark.lento
def test_refutacao_kml_com_200_mil_pontos(fonte, cliente_demo_modulo, anota):
    """A outra metade da refutação: KML grande de verdade. Não é recusado — é MEDIDO.

    Marcado `lento` (fora de `pytest -m "not lento"`): gera 35,5 MB de KML no próprio processo do teste, e a
    carga de 200 mil pontos no PostGIS leva minutos. Numa máquina com várias trilhas rodando ao mesmo tempo e
    RAM livre perto de zero, deixá-lo na suíte de todo turno derrubaria o worker por falta de memória — o que
    é uma medida sobre a MÁQUINA, não sobre este item. Rode sozinho: `pytest -m lento tests/api/conexao`."""
    import random

    random.seed(7)
    partes = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for i in range(200_000):
        lon = -74 + random.random() * 40
        lat = -33 + random.random() * 38
        partes.append(f"<Placemark><name>p{i}</name><Point><coordinates>{lon:.6f},{lat:.6f}"
                      f"</coordinates></Point></Placemark>")
    partes.append("</Document></kml>")
    corpo = "".join(partes).encode("utf-8")

    f = fonte("/grande/dados.kml", corpo, "url kml grande",
              content_type="application/vnd.google-earth.kml+xml")
    inicio = time.monotonic()
    job = f.sincronizar(timeout=900)
    duracao = time.monotonic() - inicio
    est = f.estado()
    anota("refutacao_kml_200mil", {
        "bytes": len(corpo), "estado": job["estado"], "erro": job.get("erro"),
        "feicoes": (job.get("resultado") or {}).get("feicoes"), "segundos": round(duracao, 1),
    })
    assert job["estado"] == "concluido", job.get("erro")
    assert job["resultado"]["feicoes"] == 200_000
    assert est["recargas"] == 1


# ---------------------------------------------------------------- segurança na ponta da rota
def test_endereco_interno_recusado_pela_rota_e_pelo_job(cliente_demo_modulo, worker):
    """A URL interna já é recusada na CRIAÇÃO da conexão (L6-02-a valida antes do INSERT), então a
    sincronização nunca chega a existir para ela."""
    r = cliente_demo_modulo.post("/api/conexoes", json={
        "tipo": "http", "modo": "copiada", "nome": f"{PREFIXO_TESTE} interna {SUFIXO}",
        "url": "http://169.254.169.254/latest/meta-data/",
    })
    assert r.status_code == 422, r.text
    assert "ip_bloqueado" in json.dumps(r.json())


def test_redirecionamento_para_endereco_interno_falha_o_job(fonte, anota):
    """Aqui a URL cadastrada é pública de verdade; a armadilha só aparece no `Location`."""
    f = fonte("/redireciona/interno", b"", "url que redireciona",
              redireciona_para="http://169.254.169.254/latest/meta-data/")
    job = f.sincronizar()
    assert job["estado"] == "falhou"
    assert "ip_bloqueado:link_local:169.254.169.254" in (job["erro"] or "")
    est = f.estado()
    assert est["ultimo_resultado"] == "falhou" and est["recargas"] == 0
    anota("redirect_interno_recusado", {"erro": job["erro"]})


def test_conexao_referenciada_nao_aceita_arquivo_por_url(cliente_demo_modulo, servidor):
    r = cliente_demo_modulo.post("/api/conexoes", json={
        "tipo": "http", "modo": "referenciada", "nome": f"{PREFIXO_TESTE} referenciada {SUFIXO}",
        "url": servidor.url("/geojson/dados.geojson"),
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = cliente_demo_modulo.put(f"/api/conexoes/{cid}/arquivo", json={"agendado": False})
        assert r.status_code == 422, r.text
        assert r.json()["codigo"] == "conexao_incompativel"
    finally:
        cliente_demo_modulo.delete(f"/api/conexoes/{cid}")


def test_sincronizar_sem_configurar_e_404(cliente_demo_modulo, servidor):
    r = cliente_demo_modulo.post("/api/conexoes", json={
        "tipo": "http", "modo": "copiada", "nome": f"{PREFIXO_TESTE} sem config {SUFIXO}",
        "url": servidor.url("/geojson/dados.geojson"),
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        r = cliente_demo_modulo.post(f"/api/conexoes/{cid}/arquivo/sincronizar")
        assert r.status_code == 404, r.text
        assert r.json()["codigo"] == "arquivo_nao_configurado"
    finally:
        cliente_demo_modulo.delete(f"/api/conexoes/{cid}")
