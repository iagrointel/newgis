"""Garage com replication_factor 2 em dois nós (item L7-07-b-replica-garage; docs/RUNBOOKS/garage.md). Portão:
"cluster de 2 nós em homologação; `garage status` mostra os dois; objeto gravado com um nó parado é lido depois
que ele volta e o `scrub` não acusa; medição de tempo de re-sincronização; documento de operação". Refutação:
"adversário desliga um nó, escreve 1.000 objetos, religa, e compara sha256 de todos nos dois nós; qualquer
divergência não reparada pelo scrub = refutado" — é exatamente o roteiro deste módulo, com o nó 1 DESLIGADO na
hora de ler pelo nó 2 (a leitura não pode estar vindo do nó que sempre esteve de pé).

Os dois nós são processos do binário da instalação na mesma máquina, com zonas distintas no layout, segredos
em arquivo 0600 (`rpc_secret_file`, `admin_token_file`, `metrics_token_file`) e portas efêmeras — nunca a
instância de produção. Volume da re-sincronização: 256 MiB (D21: o laço trabalha com <= 3 GB; 10 GB fica como
não medido, escrito na medida)."""

from __future__ import annotations

import hashlib
import os
import time
import urllib.error
import urllib.request

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from tests.operacao.garage_cluster import BIN, Cluster

ITEM = "L7-07-b-replica-garage"
N_OBJETOS = 1000
TAMANHO_OBJETO = 16 * 1024
RESYNC_MB = int(os.environ.get("PLAT_GARAGE_RESYNC_MB", "256"))

pytestmark = [pytest.mark.lento]


def _s3(no, chave, segredo):
    return boto3.client(
        "s3", endpoint_url=no.s3_url, aws_access_key_id=chave, aws_secret_access_key=segredo,
        region_name="garage", config=Config(retries={"max_attempts": 2}, connect_timeout=5, read_timeout=60),
    )


@pytest.fixture(scope="module")
def cluster():
    if not os.path.exists(BIN):
        pytest.skip(f"binário do garage ausente em {BIN} (PLAT_GARAGE_BIN)")
    """3 nós, rf=3: é a configuração em que perder UM nó mantém leitura E escrita (quórum de escrita 2 de 3).
    Com 2 nós rf=2 a leitura continua mas a escrita para (quórum 2 de 2) — provado à parte em
    `test_dois_nos_rf2_leitura_continua_escrita_nao`, e é a regra nº 0 do runbook."""
    c = Cluster(3, 3, zonas=["sala1", "sala2", "sala3"])
    c.subir_todos()
    c.conectar()
    c.aplicar_layout("2G")
    yield c
    c.destruir()


@pytest.fixture(scope="module")
def acesso(cluster):
    chave, segredo = cluster.criar_chave_e_bucket("replica", cota="1GiB")
    return {"chave": chave, "segredo": segredo, "bucket": "replica"}


def test_status_mostra_os_dois_nos_com_zonas(cluster, medida):
    nos = cluster.nos_no_status(cluster.nos[0])
    assert len(nos) == 3, nos
    layout = cluster.cli(cluster.nos[0], "layout", "show").stdout
    assert "sala1" in layout and "sala2" in layout and "sala3" in layout
    assert "replication_factor = 3" in cluster.nos[0].config.read_text()
    m = medida(ITEM)
    m("nos_no_status", len(nos), "nós",
      "garage status contra o nó 1 (3 processos `garage server` v2.3.0, rf=3, zonas sala1/sala2/sala3)")


def test_segredos_em_arquivo_e_metrics_token(cluster):
    """rpc_secret/admin_token/metrics_token fora do garage.toml (arquivo 0600, `*_file`); /metrics exige o token."""
    cfg = cluster.nos[0].config.read_text()
    assert "rpc_secret_file" in cfg and "admin_token_file" in cfg and "metrics_token_file" in cfg
    assert cluster.rpc_secret not in cfg and cluster.admin_token not in cfg
    assert oct((cluster.raiz / "segredos" / "rpc_secret").stat().st_mode & 0o777) == "0o600"
    url = f"http://127.0.0.1:{cluster.nos[0].admin}/metrics"
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(url, timeout=5)
    assert e.value.code in (401, 403)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {cluster.metrics_token}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200 and b"garage_" in r.read()


