"""Temas de marca (item L5-10-temas-marca): o tema do INQUILINO (marca própria: cor, fonte, raio — a
identidade visual da organização em cima da plataforma) e a lista dos 6 temas padrão.

- `GET /api/temas` — qualquer usuário autenticado (a marca do inquilino é vista por todo membro, e os
  padrões são vocabulário da casa); devolve os padrões com nome/definição/avisos de contraste e o tema
  do inquilino quando existir. É daqui que o executor `/executar`, o editor `/temas` e, depois, a página
  publicada (L5-14) carregam os tokens — o front-end NUNCA recebe tema por outro caminho.
- `PUT /api/org/tema` — grava (ou remove, com `{"tema": null}`) o tema do inquilino em
  `plat.tenant.config` -> chave `tema` (mesma coluna que o L0-07-a já usa; nunca reescreve `config`
  inteiro). Só sessão de admin (mesmo privilégio do PUT /api/org: `org.configurar`), porque trocar a
  marca do inquilino é decisão de quem administra. A definição passa pelo MESMO validador estrito de
  `app/temas.py` (formato de cor/fonte/medida/sombra) — token como `url(javascript:...)` é recusado com
  422 `tema_invalido` antes de tocar o banco; pares de texto com contraste abaixo de 4,5:1 são aceitos
  MAS voltam na resposta como `avisos` (WCAG 1.4.3; quem decide é a marca, o aviso é obrigatório).

Eventos: `org/tema_gravar` (vocabulário na migração de temas). Leitura não registra evento (mesma regra
do GET /api/org)."""

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field

from app import db, temas
from app.auth.comum import registrar_evento
from app.auth.modelos import Modelo
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["temas"])

LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
GRAVAR = {"x-auth": "S", "x-privilegio": "org.configurar"}


class TemaEntrada(Modelo):
    # obrigatório de propósito: PUT sem corpo nenhum não pode REMOVER a marca do inquilino por acidente —
    # remover é sempre uma escolha explícita, {"tema": null}
    tema: dict[str, Any] | None = Field(description="definição de tema (tokens) ou null para remover")


def _tema_do_inquilino(cur) -> dict | None:
    cur.execute("SELECT config->'tema' AS tema FROM plat.tenant WHERE id = plat.tenant_atual()")
    linha = cur.fetchone()
    tema = (linha or {}).get("tema")
    return tema if isinstance(tema, dict) and tema else None


def _padroes_json() -> dict:
    return {
        id: {"nome": t["nome"], "tema": t["tokens"], "avisos": temas.avisos_do_tema(t["tokens"])}
        for id, t in temas.TEMAS_PADRAO.items()
    }


@router.get("/temas", openapi_extra=LER)
def listar(auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        inquilino = _tema_do_inquilino(cur)
    return {
        "padroes": _padroes_json(),
        "inquilino": None if inquilino is None else {"tema": inquilino, "avisos": temas.avisos_do_tema(inquilino)},
    }


@router.put("/org/tema", openapi_extra=GRAVAR)
def gravar_tema_do_inquilino(
    corpo: TemaEntrada, request: Request, auth: Auth = autenticado("org.configurar", so_sessao=True)
):
    if corpo.tema is not None:
        definicao = temas.validar_tema(corpo.tema)
        avisos = temas.avisos_do_tema(definicao)
    else:
        definicao = None
        avisos = []
    with db.db(auth.contexto()) as cur:
        if definicao is None:
            cur.execute(
                "UPDATE plat.tenant SET config = config - 'tema' WHERE id = plat.tenant_atual() RETURNING true"
            )
        else:
            cur.execute(
                "UPDATE plat.tenant SET config = config || jsonb_build_object('tema', %s::jsonb) "
                "WHERE id = plat.tenant_atual() RETURNING true",
                (json.dumps(definicao),),
            )
        if cur.fetchone() is None:
            raise ErroAPI(404, "nao_encontrado", "inquilino inexistente")
        registrar_evento(
            cur, request, "org/tema_gravar", "tenant", auth.tenant_id,
            {"removido": definicao is None, "modos": sorted(definicao) if definicao else [],
             "avisos_contraste": len(avisos)},
        )
    return {"tema": definicao, "avisos": avisos}
