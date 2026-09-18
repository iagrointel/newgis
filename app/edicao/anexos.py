"""Anexos por feição (item L2-03-edicao, portão: "anexos com limite de tamanho e de tipo"; item
L2-03-e-anexos acrescenta miniatura, remoção de EXIF GPS por opção do inquilino, cascata no apagar da
feição e o ceife de órfãos). O objeto em si vive no Garage por trás de `app.objetos.guardar` (bucket por
inquilino, cota, dedup por sha256 — item L0-11); `plat.feicao_anexo` só liga (schema, tabela, globalid) ao
objeto guardado, porque `plat.arquivo` não conhece feição.

Entrada por JSON base64 sob cookie de sessão (mesmo padrão de `app/catalogo/rotas_miniatura.py`: o CSRF sob
cookie exige `application/json` em todo verbo de escrita — corpo cru exigiria token de serviço, ver
`app/rotas_arquivos.py`). Limite de TAMANHO e de TIPO são os dois aplicados NO SERVIDOR antes de decodificar
o base64 inteiro em memória (limite de bytes CODIFICADOS primeiro, barato, depois o tamanho DECODIFICADO real).

Acima do limite = **413** (portão do L2-03-e; o 422 inicial divergia do portão e do idioma da casa —
`app/auth/rotas_org.py::logo_grande` e o teto de corpo do middleware L0-12 também são 413). O 413 do
middleware NUNCA esconde este: `ANEXO_TAMANHO_MAX` cabe, com folga, dentro de `CORPO_MAX_PADRAO_BYTES`
mesmo inchado por base64 (~4/3), então a checagem específica dispara antes do teto genérico do corpo — a
mesma garantia que o 422 tinha, agora com o status que o portão escreveu."""

from __future__ import annotations

import base64
import binascii
import io
import logging
import shutil
import subprocess
import tempfile
import warnings

from app import limites, objetos
from app.catalogo import comum
from app.edicao.servico import _schema_tabela, camada_ou_404, exigir_camada_editavel
from app.erros import ErroAPI
from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho

log = logging.getLogger("plat.anexos")

MINIATURA_LADO = 256  # px, lado máximo da miniatura (portão L2-03-e: "dimensões ≤ 256")
_TIPOS_IMAGEM = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _decodificar(conteudo_base64: str) -> bytes:
    if len(conteudo_base64) > (limites.ANEXO_TAMANHO_MAX * 4 // 3) + 16:
        raise ErroAPI(
            413, "anexo_grande",
            f"anexo acima de {limites.ANEXO_TAMANHO_MAX} bytes (limite declarado da plataforma)",
            {"limite_bytes": limites.ANEXO_TAMANHO_MAX},
        )
    try:
        dados = base64.b64decode(conteudo_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "anexo_invalido", "conteúdo não é base64 válido") from e
    if len(dados) > limites.ANEXO_TAMANHO_MAX:
        raise ErroAPI(
            413, "anexo_grande", f"anexo de {len(dados)} bytes acima do limite de {limites.ANEXO_TAMANHO_MAX}",
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


# ---------------------------------------------------------------- EXIF GPS (opção do inquilino, LGPD)
def _remover_exif_gps_ativo(cur) -> bool:
    """`tenant.config.anexos_remover_exif_gps` (bool, PUT /api/org): ligado = todo anexo de imagem entra no
    Garage JÁ sem o bloco de GPS do EXIF (a foto sai do celular com a coordenada de onde foi tirada — dado
    pessoal que o inquilino pode não ter base legal para guardar)."""
    cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
    r = cur.fetchone()
    return bool(r and (r["config"] or {}).get("anexos_remover_exif_gps"))


def _sem_exif_gps(dados: bytes, tipo: str) -> bytes:
    """Bytes da imagem sem o IFD de GPS (0x8825) do EXIF. Só reencoda quando há GPS de verdade — sem GPS os
    bytes voltam INTOCUADOS (o sha256 conferido no download continua sendo o do arquivo enviado). Falha de
    leitura não derruba o envio: o cabeçalho já foi varrido por `escanear_cabecalho`; aqui é melhor-esforço
    com log, nunca silêncio."""
    if tipo not in _TIPOS_IMAGEM:
        return dados
    try:
        from PIL import Image
        with Image.open(io.BytesIO(dados)) as im:
            exif = im.getexif()
            if not exif or not exif.get_ifd(0x8825):
                return dados
            del exif[0x8825]
            buf = io.BytesIO()
            im.save(buf, format=im.format, exif=exif)
            return buf.getvalue()
    except Exception as e:  # noqa: BLE001 — imagem que o Pillow não lê: o anexo entra como veio
        log.warning("anexos: não consegui remover EXIF GPS (%s); anexo gravado sem tocar os bytes", e)
        return dados


# ---------------------------------------------------------------- miniatura (JPG/imagens por PIL; PDF por pdftoppm)
def _miniatura_imagem(dados: bytes) -> bytes | None:
    from PIL import Image, ImageOps
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados)) as im:
                im.load()
                im = ImageOps.exif_transpose(im)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGB")
                contida = ImageOps.contain(im, (MINIATURA_LADO, MINIATURA_LADO),
                                           method=Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        contida.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001 — sem miniatura não é falha do anexo
        log.warning("anexos: miniatura de imagem falhou (%s)", e)
        return None


def _miniatura_pdf(dados: bytes) -> bytes | None:
    """Primeira página do PDF renderizada pelo `pdftoppm` do poppler (já é dependência da casa para a
    miniatura de item do catálogo). Sem o binário no ambiente, o anexo entra sem miniatura (log, não erro)."""
    if not shutil.which("pdftoppm"):
        log.warning("anexos: pdftoppm ausente; PDF sem miniatura")
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="plat-anexo-mini-") as tmp:
            origem = f"{tmp}/a.pdf"
            with open(origem, "wb") as f:
                f.write(dados)
            subprocess.run(
                ["pdftoppm", "-png", "-singlefile", "-scale-to", str(MINIATURA_LADO), origem, f"{tmp}/m"],
                check=True, capture_output=True, timeout=30,
            )
            with open(f"{tmp}/m.png", "rb") as f:
                return f.read()
    except Exception as e:  # noqa: BLE001 — PDF malformado/pdftoppm falhou: o anexo vale sem miniatura
        log.warning("anexos: miniatura de PDF falhou (%s)", str(e)[:200])
        return None


