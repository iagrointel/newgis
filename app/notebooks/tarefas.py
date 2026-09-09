"""Job `notebooks.executar` (L2-16-b): executa um notebook AGENDADO dentro do contêiner do
inquilino (jupyter nbconvert --execute) e grava o HTML com a saída como item
`notebook_saida` + evento `notebooks/executado`.

É a cláusula do portão "notebook agendado roda e salva HTML com a saída": o mesmo contêiner
da sessão interativa serve a execução sem interface, com o MESMO isolamento (rede interna,
RAM limitada, único segredo = token do usuário).

Regras: o item de entrada tem tipo `notebook` (o .ipynb vem do Garage por dados.chave); a
execução com erro de célula FALHA o job (nbconvert sai com erro — a casa prefere falha
honesta a saída pela metade); todo trabalho longo de subprocesso fica FORA de ctx.db()
(idle_in_transaction_session_timeout = 60 s).
"""

import json
import subprocess
import uuid as modulo_uuid

import psycopg2.extras
from pydantic import BaseModel, Field

from app import db as banco
from app import objetos
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.notebooks import contenedor

TAM_MAX_NB = 10 * 1024 * 1024  # 10 MiB de .ipynb é muito; acima disso é erro de pedido
TAM_MAX_HTML = 64 * 1024 * 1024


class ExecutarParametros(BaseModel):
    item_id: str = Field(description="id do item do tipo `notebook` (.ipynb) a executar")
    timeout_s: int = Field(default=300, ge=10, le=900,
                           description="teto de execução do nbconvert (célula travada morre aqui)")


