"""Job `modelo3d.converter` (item L1-03-modelo3d, 10/09/2026): a mesma vertical do L1-01 (raster), mas para
modelo 3D — um arquivo `arquivo` já enviado (upload retomável, L0-04-a) que é `.ifc` (BIM, texto STEP) ou
`.xkt` (já convertido) vira item `modelo3d` no catálogo, com o `.xkt` guardado no armazenamento de objetos do
inquilino (`app/objetos.py`, mesmo adaptador do L1-01).

Conversor: esta instalação NÃO tem `ifcopenshell`/`IfcConvert` local (conferido 10/09/2026 — nenhum dos dois
está na venv nem no PATH). O caminho que existe de verdade é o mesmo do SIG de teste interno lido antes de
escrever este módulo (`ssh` para uma máquina com GPU que já tem `@xeokit/xeokit-convert` instalado em
`/home/dev/caixa-sinapi/tools/xkt/node_modules/`, alcançável pelo alias `gpu` do `~/.ssh/config` desta
máquina — respondeu `node --version` em 10/09/2026). Se esse destino não responder, ou se a conversão
falhar, o job termina com `FalhaDefinitiva` e uma mensagem honesta — nunca finge converter, nunca inventa um
`.xkt` vazio.

Um `.xkt` enviado direto (já convertido por outra ferramenta) não precisa de conversor nenhum: sobe como
está. É por isso que `app/uploads/tipos.py` aceita os dois tipos declarados (`ifc`, `xkt`) para o mesmo tipo
de item.

Sem miniatura nesta passagem (renderizar uma prévia 2D de um modelo 3D exige abrir um visualizador headless
— fora do orçamento desta trilha; o painel do item mostra o ícone genérico do tipo até existir)."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from app import limites, objetos
from app.catalogo import tipos as tipos_item
from app.catalogo.comum import jsonb
from app.jobs.registro import FalhaDefinitiva, tarefa

# alias do ~/.ssh/config desta máquina (mesmo destino que o ingestor de IFC do SIG anterior usa); pode ser
# trocado por variável de ambiente sem editar código, se o destino um dia mudar de nome
GPU_HOST = os.environ.get("PLAT_MODELO3D_SSH_HOST", "gpu")
XKT_CONVERTER_REMOTO = (
    "/home/dev/caixa-sinapi/tools/xkt/node_modules/@xeokit/xeokit-convert/convert2xkt.js"
)
SSH_OPCOES = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new")

# tipos IFC cuja contagem soma "n_elementos" no resumo (mesmo vocabulário medido no ingestor de IFC do
# lido antes de escrever esta função — não importado, reimplementado aqui: são ~20 palavras do padrão IFC4,
# não código operacional de um sistema de cliente)
_TIPOS_ELEMENTO = frozenset((
    "IFCWALL", "IFCWALLSTANDARDCASE", "IFCSLAB", "IFCDOOR", "IFCWINDOW", "IFCCOLUMN", "IFCBEAM", "IFCROOF",
    "IFCSTAIR", "IFCFOOTING", "IFCPILE", "IFCFLOWSEGMENT", "IFCFLOWTERMINAL", "IFCFLOWFITTING",
    "IFCLIGHTFIXTURE", "IFCOUTLET", "IFCSWITCHINGDEVICE", "IFCFURNISHINGELEMENT", "IFCCOVERING",
    "IFCRAILING", "IFCMEMBER", "IFCPLATE", "IFCBUILDINGELEMENTPROXY", "IFCSANITARYTERMINAL",
    "IFCDISTRIBUTIONELEMENT",
))


class IngestarParametros(BaseModel):
    arquivo_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=250)


def _ifc_texto(s: str) -> str:
    r"""decodifica \X2\00E3\X0\ (escape unicode do STEP) em texto normal."""
    return re.sub(
        r"\\X2\\([0-9A-Fa-f]+)\\X0\\",
        lambda m: "".join(chr(int(m.group(1)[i:i + 4], 16)) for i in range(0, len(m.group(1)), 4)),
        s or "",
    )


def _resumo_ifc(caminho: Path) -> dict:
    """Lê o IFC como texto STEP (sem ifcopenshell, que não existe nesta instalação): schema, projeto,
    pavimentos (IfcBuildingStorey), ambientes (IfcSpace) e contagem de elementos construtivos — o mínimo que
    dá para mostrar no painel do item sem abrir o modelo num visualizador."""
    txt = caminho.read_text(encoding="utf-8", errors="replace")
    schema = re.search(r"FILE_SCHEMA\(\('([^']+)'\)\)", txt)
    proj = re.search(r"IFCPROJECT\('[^']*',#\d+,'([^']*)'", txt)
    storeys = [_ifc_texto(m.group(1)) for m in re.finditer(r"IFCBUILDINGSTOREY\('[^']*',#\d+,'([^']*)'", txt)]
    espacos = [_ifc_texto(m.group(1)) for m in re.finditer(r"IFCSPACE\('[^']*',#\d+,'([^']*)'", txt)]
    tipos: dict[str, int] = {}
    for m in re.finditer(r"^#\d+\s*=\s*(IFC[A-Z0-9]+)\(", txt, re.M):
        tipos[m.group(1)] = tipos.get(m.group(1), 0) + 1
    elementos = sum(n for t, n in tipos.items() if t in _TIPOS_ELEMENTO)
    return {
        "schema_ifc": schema.group(1) if schema else None,
        "projeto": (_ifc_texto(proj.group(1)) or None) if proj else None,
        "pavimentos": storeys[:200],
        "ambientes": [{"nome": e} for e in espacos[:500]],
        "n_ambientes": len(espacos),
        "n_elementos": elementos,
    }


def _ifc_para_xkt(ctx, ifc_local: Path, xkt_local: Path) -> dict:
    """Converte por ssh numa máquina com GPU que já tem @xeokit/xeokit-convert instalado (mesma técnica lida
    no ingestor de IFC do SIG anterior antes de escrever esta função — reimplementada aqui com
    `ctx.subprocesso`, não importada: são sistemas separados). `FalhaDefinitiva` com mensagem honesta em
    qualquer um dos três jeitos de falhar (ssh, envio, conversão) — nunca um `.xkt` fingido."""
    t0 = time.monotonic()
    remoto = f"/home/dev/plat_upload/modelo3d_{ctx.job_id.hex}"
    ctx.log("INFO", f"conectando a '{GPU_HOST}' para converter {ifc_local.name}")
    r = ctx.subprocesso(["ssh", *SSH_OPCOES, GPU_HOST, "mkdir -p " + remoto])
    if r.returncode != 0:
        raise FalhaDefinitiva(
            f"conversor indisponível nesta máquina: não foi possível alcançar '{GPU_HOST}' por ssh "
            f"(código {r.returncode}); nenhum conversor IFC->xkt local foi encontrado nesta instalação "
            f"(ifcopenshell/IfcConvert ausentes)"
        )
    r = ctx.subprocesso(["scp", "-q", *SSH_OPCOES, str(ifc_local), f"{GPU_HOST}:{remoto}/{ifc_local.name}"])
    if r.returncode != 0:
        raise FalhaDefinitiva(
            f"conversor indisponível nesta máquina: falha ao enviar o IFC a '{GPU_HOST}' (scp código {r.returncode})"
        )
    comando = f"cd {remoto} && node {XKT_CONVERTER_REMOTO} -s {ifc_local.name} -o {xkt_local.name} 2>&1"
    r = ctx.subprocesso(["ssh", *SSH_OPCOES, GPU_HOST, comando])
    saida = f"{r.stdout or ''}{r.stderr or ''}".strip()
    if r.returncode != 0:
        detalhe = saida[-600:] or "sem saída"
        raise FalhaDefinitiva(f"a conversão IFC->xkt falhou no conversor remoto ({GPU_HOST}): {detalhe}")
    r = ctx.subprocesso(["scp", "-q", *SSH_OPCOES, f"{GPU_HOST}:{remoto}/{xkt_local.name}", str(xkt_local)])
    if r.returncode != 0 or not xkt_local.exists() or xkt_local.stat().st_size == 0:
        raise FalhaDefinitiva(f"a conversão terminou no conversor remoto mas o .xkt não voltou de '{GPU_HOST}'")
    ctx.subprocesso(["ssh", *SSH_OPCOES, GPU_HOST, "rm -rf " + remoto])  # limpeza; melhor esforço, não falha o job
    return {"conversor": "xeokit-convert", "destino_ssh": GPU_HOST, "duracao_s": round(time.monotonic() - t0, 2),
            "saida": saida[-2000:]}


@tarefa(
    nome="modelo3d.converter",
    descricao="ingere um modelo 3D enviado (arquivo .ifc ou .xkt): se for IFC, converte para .xkt no "
    "conversor desta instalação (ssh para uma máquina com GPU, xeokit-convert); sobe o .xkt ao Garage e cria "
    "o item modelo3d no catálogo, com o resumo do IFC (ambientes, elementos, pavimentos) quando disponível",
    parametros=IngestarParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=limites.MODELO3D_CONVERSAO_TIMEOUT_S + 300,
    tentativas=2,
    perfil_minimo="editor",
    ferramentas=("ssh", "scp"),
)
def modelo3d_converter(ctx, arquivo_id: uuid.UUID, titulo: str | None = None) -> dict:
    inicio = time.monotonic()
    with ctx.db() as cur:
        cur.execute("SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'",
                    (str(arquivo_id),))
        arq = cur.fetchone()
    if arq is None:
        raise FalhaDefinitiva(f"item de arquivo {arquivo_id} inexistente (ou de outro tipo que não 'arquivo')")
    dados_arq = arq["dados"] or {}
    chave_bruto = dados_arq.get("chave")
    if not chave_bruto:
        raise FalhaDefinitiva(f"item de arquivo {arquivo_id} sem chave de objeto no campo dados")
    tipo_declarado = (dados_arq.get("tipo_declarado") or "").lower()
    nome_original = dados_arq.get("nome_original") or "modelo"
    sufixo = ("." + nome_original.rsplit(".", 1)[-1].lower()) if "." in nome_original else ""
    if tipo_declarado not in ("ifc", "xkt"):
        # o tipo declarado no upload é quem manda (a mesma regra do raster); a extensão do nome é só logging
        if sufixo == ".ifc":
            tipo_declarado = "ifc"
        elif sufixo == ".xkt":
            tipo_declarado = "xkt"
        else:
            raise FalhaDefinitiva(
                f"item de arquivo {arquivo_id} não é ifc nem xkt (tipo_declarado={dados_arq.get('tipo_declarado')!r})"
            )
    titulo_final = (titulo or dados_arq.get("nome_original") or arq["titulo"] or "modelo 3D")[:250]

    ctx.progresso(5, "baixando o objeto do armazenamento")
    bruto = ctx.dir_trabalho / f"bruto{sufixo or ('.ifc' if tipo_declarado == 'ifc' else '.xkt')}"
    try:
        bytes_baixados = objetos.baixar(chave_bruto, bruto)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"o objeto do arquivo não existe mais no armazenamento: {e}") from e
    teto = limites.MODELO3D_IFC_BYTES_MAX if tipo_declarado == "ifc" else limites.MODELO3D_XKT_BYTES_MAX
    if bytes_baixados > teto:
        raise FalhaDefinitiva(f"modelo de {bytes_baixados} bytes acima do máximo desta instalação ({teto})")
    ctx.entrada(arquivo_id, dados_arq.get("sha256") or "", f"bruto {bytes_baixados} bytes ({tipo_declarado})")

    resumo_ifc: dict = {}
    conversao: dict = {}
    ifc_chave = None
    if tipo_declarado == "ifc":
        ctx.progresso(15, "lendo o IFC (schema, ambientes, pavimentos)")
        try:
            resumo_ifc = _resumo_ifc(bruto)
        except Exception as e:  # noqa: BLE001 — leitura de texto nunca deve derrubar o job; segue sem resumo
            ctx.log("AVISO", f"não foi possível ler o resumo do IFC: {e}")
        ctx.progresso(25, f"convertendo para .xkt em '{GPU_HOST}'")
        xkt_local = ctx.dir_trabalho / "modelo.xkt"
        conversao = _ifc_para_xkt(ctx, bruto, xkt_local)
        ctx.progresso(70, "convertido; subindo o .xkt")
        origem = "ifc_convertido"
    else:
        xkt_local = bruto
        ctx.progresso(60, "xkt já convertido; subindo")
        origem = "xkt_enviado"

    item_id = str(uuid.uuid4())
    with ctx.db() as cur:
        o_xkt = objetos.guardar_arquivo(cur, "modelo3d", xkt_local, "application/octet-stream", item_id=item_id,
                                        usuario_id=ctx.usuario_id)
    if tipo_declarado == "ifc":
        with ctx.db() as cur:
            o_ifc = objetos.guardar_arquivo(cur, "modelo3d", bruto, "application/octet-stream", item_id=item_id,
                                            usuario_id=ctx.usuario_id)
        ifc_chave = o_ifc["chave"]

    ctx.progresso(90, "gravando o item no catálogo")
    dados_item = {
        "xkt_chave": o_xkt["chave"],
        "origem": origem,
        "ifc_chave": ifc_chave,
        "bytes_xkt": o_xkt["bytes"],
        "conversao": conversao or None,
        **resumo_ifc,
    }
    tipos_item.validar("modelo3d", dados_item)
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'modelo3d', %s, %s, %s, %s, %s, %s)",
            (item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, jsonb(dados_item), o_xkt["bytes"],
             ctx.usuario_id, ctx.usuario_id),
        )
    ctx.entrada(item_id, o_xkt["sha256"], "modelo 3D (.xkt) no catálogo")

    duracao = time.monotonic() - inicio
    ctx.progresso(100, "concluído")
    return {
        "item_id": item_id,
        "titulo": titulo_final,
        "origem": origem,
        "bytes_xkt": o_xkt["bytes"],
        "sha256_xkt": o_xkt["sha256"],
        "duracao_s": round(duracao, 2),
        "conversao": conversao or None,
        "n_ambientes": resumo_ifc.get("n_ambientes"),
        "n_elementos": resumo_ifc.get("n_elementos"),
    }


__all__ = ["modelo3d_converter", "IngestarParametros"]
