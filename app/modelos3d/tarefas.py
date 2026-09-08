"""Tarefas da fila do item L2-09-c: converter IFC e gerar a árvore 3D Tiles.

`modelo3d.converter` — lê o arquivo do armazenamento de objetos (IFC ou GLB), valida, monta/valida o GLB
e grava: o GLB de volta no armazenamento (classe `modelo3d_glb`), uma linha por elemento em
`plat.modelo3d_elemento` e a caixa envolvente já posicionada em `plat.modelo3d.caixa`. No fim, enfileira
a geração do tileset se o modelo pedir.

Onde roda (decisão D32): AQUI, no trabalhador comum, porque a leitura do IFC deste repositório é Python
puro e não depende do IfcOpenShell. O que o IfcOpenShell resolveria — representação de fronteira
genérica, booleanas, varredura — sai contado em `elementos_sem_forma` e fica esperando a decisão do dono
sobre pôr o servidor de GPU no caminho (`PLAT_GPU_SSH`, executor `gpu` do registro de tarefas). Enquanto
essa decisão não vem, o job NÃO se declara `gpu`: `executor='gpu'` sem `PLAT_GPU_SSH` faz o registro
recusar a importação do módulo inteiro e derrubaria a aplicação em toda instalação sem GPU.

`modelo3d.tileset` — pega o GLB do modelo, gera o `tileset.json` e os GLB de conteúdo (`tiles3d.gerar`) e
grava cada um como objeto, com a chave derivada do caminho relativo dentro da árvore.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from pydantic import BaseModel

from app import limites, objetos
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.modelos3d import glb, ifc, montagem, posicionamento, servico, tiles3d

CLASSE_GLB = "modelo3d_glb"
CLASSE_TILESET = "modelo3d_tileset"
TIPO_GLB = "model/gltf-binary"


class ConverterParametros(BaseModel):
    modelo_id: uuid.UUID
    gerar_tileset: bool = False


class TilesetParametros(BaseModel):
    modelo_id: uuid.UUID


CAMINHO_TILESET = re.compile(r"^(?:tileset\.json|conteudo/[0-9]{1,6}\.glb)$")


def _baixar(chave: str, sha_esperado: str | None = None) -> bytes:
    try:
        dados = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"arquivo inexistente no armazenamento: {e}") from e
    if sha_esperado and hashlib.sha256(dados).hexdigest() != sha_esperado:
        raise FalhaDefinitiva("arquivo corrompido: sha256 divergente do gravado")
    return dados


def _chave_do_arquivo(cur, classe: str, sha256: str, referencia: str | None = None) -> str:
    onde = "referencia = %s" if referencia else "referencia IS NULL"
    valores = [classe, sha256] + ([referencia] if referencia else [])
    cur.execute(f"SELECT chave FROM plat.arquivo WHERE classe = %s AND sha256 = %s AND {onde} "
                "AND apagado_em IS NULL ORDER BY criado_em DESC LIMIT 1", valores)
    linha = cur.fetchone()
    if linha is None:
        raise FalhaDefinitiva(f"nenhum arquivo da classe {classe} com o sha256 declarado neste inquilino")
    return linha["chave"]


@tarefa(
    nome="modelo3d.converter",
    descricao="Converte o arquivo do modelo 3D (IFC ou glTF/GLB) e grava os elementos consultáveis",
    parametros=ConverterParametros,
    pesado=True,
    memoria_mb=limites.MODELO3D_MEMORIA_MB,
    timeout_s=limites.MODELO3D_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"modelo3d:{p.get('modelo_id')}",
    perfil_minimo="editor",
)
def modelo3d_converter(ctx, modelo_id: uuid.UUID, gerar_tileset: bool = False) -> dict:
    mid = str(modelo_id)
    with ctx.db() as cur:
        modelo = servico.obter(cur, mid)
        chave = _chave_do_arquivo(cur, modelo["arquivo_classe"], modelo["arquivo_sha256"])
        servico.marcar(cur, mid, estado="processando", erro=None)
    ctx.progresso(5, "baixando o arquivo")
    dados = _baixar(chave, modelo["arquivo_sha256"])
    ctx.entrada(mid, modelo["arquivo_sha256"], f"arquivo de origem ({modelo['origem']})")

    try:
        if modelo["origem"] == "ifc":
            ctx.progresso(25, "lendo o IFC")
            lido = ifc.carregar(dados, max_bytes=limites.MODELO3D_ARQUIVO_BYTES)
            elementos = lido.elementos
            if not elementos:
                raise FalhaDefinitiva("o IFC não tem nenhum elemento construído")
            ctx.progresso(55, f"montando o glTF de {len(elementos)} elementos")
            glb_bytes, resumo = montagem.montar(elementos, modelo["nome"])
        else:
            ctx.progresso(30, "conferindo o GLB")
            gltf, binario = glb.ler(dados)
            glb.exigir_embutido(gltf)
            minimo, maximo = glb.caixa(gltf, binario)
            elementos = []
            glb_bytes = dados
            resumo = {"elementos": 0, "elementos_com_forma": 0, "bytes": len(dados),
                      "caixa_minima": minimo, "caixa_maxima": maximo}
    except (ifc.IfcInvalido, glb.GlbInvalido, ValueError) as e:
        with ctx.db() as cur:
            servico.marcar(cur, mid, estado="falhou", erro=str(e)[:500])
        raise FalhaDefinitiva(str(e)[:500]) from e

    if len(glb_bytes) > limites.MODELO3D_GLB_BYTES:
        with ctx.db() as cur:
            servico.marcar(cur, mid, estado="falhou",
                           erro=f"GLB de {len(glb_bytes)} bytes acima do teto de {limites.MODELO3D_GLB_BYTES}")
        raise FalhaDefinitiva(f"GLB gerado tem {len(glb_bytes)} bytes, acima do teto")

    ctx.progresso(75, "gravando o glTF e os elementos")
    caixa = posicionamento.caixa_geografica(
        resumo["caixa_minima"], resumo["caixa_maxima"], modelo["lon"], modelo["lat"],
        modelo["altura_m"], modelo["rotacao_graus"], modelo["escala"])
    sem_forma = sum(1 for e in elementos if not e.tem_geometria)
    with ctx.db() as cur:
        gravado = objetos.guardar(cur, CLASSE_GLB, glb_bytes, TIPO_GLB, item_id=mid,
                                  usuario_id=ctx.usuario_id)
        servico.gravar_elementos(cur, ctx.tenant_id, mid, elementos)
        servico.marcar(cur, mid, estado="pronto", erro=None, glb_sha256=gravado["sha256"],
                       glb_bytes=len(glb_bytes), elementos=len(elementos),
                       elementos_sem_forma=sem_forma, caixa=caixa)
        cur.execute("SELECT plat.evento_registrar('modelos3d/converter', 'modelo3d', %s, %s::jsonb, NULL, NULL)",
                    (mid, _json({"elementos": len(elementos), "sem_forma": sem_forma,
                                 "bytes": len(glb_bytes)})))
    if gerar_tileset:
        # importação tardia: `app.jobs.sistema` importa `app.jobs.servico`, que importa `app.jobs.tipos`,
        # que importa este módulo — importar no topo fecharia o ciclo na carga da aplicação
        from app.jobs.sistema import enfileirar
        enfileirar(ctx.tenant_id, "modelo3d.tileset", {"modelo_id": mid}, usuario_id=ctx.usuario_id)
    return {"elementos": len(elementos), "elementos_sem_forma": sem_forma, "bytes_glb": len(glb_bytes),
            "caixa": caixa, "tileset_enfileirado": bool(gerar_tileset)}


@tarefa(
    nome="modelo3d.tileset",
    descricao="Gera a árvore OGC 3D Tiles 1.1 do modelo e grava os arquivos no armazenamento",
    parametros=TilesetParametros,
    pesado=True,
    memoria_mb=limites.MODELO3D_MEMORIA_MB,
    timeout_s=limites.MODELO3D_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"modelo3d-tileset:{p.get('modelo_id')}",
    perfil_minimo="editor",
    # o tileset é SEMPRE derivado de uma conversão já feita: quem o enfileira é o próprio backend (o job de
    # conversão, ou a rota de criação quando o pedido veio com `gerar_tileset`), nunca `POST /api/jobs` com
    # um id de modelo qualquer
    somente_sistema=True,
)
def modelo3d_tileset(ctx, modelo_id: uuid.UUID) -> dict:
    mid = str(modelo_id)
    with ctx.db() as cur:
        modelo = servico.obter(cur, mid)
        if not modelo.get("glb_sha256"):
            raise FalhaDefinitiva("o modelo ainda não tem glTF convertido")
        chave = _chave_do_arquivo(cur, CLASSE_GLB, modelo["glb_sha256"], referencia=mid)
    ctx.progresso(10, "baixando o glTF")
    dados = _baixar(chave, modelo["glb_sha256"])
    ctx.progresso(40, "montando a árvore 3D Tiles")
    try:
        tileset, conteudos = tiles3d.gerar(dados, modelo["lon"], modelo["lat"], modelo["altura_m"],
                                           modelo["rotacao_graus"], modelo["escala"], modelo["nome"])
    except glb.GlbInvalido as e:
        raise FalhaDefinitiva(str(e)[:500]) from e
    arquivos = {"tileset.json": tiles3d.escrever_json(tileset), **conteudos}
    ctx.progresso(70, f"gravando {len(arquivos)} arquivos")
    total = 0
    manifesto: dict[str, str] = {}
    with ctx.db() as cur:
        for caminho, corpo in arquivos.items():
            tipo = "application/json" if caminho.endswith(".json") else TIPO_GLB
            gravado = objetos.guardar(cur, CLASSE_TILESET, corpo, tipo, item_id=mid,
                                      usuario_id=ctx.usuario_id)
            manifesto[caminho] = gravado["chave"]
            total += len(corpo)
        servico.marcar(cur, mid, tileset=True, tileset_tiles=len(conteudos),
                       tileset_arquivos=manifesto)
        cur.execute("SELECT plat.evento_registrar('modelos3d/tileset', 'modelo3d', %s, %s::jsonb, NULL, NULL)",
                    (mid, _json({"tiles": len(conteudos), "bytes": total})))
    return {"tiles": len(conteudos), "arquivos": len(arquivos), "bytes": total}


def _json(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


__all__ = ["modelo3d_converter", "modelo3d_tileset", "CLASSE_GLB", "CLASSE_TILESET", "CAMINHO_TILESET"]
