"""Anexos por feição (item L2-03-edicao, portão: "anexos com limite de tamanho e de tipo"). O objeto em si vive
no Garage por trás de `app.objetos.guardar` (bucket por inquilino, cota, dedup por sha256 — item L0-11);
`plat.feicao_anexo` só liga (schema, tabela, globalid) ao objeto guardado, porque `plat.arquivo` não conhece
feição.

Entrada por JSON base64 sob cookie de sessão (mesmo padrão de `app/catalogo/rotas_miniatura.py`: o CSRF sob
cookie exige `application/json` em todo verbo de escrita — corpo cru exigiria token de serviço, ver
`app/rotas_arquivos.py`). Limite de TAMANHO e de TIPO são os dois aplicados NO SERVIDOR antes de decodificar
o base64 inteiro em memória (limite de bytes CODIFICADOS primeiro, barato, depois o tamanho DECODIFICADO real)."""

from __future__ import annotations

import base64
import binascii

from app import limites, objetos
from app.catalogo import comum
from app.edicao.servico import _schema_tabela, camada_ou_404, exigir_camada_editavel
from app.erros import ErroAPI
from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho


def _decodificar(conteudo_base64: str) -> bytes:
    if len(conteudo_base64) > (limites.ANEXO_TAMANHO_MAX * 4 // 3) + 16:
        raise ErroAPI(
            422, "anexo_grande",
            f"anexo acima de {limites.ANEXO_TAMANHO_MAX} bytes (limite declarado da plataforma)",
            {"limite_bytes": limites.ANEXO_TAMANHO_MAX},
        )
    try:
        dados = base64.b64decode(conteudo_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "anexo_invalido", "conteúdo não é base64 válido") from e
    if len(dados) > limites.ANEXO_TAMANHO_MAX:
        raise ErroAPI(
            422, "anexo_grande", f"anexo de {len(dados)} bytes acima do limite de {limites.ANEXO_TAMANHO_MAX}",
            {"bytes": len(dados), "limite_bytes": limites.ANEXO_TAMANHO_MAX},
        )
    return dados


def _tipo_ou_recusar(content_type: str) -> str:
    tipo = (content_type or "").split(";")[0].strip().lower()
    if tipo not in limites.ANEXO_TIPOS_PERMITIDOS:
        raise ErroAPI(
            415, "tipo_nao_permitido", f"tipo de anexo não permitido: {tipo!r}",
            {"tipo_enviado": tipo, "tipos_permitidos": sorted(limites.ANEXO_TIPOS_PERMITIDOS)},
        )
    return tipo


def enviar(
    cur, auth, request, camada_id: str, globalid: str, nome: str, content_type: str, conteudo_base64: str
) -> dict:
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    schema, tabela = _schema_tabela(dados)
    cur.execute(f'SELECT 1 FROM "{schema}"."{tabela}" WHERE globalid = %s', (globalid,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"id": globalid})

    tipo = _tipo_ou_recusar(content_type)
    dados_bin = _decodificar(conteudo_base64)
    try:
        escanear_cabecalho(dados_bin, tipo)
    except ConteudoRecusado as e:
        raise ErroAPI(415, "conteudo_recusado", str(e)) from e

    obj = objetos.guardar(cur, "feicao_anexo", dados_bin, tipo, item_id=globalid, usuario_id=auth.usuario_id)
    cur.execute(
        "INSERT INTO plat.feicao_anexo (tenant_id, schema_dado, tabela_dado, globalid, nome, content_type, "
        "bytes, sha256, chave, criado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id, numero, criado_em",
        (schema, tabela, globalid, nome[:255], tipo, obj["bytes"], obj["sha256"], obj["chave"], auth.usuario_id),
    )
    r = cur.fetchone()
    comum.registrar_evento(
        cur, request, "camadas/anexo_enviar", "item", item["id"],
        {"globalid": globalid, "anexo_id": str(r["id"]), "bytes": obj["bytes"], "content_type": tipo},
    )
    return {
        "id": str(r["id"]), "numero": r["numero"], "nome": nome[:255], "content_type": tipo,
        "bytes": obj["bytes"], "sha256": obj["sha256"], "criado_em": r["criado_em"].isoformat(),
    }


def substituir(
    cur, auth, request, camada_id: str, globalid: str, anexo_id: str, nome: str, content_type: str,
    conteudo_base64: str,
) -> dict:
    """Troca o CONTEÚDO de um anexo mantendo o mesmo identificador (item L2-04-d: o `updateAttachment` da Esri
    devolve o mesmo `attachmentId`, e cliente que guardou o id não pode ficar apontando para nada). O bloco
    antigo continua no Garage sob a chave antiga — `app/objetos.py` faz dedup por sha256 e a limpeza de objeto
    sem referência é do item de retenção, não deste."""
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    schema, tabela = _schema_tabela(dados)
    antigo = _anexo_ou_404(cur, schema, tabela, globalid, anexo_id)
    tipo = _tipo_ou_recusar(content_type)
    dados_bin = _decodificar(conteudo_base64)
    try:
        escanear_cabecalho(dados_bin, tipo)
    except ConteudoRecusado as e:
        raise ErroAPI(415, "conteudo_recusado", str(e)) from e
    obj = objetos.guardar(cur, "feicao_anexo", dados_bin, tipo, item_id=globalid, usuario_id=auth.usuario_id)
    cur.execute(
        "UPDATE plat.feicao_anexo SET nome = %s, content_type = %s, bytes = %s, sha256 = %s, chave = %s "
        "WHERE id = %s::uuid AND apagado_em IS NULL RETURNING id, numero",
        (nome[:255] or antigo["nome"], tipo, obj["bytes"], obj["sha256"], obj["chave"], anexo_id),
    )
    r = cur.fetchone()
    comum.registrar_evento(
        cur, request, "camadas/anexo_enviar", "item", item["id"],
        {"globalid": globalid, "anexo_id": anexo_id, "bytes": obj["bytes"], "content_type": tipo,
         "substituicao": True},
    )
    return {"id": str(r["id"]), "numero": r["numero"], "nome": nome[:255], "content_type": tipo,
            "bytes": obj["bytes"], "sha256": obj["sha256"]}


def listar(cur, camada_id: str, globalid: str) -> list[dict]:
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    cur.execute(
        "SELECT id, numero, nome, content_type, bytes, sha256, criado_por, criado_em FROM plat.feicao_anexo "
        "WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s AND apagado_em IS NULL "
        "ORDER BY criado_em DESC",
        (schema, tabela, globalid),
    )
    return [
        {
            "id": str(r["id"]), "numero": r["numero"], "nome": r["nome"],
            "content_type": r["content_type"], "bytes": r["bytes"],
            "sha256": r["sha256"], "criado_por": r["criado_por"], "criado_em": r["criado_em"].isoformat(),
        }
        for r in cur.fetchall()
    ]


def _anexo_ou_404(cur, schema: str, tabela: str, globalid: str, anexo_id: str) -> dict:
    cur.execute(
        "SELECT id, numero, nome, content_type, chave FROM plat.feicao_anexo WHERE id = %s::uuid "
        "AND schema_dado = %s "
        "AND tabela_dado = %s AND globalid = %s AND apagado_em IS NULL",
        (anexo_id, schema, tabela, globalid),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "anexo_inexistente", "anexo inexistente para esta feição")
    return r


def baixar(cur, camada_id: str, globalid: str, anexo_id: str) -> tuple[bytes, str, str]:
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    r = _anexo_ou_404(cur, schema, tabela, globalid, anexo_id)
    return objetos.ler(r["chave"]), r["content_type"], r["nome"]


def apagar(cur, auth, request, camada_id: str, globalid: str, anexo_id: str) -> None:
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    schema, tabela = _schema_tabela(dados)
    _anexo_ou_404(cur, schema, tabela, globalid, anexo_id)
    cur.execute(
        "UPDATE plat.feicao_anexo SET apagado_em = now() WHERE id = %s::uuid AND apagado_em IS NULL",
        (anexo_id,),
    )
    comum.registrar_evento(
        cur, request, "camadas/anexo_apagar", "item", item["id"], {"globalid": globalid, "anexo_id": anexo_id}
    )
