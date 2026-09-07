"""Banca real do item L7-06-c: nginx de verdade + API de verdade + worker de verdade + Postgres de
verdade, num pedido só, e `plat logs --req-id` reunindo o que os quatro escreveram.

Não é um teste de pytest de propósito: sobe processos e escreve em portas, o que não pode acontecer
sob o semáforo da suíte. Roda à mão e grava a medida:

    set -a; source /home/dev/plataforma/laco/var/trilha/il706clogsc.env; set +a
    venv/bin/python tests/banca_l706c_logs_req_id.py

O que ela prova, e o que não prova, está escrito no arquivo de medida que ela grava.
"""

import datetime
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app import logs_consulta  # noqa: E402


# A porta 8306 do prompt do item ESTAVA OCUPADA pelo prometheus desta máquina (medido em 07/09 com
# `ss -ltnp`), e a 8307 pelo alertmanager. Porta é recurso partilhado: escolher a porta pelo papel e
# não pela disponibilidade real faz um agente medir a aplicação de outro. Aqui a escolha é feita na
# hora, sobre quem está escutando AGORA (adendo 3 do BRIEF_WORKTREES).
def porta_livre(inicio: int) -> int:
    for porta in range(inicio, inicio + 200):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", porta))
            except OSError:
                continue
        return porta
    raise SystemExit(f"nenhuma porta livre a partir de {inicio}")


PORTA_API = porta_livre(8306)
PORTA_NGINX = porta_livre(PORTA_API + 1)
PORTA_MORTA = porta_livre(PORTA_NGINX + 1)  # ninguém escuta: é o "erro forçado" do pedido de tile (502)
BANCA = RAIZ / "var" / "banca_l706c"
MEDIDA = RAIZ / "tests" / "medidas" / "L7-06-c-logs-consulta-req-id.json"

NGINX_CONF = """
daemon off;
error_log {banca}/nginx_erro.log warn;
pid {banca}/nginx.pid;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {banca}/tmp_body;
    proxy_temp_path {banca}/tmp_proxy;
    fastcgi_temp_path {banca}/tmp_fastcgi;
    uwsgi_temp_path {banca}/tmp_uwsgi;
    scgi_temp_path {banca}/tmp_scgi;
    # o MESMO log_format que o install.sh escreve em /etc/nginx/conf.d/plat_limites.conf
    log_format plat_json escape=json '{{"ts":"$time_iso8601","req_id":"$request_id","ip":"$remote_addr",'
      '"metodo":"$request_method","rota":"$uri","consulta":"$args","status":$status,'
      '"bytes":$body_bytes_sent,"tempo_ms":$request_time,"upstream":"$upstream_addr",'
      '"upstream_status":"$upstream_status","agente":"$http_user_agent"}}';
    server {{
        listen 127.0.0.1:{porta_nginx};
        access_log {banca}/nginx.log plat_json;
        location /tiles/ {{
            proxy_pass http://127.0.0.1:{porta_morta};
            proxy_set_header X-Req-Id $request_id;
        }}
        location / {{
            proxy_pass http://127.0.0.1:{porta_api};
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Req-Id $request_id;
            proxy_read_timeout 120s;
        }}
    }}
}}
"""


def espera_porta(porta: int, segundos: float = 45.0) -> bool:
    fim = time.time() + segundos
    while time.time() < fim:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.3)
    return False


def req_id_no_log_do_nginx(rota: str) -> str | None:
    achado = None
    for linha in (BANCA / "nginx.log").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            registro = json.loads(linha)
        except ValueError:
            continue
        if registro.get("rota") == rota:
            achado = registro.get("req_id")
    return achado


def credenciais(slug: str) -> tuple[str, str]:
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (RAIZ / "tests" / "credenciais.txt"))
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0] == slug:
            return partes[1], " ".join(partes[2:])
    raise SystemExit(f"sem credencial de {slug} em {caminho}")


