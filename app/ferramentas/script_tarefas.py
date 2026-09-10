"""Job `ferramentas.executar_script` (item L2-16-c-script-vira-ferramenta): executa o script de
uma ferramenta publicada DENTRO do contêiner do inquilino (L2-16-b — a mesma rede interna sem
saída, o mesmo teto de RAM/CPU, o mesmo token de leitura) e registra o resultado como item
`ferramenta_resultado` com a procedência apontando a VERSÃO e o sha256 EXATOS do texto
executado.

Prova da versão (cláusula do portão): o job não lê o código do estado atual do item — lê o
RETRATO imutável `plat.item_versao` na versão congelada pelo parâmetro do job, e confere o
sha256 do texto antes de rodar. Versão nova publicada depois não muda execução passada nenhuma.

Contrato com o script: `entradas.json` ao lado do script traz {"parametros": {...}}; o script
declara saídas com `plat.saidas.gravar` (SDK copiado junto, na versão deste commit) para
`saida.json`; o job recusa saída com chave fora do declarado no cabeçalho. Script sem saída
válida FALHA o job (falha honesta, nunca item vazio).
"""

import hashlib
import json
import subprocess
import tarfile
import tempfile
import uuid as modulo_uuid
from io import BytesIO
from pathlib import Path

import psycopg2.extras
from pydantic import BaseModel, Field

from app import db as banco
from app.ferramentas import cabecalho
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.notebooks import contenedor

TAM_MAX_SAIDA = 16 * 1024 * 1024  # 16 MiB de saida.json é muito; acima disso é erro de ferramenta
RAIZ = Path(__file__).resolve().parents[2]


class ExecutarScriptParametros(BaseModel):
    ferramenta_id: str = Field(description="id do item `ferramenta_script` a executar")
    versao: int = Field(ge=1, description="versão do script (plat.item_versao) que a execução congela")
    sha256: str = Field(pattern="^[0-9a-f]{64}$",
                        description="sha256 do texto do script desta versão (conferido antes de rodar)")
    parametros: dict = Field(default_factory=dict, description="valores já validados pela API")
    timeout_s: int = Field(default=300, ge=5, le=900,
                           description="teto de execução do script (laço infinito morre aqui)")


def _codigo_da_versao(ctx, item_id: str, versao: int) -> str:
    with ctx.db() as cur:
        cur.execute("SELECT tipo, titulo FROM plat.item WHERE id = %s::uuid", (item_id,))
        item = cur.fetchone()
        if item is None or item["tipo"] != "ferramenta_script":
            raise FalhaDefinitiva(f"item {item_id} não é uma ferramenta de script deste inquilino")
        cur.execute("SELECT corpo FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s",
                    (item_id, versao))
        retrato = cur.fetchone()
    if retrato is None:
        raise FalhaDefinitiva(f"versão {versao} da ferramenta {item_id} não existe")
    dados = (retrato["corpo"] or {}).get("dados") or {}
    codigo = dados.get("codigo")
    if not isinstance(codigo, str) or not codigo:
        raise FalhaDefinitiva(f"retrato da versão {versao} sem código")
    return codigo


def _entradas_resolvidas(ctx, cab: dict, parametros: dict) -> dict:
    """Para parâmetro tipo `item`, confere que o item existe neste inquilino e anexa a ficha ao
    entradas.json (o script lê o conteúdo pelo SDK com o token do contêiner)."""
    fichas = {}
    por_nome = {p["nome"]: p for p in cab["parametros"]}
    for nome, valor in parametros.items():
        if por_nome.get(nome, {}).get("tipo") != "item":
            continue
        with ctx.db() as cur:
            cur.execute("SELECT id, titulo, tipo FROM plat.item WHERE id = %s::uuid", (valor,))
            linha = cur.fetchone()
        if linha is None:
            raise FalhaDefinitiva(f"item de entrada {nome!r} ({valor}) não existe mais neste inquilino")
        fichas[nome] = {"item_id": str(linha["id"]), "titulo": linha["titulo"], "tipo": linha["tipo"]}
    return fichas


