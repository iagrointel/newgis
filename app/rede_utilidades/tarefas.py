"""Job `rede.importar_bdgd` (item L4-01-c-importador-bdgd): importa um pacote BDGD da ANEEL
(`.gdb.zip` ou pasta `.gdb`) para uma rede de utilidades do inquilino, com barra de progresso,
contrato de dado ANTES da carga e contagem conferida contra o arquivo DEPOIS.

Ordem dentro do job:
1. valida o caminho (só dentro de `PLAT_BDGD_RAIZ`; nada de arquivo arbitrário do servidor);
2. extrai o zip para o diretório de trabalho do job (apagado pelo worker no fim);
3. lê as camadas do contrato e avalia as expectativas do YAML da casa — o relatório vai para a
   auditoria mesmo que a carga falhe depois;
4. `bdgd.importar` com `ctx.progresso` (5 % .. 98 %), contagem por camada, unidade do COMP, órfãos;
5. grava tudo em `plat.rede_importacao` e devolve o resumo.

⛔ D21 (disco): o job NÃO baixa pacote da ANEEL. Importação "pelo nome da distribuidora" fica
registrada como pendente de decisão do dono — o parâmetro é sempre um caminho local já existente.

Este módulo também abriga o job `redes.subredes_atualizar`
(item L4-04-b-atualizar-e-exportar-subrede): as duas trilhas nomearam o mesmo arquivo, e as
tarefas de rede de utilidades ficam juntas aqui. O trabalho em si é `subredes.atualizar_todas` —
o MESMO caminho da rota síncrona de uma subrede só; o job é apenas o transporte, porque numa rede
de cooperativa a atualização percorre dezenas de milhares de elementos por subrede e não cabe
numa requisição HTTP.

E abriga o job `redes.analisar_alimentador` (item L4-07-fluxo-de-potencia): o fluxo de
potência de um ou de todos os alimentadores da rede, um de cada vez. O motor OpenDSS é global
ao processo, e a varredura de 864 pontos de uma cooperativa inteira não cabe numa requisição
HTTP — por isso o caminho pesado é job, no processo próprio do worker.
"""

from __future__ import annotations

import re
import uuid
import zipfile
from pathlib import Path

import pyogrio
from pydantic import BaseModel, Field

from app import settings as cfg
from app.erros import ErroAPI
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.rede_utilidades import bdgd, contrato, subredes


class ImportarBdgdParametros(BaseModel):
    rede_id: uuid.UUID
    caminho: str = Field(
        min_length=1, max_length=1024, description="pacote .gdb.zip ou pasta .gdb, dentro de PLAT_BDGD_RAIZ"
    )
    seguir_com_bloqueio: bool = Field(
        default=True,
        description="com expectativa 'bloqueia' em falha, ainda assim carrega a topologia (o relatório fica gravado); "
        "False aborta antes da carga",
    )


def _raiz_permitida() -> Path:
    raiz = cfg.obter().PLAT_BDGD_RAIZ
    if not raiz:
        raise FalhaDefinitiva(
            "PLAT_BDGD_RAIZ não configurada: a importação por caminho local fica desligada nesta instalação "
            "(pendente de D21 — o pacote da ANEEL não é baixado pelo job)"
        )
    return Path(raiz).resolve()


def _resolver_caminho(caminho: str) -> Path:
    raiz = _raiz_permitida()
    p = (raiz / caminho).resolve() if not Path(caminho).is_absolute() else Path(caminho).resolve()
    if raiz != p and raiz not in p.parents:
        raise FalhaDefinitiva(f"caminho fora de PLAT_BDGD_RAIZ ({raiz}): recusado")
    if not p.exists():
        raise FalhaDefinitiva(f"pacote não encontrado: {p}")
    return p


def _extrair_se_zip(p: Path, dir_trabalho: Path) -> Path:
    """Devolve a pasta .gdb pronta para o GDAL: a própria `p` quando já é pasta, ou a extraída."""
    if p.is_dir():
        return p
    if p.suffix.lower() != ".zip" and not p.name.lower().endswith(".gdb.zip"):
        raise FalhaDefinitiva("o pacote tem de ser uma pasta .gdb ou um .gdb.zip")
    destino = dir_trabalho / "bdgd"
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p) as z:
        raizes = sorted({n.split("/")[0] for n in z.namelist() if n.lower().split("/")[0].endswith(".gdb")})
        if not raizes:
            raise FalhaDefinitiva(f"{p.name} não contém uma pasta .gdb")
        # defesa contra caminho que escapa da pasta de destino (zip malicioso)
        for n in z.namelist():
            alvo = (destino / n).resolve()
            if destino.resolve() not in alvo.parents and alvo != destino.resolve():
                raise FalhaDefinitiva("zip com caminho fora da pasta de destino: recusado")
        z.extractall(destino)
    return destino / raizes[0]


def _ano_da_safra(p: Path) -> int | None:
    m = re.search(r"(20\d{2})", p.name)
    return int(m.group(1)) if m else None


