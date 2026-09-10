"""Jobs de arquivo por URL pública (item L6-02-h-csv-url-geojson-kml).

`conexoes.arquivo_sincronizar` faz uma passagem completa numa conexão `http`/`copiada`:
  baixa condicionalmente (ETag/Last-Modified) -> reconhece o formato pelos bytes -> converte para GeoJSON se
  for KML/KMZ/GeoRSS/GPX -> guarda o arquivo no armazenamento de objetos do inquilino -> cria uma
  `plat.importacao` -> chama a INSPEÇÃO e a CARGA do L0-04 sem alterar nada delas -> a camada aparece no
  catálogo como qualquer camada importada à mão.

O que este job NÃO faz, de propósito: não recarrega quando o servidor responde `304 Não Modificado`, e também
não recarrega quando o servidor ignora o condicional e devolve 200 com o MESMO conteúdo (sha256 igual ao da
carga anterior). Nos dois casos só o contador `sincronizacoes` sobe; `recargas` fica onde estava. É esse par
de contadores que prova a cláusula do portão.

`conexoes.arquivo_sincronizar_vencidas` é o periódico (relógio do L0-05): roda no inquilino técnico
`plataforma` e enfileira uma sincronização por conexão vencida, cada uma NO INQUILINO DONO da conexão (o job
filho carrega dado do inquilino; rodar a carga no `plataforma` criaria a camada no lugar errado).
"""

from __future__ import annotations

import json
import uuid

import psycopg2.extras
from pydantic import BaseModel, Field

from app import limites, objetos
from app.conexao import arquivo_url
from app.conexao import credencial as credencial_mod
from app.conexao import google_sheets
from app.ingestao.carregar import ingestao_carregar
from app.ingestao.inspecionar import ingestao_inspecionar
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

# formato entregue ao pipeline do L0-04 depois da conversão (KML/KMZ/GeoRSS/GPX viram GeoJSON)
FORMATO_INGESTAO = {"csv": "csv", "geojson": "geojson", "kml": "geojson", "kmz": "geojson",
                    "georss": "geojson", "gpx": "geojson"}
CONTENT_TYPE_INGESTAO = {"csv": "text/csv", "geojson": "application/geo+json"}


class SincronizarParametros(BaseModel):
    conexao_id: uuid.UUID


class VencidasParametros(BaseModel):
    limite: int = Field(limites.CONEXAO_ARQUIVO_LOTE_PERIODICO, ge=1, le=200)


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _registrar(ctx, conexao_id: str, resultado: str, detalhe: str, recarregou: bool, **campos) -> None:
    with ctx.db() as cur:
        cur.execute(
            "SELECT plat.conexao_arquivo_registrar(%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s::uuid)",
            (conexao_id, resultado, detalhe, recarregou, campos.get("formato"), campos.get("etag"),
             campos.get("last_modified"), campos.get("sha256"), campos.get("bytes"), campos.get("item_id"),
             campos.get("importacao_id")),
        )


def _confirmacao_automatica(proposta: dict) -> dict:
    """Responde as perguntas da proposta do jeito que a inspeção já sugeriu. Uma sincronização agendada não tem
    usuário na frente da tela: ou existe resposta declarada na própria proposta (sugestão de SRID, codificação
    detectada, tipo de geometria dominante), ou o job falha dizendo o que faltou — nunca chuta.
    Devolve o dicionário `confirmacao` no MESMO formato que `PUT /api/importacoes/{id}/confirmar` grava."""
    confirmacao: dict = {}
    perguntas = list(proposta.get("perguntas") or [])
    if "crs" in perguntas:
        srid = (proposta.get("crs") or {}).get("sugestao") or (proposta.get("crs") or {}).get("srid")
        if not srid:
            raise FalhaDefinitiva(
                "a inspeção não conseguiu decidir o sistema de coordenadas do arquivo e a sincronização por URL "
                "não tem quem responda; importe este arquivo uma vez à mão para declarar o CRS"
            )
        confirmacao["crs"] = {"srid": int(srid)}
        perguntas.remove("crs")
    if "codificacao" in perguntas:
        valor = (proposta.get("codificacao") or {}).get("valor") or (proposta.get("codificacao") or {}).get("sugestao")
        confirmacao["codificacao"] = {"valor": valor or "UTF-8"}
        perguntas.remove("codificacao")
    if "geometria" in perguntas:
        opcoes = (proposta.get("geometria") or {}).get("opcoes") or []
        if not opcoes:
            raise FalhaDefinitiva("a inspeção não achou tipo de geometria no arquivo baixado")
        confirmacao["geometria"] = {"escolhida": opcoes[0]}
        perguntas.remove("geometria")
    if perguntas:
        raise FalhaDefinitiva(
            "a inspeção deixou perguntas que a sincronização automática não sabe responder: " + ", ".join(perguntas)
        )
    return confirmacao


