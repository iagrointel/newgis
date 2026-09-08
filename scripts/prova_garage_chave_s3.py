#!/usr/bin/env python3
"""Prova a rotação de `PLAT_GARAGE_CHAVE_S3:<slug>` (item L7-19-segredos-e-certificados) contra o Garage
REAL desta máquina — é o único dos 5 segredos cuja rotação de verdade roda em produção real dentro deste
item: nenhuma unidade systemd de produção é tocada (nem sequer reiniciada), porque a API resolve o par de
chaves por SELECT a cada requisição (nunca as guarda em memória de processo).

Cria um bucket DESCARTÁVEL (`plat-provasegredosl719<hex>`, nunca um inquilino real), roda
`scripts/segredo_rotacionar.py rotacionar PLAT_GARAGE_CHAVE_S3:<slug>` e apaga o bucket + as chaves ao
final, sucesso ou erro. Mede também `/saude` de `plat-api` ANTES e DEPOIS (sem reiniciar nada) para provar
que o produto real não sentiu a operação.

Uso: sudo venv/bin/python scripts/prova_garage_chave_s3.py
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.garage import ClienteAdmin  # noqa: E402


def env_real() -> dict[str, str]:
    valores = {}
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.startswith("#"):
            k, _, v = linha.partition("=")
            valores[k] = v
    return valores


def saude_api() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8150/saude", timeout=3.0) as r:
            return r.status
    except Exception:  # noqa: BLE001
        return -1


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("rode como root (lê /etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN): sudo venv/bin/python "
                          "scripts/prova_garage_chave_s3.py")
    env = env_real()
    admin_url = env.get("PLAT_GARAGE_ADMIN_URL", "http://127.0.0.1:3903")
    garage_url = env.get("PLAT_GARAGE_URL", "http://127.0.0.1:3900")
    regiao = env.get("PLAT_GARAGE_REGIAO", "garage")
    prefixo = env.get("PLAT_GARAGE_BUCKET_PREFIXO", "plat-")
    token = Path("/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN").read_text(encoding="utf-8").strip()

    slug = f"provasegredosl719{secrets.token_hex(4)}"
    alias = f"{prefixo}{slug}"
    admin = ClienteAdmin(admin_url, token)

    saude_antes = saude_api()
    print(f"/saude de plat-api ANTES: {saude_antes}")

    resultado: dict = {"item": "L7-19-segredos-e-certificados", "segredo": f"PLAT_GARAGE_CHAVE_S3:{slug}"}
    bucket_id = None
    try:
        bucket = admin.criar_bucket(alias)
        bucket_id = bucket["id"]
        chave_inicial = admin.criar_chave(f"{alias}-rw")
        admin.permitir(bucket_id, chave_inicial["accessKeyId"], ler=True, escrever=True, dono=True)
        print(f"bucket de prova criado: {alias} ({bucket_id[:12]}...)")

        cmd = [
            sys.executable, str(RAIZ / "scripts" / "segredo_rotacionar.py"), "rotacionar",
            f"PLAT_GARAGE_CHAVE_S3:{slug}",
            "--garage-admin-url", admin_url, "--garage-url", garage_url, "--garage-regiao", regiao,
            "--bucket-prefixo", prefixo, "--cred-dir", "/etc/plat/segredos",
        ]
        r = subprocess.run(cmd, text=True, capture_output=True)
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            raise SystemExit(f"rotação falhou (código {r.returncode})")
        resultado.update(json.loads(r.stdout))
    finally:
        saude_depois = saude_api()
        resultado["saude_plat_api_antes"] = saude_antes
        resultado["saude_plat_api_depois"] = saude_depois
        print(f"/saude de plat-api DEPOIS: {saude_depois}")
        if bucket_id is not None:
            # a rotação grava um objeto de prova (_prova_rotacao/heartbeat.txt) com a chave NOVA — apaga
            # com alguma chave ainda viva do bucket antes de tentar apagar o bucket (Garage recusa
            # DeleteBucket não-vazio)
            try:
                chaves_do_bucket = [k for k in admin.listar_chaves() if k.get("name", "").startswith(f"{alias}-rw")]
                for k in chaves_do_bucket:
                    info = admin._chamar("GET", f"/v2/GetKeyInfo?id={k['id']}&showSecretKey=true")
                    from app.garage import ClienteS3

                    cli = ClienteS3(garage_url, info["accessKeyId"], info["secretAccessKey"], regiao=regiao)
                    try:
                        cli.delete(alias, "_prova_rotacao/heartbeat.txt")
                    except Exception:  # noqa: BLE001 — chave pode já não valer mais (a antiga foi apagada)
                        pass
            except Exception as e:  # noqa: BLE001
                print(f"aviso: falha ao esvaziar o bucket antes de apagar: {e}", file=sys.stderr)
            for k in admin.listar_chaves():
                if k.get("name", "").startswith(alias):
                    try:
                        admin.apagar_chave(k["id"])
                    except Exception as e:  # noqa: BLE001
                        print(f"aviso: falha ao apagar chave {k['id']}: {e}", file=sys.stderr)
            try:
                admin.apagar_bucket(bucket_id)
                print(f"bucket de prova apagado: {alias}")
            except Exception as e:  # noqa: BLE001
                print(f"aviso: falha ao apagar bucket {alias}: {e}", file=sys.stderr)

    destino = RAIZ / "tests" / "medidas" / "_prova_garage_chave_s3.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nresultado em {destino}")


if __name__ == "__main__":
    main()
