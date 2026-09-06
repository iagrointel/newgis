"""Configuração do plat: lê o .env da raiz, valida as chaves obrigatórias e expõe `settings`
(dataclass congelada). Falha na partida nomeando a chave ausente ou inválida (ADR 0001 seção 8).
`settings` é carregado na primeira leitura (módulo __getattr__), para que testes de unidade
consigam importar este módulo sem .env."""

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

from app import limites

ROOT = Path(__file__).resolve().parents[1]
AMBIENTES = ("producao", "dev")
NIVEIS = ("DEBUG", "INFO", "WARNING", "ERROR")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
POOL_MIN_PADRAO = 1
POOL_MAX_PADRAO = 8


class ErroConfiguracao(RuntimeError):
    """Chave de configuração ausente ou inválida; a mensagem nomeia a chave."""


@dataclass(frozen=True)
class Settings:
    PLAT_DSN: str
    PLAT_SECRET: str
    PLAT_AMBIENTE: str
    PLAT_URL_PUBLICA: str
    PLAT_GIT_SHA: str | None
    PLAT_MARTIN_URL: str | None
    PLAT_TITILER_URL: str | None
    PLAT_GARAGE_URL: str | None
    # arquivos/objetos (L0-11; ADR 0006): garage vira obrigatório a partir deste item (saude.py); admin api
    # (:3903) só é usada pelo backend para criar bucket/chave/cota — nunca chega ao navegador
    PLAT_GARAGE_ADMIN_URL: str | None
    PLAT_GARAGE_ADMIN_TOKEN: str | None
    PLAT_GARAGE_REGIAO: str
    PLAT_GARAGE_BUCKET_PREFIXO: str
    PLAT_LOG_NIVEL: str
    # fila de jobs e worker plat-worker (ADR 0003 seção 11); acrescentados ao fim pela trilha B
    PLAT_WORKER_URL: str | None
    PLAT_WORKER_NOME: str | None
    PLAT_WORKER_PROCESSOS: int
    PLAT_WORKER_MEMORIA_MB: int
    PLAT_JOBS_DIR: str | None
    PLAT_JOB_MAX_REINICIOS: int
    PLAT_GPU_SSH: str | None
    PLAT_GPU_DIR: str | None
    PLAT_RELOGIO_TESTE: str | None
    PLAT_DSN_WORKER: str | None  # role plat_worker (006): só ela muda estado de job
    # rede de rota (L2-11-c): OSRM isolado plat-osrm-guarulhos (:5010), só recorte de teste ≤ 50 MB;
    # nunca aponta para os OSRM de outras frentes da casa (5000-5003)
    PLAT_OSRM_URL: str
    PLAT_ROTA_MATRIZ_MAX: int
    PLAT_ROTA_ISOCRONA_MAX_PONTOS: int
    # item L7-31 (docs/HOMOLOGACAO.md): homologação reusa o MESMO banco iagro_sat, nunca um banco novo (disco a
    # 98%) — schema e canal de notificação viram configuráveis para que o mesmo código sirva os dois ambientes
    # sem colisão. Produção nunca declara estas 4 chaves no .env: os padrões abaixo reproduzem bit a bit o que
    # já rodava (app/schema_ambiente.py só reescreve a consulta quando o schema difere do padrão `plat`).
    PLAT_SCHEMA: str
    PLAT_SCHEMA_TRABALHO: str
    PLAT_CANAL_JOB: str
    PLAT_CANAL_WORKER: str
    # SMTP de instalação (item L0-07-d-smtp-convites; ADR 0013): padrão de TODOS os inquilinos que não têm
    # override próprio em tenant.config.smtp (app/correio/config.py::smtp_efetivo). Nenhuma chave é obrigatória:
    # sem PLAT_SMTP_HOST a instalação simplesmente não tem SMTP — o inquilino que precisar configura o dele, e
    # quem não configurar nada cai no caminho manual (senha temporária mostrada ao admin, já existente).
    PLAT_SMTP_HOST: str | None
    PLAT_SMTP_PORTA: int
    PLAT_SMTP_TLS: bool
    PLAT_SMTP_USUARIO: str | None
    PLAT_SMTP_SENHA: str | None
    PLAT_SMTP_REMETENTE: str | None
    PLAT_SMTP_ROTULO: str | None
    # tamanho do pool psycopg2 (app/db.py). O padrão 1/8 reproduz bit a bit o que rodava antes desta chave
    # existir: produção não muda em nada. A chave existe para as TRILHAS do laço, que rodam dezenas de
    # instâncias da app contra o MESMO Postgres compartilhado da casa (max_connections=100, 3 reservadas
    # ao superusuário). Vinte trilhas a 8 conexões pedem 160 — mais do que o servidor inteiro tem. Cada
    # .env de trilha grava PLAT_POOL_MAX=2 (ver laco/trilha_ambiente.sh).
    PLAT_POOL_MIN: int
    PLAT_POOL_MAX: int
    # backup lógico (item L0-06-a; ADR 20260906T2124): diretório dos .dump (padrão var/backups da árvore);
    # destino externo S3 opcional — as 4 chaves juntas ou nenhuma (destino.py recusa configuração pela metade)
    PLAT_BACKUP_DIR: str | None
    PLAT_BACKUP_EXTERNO_URL: str | None
    PLAT_BACKUP_EXTERNO_BUCKET: str | None
    PLAT_BACKUP_EXTERNO_CHAVE: str | None
    PLAT_BACKUP_EXTERNO_SEGREDO: str | None
    PLAT_BACKUP_EXTERNO_REGIAO: str | None

    @property
    def producao(self) -> bool:
        return self.PLAT_AMBIENTE == "producao"

    def servicos(self) -> dict[str, str | None]:
        return {"martin": self.PLAT_MARTIN_URL, "titiler": self.PLAT_TITILER_URL, "garage": self.PLAT_GARAGE_URL,
                "worker": self.PLAT_WORKER_URL}


