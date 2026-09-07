#!/usr/bin/env python3
"""`plat segredo rotacionar <nome>` (item L7-19-segredos-e-certificados; docs/RUNBOOKS/segredos.md).

Rotaciona um dos 5 segredos do plat sem editar unidade systemd e com a menor baixa possível: gera valor
novo, atualiza a role no banco ou a chave no Garage quando aplicável, grava o credential
(`/etc/plat/segredos/<NOME>`, 0600, dono root) e reinicia só a(s) unidade(s) que leem aquele segredo — uma
de cada vez, cada uma health-checada antes de seguir para a próxima ("reinício em cadeia sem erro").
Durante a janela de restart, um martelo HTTP em `/saude` mede quantas respostas 5xx aconteceram (o portão
exige zero) — nunca confunde isso com "sem baixa": a baixa real (se houver) aparece como erro de conexão,
reportado à parte, nunca escondido dentro da contagem de 5xx.

Os nomes de unidade/porta são PARÂMETROS com valor-padrão de produção (`plat-api`:8150, `plat-worker`:8153)
de propósito: é o mesmo script que roda em produção (`sudo plat segredo rotacionar PLAT_SECRET`, runbook)
e que este item usa para provar o mecanismo contra unidades DE TESTE (`--unidade-api
plat-teste-segredo-a --porta-api 8199 ...`) sem nunca reiniciar plat-api/plat-worker/nginx/postgres de
verdade — ver `scripts/prova_segredos_l7_19.py`, que é quem passa os overrides.

Uso: sudo venv/bin/python scripts/segredo_rotacionar.py rotacionar <NOME> [opções]
NOME em: PLAT_SECRET | PLAT_DSN | PLAT_DSN_WORKER | PLAT_GARAGE_ADMIN_TOKEN | PLAT_GARAGE_CHAVE_S3:<slug>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para `from app.garage import ClienteAdmin`


def sha_curto(valor: str) -> str:
    """Nunca o segredo em si — só o suficiente para provar 'mudou' em log/relatório."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12]


@dataclass
class MedicaoRestart:
    unidade: str
    total_requisicoes: int = 0
    codigo_5xx: int = 0
    codigo_outros_erro: int = 0
    erros_conexao: int = 0
    codigos: dict[str, int] = field(default_factory=dict)
    tempo_ate_saudavel_s: float | None = None
    restart_falhou: bool = False

    def como_dict(self) -> dict:
        return {
            "unidade": self.unidade,
            "total_requisicoes": self.total_requisicoes,
            "codigo_5xx": self.codigo_5xx,
            "codigo_outros_erro": self.codigo_outros_erro,
            "erros_conexao": self.erros_conexao,
            "codigos": self.codigos,
            "tempo_ate_saudavel_s": self.tempo_ate_saudavel_s,
            "restart_falhou": self.restart_falhou,
        }


def _martelo(url: str, parar: threading.Event, medicao: MedicaoRestart, intervalo_s: float = 0.05) -> None:
    while not parar.is_set():
        medicao.total_requisicoes += 1
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                codigo = r.status
        except urllib.error.HTTPError as e:
            codigo = e.code
        except Exception:  # noqa: BLE001 — connection refused/timeout: baixa real, não é 5xx
            medicao.erros_conexao += 1
            time.sleep(intervalo_s)
            continue
        medicao.codigos[str(codigo)] = medicao.codigos.get(str(codigo), 0) + 1
        if 500 <= codigo < 600:
            medicao.codigo_5xx += 1
        elif codigo >= 400:
            medicao.codigo_outros_erro += 1
        time.sleep(intervalo_s)


