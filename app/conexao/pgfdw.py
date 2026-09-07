"""Conector `postgres_fdw` de `plat.conexao` (item L0-04-i-fonte-registrada; ver
docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md).

"Fonte de dado registrada" = o "data store item" de Esri Enterprise 11.4 ("Data store items", ver
`docs/PARIDADE.md`) / o "store" do GeoServer, restrito ao conector PostgreSQL/PostGIS externo: registra a
conexão (usa o modelo genérico `plat.conexao` de L6-02-a), lista as tabelas do banco do cliente, e publica em
massa — uma camada REFERENCIADA por tabela, nunca copiando dado (o "bulk publish" do Esri). A tabela
estrangeira vira `plat.item` tipo `camada_vetorial` com `dados.fonte = "referenciada"`; o objeto físico é uma
VIEW sobre uma `FOREIGN TABLE` criada por `plat.conexao_fdw_publicar` (SECURITY DEFINER, migração
20260907T0148 — `plat_app` não tem CREATE nem USAGE na extensão `postgres_fdw`, só essa função tem).

Esta conexão é sempre TCP direto a um Postgres, nunca HTTP: a defesa de SSRF do módulo irmão
(`app/conexao/seguranca.py`, feita para requisições HTTP) não se aplica ao pé da letra — um Postgres de
cliente pode estar legitimamente numa rede privada/VPN, o que um alvo HTTP arbitrário não deveria estar.
Por isso o bloqueio aqui é MENOR em categoria de IP (só link_local/multicast/não-especificado — cobre
metadado de nuvem) e MAIOR em lista explícita: qualquer host que resolva para o mesmo (host, porta, banco)
do PLAT_DSN desta própria instalação é recusado, e o nome de banco `iagro_sat` é recusado em QUALQUER host
(o adversário do item aponta para o próprio banco da casa — `validar_alvo` recusa nos dois testes,
independente de qual dos dois o adversário tentar primeiro).

Nomes de tabela/schema do cliente NUNCA entram em SQL por concatenação: `_IDENTIFICADOR` valida com regex
antes de qualquer uso, e a lista de colunas publicada vem SEMPRE de uma segunda leitura fresca do
`pg_catalog` do banco remoto no momento de publicar — nunca do que o corpo da requisição alegou ter visto
antes (o adversário injeta no NOME da tabela; `_IDENTIFICADOR` recusa antes de qualquer consulta)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import psycopg2
import psycopg2.extras

from app import limites
from app.conexao import seguranca
from app.settings import settings

_IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class ErroAlvoProibido(ValueError):
    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


class ErroFonteIndisponivel(RuntimeError):
    """A conexão TCP/autenticação com o Postgres do cliente falhou. Vira 503 na rota — a camada e a conexão
    continuam no catálogo, nada é apagado por causa disto (portão de pronto do item)."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


@dataclass(frozen=True)
class AlvoPg:
    host: str
    porta: int
    banco: str
    usuario: str
    schema_remoto: str


def identificador_ok(nome: str) -> bool:
    return bool(_IDENTIFICADOR.match(nome or ""))


def alvo_da_url(url: str) -> tuple[str, int, str]:
    """`postgres://host:porta/banco` -> (host, porta, banco); nunca aceita userinfo na URL (a senha vive só
    em `credencial`, cifrada — mesma regra do resto de `plat.conexao`)."""
    partes = urlsplit(url or "")
    if partes.scheme.lower() not in ("postgres", "postgresql"):
        raise ValueError("esquema_nao_permitido")
    if partes.username is not None or partes.password is not None:
        raise ValueError("userinfo_na_url")
    if not partes.hostname:
        raise ValueError("host_ausente")
    banco = (partes.path or "/").lstrip("/")
    if not banco:
        raise ValueError("banco_ausente_na_url")
    return partes.hostname, partes.port or 5432, banco


def _alvo_producao() -> tuple[str, int, str]:
    """(host, porta, banco) do PLAT_DSN desta própria instalação — o mesmo banco `iagro_sat` compartilhado
    por todas as trilhas (ADR 0001). Usado só para a checagem explícita de auto-referência."""
    partes = urlsplit(settings.PLAT_DSN)
    banco = (partes.path or "/").lstrip("/")
    return partes.hostname or "", partes.port or 5432, banco


