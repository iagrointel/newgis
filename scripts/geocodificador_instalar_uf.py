#!/usr/bin/env python3
"""Instalador do geocodificador por UF (item L2-11-b-geocodificador-brasil, ADR 0013 seção 6).

    venv/bin/python3 scripts/geocodificador_instalar_uf.py --uf RR [--forcar] [--sem-download ARQ.zip]

Baixa o CSV de endereços do CNEFE 2022 (IBGE) de UMA UF por vez — o item pede demo com UF pequena, e o
tamanho é MEDIDO por HEAD antes de baixar (decisão D28 do dono sobre disco: teto de 200 MB comprimido por
padrão, `--forcar` ignora o teto). Fonte:
    https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/
    Arquivos_CNEFE/CSV/UF/<COD>_<SIGLA>.zip
Município (nome) vem da API pública do IBGE (servicodados.ibge.gov.br/api/v1/localidades/estados/<COD>/municipios).

Carga por streaming: o zip nunca é extraído por inteiro em disco (lido membro a membro com `zipfile`), e as
linhas do CSV vão para `plat.geo_endereco` por `COPY` em lotes (baixo consumo de memória e de tempo — medido
em tests/medidas). Nenhuma coluna de nome de pessoa existe no CNEFE (o item pede conferência: ver
tests/api/test_geocodificador.py::test_cnefe_sem_coluna_de_pessoa, que faz o mesmo grep de colunas descrito
aqui). Idempotente por UF: reinstalar a mesma UF apaga e recarrega (nunca duplica)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx
import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.geocodificador.normalizacao import expandir_abreviacoes  # noqa: E402
from app.schema_ambiente import CursorSchemaAmbiente  # noqa: E402 -- depois do sys.path acima; fábrica única (item F9), a reinvenção local do L2-11-a foi removida

BASE_CNEFE = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/"
    "Arquivos_CNEFE/CSV/UF"
)
BASE_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
TETO_BYTES_PADRAO = 200 * 1024 * 1024  # 200 MB comprimidos; D28 (teto de disco do laço) — ver README do laço
LOTE_COPY = 20_000
USER_AGENT = "plat-geocodificador/1.0 (+iAgroIntel; instalador por UF, item L2-11-b)"

UFS = {  # cod IBGE -> sigla (fechado; usado só para validar --uf e montar a URL)
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
    24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
SIGLA_PARA_COD = {v: k for k, v in UFS.items()}


def _log(msg: str) -> None:
    print(f"[geocodificador_instalar_uf] {msg}", file=sys.stderr, flush=True)


def _dsn() -> str:
    """PLAT_DSN do ambiente do processo (trilha: `laco/trilha_ambiente.sh` grava um .env de trilha e o
    chamador faz `set -a; source ...`) OU do `.env` da raiz, nesta ordem — não usa `app.settings`: este
    script não precisa de PLAT_SECRET/segredos systemd, que desde o item L7-19 não moram mais no .env
    (exigi-los aqui quebraria a carga sem motivo). O ambiente vence porque é o único jeito de uma trilha
    (que não tem `.env` na raiz do worktree) apontar este script para o Postgres certo sem editar o script."""
    dsn = os.environ.get("PLAT_DSN") or dotenv_values(ROOT / ".env").get("PLAT_DSN")
    if not dsn:
        raise SystemExit("PLAT_DSN ausente (nem no ambiente, nem em .env)")
    return dsn


def _conectar():
    """Conexao com a fabrica de cursor do ambiente. Sem ela, tanto o `INSERT INTO plat.geo_uf` quanto o
    `COPY plat.geo_endereco ... FROM STDIN` (lotes de 20.000) gravavam no `plat` de PRODUCAO a partir de
    qualquer trilha (achado F9; o COPY e o F2, coberto agora por `CursorSchemaAmbiente.copy_expert`)."""
    return psycopg2.connect(_dsn(), cursor_factory=CursorSchemaAmbiente)


def medir_tamanho(cliente: httpx.Client, url: str) -> int:
    r = cliente.head(url, follow_redirects=True)
    r.raise_for_status()
    return int(r.headers["content-length"])


def baixar(cliente: httpx.Client, url: str, destino: Path) -> str:
    h = hashlib.sha256()
    with cliente.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        with destino.open("wb") as f:
            for pedaco in r.iter_bytes(1024 * 256):
                f.write(pedaco)
                h.update(pedaco)
    return h.hexdigest()


def buscar_municipios(cliente: httpx.Client, cod_uf: int) -> list[dict]:
    r = cliente.get(f"{BASE_LOCALIDADES}/{cod_uf}/municipios", follow_redirects=True)
    r.raise_for_status()
    return [{"cod": int(m["id"]), "nome": m["nome"]} for m in r.json()]


def _sem_numero(numero_txt: str, modificador: str) -> tuple[int | None, bool]:
    if numero_txt in ("", None):
        return None, True
    n = int(numero_txt)
    if n == 0 or (modificador or "").strip().upper() == "SN":
        return (n if n else None), True
    return n, False


def _logradouro_norm_bruto(tipo: str, titulo: str, nome: str) -> str:
    """Concatena tipo+título+nome já EXPANDIDO (mesma função usada na consulta) antes do unaccent/upper, que
    é feito em SQL no UPDATE final — garante que carga e consulta passem pela mesma dobra de acento."""
    partes = [p for p in (tipo, titulo, nome) if p]
    return expandir_abreviacoes(" ".join(partes))


def preparar_lote(linhas: list[dict]) -> io.StringIO:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL, escapechar="\\")
    for linha in linhas:
        w.writerow(linha)
    buf.seek(0)
    return buf


def instalar(sigla: str, *, teto_bytes: int, forcar: bool, arquivo_local: str | None,
             manter_download: bool) -> dict:
    sigla = sigla.upper()
    if sigla not in SIGLA_PARA_COD:
        raise SystemExit(f"UF desconhecida: {sigla!r} (esperado uma sigla de {sorted(SIGLA_PARA_COD)})")
    cod_uf = SIGLA_PARA_COD[sigla]
    url = f"{BASE_CNEFE}/{cod_uf:02d}_{sigla}.zip"
    dir_download = ROOT / "var" / "geocodificador"
    dir_download.mkdir(parents=True, exist_ok=True)
    zip_path = dir_download / f"{cod_uf:02d}_{sigla}.zip"

    t0 = time.monotonic()
    with httpx.Client(timeout=120.0, headers={"User-Agent": USER_AGENT}) as cliente:
        if arquivo_local:
            zip_path = Path(arquivo_local)
            arquivo_bytes = zip_path.stat().st_size
            sha256_zip = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            _log(f"usando arquivo local {zip_path} ({arquivo_bytes} bytes)")
        else:
            arquivo_bytes = medir_tamanho(cliente, url)
            _log(f"{url} -> {arquivo_bytes} bytes ({arquivo_bytes / 1024 / 1024:.1f} MiB)")
            if arquivo_bytes > teto_bytes and not forcar:
                raise SystemExit(
                    f"arquivo de {sigla} tem {arquivo_bytes} bytes, acima do teto de {teto_bytes} "
                    f"(D28; use --forcar para ignorar)"
                )
            sha256_zip = baixar(cliente, url, zip_path)
            _log(f"baixado, sha256={sha256_zip}")
        municipios = buscar_municipios(cliente, cod_uf)
    _log(f"{len(municipios)} municípios de {sigla} (IBGE localidades)")

    con = _conectar()
    con.autocommit = False
    try:
        with con.cursor() as cur:
            cur.execute("SELECT 1 FROM plat.geo_uf WHERE cod = %s", (cod_uf,))
            if cur.fetchone() is None:
                nomes_uf = {
                    11: "Rondônia", 12: "Acre", 13: "Amazonas", 14: "Roraima", 15: "Pará", 16: "Amapá",
                    17: "Tocantins", 21: "Maranhão", 22: "Piauí", 23: "Ceará", 24: "Rio Grande do Norte",
                    25: "Paraíba", 26: "Pernambuco", 27: "Alagoas", 28: "Sergipe", 29: "Bahia",
                    31: "Minas Gerais", 32: "Espírito Santo", 33: "Rio de Janeiro", 35: "São Paulo",
                    41: "Paraná", 42: "Santa Catarina", 43: "Rio Grande do Sul", 50: "Mato Grosso do Sul",
                    51: "Mato Grosso", 52: "Goiás", 53: "Distrito Federal",
                }
                cur.execute("INSERT INTO plat.geo_uf (cod, sigla, nome) VALUES (%s, %s, %s)",
                            (cod_uf, sigla, nomes_uf[cod_uf]))
            for m in municipios:
                cur.execute(
                    "INSERT INTO plat.geo_municipio (cod, cod_uf, nome, nome_norm) "
                    "VALUES (%s, %s, %s, upper(public.unaccent(%s))) "
                    "ON CONFLICT (cod) DO UPDATE SET nome = EXCLUDED.nome, nome_norm = EXCLUDED.nome_norm",
                    (m["cod"], cod_uf, m["nome"], m["nome"]),
                )
            # reinstalar a UF: apaga o que já havia dela (idempotente, nunca duplica)
            cur.execute("DELETE FROM plat.geo_endereco WHERE cod_uf = %s", (cod_uf,))

            nome_membro, csv_bytes, linhas_total = None, 0, 0
            with zipfile.ZipFile(zip_path) as z:
                nome_membro = z.namelist()[0]
                csv_bytes = z.getinfo(nome_membro).file_size
                with z.open(nome_membro) as bruto:
                    texto = io.TextIOWrapper(bruto, encoding="utf-8", newline="")
                    leitor = csv.DictReader(texto, delimiter=";")
                    lote: list[dict] = []
                    for linha in leitor:
                        numero, sem_num = _sem_numero(linha["NUM_ENDERECO"], linha["DSC_MODIFICADOR"])
                        logr_norm = _logradouro_norm_bruto(
                            linha["NOM_TIPO_SEGLOGR"], linha["NOM_TITULO_SEGLOGR"], linha["NOM_SEGLOGR"]
                        )
                        loc_norm = linha["DSC_LOCALIDADE"] or ""
                        face_id = f"{linha['COD_SETOR']}/{linha['NUM_QUADRA']}/{linha['NUM_FACE']}"
                        lote.append({
                            "cod_unico_endereco": linha["COD_UNICO_ENDERECO"], "cod_uf": cod_uf,
                            "cod_municipio": linha["COD_MUNICIPIO"], "cod_setor": linha["COD_SETOR"],
                            "num_quadra": linha["NUM_QUADRA"], "num_face": linha["NUM_FACE"],
                            "face_id": face_id, "cep": linha["CEP"], "localidade": linha["DSC_LOCALIDADE"],
                            "localidade_norm": loc_norm, "tipo_logradouro": linha["NOM_TIPO_SEGLOGR"],
                            "titulo_logradouro": linha["NOM_TITULO_SEGLOGR"], "nome_logradouro": linha["NOM_SEGLOGR"],
                            "logradouro_norm": logr_norm, "numero": numero, "sem_numero": sem_num,
                            "modificador": linha["DSC_MODIFICADOR"], "especie": linha["COD_ESPECIE"],
                            "nivel_geo": linha["NV_GEO_COORD"], "lat": linha["LATITUDE"], "lon": linha["LONGITUDE"],
                        })
                        if len(lote) >= LOTE_COPY:
                            _copiar_lote(cur, lote)
                            linhas_total += len(lote)
                            lote = []
                    if lote:
                        _copiar_lote(cur, lote)
                        linhas_total += len(lote)

            # dobra de acento/caixa em SQL (unaccent, mesma função da consulta) e geom a partir de lat/lon
            cur.execute(
                "UPDATE plat.geo_endereco SET logradouro_norm = upper(public.unaccent(logradouro_norm)), "
                "  localidade_norm = upper(public.unaccent(localidade_norm)) "
                "WHERE cod_uf = %s AND localidade_norm !~ '^[A-Z0-9 ]*$'",
                (cod_uf,),
            )
            cur.execute(
                "UPDATE plat.geo_endereco SET logradouro_norm = upper(public.unaccent(logradouro_norm)) "
                "WHERE cod_uf = %s AND logradouro_norm ~ '[^A-Z0-9 ]'",
                (cod_uf,),
            )
            cur.execute(
                "UPDATE plat.geo_municipio m SET centro_lat = s.lat, centro_lon = s.lon, enderecos = s.n "
                "FROM (SELECT cod_municipio, AVG(lat) AS lat, AVG(lon) AS lon, COUNT(*) AS n "
                "      FROM plat.geo_endereco WHERE cod_uf = %s GROUP BY cod_municipio) s "
                "WHERE m.cod = s.cod_municipio",
                (cod_uf,),
            )
            duracao_s = time.monotonic() - t0
            cur.execute(
                "INSERT INTO plat.geo_instalacao (cod_uf, sigla, fonte_url, arquivo_bytes, csv_bytes, linhas, "
                "  municipios, duracao_s, sha256_zip) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (cod_uf) DO UPDATE SET sigla = EXCLUDED.sigla, fonte_url = EXCLUDED.fonte_url, "
                "  arquivo_bytes = EXCLUDED.arquivo_bytes, csv_bytes = EXCLUDED.csv_bytes, "
                "  linhas = EXCLUDED.linhas, municipios = EXCLUDED.municipios, duracao_s = EXCLUDED.duracao_s, "
                "  sha256_zip = EXCLUDED.sha256_zip, instalado_em = now()",
                (cod_uf, sigla, url if not arquivo_local else f"local:{arquivo_local}", arquivo_bytes, csv_bytes,
                 linhas_total, len(municipios), duracao_s, sha256_zip),
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    if not manter_download and not arquivo_local:
        zip_path.unlink(missing_ok=True)
    resultado = {
        "uf": sigla, "cod_uf": cod_uf, "arquivo_bytes": arquivo_bytes, "csv_bytes": csv_bytes,
        "linhas": linhas_total, "municipios": len(municipios), "duracao_s": round(duracao_s, 1),
        "sha256_zip": sha256_zip,
    }
    _log(f"concluído: {resultado}")
    return resultado


def _escapar_copy(valor) -> str:
    """Escape do formato TEXT do COPY (não é CSV): \\N é NULL; barra invertida, tab, \\n e \\r escapados."""
    if valor is None or valor == "":
        return r"\N"
    s = str(valor)
    return (s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r"))


def _copiar_lote(cur, lote: list[dict]) -> None:
    colunas = (
        "cod_unico_endereco", "cod_uf", "cod_municipio", "cod_setor", "num_quadra", "num_face", "face_id",
        "cep", "localidade", "localidade_norm", "tipo_logradouro", "titulo_logradouro", "nome_logradouro",
        "logradouro_norm", "numero", "sem_numero", "modificador", "especie", "nivel_geo", "lat", "lon", "geom",
    )
    buf = io.StringIO()
    for r in lote:
        r = dict(r)
        r["geom"] = f"SRID=4326;POINT({r['lon']} {r['lat']})"
        r["sem_numero"] = "t" if r["sem_numero"] else "f"
        buf.write("\t".join(_escapar_copy(r.get(c)) for c in colunas))
        buf.write("\n")
    buf.seek(0)
    cur.copy_expert(f"COPY plat.geo_endereco ({', '.join(colunas)}) FROM STDIN", buf)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", required=True, help="sigla da UF (ex.: RR)")
    ap.add_argument("--teto-bytes", type=int, default=TETO_BYTES_PADRAO)
    ap.add_argument("--forcar", action="store_true", help="ignora o teto de tamanho (D28)")
    ap.add_argument("--sem-download", metavar="ARQUIVO.zip", default=None,
                     help="usa um zip já baixado em vez de buscar no IBGE (depuração/teste)")
    ap.add_argument("--manter-download", action="store_true", help="não apaga o zip baixado ao final")
    args = ap.parse_args()
    resultado = instalar(args.uf, teto_bytes=args.teto_bytes, forcar=args.forcar,
                         arquivo_local=args.sem_download, manter_download=args.manter_download)
    print(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
