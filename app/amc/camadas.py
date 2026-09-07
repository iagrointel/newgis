"""Proveniência das camadas de entrada de uma execução (decisão A10 do L3L6_CONCEITO).

A execução congela, para CADA camada citada pelo modelo (fator ou restrição), o que dá para provar no instante em que
ela roda: identificador, título, sha256 do conteúdo quando o registro tem, contagem de linhas e versão. O que não
existe entra como `"nao_registrado"` — nunca como zero, nunca como valor inventado (regra da casa: procedência errada é
pior que procedência nenhuma; o método do motor de LT, regra 1: "ausência de dado nunca vira medição").

Duas origens, como o esquema do modelo permite (`camada.tipo`):

- `acervo`: slug `<fonte_id>/<schema>.<tabela>` em `plat.acervo_camada` (item L6-01), que já traz `sha256`,
  `linhas_exatas`, `linhas_contadas_em` e `estado`. Camada bloqueada ou inexistente recusa a execução com 422.
  A partir do item L6-04-acervo-no-motor, também exige que o INQUILINO ASSINE a camada
  (`plat.acervo_pode_ler`, a mesma porta de `app.acervo.publicacao`): sem assinatura, 422 `sem_assinatura` —
  é isto que "revogar a assinatura impede nova execução" do portão do item significa; uma execução já
  registrada não é afetada (a proveniência congelada e os resultados antigos ficam).
- `item`: item do catálogo do inquilino (`plat.item`, RLS). Para `camada_vetorial` hospedada no schema de trabalho a
  contagem sai de `COUNT(*)` com `statement_timeout` de CONTAGEM_TIMEOUT_S; se o tempo estourar, o campo diz
  `"contagem_nao_concluida"` com o tempo, como faz o `contagem exata do acervo (`contagem2.py`) — nunca zero.
"""

import psycopg2

from app.erros import ErroAPI
from app.settings import settings

CONTAGEM_TIMEOUT_S = 25
NAO_REGISTRADO = "nao_registrado"


def referencias(definicao: dict) -> list[dict]:
    """Camadas citadas pelo modelo, na ordem do documento, sem repetir a mesma (tipo, id, atributo, banda)."""
    saida: list[dict] = []
    vistas: set[tuple] = set()
    for origem, chave_lista in (("fator", "fatores"), ("restricao", "restricoes")):
        for entrada in definicao.get(chave_lista) or []:
            if not isinstance(entrada, dict):
                continue
            camada = entrada.get("camada")
            if not isinstance(camada, dict):
                continue
            chave = (camada.get("tipo"), camada.get("id"), camada.get("atributo"), camada.get("banda"))
            if chave in vistas:
                continue
            vistas.add(chave)
            saida.append({
                "origem": origem,
                "chave": entrada.get("id"),
                "tipo": camada.get("tipo"),
                "id": camada.get("id"),
                "atributo": camada.get("atributo"),
                "banda": camada.get("banda"),
            })
    return saida