@tarefa(
    nome="notebooks.executar",
    descricao="Executa um notebook agendado no contêiner do inquilino e grava o HTML com a saída",
    parametros=ExecutarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=960,
    tentativas=1,
    perfil_minimo="editor",
    versao=1,
)
def notebooks_executar(ctx, item_id: str, timeout_s: int = 300) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT tipo, dados FROM plat.item WHERE id = %s::uuid", (item_id,))
        item = cur.fetchone()
    if item is None or item["tipo"] != "notebook":
        raise FalhaDefinitiva(f"item {item_id} não é um notebook deste inquilino")
    chave = (item["dados"] or {}).get("chave")
    if not chave:
        raise FalhaDefinitiva("item do notebook sem objeto (.ipynb) anexado")
    bruto = objetos.ler(chave)
    if len(bruto) > TAM_MAX_NB:
        raise FalhaDefinitiva(f"notebook acima do teto de {TAM_MAX_NB} bytes")
    try:
        nb = json.loads(bruto)
        celulas = nb["cells"]
        if not isinstance(celulas, list) or not celulas:
            raise ValueError("sem células")
    except (ValueError, KeyError, TypeError) as e:
        raise FalhaDefinitiva(f"conteúdo do .ipynb inválido: {e}") from None

    if not ctx.usuario_id:
        raise FalhaDefinitiva("job de notebook sem usuário: o token do contêiner precisa de dono")
    with ctx.db() as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        linha = cur.fetchone()
    if linha is None:
        raise FalhaDefinitiva(f"inquilino {ctx.tenant_id} inexistente")
    slug = linha["slug"]

    ctx.progresso(10, "levantando contêiner do inquilino")
    # fora de ctx.db(): levantar roda docker CLI e espera partida (até 20 s)
    subida = contenedor.levantar(slug, banco.Contexto(ctx.tenant_id, ctx.usuario_id, "worker"))
    nome = subida["contenedor"]

    ctx.progresso(30, "copiando notebook para o contêiner")
    caminho_nb = f"/home/jovyan/trabalho/{item_id}.ipynb"
    caminho_html = f"/home/jovyan/trabalho/{item_id}.html"
    copiado = subprocess.run(["docker", "exec", "-i", nome, "sh", "-c", f"cat > {caminho_nb}"],
                             input=bruto, capture_output=True, timeout=60)
    if copiado.returncode != 0:
        raise FalhaDefinitiva("não consegui escrever o .ipynb no contêiner: "
                              + copiado.stderr.decode(errors="replace")[-300:])

    ctx.progresso(50, "executando notebook (nbconvert)")
    try:
        convertido = subprocess.run(
            ["docker", "exec", nome, "jupyter", "nbconvert", "--to", "html", "--execute",
             f"--ExecutePreprocessor.timeout={timeout_s}",
             caminho_nb, "--output", caminho_html],
            capture_output=True, timeout=timeout_s + 120,
        )
    except subprocess.TimeoutExpired as e:
        raise FalhaDefinitiva(f"execução do notebook passou de {timeout_s} s") from e
    if convertido.returncode != 0:
        cauda = convertido.stderr.decode(errors="replace")[-500:]
        raise FalhaDefinitiva(f"notebook terminou com erro de execução: {cauda}")

    ctx.progresso(80, "lendo a saída HTML")
    lido = subprocess.run(["docker", "exec", nome, "cat", caminho_html],
                          capture_output=True, timeout=60)
    if lido.returncode != 0:
        raise FalhaDefinitiva("notebook executou mas o HTML não voltou: "
                              + lido.stderr.decode(errors="replace")[-300:])
    html = lido.stdout
    if len(html) > TAM_MAX_HTML:
        raise FalhaDefinitiva(f"saída HTML acima do teto de {TAM_MAX_HTML} bytes")

    ctx.progresso(90, "gravando item de saída")
    novo_id = str(modulo_uuid.uuid4())
    with ctx.db() as cur:
        guardado = objetos.guardar(cur, "notebook_saida", html, "text/html",
                                   item_id=novo_id, usuario_id=ctx.usuario_id)
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, "
            "criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'notebook_saida', %s, %s, %s, %s, %s)",
            [
                novo_id, ctx.tenant_id, f"saída do notebook {item_id[:8]}", ctx.usuario_id,
                psycopg2.extras.Json({
                    "chave": guardado["chave"],
                    "sha256": guardado["sha256"],
                    "bytes": guardado["bytes"],
                    "content_type": guardado["content_type"],
                    "nome_original": f"{item_id}.html",
                    "notebook_id": item_id,
                    "job_id": str(ctx.job_id),
                }, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str)),
                ctx.usuario_id, ctx.usuario_id,
            ],
        )
        cur.execute("SELECT plat.evento_registrar('notebooks/executado', 'item', %s, %s::jsonb, NULL, NULL)",
                    (novo_id, json.dumps({"notebook_id": item_id, "job_id": str(ctx.job_id),
                                          "bytes_html": guardado["bytes"]})))
    return {"item_id": novo_id, "bytes": guardado["bytes"], "contenedor": nome,
            "partida_s": subida["s"]}


class CeifarParametros(BaseModel):
    """Sem parâmetros: os limites vêm do ambiente (PLAT_NOTEBOOK_OCIOSIDADE_MIN/TETO_HORAS)."""


@tarefa(
    nome="notebooks.ceifar",
    descricao="Encerra notebooks ociosos (OCIOSIDADE_MIN sem uso) ou velhos demais (TETO_HORAS)",
    parametros=CeifarParametros,
    pesado=False,
    memoria_mb=128,
    timeout_s=300,
    tentativas=1,
    chave=lambda p: "notebook_ceifar",
    perfil_minimo="admin",
)
def notebooks_ceifar(ctx) -> dict:
    ctx.progresso(50, "ceifando notebooks ociosos")
    ceifados = contenedor.ceifar()
    return {"ceifados": ceifados}


# periódico da casa (mesma forma de app/catalogo/periodicos.py): o worker lê a lista de
# app/jobs/periodicos.py ao sincronizar; nenhum arquivo do L0-05 é editado aqui.
from app.jobs import periodicos as _base_periodicos  # noqa: E402 — registro por importação

PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("notebooks ociosos", "*/5 * * * *", "notebooks.ceifar", {}),
]
for _p in PERIODICOS:
    if _p not in _base_periodicos.PERIODICOS:
        _base_periodicos.PERIODICOS.append(_p)
