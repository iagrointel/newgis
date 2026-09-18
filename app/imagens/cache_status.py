"""Taxa de acerto do cache de ladrilhos, por dia (item L1-02-d).

Por que isto não sai do banco nem de um contador no processo: o cache de ladrilho fica no NGINX, antes
da aplicação. Um acerto (`HIT`) é respondido pelo nginx e nunca chega ao processo Python — uma contagem
feita aqui dentro veria só os MISS e concluiria que a taxa de acerto é zero, que é o número errado com
a aparência de número certo. A única fonte honesta é `$upstream_cache_status` no log do nginx.

A leitura reusa a mesma fonte `nginx` de `plat logs --req-id` (`app/logs_consulta.py`: journal pela
etiqueta `plat_nginx`, uma linha JSON por requisição). O campo novo é `cache`; o formato que o grava
está em `deploy/nginx-log-formats.conf` como `plat_json_cache`.

⛔ Quando as linhas existem mas NENHUMA traz o campo `cache`, esta função devolve `sem_dado` e diz o
que falta ligar. Ela nunca devolve 0 % nesse caso: taxa de acerto desconhecida e taxa de acerto zero
são coisas diferentes, e confundi-las esconderia justamente o cache desligado.
"""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

# Valores de $upstream_cache_status (documentação do ngx_http_proxy_module). `REVALIDATED` conta como
# acerto: a resposta veio do cache, com uma ida ao upstream só para confirmar que continua válida.
ACERTOS = frozenset({"HIT", "STALE", "UPDATING", "REVALIDATED"})
ERROS = frozenset({"MISS", "EXPIRED", "BYPASS"})
SEM_CACHE = frozenset({"", "-", "NONE"})


def _dia(texto: str) -> str | None:
    try:
        return datetime.datetime.fromisoformat(texto.replace("Z", "+00:00")).date().isoformat()
    except (ValueError, AttributeError):
        return None


def resumir(linhas: list[str]) -> dict:
    """Conta acerto/erro/sem_cache por dia sobre linhas JSON do nginx.

    Recebe as linhas cruas para poder ser medida sem journal, sem nginx e sem rede — a contagem é a
    parte que pode errar, e ela é aritmética pura."""
    por_dia: dict[str, dict[str, int]] = defaultdict(lambda: {"acertos": 0, "erros": 0, "sem_cache": 0})
    com_campo = 0
    consideradas = 0
    for linha in linhas:
        try:
            registro = json.loads(linha)
        except (ValueError, TypeError):
            continue
        if not isinstance(registro, dict):
            continue
        consideradas += 1
        dia = _dia(registro.get("ts", ""))
        if dia is None:
            continue
        estado = str(registro.get("cache", "")).strip().upper()
        if "cache" not in registro:
            continue
        com_campo += 1
        if estado in ACERTOS:
            por_dia[dia]["acertos"] += 1
        elif estado in ERROS:
            por_dia[dia]["erros"] += 1
        elif estado in SEM_CACHE:
            por_dia[dia]["sem_cache"] += 1
        else:  # valor que o nginx ainda não tinha quando isto foi escrito: contar, nunca descartar
            por_dia[dia]["sem_cache"] += 1

    dias = []
    for dia in sorted(por_dia):
        c = por_dia[dia]
        decididas = c["acertos"] + c["erros"]
        dias.append({
            "dia": dia,
            "acertos": c["acertos"],
            "erros": c["erros"],
            "sem_cache": c["sem_cache"],
            "pedidos_com_cache": decididas,
            # a taxa é sobre o que PASSOU por zona de cache; requisição sem cache nenhum não é erro
            "taxa_de_acerto": round(c["acertos"] / decididas, 4) if decididas else None,
        })
    if consideradas and not com_campo:
        return {"estado": "sem_dado", "dias": [], "linhas_lidas": consideradas,
                "por_que": ("as linhas do nginx não trazem o campo `cache`; ligue o log_format "
                            "`plat_json_cache` (deploy/nginx-log-formats.conf) no access_log da "
                            "location dos ladrilhos. Taxa desconhecida não é taxa zero.")}
    if not consideradas:
        return {"estado": "sem_linhas", "dias": [], "linhas_lidas": 0,
                "por_que": "nenhuma linha do nginx na janela pedida"}
    return {"estado": "ok", "dias": dias, "linhas_lidas": consideradas, "linhas_com_campo": com_campo}


def por_dia(desde: str = "-7d", ate: str | None = None) -> dict:
    """Taxa de acerto do cache por dia, lida do journal do nginx."""
    from app import logs_consulta

    fonte = logs_consulta.Fonte("nginx", "tag", "plat_nginx")
    linhas = [texto for _, texto in logs_consulta._do_journal(fonte, desde, ate)]
    resumo = resumir(linhas)
    resumo["janela"] = {"desde": desde, "ate": ate}
    return resumo