def _obrigatoria(valores: Mapping[str, str | None], chave: str) -> str:
    v = (valores.get(chave) or "").strip()
    if not v:
        raise ErroConfiguracao(f"chave obrigatória ausente: {chave}")
    return v


def _opcional(valores: Mapping[str, str | None], chave: str) -> str | None:
    v = (valores.get(chave) or "").strip()
    return v or None


def _inteiro(valores: Mapping[str, str | None], chave: str, padrao: int, minimo: int) -> int:
    v = _opcional(valores, chave)
    if v is None:
        return padrao
    try:
        n = int(v)
    except ValueError as e:
        raise ErroConfiguracao(f"{chave} inválida: {v!r}; exige inteiro >= {minimo}") from e
    if n < minimo:
        raise ErroConfiguracao(f"{chave} inválida: {n}; exige inteiro >= {minimo}")
    return n


def _booleano(valores: Mapping[str, str | None], chave: str, padrao: bool) -> bool:
    v = _opcional(valores, chave)
    if v is None:
        return padrao
    baixo = v.strip().lower()
    if baixo in ("1", "true", "verdadeiro", "sim"):
        return True
    if baixo in ("0", "false", "falso", "nao", "não"):
        return False
    raise ErroConfiguracao(f"{chave} inválida: {v!r}; exige verdadeiro/falso (1/0, true/false)")


def _dsn_worker(valores: Mapping[str, str | None], papel_worker: str) -> str | None:
    v = _opcional(valores, "PLAT_DSN_WORKER")
    prefixo = f"postgresql://{papel_worker}:"
    if v is not None and not v.startswith(prefixo):
        raise ErroConfiguracao(f"PLAT_DSN_WORKER inválida: deve começar com {prefixo}")
    return v


_IDENTIFICADOR = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _identificador(valores: Mapping[str, str | None], chave: str, padrao: str) -> str:
    """Nome de schema/canal (item L7-31): mesma regra de identificador do Postgres, minúsculo, sem aspas —
    ele entra em SQL por f-string em app/schema_ambiente.py e nas migrações de homologação, então tem de
    ser validado aqui, na partida, e não confiado a quem monta o .env."""
    v = _opcional(valores, chave) or padrao
    if not _IDENTIFICADOR.match(v):
        raise ErroConfiguracao(f"{chave} inválido: {v!r}; exige identificador ^[a-z][a-z0-9_]{{0,62}}$")
    return v