def _acervo(cur, ref: dict) -> dict:
    cur.execute(
        "SELECT acervo_camada_id, fonte_id, schema_nome, tabela, sha256, linhas_exatas, linhas_estimadas, "
        "linhas_contadas_em, estado FROM plat.acervo_camada WHERE acervo_camada_id = %s",
        (ref["id"],),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(422, "camada_inexistente", f"camada do acervo inexistente: {ref['id']!r}",
                      {"fator": ref["chave"], "camada": ref["id"], "tipo": "acervo"})
    if r["estado"] != "exposta":
        raise ErroAPI(422, "camada_bloqueada", f"a camada do acervo {ref['id']!r} está em estado {r['estado']!r} e não "
                      f"entra numa execução", {"fator": ref["chave"], "camada": ref["id"], "estado": r["estado"]})
    # item L6-04-acervo-no-motor: sem assinatura do inquilino, a execução não nasce. Mesmo porteiro que
    # app.acervo.publicacao usa para a API de mapa — nunca um segundo critério que pudesse divergir dele.
    cur.execute("SELECT plat.acervo_pode_ler(%s) AS pode", (ref["id"],))
    if not cur.fetchone()["pode"]:
        raise ErroAPI(422, "sem_assinatura",
                      f"o inquilino não assina a camada do acervo {ref['id']!r}; assine em "
                      f"POST /api/acervo/camadas/{{camada}}/assinatura antes de usá-la num modelo",
                      {"fator": ref["chave"], "camada": ref["id"]})
    return {
        "titulo": f"{r['fonte_id']} · {r['schema_nome']}.{r['tabela']}",
        "fonte_id": r["fonte_id"],
        "sha256": r["sha256"] or NAO_REGISTRADO,
        "contagem": r["linhas_exatas"] if r["linhas_exatas"] is not None else NAO_REGISTRADO,
        "contagem_origem": "acervo.linhas_exatas" if r["linhas_exatas"] is not None else NAO_REGISTRADO,
        "contagem_em": r["linhas_contadas_em"].isoformat() if r["linhas_contadas_em"] else NAO_REGISTRADO,
        "versao": NAO_REGISTRADO,
    }


def _contar(cur, schema: str, tabela: str) -> tuple:
    """(contagem, origem). Só conta tabela do schema de trabalho do inquilino; timeout vira 'contagem_nao_concluida'."""
    if schema != settings.PLAT_SCHEMA_TRABALHO:
        return NAO_REGISTRADO, NAO_REGISTRADO
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s", (schema, tabela)
    )
    if cur.fetchone() is None:
        return NAO_REGISTRADO, NAO_REGISTRADO
    # SAVEPOINT e não rollback: o timeout da contagem não pode derrubar a transação que grava a execução
    cur.execute("SAVEPOINT amc_contagem")
    try:
        cur.execute(f"SET LOCAL statement_timeout = '{CONTAGEM_TIMEOUT_S}s'")
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
        n = cur.fetchone()["n"]
    except psycopg2.Error:
        cur.execute("ROLLBACK TO SAVEPOINT amc_contagem")
        return f"contagem_nao_concluida_em_{CONTAGEM_TIMEOUT_S}s", "COUNT(*)"
    cur.execute("RELEASE SAVEPOINT amc_contagem")
    cur.execute("SET LOCAL statement_timeout = 0")
    return n, "COUNT(*)"


def _item(cur, ref: dict) -> dict:
    cur.execute(
        "SELECT id, titulo, tipo, dados, versao_atual FROM plat.item WHERE id = %s::uuid AND apagado_em IS NULL",
        (ref["id"],),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(422, "camada_inexistente", f"camada do catálogo inexistente neste inquilino: {ref['id']!r}",
                      {"fator": ref["chave"], "camada": ref["id"], "tipo": "item"})
    dados = r["dados"] or {}
    contagem, origem_contagem = NAO_REGISTRADO, NAO_REGISTRADO
    if r["tipo"] == "camada_vetorial" and dados.get("fonte") == "hospedada" and dados.get("tabela"):
        contagem, origem_contagem = _contar(cur, str(dados.get("schema")), str(dados["tabela"]))
    return {
        "titulo": r["titulo"],
        "item_tipo": r["tipo"],
        "sha256": dados.get("sha256") or NAO_REGISTRADO,
        "contagem": contagem,
        "contagem_origem": origem_contagem,
        "versao": r["versao_atual"],
    }


def resolver(cur, definicao: dict) -> list[dict]:
    """Lista gravada em `plat.amc_execucao.camadas`. Camada citada que não existe (ou está bloqueada) recusa a
    execução inteira com 422: uma execução sem entrada resolvida não é auditável e não deve nascer."""
    saida = []
    for ref in referencias(definicao):
        if ref["tipo"] == "acervo":
            ficha = _acervo(cur, ref)
        elif ref["tipo"] == "item":
            ficha = _item(cur, ref)
        else:  # o JSON Schema já fecha o enum; aqui é só a rede de segurança
            raise ErroAPI(422, "camada_invalida", f"tipo de camada desconhecido: {ref['tipo']!r}", {"camada": ref})
        saida.append({**ref, **ficha})
    return saida