def curl(caminho: str, *, metodo="GET", corpo=None, cookies=None, cabecalhos=()) -> tuple[int, dict, str]:
    comando = ["curl", "-sS", "-o", str(BANCA / "corpo.out"), "-D", str(BANCA / "cabecalhos.out"),
               "-w", "%{http_code}", "-X", metodo, f"http://127.0.0.1:{PORTA_NGINX}{caminho}"]
    if cookies:
        comando += ["-b", str(cookies), "-c", str(cookies)]
    if corpo is not None:
        comando += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corpo)]
    for c in cabecalhos:
        comando += ["-H", c]
    codigo = subprocess.run(comando, capture_output=True, text=True, check=False).stdout.strip()
    cab = {}
    for linha in (BANCA / "cabecalhos.out").read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in linha:
            k, _, v = linha.partition(":")
            cab[k.strip().lower()] = v.strip()
    return int(codigo or 0), cab, (BANCA / "corpo.out").read_text(encoding="utf-8", errors="replace")


LOG_POSTGRES = "/var/log/postgresql/postgresql-16-main.log"


def tamanho_log_postgres() -> int | None:
    """O `log_line_prefix` deste servidor já traz `app=%a` (conferido com `SHOW log_line_prefix`), e o
    pacote Debian manda a saída de erro para um arquivo, não para o journal. O arquivo é do grupo `adm`:
    a leitura pede sudo. Guardamos o tamanho ANTES do pedido e lemos só o que veio depois — o arquivo
    tem centenas de MB e é de toda a casa, não só desta trilha."""
    r = subprocess.run(["sudo", "-n", "stat", "-c", "%s", LOG_POSTGRES], capture_output=True, text=True, check=False)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def recortar_log_postgres(desde_byte: int | None, destino: Path) -> bool:
    if desde_byte is None:
        return False
    r = subprocess.run(["sudo", "-n", "tail", "-c", f"+{desde_byte + 1}", LOG_POSTGRES],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False
    destino.write_text(r.stdout, encoding="utf-8")
    return True


def principal() -> int:
    if not os.environ.get("PLAT_SCHEMA", "").startswith("plat_t"):
        raise SystemExit("rode com o ambiente da trilha (PLAT_SCHEMA=plat_t...), nunca contra o schema plat")
    schema = os.environ["PLAT_SCHEMA"]
    papel = os.environ["PLAT_DSN"].split("//", 1)[1].split(":", 1)[0]
    shutil.rmtree(BANCA, ignore_errors=True)
    for sub in ("tmp_body", "tmp_proxy", "tmp_fastcgi", "tmp_uwsgi", "tmp_scgi"):
        (BANCA / sub).mkdir(parents=True, exist_ok=True)
    (BANCA / "nginx.log").touch()

    # O registro de sentença do Postgres é ligado SÓ para o papel desta trilha, ANTES de a API subir:
    # `ALTER ROLE ... SET` só vale para sessão nova, e o pool abre as dele no arranque. Desligado no fim.
    subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-q", "-c",
                    f"ALTER ROLE {papel} SET log_min_duration_statement = 0"], check=True,
                   capture_output=True, text=True)
    api_log = open(BANCA / "api.log", "w", encoding="utf-8")
    worker_log = open(BANCA / "worker.log", "w", encoding="utf-8")
    conf = BANCA / "nginx.conf"
    conf.write_text(NGINX_CONF.format(banca=BANCA, porta_api=PORTA_API, porta_nginx=PORTA_NGINX,
                                      porta_morta=PORTA_MORTA), encoding="utf-8")

    # a venv não instala o console script do uvicorn; o módulo é o mesmo programa
    api = subprocess.Popen([str(RAIZ / "venv/bin/python"), "-m", "uvicorn", "app.main:app",
                            "--port", str(PORTA_API), "--host", "127.0.0.1", "--log-level", "warning"],
                           cwd=RAIZ, stdout=api_log, stderr=subprocess.STDOUT)
    # PLAT_GIT_SHA: o worker exige o sha do commit e o `git rev-parse` não roda de dentro do processo
    # filho nesta árvore (worktree: o .git é um arquivo, e o git recusa por dono duvidoso). Passar o sha
    # medido aqui é o caminho previsto pelo próprio app/versao.py.
    sha = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=False).stdout.strip()
    ambiente_worker = {**os.environ, "PLAT_WORKER_URL": f"http://127.0.0.1:{porta_livre(PORTA_MORTA + 1)}",
                       "PLAT_GIT_SHA": sha or "0" * 40}
    worker = subprocess.Popen([str(RAIZ / "venv/bin/python"), "-m", "app.jobs.worker"],
                              cwd=RAIZ, stdout=worker_log, stderr=subprocess.STDOUT, env=ambiente_worker)
    nginx = subprocess.Popen(["nginx", "-c", str(conf), "-p", str(BANCA)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    resultado: dict = {}
    try:
        if not espera_porta(PORTA_API):
            raise SystemExit("a API não subiu; veja var/banca_l706c/api.log")
        if not espera_porta(PORTA_NGINX):
            raise SystemExit(f"o nginx não subiu: {nginx.stderr.read().decode(errors='replace')[:400]}")

        byte_postgres = tamanho_log_postgres()
        biscoito = BANCA / "cookies.txt"
        login, senha = credenciais("demo")
        codigo, _, corpo = curl("/api/login", metodo="POST", cookies=biscoito,
                                corpo={"inquilino": "demo", "login": login, "senha": senha})
        if codigo != 200:
            raise SystemExit(f"login falhou ({codigo}): {corpo[:300]}")

        # -------- pedido 1: tile com erro forçado (o servidor de tiles não responde: 502 no nginx)
        codigo_tile, cab_tile, _ = curl("/tiles/plat_teste_interno/1/2/3.pbf")
        # num 502 não há resposta do upstream, logo não há cabeçalho X-Req-Id para o cliente: o
        # identificador do pedido é o que o NGINX cunhou, e está na linha de acesso dele. É assim que o
        # operador acha o identificador de um pedido que nem chegou à aplicação.
        rid_tile = cab_tile.get("x-req-id") or req_id_no_log_do_nginx("/tiles/plat_teste_interno/1/2/3.pbf")

        # -------- pedido 2: cria um job -> nginx, API, Postgres e o WORKER escrevem com o mesmo id
        codigo_job, cab_job, corpo_job = curl(
            "/api/jobs", metodo="POST", cookies=biscoito,
            corpo={"tipo": "prova.progresso", "parametros": {"duracao_s": 2, "passos": 2}})
        rid_job = cab_job.get("x-req-id")
        time.sleep(6)  # o worker pega o job no próximo tique

        # -------- pedido 3: erro DENTRO do Postgres, com o application_name do pedido
        subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-q", "-c",
                        f"REVOKE SELECT ON {schema}.log_acesso FROM {papel}"], check=True,
                       capture_output=True, text=True)
        try:
            codigo_erro, cab_erro, _ = curl("/api/log?limite=1", cookies=biscoito)
            # numa exceção não tratada a resposta sai do tratador do próprio servidor, antes do nosso
            # middleware pôr o X-Req-Id: quem guarda o identificador é a linha do nginx. Limitação real,
            # registrada na medida — não se conserta escondendo.
            rid_erro = cab_erro.get("x-req-id") or req_id_no_log_do_nginx("/api/log")
        finally:
            subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-q", "-c",
                            f"GRANT SELECT ON {schema}.log_acesso TO {papel}"], check=True,
                           capture_output=True, text=True)
        # -------- pedido 4: UM pedido só nos QUATRO serviços.
        # Um pedido de tile nunca alcança os quatro: quem serve tile é o Martin, sem passar pela
        # aplicação nem pela fila. O pedido que atravessa os quatro é o que cria trabalho. Para o
        # Postgres escrever a linha dele, o registro de sentença é ligado SÓ para o papel desta trilha
        # (`ALTER ROLE ... SET log_min_duration_statement = 0`), e desligado no `finally`.
        codigo_quatro, cab_quatro, _ = curl("/api/jobs", metodo="POST", cookies=biscoito,
                                            corpo={"tipo": "prova.progresso",
                                                   "parametros": {"duracao_s": 2, "passos": 2}})
        rid_quatro = cab_quatro.get("x-req-id")
        time.sleep(8)  # o worker tem de pegar o job e escrever a linha dele
        api_log.flush()
        worker_log.flush()

        tem_postgres = recortar_log_postgres(byte_postgres, BANCA / "postgres.log")
        fontes = (f"nginx=arquivo:{BANCA}/nginx.log,api=arquivo:{BANCA}/api.log,"
                  f"worker=arquivo:{BANCA}/worker.log,postgres=arquivo:{BANCA}/postgres.log")

        def reuniao(rid):
            linhas = logs_consulta.reunir(rid, especificacao=fontes) if rid else []
            return {"req_id": rid, "servicos": sorted({linha.servico for linha in linhas}),
                    "linhas": [linha.como_dicionario() for linha in linhas],
                    "em_ordem": [linha.em for linha in linhas] == sorted(
                        [linha.em for linha in linhas],
                        key=lambda e: (e is None, e or datetime.datetime.min.replace(tzinfo=datetime.UTC)))}

        resultado = {
            "medido_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "carga_1min": os.getloadavg()[0],
            "postgres_lido_do_arquivo_do_servidor": tem_postgres,
            "tile_erro_forcado": {"status_http": codigo_tile, **reuniao(rid_tile)},
            "criacao_de_job": {"status_http": codigo_job, **reuniao(rid_job)},
            "erro_no_postgres": {"status_http": codigo_erro, **reuniao(rid_erro)},
            "um_pedido_quatro_servicos": {"status_http": codigo_quatro, **reuniao(rid_quatro)},
        }
        for nome, bloco in (("tile", resultado["tile_erro_forcado"]),
                            ("job", resultado["criacao_de_job"]),
                            ("erro", resultado["erro_no_postgres"]),
                            ("quatro", resultado["um_pedido_quatro_servicos"])):
            print(f"{nome}: req_id={bloco['req_id']} servicos={bloco['servicos']} ordem_ok={bloco['em_ordem']}")
        todos = sorted(set(resultado["tile_erro_forcado"]["servicos"])
                       | set(resultado["criacao_de_job"]["servicos"])
                       | set(resultado["erro_no_postgres"]["servicos"])
                       | set(resultado["um_pedido_quatro_servicos"]["servicos"]))
        resultado["servicos_distintos_provados"] = todos
        print("serviços distintos com linha carregando o identificador:", todos)
    finally:
        for proc in (nginx, worker, api):
            with contextlib_suppress():
                proc.send_signal(signal.SIGTERM)
        for proc in (nginx, worker, api):
            with contextlib_suppress():
                proc.wait(timeout=20)
        api_log.close()
        worker_log.close()
        subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-q", "-c",
                        f"ALTER ROLE {papel} RESET log_min_duration_statement"], check=False,
                       capture_output=True, text=True)
    if resultado:
        MEDIDA.parent.mkdir(parents=True, exist_ok=True)
        anterior = json.loads(MEDIDA.read_text(encoding="utf-8")) if MEDIDA.exists() else {}
        anterior["banca_processos_reais"] = resultado
        MEDIDA.write_text(json.dumps(anterior, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("medida gravada em", MEDIDA)
    return 0


class contextlib_suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


if __name__ == "__main__":
    raise SystemExit(principal())