def reiniciar_e_medir(unidade: str, porta: int, caminho_saude: str = "/saude", timeout_saudavel_s: float = 30.0,
                       folga_pos_s: float = 1.5) -> MedicaoRestart:
    """Martelo começa ANTES do restart, o restart acontece, o martelo continua até `/saude` responder 200
    de novo (ou o teto) + uma folga — só então para. `systemctl restart` é síncrona (bloqueia até a unidade
    reportar ativa ou falhar), então a chamada em si já é o grosso da janela medida."""
    url = f"http://127.0.0.1:{porta}{caminho_saude}"
    medicao = MedicaoRestart(unidade=unidade)
    parar = threading.Event()
    t = threading.Thread(target=_martelo, args=(url, parar, medicao), daemon=True)
    t.start()
    inicio = time.monotonic()
    try:
        subprocess.run(["systemctl", "restart", unidade], check=True, timeout=timeout_saudavel_s)
    except subprocess.CalledProcessError:
        medicao.restart_falhou = True
    for _ in range(int(timeout_saudavel_s * 10)):
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    medicao.tempo_ate_saudavel_s = round(time.monotonic() - inicio, 3)
                    break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    time.sleep(folga_pos_s)
    parar.set()
    t.join(timeout=2.0)
    return medicao


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8").strip()


def _gravar_credential(caminho: Path, valor: str) -> None:
    caminho.write_text(valor, encoding="utf-8")
    os.chmod(caminho, 0o600)
    try:
        import pwd

        os.chown(caminho, pwd.getpwnam("root").pw_uid, pwd.getpwnam("root").pw_gid)
    except (KeyError, PermissionError):
        pass  # fora de root de verdade (teste sem sudo): a permissão importa em produção, não aqui


def _psql(db: str, sql: str) -> None:
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", db, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True, capture_output=True, text=True,
    )


def _autentica(dsn: str) -> bool:
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente  # F9: toda conexão nasce com a fábrica, mesmo só p/ autenticar

    try:
        con = psycopg2.connect(dsn, connect_timeout=3, cursor_factory=CursorSchemaAmbiente)
        con.close()
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- PLAT_SECRET (dupla-chave)
def rotacionar_plat_secret(args) -> dict:
    cred = Path(args.cred_dir)
    atual = _ler(cred / "PLAT_SECRET")
    novo = secrets.token_hex(32)
    # ordem: grava ANTERIOR primeiro (nunca perde o valor que estava valendo), só então troca o atual —
    # se o processo morrer entre as duas escritas, o pior caso é ANTERIOR == atual antigo (settings.py já
    # trata ANTERIOR igual a atual como "sem anterior", nunca como erro).
    _gravar_credential(cred / "PLAT_SECRET_ANTERIOR", atual)
    _gravar_credential(cred / "PLAT_SECRET", novo)
    medicao = reiniciar_e_medir(args.unidade_api, args.porta_api)
    return {
        "segredo": "PLAT_SECRET",
        "sha_antigo": sha_curto(atual),
        "sha_novo": sha_curto(novo),
        "sha_anterior_gravado": sha_curto(_ler(cred / "PLAT_SECRET_ANTERIOR")),
        "restart": medicao.como_dict(),
    }


# ---------------------------------------------------------------- PLAT_DSN (senha de plat_app)
def rotacionar_plat_dsn(args) -> dict:
    cred = Path(args.cred_dir)
    role = args.role_app
    dsn_atual = _ler(cred / "PLAT_DSN")
    m = re.match(rf"^postgresql://{re.escape(role)}:([^@]+)@(.+)$", dsn_atual)
    if not m:
        raise SystemExit(f"{cred / 'PLAT_DSN'} não tem a forma postgresql://{role}:<senha>@<resto>")
    senha_antiga, resto = m.group(1), m.group(2)
    senha_nova = secrets.token_hex(16)
    dsn_novo = f"postgresql://{role}:{senha_nova}@{resto}"
    _psql(args.db, f"ALTER ROLE {role} PASSWORD '{senha_nova}'")
    _gravar_credential(cred / "PLAT_DSN", dsn_novo)
    medicao_api = reiniciar_e_medir(args.unidade_api, args.porta_api)
    cadeia = [medicao_api.como_dict()]
    if args.unidade_worker:  # "reinício em cadeia": produção só precisa da API para PLAT_DSN, mas a
        # prova do mecanismo (scripts/prova_segredos_l7_19.py) passa um segundo consumidor da MESMA role
        # para provar que a cadeia de N unidades fecha sem erro, uma depois da outra, cada uma checada.
        medicao_worker = reiniciar_e_medir(args.unidade_worker, args.porta_worker)
        cadeia.append(medicao_worker.como_dict())
    ainda_autentica_com_a_antiga = _autentica(f"postgresql://{role}:{senha_antiga}@{resto}")
    return {
        "segredo": "PLAT_DSN",
        "sha_senha_antiga": sha_curto(senha_antiga),
        "sha_senha_nova": sha_curto(senha_nova),
        "senha_antiga_ainda_autentica": ainda_autentica_com_a_antiga,
        "restart_cadeia": cadeia,
    }