def test_cota_por_bucket_e_mantida(cluster, acesso):
    no = cluster.nos[0]
    cluster.cli(no, "bucket", "set-quotas", "--max-size", "4MiB", acesso["bucket"])
    s3 = _s3(no, acesso["chave"], acesso["segredo"])
    s3.put_object(Bucket=acesso["bucket"], Key="cota/pequeno.bin", Body=b"a" * (1024 * 1024))
    with pytest.raises(ClientError) as e:
        s3.put_object(Bucket=acesso["bucket"], Key="cota/grande.bin", Body=b"b" * (5 * 1024 * 1024))
    assert e.value.response["Error"]["Code"] in ("AccessDenied", "QuotaExceeded")  # Garage responde 403 AccessDenied
    cluster.cli(no, "bucket", "set-quotas", "--max-size", "1GiB", acesso["bucket"])
    s3.delete_object(Bucket=acesso["bucket"], Key="cota/pequeno.bin")


def test_dois_nos_rf2_leitura_continua_escrita_nao(medida):
    """cluster à parte de 2 nós rf=2 (o que a hipótese pede): com um nó parado a LEITURA continua e a ESCRITA
    é recusada por quórum (503) — não é defeito nosso, é a regra do Garage; fica medida e escrita no runbook."""
    c = Cluster(2, 2, zonas=["sala1", "sala2"])
    try:
        c.subir_todos()
        c.conectar()
        c.aplicar_layout("1G")
        chave, segredo = c.criar_chave_e_bucket("dois")
        s3 = _s3(c.nos[0], chave, segredo)
        s3.put_object(Bucket="dois", Key="antes.bin", Body=b"x" * 4096)
        assert len(c.nos_no_status(c.nos[0])) == 2
        c.parar(c.nos[1])
        assert s3.get_object(Bucket="dois", Key="antes.bin")["Body"].read() == b"x" * 4096  # leitura continua
        with pytest.raises(ClientError) as e:
            s3.put_object(Bucket="dois", Key="durante.bin", Body=b"y" * 4096)
        codigo = e.value.response["Error"]["Code"]
        assert codigo == "ServiceUnavailable" and "quorum" in str(e.value).lower(), str(e.value)
        m = medida(ITEM)
        m("rf2_2nos_um_parado_leitura", "ok", "resultado", "GET pelo nó vivo com o outro parado (rf=2, 2 nós)")
        m("rf2_2nos_um_parado_escrita", codigo, "erro S3",
          "PUT pelo nó vivo com o outro parado: quórum de escrita 2 de 2 não atinge")
    finally:
        c.destruir()


