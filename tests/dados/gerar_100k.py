"""Gera o shapefile de 100 mil feições do portão do item L0-04-c-tabela-camada ("shapefile de 100 mil feições,
dado aberto, ex. setores censitários de um estado, importa e aparece na lista em ≤ 60 s").

DADO ABERTO REAL, já ingerido na casa: malha de setores censitários do Censo 2022 do IBGE
(`public.amc_setores_censitarios_2022` no banco `iagro_sat`, SIRGAS 2000 / EPSG:4674, MULTIPOLYGON).
São 472.780 setores no país; este gerador recorta os 100.000 primeiros de São Paulo (cd_uf='35', que tem
103.620) pela ordem de `cd_setor`, de forma determinística — a mesma chamada devolve sempre o mesmo arquivo.

Não baixa nada (disco a 98 %) e não escreve no schema da plataforma: só lê a tabela pública com `ogr2ogr` e
grava `tests/dados/gerados/setores_sp_100k.zip` (a pasta está no .gitignore). Roda como o usuário `postgres`
(`sudo -u postgres`) porque a leitura é da base de dados abertos da casa, não da base da plataforma.

Uso:  venv/bin/python tests/dados/gerar_100k.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

SAIDA = Path(__file__).resolve().parent / "gerados"
DESTINO_ZIP = SAIDA / "setores_sp_100k.zip"
N_FEICOES = 100_000
UF = "35"  # São Paulo (103.620 setores no Censo 2022)
BANCO = "iagro_sat"
TABELA = "public.amc_setores_censitarios_2022"

SQL = (
    "SELECT cd_setor, situacao, cd_mun, nm_mun, nm_bairro, area_km2, geom "
    f"FROM {TABELA} WHERE cd_uf = '{UF}' ORDER BY cd_setor LIMIT {N_FEICOES}"
)


def gerar() -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    if DESTINO_ZIP.exists():
        return DESTINO_ZIP
    # o ogr2ogr roda como `postgres` (le a base de dados abertos da casa), que nao escreve no diretorio do
    # repositorio: a saida vai para um diretorio temporario com permissao para todos e so o zip final volta.
    tmp = Path(tempfile.mkdtemp(prefix="setores100k-"))
    tmp.chmod(0o777)
    r = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "ogr2ogr", "-f", "ESRI Shapefile", str(tmp / "setores_sp_100k.shp"),
         f"PG:dbname={BANCO}", "-sql", SQL, "-nln", "setores_sp_100k", "-lco", "ENCODING=UTF-8"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ogr2ogr falhou: {r.stderr[-2000:]}")
    subprocess.run(["sudo", "-n", "chmod", "-R", "a+r", str(tmp)], check=True)
    membros = sorted(p for p in tmp.iterdir() if p.is_file())
    with zipfile.ZipFile(DESTINO_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in membros:
            zf.write(m, m.name)
    shutil.rmtree(tmp, ignore_errors=True)
    return DESTINO_ZIP


if __name__ == "__main__":
    caminho = gerar()
    print(f"{caminho} · {caminho.stat().st_size / 1024 / 1024:.1f} MiB")