# ---------------------------------------------------------------- PLAT_DSN_WORKER (senha de plat_worker)
def rotacionar_plat_dsn_worker(args) -> dict:
    cred = Path(args.cred_dir)
    role = args.role_worker
    dsn_atual = _ler(cred / "PLAT_DSN_WORKER")
    m = re.match(rf"^postgresql://{re.escape(role)}:([^@]+)@(.+)$", dsn_atual)
    if not m:
        raise SystemExit(f"{cred / 'PLAT_DSN_WORKER'} não tem a forma postgresql://{role}:<senha>@<resto>")
    senha_antiga, resto = m.group(1), m.group(2)
    senha_nova = secrets.token_hex(16)
    dsn_novo = f"postgresql://{role}:{senha_nova}@{resto}"
    _psql(args.db, f"ALTER ROLE {role} PASSWORD '{senha_nova}'")
    _gravar_credential(cred / "PLAT_DSN_WORKER", dsn_novo)
    medicao = reiniciar_e_medir(args.unidade_worker, args.porta_worker)
    ainda_autentica_com_a_antiga = _autentica(f"postgresql://{role}:{senha_antiga}@{resto}")
    return {
        "segredo": "PLAT_DSN_WORKER",
        "sha_senha_antiga": sha_curto(senha_antiga),
        "sha_senha_nova": sha_curto(senha_nova),
        "senha_antiga_ainda_autentica": ainda_autentica_com_a_antiga,
        "restart": medicao.como_dict(),
    }


