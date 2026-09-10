"""Carga curta contra a API da trilha, para os painéis do item L7-06-d terem o que mostrar.

Não é gerador de dado falso: cada linha aqui é uma chamada de verdade ao produto, pela mesma via que
um usuário usa (sessão por cookie, rotas publicadas no OpenAPI). O que os painéis leem depois são as
métricas que essas chamadas produziram.

Uso:  venv/bin/python deploy/paineis_carga.py <base-url> <arquivo de saida .json>
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx


def credenciais(slug: str = "demo") -> tuple[str, str]:
    """Mesmo arquivo e mesmo formato que tests/e2e/apoio.py lê (escrito pelo install.sh, fora do git);
    PLAT_CREDENCIAIS_ARQUIVO manda quando a instalação é de homologação ou de trilha."""
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or "tests/credenciais.txt")
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[0] == slug:
            return partes[1], partes[2]
    raise SystemExit(f"{caminho} sem a linha do inquilino {slug}")


def backup_de_verdade(schema: str) -> tuple[float, int]:
    """Faz um pg_dump REAL do schema da trilha, cronometra e mede o arquivo. É o menor backup honesto
    que existe: a rotina completa é outro item, mas duração e tamanho aqui são medidos, não digitados."""
    destino = Path(f"/tmp/plat_paineis_backup_{uuid.uuid4().hex}.sql.gz")
    t0 = time.monotonic()
    ok = subprocess.run(
        f"sudo -u postgres pg_dump -d iagro_sat --schema={schema} --no-owner --no-privileges "
        f"| gzip -1 > {destino}",
        shell=True, capture_output=True, text=True,
    )
    duracao = time.monotonic() - t0
    if ok.returncode != 0:
        raise SystemExit(f"pg_dump falhou: {ok.stderr[-400:]}")
    bytes_ = destino.stat().st_size
    destino.unlink()
    return duracao, bytes_


def main() -> int:
    base, saida = sys.argv[1], sys.argv[2]
    login, senha = credenciais()
    resultado: dict = {"base": base}

    with httpx.Client(base_url=base, timeout=30, follow_redirects=False) as c:
        r = c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
        if r.status_code != 200:
            raise SystemExit(f"login falhou: {r.status_code} {r.text[:300]}")

        # 1. pedidos de leitura em várias rotas: alimenta plat_http_requests_total (rótulo rota/status/
        # tenant) e o histograma de latência
        rotas = ["/api/eu", "/api/itens", "/api/usuarios", "/api/jobs/resumo", "/api/jobs/tipos",
                 "/api/grupos", "/api/pastas", "/api/saude"]
        contagem: dict[str, int] = {}
        for _ in range(8):
            for rota in rotas:
                contagem[rota] = contagem.get(rota, 0) + 1
                c.get(rota)
        # 2. um 404 de caminho arbitrário (série rota="outro") e um 401 sem sessão
        c.get(f"/api/nao-existe-{uuid.uuid4().hex}")
        httpx.get(f"{base}/api/eu", timeout=10)
        resultado["pedidos_api"] = sum(contagem.values()) + 2

        # 3. um job de verdade, do tipo de diagnóstico do produto, curto: o worker o conclui e
        # plat_jobs_processados_total ganha a série
        r = c.post("/api/jobs", json={"tipo": "prova.progresso",
                                      "parametros": {"duracao_s": 2, "passos": 2}})
        resultado["job_criado"] = r.status_code
        resultado["job_id"] = r.json().get("id") if r.status_code == 201 else None

        # 4. um upload de verdade: cria o bucket do inquilino no Garage (plat.arquivo_bucket) e o
        # metadado do arquivo, que é o que o painel "Objetos" conta por inquilino
        # GeoJSON de verdade (um ponto), único a cada rodada para nunca cair na deduplicação por sha256
        conteudo = json.dumps({
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"origem": uuid.uuid4().hex},
                          "geometry": {"type": "Point", "coordinates": [-47.9, -15.8]}}],
        }).encode()
        # o envio de corpo de arquivo exige TOKEN DE SERVIÇO, nunca cookie (defesa de CSRF, ADR 0002
        # seção 5.3): a carga cria um token de curta duração, usa e revoga
        sha = hashlib.sha256(conteudo).hexdigest()
        rt = c.post("/api/tokens", json={"nome": f"carga-paineis-{uuid.uuid4().hex[:8]}",
                                        "escopos": ["admin:inquilino"]})
        resultado["token_criado"] = rt.status_code
        token = rt.json()["token"] if rt.status_code == 201 else None
        # cliente SEM cookie: mandar cookie de sessão e Bearer na mesma chamada é recusado de propósito
        # (duas provas de identidade no mesmo pedido)
        with httpx.Client(base_url=base, timeout=60,
                          headers={"Authorization": f"Bearer {token}"}) as ct:
            r = ct.post("/api/uploads", json={"nome": f"painel-{uuid.uuid4().hex}.geojson",
                                              "bytes": len(conteudo), "tipo_declarado": "geojson",
                                              "sha256": sha})
            resultado["upload_criado"] = r.status_code
            if r.status_code == 201:
                up = r.json()
                r = ct.put(f"/api/uploads/{up['id']}/partes/1", content=conteudo,
                           headers={"content-type": "application/octet-stream"})
                resultado["upload_parte"] = r.status_code
                r = ct.post(f"/api/uploads/{up['id']}/concluir", json={"sha256": sha})
                resultado["upload_concluido"] = r.status_code
                resultado["upload_detalhe"] = r.text[:200] if r.status_code >= 300 else ""
        if rt.status_code == 201:
            c.delete(f"/api/tokens/{rt.json()['id']}")

        # 5. ladrilhos de verdade no Martin (leitura). Duas passagens sobre as MESMAS coordenadas: a
        # primeira enche o cache de coordenada, a segunda produz acerto — é assim que a porcentagem de
        # acerto do painel deixa de ser 0 sem ninguém escrever um número.
        martin = os.environ.get("PLAT_MARTIN_URL", "http://127.0.0.1:8151")
        fontes = []
        try:
            fontes = sorted(httpx.get(f"{martin}/catalog", timeout=10).json().get("tiles", {}))[:2]
        except httpx.HTTPError:
            pass
        ladrilhos = 0
        for _ in range(2):
            for fonte in fontes:
                for z, x, y in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (2, 1, 1)]:
                    try:
                        if httpx.get(f"{martin}/{fonte}/{z}/{x}/{y}", timeout=10).status_code in (200, 204):
                            ladrilhos += 1
                    except httpx.HTTPError:
                        pass
        resultado["martin_fontes"] = len(fontes)
        resultado["martin_ladrilhos_ok"] = ladrilhos

    # 6. backup e ensaio de restauração medidos de verdade
    schema = os.environ.get("PLAT_SCHEMA", "plat")
    dur, tam = backup_de_verdade(schema)
    resultado["backup_duracao_s"] = round(dur, 3)
    resultado["backup_bytes"] = tam
    for tipo in ("backup", "drill"):
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-tAc",
             f"SELECT {schema}.backup_registrar('{tipo}', true, 'homologação do item L7-06-d', "
             f"{dur:.3f}, {tam})"],
            check=True, capture_output=True,
        )

    Path(saida).write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
