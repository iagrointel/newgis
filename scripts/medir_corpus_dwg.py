#!/usr/bin/env python3
"""Mede, sobre um corpus de DWG, DUAS coisas que não são a mesma (item L0-04-e, ADR 0020 seção 7):

1. quantos arquivos o **LibreDWG** (`dwg2dxf`) consegue converter (código de saída 0 e DXF com bytes);
2. de quantos o **driver DXF do GDAL** consegue tirar ao menos uma feição.

Confundir as duas foi o primeiro erro desta medição: 20,57 % de "falha" eram desenhos que o LibreDWG leu
inteiros e cuja única entidade (RAY, XLINE, HELIX, SPLINE, sólido 3D) o GDAL não representa. Trocar o conversor
não resolveria nada disso.

Uso: `python3 scripts/medir_corpus_dwg.py <raiz do corpus> <saida.json> [caminho do dwg2dxf]`
Saída: total, ok, taxa por versão do DWG e o registro de cada arquivo."""
import json
import os
import subprocess
import sys
import tempfile
import time

VERSOES = {"AC1.40":"R1.4","AC1.50":"R2.05","AC2.10":"R2.10","AC1002":"R2.5","AC1003":"R2.6",
 "AC1004":"R9","AC1006":"R10","AC1009":"R11/R12","AC1012":"R13","AC1014":"R14","AC1015":"R2000",
 "AC1018":"R2004","AC1021":"R2007","AC1024":"R2010","AC1027":"R2013","AC1032":"R2018"}
raiz, saida = sys.argv[1], sys.argv[2]
exe = sys.argv[3] if len(sys.argv) > 3 else "dwg2dxf"
arqs = []
for d, _, fs in os.walk(raiz):
    for f in fs:
        if f.lower().endswith(".dwg"):
            arqs.append(os.path.join(d, f))
arqs.sort()
reg = []
t0 = time.time()
for i, a in enumerate(arqs):
    with open(a, "rb") as fh:
        cab = fh.read(6).decode("latin-1", "replace")
    ver = VERSOES.get(cab, "desconhecida")
    with tempfile.TemporaryDirectory() as td:
        alvo = os.path.join(td, "s.dxf")
        ini = time.time()
        try:
            r = subprocess.run([exe, "-y", "-o", alvo, a], capture_output=True, text=True, timeout=120)
            rc, err = r.returncode, (r.stderr or "").strip().splitlines()[-1:]
        except subprocess.TimeoutExpired:
            rc, err = -9, ["tempo esgotado (120 s)"]
        except Exception as e:
            rc, err = -1, [str(e)]
        dur = time.time() - ini
        tam = os.path.getsize(alvo) if os.path.exists(alvo) else 0
        feicoes = -1
        if tam > 0:
            try:
                q = subprocess.run(["ogrinfo", "-ro", "-json", "-so", alvo, "entities"],
                                   capture_output=True, text=True, timeout=120,
                                   env=dict(os.environ, GDAL_SKIP="HTTP", CPL_LOG="/dev/null"))
                if q.returncode == 0:
                    d = json.loads(q.stdout)
                    feicoes = sum(int(c.get("featureCount") or 0) for c in d.get("layers", []))
            except Exception:
                feicoes = -1
    ok = rc == 0 and tam > 0 and feicoes > 0
    reg.append(dict(arquivo=os.path.relpath(a, raiz), cabecalho=cab, versao=ver, rc=rc,
                    bytes_dxf=tam, feicoes=feicoes, segundos=round(dur, 3), ok=ok, erro=(err[0][:200] if err else "")))
    if i % 25 == 0:
        print(i, len(arqs), flush=True)
por_versao = {}
for r in reg:
    v = por_versao.setdefault(r["versao"], {"total": 0, "ok": 0})
    v["total"] += 1
    v["ok"] += int(r["ok"])
for v in por_versao.values():
    v["falhas"] = v["total"] - v["ok"]
    v["taxa_falha_pct"] = round(100.0 * v["falhas"] / v["total"], 2)
tot = len(reg)
okn = sum(1 for r in reg if r["ok"])
versao_exe = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip().splitlines()[0]
res = dict(raiz=raiz, conversor=versao_exe,
           total=tot, ok=okn, falhas=tot - okn, taxa_falha_pct=round(100.0 * (tot - okn) / max(1, tot), 2),
           segundos=round(time.time() - t0, 1), por_versao=por_versao, registros=reg)
json.dump(res, open(saida, "w"), ensure_ascii=False, indent=1)
print("TOTAL", tot, "OK", okn, "FALHA_PCT", res["taxa_falha_pct"])
