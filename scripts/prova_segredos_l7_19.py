#!/usr/bin/env python3
"""Orquestra a PROVA do item L7-19-segredos-e-certificados inteira, do zero até a limpeza, sem nunca
reiniciar/parar `plat-api`, `plat-worker`, `nginx` ou `postgres` de produção (limite duro deste turno).

Cria, para a duração da prova:
  - `/etc/plat/segredos-teste-l7-19/` (credenciais SINTÉTICAS, nunca um valor real da casa);
  - duas roles de Postgres descartáveis (`plat_teste19_app`, `plat_teste19_worker`) + 2 linhas de
    `pg_hba.conf` (removidas ao final; `pg_reload_conf()`, nunca restart do serviço);
  - 3 pares soquete+serviço systemd `plat-teste-segredo-{a,b,garage}` (portas 8185-8187, fora da faixa
    8150-8159 do produto e fora das portas das trilhas de integração — 8197-8199 colidiu com o worker
    da fila em 07/09) rodando `scripts/teste_segredo_servico.py`, todos com socket activation
    (`Sockets=`) — é a técnica que segura conexão nova na fila do kernel durante um restart, medida
    aqui como a razão de "zero 5xx" não ser um acaso de sorte;
  - um `garage-teste.toml` (não é o Garage real: só o arquivo que `scripts/segredo_rotacionar.py`
    edita, exatamente como editaria o de verdade).

Roda `sudo venv/bin/python scripts/segredo_rotacionar.py rotacionar <NOME> ...` para cada um dos 5
segredos contra essa infraestrutura, grava `tests/medidas/_prova_segredos_bruta.json` (de onde o
`tests/medidas/L7-19.json` curado cita os números) e desfaz tudo no final (units, roles, pg_hba,
diretório de credenciais), sucesso ou erro — `finally` cobre a limpeza inteira.

Uso: sudo venv/bin/python scripts/prova_segredos_l7_19.py
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CRED_DIR = Path("/etc/plat/segredos-teste-l7-19")
PG_HBA = Path("/etc/postgresql/16/main/pg_hba.conf")
DB = "iagro_sat"
UNIDADES_SYSTEMD = Path("/etc/systemd/system")
GARAGE_TOML_TESTE = CRED_DIR / "garage-teste.toml"

PORTAS = {"a": 8187, "b": 8186, "garage": 8185}
ROLE_APP = "plat_teste19_app"
ROLE_WORKER = "plat_teste19_worker"

# cláusula do portão "0 erro 5xx durante a rotação, medido pelo k6 curto": a régua é um k6 externo
# (scripts/k6_saude_5xx.js, 1 VU em laço fechado), processo separado do que está sendo medido. O
# martelo interno do segredo_rotacionar.py continua existindo — é o log da própria rotação — mas o
# número que responde à cláusula sai do k6. Binário em PLAT_K6, no PATH, ou em ~/tools/k6/k6 desta
# máquina (pré-requisito da prova, anotado em docs/RUNBOOKS/segredos.md).
K6 = os.environ.get("PLAT_K6") or shutil.which("k6") or "/home/dev/tools/k6/k6"
K6_JS = RAIZ / "scripts" / "k6_saude_5xx.js"

registro_para_desfazer: list[str] = []  # log em português do que foi criado, na ordem — a limpeza anda ao contrário


def sh(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, text=True, capture_output=True, **kw)


def psql(sql: str) -> None:
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", DB, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], check=True
    )


def unidade_texto(nome: str, porta: int) -> tuple[str, str]:
    socket_txt = f"""[Unit]
Description=soquete DE TESTE {nome} (item L7-19-segredos-e-certificados; nunca produto real)

[Socket]
ListenStream=127.0.0.1:{porta}

[Install]
WantedBy=sockets.target
"""
    service_txt = f"""[Unit]
Description=serviço DE TESTE {nome} (item L7-19-segredos-e-certificados; prova, não produto — criado e
apagado por scripts/prova_segredos_l7_19.py)
Requires={nome}.socket

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory={RAIZ}
Environment=PYTHONNOUSERSITE=1
EnvironmentFile=-{CRED_DIR}/ambiente-{nome.rsplit('-', 1)[-1]}.env
LoadCredential=PLAT_SECRET:{CRED_DIR}/PLAT_SECRET
LoadCredential=PLAT_SECRET_ANTERIOR:{CRED_DIR}/PLAT_SECRET_ANTERIOR
LoadCredential=PLAT_DSN:{CRED_DIR}/PLAT_DSN
LoadCredential=PLAT_DSN_WORKER:{CRED_DIR}/PLAT_DSN_WORKER
LoadCredential=PLAT_GARAGE_ADMIN_TOKEN:{CRED_DIR}/PLAT_GARAGE_ADMIN_TOKEN
ExecStart={RAIZ}/venv/bin/python {RAIZ}/scripts/teste_segredo_servico.py
Sockets={nome}.socket
Restart=no

