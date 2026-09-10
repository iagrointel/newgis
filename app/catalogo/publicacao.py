"""Publicação de documento de construtor em URL pública (item L5-14-publicacao-links-embed; ADR
0018-publicacao-links-embed; depende de L5-05-documento-versoes e L1-02-tiles-token).

Publicar = apontar `plat.item.versao_publicada` para a versão escolhida e abrir uma URL fixa
`/p/<inquilino>/<slug>` que só serve ESSA versão (rascunho, ou uma versão publicada mais nova depois
sobrescrita, nunca aparece lá até novo publish). A leitura pública passa por `plat.publicacao_resolver`
(SECURITY DEFINER, mesmo desenho de `plat.link_resolver`), que também grava a visualização do dia.

O acesso ao aplicativo publicado é: **público** (quando `item.acesso = 'publico'` e o inquilino permite,
igual ao D24 de `rotas_compartilhamento.py`) ou **por link com token** (reaproveita literalmente
`plat.compartilhamento_link`/`resolver_link` — o mesmo mecanismo de convite anônimo que qualquer outro
item já tem, nenhum mecanismo novo). O acesso a inquilino/grupo autenticado já existe pela navegação normal
do item dentro do produto; `/p/` é a vitrine ANÔNIMA e não duplica sessão.

Os DADOS que o aplicativo publicado lê (tiles, feições) passam por um token de serviço PRÓPRIO da
publicação (mesmo `plat.token_servico` do L0-02, mesmos escopos `tiles:ler:<uuid>`/`camada:ler:<uuid>` do
L1-02): o escopo é calculado automaticamente a partir do grafo de dependências do documento
(`plat.item_relacao`, por `app/catalogo/relacoes.py`) e a `restricao.referer` do token é a lista de
domínios permitidos para incorporação — assim um token roubado do HTML de um iframe só funciona a partir
de uma origem já cadastrada (a mesma checagem de Origin/Referer que qualquer token de serviço já sofre em
`app/auth/sessao.py::_checar_restricao`).

O valor do token fica gravado em `item_publicacao.token_valor` (plaintext, não só o hash): ele é uma
"chave publicável" — qualquer visitante da página pública o vê no HTML/JS servido por definição (é assim
que o navegador do visitante chama a API), então escondê-lo do banco não protegeria nada; a única coisa
que protege é o escopo (só as camadas citadas) e a restrição de domínio, ambas na linha de
`plat.token_servico` de sempre.
"""

from __future__ import annotations

import datetime
import html
import json
import re

from fastapi import Request

from app import limites
from app.auth import escopos as esc
from app.auth.rotas_tokens import _inserir as _inserir_token
from app.auth.rotas_tokens import _validar_restricao
from app.auth.sessao import Auth, iso
from app.catalogo import narrativa, tipos
from app.catalogo.comum import contexto_anonimo, exigir_edicao, registrar_evento
from app.catalogo.relacoes import criado_a_partir_de
from app.erros import ErroAPI
from app.settings import settings

_MIN, _MAX = limites.PUBLICACAO_SLUG_MIN - 2, limites.PUBLICACAO_SLUG_MAX - 2
SLUG = re.compile(rf"^[a-z0-9][a-z0-9-]{{{_MIN},{_MAX}}}[a-z0-9]$")
FAMILIAS_PUBLICAVEIS = {"app", "painel", "narrativa"}