def carregar(valores: Mapping[str, str | None]) -> Settings:
    """Monta e valida um Settings a partir de um dicionário (o .env, o ambiente ou um teste)."""
    dsn = _obrigatoria(valores, "PLAT_DSN")
    if not dsn.startswith("postgresql://"):
        raise ErroConfiguracao("PLAT_DSN inválida: deve começar com postgresql://")
    segredo = _obrigatoria(valores, "PLAT_SECRET")
    if not _HEX64.match(segredo):
        raise ErroConfiguracao("PLAT_SECRET inválido: exige 64 caracteres hexadecimais (openssl rand -hex 32)")
    ambiente = _obrigatoria(valores, "PLAT_AMBIENTE")
    if ambiente not in AMBIENTES:
        raise ErroConfiguracao(f"PLAT_AMBIENTE inválido: {ambiente!r}; admitidos {AMBIENTES}")
    url = _obrigatoria(valores, "PLAT_URL_PUBLICA").rstrip("/")
    if not url.startswith("https://"):
        raise ErroConfiguracao("PLAT_URL_PUBLICA inválida: deve começar com https://")
    nivel = (_opcional(valores, "PLAT_LOG_NIVEL") or "INFO").upper()
    if nivel not in NIVEIS:
        raise ErroConfiguracao(f"PLAT_LOG_NIVEL inválido: {nivel!r}; admitidos {NIVEIS}")
    if ambiente == "producao" and nivel == "DEBUG":
        logging.getLogger("plat.settings").warning("PLAT_LOG_NIVEL=DEBUG não vale em producao; rebaixado para INFO")
        nivel = "INFO"
    schema = _identificador(valores, "PLAT_SCHEMA", "plat")
    pool_min = _inteiro(valores, "PLAT_POOL_MIN", POOL_MIN_PADRAO, 1)
    pool_max = _inteiro(valores, "PLAT_POOL_MAX", POOL_MAX_PADRAO, 1)
    if pool_max < pool_min:
        raise ErroConfiguracao(f"PLAT_POOL_MAX inválida: {pool_max}; exige >= PLAT_POOL_MIN ({pool_min})")
    # o papel do worker segue o schema por convenção (item L7-31): plat -> plat_worker, plat_homolog ->
    # plat_homolog_worker — é a MESMA troca que db/reescrever_homolog.py faz nas migrações.
    return Settings(
        PLAT_DSN=dsn,
        PLAT_SECRET=segredo,
        PLAT_AMBIENTE=ambiente,
        PLAT_URL_PUBLICA=url,
        PLAT_GIT_SHA=_opcional(valores, "PLAT_GIT_SHA"),
        PLAT_MARTIN_URL=_opcional(valores, "PLAT_MARTIN_URL"),
        PLAT_TITILER_URL=_opcional(valores, "PLAT_TITILER_URL"),
        PLAT_GARAGE_URL=_opcional(valores, "PLAT_GARAGE_URL"),
        PLAT_GARAGE_ADMIN_URL=_opcional(valores, "PLAT_GARAGE_ADMIN_URL"),
        PLAT_GARAGE_ADMIN_TOKEN=_opcional(valores, "PLAT_GARAGE_ADMIN_TOKEN"),
        PLAT_GARAGE_REGIAO=_opcional(valores, "PLAT_GARAGE_REGIAO") or "garage",
        PLAT_GARAGE_BUCKET_PREFIXO=_opcional(valores, "PLAT_GARAGE_BUCKET_PREFIXO") or "plat-",
        PLAT_LOG_NIVEL=nivel,
        PLAT_WORKER_URL=_opcional(valores, "PLAT_WORKER_URL"),
        PLAT_WORKER_NOME=_opcional(valores, "PLAT_WORKER_NOME"),
        PLAT_WORKER_PROCESSOS=_inteiro(valores, "PLAT_WORKER_PROCESSOS", 1, 1),
        PLAT_WORKER_MEMORIA_MB=_inteiro(valores, "PLAT_WORKER_MEMORIA_MB", 1536, 128),
        PLAT_JOBS_DIR=_opcional(valores, "PLAT_JOBS_DIR"),
        PLAT_JOB_MAX_REINICIOS=_inteiro(valores, "PLAT_JOB_MAX_REINICIOS", 5, 1),
        PLAT_GPU_SSH=_opcional(valores, "PLAT_GPU_SSH"),
        PLAT_GPU_DIR=_opcional(valores, "PLAT_GPU_DIR"),
        PLAT_RELOGIO_TESTE=_opcional(valores, "PLAT_RELOGIO_TESTE"),
        PLAT_DSN_WORKER=_dsn_worker(valores, f"{schema}_worker"),
        PLAT_OSRM_URL=(_opcional(valores, "PLAT_OSRM_URL") or "http://127.0.0.1:5010").rstrip("/"),
        PLAT_ROTA_MATRIZ_MAX=_inteiro(valores, "PLAT_ROTA_MATRIZ_MAX", limites.ROTA_MATRIZ_MAX_PADRAO, 1),
        PLAT_ROTA_ISOCRONA_MAX_PONTOS=_inteiro(
            valores, "PLAT_ROTA_ISOCRONA_MAX_PONTOS", limites.ROTA_ISOCRONA_MAX_PONTOS_PADRAO, 4
        ),
        PLAT_SCHEMA=schema,
        PLAT_SCHEMA_TRABALHO=_identificador(valores, "PLAT_SCHEMA_TRABALHO", "plat_trabalho"),
        PLAT_CANAL_JOB=_identificador(valores, "PLAT_CANAL_JOB", "plat_job"),
        PLAT_CANAL_WORKER=_identificador(valores, "PLAT_CANAL_WORKER", "plat_worker"),
        PLAT_SMTP_HOST=_opcional(valores, "PLAT_SMTP_HOST"),
        PLAT_SMTP_PORTA=_inteiro(valores, "PLAT_SMTP_PORTA", 587, 1),
        PLAT_SMTP_TLS=_booleano(valores, "PLAT_SMTP_TLS", True),
        PLAT_SMTP_USUARIO=_opcional(valores, "PLAT_SMTP_USUARIO"),
        PLAT_SMTP_SENHA=_opcional(valores, "PLAT_SMTP_SENHA"),
        PLAT_SMTP_REMETENTE=_opcional(valores, "PLAT_SMTP_REMETENTE"),
        PLAT_SMTP_ROTULO=_opcional(valores, "PLAT_SMTP_ROTULO"),
        PLAT_POOL_MIN=pool_min,
        PLAT_POOL_MAX=pool_max,
        PLAT_BACKUP_DIR=_opcional(valores, "PLAT_BACKUP_DIR"),
        PLAT_BACKUP_EXTERNO_URL=_opcional(valores, "PLAT_BACKUP_EXTERNO_URL"),
        PLAT_BACKUP_EXTERNO_BUCKET=_opcional(valores, "PLAT_BACKUP_EXTERNO_BUCKET"),
        PLAT_BACKUP_EXTERNO_CHAVE=_opcional(valores, "PLAT_BACKUP_EXTERNO_CHAVE"),
        PLAT_BACKUP_EXTERNO_SEGREDO=_opcional(valores, "PLAT_BACKUP_EXTERNO_SEGREDO"),
        PLAT_BACKUP_EXTERNO_REGIAO=_opcional(valores, "PLAT_BACKUP_EXTERNO_REGIAO"),
    )


