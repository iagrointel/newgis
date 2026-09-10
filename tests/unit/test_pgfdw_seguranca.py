"""Refutação do item L0-04-i-fonte-registrada: "adversário aponta para o próprio iagro_sat (deve recusar por
lista de hosts proibidos)" e "injeta no nome da tabela". Diferente da defesa de SSRF HTTP
(`tests/unit/test_conexao_seguranca.py`), o conector `postgres_fdw` conecta a um Postgres de cliente que pode
legitimamente estar numa rede privada/VPN — por isso `pgfdw.validar_alvo` bloqueia MENOS categoria de IP (só
metadado de nuvem/multicast/não-especificado) e MAIS por lista explícita (o nome do banco de produção da casa
e o (host,porta,banco) do PLAT_DSN desta própria instalação)."""

import pytest

from app.conexao import pgfdw
from app.settings import settings


# --------------------------------------------------------------------- alvo proibido (auto-referência)
def test_recusa_banco_iagro_sat_em_qualquer_host():
    """O adversário pode tentar em QUALQUER host — o nome do banco sozinho já recusa (defesa mais forte que
    checar só o host, porque o Postgres pode ter réplicas/hosts alternativos com o mesmo nome de banco)."""
    with pytest.raises(pgfdw.ErroAlvoProibido) as exc:
        pgfdw.validar_alvo("algum-host-qualquer.example.org", 5432, "iagro_sat")
    assert "banco_proibido" in exc.value.motivo

    with pytest.raises(pgfdw.ErroAlvoProibido) as exc2:
        pgfdw.validar_alvo("127.0.0.1", 5432, "IAGRO_SAT")  # maiúsculas: comparação sempre em minúsculas
    assert "banco_proibido" in exc2.value.motivo


def test_recusa_mesmo_servidor_do_plat_dsn_mesmo_com_outro_nome_de_dbname_igual():
    """(host, porta, banco) idênticos ao PLAT_DSN desta trilha (127.0.0.1:5432/iagro_sat) — recusa pela
    checagem explícita de auto-referência, mesmo que a checagem de nome de banco (acima) já bastasse; prova
    que as DUAS defesas cobrem o mesmo alvo por caminhos diferentes."""
    from urllib.parse import urlsplit

    partes = urlsplit(settings.PLAT_DSN)
    host, porta, banco = partes.hostname, partes.port or 5432, (partes.path or "/").lstrip("/")
    assert banco  # a trilha sempre aponta para iagro_sat
    with pytest.raises(pgfdw.ErroAlvoProibido):
        pgfdw.validar_alvo(host, porta, banco)


def test_aceita_docker_local_com_banco_e_porta_diferentes():
    """O host de teste (docker local, mesma máquina) usa PORTA e BANCO diferentes do PLAT_DSN — só o host
    (127.0.0.1) coincide, e loopback NÃO está na lista de categorias bloqueadas deste conector (diferente do
    HTTP): um Postgres de cliente pode estar em qualquer rede, inclusive uma acessível por túnel local."""
    ips = pgfdw.validar_alvo("127.0.0.1", 55499, "amostra_aberta")
    assert "127.0.0.1" in ips


@pytest.mark.parametrize(
    "host,motivo_esperado",
    [
        ("169.254.169.254", "link_local"),  # metadado de nuvem: continua bloqueado (defesa em profundidade)
        ("224.0.0.1", "multicast"),
        ("0.0.0.0", "nao_especificado"),
    ],
)
def test_recusa_categorias_de_ip_ainda_bloqueadas(host, motivo_esperado):
    with pytest.raises(pgfdw.ErroAlvoProibido) as exc:
        pgfdw.validar_alvo(host, 5432, "qualquer_banco")
    assert motivo_esperado in exc.value.motivo


def test_aceita_ip_privado_comum_rede_de_cliente():
    """Diferente da defesa HTTP: 10.x/172.16.x/192.168.x NÃO são recusados aqui — o Postgres de um cliente
    real costuma estar numa rede privada/VPN (decisão documentada em app/limites.py CONEXAO_PG_*)."""
    assert pgfdw.validar_alvo("10.20.30.40", 5432, "banco_do_cliente") == ("10.20.30.40",)
    assert pgfdw.validar_alvo("192.168.1.50", 5432, "banco_do_cliente") == ("192.168.1.50",)


# --------------------------------------------------------------------- injeção no nome da tabela/schema
@pytest.mark.parametrize(
    "nome",
    [
        "tabela; DROP TABLE plat.item;--",
        "tabela\" DROP TABLE x --",
        "tabela'); DROP TABLE x; --",
        "tabela--comentario",
        "tabela/*com*/",
        "tabela com espaco",
        "",
        "1tabela",  # não pode começar com dígito
        "tabela;select 1",
        "a" * 64,  # passa do limite de identificador do Postgres (63)
    ],
)
def test_identificador_ok_recusa_injecao(nome):
    assert pgfdw.identificador_ok(nome) is False


@pytest.mark.parametrize("nome", ["municipios", "estados", "precipitacao_mensal", "_tabela", "t1", "T_Maiuscula"])
def test_identificador_ok_aceita_nomes_normais(nome):
    assert pgfdw.identificador_ok(nome) is True


def test_colunas_da_tabela_recusa_nome_injetado_antes_de_qualquer_sql():
    """`colunas_da_tabela` nunca chega a abrir conexão com um nome de tabela inválido — a validação de
    identificador acontece antes de `conectar`."""
    alvo = pgfdw.AlvoPg(
        host="127.0.0.1", porta=55499, banco="amostra_aberta", usuario="ro_amostra", schema_remoto="public"
    )
    with pytest.raises(pgfdw.ErroAlvoProibido) as exc:
        pgfdw.colunas_da_tabela(alvo, "senha-nao-importa", "municipios; DROP TABLE municipios;--")
    assert "nome_de_tabela_invalido" in exc.value.motivo


# --------------------------------------------------------------------- mapeamento de geometria
@pytest.mark.parametrize(
    "tipo_postgis,esperado",
    [
        (None, "nenhuma"),
        ("POINT", "Point"),
        ("MULTIPOLYGON", "MultiPolygon"),
        ("LINESTRING", "LineString"),
        ("algo_nao_mapeado", "Geometry"),
    ],
)
def test_geometria_enum(tipo_postgis, esperado):
    assert pgfdw.geometria_enum(tipo_postgis) == esperado


# --------------------------------------------------------------------- alvo_da_url
def test_alvo_da_url_recusa_userinfo():
    with pytest.raises(ValueError, match="userinfo_na_url"):
        pgfdw.alvo_da_url("postgres://usuario:senha@host/banco")


def test_alvo_da_url_recusa_esquema_http():
    with pytest.raises(ValueError, match="esquema_nao_permitido"):
        pgfdw.alvo_da_url("http://host:5432/banco")


def test_alvo_da_url_ok():
    assert pgfdw.alvo_da_url("postgres://127.0.0.1:55499/amostra_aberta") == ("127.0.0.1", 55499, "amostra_aberta")
