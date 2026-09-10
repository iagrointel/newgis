"""Reunião das linhas de log de um MESMO pedido, em ordem de relógio (item L7-06-c).

O identificador é o `X-Req-Id` cunhado pelo nginx (`$request_id`) e propagado para a API
(`app/auth/middleware.py`). Cada serviço carrega esse identificador de um jeito diferente, e é honesto
dizer qual é qual, porque só dois deles o registram por vontade própria:

| serviço            | como a linha carrega o pedido                                                  |
|--------------------|--------------------------------------------------------------------------------|
| nginx              | `$request_id` no `log_format plat_json` (deploy/nginx.conf) — nativo            |
| API (plat-api)     | campo `req_id` da linha JSON de `app/log.py` — nativo                           |
| worker (plat-worker)| campo `req_id` herdado do job que a API enfileirou — nativo                    |
| Postgres           | `application_name` = `plat:<12 hex do req_id>`, que entra no `log_line_prefix`  |
|                    | pelo `%a` (`app/db.py`) — nativo na conexão, não na linha do SQL                |
| Martin / TiTiler   | **não** registram identificador de pedido próprio; a ligação é a linha do nginx |
|                    | que os PROXIA (mesmo `$request_id`, `upstream_addr` deles)                       |

Por isso a busca é por SUBSTRING do identificador na linha bruta, com dois anzóis: o identificador
inteiro e o prefixo de 12 caracteres que vai no `application_name`. Não há junção por horário nem por
adivinhação: linha sem o identificador não entra.

Fontes: por padrão as unidades do systemd desta máquina; `PLAT_LOG_FONTES` troca a lista, no formato
`nome=journal:unidade,nome=arquivo:/caminho,nome=tag:etiqueta` (a leitura por arquivo serve tanto para
`/var/log/nginx/*.log` quanto para uma banca de teste que capture a saída dos processos).
"""

import datetime
import json
import os
import shutil
import subprocess
from dataclasses import dataclass

FONTES_PADRAO = (
    ("nginx", "tag", "plat_nginx"),
    ("api", "journal", "plat-api.service"),
    ("worker", "journal", "plat-worker.service"),
    ("martin", "journal", "plat-martin.service"),
    ("titiler", "journal", "plat-titiler.service"),
    ("postgres", "journal", "postgresql@16-main.service"),
)
CAMPOS_TEMPO = ("ts", "em", "time_iso8601", "time", "hora")


@dataclass(frozen=True)
class Fonte:
    nome: str
    especie: str  # journal | tag | arquivo
    alvo: str


@dataclass(frozen=True)
class Linha:
    servico: str
    em: datetime.datetime | None
    texto: str

    def como_dicionario(self) -> dict:
        return {"servico": self.servico, "em": self.em.isoformat() if self.em else None, "texto": self.texto}


def _erro_fonte(especificacao: str) -> ValueError:
    return ValueError(
        f"fonte inválida: {especificacao!r}; use nome=journal:unidade, nome=tag:etiqueta ou nome=arquivo:/caminho"
    )


def fontes(especificacao: str | None = None) -> list[Fonte]:
    """`especificacao` vem do argumento `--fonte` ou de `PLAT_LOG_FONTES`; vazio = as unidades padrão."""
    bruto = especificacao if especificacao is not None else os.environ.get("PLAT_LOG_FONTES", "")
    if not bruto.strip():
        return [Fonte(n, e, a) for n, e, a in FONTES_PADRAO]
    saida = []
    for pedaco in bruto.split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        nome, _, resto = pedaco.partition("=")
        especie, _, alvo = resto.partition(":")
        if not nome or especie not in ("journal", "tag", "arquivo") or not alvo:
            raise _erro_fonte(pedaco)
        saida.append(Fonte(nome, especie, alvo))
    if not saida:
        raise _erro_fonte(bruto)
    return saida


def anzois(req_id: str) -> tuple[str, ...]:
    """O identificador inteiro e o prefixo que o Postgres recebe em `application_name` (12 hex)."""
    req_id = req_id.strip()
    if len(req_id) < 8 or not all(c in "0123456789abcdefABCDEF" for c in req_id):
        raise ValueError(f"req_id inválido: {req_id!r}; esperado hexadecimal de 8 caracteres ou mais")
    curto = req_id[:12]
    return (req_id,) if curto == req_id else (req_id, curto)


def _tempo_do_json(objeto: dict) -> datetime.datetime | None:
    for campo in CAMPOS_TEMPO:
        valor = objeto.get(campo)
        if isinstance(valor, str):
            try:
                return datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def _tempo_da_linha(texto: str) -> datetime.datetime | None:
    texto = texto.strip()
    if texto.startswith("{"):
        try:
            objeto = json.loads(texto)
        except ValueError:
            return None
        if isinstance(objeto, dict):
            return _tempo_do_json(objeto)
        return None
    # linha do Postgres: "2026-09-07 18:03:11.123 UTC [123] db=..,app=plat:abc,.."
    cabeca = texto[:23]
    try:
        return datetime.datetime.fromisoformat(cabeca).replace(tzinfo=datetime.UTC)
    except ValueError:
        return None


def _do_journal(fonte: Fonte, desde: str, ate: str | None) -> list[tuple[datetime.datetime | None, str]]:
    if not shutil.which("journalctl"):
        return []
    seletor = ["-t", fonte.alvo] if fonte.especie == "tag" else ["-u", fonte.alvo]
    comando = ["journalctl", *seletor, "--since", desde, "--output", "json", "--no-pager"]
    if ate:
        comando += ["--until", ate]
    try:
        bruto = subprocess.run(comando, capture_output=True, text=True, timeout=120, check=False).stdout
    except subprocess.TimeoutExpired:
        return []
    saida = []
    for linha in bruto.splitlines():
        try:
            registro = json.loads(linha)
        except ValueError:
            continue
        mensagem = registro.get("MESSAGE")
        if not isinstance(mensagem, str):
            continue
        micros = registro.get("__REALTIME_TIMESTAMP")
        em = datetime.datetime.fromtimestamp(int(micros) / 1_000_000, datetime.UTC) if micros else None
        saida.append((em, mensagem))
    return saida


def _do_arquivo(fonte: Fonte) -> list[tuple[datetime.datetime | None, str]]:
    try:
        with open(fonte.alvo, encoding="utf-8", errors="replace") as f:
            return [(_tempo_da_linha(linha), linha.rstrip("\n")) for linha in f if linha.strip()]
    except FileNotFoundError:
        return []


def reunir(req_id: str, *, desde: str = "-24h", ate: str | None = None,
           especificacao: str | None = None) -> list[Linha]:
    """Todas as linhas dos serviços configurados que citam o pedido, em ordem de relógio. Linha sem
    horário legível fica no fim do bloco do próprio serviço, nunca é descartada nem inventada."""
    alvos = anzois(req_id)
    achadas: list[Linha] = []
    for fonte in fontes(especificacao):
        cruas = _do_arquivo(fonte) if fonte.especie == "arquivo" else _do_journal(fonte, desde, ate)
        for em, texto in cruas:
            if any(a in texto for a in alvos):
                achadas.append(Linha(fonte.nome, em, texto))
    achadas.sort(key=lambda linha: (linha.em is None, linha.em or datetime.datetime.min.replace(tzinfo=datetime.UTC)))
    return achadas
