"""Fixtures da exportação de camada (item L0-04-h-exportar).

Constrói o cenário que o portão do item exige, e nada além disso:

- DOIS inquilinos temporários (`zt-inq-*`, criados e apagados pelo superadmin, nunca os de demonstração): o A
  com a camada de 100 mil feições e um usuário editor sem privilégio de exportar; o B só para a prova de que a
  exportação de um inquilino nunca traz linha do outro;
- a camada é criada por SQL (100 mil pontos de `generate_series` sobre a área de Guarulhos) e passa pela MESMA
  `plat.camada_preparar` da ingestão — logo tem as mesmas colunas obrigatórias, a mesma RLS FORCE e os mesmos
  gatilhos de uma camada carregada pelo usuário. Fazer 100 mil feições subirem por `POST /api/importacoes`
  levaria minutos por rodada e não provaria nada a mais sobre a EXPORTAÇÃO;
- um worker próprio em subprocesso (a unidade `plat-worker` do sistema roda no schema `plat` de produção e
  nunca veria os jobs de uma base de trilha).
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import InquilinoTemporario, Usuarios

ROOT = Path(__file__).resolve().parents[3]
FEICOES = 100_000


# ---------------------------------------------------------------- worker próprio (a base é a da trilha)
def porta_livre() -> int:
    """Porta efêmera livre no momento. Porta FIXA aqui é armadilha medida: às 16:21 de 06/09 a :18162 já
    estava ocupada pelo worker de OUTRA trilha desta mesma máquina; o `/saude` respondeu, o teste achou que
    era o seu worker e ficou 18 minutos esperando um job que ninguém ia pegar (o worker de lá fala com outro
    schema). Por isso, além da porta efêmera, a checagem abaixo confere o NOME do worker que respondeu."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class WorkerDeTeste:
    def __init__(self, env: dict, nome: str, porta: int | None = None, processos: int = 2):
        porta = porta or porta_livre()
        ambiente = dict(os.environ)
        ambiente.update({k: v for k, v in env.items() if v is not None})
        ambiente.update({"PYTHONNOUSERSITE": "1", "PLAT_WORKER_NOME": nome,
                         "PLAT_WORKER_PROCESSOS": str(processos),
                         "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}"})
        self.porta = porta
        # stderr num arquivo, nunca DEVNULL: quando um filho do worker morre por SINAL (o abort do DuckDB
        # depois de fork foi assim), a única pista fica na saída de erro do processo — jogá-la fora custou
        # uma hora nesta trilha
        self.log = pathlib.Path(tempfile.gettempdir()) / f"plat-worker-teste-{os.getpid()}.log"
        self.arquivo_log = self.log.open("wb")
        self.proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
                                     stdout=self.arquivo_log, stderr=self.arquivo_log)
        for _ in range(100):
            try:
                s = self.saude()
                if s.get("nome_base") == nome:
                    break
                self.proc.kill()
                pytest.fail(f"a porta {porta} respondeu com o worker {s.get('nome_base')!r}, não com {nome!r}: "
                            "há outro worker ocupando a porta (ver `porta_livre` acima)")
            except OSError:
                time.sleep(0.2)
        else:
            self.proc.kill()
            pytest.fail(f"worker de teste não respondeu em /saude (:{porta}) em 20 s")

    def saude(self) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/saude", timeout=1) as r:
            return json.loads(r.read().decode("utf-8"))

    def cauda_do_log(self, linhas: int = 20) -> str:
        try:
            return "\n".join(self.log.read_text(errors="replace").splitlines()[-linhas:])
        except OSError:
            return ""

    def parar(self) -> None:
        try:
            self.arquivo_log.close()
        except OSError:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


@pytest.fixture(scope="session")
def worker_exportacao(env):
    w = WorkerDeTeste(env, f"teste-exportacao-{os.getpid()}")
    yield w
    w.parar()


# ---------------------------------------------------------------- inquilinos e camada
class InquilinoDeExportacao(InquilinoTemporario):
    """`InquilinoTemporario` com slug SEM HÍFEN.

    Achado desta trilha em 06/09/2026, gravado aqui para não se perder: `plat.camada_schema_garantir` e
    `plat.camada_preparar` (migração 029) validam o slug com `^[a-z][a-z0-9_]{0,60}$` e o schema com
    `^d_[a-z0-9_]{1,60}$` — sem hífen — enquanto `POST /api/plataforma/inquilinos` ACEITA hífen
    ("minúsculas, dígitos e hífen, 2 a 39 caracteres") e `plat.tenant_criar` cria o schema `d_<slug>` com
    hífen sem reclamar. Resultado: num inquilino de slug hifenizado a ingestão vetorial falha com
    `slug_invalido`. Não é bug DESTE item (é do L0-04-c) e está relatado no handoff; aqui a fixture só evita
    o hífen para poder usar as MESMAS funções da ingestão ao semear a camada.
    """

    def __init__(self, sessao_plat, config=None):
        self.slug = f"ztexp{secrets.token_hex(4)}"
        r = sessao_plat.post(
            "/api/plataforma/inquilinos",
            json={"slug": self.slug, "nome": f"Inquilino de exportacao {self.slug}", "admin_login": "admin",
                  "admin_nome": "Administrador de teste", "config": config or {}},
        )
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.admin_id = r.json()["admin"]["id"]
        temporaria = r.json()["senha_temporaria"]
        from tests.api.conftest import entrar, novo_cliente

        self.admin = novo_cliente()
        assert entrar(self.admin, self.slug, "admin", temporaria).status_code == 200
        self.senha = "Senha-do-admin-1" + secrets.token_hex(3)
        assert self.admin.put("/api/eu/senha", json={"atual": temporaria, "nova": self.senha}).status_code == 204
        self._plat = sessao_plat