@tarefa(
    nome="conexoes.arquivo_sincronizar",
    descricao="Baixa o arquivo (CSV/GeoJSON/KML/KMZ/GeoRSS/GPX) da URL de uma conexão e o carrega como camada",
    parametros=SincronizarParametros, pesado=True, memoria_mb=1024, timeout_s=3600, tentativas=1,
    chave=lambda p: f"conexao_arquivo:{p.get('conexao_id')}", perfil_minimo="editor", ferramentas=("gdal",),
    # somente_sistema: este tipo nunca nasce de `POST /api/jobs` com parâmetro livre — nasce (a) da rota
    # `POST /api/conexoes/{id}/arquivo/sincronizar`, que ANTES confere que a conexão é do inquilino e que o
    # usuário tem `conteudo.publicar_camada` (o mesmo padrão do convite descrito em app/jobs/sistema.py: o
    # privilégio é gasto na própria rota), ou (b) do periódico, para conexões que o inquilino marcou como
    # agendadas. Sem a marca, qualquer um com `jobs.executar` mandaria a plataforma baixar uma URL arbitrária.
    somente_sistema=True,
)
def conexoes_arquivo_sincronizar(ctx, conexao_id: uuid.UUID) -> dict:
    cid = str(conexao_id)
    with ctx.db() as cur:
        cur.execute("SELECT id, tipo, modo, url, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
        conexao = cur.fetchone()
        if conexao is None:
            raise FalhaDefinitiva("conexão inexistente neste inquilino")
        cur.execute("SELECT * FROM plat.conexao_arquivo WHERE conexao_id = %s::uuid", (cid,))
        estado = cur.fetchone()
    if estado is None:
        raise FalhaDefinitiva(
            "a conexão não está configurada como arquivo por URL (POST /api/conexoes/{id}/arquivo antes)"
        )

    # autenticação por tipo (item L6-02-i): google_sheets troca o JSON da conta de serviço por access token
    # em cabecalhos_auth; os demais usam a credencial como Bearer direto (comportamento do L6-02-h). Conta do
    # Google revogada/desativada = passagem registrada como 'falhou' — a camada NUNCA mostra dado velho como
    # se fosse novo (é exatamente o que a refutação do item mede).
    cabecalhos = None
    if conexao["tipo"] == "google_sheets":
        try:
            em_claro = credencial_mod.decifrar(conexao["credencial_cifrada"], settings.PLAT_SECRET) \
                if conexao["credencial_cifrada"] else None
            cabecalhos = google_sheets.cabecalhos_auth("google_sheets", em_claro)
        except google_sheets.ErroGoogleSheets as e:
            _registrar(ctx, cid, "falhou", e.detalhe, False)
            raise FalhaDefinitiva(e.detalhe) from e
    elif conexao["credencial_cifrada"]:
        try:
            token = credencial_mod.decifrar(conexao["credencial_cifrada"], settings.PLAT_SECRET)
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except ValueError:
            cabecalhos = None  # PLAT_SECRET trocado: tenta sem credencial, mesma decisão do teste de saúde (L6-02-l)

    ctx.progresso(5, "conferindo o endereço")
    baixado = arquivo_url.baixar(
        conexao["url"], etag=estado["etag"], last_modified=estado["last_modified"], cabecalhos=cabecalhos,
    )
    if not baixado.ok:
        _registrar(ctx, cid, "falhou", baixado.mensagem, False)
        raise FalhaDefinitiva(f"o endereço não entregou o arquivo: {baixado.mensagem}")
    if baixado.nao_modificado:
        _registrar(ctx, cid, "nao_modificada", "HTTP 304: o servidor confirmou que o arquivo não mudou", False,
                   etag=baixado.etag, last_modified=baixado.last_modified)
        ctx.progresso(100, "arquivo inalterado (HTTP 304); nada recarregado")
        return {"recarregou": False, "motivo": "http_304", "status": 304}
    if estado["sha256"] and baixado.sha256 == estado["sha256"]:
        _registrar(ctx, cid, "nao_modificada",
                   "o servidor ignorou o condicional e respondeu 200, mas o conteúdo é byte a byte o mesmo "
                   "(sha256 igual ao da última carga)", False,
                   etag=baixado.etag, last_modified=baixado.last_modified)
        ctx.progresso(100, "arquivo idêntico ao anterior (sha256); nada recarregado")
        return {"recarregou": False, "motivo": "sha256_igual", "status": baixado.status}

    ctx.progresso(20, "reconhecendo o formato")
    try:
        analise = arquivo_url.analisar(baixado.dados, baixado.content_type, conexao["url"])
        if analise.formato == "csv":
            arquivo_url.conferir_faixa_coordenada(baixado.dados)
        if analise.precisa_converter:
            ctx.progresso(35, f"convertendo {analise.formato} para GeoJSON")
            corpo = arquivo_url.converter_para_geojson(ctx, baixado.dados, analise)
        else:
            corpo = baixado.dados
    except arquivo_url.ArquivoRecusado as e:
        _registrar(ctx, cid, "falhou", str(e), False, etag=baixado.etag, last_modified=baixado.last_modified)
        raise FalhaDefinitiva(str(e)) from e

    formato_ingestao = FORMATO_INGESTAO[analise.formato]
    ctx.progresso(45, "guardando o arquivo")
    nome_original = (conexao["url"].rsplit("/", 1)[-1].split("?")[0] or "arquivo")[:200]
    with ctx.db() as cur:
        obj = objetos.guardar(cur, "camada_arquivo", corpo,
                              CONTENT_TYPE_INGESTAO[formato_ingestao], usuario_id=ctx.usuario_id)
        cur.execute(
            "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s, 'arquivo', %s, %s, %s, %s, %s, %s) RETURNING id",
            (ctx.tenant_id, f"{nome_original} (por URL)"[:250], ctx.usuario_id,
             _jsonb({"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                     "content_type": obj["content_type"], "nome_original": nome_original,
                     "origem_url": conexao["url"], "conexao_id": cid}),
             obj["bytes"], ctx.usuario_id, ctx.usuario_id),
        )
        arquivo_item_id = str(cur.fetchone()["id"])
        item_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO plat.importacao(tenant_id, usuario_id, arquivo_id, item_id, formato) "
            "VALUES (%s, %s, %s::uuid, %s::uuid, %s) RETURNING id",
            (ctx.tenant_id, ctx.usuario_id, arquivo_item_id, item_id, formato_ingestao),
        )
        importacao_id = str(cur.fetchone()["id"])

    try:
        ctx.progresso(55, "inspecionando")
        ingestao_inspecionar(ctx, importacao_id=uuid.UUID(importacao_id))
        with ctx.db() as cur:
            cur.execute("SELECT estado, proposta, erro FROM plat.importacao WHERE id = %s::uuid", (importacao_id,))
            imp = cur.fetchone()
        if imp["estado"] != "proposta":
            raise FalhaDefinitiva(f"a inspeção do arquivo baixado não gerou proposta: {imp['erro'] or imp['estado']}")
        confirmacao = _confirmacao_automatica(imp["proposta"] or {})
        confirmacao["titulo"] = (imp["proposta"] or {}).get("titulo") or nome_original
        with ctx.db() as cur:
            cur.execute(
                "UPDATE plat.importacao SET estado = 'confirmada', confirmacao = %s, atualizado_em = now() "
                "WHERE id = %s::uuid", (_jsonb(confirmacao), importacao_id),
            )
        ctx.progresso(70, "carregando a camada")
        resultado = ingestao_carregar(ctx, importacao_id=uuid.UUID(importacao_id))
    except FalhaDefinitiva as e:
        _registrar(ctx, cid, "falhou", str(e), False, formato=analise.formato, etag=baixado.etag,
                   last_modified=baixado.last_modified, importacao_id=importacao_id)
        raise

    # a camada anterior desta conexão (se houver) sai de cena: a conexão aponta sempre para a cópia mais nova
    anterior = estado["item_id"]
    _registrar(ctx, cid, "carregada", f"{resultado['feicoes']} feições carregadas", True,
               formato=analise.formato, etag=baixado.etag, last_modified=baixado.last_modified,
               sha256=baixado.sha256, bytes=len(baixado.dados), item_id=resultado["item_id"],
               importacao_id=importacao_id)
    ctx.progresso(100, "camada atualizada")
    return {"recarregou": True, "formato": analise.formato, "item_id": resultado["item_id"],
            "feicoes": resultado["feicoes"], "item_anterior": str(anterior) if anterior else None,
            "importacao_id": importacao_id, "bytes": len(baixado.dados)}


