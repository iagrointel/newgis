"""Registro de tipos de job por decorador (D19; ADR 0003 seção 3.1). Um tipo é uma função Python
`f(ctx: ContextoJob, **parametros) -> dict` mais os limites que o job carrega ao ser criado (pesado, memoria_mb,
timeout_s, tentativas, executor). A validação acontece na importação: nome único no padrão `<area>.<verbo>`,
memória dentro do teto, executor 'gpu' só com PLAT_GPU_SSH e sempre pesado."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

PADRAO_NOME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
PERFIS = ("visualizador", "campo", "editor", "admin")
EXECUTORES = ("local", "gpu")
MINIMO_MB = 128
TETO_LEVE_MB = 1024


class ErroRegistro(ValueError):
    """Tipo de job mal declarado; a mensagem nomeia o campo (ou a chave de configuração) em falta."""


class Cancelado(Exception):
    """Levantada por `ContextoJob.progresso()`/`verificar()` quando o cancelamento foi pedido; a tarefa pode capturar
    para limpar e deve relançar."""


class FalhaDefinitiva(Exception):
    """Falha que não vale a pena repetir (dado de entrada inválido, hash divergente): o job vai a `falhou` sem
    retentativa."""


@dataclass(frozen=True)
class Tarefa:
    nome: str
    descricao: str
    parametros: type[BaseModel]
    funcao: Callable
    pesado: bool
    memoria_mb: int
    timeout_s: int
    tentativas: int
    chave: Callable[[dict], str | None] | None
    executor: str
    versao: int
    threads_blas: int
    perfil_minimo: str
    ferramentas: tuple[str, ...]
    somente_sistema: bool


REGISTRO: dict[str, Tarefa] = {}


def _teto_memoria() -> int:
    from app import settings as cfg  # importação tardia: o registro é importado por testes de unidade sem .env

    return cfg.obter().PLAT_WORKER_MEMORIA_MB


def _gpu_configurado() -> bool:
    from app import settings as cfg

    return bool(cfg.obter().PLAT_GPU_SSH)


def ordem_perfil(perfil: str) -> int:
    return PERFIS.index(perfil) if perfil in PERFIS else -1


def tarefa(*, nome: str, descricao: str, parametros: type[BaseModel], pesado: bool = False, memoria_mb: int = 256,
           timeout_s: int = 3600, tentativas: int = 3, chave: Callable[[dict], str | None] | None = None,
           executor: str = "local", versao: int = 1, threads_blas: int = 1, perfil_minimo: str = "editor",
           ferramentas: tuple[str, ...] = (), somente_sistema: bool = False):
    """Decorador de registro. Recusa na importação (ErroRegistro) tudo o que a seção 3.1 do ADR 0003 proíbe.

    `somente_sistema=True` (item L0-07-d-smtp-convites) marca um tipo que só o PRÓPRIO backend enfileira
    (`app/jobs/sistema.py::enfileirar`), nunca `POST /api/jobs`: sem a marca, qualquer usuário com
    `jobs.executar` poderia criar `correio.enviar` com destinatário/assunto/texto arbitrários e usar o SMTP
    do inquilino como canhão de spam/phishing — `app/jobs/servico.py::criar` recusa com 403 antes de chegar
    à fila (achado desta sessão ao desenhar o item, não do adversário — registrado aqui para não se repetir)."""
    if not PADRAO_NOME.match(nome):
        raise ErroRegistro(f"nome de tipo fora do padrão <area>.<verbo>: {nome!r}")
    if nome in REGISTRO:
        raise ErroRegistro(f"tipo de job repetido: {nome!r}")
    if not (isinstance(parametros, type) and issubclass(parametros, BaseModel)):
        raise ErroRegistro(f"{nome}: parametros deve ser um modelo pydantic")
    if executor not in EXECUTORES:
        raise ErroRegistro(f"{nome}: executor inválido {executor!r}; admitidos {EXECUTORES}")
    if perfil_minimo not in PERFIS:
        raise ErroRegistro(f"{nome}: perfil_minimo inválido {perfil_minimo!r}; admitidos {PERFIS}")
    if timeout_s < 1:
        raise ErroRegistro(f"{nome}: timeout_s deve ser >= 1")
    if tentativas < 1:
        raise ErroRegistro(f"{nome}: tentativas deve ser >= 1")
    if threads_blas < 1:
        raise ErroRegistro(f"{nome}: threads_blas deve ser >= 1")
    teto = _teto_memoria()
    if memoria_mb < MINIMO_MB or memoria_mb > teto:
        raise ErroRegistro(f"{nome}: memoria_mb={memoria_mb} fora de [{MINIMO_MB}, {teto}] "
                           "(teto PLAT_WORKER_MEMORIA_MB)")
    if not pesado and memoria_mb > TETO_LEVE_MB:
        raise ErroRegistro(f"{nome}: memoria_mb={memoria_mb} > {TETO_LEVE_MB} exige pesado=True")
    if executor == "gpu":
        if not pesado:
            raise ErroRegistro(f"{nome}: executor='gpu' exige pesado=True (a GPU é uma só)")
        if not _gpu_configurado():
            raise ErroRegistro(f"{nome}: executor='gpu' exige a chave PLAT_GPU_SSH no .env (ADR 0003 seção 8)")

    def decorar(funcao: Callable) -> Callable:
        REGISTRO[nome] = Tarefa(
            nome=nome, descricao=descricao, parametros=parametros, funcao=funcao, pesado=pesado,
            memoria_mb=memoria_mb, timeout_s=timeout_s, tentativas=tentativas, chave=chave, executor=executor,
            versao=versao, threads_blas=threads_blas, perfil_minimo=perfil_minimo, ferramentas=tuple(ferramentas),
            somente_sistema=somente_sistema,
        )
        return funcao

    return decorar


def esquema_parametros(t: Tarefa) -> dict:
    return t.parametros.model_json_schema()


def validar_parametros(t: Tarefa, dados: dict) -> dict:
    """Valida pelo modelo do tipo e devolve o dicionário normalizado (JSON). Levanta pydantic.ValidationError."""
    return t.parametros.model_validate(dados or {}).model_dump(mode="json")


def chave_de(t: Tarefa, parametros: dict) -> str | None:
    if t.chave is None:
        return None
    valor = t.chave(parametros)
    return None if valor in (None, "") else str(valor)[:200]


def descrever(t: Tarefa) -> dict:
    """Linha de `GET /api/jobs/tipos` (ADR 0003 seção 9)."""
    return {
        "nome": t.nome, "descricao": t.descricao, "pesado": t.pesado, "memoria_mb": t.memoria_mb,
        "timeout_s": t.timeout_s, "tentativas": t.tentativas, "executor": t.executor, "versao": t.versao,
        "perfil_minimo": t.perfil_minimo, "parametros_schema": esquema_parametros(t),
        "somente_sistema": t.somente_sistema,
    }
