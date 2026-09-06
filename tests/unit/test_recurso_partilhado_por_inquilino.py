"""TRAVA de classe: todo RECURSO PARTILHADO da plataforma tem de ter dimensão de inquilino.

Em 06/09/2026 cinco adversários independentes atacaram cinco grupos diferentes e escreveram o mesmo
veredito (laudos `laco/handoffs/T3/ataque-g2|g3|g4|g6-ADVERSARIO.md`): o que é POR LINHA está protegido
— segurança de linha, filtro de dono, contexto por inquilino aguentaram o ataque —, e o que é RECURSO
PARTILHADO não tinha dimensão de inquilino nenhuma: a fila, a chave do trinco, o schema de dado, o
contador de cota e o orçamento de conexões.

Este arquivo varre esses cinco pontos e reprova quando UM deles perde a dimensão de inquilino. Não é
teste de item: é a trava que impede a classe de voltar na próxima leva. Quem acrescentar um recurso
partilhado novo (um contador em memória, um nome de objeto derivado, uma fila, um orçamento)
acrescenta uma linha em PONTOS aqui.

Tudo é conferido na FONTE (migrações e módulos), sem banco e sem servidor: a trava roda em qualquer
máquina, inclusive antes de a migração ser aplicada."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import limites, migracoes

RAIZ = Path(__file__).resolve().parents[2]
MIGRACOES = RAIZ / "db" / "migracoes"


def corpo_da_funcao(nome: str) -> str:
    """Última definição de `plat.<nome>` no corpo das migrações, na ordem de aplicação — que é a
    definição que vale no banco depois de aplicar tudo."""
    achado = ""
    abre = re.compile(rf"CREATE OR REPLACE FUNCTION plat\.{re.escape(nome)}\b")
    for m in migracoes.listar(MIGRACOES):
        texto = (MIGRACOES / f"{m}.sql").read_text(encoding="utf-8")
        for casamento in abre.finditer(texto):
            fim = texto.find("\n$$;", casamento.start())
            if fim == -1:  # função construída por EXECUTE format dentro de um bloco DO
                fim = texto.find("$fn$ $f$", casamento.start())
            achado = texto[casamento.start(): fim if fim != -1 else len(texto)]
    return achado


def sem_comentario(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in sql.splitlines())


# ---------------------------------------------------------------- os cinco pontos
def chave_do_trinco() -> tuple[bool, str]:
    """O trinco (`job.chave`) protege um recurso DO INQUILINO; a chave tem de ser comparada junto com o
    inquilino, senão um inquilino congela o trabalho de outro (medido: laudo g3, L0-05-a achado 2)."""
    corpo = sem_comentario(corpo_da_funcao("job_pegar"))
    if not corpo:
        return False, "plat.job_pegar não foi encontrada nas migrações"
    m = re.search(r"NOT EXISTS\s*\(\s*SELECT 1 FROM plat\.job r(.*?)\)\)", corpo, re.S)
    if m is None:
        return False, "a subconsulta do trinco por chave sumiu de plat.job_pegar"
    trecho = " ".join(m.group(1).split())
    if "r.tenant_id" not in trecho:
        return False, f"o trinco por chave não olha o inquilino: {trecho}"
    return True, trecho


def nome_do_schema_de_dado() -> tuple[bool, str]:
    """O schema físico do inquilino tem de carregar o prefixo da INSTALAÇÃO. Sem ele, produção,
    homologação e as trilhas do laço escrevem todas em `d_<slug>` e a segunda instalação não importa
    nada (medido: laudo g3, L0-04-c achado 1, `permission denied for schema d_demo`)."""
    corpo = corpo_da_funcao("camada_schema_garantir")
    if not corpo:
        return False, "plat.camada_schema_garantir não foi encontrada nas migrações"
    if "camada_schema_prefixo" not in corpo and "%L || p_slug" not in corpo:
        return False, "o nome do schema de dado não passa por um prefixo de instalação"
    if re.search(r"'d_'\s*\|\|\s*p_slug", corpo):
        return False, "plat.camada_schema_garantir ainda monta o schema como 'd_' || slug"
    fonte = (RAIZ / "app" / "ingestao" / "carregar.py").read_text(encoding="utf-8")
    if re.search(r'f"d_\{', fonte):
        return False, "app/ingestao/carregar.py ainda monta o schema como d_<slug> no código"
    return True, "prefixo de instalação em plat.camada_schema_prefixo()"


def contador_de_cota() -> tuple[bool, str]:
    """`plat.tenant.uso_bytes` é o contador de cota do inquilino. Ele só subia: a soma vivia no código
    de carga e não havia caminho de devolução (medido: 188.416 -> 376.832 -> 376.832 depois de apagar e
    expurgar). Quem soma tem de ser o mesmo que devolve — um gatilho simétrico em plat.item."""
    corpo = corpo_da_funcao("item_uso_bytes")
    if not corpo:
        return False, "não existe função de contabilidade de uso_bytes nas migrações"
    if "uso_bytes - antes + depois" not in " ".join(corpo.split()):
        return False, "a contabilidade de uso_bytes não é simétrica (soma e devolve na mesma conta)"
    gatilho = any(
        "CREATE TRIGGER item_uso_bytes" in (MIGRACOES / f"{m}.sql").read_text(encoding="utf-8")
        and "AFTER INSERT OR DELETE" in (MIGRACOES / f"{m}.sql").read_text(encoding="utf-8")
        for m in migracoes.listar(MIGRACOES))
    if not gatilho:
        return False, "o gatilho item_uso_bytes não cobre INSERT e DELETE"
    for py in (RAIZ / "app").rglob("*.py"):
        if re.search(r"uso_bytes\s*=\s*uso_bytes\s*\+", py.read_text(encoding="utf-8")):
            return False, f"{py.relative_to(RAIZ)} soma uso_bytes fora do gatilho (volta a só subir)"
    return True, "gatilho plat.item_uso_bytes, simétrico, sem soma manual no código"


def justica_da_fila() -> tuple[bool, str]:
    """A fila é um recurso partilhado por todos os inquilinos. Ordenar só por (prioridade, data) é
    global e a prioridade 1..9 é livre a qualquer usuário: quem chegou primeiro foi servido em 21º
    (medido: laudo g3, L0-05-a achado 3). A escolha tem de repartir por inquilino primeiro."""
    corpo = sem_comentario(corpo_da_funcao("job_pegar"))
    if not corpo:
        return False, "plat.job_pegar não foi encontrada nas migrações"
    if "GROUP BY j.tenant_id" not in corpo:
        return False, "plat.job_pegar não reparte a escolha por inquilino (sem GROUP BY j.tenant_id)"
    if "j.tenant_id = t.tenant_id" not in corpo:
        return False, "a escolha do trabalho não está presa ao inquilino escolhido na repartição"
    return True, "repartição por inquilino antes da prioridade de dentro do inquilino"


def orcamento_de_conexoes() -> tuple[bool, str]:
    """O orçamento de conexões de eventos (SSE) é da máquina. Sem teto por inquilino, um inquilino
    consome tudo; e um teto guardado em memória de processo vale N vezes quando a unidade sobe
    `--workers N` (medido: laudo g3, L0-05-b achado 1)."""
    from app.jobs import eventos

    fonte = (RAIZ / "app" / "jobs" / "eventos.py").read_text(encoding="utf-8")
    if "_por_inquilino" not in fonte:
        return False, "app/jobs/eventos.py não tem contador de conexões por inquilino"
    if not hasattr(eventos, "POR_INQUILINO_MAX") or not hasattr(eventos, "TOTAL_MAX"):
        return False, "faltam os tetos POR_INQUILINO_MAX/TOTAL_MAX no orçamento de eventos"
    unidade = (RAIZ / "deploy" / "plat-api.service").read_text(encoding="utf-8")
    m = re.search(r"--workers\s+(\d+)", unidade)
    processos = int(m.group(1)) if m else 1
    for rotulo, teto in (("usuário", eventos.POR_USUARIO_MAX), ("inquilino", eventos.POR_INQUILINO_MAX),
                         ("instalação", eventos.TOTAL_MAX)):
        efetivo = eventos.cota_por_processo(teto) * processos
        if efetivo > teto:
            return False, (f"teto por {rotulo}: publicado {teto}, real {efetivo} "
                           f"({eventos.cota_por_processo(teto)} por processo × {processos} processos)")
    return True, f"tetos {eventos.POR_USUARIO_MAX}/{eventos.POR_INQUILINO_MAX}/{eventos.TOTAL_MAX}, {processos} processos"


PONTOS = {
    "chave de trinco": chave_do_trinco,
    "nome de schema de dado": nome_do_schema_de_dado,
    "contador de cota": contador_de_cota,
    "fila de trabalhos": justica_da_fila,
    "orçamento de conexões de eventos": orcamento_de_conexoes,
}


@pytest.mark.parametrize("ponto", sorted(PONTOS))
def test_recurso_partilhado_tem_dimensao_de_inquilino(ponto):
    ok, detalhe = PONTOS[ponto]()
    assert ok, f"recurso partilhado sem dimensão de inquilino — {ponto}: {detalhe}"


def test_a_varredura_cobre_os_cinco_pontos_do_laudo():
    """A lista não pode encolher em silêncio: o laudo nomeia cinco pontos e os cinco são varridos."""
    assert len(PONTOS) >= 5, f"a varredura de recurso partilhado encolheu para {len(PONTOS)} pontos"


def test_chave_de_periodico_da_plataforma_esta_no_espaco_reservado():
    """Segunda camada do ponto 1: as chaves dos periódicos da plataforma eram constantes de código, e
    qualquer usuário com perfil de editor podia ocupá-las (laudo g3, L0-05-d). Agora vivem no espaço de
    nome reservado, que o gatilho plat.job_chave_reservada recusa a inquilino comum fora de agenda."""
    from app.jobs import periodicos

    fonte = (RAIZ / "app" / "jobs" / "periodicos.py").read_text(encoding="utf-8")
    constantes = re.findall(r'chave=lambda p: (?:f)?"([^"{]*)"', fonte)
    assert not constantes, (f"periódico da plataforma com chave constante fora do espaço reservado "
                            f"{limites.CHAVE_RESERVADA!r}: {constantes}")
    assert periodicos.PERIODICOS, "a lista de periódicos da plataforma ficou vazia"
    corpo = corpo_da_funcao("job_chave_reservada")
    assert limites.CHAVE_RESERVADA in corpo, (
        f"o gatilho que reserva o espaço {limites.CHAVE_RESERVADA!r} sumiu das migrações")


def test_morte_do_executor_consome_tentativa_e_nao_reinicio():
    """Contrato do L0-05-a que veio junto: três mortes seguidas do executor terminavam em `concluido`
    porque a ceifa devolvia sem consumir tentativa e o teto de reinícios é cinco. A ceifa passa a
    devolver com p_conta_tentativa := true; `reinicios` fica para a parada limpa do worker."""
    corpo = sem_comentario(corpo_da_funcao("job_ceifar"))
    assert corpo, "plat.job_ceifar não foi encontrada nas migrações"
    m = re.search(r"plat\.job_devolver\((.*?)\)", " ".join(corpo.split()))
    assert m, "plat.job_ceifar não chama plat.job_devolver"
    assert ", true," in m.group(1), f"a ceifa devolve sem consumir tentativa: job_devolver({m.group(1)})"
    fonte = (RAIZ / "app" / "jobs" / "worker.py").read_text(encoding="utf-8")
    assert "'worker reiniciado', false" in fonte, (
        "a parada limpa do worker deixou de contar reinício (e passaria a gastar tentativa do trabalho)")


def test_a_api_ceifa_quando_nenhum_executor_esta_vivo():
    """Sem executor vivo ninguém ceifava: `plat.job_ceifar` só era chamada de dentro do laço do worker e
    só plat_worker tinha EXECUTE (medido: 68 s depois do SIGKILL o trabalho seguia `rodando`)."""
    corpo = corpo_da_funcao("job_ceifar_vencidos")
    assert corpo, "não existe ceifa chamável pela API"
    assert "plat.tenant_atual()" in corpo, "a ceifa da API não se limita ao inquilino do contexto"
    concedido = any(
        "GRANT EXECUTE ON FUNCTION plat.job_ceifar_vencidos" in (MIGRACOES / f"{m}.sql").read_text(encoding="utf-8")
        for m in migracoes.listar(MIGRACOES))
    assert concedido, "plat_app não tem EXECUTE na ceifa da API"
    fonte = (RAIZ / "app" / "jobs" / "servico.py").read_text(encoding="utf-8")
    assert "ceifar_vencidos" in fonte, "a leitura da fila não ceifa o que ficou sem executor"


def test_rastro_de_erro_do_trabalho_e_saneado():
    """Portão do L0-05-a: o trabalho termina com o rastro SANEADO. A interface devolvia o caminho do
    servidor a quem tem `jobs.ver`."""
    from app.jobs.sanear import RAIZ_APP, sanear

    rastro = (f'Traceback (most recent call last):\n  File "{RAIZ_APP}/app/ingestao/carregar.py", line 10, '
              'in carregar\n    raise RuntimeError("x")\nRuntimeError: x')
    limpo = sanear(rastro)
    assert RAIZ_APP not in limpo, f"o saneador deixou o caminho do servidor passar: {limpo}"
    assert "carregar.py" in limpo and "line 10" in limpo, f"o saneador comeu o que serve para depurar: {limpo}"
    assert "<credencial>@" in sanear("postgresql://plat_app:segredo@127.0.0.1:5432/base")
    fonte = (RAIZ / "app" / "jobs" / "filho.py").read_text(encoding="utf-8")
    assert "sanear(" in fonte, "app/jobs/filho.py voltou a gravar o rastro cru"
