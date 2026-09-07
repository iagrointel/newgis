"""Cláusulas de TEMPO e de RAM do item L3-16-desempenho-escala, medidas nesta máquina.

Regra da casa para toda cláusula com tempo (brief das trilhas, 07/09/2026): número medido sob disputa
não diz nada sobre o produto. Antes de medir, este arquivo olha `os.getloadavg()` e a RAM livre; com
carga de 1 minuto acima de 8 (são 12 núcleos) a cláusula é marcada como NÃO MEDIDA, com o motivo escrito
em `tests/medidas/L3-16-desempenho-escala.json`, e o teste não reprova o produto por causa da casa. Todo
número gravado carrega ao lado `carga_1min`, `ram_livre_gb` e `medido_em`.

O que se mede aqui:

1. **Recombinação de 1 milhão de unidades no servidor, ≤ 5 s** — `app.amc.combinacao.combinar` sobre
   1.000.000 × 15, o mesmo caminho que o job `amc.recombinar` percorre bloco a bloco. Junto vão os
   tamanhos de 10 mil e 100 mil, que formam a tabela de tempos por tamanho pedida pela hipótese do item.
2. **Pico de RAM da recombinação em blocos** — `ru_maxrss` antes e depois de percorrer 1.000.000 de
   unidades em blocos de 50 mil, para mostrar que o pico é o de UM bloco e não o do conjunto.
3. **Custo de extração por unidade × fator** — estatística zonal REAL (`app.amc.zonal.extrair`) sobre um
   GeoTIFF gerado no disco, com unidades em EPSG:4326. Daqui sai a PROJEÇÃO para 1 mi × 15 fatores.
   ⚠ projeção não é medição: a linha do JSON diz `projetado` e o handoff repete. Extrair 1 milhão de
   células × 15 camadas reais levaria horas de máquina e camadas que esta árvore não tem.

Grava só com `PLAT_GRAVAR_MEDIDAS=1` (ADR 0001 seção 10): a suíte comum roda a montagem e a checagem do
limite, mas não suja a árvore a cada rodada."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import box, mapping

from app import limites
from app.amc import escala
from app.amc.combinacao import combinar

ROOT = Path(__file__).resolve().parents[2]
MEDIDAS = ROOT / "tests" / "medidas"
ITEM = "L3-16-desempenho-escala"
ARQUIVO = MEDIDAS / f"{ITEM}.json"

TAMANHOS = (10_000, 100_000, 1_000_000)
FATORES = 15
LIMITE_RECOMBINACAO_S = 5.0
LIMITE_EXTRACAO_S = 1800.0     # 30 min do portão
CARGA_MAXIMA = 8.0
SRID_UTM = 31982               # SIRGAS 2000 / UTM 22S, a mesma família que app.amc.crs escolhe


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")


def _contexto() -> dict:
    return {
        "carga_1min": round(os.getloadavg()[0], 2),
        "ram_livre_gb": _ram_livre_gb(),
        "medido_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _gravar(nome: str, valor, unidade: str, comando: str, contexto: dict, estado: str = "medido") -> None:
    """Escreve uma medida com a carga da máquina AO LADO do número (regra do item). `estado` diz se o
    número é `medido`, `projetado` (conta a partir de uma medida menor) ou `nao_medido` (com o motivo)."""
    if os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1":
        return
    from app.versao import git_sha_curto

    MEDIDAS.mkdir(parents=True, exist_ok=True)
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8")) if ARQUIVO.exists() else {"item": ITEM, "medidas": {}}
    anterior = dados.get("medidas", {}).get(nome)
    if estado == "nao_medido" and anterior and anterior.get("estado") != "nao_medido":
        return  # rodada sob carga NÃO apaga uma medida boa de rodada anterior; o número honesto fica
    dados["gerado_em"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dados["git_sha"] = git_sha_curto()
    dados.setdefault("medidas", {})[nome] = {
        "valor": valor, "unidade": unidade, "estado": estado, "comando": comando, **contexto,
    }
    ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _matriz(n_unidades: int, n_fatores: int = FATORES):
    rng = np.random.default_rng(316_000 + n_unidades)
    m = rng.uniform(0.0, 100.0, size=(n_unidades, n_fatores))
    m[rng.uniform(size=m.shape) < 0.1] = np.nan   # mesma ordem de ausência do motor logístico da casa
    return m, list(rng.uniform(0.1, 5.0, size=n_fatores))


def _mediana_s(funcao, repeticoes: int) -> float:
    tempos = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        funcao()
        tempos.append(time.perf_counter() - t0)
    tempos.sort()
    return tempos[len(tempos) // 2]


def _raster(caminho: Path, lado: int = 400) -> None:
    """GeoTIFF real no disco: `lado`×`lado` células de 10 m em UTM, valores contínuos e um nodata."""
    dados = (np.indices((lado, lado)).sum(axis=0) % 97).astype("float32")
    dados[0, 0] = -9999.0
    perfil = {
        "driver": "GTiff", "height": lado, "width": lado, "count": 1, "dtype": "float32",
        "crs": CRS.from_epsg(SRID_UTM), "transform": Affine(10.0, 0.0, 300_000.0, 0.0, -10.0, 7_400_000.0),
        "nodata": -9999.0,
    }
    with rasterio.open(caminho, "w", **perfil) as ds:
        ds.write(dados, 1)


def _unidades_4326(n: int, caminho: Path):
    """`n` células quadradas de 250 m dentro do raster, já em EPSG:4326 (a entrada real de zonal.extrair)."""
    import pyproj

    para_4326 = pyproj.Transformer.from_crs(SRID_UTM, 4326, always_xy=True)
    lado_m, colunas = 250.0, int(np.ceil(np.sqrt(n)))
    saida = []
    for i in range(n):
        cx = 300_000.0 + (i % colunas) * lado_m
        cy = 7_400_000.0 - (i // colunas) * lado_m
        x0, y0 = para_4326.transform(cx, cy - lado_m)
        x1, y1 = para_4326.transform(cx + lado_m, cy)
        saida.append((f"u{i:07d}", mapping(box(x0, y0, x1, y1))))
    return saida


# ------------------------------------------------------------------ cláusula: recombinação de 1 mi ≤ 5 s

def test_recombinacao_por_tamanho_e_o_milhao_dentro_de_cinco_segundos():
    contexto = _contexto()
    if contexto["carga_1min"] > CARGA_MAXIMA:
        for n in TAMANHOS:
            _gravar(f"recombinacao_{n}x{FATORES}_servidor_s", None, "s",
                    f"combinar() sobre {n}×{FATORES} — NÃO MEDIDO: carga de 1 min "
                    f"{contexto['carga_1min']} > {CARGA_MAXIMA} em 12 núcleos", contexto, estado="nao_medido")
        pytest.skip(f"cláusula NÃO MEDIDA: carga de 1 min {contexto['carga_1min']} > {CARGA_MAXIMA} ({contexto})")

    tempos = {}
    for n in TAMANHOS:
        m, pesos = _matriz(n)
        repeticoes = 20 if n <= 100_000 else 5
        tempos[n] = _mediana_s(lambda m=m, pesos=pesos: combinar(m, pesos), repeticoes)
        _gravar(
            f"recombinacao_{n}x{FATORES}_servidor_s", round(tempos[n], 4), "s",
            f"mediana de {repeticoes} chamadas a app.amc.combinacao.combinar() sobre {n} unidades × {FATORES} "
            f"fatores (soma_ponderada, 10% de ausência sorteada), o mesmo caminho do job amc.recombinar",
            contexto,
        )
        del m
    assert tempos[1_000_000] <= LIMITE_RECOMBINACAO_S, (
        f"recombinação de 1 mi × {FATORES}: {tempos[1_000_000]:.3f} s > {LIMITE_RECOMBINACAO_S} s ({contexto})"
    )
    assert tempos[10_000] <= tempos[100_000] <= tempos[1_000_000], tempos


def test_pico_de_ram_da_recombinacao_de_um_milhao_em_blocos_fica_no_orcamento_do_job():
    """1 milhão de unidades × 15 fatores recombinadas em blocos num processo NOVO, e o pico desse processo
    inteiro tem de caber no orçamento que o job pede. É medido em filho de propósito: o pico do processo do
    pytest já vem alto do resto da suíte e só cresce, então mediria a suíte, não a recombinação.

    O pico do filho é lido em `VmHWM` de `/proc/self/status`, não em `ru_maxrss`: MEDIDO em 07/09/2026, o
    `ru_maxrss` do filho é herdado do processo que deu fork e não volta a zero no exec — dava 748 MB (o pico
    do pytest) quando o arquivo inteiro rodava e 111 MB quando o teste rodava sozinho. `VmHWM` vem do
    `mm_struct`, que o exec cria do zero, e é o pico deste processo e de mais ninguém."""
    contexto = _contexto()
    plano = escala.plano(1_000_000, FATORES)
    programa = (
        "import numpy as np, json\n"
        "from app.amc import escala\n"
        f"bloco, n_blocos, fatores = {plano['bloco']}, {plano['n_blocos']}, {FATORES}\n"
        "rng = np.random.default_rng(316)\n"
        "m = rng.uniform(0.0, 100.0, size=(bloco, fatores))\n"
        "m[rng.uniform(size=m.shape) < 0.1] = np.nan\n"
        "ids = [f'u{i:07d}' for i in range(bloco)]\n"
        "blocos = ((ids, m) for _ in range(n_blocos))\n"
        "n = sum(len(p) for p, _ in escala.combinar_em_blocos(blocos, [1.0] * fatores))\n"
        # VmHWM, não ru_maxrss (o porquê está na docstring do teste)
        "pico = [int(l.split()[1]) / 1024 for l in open('/proc/self/status') if l.startswith('VmHWM:')][0]\n"
        "print(json.dumps({'unidades': n, 'pico_mb': round(pico, 2)}))\n"
    )
    # 1 thread de BLAS, como o worker faz com todo job (app/jobs/filho.py::preparar_ambiente aplica
    # threads_blas, que vale 1 em amc.recombinar).
    ambiente = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    r = subprocess.run([str(ROOT / "venv" / "bin" / "python"), "-c", programa],
                       capture_output=True, text=True, cwd=ROOT, timeout=900, check=True, env=ambiente)
    saida = json.loads(r.stdout.strip().splitlines()[-1])
    assert saida["unidades"] == 1_000_000
    _gravar("pico_ram_recombinacao_1mi_em_blocos_mb", saida["pico_mb"], "MB",
            f"VmHWM (pico de RSS) de um processo Python que recombina 1.000.000 de unidades × {FATORES} fatores em "
            f"{plano['n_blocos']} blocos de {plano['bloco']}, com 1 thread de BLAS como o worker faz "
            f"(interpretador e numpy incluídos); o job "
            f"amc.recombinar pede {plano['orcamento_mb']} MB e o modelo de app/amc/escala.py prevê "
            f"{plano['pico_estimado_mb']} MB", contexto)
    assert saida["pico_mb"] <= plano["orcamento_mb"], (
        f"pico real {saida['pico_mb']} MB acima do orçamento {plano['orcamento_mb']} MB do job ({contexto})"
    )
    assert saida["pico_mb"] <= plano["pico_estimado_mb"], (
        f"pico real {saida['pico_mb']} MB acima do modelo {plano['pico_estimado_mb']} MB ({contexto})"
    )


def test_plano_de_extracao_de_um_milhao_por_quinze_e_recusado_pelo_prazo_projetado():
    """ACHADO deste item, e a razão de o guardrail existir: à taxa MEDIDA da estatística zonal, extrair
    1 milhão de células × 15 fatores leva cerca de 3 horas — seis vezes o prazo de 30 minutos do portão.
    O plano recusa isso ANTES de enfileirar, com o número na mensagem, em vez de deixar o relógio do job
    matar o trabalho no fim. A cláusula de extração do portão está, portanto, REFUTADA no tamanho cheio e
    o limite honesto do produto é o que este teste calcula."""
    with pytest.raises(escala.ErroEscala) as e:
        escala.plano(1_000_000, FATORES, tarefa="extracao")
    assert e.value.codigo == "prazo_projetado_estourado"
    projetado = e.value.detalhe["tempo_projetado_s"]
    assert projetado > limites.AMC_EXTRACAO_TIMEOUT_S

    # maior grade que CABE no prazo com 15 fatores, à taxa medida (o limite honesto que o produto declara)
    cabem = int(limites.AMC_EXTRACAO_TIMEOUT_S * 1e6 / (limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR * FATORES))
    escala.plano(cabem, FATORES, tarefa="extracao")            # cabe: não levanta
    with pytest.raises(escala.ErroEscala) as acima:
        escala.plano(int(cabem * 1.05), FATORES, tarefa="extracao")   # 5% a mais já não cabe
    assert acima.value.codigo == "prazo_projetado_estourado"
    _gravar("extracao_unidades_max_em_30min_com_15_fatores", cabem, "unidades",
            f"maior grade que a extração termina em {limites.AMC_EXTRACAO_TIMEOUT_S} s com {FATORES} "
            f"fatores, à taxa medida de {limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR} µs por unidade e fator "
            f"(app/amc/escala.py recusa acima disso com prazo_projetado_estourado)", _contexto())


# ------------------------------------------------------------------ cláusula: extração de 1 mi × 15 em ≤ 30 min

def test_custo_de_extracao_medido_e_projecao_para_um_milhao_por_quinze_fatores(tmp_path):
    """Mede a estatística zonal REAL (raster no disco, unidades em 4326) e projeta 1 mi × 15 fatores.

    O que é medido: o tempo por unidade × fator, com o extrator de verdade. O que é PROJETADO: o total de
    1.000.000 × 15, por multiplicação. A projeção é gravada com `estado: projetado` e nunca é apresentada
    como medição — extrair 1 milhão de células de 15 camadas reais é trabalho de horas e exige camadas que
    esta árvore não tem (o item L3-01-c2-extracao-em-lote é quem vai medir o caso completo)."""
    contexto = _contexto()
    if contexto["carga_1min"] > CARGA_MAXIMA:
        _gravar("extracao_1mi_x15_projetado_s", None, "s",
                f"NÃO MEDIDO: carga de 1 min {contexto['carga_1min']} > {CARGA_MAXIMA}", contexto,
                estado="nao_medido")
        pytest.skip(f"cláusula NÃO MEDIDA: carga de 1 min {contexto['carga_1min']} > {CARGA_MAXIMA} ({contexto})")

    from app.amc import zonal

    caminho = tmp_path / "fator.tif"
    _raster(caminho)
    n = 2_000
    unidades = _unidades_4326(n, caminho)
    t0 = time.perf_counter()
    r = zonal.extrair(str(caminho), 1, unidades, "raster_media")
    medido_s = time.perf_counter() - t0
    assert len(r) == n
    com_dado = sum(1 for v in r.values() if v["valor"] is not None)
    assert com_dado > 0, "o extrator devolveu só NULL: a medida não vale (raster e unidades não se tocam)"

    por_unidade_fator_us = medido_s / n * 1e6
    projetado_s = (medido_s / n) * 1_000_000 * FATORES
    _gravar("extracao_por_unidade_por_fator_us", round(por_unidade_fator_us, 2), "µs",
            f"app.amc.zonal.extrair(raster_media) sobre {n} células de 250 m em GeoTIFF de 10 m "
            f"(400×400, nodata declarado), {com_dado} com dado; tempo total {medido_s:.3f} s", contexto)
    _gravar("extracao_1mi_x15_projetado_s", round(projetado_s, 1), "s",
            f"PROJEÇÃO por multiplicação: {por_unidade_fator_us:.2f} µs × 1.000.000 × {FATORES} fatores. "
            f"Não é medição do caso completo; o portão do item L3-01-c2-extracao-em-lote é quem mede a "
            f"extração em lote de verdade. Limite do portão: {LIMITE_EXTRACAO_S:.0f} s (30 min)",
            contexto, estado="projetado")
    _gravar("extracao_1mi_x15_limite_do_portao_s", LIMITE_EXTRACAO_S, "s",
            "limites.AMC_EXTRACAO_TIMEOUT_S — prazo do job de extração declarado no portão do item",
            contexto)
    assert projetado_s > 0


# ------------------------------------------------------------------ tabela do navegador (o outro lado da fronteira)

def test_navegador_no_maior_tamanho_que_aceita():
    """O navegador só aceita até `AMC_COMBINAR_NAVEGADOR_MAX`; o tempo desse tamanho máximo é o que o
    usuário sente antes de a conta passar ao servidor. Medido com performance.now via node, o mesmo
    relógio do navegador (mesmo runner do item L3-01-e)."""
    contexto = _contexto()
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("node ausente nesta máquina")
    if contexto["carga_1min"] > CARGA_MAXIMA:
        pytest.skip(f"cláusula NÃO MEDIDA: carga de 1 min {contexto['carga_1min']} > {CARGA_MAXIMA}")

    n = limites.AMC_COMBINAR_NAVEGADOR_MAX
    m, pesos = _matriz(n)
    entrada = {
        "fatores": [[None if not np.isfinite(v) else float(v) for v in linha] for linha in m],
        "pesos": pesos, "opcoes": {}, "repeticoes": 5,
    }
    r = subprocess.run(["node", str(ROOT / "tests" / "amc" / "executar_js.mjs"), "--desempenho"],
                       input=json.dumps(entrada), capture_output=True, text=True, timeout=300,
                       cwd=ROOT, check=True)
    ms = json.loads(r.stdout)["ms_mediano"]
    _gravar(f"combinacao_navegador_{n}x{FATORES}_ms", round(ms, 2), "ms",
            f"mediana de 5 chamadas a combinar() em web/js/amc/combinacao.js sobre {n} × {FATORES}, "
            f"medida com performance.now() via node (tests/amc/executar_js.mjs --desempenho); {n} é o maior "
            f"tamanho que o navegador aceita — acima disso ele recusa e a conta vai ao servidor", contexto)
    assert ms > 0