# ---------------------------------------------------------------- PLAT_GARAGE_ADMIN_TOKEN
def rotacionar_garage_admin_token(args) -> dict:
    """Em produção de verdade o `admin_token` mora em `garage.toml` (é o Garage quem autentica a Admin
    API contra ele) — rotacionar exige editar aquele arquivo E reiniciar o daemon do Garage, ALÉM do
    consumidor (plat-api). `--garage-toml`/`--unidade-garage` apontam para onde isso deveria acontecer em
    produção; a prova deste item (`scripts/prova_segredos_l7_19.py`) aponta as duas para um TOML e uma
    unidade de teste, nunca para o Garage real (evita colidir com a trilha L0-11, ativa na mesma janela;
    ver docs/RUNBOOKS/segredos.md secção 5 para o procedimento real)."""
    cred = Path(args.cred_dir)
    atual = _ler(cred / "PLAT_GARAGE_ADMIN_TOKEN")
    novo = secrets.token_urlsafe(32)
    toml_path = Path(args.garage_toml)
    texto = toml_path.read_text(encoding="utf-8")
    if f'admin_token = "{atual}"' not in texto:
        raise SystemExit(f"admin_token atual não encontrado (verbatim) em {toml_path}")
    toml_path.write_text(texto.replace(f'admin_token = "{atual}"', f'admin_token = "{novo}"'), encoding="utf-8")
    # a fonte que o Garage lê (garage.toml) e o credential que o plat-api lê são gravados ANTES de
    # reiniciar qualquer um dos dois consumidores — nunca reiniciar com a fonte ainda apontando para o
    # valor antigo, senão o processo reiniciado volta a exigir/enviar o token velho (achado desta
    # implementação: a 1ª versão reiniciava o Garage antes de gravar o credential e o teste provava o
    # oposto do que devia — token velho continuava validando, token novo não).
    _gravar_credential(cred / "PLAT_GARAGE_ADMIN_TOKEN", novo)
    medicao_garage = reiniciar_e_medir(args.unidade_garage, args.porta_garage_admin, caminho_saude=args.saude_garage)
    medicao_api = reiniciar_e_medir(args.unidade_api, args.porta_api)

    def _bate(token: str) -> bool:
        req = urllib.request.Request(
            f"http://127.0.0.1:{args.porta_garage_admin}{args.caminho_admin_garage}",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            return e.code == 200
        except Exception:  # noqa: BLE001
            return False

    return {
        "segredo": "PLAT_GARAGE_ADMIN_TOKEN",
        "sha_antigo": sha_curto(atual),
        "sha_novo": sha_curto(novo),
        "token_antigo_ainda_autentica": _bate(atual),
        "token_novo_autentica": _bate(novo),
        "restart_cadeia": [medicao_garage.como_dict(), medicao_api.como_dict()],
    }


# ---------------------------------------------------------------- PLAT_GARAGE_CHAVE_S3:<slug>
def rotacionar_garage_chave_s3(args, slug: str) -> dict:
    """Sem restart nenhum: a API resolve o par de chaves do bucket por SELECT a cada requisição
    (`app.objetos._resolver_bucket_por_slug`/`plat.arquivo_bucket`), então trocar a chave no Garage + no
    banco muda o próximo request, não exige reiniciar processo nenhum — é por isso que este é o único dos
    5 segredos cuja rotação de verdade acontece em produção real dentro deste item (nada em
    plat-api/plat-worker/nginx/postgres é tocado)."""
    from app.garage import ClienteAdmin, ClienteS3, ErroGarage

    admin = ClienteAdmin(args.garage_admin_url, _ler(Path(args.cred_dir) / "PLAT_GARAGE_ADMIN_TOKEN"))
    alias = f"{args.bucket_prefixo}{slug}"
    bucket = admin.bucket_por_alias(alias)
    if bucket is None:
        raise SystemExit(f"bucket {alias!r} não existe no Garage (rode a prova com um bucket de teste primeiro)")
    bucket_id = bucket["id"]
    nome_chave_rw = f"{alias}-rw"
    chave_velha = admin.chave_por_nome(nome_chave_rw)
    if chave_velha is None:
        raise SystemExit(f"chave {nome_chave_rw!r} não existe")
    # ListKeys (chave_por_nome/listar_chaves) NUNCA devolve o secretAccessKey — só o id/nome; o segredo
    # em si só vem de CreateKey (na criação) ou de GetKeyInfo com showSecretKey=true (achado desta
    # implementação, MEDIDO contra o Garage real desta máquina: a resposta de ListKeys tem só
    # id/name/created/expiration/expired).
    id_velho = chave_velha["id"]
    info_velho = admin._chamar("GET", f"/v2/GetKeyInfo?id={id_velho}&showSecretKey=true")
    segredo_velho = info_velho["secretAccessKey"]

    nome_chave_nova = f"{nome_chave_rw}-{secrets.token_hex(3)}"
    # sempre uma chave NOVA (nunca idempotente aqui, ao contrário de admin.criar_chave): rotação existe
    # exatamente para nunca reaproveitar o segredo antigo.
    chave_nova = admin._chamar("POST", "/v2/CreateKey", {"name": nome_chave_nova})
    admin.permitir(bucket_id, chave_nova["accessKeyId"], ler=True, escrever=True, dono=True)

    endpoint = args.garage_url
    cliente_antigo = ClienteS3(endpoint, id_velho, segredo_velho, regiao=args.garage_regiao)
    cliente_novo = ClienteS3(
        endpoint, chave_nova["accessKeyId"], chave_nova["secretAccessKey"], regiao=args.garage_regiao
    )
    chave_objeto_teste = "_prova_rotacao/heartbeat.txt"
    cliente_novo.put(alias, chave_objeto_teste, b"prova-l7-19")
    novo_funciona = cliente_novo.head(alias, chave_objeto_teste) is not None

    admin.apagar_chave(id_velho)
    velho_falha = False
    try:
        cliente_antigo.head(alias, chave_objeto_teste)
    except ErroGarage as e:
        velho_falha = "403" in str(e) or "InvalidAccessKeyId" in str(e) or "SignatureDoesNotMatch" in str(e)
    except Exception:  # noqa: BLE001
        velho_falha = True

    return {
        "segredo": f"PLAT_GARAGE_CHAVE_S3:{slug}",
        "bucket": alias,
        "chave_antiga_id_sha": sha_curto(id_velho),
        "chave_nova_id_sha": sha_curto(chave_nova["accessKeyId"]),
        "chave_nova_funciona": novo_funciona,
        "chave_antiga_falha_depois_de_apagada": velho_falha,
        "restart": None,  # nenhuma unidade reiniciada — ver docstring
    }


def montar_argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    r = sub.add_parser("rotacionar")
    r.add_argument("nome")
    r.add_argument("--cred-dir", default="/etc/plat/segredos")
    r.add_argument("--db", default=os.environ.get("PLAT_DB", "iagro_sat"))
    r.add_argument("--unidade-api", default="plat-api")
    r.add_argument("--role-app", default="plat_app")
    r.add_argument("--role-worker", default="plat_worker")
    r.add_argument("--porta-api", type=int, default=8150)
    r.add_argument("--unidade-worker", default=None)
    r.add_argument("--porta-worker", type=int, default=8153)
    r.add_argument("--unidade-garage", default="plataforma-garage")
    r.add_argument("--porta-garage-admin", type=int, default=3903)
    r.add_argument("--saude-garage", default="/health")
    r.add_argument("--caminho-admin-garage", default="/admin")
    r.add_argument("--garage-toml", default="/home/dev/plataforma/pipeline/garage/garage.toml")
    r.add_argument("--garage-admin-url", default="http://127.0.0.1:3903")
    r.add_argument("--garage-url", default="http://127.0.0.1:3900")
    r.add_argument("--garage-regiao", default="garage")
    r.add_argument("--bucket-prefixo", default="plat-")
    r.add_argument("--json-saida", default=None, help="grava o resultado também neste caminho")
    return p


def main() -> None:
    args = montar_argparse().parse_args()
    if os.geteuid() != 0:
        raise SystemExit("rode como root: sudo venv/bin/python scripts/segredo_rotacionar.py rotacionar ...")
    inicio = time.monotonic()
    if args.nome == "PLAT_SECRET":
        resultado = rotacionar_plat_secret(args)
    elif args.nome == "PLAT_DSN":
        resultado = rotacionar_plat_dsn(args)
    elif args.nome == "PLAT_DSN_WORKER":
        resultado = rotacionar_plat_dsn_worker(args)
    elif args.nome == "PLAT_GARAGE_ADMIN_TOKEN":
        resultado = rotacionar_garage_admin_token(args)
    elif args.nome.startswith("PLAT_GARAGE_CHAVE_S3:"):
        resultado = rotacionar_garage_chave_s3(args, args.nome.split(":", 1)[1])
    else:
        raise SystemExit(
            f"segredo desconhecido: {args.nome!r} (admitidos: PLAT_SECRET, PLAT_DSN, PLAT_DSN_WORKER, "
            "PLAT_GARAGE_ADMIN_TOKEN, PLAT_GARAGE_CHAVE_S3:<slug>)"
        )
    resultado["tempo_total_s"] = round(time.monotonic() - inicio, 3)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    print(texto)
    if args.json_saida:
        Path(args.json_saida).write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    main()
