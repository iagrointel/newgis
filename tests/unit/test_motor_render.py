"""Motor de render no servidor (item L2-12-a-motor-render-servidor): pool de páginas do chromium do
playwright, fila com limite, teto de tempo, isolamento de rede — medido contra um `uvicorn app.main:app` REAL
(tests/render_apoio.py), nunca o transporte ASGI em processo (o playwright não alcança isso).

Marcado `lento`: sobe chromium de verdade. Roda isolado (`pytest tests/unit/test_motor_render.py`), nunca
dentro da suíte inteira — cada teste aqui tem seu próprio Motor (pool de 2), fechado ao fim.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image
from playwright.async_api import Error as ErroPlaywright

from app.render.motor import ErroFilaCheia, ErroRenderTimeout, Motor
from tests.render_apoio import (
    derrubar_servidor,
    memoria_max_do_cgroup,
    memoria_pico_do_cgroup,
    rss_dos_descendentes,
    subir_servidor,
)

pytestmark = pytest.mark.lento

ITEM = "L2-12-a-motor-render-servidor"
MEDIDAS = None  # preenchido por test_medidas_completo ao fim; ver tests/medidas/L2-12-a-motor-render-servidor.json


@pytest.fixture(scope="module")
def servidor():
    proc, base_url = subir_servidor()
    yield base_url
    derrubar_servidor(proc)


def url_demo(base_url: str, **q) -> str:
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    return f"{base_url}/render/mapa" + (f"?{qs}" if qs else "")


@pytest.fixture
def motor_novo():
    """Devolve um `Motor` ainda NÃO iniciado. `iniciar()`/`parar()` criam objetos do asyncio (Queue,
    Semaphore, Lock) e do playwright que ficam PRESOS ao event loop onde nasceram — um `asyncio.run()` na
    fixture e outro no corpo do teste seriam DOIS loops diferentes, e o segundo uso rejeita os objetos do
    primeiro (achado real, não hipotético: era exatamente isso que travava o teste antes deste comentário
    existir). Por isso cada teste chama `iniciar()`/`renderizar()`/`parar()` dentro do MESMO `asyncio.run()`."""
    return Motor(tamanho_pool=2, fila_max=10, timeout_s=30)


def test_png_tem_o_tamanho_pedido(servidor, motor_novo):
    async def cenario():
        await motor_novo.iniciar()
        try:
            return await motor_novo.renderizar(url_demo(servidor, zoom=13), largura=640, altura=480, formato="png")
        finally:
            await motor_novo.parar()

    dados, media = asyncio.run(cenario())
    assert media == "image/png"
    im = Image.open(io.BytesIO(dados))
    assert im.size == (640, 480)


def test_pdf_e_gerado(servidor, motor_novo):
    async def cenario():
        await motor_novo.iniciar()
        try:
            return await motor_novo.renderizar(url_demo(servidor, zoom=13), largura=800, altura=600, formato="pdf")
        finally:
            await motor_novo.parar()

    dados, media = asyncio.run(cenario())
    assert media == "application/pdf"
    assert dados[:4] == b"%PDF"
    assert len(dados) > 500


def test_png_300dpi_a4_e_gerado(servidor, motor_novo):
    """Cláusula do portão: "PNG a 300 DPI de A4 (2.480×3.508) gerado"."""

    async def cenario():
        await motor_novo.iniciar()
        try:
            return await motor_novo.renderizar(url_demo(servidor, zoom=13), largura=2480, altura=3508, dpi=300,
                                                 formato="png")
        finally:
            await motor_novo.parar()

    dados, media = asyncio.run(cenario())
    im = Image.open(io.BytesIO(dados))
    assert im.size == (2480, 3508)


def test_fila_recusa_acima_do_limite(servidor):
    """Motor com fila de tamanho 1 e pool de 1: o 3º pedido concorrente encontra fila cheia (2 já contados:
    1 em execução + 1 na fila) e recebe ErroFilaCheia, nunca um pedido sem fundo."""
    m = Motor(tamanho_pool=1, fila_max=2, timeout_s=30)

    async def cenario():
        await m.iniciar()
        try:
            tarefas = [
                asyncio.create_task(m.renderizar(url_demo(servidor, zoom=13), largura=400, altura=300))
                for _ in range(4)
            ]
            resultados = await asyncio.gather(*tarefas, return_exceptions=True)
            return resultados
        finally:
            await m.parar()

    resultados = asyncio.run(cenario())
    cheias = [r for r in resultados if isinstance(r, ErroFilaCheia)]
    ok = [r for r in resultados if not isinstance(r, Exception)]
    assert len(cheias) >= 1, resultados
    assert len(ok) >= 1


def test_pool_se_recupera_de_pagina_que_travou_no_meio(servidor):
    """Cláusula da refutação do item: "mata o processo do chromium no meio e confere recuperação do pool".
    Achado real (não hipotético — apareceu medindo o p95 sob carga): um `goto` que estoura o timeout deixa a
    MESMA página presa, e as navegações seguintes NAQUELA página falham também até alguém trocá-la. Este
    teste força esse travamento contra um socket que aceita a conexão e nunca responde (a requisição HTTP
    fica pendurada de propósito) e confere que o PRÓXIMO pedido, na mesma pool de tamanho 1, funciona —
    prova de que `Motor._pagina_de_reposicao` troca a página envenenada em vez de devolvê-la ao pool."""
    import socket as socket_mod
    import threading

    buraco_negro = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
    buraco_negro.bind(("127.0.0.1", 0))
    buraco_negro.listen(5)
    porta_bn = buraco_negro.getsockname()[1]
    parar = threading.Event()
    conexoes_abertas = []  # referência viva: sem isso o GC fecharia o socket e o cliente veria RST, não um pendurar

    def aceitar_e_nunca_responder():
        buraco_negro.settimeout(0.5)
        while not parar.is_set():
            try:
                conexao, _ = buraco_negro.accept()
                conexoes_abertas.append(conexao)  # aceita e NUNCA escreve nada de volta
            except socket_mod.timeout:
                continue

    fio = threading.Thread(target=aceitar_e_nunca_responder, daemon=True)
    fio.start()

    m = Motor(tamanho_pool=1, fila_max=5, timeout_s=10)

    async def cenario():
        await m.iniciar()
        try:
            with pytest.raises((ErroPlaywright, ErroRenderTimeout)):
                await m.renderizar(f"http://127.0.0.1:{porta_bn}/nunca-responde", largura=400, altura=300,
                                    espera_timeout_ms=1500)
            # a MESMA pool (tamanho 1) recebe um pedido de verdade logo depois: se a página não tivesse sido
            # trocada, este segundo `goto` herdaria a navegação pendurada e falharia também
            return await m.renderizar(url_demo(servidor, zoom=13), largura=400, altura=300)
        finally:
            await m.parar()
            parar.set()
            fio.join(timeout=2)
            for c in conexoes_abertas:
                c.close()
            buraco_negro.close()

    dados, media = asyncio.run(cenario())
    assert media == "image/png"
    assert len(dados) > 0


def test_20_pedidos_simultaneos_respeitam_o_pool_e_terminam_em_30s(servidor, medida):
    """Cláusula do portão, inteira: "20 pedidos simultâneos: fila respeita o limite e nenhum pedido passa de
    30 s nem derruba a API (RSS do pool <= MemoryMax)". Quatro coisas, medidas na MESMA rodada:

    1. **fila respeita o limite** — um observador amostra `stats.em_execucao` e `stats.fila_atual` enquanto
       os 20 pedidos correm: em execução nunca passa de `tamanho_pool` (senão o semáforo não vale nada) e a
       fila nunca passa de `fila_max`. E exige-se que a fila tenha de fato PASSADO do tamanho do pool em
       algum instante — sem isso o teste estaria provando enfileiramento num cenário que nunca enfileirou.
    2. **nenhum pedido passa de 30 s** — o tempo é medido POR PEDIDO (o teto do portão é por pedido, não do
       lote); o máximo individual é o número que vai ao laudo.
    3. **não derruba a API** — depois do lote, o mesmo servidor uvicorn responde 200 em `/render/mapa` e em
       `/api/render/saude`. Um pool que morre no meio derruba o servidor junto, e só uma chamada DEPOIS do
       lote distingue isso de "os 20 renders voltaram".
    4. **RSS do pool <= MemoryMax** — o teto NÃO é escolhido aqui: é o `memory.max` do cgroup em que
       `laco/roda_teste.sh` põe o pytest (`MemoryMax=${PLAT_TESTE_RSS:-4G}`, `MemorySwapMax=0`). Mede-se o
       pico do RSS somado de todos os descendentes deste processo (driver node + processos do chromium) e,
       junto, o `memory.peak` do cgroup inteiro — o primeiro é o pool, o segundo é o que o núcleo mataria.
    """
    m = Motor(tamanho_pool=2, fila_max=20, timeout_s=30)
    maximo_em_execucao = 0
    maximo_na_fila = 0
    pico_rss_pool = 0
    pico_n_processos = 0

    async def observar():
        nonlocal maximo_em_execucao, maximo_na_fila, pico_rss_pool, pico_n_processos
        passo = 0
        while True:
            maximo_em_execucao = max(maximo_em_execucao, m.stats.em_execucao)
            maximo_na_fila = max(maximo_na_fila, m.stats.fila_atual)
            if passo % 10 == 0:  # varrer /proc a cada ~0,2 s; a cada 20 ms custaria mais que o que se mede
                rss, n = rss_dos_descendentes()
                if rss > pico_rss_pool:
                    pico_rss_pool, pico_n_processos = rss, n
            passo += 1
            await asyncio.sleep(0.02)

    async def um_pedido():
        t0 = time.perf_counter()
        dados, media = await m.renderizar(url_demo(servidor, zoom=13), largura=1024, altura=768)
        return (time.perf_counter() - t0) * 1000, len(dados), media

    async def cenario():
        await m.iniciar()
        try:
            obs = asyncio.create_task(observar())
            inicio = time.perf_counter()
            tarefas = [asyncio.create_task(um_pedido()) for _ in range(20)]
            resultados = await asyncio.gather(*tarefas, return_exceptions=True)
            total_s = time.perf_counter() - inicio
            obs.cancel()
            return resultados, total_s
        finally:
            await m.parar()

    resultados, total_s = asyncio.run(cenario())
    falhas = [r for r in resultados if isinstance(r, Exception)]
    assert not falhas, falhas
    assert len(resultados) == 20
    tempos_ms = [round(r[0], 1) for r in resultados]
    assert all(r[2] == "image/png" and r[1] > 0 for r in resultados)
    pior_ms = max(tempos_ms)

    # a API continua de pé DEPOIS do lote (o servidor é o mesmo uvicorn que serviu as 20 páginas)
    pagina = httpx.get(f"{servidor}/render/mapa", timeout=10)
    saude = httpx.get(f"{servidor}/api/render/saude", timeout=10)

    teto_rss = memoria_max_do_cgroup()
    pico_cgroup = memoria_pico_do_cgroup()
    carga = [round(x, 2) for x in os.getloadavg()]
    laudo = {
        "pedidos": 20, "pool": m.tamanho_pool, "fila_max": m.fila_max,
        "tempos_ms": tempos_ms, "pior_pedido_ms": pior_ms, "lote_total_s": round(total_s, 1),
        "maximo_em_execucao": maximo_em_execucao, "maximo_na_fila": maximo_na_fila,
        "pico_rss_pool_mb": round(pico_rss_pool / 1048576, 1), "processos_no_pico": pico_n_processos,
        "memoria_max_cgroup_mb": None if teto_rss is None else round(teto_rss / 1048576, 1),
        "pico_cgroup_mb": None if pico_cgroup is None else round(pico_cgroup / 1048576, 1),
        "carga_1min": carga[0], "carga_5min": carga[1], "carga_15min": carga[2],
        "api_depois_render_mapa": pagina.status_code, "api_depois_saude": saude.status_code,
    }

    gravar = medida(ITEM)
    gravar("concorrencia_pior_pedido_ms", pior_ms, "ms",
           RESSALVA_FIDELIDADE + " | maior tempo de um pedido individual entre 20 renders "
           "1024x768 simultâneos (pool=2, fila_max=20); "
           "teto do portão: 30.000 ms por pedido. Laudo completo: " + json.dumps(laudo, ensure_ascii=False))
    gravar("concorrencia_maximo_em_execucao", maximo_em_execucao, "pedidos",
           f"pico de pedidos em execução ao mesmo tempo, amostrado a cada 20 ms; o pool é {m.tamanho_pool}")
    gravar("concorrencia_maximo_na_fila", maximo_na_fila, "pedidos",
           f"pico da fila interna; o limite é fila_max={m.fila_max}")
    gravar("concorrencia_pico_rss_pool_mb", laudo["pico_rss_pool_mb"], "MB",
           RESSALVA_FIDELIDADE + " | pico do RSS somado de todos os descendentes do pytest "
           "(driver node + chromium) durante os 20 "
           "pedidos, amostrado a cada ~0,2 s em /proc/<pid>/statm")
    gravar("concorrencia_memoria_max_cgroup_mb", laudo["memoria_max_cgroup_mb"], "MB",
           "memory.max do cgroup em que laco/roda_teste.sh põe o pytest (MemoryMax=${PLAT_TESTE_RSS:-4G}) — "
           "o teto do portão não é escolhido no teste")
    gravar("concorrencia_carga_1min", carga[0], "carga",
           "carga de 1 min da máquina no instante da medida (máquina compartilhada por dezenas de trilhas)")

    assert maximo_em_execucao <= m.tamanho_pool, laudo
    assert maximo_na_fila <= m.fila_max, laudo
    assert maximo_na_fila > m.tamanho_pool, ("a fila nunca passou do tamanho do pool: este lote não chegou a "
                                             "enfileirar, então não prova a cláusula da fila", laudo)
    assert pior_ms < 30000, laudo
    assert pagina.status_code == 200 and saude.status_code == 200, laudo
    assert saude.json()["ativo"] is False or saude.json()["tamanho_pool"] >= 0, laudo
    assert teto_rss is not None, ("sem teto de memória no cgroup: rode por "
                                  "`bash /home/dev/plataforma/laco/roda_teste.sh`, que é quem põe o "
                                  "MemoryMax que esta cláusula compara")
    assert pico_rss_pool <= teto_rss, laudo
    if pico_cgroup is not None:
        assert pico_cgroup <= teto_rss, laudo


def test_pagina_headless_nao_alcanca_host_externo(servidor, motor_novo):
    """Cláusula "página headless sem acesso à rede externa": a página do render tenta um `fetch` para um host
    de fora (nunca vai existir de propósito) e a promise precisa RESOLVER com falha de rede (a interceptação
    aborta o pedido) em vez de a página travar esperando um DNS/timeout de verdade."""

    async def cenario():
        # injeta um fetch externo na própria página via `page.evaluate`, DEPOIS do goto/idle (a página do
        # motor não tenta isso sozinha — o teste simula um estilo malicioso que apontasse para fora)
        await motor_novo.iniciar()
        try:
            pagina = await motor_novo._paginas.get()
            try:
                await pagina.goto(url_demo(servidor, zoom=13), wait_until="load", timeout=15000)
                await pagina.wait_for_selector("body[data-pronto='1']", timeout=15000)
                resultado = await pagina.evaluate(
                    """async () => {
                        try {
                            await fetch('http://exemplo-externo-proibido.invalido/');
                            return 'passou';
                        } catch (e) {
                            return 'bloqueado: ' + e.message;
                        }
                    }"""
                )
                return resultado
            finally:
                await motor_novo._paginas.put(pagina)
        finally:
            await motor_novo.parar()

    resultado = asyncio.run(cenario())
    assert resultado.startswith("bloqueado"), resultado


RESSALVA_FIDELIDADE = (
    "RESSALVA (18/09/2026, medida por tests/e2e/test_render_fidelidade.py): estes tempos e este consumo foram "
    "colhidos com a página do render desenhando SÓ O FUNDO. `web/static/js/mapa/render_entrada.js` chama "
    "`construirEstilo(urlDado(...))` passando uma STRING, e a assinatura de web/js/mapa/estilo.js espera o "
    "descritor `{tipo, url}` — a string cai em `plat-sem-base` (0 fontes, 1 camada), enquanto o visualizador monta "
    "`plat-instrumento-guarulhos` (6 camadas). Medido no navegador contra a bancada, não deduzido. Logo: 64,4 % dos "
    "pixels diferem do visualizador, e todo tempo/RSS deste arquivo vai MUDAR quando o mapa-base passar a pintar de "
    "verdade. Ler estes números como 'render de mapa' seria erro."
)

TETO_QUENTE_MS = 1000
TETO_FRIO_MS = 3000
N_QUENTE_PORTAO = 50  # portão literal: "p95 de 50"


def test_frio_e_quente_p95_da_demo_1024x768(servidor):
    """Cláusula do portão: "1024×768 do mapa da demo quente ≤ 1 s e frio ≤ 3 s (p95 de 50, medido em
    tests/medidas)". Definição operacional (declarada em app/render/motor.py): os primeiros `tamanho_pool`
    renders de um Motor recém-iniciado são frio; os 50 seguintes, quente. Grava a medida em
    tests/medidas/L2-12-a-motor-render-servidor.json para o portão citar o número, não a promessa.

    Margem/retentativa documentada (achado do adversário do T9, 18/09/2026 — o fechamento f2a8cb15 commitou
    uma medida VERMELHA de quente_p95=1290,2 ms colhida com a máquina a carga ~20, e ninguém percebeu):
    este gate é sensível à disputa de CPU da máquina compartilhada, então a regra aqui é —
    1. cada tentativa grava a carga do instante como NÚMERO (carga_1/5/15min), nunca em prosa;
    2. se o p95 estourar o teto E a carga de 1 min estiver acima de 1 por CPU, a tentativa é contenção
       externa, não regressão do motor: espera-se a carga cair (teto de relógio, abaixo) e re-mede-se,
       até TENTATIVAS_MAX vezes; todas as tentativas ficam registradas em `tentativas` no JSON — a
       margem é pública, nunca um descarte silencioso;
    3. se o p95 estourar com carga BAIXA (≤ 1 por CPU), é regressão real do motor: reprova na hora, sem
       retentar — retentativa não existe para esconder o motor lento;
    4. o JSON só vai ao disco DEPOIS das asserções (antes era gravado no meio do teste: uma rodada
       reprovada deixava o arquivo vermelho na árvore, pronto para ser commitado como "prova" — foi
       exatamente o furo do f2a8cb15; a guarda de tests/conftest.py cobre a fixture `medida`, mas este
       teste escreve o arquivo na mão e precisava da mesma disciplina)."""
    # timeout_s alto de propósito (máquina COMPARTILHADA por dezenas de trilhas): um goto que estoura 15s
    # sob contenção vira amostra descartada, não crash — o teto do PORTÃO é conferido no p95, não aqui.
    TENTATIVAS_MAX = 3
    # orçamento de relógio do teste inteiro (roda_teste.sh dá 10 min): 3 tentativas de ~2 min + esperas.
    prazo_total = time.perf_counter() + 420

    async def medir_uma_vez():
        m = Motor(tamanho_pool=2, fila_max=10, timeout_s=60)

        async def uma_amostra():
            """Uma tentativa; None se estourar o teto de rede/CPU da máquina compartilhada — vira "falha"
            na medida, não crash do teste (a medida quer o tempo do MOTOR; a contenção entra como carga)."""
            t0 = time.perf_counter()
            try:
                await m.renderizar(url_demo(servidor, zoom=13), largura=1024, altura=768, formato="png",
                                    espera_timeout_ms=15000)
            except Exception as e:  # noqa: BLE001 — vira "falha" na medida, não um crash do teste
                return None, str(e)
            return (time.perf_counter() - t0) * 1000, None

        # teto por tentativa: sem ele, uma máquina ruim o bastante faz o teste nunca escrever nada
        prazo_amostras = min(time.perf_counter() + 120, prazo_total)
        await m.iniciar()
        try:
            tempos_frio, falhas_frio = [], []
            for i in range(m.tamanho_pool):
                dt, erro = await uma_amostra()
                (tempos_frio if dt is not None else falhas_frio).append(dt if dt is not None else erro)
                print(f"frio[{i}] {'%.1fms' % dt if dt is not None else 'FALHOU: ' + erro}", flush=True)
            tempos_quente, falhas_quente = [], []
            for i in range(N_QUENTE_PORTAO):
                if time.perf_counter() > prazo_amostras:
                    print(f"orçamento da tentativa esgotado em quente[{i}]", flush=True)
                    break
                dt, erro = await uma_amostra()
                (tempos_quente if dt is not None else falhas_quente).append(dt if dt is not None else erro)
                print(f"quente[{i}] {'%.1fms' % dt if dt is not None else 'FALHOU: ' + erro}", flush=True)
            return tempos_frio, falhas_frio, tempos_quente, falhas_quente
        finally:
            await m.parar()

    def p95(xs):
        if not xs:
            return None
        xs = sorted(xs)
        idx = max(0, min(len(xs) - 1, int(round(0.95 * (len(xs) - 1)))))
        return round(xs[idx], 1)

    def carga_por_cpu():
        return (os.cpu_count() or 1) * 1.0

    def esperar_carga_cair():
        """Espera a carga de 1 min cair abaixo de 0,75 por CPU, até o prazo total — a retentativa só faz
        sentido medindo num instante menos disputado; sem vaga dentro do relógio, mede assim mesmo e a
        tentativa registra a carga que havia."""
        while time.perf_counter() < prazo_total and os.getloadavg()[0] > carga_por_cpu() * 0.75:
            time.sleep(5)

    def aprovou(t):
        return (t["n_quente_ok"] >= N_QUENTE_PORTAO and t["quente_p95_ms"] is not None
                and t["quente_p95_ms"] <= TETO_QUENTE_MS and t["n_frio_ok"] >= 1
                and t["frio_p95_ms"] is not None and t["frio_p95_ms"] <= TETO_FRIO_MS)

    tentativas = []
    while len(tentativas) < TENTATIVAS_MAX and time.perf_counter() < prazo_total:
        tempos_frio, falhas_frio, tempos_quente, falhas_quente = asyncio.run(medir_uma_vez())
        carga = [round(x, 2) for x in os.getloadavg()]
        tentativa = {
            "carga_1min": carga[0], "carga_5min": carga[1], "carga_15min": carga[2],
            "frio_ms": [round(x, 1) for x in tempos_frio],
            "quente_ms": [round(x, 1) for x in tempos_quente],
            "frio_p95_ms": p95(tempos_frio),
            "quente_p95_ms": p95(tempos_quente),
            "n_frio_ok": len(tempos_frio),
            "n_frio_falhou": len(falhas_frio),
            "n_quente_ok": len(tempos_quente),
            "n_quente_falhou": len(falhas_quente),
        }
        tentativas.append(tentativa)
        print(f"tentativa {len(tentativas)}: quente_p95={tentativa['quente_p95_ms']}ms "
              f"frio_p95={tentativa['frio_p95_ms']}ms carga_1min={carga[0]}", flush=True)
        if aprovou(tentativa):
            break
        if carga[0] <= carga_por_cpu():
            print("carga baixa e p95 estourado: regressão do motor, não contenção — sem retentativa",
                  flush=True)
            break
        esperar_carga_cair()

    ultima = tentativas[-1]
    medida = {
        "item": "L2-12-a-motor-render-servidor",
        "cenario": "1024x768, mapa-base local (pmtiles Guarulhos), pool=2",
        # 18/09/2026 (achado do adversário do T9): este gate é sensível a carga e a carga era descrita em
        # PROSA, então ninguém distinguia "o motor piorou" de "a máquina estava lotada" lendo o laudo.
        # Carga como NÚMERO + retentativa documentada (docstring do teste): todas as tentativas ficam em
        # `tentativas`, com a carga do instante de cada uma — a margem é pública, nunca descarte silencioso.
        "carga_1min": ultima["carga_1min"], "carga_5min": ultima["carga_5min"],
        "carga_15min": ultima["carga_15min"],
        "cpus": os.cpu_count(),
        "maquina_no_dia_da_medida": "máquina compartilhada por dezenas de trilhas do laço; a carga do "
                                     "momento está em carga_1min/5min/15min e a de cada tentativa em "
                                     "tentativas[]. Referência medida: com carga ~20 esta medida deu "
                                     "quente_p95 1290,2 ms (fechamento f2a8cb15, reprovado), com carga ~2 "
                                     "deu 165,4 ms — o teto de 1 s do portão só é significativo junto com "
                                     "a carga, e por isso os dois números saem juntos.",
        "tentativas": tentativas,
        "frio_ms": ultima["frio_ms"],
        "quente_ms": ultima["quente_ms"],
        "frio_p95_ms": ultima["frio_p95_ms"],
        "quente_p95_ms": ultima["quente_p95_ms"],
        "n_frio_ok": ultima["n_frio_ok"],
        "n_frio_falhou": ultima["n_frio_falhou"],
        "n_quente_ok": ultima["n_quente_ok"],
        "n_quente_falhou": ultima["n_quente_falhou"],
        "comando": "venv/bin/pytest tests/unit/test_motor_render.py::test_frio_e_quente_p95_da_demo_1024x768 -q",
        "ressalva": RESSALVA_FIDELIDADE,
    }

    # as asserções vêm ANTES da escrita: rodada reprovada não deixa arquivo na árvore para ser commitado
    # como "prova" (o furo do f2a8cb15 era exatamente este — escrita no meio do teste, asserção depois).
    assert aprovou(ultima), medida
    _gravar_no_arquivo_da_medida(medida)


CAMINHO_MEDIDA = "tests/medidas/L2-12-a-motor-render-servidor.json"


def _gravar_no_arquivo_da_medida(novos: dict) -> None:
    """Escreve no JSON do item PRESERVANDO as chaves que já estão lá.

    Antes era um `json.dump` do dicionário inteiro: qualquer rodada deste teste APAGAVA o que a fixture
    `medida` de tests/conftest.py tinha escrito na chave `medidas` (é onde moram, hoje, a concorrência e a
    fidelidade de imagem deste mesmo item). Duas cláusulas medidas sumiam sem ninguém notar, porque o
    arquivo continuava existindo e com números bons dentro."""
    caminho = Path(CAMINHO_MEDIDA)
    atual = {}
    if caminho.exists():
        atual = json.loads(caminho.read_text(encoding="utf-8"))
    atual.update(novos)
    caminho.write_text(json.dumps(atual, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")


N_FRIO_PORTAO = 50  # portão literal: "frio <= 3 s (p95 de 50)"


def test_frio_p95_com_50_amostras(servidor, medida):
    """Cláusula do portão "frio <= 3 s (p95 de 50)". A medida anterior deste item tinha DUAS amostras frias,
    porque frio, pela definição do motor (docstring de app/render/motor.py), são os primeiros `tamanho_pool`
    renders de um Motor recém-iniciado — um Motor de pool=2 só produz duas. Cinquenta amostras frias exigem,
    portanto, cinquenta PÁGINAS que nunca navegaram: aqui isso é feito com Motores de pool=1 abertos e
    fechados em sequência, um por amostra. Cada amostra custa uma subida de chromium, e é por isso que o
    número de amostras vai ao laudo junto do p95: se o orçamento de relógio estourar antes das 50, o teste
    REPROVA dizendo quantas deu — nunca publica um p95 de amostra curta como se fosse o do portão."""
    prazo = time.perf_counter() + 420
    tempos, falhas = [], []

    async def uma_amostra_fria():
        m = Motor(tamanho_pool=1, fila_max=2, timeout_s=60)
        await m.iniciar()
        try:
            t0 = time.perf_counter()
            await m.renderizar(url_demo(servidor, zoom=13), largura=1024, altura=768, formato="png",
                                espera_timeout_ms=15000)
            return (time.perf_counter() - t0) * 1000
        finally:
            await m.parar()

    for i in range(N_FRIO_PORTAO):
        if time.perf_counter() > prazo:
            print(f"orçamento de relógio esgotado na amostra fria {i}", flush=True)
            break
        try:
            dt = asyncio.run(uma_amostra_fria())
        except Exception as e:  # noqa: BLE001 — vira falha na medida, não crash do teste
            falhas.append(str(e))
            print(f"frio[{i}] FALHOU: {e}", flush=True)
            continue
        tempos.append(dt)
        print(f"frio[{i}] {dt:.1f}ms", flush=True)

    def p95(xs):
        if not xs:
            return None
        xs = sorted(xs)
        return round(xs[max(0, min(len(xs) - 1, int(round(0.95 * (len(xs) - 1)))))], 1)

    carga = [round(x, 2) for x in os.getloadavg()]
    valor = p95(tempos)
    laudo = {"n_frio_ok": len(tempos), "n_frio_falhou": len(falhas), "frio_p95_ms": valor,
             "frio_ms": [round(x, 1) for x in tempos], "carga_1min": carga[0], "carga_5min": carga[1],
             "carga_15min": carga[2], "teto_ms": TETO_FRIO_MS,
             "cenario": "1024x768, mapa-base local (pmtiles Guarulhos), um Motor de pool=1 por amostra"}
    gravar = medida(ITEM)
    gravar("frio_p95_ms_50_amostras", valor, "ms",
           RESSALVA_FIDELIDADE + " | p95 do render FRIO 1024x768 (pool=1, um Motor novo por "
           "amostra); teto do portão 3.000 ms. "
           "Laudo: " + json.dumps(laudo, ensure_ascii=False))
    gravar("frio_n_amostras", len(tempos), "amostras",
           "quantas amostras frias entraram no p95 acima; o portão pede 50")
    gravar("frio_carga_1min", carga[0], "carga", "carga de 1 min da máquina no instante da medida")

    assert len(tempos) >= N_FRIO_PORTAO, laudo
    assert valor is not None and valor <= TETO_FRIO_MS, laudo