def validar_alvo(host: str, porta: int, banco: str) -> tuple[str, ...]:
    """Recusa (a) nome de banco na lista de proibidos explícita (`iagro_sat`, em QUALQUER host — é o teste do
    adversário do item), (b) IP resolvido em categoria bloqueada (metadado de nuvem etc.), (c) o MESMO
    (host, porta, banco) do PLAT_DSN desta instalação (defesa redundante da (a), pelo caminho do IP em vez do
    nome). Devolve os IPs resolvidos (para log/depuração), nunca None."""
    if not host or not (1 <= porta <= 65535):
        raise ErroAlvoProibido("alvo_malformado")
    if (banco or "").strip().lower() in limites.CONEXAO_PG_BANCOS_PROIBIDOS:
        raise ErroAlvoProibido("banco_proibido:" + banco)
    try:
        ips = seguranca.resolver_ips_bloqueando_categorias(host, porta, limites.CONEXAO_PG_CATEGORIAS_BLOQUEADAS)
    except seguranca.ErroURLInsegura as e:
        raise ErroAlvoProibido(e.motivo) from e
    prod_host, prod_porta, prod_banco = _alvo_producao()
    if porta == prod_porta and (banco or "").strip().lower() == (prod_banco or "").strip().lower():
        try:
            ips_prod = seguranca.resolver_ips_bloqueando_categorias(prod_host, prod_porta, frozenset())
        except seguranca.ErroURLInsegura:
            ips_prod = ()
        if set(ips) & set(ips_prod):
            raise ErroAlvoProibido("mesmo_servidor_do_iagro_sat")
    return ips


def conectar(alvo: AlvoPg, senha: str):
    """Conexão psycopg2 direta ao Postgres do cliente, timeout curto, statement_timeout curto — nunca prende
    a rota por causa de um banco de cliente lento ou fora do ar. Qualquer falha vira `ErroFonteIndisponivel`
    (nunca deixa a exceção crua do driver subir até a rota)."""
    validar_alvo(alvo.host, alvo.porta, alvo.banco)
    try:
        conn = psycopg2.connect(
            host=alvo.host, port=alvo.porta, dbname=alvo.banco, user=alvo.usuario, password=senha,
            connect_timeout=limites.CONEXAO_PG_CONECTAR_TIMEOUT_S,
            options=f"-c statement_timeout={limites.CONEXAO_PG_ESTATEMENT_TIMEOUT_MS}",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.set_session(readonly=True, autocommit=True)
        return conn
    except psycopg2.OperationalError as e:
        raise ErroFonteIndisponivel(_mensagem_amigavel(e)) from e


def _mensagem_amigavel(e: Exception) -> str:
    texto = str(e).strip().splitlines()[0] if str(e).strip() else "erro_de_conexao"
    return texto[:300]


@dataclass(frozen=True)
class ResultadoTestePg:
    ok: bool
    status: int | None  # sempre None (não é HTTP); existe só para o mesmo formato de ResultadoBusca
    mensagem: str
    latencia_ms: int
    superuser: bool = False
    aviso: str | None = None


def testar_e_medir(alvo: AlvoPg, senha: str) -> ResultadoTestePg:
    """Mesmo formato de `seguranca.ResultadoBusca` (ok/status/mensagem/latencia_ms) para a rota genérica
    `POST /api/conexoes/{id}/testar` conseguir tratar os dois protocolos igual; nunca levanta — falha vira
    `ok=False` com o motivo em `mensagem` (mesma regra de `buscar_seguro`)."""
    import time

    inicio = time.monotonic()
    try:
        r = testar(alvo, senha)
    except (ErroFonteIndisponivel, ErroAlvoProibido) as e:
        return ResultadoTestePg(
            ok=False, status=None, mensagem=e.motivo, latencia_ms=int((time.monotonic() - inicio) * 1000)
        )
    return ResultadoTestePg(
        ok=True, status=None, mensagem=f"conectado_como_{r['usuario']}",
        latencia_ms=int((time.monotonic() - inicio) * 1000), superuser=r["superuser"], aviso=r["aviso"],
    )


def testar(alvo: AlvoPg, senha: str) -> dict:
    """Conecta, confere se o usuário é superusuário (item: "adversário registra com usuário superuser — deve
    avisar"; nunca recusamos o REGISTRO por isto, só avisamos e, adiante, a publicação nunca concede
    privilégio de escrita além do que a VIEW final já limita a SELECT)."""
    conn = conectar(alvo, senha)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user AS usuario, "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS superuser, "
                "current_setting('server_version') AS versao"
            )
            r = cur.fetchone()
        return {
            "ok": True, "usuario": r["usuario"], "superuser": bool(r["superuser"]), "versao": r["versao"],
            "aviso": "usuario_e_superuser_privilegio_de_escrita_nao_e_usado" if r["superuser"] else None,
        }
    finally:
        conn.close()


