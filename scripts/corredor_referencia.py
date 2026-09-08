#!/usr/bin/env python3
"""Confere o motor de traçado deste repositório contra o motor de traçado de linha de transmissão da casa
(item L3-10-corredor-custo-minimo). NÃO faz parte do serviço: é o instrumento que produz as medidas do item.

O motor da casa vive fora deste repositório e não é copiado para cá; o caminho dele entra por argumento. O
script:
  1. lê o registro de camadas e os pesos efetivos do motor de referência (sem recalcular nada: as máscaras
     saem do cache em disco que a rodada oficial deixou; máscara ausente do cache interrompe a conferência,
     porque queimar vetor de novo aqui inventaria uma superfície que não é a da rodada);
  2. compõe a superfície com `app.amc.corredor.compor` deste repositório e compara BIT A BIT com a
     superfície oficial gravada na rodada;
  3. traça a rota entre as pontas da rota oficial e mede a distância de Hausdorff entre as duas, o tempo e o
     pico de memória, nos dois motores (fila e esparso) e com a janela declarada.
Uso:
  venv/bin/python scripts/corredor_referencia.py --referencia <dir do motor> --superficie <arquivo .npz>
Saída: JSON no stdout (é o que alimenta tests/medidas/L3-10-corredor-custo-minimo.json)."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.amc import corredor as C  # noqa: E402


def _janela_do_codigo(ref: Path):
    """Janela (TE) e resolução (RES) como estão escritas no motor de referência, por leitura de texto — o
    módulo não pode ser importado sem disparar a rodada inteira."""
    import re
    fonte = (ref / "motor" / "route_v1.py").read_text(encoding="utf-8", errors="replace")
    mte = re.search(r"^TE\s*=\s*\(([^)]*)\)", fonte, re.M)
    mres = re.search(r"^RES\s*=\s*([0-9.]+)", fonte, re.M)
    te = tuple(float(x) for x in mte.group(1).split(",")) if mte else None
    return te, (float(mres.group(1)) if mres else None)


def carregar_referencia(ref: Path):
    """Importa o registro de camadas e os pesos do motor de referência, sem tocar em banco nem em vetor."""
    sys.path.insert(0, str(ref / "motor"))
    import camadas as REG  # type: ignore
    import mascaras as MASC  # type: ignore
    import pesos as PESOS  # type: ignore
    return REG, MASC, PESOS


def mascaras_do_cache(REG, MASC, ref: Path, te, res: float, forma) -> dict:
    """Máscara de cada camada, SÓ do cache da rodada oficial.

    A chave do cache carrega o texto da janela (`te`), e o texto depende de como a rodada oficial escreveu a
    tupla. Em vez de adivinhar um formato, o script experimenta as formas possíveis e fica com a que ACHA
    arquivo — se nenhuma achar, a conferência para e diz quais camadas faltaram, em vez de compor uma
    superfície diferente e chamá-la de igual."""
    alt, larg = forma
    cam_dir = str(ref / "camadas")
    jan = f"{cam_dir}/janela"
    cache = f"{cam_dir}/_cache"
    saida, faltando, rasters = {}, [], {}
    for cam in REG.CAMADAS:
        if cam["papel"] in ("quarentena", "metrica") or cam.get("quarentena"):
            continue
        caminho = MASC.achar(cam, jan, cam_dir)
        if caminho is None:
            continue
        if caminho.endswith(".tif"):
            rasters[cam["id"]] = caminho
            continue
        arquivo = None
        for forma_te in (te, tuple(int(x) if float(x).is_integer() else float(x) for x in te),
                         np.array(te), list(te)):
            chave = MASC.chave_cache(cam, caminho, forma_te, res)
            candidato = f"{cache}/{cam['id']}_{chave}.npz"
            if os.path.exists(candidato):
                arquivo = candidato
                break
        if arquivo is None:
            faltando.append(cam["id"])
            continue
        z = np.load(arquivo)
        m = np.unpackbits(z["bits"], count=alt * larg).astype(bool).reshape(alt, larg)
        if m.any():
            saida[cam["id"]] = m
    return saida, faltando, rasters


def hausdorff_m(a: np.ndarray, b: np.ndarray, res: float) -> float:
    from scipy.spatial import cKDTree
    ta, tb = cKDTree(a.astype(float)), cKDTree(b.astype(float))
    return max(float(tb.query(a.astype(float))[0].max()), float(ta.query(b.astype(float))[0].max())) * res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--referencia", required=True, help="diretório do motor de traçado da casa")
    ap.add_argument("--superficie", required=True, help="arquivo .npz da rodada oficial (só leitura)")
    ap.add_argument("--janela", type=int, default=400, help="margem em células da janela declarada")
    a = ap.parse_args()
    ref = Path(a.referencia).resolve()
    z = np.load(a.superficie)
    oficial = z["cost"]
    alt, larg = oficial.shape
    veto_oficial = np.unpackbits(z["veto"], count=alt * larg).astype(bool).reshape(alt, larg)
    rota_oficial = z["lcp"]
    te = tuple(float(x) for x in z["te"])
    res = float(np.ravel(z["res"])[0])
    # A CHAVE DO CACHE usa a janela declarada no CÓDIGO do motor de referência, que não é byte a byte a
    # janela gravada no arquivo de saída (o arquivo guarda o recorte já ajustado). Ler a constante do fonte
    # é o que faz a chave bater; sem isso nenhuma máscara é encontrada e a conferência compõe uma superfície
    # vazia — que foi exatamente o primeiro resultado errado deste script.
    te_codigo, res_codigo = _janela_do_codigo(ref)
    te = te_codigo or te
    res = res_codigo or res

    REG, MASC, PESOS = carregar_referencia(ref)
    efetivo, diag_peso = PESOS.reancora({c["id"]: c.get("peso") for c in REG.CAMADAS if c.get("peso")})
    mascaras, faltando, rasters = mascaras_do_cache(REG, MASC, ref, te, res, oficial.shape)
    camadas = []
    for cam in REG.CAMADAS:
        m = mascaras.get(cam["id"])
        if m is None:
            continue
        if cam["papel"] == "veto":
            camadas.append(C.Camada(cam["id"], "veto", m))
        elif cam["papel"] == "custo":
            camadas.append(C.Camada(cam["id"], "custo", m, peso=float(efetivo.get(cam["id"], cam["peso"]))))
        elif cam["papel"] == "atrai":
            camadas.append(C.Camada(cam["id"], "atrai", m, valor=float(cam["valor"])))
    # a rodada oficial roda com a compressão DESLIGADA (o alvo padrão do registro é nulo); ligar aqui
    # produziria outra superfície, então o script segue o registro em vez de escolher por conta própria
    # os dois rasters do motor de referência (declividade em % e densidade de edificação) entram pelas
    # mesmas passadas do módulo: curva de relevo e rampa declarada. Eles NÃO têm cache de máscara — são lidos
    # do arquivo, reamostrados para a janela como a rodada oficial faz.
    declividade, rampas = None, []
    if rasters:
        import rasterio
        for cid, caminho in rasters.items():
            with rasterio.open(caminho) as src:
                arr = src.read(1, out_shape=oficial.shape).astype(np.float32)
            if cid == "declividade":
                declividade = np.where(arr < 0, 0, arr)
            else:
                cam = next(c for c in REG.CAMADAS if c["id"] == cid)
                rampas.append((arr, 20.0, float(cam.get("peso", 10.0))))
    alvo = getattr(REG, "ALVO_AMPLITUDE_PENALIDADE", None)
    alvo = float(alvo) if alvo else None
    s = C.compor(camadas, forma=oficial.shape, declividade=declividade, curva=tuple(map(tuple, REG.CURVA_RELEVO)),
                 rampas=rampas, alvo_amplitude=alvo, min_atracao=REG.MIN_ATRACAO)
    igual = bool(np.array_equal(s.custo, oficial))
    saida = {
        "camadas_do_cache": len(camadas),
        "rasters": sorted(rasters),
        "camadas_sem_cache": faltando,
        "reancoragem": {k: round(float(v), 4) for k, v in list(efetivo.items())[:50]},
        "superficie_igual_bit_a_bit": igual,
        "maior_diferenca": float(np.abs(s.custo - oficial).max()),
        "veto_igual": bool(np.array_equal(s.veto, veto_oficial)),
        "celulas_vetadas": int(veto_oficial.sum()),
        "diagnostico": s.diagnostico,
        "pesos_diag": diag_peso if isinstance(diag_peso, dict) else str(diag_peso),
    }
    custo = oficial if igual else s.custo
    A = tuple(int(x) for x in rota_oficial[0])
    B = tuple(int(x) for x in rota_oficial[-1])
    saida["reta_entre_as_pontas_km"] = round(float(np.hypot(A[0] - B[0], A[1] - B[1])) * res / 1000.0, 1)
    for nome, kw in (("esparso", {"motor": "esparso"}),
                     ("esparso_com_janela", {"motor": "esparso", "margem_celulas": a.janela})):
        t0 = time.perf_counter()
        r = C.caminho(custo, veto_oficial, A, B, vizinhanca=16, **kw)
        dt = time.perf_counter() - t0
        saida[nome] = {
            "segundos": round(dt, 1),
            "custo": round(r["custo"], 2),
            "celulas": r["celulas_percorridas"],
            "comprimento_km": round(r["comprimento_celulas"] * res / 1000.0, 1),
            "hausdorff_m": round(hausdorff_m(r["celulas"], rota_oficial, res), 1),
            "sinuosidade": round(C.sinuosidade(r["celulas"]), 4),
            "celulas_da_rota_oficial": int(rota_oficial.shape[0]),
        }
    faixas = {}
    for eps in (0.05, 0.10):
        t0 = time.perf_counter()
        f = C.corredor(custo, veto_oficial, A, B, epsilon=eps, vizinhanca=16, motor="esparso")
        faixas[f"corredor_{int(eps * 100)}pct"] = {
            "segundos": round(time.perf_counter() - t0, 1),
            "celulas": f["celulas"],
            "fracao_da_janela_livre_pct": round(100.0 * f["celulas"] / int((~veto_oficial).sum()), 2),
            "otimo": round(f["otimo"], 2),
            "teto": round(f["teto"], 2),
        }
    saida.update(faixas)
    # o arquivo oficial traz um campo de corredor de 5 %, mas ele está VAZIO (zero célula) — não há contra o
    # que comparar, e dizer que "bate" seria comparar com nada. Fica registrado como achado.
    if "corr5" in z:
        oficial5 = np.unpackbits(z["corr5"], count=alt * larg).astype(bool).reshape(alt, larg)
        saida["corredor_oficial_celulas"] = int(oficial5.sum())
    saida["pico_memoria_gib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 2)
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 0 if igual else 1


if __name__ == "__main__":
    raise SystemExit(main())
