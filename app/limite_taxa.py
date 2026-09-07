"""Limite de taxa por inquilino/plano — camada 2 do item L7-03-b-rate-limit-abuso (ADR desta trilha,
docs/SEGURANCA.md §9). As outras duas camadas do item vivem fora do Python:

  camada 1 (borda, por IP)      nginx, zonas `plat_api`/`plat_tiles` (deploy/nginx.conf) — pára o volume
                                 bruto antes de gastar CPU/conexão de banco; não sabe o que é um inquilino.
  camada 2 (aqui, por inquilino) janela deslizante em Postgres (plat.limite_taxa_verificar, migração
                                 20260907T1444), chave = "tenant:<id>", teto por tenant.config.limites.
  camada 3 (fail2ban)           bane o IP que insiste em 401/429 repetidos no log do nginx (deploy/fail2ban/).

Por que Postgres, não memória de processo: `plat-api` sobe com `--workers 2` (deploy/plat-api.service) — um
contador em memória do worker A nunca veria as requisições que caíram no worker B, e um atacante distribuído
entre os dois workers teria o dobro da cota de graça. A hipótese do item deixava as duas opções em aberto
("Postgres OU em memória por worker"); Postgres foi escolhido porque o produto já paga essa latência em toda
requisição autenticada (a MESMA consulta que resolve o token/sessão), e porque o mesmo padrão já existe e está
testado em produção há um item (`plat.redefinicao_solicitar`, migração 047) — reaproveitar desenho testado
pesa mais que os ~1-2 ms extra de uma segunda ida ao banco, que MEDIDA (§9 do SEGURANCA.md) fica dentro do
ruído da consulta de autenticação que já roda na mesma requisição.

Não é limite por IP (isso é a camada 1): é por CHAVE DE INQUILINO, para que a refutação do item funcione nos
dois sentidos — 50 IPs martelando o MESMO token continuam batendo na MESMA chave (camada 2 seguraria mesmo se
a camada 1 não existisse); 1 IP com 50 tokens de 50 inquilinos diferentes não compartilha chave nenhuma na
camada 2 (cada tenant tem sua própria cota — é exatamente por isso que a camada 1, por IP, existe também)."""

import logging

from fastapi import Request

from app import db, limites
from app.erros import ErroAPI

log = logging.getLogger("plat.limite_taxa")


def limite_de(config: dict, chave: str) -> int:
    """Lê tenant.config.limites.<chave>, corta para a faixa (padrao, min, max) de LIMITE_TAXA_PADROES —
    mesmo espírito do corte de app/auth/politica.py: um inquilino nunca consegue configurar um teto ABAIXO
    do mínimo (travaria o próprio uso) nem ACIMA do máximo (a defesa vira decorativa)."""
    padrao, minimo, maximo = limites.LIMITE_TAXA_PADROES[chave]
    bruto = (config or {}).get("limites", {}).get(chave, padrao)
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        valor = padrao
    return max(minimo, min(maximo, valor))


def chave_tenant(tenant_id: int) -> str:
    return f"tenant:{tenant_id}"


def verificar(chave: str, escopo: str, maximo: int, janela_s: int = limites.LIMITE_TAXA_JANELA_S):
    """Chama plat.limite_taxa_verificar numa conexão própria (nunca dentro da transação de negócio da rota:
    o contador tem de valer mesmo que a rota dê rollback depois, senão um cliente que sempre erra o corpo do
    pedido nunca esbarraria no limite). Devolve (permitido, restante, expira_em)."""
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.limite_taxa_verificar(%s, %s, %s, %s)", (chave, escopo, janela_s, maximo))
        r = cur.fetchone()
    return r["permitido"], r["restante"], r["expira_em"]


def contagem_atual(chave: str, escopo: str, janela_s: int = limites.LIMITE_TAXA_JANELA_S) -> int:
    """Só para teste/observabilidade — não decide nada (ver docstring da função SQL homônima)."""
    with db.db() as cur:
        cur.execute("SELECT plat.limite_taxa_contagem(%s, %s, %s) AS n", (chave, escopo, janela_s))
        return cur.fetchone()["n"]


def _retry_after_s(expira_em) -> int:
    import datetime

    faltam = (expira_em - datetime.datetime.now(datetime.UTC)).total_seconds()
    return max(limites.LIMITE_TAXA_RETRY_AFTER_MIN_S, round(faltam))


def exigir(request: Request, tenant_id: int, config: dict, escopo: str, chave_config: str) -> None:
    """Levanta 429 (RFC 6585, com Retry-After) quando o inquilino estourou o teto do escopo. Chamada pelo
    ponto que já resolveu tenant_id (app/auth/sessao.py::resolver) — nunca duas vezes por requisição: se a
    rota já tem `request.state.limite_taxa_ok` marcado para este escopo, não bate no banco de novo (uma
    requisição só resolve autenticação uma vez; isto é defensivo para quem chamar `resolver()` mais de uma
    vez no mesmo request, o que já acontece por design — `resolver` tem cache em `request.state.auth`)."""
    marcador = f"_limite_taxa_{escopo}"
    if getattr(request.state, marcador, False):
        return
    maximo = limite_de(config, chave_config)
    permitido, restante, expira_em = verificar(chave_tenant(tenant_id), escopo, maximo)
    setattr(request.state, marcador, True)
    if not permitido:
        retry = _retry_after_s(expira_em)
        log.warning("limite_taxa: recusado tenant_id=%s escopo=%s maximo=%s", tenant_id, escopo, maximo)
        raise ErroAPI(
            429,
            "limite_de_taxa",
            f"limite de {maximo} pedidos/{limites.LIMITE_TAXA_JANELA_S}s excedido para este inquilino; "
            f"aguarde {retry}s",
            {"escopo": escopo, "maximo": maximo, "janela_s": limites.LIMITE_TAXA_JANELA_S},
            headers={"Retry-After": str(retry)},
        )