def _slug_ok(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG.match(slug):
        raise ErroAPI(
            422,
            "slug_invalido",
            f"slug precisa ter {limites.PUBLICACAO_SLUG_MIN}-{limites.PUBLICACAO_SLUG_MAX} caracteres "
            "(a-z 0-9 e hífen, sem começar/terminar em hífen)",
            {"campo": "slug"},
        )
    return slug


def _dominios_ok(dominios: list[str] | None) -> list[str]:
    saida: list[str] = []
    for d in dominios or []:
        d = (d or "").strip().lower()
        if not d:
            continue
        m = re.match(r"^https?://[a-z0-9.-]+(?::\d{1,5})?$", d)
        if not m:
            raise ErroAPI(
                422,
                "dominio_invalido",
                f"domínio precisa ser uma origem (esquema://host[:porta]): {d}",
                {"campo": "dominios_permitidos"},
            )
        if d not in saida:
            saida.append(d)
    if len(saida) > limites.PUBLICACAO_DOMINIOS_MAX:
        raise ErroAPI(422, "dominios_demais", f"no máximo {limites.PUBLICACAO_DOMINIOS_MAX} domínios")
    return saida


def camadas_citadas(cur, item_id: str, profundidade: int = limites.PUBLICACAO_CAMADAS_PROFUNDIDADE) -> list[str]:
    """Fecho de itens da família `camada` alcançáveis a partir de `item_id` pelo grafo de dependências
    declaradas (`plat.item_relacao`; app -> mapa -> camada é o caminho comum, mas qualquer profundidade até
    o teto conta). Item oculto (que o publicador não lê) não entra: não dá para escopar um token para o que
    nem o próprio publicador vê."""
    vistos = {item_id}
    fila = [item_id]
    camadas: list[str] = []
    for _ in range(profundidade):
        proxima = []
        for iid in fila:
            for d in criado_a_partir_de(cur, iid):
                did = d["id"]
                if did in vistos or d.get("oculto"):
                    continue
                vistos.add(did)
                try:
                    familia = tipos.familia_de(d["tipo"])
                except ErroAPI:
                    familia = None
                if familia == "camada":
                    camadas.append(did)
                else:
                    proxima.append(did)
        fila = proxima
        if not fila:
            break
    return sorted(set(camadas))


def _publicacao_json(r: dict, camadas: list[str] | None = None) -> dict:
    return {
        "item_id": str(r["item_id"]),
        "slug": r["slug"],
        "url": f"{settings.PLAT_URL_PUBLICA}/p/{r['tenant_slug']}/{r['slug']}",
        "dominios_permitidos": list(r["dominios_permitidos"] or []),
        "token_id": r["token_id"],
        "publicado_em": iso(r["publicado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
        "camadas_citadas": camadas if camadas is not None else [],
    }


def estado(cur, item_id: str) -> dict | None:
    cur.execute(
        "SELECT p.*, t.slug AS tenant_slug FROM plat.item_publicacao p "
        "JOIN plat.tenant t ON t.id = p.tenant_id WHERE p.item_id = %s::uuid",
        (item_id,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return _publicacao_json(r, camadas_citadas(cur, item_id))


def publicar(
    cur, request: Request, auth: Auth, item_id: str, slug: str, dominios: list[str] | None, versao: int | None
) -> dict:
    r = exigir_edicao(cur, item_id)
    if tipos.familia_de(r["tipo"]) not in FAMILIAS_PUBLICAVEIS:
        raise ErroAPI(422, "tipo_nao_publicavel", "só documentos de construtor (app/painel/narrativa) publicam em /p/")
    slug = _slug_ok(slug)
    dominios = _dominios_ok(dominios)
    alvo = versao if versao is not None else r["versao_atual"]
    cur.execute("SELECT corpo FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (item_id, alvo))
    linha_versao = cur.fetchone()
    if linha_versao is None:
        raise ErroAPI(404, "versao_inexistente", "versão inexistente")
    if tipos.familia_de(r["tipo"]) == "narrativa":
        # L5-04-a: imagem sem texto alternativo (e endereço inseguro, tipo desconhecido) não publica — a versão
        # é gravada mesmo assim (rascunho), só a PUBLICAÇÃO é recusada, com a lista de blocos e o motivo
        retrato = linha_versao["corpo"] or {}
        problemas = narrativa.problemas_para_publicar(retrato.get("dados") if isinstance(retrato, dict) else None)
        if problemas:
            raise ErroAPI(
                422, "narrativa_nao_publicavel",
                "a narrativa não pode ser publicada: " + "; ".join(p["erro"] for p in problemas[:5])
                + (f" (+{len(problemas) - 5})" if len(problemas) > 5 else ""),
                problemas,
            )
    cur.execute(
        "SELECT item_id FROM plat.item_publicacao WHERE tenant_id = %s AND slug = %s", (auth.tenant_id, slug)
    )
    outro = cur.fetchone()
    if outro is not None and str(outro["item_id"]) != item_id:
        raise ErroAPI(409, "slug_em_uso", "já existe um aplicativo publicado com este slug")

    camadas = camadas_citadas(cur, item_id)
    escopos = sorted({e for cid in camadas for e in (f"camada:ler:{cid}", f"tiles:ler:{cid}")})
    sem_item = esc.uuids_inexistentes(auth, escopos)
    if sem_item:
        # a camada foi apagada/ficou ilegível entre o cálculo e a criação do token: publica sem ela
        escopos = [e for e in escopos if e not in sem_item]
    restricao = _validar_restricao({"referer": dominios} if dominios else None)

    cur.execute("SELECT token_id FROM plat.item_publicacao WHERE item_id = %s::uuid", (item_id,))
    anterior = cur.fetchone()
    if anterior and anterior["token_id"]:
        cur.execute("UPDATE plat.token_servico SET revogado_em = now() WHERE id = %s", (anterior["token_id"],))

    novo_token, valor_token = _inserir_token(
        cur, auth, f"publicacao:{slug}", escopos, restricao, auth.politica.token_max_dias
    )

    cur.execute("UPDATE plat.item SET versao_publicada = %s WHERE id = %s::uuid", (alvo, item_id))
    cur.execute(
        """
        INSERT INTO plat.item_publicacao(item_id, tenant_id, slug, dominios_permitidos, token_id, token_valor,
                                          publicado_por, publicado_em, atualizado_em)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (item_id) DO UPDATE SET
            slug = EXCLUDED.slug, dominios_permitidos = EXCLUDED.dominios_permitidos,
            token_id = EXCLUDED.token_id, token_valor = EXCLUDED.token_valor,
            publicado_por = EXCLUDED.publicado_por, atualizado_em = now()
        """,
        (item_id, auth.tenant_id, slug, dominios, novo_token["id"], valor_token, auth.usuario_id),
    )
    registrar_evento(
        cur,
        request,
        "publicacao/publicar",
        "item",
        item_id,
        {"slug": slug, "versao": alvo, "dominios_permitidos": dominios, "camadas_citadas": camadas},
    )
    return estado(cur, item_id)


def despublicar(cur, request: Request, item_id: str) -> None:
    exigir_edicao(cur, item_id)
    cur.execute("SELECT token_id FROM plat.item_publicacao WHERE item_id = %s::uuid", (item_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "publicacao_inexistente", "este item não está publicado")
    if r["token_id"]:
        cur.execute("UPDATE plat.token_servico SET revogado_em = now() WHERE id = %s", (r["token_id"],))
    cur.execute("DELETE FROM plat.item_publicacao WHERE item_id = %s::uuid", (item_id,))
    registrar_evento(cur, request, "publicacao/despublicar", "item", item_id, {})


def visualizacoes(cur, item_id: str, dias: int) -> list[dict]:
    exigir_edicao(cur, item_id)  # sem isto, item inexistente ou sem permissão devolve [] em silêncio
    dias = max(1, min(dias, limites.PUBLICACAO_VISUALIZACOES_DIAS_MAX))
    cur.execute("SELECT * FROM plat.publicacao_visualizacoes(%s::uuid, %s)", (item_id, dias))
    return [{"dia": r["dia"].isoformat(), "visualizacoes": r["visualizacoes"]} for r in cur.fetchall()]


# ---------------------------------------------------------------- leitura pública (sem sessão)
def dominios_de(cur, tenant_slug: str, slug: str) -> list[str] | None:
    """Só os domínios permitidos, sem contar visualização (a casca HTML chama isto para montar o cabeçalho
    `frame-ancestors` ANTES do front pedir o documento; None = publicação inexistente)."""
    cur.execute("SELECT * FROM plat.publicacao_dominios(%s, %s)", (tenant_slug, slug))
    r = cur.fetchone()
    return list(r["dominios_permitidos"] or []) if r else None


def resolver(cur, tenant_slug: str, slug: str) -> dict:
    cur.execute("SELECT * FROM plat.publicacao_resolver(%s, %s)", (tenant_slug, slug))
    r = cur.fetchone()
    if r["motivo"] != "ok":
        raise ErroAPI(404, "publicacao_inexistente", "aplicativo publicado inexistente")
    return r


def _corpo_publicado(cur, item_id: str, versao: int) -> dict:
    cur.execute("SELECT corpo FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (item_id, versao))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "publicacao_inexistente", "versão publicada inexistente")
    return r["corpo"]


def documento_publico(cur, tenant_slug: str, slug: str, request: Request, link: str | None) -> dict:
    """JSON servido por `GET /api/p/<inquilino>/<slug>`: exige acesso público OU link válido (reaproveita
    `resolver_link` de `rotas_compartilhamento.py` — importado tardio para não criar ciclo de módulo)."""
    from app.catalogo.rotas_compartilhamento import resolver_link  # import tardio: evita ciclo de módulo

    r = resolver(cur, tenant_slug, slug)
    aberto = False
    if r["acesso"] == "publico":
        cur.execute("SELECT 1 FROM plat.tenant_publico_itens(%s::uuid) t", (r["item_id"],))
        if cur.fetchone() is not None:
            # sem isto a leitura seguinte de `item_versao` bate na RLS: `tenant_atual()` fica NULL sem
            # contexto nenhum, e a política exige `tenant_id = tenant_atual()` além de `pode_ler` — item
            # público sem contexto aberto não lê NADA, nem o que é público (mesmo bug que `_contexto_publico`
            # de `rotas_compartilhamento.py` evita chamando `contexto_anonimo` antes de qualquer SELECT).
            contexto_anonimo(cur, r["tenant_id"], [str(r["item_id"])])
            aberto = True
    if not aberto and link:
        # a resolução do link (`/api/compartilhado/`) devolve 404/410 pelo seu próprio contrato; aqui a
        # cláusula do portão pede 401/403 ("nega após revogação") — traduz para o vocabulário desta rota,
        # sem mudar `resolver_link` (usado por outra rota com outro contrato já testado).
        try:
            info = resolver_link(cur, link, request)
        except ErroAPI as e:
            raise ErroAPI(403, "link_invalido", "link inexistente, expirado ou revogado") from e
        if info["item_id"] != str(r["item_id"]):
            raise ErroAPI(403, "link_invalido", "link não corresponde a este aplicativo")
        aberto = True
    if not aberto:
        raise ErroAPI(401, "sem_acesso", "este aplicativo exige um link de acesso (?link=<token>)")
    retrato = _corpo_publicado(cur, r["item_id"], r["versao"])  # retrato congelado da versão publicada
    cur.execute("SELECT tipo FROM plat.item WHERE id = %s::uuid", (r["item_id"],))
    tipo_item = cur.fetchone()["tipo"]  # o TIPO não é editável em CAMPOS_VERSAO; vem da linha viva
    return {
        "item_id": str(r["item_id"]),
        "titulo": retrato.get("titulo"),
        "tipo": tipo_item,
        "resumo": retrato.get("resumo"),
        "versao_publicada": r["versao"],
        "corpo": retrato.get("dados") or {},
        "dominios_permitidos": list(r["dominios_permitidos"] or []),
        "token": r["token_valor"],
    }


# ---------------------------------------------------------------- exportação estática (clausula 4 do portão)
def _escapar_json_para_script(dados: dict) -> str:
    """JSON dentro de <script type="application/json">: só precisa escapar `</script>` e afins; nunca HTML-escape
    (corromperia aspas do JSON) — só a sequência perigosa de fechamento de tag."""
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, indent=None).replace("</", "<\\/")


def exportacao_estatica(cur, item_id: str) -> bytes:
    """HTML autocontido (sem CSS/JS externo, sem chamada de rede): abre por `file://` e mostra o mesmo
    conteúdo da versão publicada — título, grafo de nós/ligações e metadado das camadas citadas (nome, tipo,
    acesso). Não inclui geometria/feição (a exportação é do DOCUMENTO, não um espelho do banco de dado)."""
    r = exigir_edicao(cur, item_id)
    if r["versao_publicada"] is None:
        raise ErroAPI(422, "nao_publicado", "publique o item antes de exportar")
    retrato = _corpo_publicado(cur, item_id, r["versao_publicada"])
    dados_doc = retrato.get("dados") or {}
    camadas = camadas_citadas(cur, item_id)
    if camadas:
        cur.execute(
            "SELECT id, titulo, tipo, acesso FROM plat.item WHERE id = ANY (%s::uuid[]) ORDER BY titulo", (camadas,)
        )
        meta_camadas = [{"id": str(x["id"]), "titulo": x["titulo"], "tipo": x["tipo"], "acesso": x["acesso"]}
                        for x in cur.fetchall()]
    else:
        meta_camadas = []
    pacote = {
        "item_id": item_id,
        "titulo": retrato.get("titulo"),
        "tipo": r["tipo"],
        "versao_publicada": r["versao_publicada"],
        "corpo": dados_doc,
        "camadas_citadas": meta_camadas,
        "exportado_em": iso(datetime.datetime.now(datetime.UTC)),
    }
    titulo = html.escape(str(retrato.get("titulo") or ""))
    nos = dados_doc.get("corpo", {}).get("nos", []) if isinstance(dados_doc, dict) else []
    linhas_nos = "".join(f"<li>{html.escape(str(n.get('tipo', '?')))} · <code>{html.escape(str(n.get('id', '')))}"
                         f"</code></li>" for n in nos if isinstance(n, dict))
    linhas_camadas = "".join(
        f"<li>{html.escape(c['titulo'])} · {html.escape(c['tipo'])} · {html.escape(c['acesso'])}</li>"
        for c in meta_camadas
    )
    corpo_html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{titulo} · exportação estática</title>
<meta name="robots" content="noindex, nofollow">
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 780px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  .aviso {{ background: #fff3cd; padding: .5rem 1rem; border-radius: 4px; font-size: .9rem; }}
  ul {{ padding-left: 1.25rem; }}
</style>
</head>
<body>
<p class="aviso">análise / beta privado — exportação estática, sem chamada de rede</p>
<h1>{titulo}</h1>
<p>versão publicada: {pacote["versao_publicada"]} · exportado em {html.escape(pacote["exportado_em"])}</p>
<h2>nós do documento ({len(nos)})</h2>
<ul id="nos">{linhas_nos or "<li>(nenhum)</li>"}</ul>
<h2>camadas citadas ({len(meta_camadas)})</h2>
<ul id="camadas">{linhas_camadas or "<li>(nenhuma)</li>"}</ul>
<script type="application/json" id="dados-publicados">{_escapar_json_para_script(pacote)}</script>
</body>
</html>
"""
    return corpo_html.encode("utf-8")