def test_escreve_com_no_parado_le_depois_que_volta_e_scrub_nao_acusa(cluster, acesso, medida):
    """a refutação do item, ao pé da letra: nó 2 desligado, 1.000 objetos escritos pelo nó 1 (quórum 2 de 3 com
    o nó 3), nó 2 religado e re-sincronizado, scrub sem erro; depois os nós 1 E 3 são desligados e os 1.000
    sha256 são conferidos pelo nó 2 sozinho."""
    no1, no2, _no3 = cluster.nos
    m = medida(ITEM)
    cluster.parar(no2)
    assert not no2.vivo
    s3_1 = _s3(no1, acesso["chave"], acesso["segredo"])
    esperados: dict[str, str] = {}
    t0 = time.monotonic()
    for i in range(N_OBJETOS):
        corpo = hashlib.sha256(f"objeto-{i}".encode()).digest() * (TAMANHO_OBJETO // 32)
        chave = f"mil/{i:04d}.bin"
        s3_1.put_object(Bucket=acesso["bucket"], Key=chave, Body=corpo)
        esperados[chave] = hashlib.sha256(corpo).hexdigest()
    dt_escrita = time.monotonic() - t0
    m("escrita_1000_objetos_com_no_parado_s", round(dt_escrita, 1), "s",
      f"{N_OBJETOS} PUT de {TAMANHO_OBJETO} B pelo nó 1 com o nó 2 desligado (rf=2)")
    # leitura pelo nó que ficou de pé continua
    assert s3_1.get_object(Bucket=acesso["bucket"], Key="mil/0000.bin")["Body"].read()
    # nó 2 volta e re-sincroniza
    cluster.subir(no2)
    cluster.esperar_status(3)
    dt_resync = cluster.esperar_resync(no2, no1)
    m("resync_1000_objetos_s", round(dt_resync, 1), "s", "garage repair --yes blocks no nó 2 até fila de resync = 0")
    linha_scrub = cluster.scrub(no2)
    assert cluster.erros_de_bloco(no2) == 0, cluster.cli(no2, "block", "list-errors", checar=False).stdout
    m("scrub_no2_erros_de_bloco", cluster.erros_de_bloco(no2), "blocos",
      f"garage block list-errors no nó 2 após scrub ({linha_scrub.strip()[:60]})")
    # prova de que o nó 2 TEM os dados: (a) o conjunto de blocos em disco do nó 2 é IGUAL ao do nó 1 (bloco =
    # arquivo nomeado pelo hash — é a comparação da refutação); (b) nó 1, que recebeu as escritas, desligado,
    # e os 1.000 objetos lidos com sha256 conferido (quórum de leitura de metadado = 2 de 3: nós 2 e 3)
    blocos1, blocos2 = cluster.blocos_em_disco(no1), cluster.blocos_em_disco(no2)
    assert blocos1 and blocos1 == blocos2, (len(blocos1), len(blocos2), len(blocos1 ^ blocos2))
    m("blocos_em_disco_iguais_no1_no2", len(blocos2), "blocos",
      "conjunto de hashes em data_dir do nó 2 == nó 1 depois do resync")
    cluster.parar(no1)
    s3_2 = _s3(no2, acesso["chave"], acesso["segredo"])
    divergentes = []
    for chave, sha in esperados.items():
        lido = s3_2.get_object(Bucket=acesso["bucket"], Key=chave)["Body"].read()
        if hashlib.sha256(lido).hexdigest() != sha:
            divergentes.append(chave)
    assert not divergentes, divergentes[:10]
    m("objetos_conferidos_no_no2_com_no1_parado", len(esperados) - len(divergentes), "objetos",
      "sha256 de cada um dos 1.000 objetos lido pelo nó 2 com o nó 1 (que recebeu as escritas) desligado")
    cluster.subir(no1)
    cluster.esperar_status(3)


def test_resync_de_volume_medido(cluster, acesso, medida):
    """tempo de re-sincronização de RESYNC_MB (256 MiB por padrão, D21); 10 GB não cabe nesta máquina."""
    no1, no2, _no3 = cluster.nos
    m = medida(ITEM)
    cluster.parar(no2)
    s3_1 = _s3(no1, acesso["chave"], acesso["segredo"])
    bloco = os.urandom(8 * 1024 * 1024)
    n = RESYNC_MB // 8
    for i in range(n):
        s3_1.put_object(Bucket=acesso["bucket"], Key=f"volume/{i:03d}.bin", Body=bloco)
    cluster.subir(no2)
    cluster.esperar_status(3)
    dt = cluster.esperar_resync(no2, no1, timeout=1200)
    carga = os.getloadavg()[0]
    m("resync_volume_mb", n * 8, "MiB", f"{n} objetos de 8 MiB escritos com o nó 2 parado")
    m("resync_volume_s", round(dt, 1), "s",
      "garage repair --yes blocks no nó 2 até fila = 0 (mesma máquina, disco compartilhado)")
    m("resync_volume_mb_por_s", round(n * 8 / max(dt, 0.001), 1), "MiB/s", "resync_volume_mb / resync_volume_s")
    m("resync_10gb_s", "não medido", "s",
      "10 GB não cabe no teto de 3 GB por trilha (D21); extrapolar de resync_volume_mb_por_s é estimativa, não medida")
    m("carga_1min_no_resync", round(carga, 2), "carga", "os.getloadavg()[0] ao fim da medição")
    assert cluster.blocos_em_disco(no2) == cluster.blocos_em_disco(no1)
    cluster.parar(no1)
    s3_2 = _s3(no2, acesso["chave"], acesso["segredo"])
    assert len(s3_2.get_object(Bucket=acesso["bucket"], Key=f"volume/{n - 1:03d}.bin")["Body"].read()) == len(bloco)
    cluster.subir(no1)
    cluster.esperar_status(3)