@pytest.fixture(scope="session")
def inquilino_a(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="session")
def inquilino_b(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


def conexao(env):
    """Conexão como `plat_app` com o cursor que honra PLAT_SCHEMA. **Sem autocommit de propósito**: o contexto
    do inquilino é gravado com `set_config(..., true)`, que é LOCAL À TRANSAÇÃO — em autocommit cada comando é
    a sua própria transação e o contexto some antes da consulta seguinte (foi assim que a 1ª rodada deste teste
    falhou com `schema_de_outro_inquilino`). Quem usa fecha com `con.commit()`."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    return con


def _contexto(con, tenant_id: int, usuario_id: int) -> None:
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', 'teste-exportacao', true)",
            (str(tenant_id), str(usuario_id)),
        )


def semear_camada(env, inq, feicoes: int, titulo: str, prefixo: str = "ponto") -> dict:
    """Cria `d_<slug>.c_<16 hex>` com `feicoes` pontos e publica o item `camada_vetorial`. Devolve o item."""
    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    schema = f"d_{inq.slug}"
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inq.slug,))
            cur.execute(
                f'CREATE TABLE "{schema}"."{tabela}" ('
                " fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                " nome text, categoria text, area_ha double precision, quantidade integer,"
                " geom geometry(Point, 4674))"
            )
            cur.execute(
                # `%%` porque este comando leva parâmetros: com params, o psycopg2 interpola `%` e um
                # `i % 3` cru vira IndexError antes de o SQL sair daqui
                f'INSERT INTO "{schema}"."{tabela}" (nome, categoria, area_ha, quantidade, geom) '
                "SELECT %s || ' ' || i, (ARRAY['mata','pasto','urbano'])[1 + (i %% 3)], "
                "       round((i %% 977) * 1.25 + 0.5)::double precision + 0.5, i %% 100, "
                "       ST_SetSRID(ST_MakePoint(-46.55 + (i %% 317) * 0.0009, -23.45 + (i / 317) * 0.0009), 4674) "
                "FROM generate_series(1, %s) i",
                (prefixo, feicoes),
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4674, "Point", inq.admin_id))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            dados = {
                "schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4674, "fonte": "hospedada",
                "campos": [
                    {"nome": "fid", "tipo": "bigint"}, {"nome": "nome", "tipo": "text"},
                    {"nome": "categoria", "tipo": "text"}, {"nome": "area_ha", "tipo": "double precision"},
                    {"nome": "quantidade", "tipo": "integer"},
                ],
            }
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s::jsonb, "
                "pg_total_relation_size(%s::regclass), %s, %s)",
                (item_id, inq.id, titulo, inq.admin_id, json.dumps(dados), f'"{schema}"."{tabela}"',
                 inq.admin_id, inq.admin_id),
            )
        con.commit()
    finally:
        con.close()
    return {"item_id": item_id, "schema": schema, "tabela": tabela, "feicoes": feicoes, "dados": dados}


@pytest.fixture(scope="session")
def camada_a(env, inquilino_a):
    """A camada do portão: 100 mil feições no inquilino A."""
    return semear_camada(env, inquilino_a, FEICOES, "zt camada de exportacao (100 mil feicoes)")


@pytest.fixture(scope="session")
def camada_b(env, inquilino_b):
    """Camada do inquilino B, com os MESMOS nomes de campo — é o que torna a prova cruzada honesta: se a
    exportação de A trouxesse linha de B, o arquivo não acusaria pelo esquema, só pelo conteúdo."""
    return semear_camada(env, inquilino_b, 1_000, "zt camada do outro inquilino", prefixo="OUTRO-INQUILINO")


@pytest.fixture(scope="session")
def editor_sem_exportar(inquilino_a):
    """Usuário `editor` do inquilino A com papel personalizado que NÃO inclui `conteudo.exportar` (a interseção
    perfil × papel é o mecanismo do ADR 0002 seção 3.2, `plat.privilegios_de`). Devolve o cliente já logado."""
    s = inquilino_a.admin
    r = s.post("/api/papeis", json={"nome": f"zt-sem-exportar-{secrets.token_hex(3)}",
                                    "descricao": "papel de teste sem conteudo.exportar",
                                    "privilegios": ["conteudo.ver_inquilino", "conteudo.criar", "jobs.ver",
                                                    "jobs.executar"]})
    assert r.status_code == 201, r.text
    papel_id = r.json()["id"]
    usuarios = Usuarios(s)
    cliente, _usuario, _senha = usuarios.sessao("editor", papel_id=papel_id)
    privilegios = set(cliente.get("/api/eu").json()["privilegios"])
    assert "conteudo.exportar" not in privilegios, privilegios
    yield cliente
    usuarios.limpar()
    s.delete(f"/api/papeis/{papel_id}")


def esperar_exportacao(cliente, exportacao_id: str, timeout: float = 180) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = cliente.get(f"/api/exportacoes/{exportacao_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("pronta", "falhou", "cancelada", "expirada"):
            return ultimo
        time.sleep(0.25)
    pytest.fail(f"exportação {exportacao_id} não terminou em {timeout} s: {ultimo}")


def exportar(cliente, corpo: dict, timeout: float = 180) -> dict:
    r = cliente.post("/api/exportacoes", json=corpo)
    assert r.status_code == 202, r.text
    final = esperar_exportacao(cliente, r.json()["exportacao_id"], timeout)
    final["job_id"] = r.json()["job_id"]
    return final