def _credenciais_systemd() -> dict[str, str]:
    """Segredos entregues por `LoadCredential=` do systemd (item L7-19; docs/SEGURANCA.md §1 tem o que
    isso isola e o que não isola, medido nesta máquina). O systemd exporta `$CREDENTIALS_DIRECTORY` só
    dentro da unidade que declarou o `LoadCredential=`; cada arquivo ali cujo nome bate com um campo de
    `Settings` vira o valor daquela chave, por cima do `.env`. Fora do systemd (dev, pytest, CLI) a
    variável não existe: a função devolve vazio e o `.env`/ambiente do processo mandam como antes —
    retrocompatível com quem já tinha tudo no `.env` (P5)."""
    diretorio = os.environ.get("CREDENTIALS_DIRECTORY")
    if not diretorio:
        return {}
    valores: dict[str, str] = {}
    for chave in Settings.__dataclass_fields__:
        caminho = Path(diretorio) / chave
        if caminho.is_file():
            valores[chave] = caminho.read_text().strip()
    return valores


def valores_do_ambiente() -> dict[str, str | None]:
    """`.env` da raiz, depois os segredos do `LoadCredential=` do systemd (L7-19), depois o ambiente do
    processo por cima (o ambiente vence, como no SIG de teste interno — é assim que a suíte injeta
    PLAT_SECRET/PLAT_DSN_WORKER sem journal nem arquivo, ver `Makefile`)."""
    valores: dict[str, str | None] = dict(dotenv_values(ROOT / ".env"))
    valores.update(_credenciais_systemd())
    for chave in Settings.__dataclass_fields__:
        if chave in os.environ:
            valores[chave] = os.environ[chave]
    return valores


@lru_cache(maxsize=1)
def obter() -> Settings:
    return carregar(valores_do_ambiente())


def __getattr__(nome: str):
    if nome == "settings":
        return obter()
    raise AttributeError(nome)