def _copiar(nome: str, diretorio: str, caminho_local: str, caminho_remoto: str) -> None:
    """Copia um arquivo do host para o contêiner (docker exec cat). Fora de ctx.db(): docker CLI."""
    with open(caminho_local, "rb") as arq:
        copiado = subprocess.run(
            ["docker", "exec", "-i", nome, "sh", "-c", f"mkdir -p {diretorio} && cat > {caminho_remoto}"],
            input=arq.read(), capture_output=True, timeout=120)
    if copiado.returncode != 0:
        raise FalhaDefinitiva(f"não consegui escrever {caminho_remoto} no contêiner: "
                              + copiado.stderr.decode(errors="replace")[-300:])


def _copiar_sdk(nome: str, diretorio: str) -> None:
    """Copia o pacote do SDK DESTE COMMIT para o contêiner (o interpretador roda com o SDK
    carimbado pela execução, não com o que a imagem instalou quando foi construída). O tar
    extrai `plat/` DENTRO do diretório do script: sys.path[0] é o diretório do script, então
    a cópia da execução vence o SDK velho do site-packages da imagem."""
    pacote = RAIZ / "pacote"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        tar.add(pacote / "plat", arcname="plat")
    copiado = subprocess.run(
        ["docker", "exec", "-i", nome, "sh", "-c",
         f"mkdir -p {diretorio} && tar -xf - -C {diretorio}"],
        input=buffer.getvalue(), capture_output=True, timeout=120)
    if copiado.returncode != 0:
        raise FalhaDefinitiva("não consegui copiar o SDK para o contêiner: "
                              + copiado.stderr.decode(errors="replace")[-300:])


