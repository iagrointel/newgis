"""Erros do SDK como Problem Details (RFC 9457).

A API não fala o formato de fio da RFC 9457 (o contrato dela é `{"erro","mensagem","detalhe","req_id"}`,
ADR 0002 seção 14, decisão D18 — decisão já tomada, este SDK não reabre): o que este módulo faz é traduzir
esse corpo, sempre presente em toda resposta de erro da API, para uma exceção Python cujos atributos seguem
o vocabulário da RFC 9457 (RFC 9457 §3): `tipo` (membro "type"), `titulo` ("title"), `status`, `detalhe`
("detail") e `instancia` ("instance") — aqui `instancia` é o `req_id` que a API já grava em todo log de
acesso, o mesmo identificador que aparece em `plat.log_acesso`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ErroPlataforma(Exception):
    """Uma resposta de erro HTTP da plataforma, na forma de Problem Details (RFC 9457).

    Atributos:
        status: código HTTP (RFC 9457 "status").
        tipo: código curto da API, ex. "sem_permissao", "escopo_insuficiente" (RFC 9457 "type";
            aqui um identificador estável, não uma URI — a API não publica um catálogo de URIs).
        titulo: mensagem em português da API (RFC 9457 "title").
        detalhe: corpo livre que a API anexa (lista de campos inválidos, escopo exigido, etc.;
            RFC 9457 "detail" — aqui estruturado, não só texto).
        instancia: `req_id` da requisição que falhou (RFC 9457 "instance"); usar para casar com
            `plat.log_acesso.req_id` ao investigar um incidente.
    """

    status: int
    tipo: str
    titulo: str
    detalhe: Any = None
    instancia: str | None = None
    corpo_bruto: dict = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover — repr trivial
        base = f"{self.status} {self.tipo}: {self.titulo}"
        if self.detalhe is not None:
            base += f" (detalhe={self.detalhe!r})"
        return base

    def to_problem_details(self) -> dict:
        """Devolve o dicionário no vocabulário RFC 9457 (para logar ou repassar)."""
        d = {"status": self.status, "type": self.tipo, "title": self.titulo}
        if self.detalhe is not None:
            d["detail"] = self.detalhe
        if self.instancia is not None:
            d["instance"] = self.instancia
        return d


def erro_de_corpo(status: int, corpo: Any) -> ErroPlataforma:
    """Constrói um `ErroPlataforma` a partir do corpo JSON de erro da API (`app.erros.corpo_erro`).
    Corpo que não bater com o contrato (proxy fora da API, 5xx sem JSON) ainda vira ErroPlataforma,
    com `tipo="erro_desconhecido"` e o corpo bruto em `detalhe` — nunca uma exceção genérica sem
    contexto, que obrigaria quem chama a inspecionar `status_code` na mão."""
    if isinstance(corpo, dict) and "erro" in corpo:
        return ErroPlataforma(
            status=status,
            tipo=str(corpo.get("erro")),
            titulo=str(corpo.get("mensagem") or ""),
            detalhe=corpo.get("detalhe"),
            instancia=corpo.get("req_id"),
            corpo_bruto=corpo,
        )
    return ErroPlataforma(
        status=status,
        tipo="erro_desconhecido",
        titulo="a API devolveu um corpo fora do contrato esperado",
        detalhe=corpo,
        corpo_bruto=corpo if isinstance(corpo, dict) else {"corpo": corpo},
    )