def _miniatura(dados: bytes, tipo: str) -> bytes | None:
    if tipo in _TIPOS_IMAGEM:
        return _miniatura_imagem(dados)
    if tipo == "application/pdf":
        return _miniatura_pdf(dados)
    return None


def _guardar_com_miniatura(cur, dados_bin: bytes, tipo: str, globalid: str, usuario_id: int) -> tuple[dict, str | None]:
    """Guarda o anexo e, quando o tipo tem miniatura, a miniatura (objetos classe `feicao_anexo_mini`,
    PNG ≤ 256 px de lado). Devolve (objeto do anexo, chave da miniatura ou None)."""
    obj = objetos.guardar(cur, "feicao_anexo", dados_bin, tipo, item_id=globalid, usuario_id=usuario_id)
    mini = _miniatura(dados_bin, tipo)
    if not mini:
        return obj, None
    om = objetos.guardar(cur, "feicao_anexo_mini", mini, "image/png", item_id=globalid, usuario_id=usuario_id)
    return obj, om["chave"]


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
    if _remover_exif_gps_ativo(cur):
        dados_bin = _sem_exif_gps(dados_bin, tipo)

    obj, mini_chave = _guardar_com_miniatura(cur, dados_bin, tipo, globalid, auth.usuario_id)
    cur.execute(
        "INSERT INTO plat.feicao_anexo (tenant_id, schema_dado, tabela_dado, globalid, nome, content_type, "
        "bytes, sha256, chave, mini_chave, criado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id, numero, criado_em",
        (schema, tabela, globalid, nome[:255], tipo, obj["bytes"], obj["sha256"], obj["chave"], mini_chave,
         auth.usuario_id),
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
    if _remover_exif_gps_ativo(cur):
        dados_bin = _sem_exif_gps(dados_bin, tipo)
    obj, mini_chave = _guardar_com_miniatura(cur, dados_bin, tipo, globalid, auth.usuario_id)
    cur.execute(
        "UPDATE plat.feicao_anexo SET nome = %s, content_type = %s, bytes = %s, sha256 = %s, chave = %s, "
        "mini_chave = %s "
        "WHERE id = %s::uuid AND apagado_em IS NULL RETURNING id, numero",
        (nome[:255] or antigo["nome"], tipo, obj["bytes"], obj["sha256"], obj["chave"], mini_chave, anexo_id),
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
        "SELECT id, numero, nome, content_type, bytes, sha256, mini_chave, criado_por, criado_em "
        "FROM plat.feicao_anexo "
        "WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s AND apagado_em IS NULL "
        "ORDER BY criado_em DESC",
        (schema, tabela, globalid),
    )
    return [
        {
            "id": str(r["id"]), "numero": r["numero"], "nome": r["nome"],
            "content_type": r["content_type"], "bytes": r["bytes"],
            "sha256": r["sha256"], "miniatura": r["mini_chave"] is not None,
            "criado_por": r["criado_por"], "criado_em": r["criado_em"].isoformat(),
        }
        for r in cur.fetchall()
    ]


def _anexo_ou_404(cur, schema: str, tabela: str, globalid: str, anexo_id: str) -> dict:
    cur.execute(
        "SELECT id, numero, nome, content_type, chave, mini_chave FROM plat.feicao_anexo WHERE id = %s::uuid "
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


def baixar_miniatura(cur, camada_id: str, globalid: str, anexo_id: str) -> bytes:
    """PNG da miniatura (≤ 256 px de lado, gerada no envio). 404 quando o tipo do anexo não tem miniatura
    (GIF animado pequeno demais, PDF sem pdftoppm no envio) — "sem miniatura" é estado, não erro."""
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    r = _anexo_ou_404(cur, schema, tabela, globalid, anexo_id)
    if not r["mini_chave"]:
        raise ErroAPI(404, "anexo_sem_miniatura", "este anexo não tem miniatura")
    return objetos.ler(r["mini_chave"])


# ---------------------------------------------------------------- cascata no apagar da feição (portão L2-03-e)
def apagar_das_feicoes(cur, schema: str, tabela: str, globalids: list) -> int:
    """Apagamento LÓGICO de todos os anexos das feições dadas — chamado por todo caminho que apaga a feição
    (`servico._apagar`, `lote.executar` apagar/mover), NA MESMA TRANSAÇÃO do DELETE da feição: ou entram os
    dois ou nenhum. O objeto do Garage sai depois, pelo ceife de órfãos (`tarefas.edicao_anexos_ceifar`).
    Importado LOCALMENTE pelos chamadores: este módulo já importa `servico`, um import no topo fecharia ciclo."""
    if not globalids:
        return 0
    cur.execute(
        "UPDATE plat.feicao_anexo SET apagado_em = now() WHERE schema_dado = %s AND tabela_dado = %s "
        "AND globalid = ANY(%s::uuid[]) AND apagado_em IS NULL",
        (schema, tabela, [str(g) for g in globalids]),
    )
    return cur.rowcount


def contar_das_feicoes(cur, schema: str, tabela: str, globalids: list) -> dict:
    """{globalid: n} de anexos vivos por feição, UMA consulta agrupada — usado pela tabela de atributos
    (uma contagem por LINHA da página, sem N+1) e pelo popup do mapa."""
    if not globalids:
        return {}
    cur.execute(
        "SELECT globalid, count(*) AS n FROM plat.feicao_anexo WHERE schema_dado = %s AND tabela_dado = %s "
        "AND globalid = ANY(%s::uuid[]) AND apagado_em IS NULL GROUP BY globalid",
        (schema, tabela, [str(g) for g in globalids]),
    )
    return {str(r["globalid"]): int(r["n"]) for r in cur.fetchall()}


# ---------------------------------------------------------------- ceife de órfãos (objeto físico some DEPOIS do apagado lógico)
def ceifar_orfaos(cur, apagar_objeto=None, limite: int = 1000) -> dict:
    """Remove do Garage os objetos de anexos com `apagado_em` marcado (por `apagar` ou pela cascata da
    feição), quando NENHUMA linha viva usa a mesma chave — o dedup por sha256 faz dois anexos idênticos
    da mesma feição dividirem chave, e apagar um não pode derrubar o outro. Depois zera `chave`/`mini_chave`
    da linha (fica o sha256 para auditoria), para a próxima passada não revarrer o que já foi físico.

    `cur` roda SEM contexto de inquilino: a seleção e a limpeza são as funções SECURITY DEFINER da migração
    20260918T1700 (a política de `plat.feicao_anexo` é FORCE RLS — sem definer o ceife não enxergaria nada).
    MVCC cobre a corrida com a transação que está apagando AGORA: a linha marcada mas não commitada ainda é
    vista como viva, então o objeto dela não entra na lista. `apagar_objeto` é injeção para o teste medir
    sem Garage; em produção é `objetos.apagar`. Idempotente por construção: objeto já ausente devolve False
    e a linha é limpa mesmo assim."""
    if apagar_objeto is None:
        apagar_objeto = objetos.apagar
    cur.execute("SELECT * FROM plat.feicao_anexo_orfaos(%s)", (limite,))
    linhas = cur.fetchall()
    removidos, falhas, limpos = 0, 0, []
    for l in linhas:
        try:
            apagar_objeto(l["chave"])
            if l["mini_chave"]:
                apagar_objeto(l["mini_chave"])
        except Exception as e:  # noqa: BLE001 — melhor-esforço por objeto: o que falha volta na próxima passada
            log.warning("anexos: ceife não removeu %s (%s)", l["chave"], str(e)[:200])
            falhas += 1
            continue
        limpos.append(str(l["id"]))
        removidos += 1
    if limpos:
        cur.execute("SELECT plat.feicao_anexo_chave_limpar(%s::uuid[]) AS n", (limpos,))
    return {"candidatos": len(linhas), "objetos_removidos": removidos, "falhas": falhas}