@tarefa(
    nome="ferramentas.executar_script",
    descricao="Executa o script de uma ferramenta publicada no contêiner do inquilino e registra o resultado",
    parametros=ExecutarScriptParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=960,
    tentativas=1,
    perfil_minimo="editor",
    versao=1,
)
def ferramentas_executar_script(ctx, ferramenta_id: str, versao: int, sha256: str,
                                parametros: dict, timeout_s: int = 300) -> dict:
    codigo = _codigo_da_versao(ctx, ferramenta_id, versao)
    real = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    if real != sha256:
        raise FalhaDefinitiva("sha256 do texto da versão congelada não confere com o do pedido: "
                              "a execução recusa rodar texto de procedência duvidosa")
    cab = cabecalho.parse(codigo)
    valores = cabecalho.validar_valores(cab, parametros)  # 2ª cerca: o worker não confia na fila
    entradas = _entradas_resolvidas(ctx, cab, valores)

    if not ctx.usuario_id:
        raise FalhaDefinitiva("job de ferramenta sem usuário: o token do contêiner precisa de dono")
    with ctx.db() as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        linha = cur.fetchone()
    if linha is None:
        raise FalhaDefinitiva(f"inquilino {ctx.tenant_id} inexistente")
    slug = linha["slug"]

    ctx.progresso(10, "levantando contêiner do inquilino")
    subida = contenedor.levantar(slug, banco.Contexto(ctx.tenant_id, ctx.usuario_id, "worker"))
    nome = subida["contenedor"]
    diretorio = f"/home/jovyan/trabalho/ferramenta-{ctx.job_id}"
    remoto_script = f"{diretorio}/script.py"

    ctx.progresso(30, "copiando script, SDK e entradas")
    with tempfile.TemporaryDirectory() as tmp:
        caminho_script = str(Path(tmp) / "script.py")
        Path(caminho_script).write_text(codigo, encoding="utf-8")
        _copiar(nome, diretorio, caminho_script, remoto_script)
        caminho_entradas = str(Path(tmp) / "entradas.json")
        Path(caminho_entradas).write_text(
            json.dumps({"parametros": valores, "entradas": entradas}, ensure_ascii=False),
            encoding="utf-8")
        _copiar(nome, diretorio, caminho_entradas, f"{diretorio}/entradas.json")
    _copiar_sdk(nome, diretorio)

    ctx.progresso(50, f"executando script (teto {timeout_s} s)")
    # o timeout roda DENTRO do contêiner (coreutils): o python do laço infinito morre lá, não
    # só o cliente docker exec; o teto do subprocesso é a rede de segurança do cliente
    try:
        rodado = subprocess.run(
            ["docker", "exec", nome, "sh", "-c",
             f"cd {diretorio} && timeout -k 5 {timeout_s}s python3 script.py"],
            capture_output=True, timeout=timeout_s + 60,
        )
    except subprocess.TimeoutExpired as e:
        raise FalhaDefinitiva(f"execução do script passou de {timeout_s} s") from e
    if rodado.returncode == 124:
        # convenção do coreutils `timeout`: 124 = foi o TETO do comando que matou o script
        raise FalhaDefinitiva(f"execução do script passou de {timeout_s} s (código 124 do teto)")
    if rodado.returncode != 0:
        cauda = (rodado.stderr or rodado.stdout).decode(errors="replace")[-500:]
        raise FalhaDefinitiva(f"script terminou com erro (código {rodado.returncode}): {cauda}")

    ctx.progresso(80, "lendo a saída declarada")
    lido = subprocess.run(["docker", "exec", nome, "cat", f"{diretorio}/saida.json"],
                          capture_output=True, timeout=60)
    if lido.returncode != 0:
        raise FalhaDefinitiva("script terminou sem erro mas não declarou saída nenhuma "
                              "(plat.saidas.gravar nunca foi chamado)")
    if len(lido.stdout) > TAM_MAX_SAIDA:
        raise FalhaDefinitiva(f"saída acima do teto de {TAM_MAX_SAIDA} bytes")
    try:
        saida = json.loads(lido.stdout)
    except ValueError as e:
        raise FalhaDefinitiva(f"saida.json não é JSON válido: {e}") from None
    if not isinstance(saida, dict) or not saida:
        raise FalhaDefinitiva("saida.json tem de ser um objeto com as saídas declaradas")
    declaradas = {s["nome"] for s in cab["saidas"]}
    estranhas = sorted(set(saida) - declaradas)
    if estranhas:
        raise FalhaDefinitiva(f"saída fora do declarado no cabeçalho: {', '.join(estranhas)}")

    ctx.progresso(90, "gravando item de resultado")
    novo_id = str(modulo_uuid.uuid4())
    titulo = f"{cab['titulo']} — execução {str(ctx.job_id)[:8]}"
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'ferramenta_resultado', %s, %s, %s, %s, %s)",
            [
                novo_id, ctx.tenant_id, titulo[:250], ctx.usuario_id,
                psycopg2.extras.Json({
                    "ferramenta": f"script:{cab['nome']}",
                    "parametros": {**valores, "entradas": entradas},
                    "resultado": saida,
                    "job_id": str(ctx.job_id),
                    "procedencia": {
                        "origem": "script",
                        "ferramenta_id": ferramenta_id,
                        "ferramenta": f"script:{cab['nome']}",
                        "titulo": cab["titulo"],
                        "versao": versao,
                        "sha256_script": real,
                        "sdk": "pacote copiado da casa no momento da execução",
                    },
                }, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str)),
                ctx.usuario_id, ctx.usuario_id,
            ],
        )
        cur.execute("SELECT plat.evento_registrar('ferramentas/script-executado', 'item', %s, "
                    "%s::jsonb, NULL, NULL)",
                    (novo_id, json.dumps({"ferramenta_id": ferramenta_id, "versao": versao,
                                          "sha256_script": real, "job_id": str(ctx.job_id),
                                          "saidas": sorted(saida)})))

    # limpeza do diretório de execução: melhor esforço, o volume é efêmero na ceifa de qualquer forma
    subprocess.run(["docker", "exec", nome, "rm", "-rf", diretorio], capture_output=True, timeout=60)
    return {"item_id": novo_id, "saidas": sorted(saida), "contenedor": nome, "versao": versao,
            "sha256_script": real}