def listar_tabelas(alvo: AlvoPg, senha: str) -> list[dict]:
    """Tabelas base (`relkind='r'`) do schema `alvo.schema_remoto`, via `pg_catalog` (nunca
    `information_schema` por string concatenada) — schema já validado por `_IDENTIFICADOR` antes de chegar
    aqui (ver rota). Detecta coluna de geometria via `public.geometry_columns` quando o PostGIS existe no
    banco remoto; senão, cada tabela aparece como não espacial (`geometria: null` na resposta — a rota de
    publicar decide "nenhuma")."""
    if not identificador_ok(alvo.schema_remoto):
        raise ErroAlvoProibido("schema_invalido")
    conn = conectar(alvo, senha)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.relname AS tabela, "
                "(SELECT count(*) FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 "
                " AND NOT a.attisdropped) AS n_colunas, "
                "pg_catalog.obj_description(c.oid) AS comentario "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = %s ORDER BY c.relname LIMIT %s",
                (alvo.schema_remoto, limites.CONEXAO_PG_TABELAS_MAX),
            )
            tabelas = [dict(r) for r in cur.fetchall()]
            geometrias: dict[str, dict] = {}
            try:
                with conn.cursor() as cur2:
                    cur2.execute(
                        "SELECT f_table_name AS tabela, f_geometry_column AS coluna, type AS tipo, srid "
                        "FROM public.geometry_columns WHERE f_table_schema = %s",
                        (alvo.schema_remoto,),
                    )
                    for row in cur2.fetchall():
                        geometrias[row["tabela"]] = dict(row)
            except psycopg2.Error:
                pass  # PostGIS ausente no banco remoto: segue sem geometria (não é erro do item)
        for t in tabelas:
            g = geometrias.get(t["tabela"])
            t["geometria_coluna"] = g["coluna"] if g else None
            t["geometria_tipo"] = g["tipo"] if g else None
            t["srid"] = g["srid"] if g else None
        return tabelas
    finally:
        conn.close()


_GEOMETRIA_ENUM = {
    "POINT": "Point", "MULTIPOINT": "MultiPoint", "LINESTRING": "LineString",
    "MULTILINESTRING": "MultiLineString", "POLYGON": "Polygon", "MULTIPOLYGON": "MultiPolygon",
    "GEOMETRY": "Geometry", "GEOMETRYCOLLECTION": "Geometry",
}


def geometria_enum(tipo_postgis: str | None) -> str:
    """PostGIS `geometry_columns.type` (ex. "MULTIPOLYGON") -> o vocabulário de `tipo_item.camada_vetorial`
    (ex. "MultiPolygon"); tipo não mapeado ou ausente vira "nenhuma" (a tabela publica como não espacial)."""
    if not tipo_postgis:
        return "nenhuma"
    return _GEOMETRIA_ENUM.get(tipo_postgis.upper(), "Geometry")


def colunas_da_tabela(alvo: AlvoPg, senha: str, tabela: str) -> list[dict]:
    """Leitura FRESCA das colunas de `tabela` no momento de publicar (nunca reaproveita o que uma chamada
    anterior a `listar_tabelas` alegou) — `format_type` devolve a sintaxe de tipo pronta para
    `CREATE FOREIGN TABLE` (inclusive `geometry(Point,4326)` quando o PostGIS registra o typmod)."""
    if not identificador_ok(tabela):
        raise ErroAlvoProibido("nome_de_tabela_invalido:" + str(tabela))
    conn = conectar(alvo, senha)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.attname AS nome, pg_catalog.format_type(a.atttypid, a.atttypmod) AS tipo_pg "
                "FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped "
                "ORDER BY a.attnum LIMIT %s",
                (alvo.schema_remoto, tabela, limites.CONEXAO_PG_COLUNAS_MAX),
            )
            colunas = [dict(r) for r in cur.fetchall()]
        if not colunas:
            raise ErroAlvoProibido("tabela_inexistente:" + tabela)
        return colunas
    finally:
        conn.close()