[Install]
WantedBy=multi-user.target
"""
    return socket_txt, service_txt


def escrever_credential(nome: str, valor: str) -> None:
    caminho = CRED_DIR / nome
    caminho.write_text(valor, encoding="utf-8")
    os.chmod(caminho, 0o600)
    sh("chown", "root:root", str(caminho))


def escrever_ambiente(sufixo: str, linhas: list[str]) -> None:
    (CRED_DIR / f"ambiente-{sufixo}.env").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def esperar_saude(porta: int, tentativas: int = 50) -> bool:
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1.0) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    return False


def preparar() -> dict:
    print("== preparo: diretório de credenciais de teste")
    if CRED_DIR.exists():
        raise SystemExit(f"{CRED_DIR} já existe — rode a limpeza de uma prova anterior antes")
    # as 3 portas têm de estar livres ANTES de criar qualquer coisa: 07/09 a faixa antiga (8197-8199)
    # colidiu com o worker da fila de junção (trilha-integra escuta 8199) e o preparo morreu na cara;
    # portas novas 8185-8187, e mesmo assim só se segue se ninguém estiver escutando nelas.
    import socket as _socket

    for apelido, porta in PORTAS.items():
        with _socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                raise SystemExit(
                    f"porta {porta} (unidade de teste '{apelido}') já está em uso — a prova não cria "
                    "nada em cima de serviço dos outros; libere a porta ou troque PORTAS"
                )
    # reset-failed um a um e sem check: unidade que não existe/carregou devolve erro no systemctl,
    # e é exatamente o caso comum (só há algo a limpar depois de uma prova interrompida)
    for u in ("a", "b", "garage"):
        subprocess.run(["systemctl", "reset-failed", f"plat-teste-segredo-{u}.socket"],
                       check=False, capture_output=True)
        subprocess.run(["systemctl", "reset-failed", f"plat-teste-segredo-{u}.service"],
                       check=False, capture_output=True)
    sh("install", "-d", "-m", "0700", "-o", "root", "-g", "root", str(CRED_DIR))
    registro_para_desfazer.append(f"diretorio:{CRED_DIR}")

    segredo_inicial = secrets.token_hex(32)
    escrever_credential("PLAT_SECRET", segredo_inicial)
    escrever_credential("PLAT_SECRET_ANTERIOR", "")

    print("== preparo: 2 roles de Postgres descartáveis + pg_hba")
    senha_app = secrets.token_hex(16)
    senha_worker = secrets.token_hex(16)
    for role, senha in ((ROLE_APP, senha_app), (ROLE_WORKER, senha_worker)):
        # resíduo de uma prova anterior interrompida (GRANT CONNECT sem DROP OWNED BY antes do DROP ROLE);
        # `DROP OWNED BY` não aceita `IF EXISTS` no nome do papel, então tenta e ignora se o papel não existir
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-d", DB, "-Atc", f"DROP OWNED BY {role}"],
            check=False, capture_output=True,
        )
        psql(f"DROP ROLE IF EXISTS {role}")
        psql(f"CREATE ROLE {role} LOGIN PASSWORD '{senha}'")
        psql(f"GRANT CONNECT ON DATABASE {DB} TO {role}")
        registro_para_desfazer.append(f"role:{role}")
    linhas_hba = [
        f"host    {DB:<15} {ROLE_APP:<15} 127.0.0.1/32            scram-sha-256\n",
        f"host    {DB:<15} {ROLE_WORKER:<15} 127.0.0.1/32            scram-sha-256\n",
    ]
    texto_hba = PG_HBA.read_text(encoding="utf-8")
    if any(li in texto_hba for li in linhas_hba):
        raise SystemExit("linha de pg_hba da prova já existe — limpeza anterior incompleta")
    with PG_HBA.open("a", encoding="utf-8") as f:
        f.writelines(linhas_hba)
    registro_para_desfazer.append("pg_hba")
    sh("sudo", "-u", "postgres", "psql", "-Atc", "SELECT pg_reload_conf()")

    escrever_credential("PLAT_DSN", f"postgresql://{ROLE_APP}:{senha_app}@127.0.0.1:5432/{DB}")
    escrever_credential("PLAT_DSN_WORKER", f"postgresql://{ROLE_WORKER}:{senha_worker}@127.0.0.1:5432/{DB}")
    token_inicial = secrets.token_urlsafe(32)
    escrever_credential("PLAT_GARAGE_ADMIN_TOKEN", token_inicial)
    conteudo_toml = f'admin_token = "{token_inicial}"\n# arquivo SINTÉTICO da prova L7-19\n'
    GARAGE_TOML_TESTE.write_text(conteudo_toml, encoding="utf-8")
    os.chmod(GARAGE_TOML_TESTE, 0o600)

    print("== preparo: 3 pares soquete+serviço systemd (portas 8197-8199)")
    escrever_ambiente(
        "a",
        ["PLAT_TESTE_CREDS=PLAT_SECRET,PLAT_SECRET_ANTERIOR,PLAT_GARAGE_ADMIN_TOKEN", "PLAT_TESTE_DSN_CRED=PLAT_DSN"],
    )
    escrever_ambiente("b", ["PLAT_TESTE_DSN_CRED=PLAT_DSN"])
    escrever_ambiente("garage", ["PLAT_TESTE_TOKEN_CRED=PLAT_GARAGE_ADMIN_TOKEN"])
    for suf, porta in PORTAS.items():
        nome = f"plat-teste-segredo-{suf}"
        socket_txt, service_txt = unidade_texto(nome, porta)
        (UNIDADES_SYSTEMD / f"{nome}.socket").write_text(socket_txt, encoding="utf-8")
        (UNIDADES_SYSTEMD / f"{nome}.service").write_text(service_txt, encoding="utf-8")
        registro_para_desfazer.append(f"unidade:{nome}")
    sh("systemctl", "daemon-reload")
    for suf, porta in PORTAS.items():
        nome = f"plat-teste-segredo-{suf}"
        sh("systemctl", "start", f"{nome}.socket")
        sh("systemctl", "start", f"{nome}.service")
        if not esperar_saude(porta):
            raise SystemExit(f"{nome} não respondeu em /saude depois de start")
    print("preparo concluído: 3 serviços de teste no ar, 2 roles de banco, credenciais sintéticas")
    return {"senha_app_inicial_sha": senha_app[:0] or "oculta", "token_inicial_gerado": True}


def k6_iniciar(portas: list[int]) -> tuple[subprocess.Popen, Path]:
    """k6 curto martelando /saude das portas em laço fechado. Para com SIGINT — o k6 roda o
    handleSummary mesmo assim e grava o JSON no caminho de K6_SAIDA."""
    if not Path(K6).exists():
        raise SystemExit(
            f"k6 não achado ({K6}): a cláusula do portão exige a medição de 5xx PELO K6. "
            "Instale em ~/tools/k6 (tar.gz de github.com/grafana/k6/releases) ou aponte PLAT_K6."
        )
    saida = Path(tempfile.mkstemp(prefix="k6-saude-", suffix=".json")[1])
    env = dict(os.environ)
    env["K6_URLS"] = json.dumps([f"http://127.0.0.1:{p}/saude" for p in portas])
    env["K6_SAIDA"] = str(saida)
    proc = subprocess.Popen(
        # --duration longa de propósito: sem ela o k6 roda UMA iteração por VU e sai (medimos 6
        # requisições em 4 rotações — janela vazia); quem encerra é o SIGINT do k6_colher, que o k6
        # honra rodando o handleSummary com tudo o que mediu até ali.
        [K6, "run", "--quiet", "--duration", "10m", str(K6_JS)], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # arranque do binário + compilação do JS + 1ª requisição: o martelo já está de pé antes de a
    # rotação começar (e o segredo_rotacionar.py ainda gasta ~1 s próprio antes do 1º restart)
    time.sleep(2.0)
    return proc, saida


def k6_colher(proc: subprocess.Popen, saida: Path) -> dict:
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise SystemExit("k6 não encerrou no SIGINT em 30 s — sem resumo, cláusula não checada") from None
    d = json.loads(saida.read_text(encoding="utf-8"))
    metricas = d.get("metrics", {})
    return {
        "requisicoes": int(metricas.get("http_reqs", {}).get("values", {}).get("count", 0)),
        "codigo_5xx": int(metricas.get("saude_5xx", {}).get("values", {}).get("count", 0)),
    }


def rodar_rotacao(nome_segredo: str, extra: list[str], portas_martelo: list[int]) -> dict:
    print(f"\n== rotacionando {nome_segredo}")
    cmd = [
        sys.executable, str(RAIZ / "scripts" / "segredo_rotacionar.py"), "rotacionar", nome_segredo,
        "--cred-dir", str(CRED_DIR), "--db", DB, "--pg-hba", str(PG_HBA),
        *extra,
    ]
    martelo, resumo_k6 = k6_iniciar(portas_martelo)
    try:
        r = subprocess.run(cmd, text=True, capture_output=True)
    finally:
        medida_k6 = k6_colher(martelo, resumo_k6)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"rotação de {nome_segredo} falhou (código {r.returncode})")
    print(r.stdout)
    resultado = json.loads(r.stdout)
    resultado["k6"] = medida_k6
    return resultado


def limpar() -> None:
    print("\n== limpeza (na ordem inversa do que foi criado)")
    for item in reversed(registro_para_desfazer):
        tipo, _, valor = item.partition(":")
        try:
            if tipo == "unidade":
                subprocess.run(["systemctl", "stop", f"{valor}.service"], check=False)
                subprocess.run(["systemctl", "stop", f"{valor}.socket"], check=False)
                subprocess.run(["systemctl", "disable", f"{valor}.service", f"{valor}.socket"], check=False,
                                capture_output=True)
                (UNIDADES_SYSTEMD / f"{valor}.service").unlink(missing_ok=True)
                (UNIDADES_SYSTEMD / f"{valor}.socket").unlink(missing_ok=True)
            elif tipo == "pg_hba":
                texto = PG_HBA.read_text(encoding="utf-8")
                linhas = [li for li in texto.splitlines(keepends=True)
                          if ROLE_APP not in li and ROLE_WORKER not in li]
                PG_HBA.write_text("".join(linhas), encoding="utf-8")
                subprocess.run(["sudo", "-u", "postgres", "psql", "-Atc", "SELECT pg_reload_conf()"], check=False)
            elif tipo == "role":
                subprocess.run(
                    ["sudo", "-u", "postgres", "psql", "-d", DB, "-Atc", f"DROP OWNED BY {valor}"], check=False
                )
                subprocess.run(
                    ["sudo", "-u", "postgres", "psql", "-d", DB, "-Atc", f"DROP ROLE IF EXISTS {valor}"], check=False
                )
            elif tipo == "diretorio":
                pass  # apagado por último, fora do loop (precisa terminar as unidades primeiro)
        except Exception as e:  # noqa: BLE001 — limpeza é best-effort documentado, nunca esconde o que falhou
            print(f"aviso: falha ao desfazer {item}: {e}", file=sys.stderr)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    if CRED_DIR.exists():
        subprocess.run(["rm", "-rf", str(CRED_DIR)], check=False)
    print("limpeza concluída")


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("rode como root: sudo venv/bin/python scripts/prova_segredos_l7_19.py")
    resultado: dict = {
        "item": "L7-19-segredos-e-certificados",
        "quando_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        preparar()
        rotacoes = {}
        rotacoes["PLAT_SECRET"] = rodar_rotacao(
            "PLAT_SECRET",
            [
                "--unidade-api", "plat-teste-segredo-a", "--porta-api", str(PORTAS["a"]),
                # worker também reinicia (adversário T7: ele carrega settings uma vez e decifra
                # dentro de jobs — sem restart ficaria semanas com a chave velha como atual)
                "--unidade-worker", "plat-teste-segredo-b", "--porta-worker", str(PORTAS["b"]),
            ],
            [PORTAS["a"], PORTAS["b"]],
        )
        rotacoes["PLAT_DSN"] = rodar_rotacao(
            "PLAT_DSN",
            [
                "--unidade-api", "plat-teste-segredo-a", "--porta-api", str(PORTAS["a"]),
                "--unidade-worker", "plat-teste-segredo-b", "--porta-worker", str(PORTAS["b"]),
                "--role-app", ROLE_APP,
            ],
            [PORTAS["a"], PORTAS["b"]],
        )
        # unidade b muda de papel agora: era o 2º elo da cadeia de PLAT_DSN, vira a única consumidora de
        # PLAT_DSN_WORKER — precisa apontar para o outro credential antes da próxima rotação
        escrever_ambiente("b", ["PLAT_TESTE_DSN_CRED=PLAT_DSN_WORKER"])
        rotacoes["PLAT_DSN_WORKER"] = rodar_rotacao(
            "PLAT_DSN_WORKER",
            [
                "--unidade-worker", "plat-teste-segredo-b", "--porta-worker", str(PORTAS["b"]),
                "--role-worker", ROLE_WORKER,
            ],
            [PORTAS["b"]],
        )
        rotacoes["PLAT_GARAGE_ADMIN_TOKEN"] = rodar_rotacao(
            "PLAT_GARAGE_ADMIN_TOKEN",
            [
                "--unidade-api", "plat-teste-segredo-a", "--porta-api", str(PORTAS["a"]),
                "--unidade-garage", "plat-teste-segredo-garage", "--porta-garage-admin", str(PORTAS["garage"]),
                "--saude-garage", "/saude", "--caminho-admin-garage", "/admin",
                "--garage-toml", str(GARAGE_TOML_TESTE),
            ],
            [PORTAS["a"], PORTAS["garage"]],
        )
        resultado["rotacoes"] = rotacoes
        resultado["status"] = "ok"
    except Exception as e:  # noqa: BLE001 — a prova precisa terminar em JSON mesmo quando falha, para diagnóstico
        resultado["status"] = "erro"
        resultado["erro"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        destino = RAIZ / "tests" / "medidas" / "_prova_segredos_bruta.json"
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        limpar()
    print(f"\nresultado bruto em {destino}")


if __name__ == "__main__":
    main()