def _ler_camadas_do_contrato(gdb: Path, progresso) -> dict:
    camadas = {}
    for i, nome in enumerate(contrato.CAMADAS_DO_CONTRATO):
        try:
            geometria = nome in ("PONNOT",)
            camadas[nome] = pyogrio.read_dataframe(str(gdb), layer=nome, read_geometry=geometria)
        except Exception:
            continue  # camada ausente no GDB: o contrato marca as expectativas dela como não avaliadas
        progresso(2 + int(6 * (i + 1) / len(contrato.CAMADAS_DO_CONTRATO)), f"contrato: lendo {nome}")
    return camadas


@tarefa(
    nome="rede.importar_bdgd",
    descricao="Importa um pacote BDGD (ANEEL) para a rede: contrato de dado, carga com contagem conferida, "
    "unidade do COMP e órfãos",
    parametros=ImportarBdgdParametros,
    pesado=True,
    # teto PLAT_WORKER_MEMORIA_MB; a maior camada cabe (medido na distribuidora de referência:
    # menos de 100 mil linhas)
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"rede-bdgd:{p.get('rede_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def rede_importar_bdgd(ctx, rede_id: uuid.UUID, caminho: str, seguir_com_bloqueio: bool = True) -> dict:
    p = _resolver_caminho(caminho)
    ctx.progresso(1, f"pacote: {p.name}")
    gdb = _extrair_se_zip(p, Path(ctx.dir_trabalho))
    safra = _ano_da_safra(p)

    with ctx.db() as cur:
        cur.execute("SELECT id FROM plat.rede WHERE id = %s::uuid", (str(rede_id),))
        if cur.fetchone() is None:
            raise FalhaDefinitiva("rede inexistente ou de outro inquilino")

    camadas = _ler_camadas_do_contrato(gdb, ctx.progresso)
    ctx.progresso(9, "contrato: avaliando expectativas")
    relatorio = contrato.avaliar_contrato(camadas, safra_ano=safra)
    del camadas
    ctx.log(
        "info",
        f"contrato: {relatorio['avaliadas']}/{relatorio['total']} avaliadas, "
        f"{relatorio['bloqueia_falhas']} 'bloqueia' em falha",
    )
    if relatorio["bloqueia_falhas"] and not seguir_com_bloqueio:
        # ainda assim deixa rastro: auditoria só do contrato, sem carga
        with ctx.db() as cur:
            imp = bdgd._Importador(cur, ctx.tenant_id, str(rede_id), str(gdb), None, True)
            imp._abrir_auditoria(bdgd.inspecionar(gdb))
            imp.gravar_contrato(relatorio)
            imp._fechar_auditoria(
                None, f"{relatorio['bloqueia_falhas']} expectativa(s) 'bloqueia' em falha; carga não iniciada"
            )
        raise FalhaDefinitiva(f"contrato de dado: {relatorio['bloqueia_falhas']} expectativa(s) 'bloqueia' em falha")

    def progresso(pct, msg):
        ctx.progresso(10 + int(pct * 0.88), msg)

    with ctx.db() as cur:
        resultado = bdgd.importar(cur, ctx.tenant_id, str(rede_id), str(gdb), progresso=progresso, registrar=True)
        if resultado.get("importacao_id"):
            cur.execute(
                "UPDATE plat.rede_importacao SET contrato = %s, job_id = %s::uuid, atualizado_em = now() "
                "WHERE id = %s::uuid",
                (bdgd.Json(relatorio), str(ctx.job_id), resultado["importacao_id"]),
            )
    ctx.progresso(100, "importação concluída")
    return {
        "importacao_id": resultado["importacao_id"],
        "conferido": resultado["conferido"],
        "contagens": resultado["contagens"],
        "comp": resultado["comp"],
        "orfaos": {k: v["quantidade"] for k, v in resultado["orfaos"].items()},
        "desvios": {k: v["quantidade"] for k, v in resultado["desvios"].items()},
        "contrato": {
            "avaliadas": relatorio["avaliadas"],
            "total": relatorio["total"],
            "bloqueia_falhas": relatorio["bloqueia_falhas"],
            "resumo": relatorio["resumo"],
        },
        "duracao_ms": resultado["duracao_ms"],
    }


class AtualizarSubredesParametros(BaseModel):
    rede_id: str = Field(min_length=36, max_length=36)
    # `todas=False` (padrão) é a atualização INCREMENTAL: só as subredes sujas, inclusive as que a área suja
    # da última edição tocou. `todas=True` refaz a rede inteira (primeira carga, ou desconfiança do índice).
    todas: bool = False
    # `tier` restringe o lote a um tier da rede (código do pacote); vazio = todos.
    tier: str | None = Field(default=None, max_length=63)


@tarefa(
    nome="redes.subredes_atualizar",
    descricao="Atualiza as subredes sujas de uma rede de utilidades (traçado, nome nos elementos, "
              "propagação, linha agregada)",
    parametros=AtualizarSubredesParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"redes_subredes_atualizar:{p['rede_id']}",
    perfil_minimo="editor",
)
def redes_subredes_atualizar(ctx, rede_id: str, todas: bool = False, tier: str | None = None) -> dict:
    with ctx.db() as cur:
        return subredes.atualizar_todas(cur, ctx.tenant_id, rede_id, todas=todas, tier=tier,
                                        progresso=ctx.progresso)


class AnalisarAlimentadorParametros(BaseModel):
    """Parâmetros do job `redes.analisar_alimentador` (item L4-07-fluxo-de-potencia).

    `subredes` vazio = cada um dos alimentadores do tier escolhido que já foram atualizados. É assim que a
    cooperativa inteira é analisada: um alimentador de cada vez, com o resultado de cada um gravado assim
    que sai — a análise de 16 alimentadores que morre no décimo deixa nove resultados no banco, não zero.
    O importador BDGD já mostrou que trabalhar por alimentador é a única forma que fecha nesta base."""

    rede_id: str = Field(min_length=36, max_length=36)
    subredes: list[str] = Field(default_factory=list, max_length=500)
    tier: str = Field(default="media_tensao", max_length=63)
    # o alimentador inteiro inclui o que pende do transformador (o tier de baixa tensão)
    jusante: bool = False
    parametros: dict = Field(default_factory=dict)


@tarefa(
    nome="redes.analisar_alimentador",
    descricao="Fluxo de potência (OpenDSS) de um ou de todos os alimentadores de uma rede de utilidades, "
              "com convergência por alimentador e agregação que exclui quem não convergiu",
    parametros=AnalisarAlimentadorParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=7200,
    tentativas=1,
    chave=lambda p: f"redes_analisar_alimentador:{p['rede_id']}",
    perfil_minimo="editor",
)
def redes_analisar_alimentador(ctx, rede_id: str, subredes: list[str] | None = None,
                               tier: str = "media_tensao", jusante: bool = False,
                               parametros: dict | None = None) -> dict:
    """Um alimentador de cada vez. O que falhar (dado que não permite montar o modelo, circuito que não
    compila) entra em `recusados` com o motivo e NÃO derruba o lote; o que não convergir entra no resultado
    marcado e fica FORA da agregação, nomeado em `alimentadores_fora_por_nao_convergencia`."""
    from app.rede_utilidades import fluxo_potencia

    # valida os parâmetros UMA vez, antes de tocar em alimentador nenhum: pedido malformado tem de falhar
    # no primeiro segundo, não no décimo alimentador.
    try:
        fluxo_potencia.validar_parametros(parametros)
    except fluxo_potencia.ErroFluxo as e:
        raise FalhaDefinitiva(f"{e.codigo}: {e.mensagem}") from e

    with ctx.db() as cur:
        nomes = list(subredes or [])
        if not nomes:
            cur.execute(
                "SELECT s.nome FROM plat.rede_subrede s JOIN plat.rede_tier t ON t.id = s.tier_id "
                "WHERE s.rede_id = %s::uuid AND t.codigo = %s AND s.atualizado_em IS NOT NULL "
                "ORDER BY s.nome", (rede_id, tier))
            nomes = [r["nome"] for r in cur.fetchall()]
    if not nomes:
        raise FalhaDefinitiva(
            f"a rede não tem alimentador atualizado no tier '{tier}': atualize as subredes antes de analisar")

    feitos: list[dict] = []
    recusados: list[dict] = []
    for i, nome in enumerate(nomes):
        ctx.progresso(int(100 * i / len(nomes)), f"alimentador {nome} ({i + 1} de {len(nomes)})")
        try:
            with ctx.db() as cur:
                saida = fluxo_potencia.calcular_e_gravar(cur, ctx.tenant_id, rede_id, nome, parametros,
                                                         tier, jusante)
        except fluxo_potencia.ErroFluxo as e:
            recusados.append({"subrede": nome, "codigo": e.codigo, "mensagem": e.mensagem})
            continue
        except ErroAPI as e:
            # em ErroAPI o código curto chama-se `erro` (app/erros.py), não `codigo` como em ErroFluxo
            recusados.append({"subrede": nome, "codigo": e.erro, "mensagem": e.mensagem})
            continue
        feitos.append(saida)

    ctx.progresso(100, "análise concluída")
    return {
        "alimentadores_pedidos": len(nomes),
        "analisados": [{"subrede": f["subrede"], "convergiu": f["convergiu"],
                        "pontos": f["convergencia"]["pontos"],
                        "pontos_sem_convergencia": f["convergencia"]["pontos_sem_convergencia"],
                        "ponto_critico": f["ponto_critico"], "energia": f["energia"],
                        "resumo": f["resumo"], "elementos": f["elementos"],
                        "duracao_ms": f["duracao_ms"], "pico_ram_mb": f["pico_ram_mb"]}
                       for f in feitos],
        "recusados": recusados,
        "agregado": fluxo_potencia.agregar(feitos),
        "pico_ram_mb": max((f["pico_ram_mb"] for f in feitos), default=None),
    }