@tarefa(
    nome="conexoes.arquivo_sincronizar_vencidas",
    descricao="Enfileira a sincronização das conexões de arquivo por URL cujo intervalo venceu (todos os inquilinos)",
    # 512 MB e não 256: MEDIDO nesta máquina em 06/09/2026 — a execução de 16:16 falhou com "memória excedida
    # (limite 256 MB)". O processo filho já carrega o app inteiro (~107 MB de RSS só de import, com GDAL/
    # shapely/pyproj no caminho) antes de rodar uma linha da tarefa; 256 MB não deixa folga sob pressão.
    parametros=VencidasParametros, pesado=False, memoria_mb=512, timeout_s=300, tentativas=1,
    chave=lambda p: "arquivo_sincronizar_vencidas", perfil_minimo="admin",
)
def conexoes_arquivo_sincronizar_vencidas(ctx, limite: int = limites.CONEXAO_ARQUIVO_LOTE_PERIODICO) -> dict:
    from app.jobs import sistema

    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.conexao_arquivo_candidatas(%s)", (limite,))
        candidatas = cur.fetchall()
    enfileiradas = 0
    for c in candidatas:
        ctx.verificar()
        sistema.enfileirar(
            c["tenant_id"], "conexoes.arquivo_sincronizar", {"conexao_id": str(c["conexao_id"])},
            usuario_id=c["dono_id"],
        )
        enfileiradas += 1
    ctx.progresso(100, f"{enfileiradas} sincronizações enfileiradas")
    return {"candidatas": len(candidatas), "enfileiradas": enfileiradas}
