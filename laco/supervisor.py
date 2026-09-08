#!/usr/bin/env python3
"""Supervisor do laço PLATAFORMA ENTERPRISE.

A cada 20 s: colhe o estado dos processos, reconcilia quem morreu, publica o instantâneo do
painel e lança agentes até o teto efetivo. Instância única sob `flock laco/.supervisor.lock`.
Ao reiniciar, ADOTA os agentes vivos conferindo /proc/<pid> e o starttime (o número de processo
é reciclado pelo núcleo; só o par pid+starttime identifica um processo).

Teto efetivo = menor entre
  memória      (memória disponível − 3500 MB) / 250 MB
  conexões     para de lançar acima de 70 de 100 no Postgres
  cota         0 durante a pausa por cota, 1 na volta de teste
  rendimento   não cresce enquanto o repositório não recebe commit
e nunca acima de 8 por sessão.

Falhas tratadas separadamente, porque têm causas diferentes:
  COTA     — falha CORRELACIONADA (mata todos os agentes ao mesmo tempo). Detectada por saída em
             menos de 3 min com o log casando 429|rate limit|usage limit|session limit. Pausa
             TUDO e volta com espera de 5, 10, 20, 40 e 60 min, testando com UM agente antes de
             reabrir. Não conta tentativa contra o item.
  MEMÓRIA  — também não conta tentativa (a máquina falhou, não o item).
  VENENO   — 3 tentativas com causa que não seja cota nem falta de memória: o item vira
             `pendencia_declarada`, sai da fila e leva junto quem dependia dele.

Arquivo quente por ARRENDAMENTO (`laco/vivo/leases/`): um agente por vez em cada arquivo que a
árvore principal também mexe. O arrendamento só é pedido quando o próprio texto do item cita o
arquivo — senão o CHANGELOG.md serializaria a corrida inteira.

Uso:
    python3 supervisor.py --seco        mostra a decisão sem lançar nada (nada é escrito)
    python3 supervisor.py --uma-volta   uma volta de verdade
    python3 supervisor.py               o laço
"""
import argparse
import fcntl
import json
import os
import random
import re
import subprocess
import sys
import time
import datetime

BASE = "/home/dev/plataforma/laco"
REPO = "/home/dev/plataforma/enterprise"
VIVO = f"{BASE}/vivo"
AGENTES = f"{VIVO}/agentes"
LEASES = f"{VIVO}/leases"
LOGS = f"{VIVO}/logs"
PROMPTS = f"{VIVO}/prompts"
ESTADO = f"{BASE}/estado.json"
MEMORIA = f"{VIVO}/supervisor.json"
PAUSA = f"{VIVO}/pausa.json"
TRAVA = f"{BASE}/.supervisor.lock"
CLAUDE = "/home/dev/.local/bin/claude"
MARCAR = f"{BASE}/marcar_item.py"
GERA_PROMPT = f"{BASE}/prompt_item.py"

INTERVALO = 20            # s entre voltas
TETO_SESSAO = 8
RESERVA_MB = 3500         # memória que nunca se toca
MB_POR_AGENTE = 250
TETO_CONEXOES_LANCAR = 70
TETO_CONEXOES = 100
MAX_TENTATIVAS = 3
CURTO_S = 180             # saída em menos disso + log de cota = falha de cota
ESPERAS_MIN = [5, 10, 20, 40, 60]
TESTE_OK_S = 360          # agente de teste que passa disso reabre a corrida
SEM_COMMIT_S = 45 * 60    # sem commit por tanto tempo = não crescer
LIMITE_CASCATA = 25       # arrasto maior que isto sai da fila mas NÃO é gravado no estado.json

RE_COTA = re.compile(r"429|rate.?limit|usage limit|session limit|quota", re.I)
RE_MEMORIA = re.compile(r"MemoryError|Cannot allocate|Killed|Out of memory|oom", re.I)

QUENTES = [
    "app/main.py", "app/jobs/tipos.py", "CHANGELOG.md", "docs/PARIDADE.md",
    "MANUAL.md", "ARQUITETURA.md", "install.sh", "docs/openapi.json",
    "tests/api/cruzado_casos.py", "tests/api/eventos_esperados.py",
]


# --- modelo do dono (06/09): se laco/var/kimi.env existir, todo agente lançado pelo supervisor roda
# no Kimi K3 (janela 1.048.576) em vez de gastar a cota da conta Anthropic, que derrubou agentes em
# massa três vezes hoje. O arquivo fica em laco/var/ (fora do git; o repositório é público).
def ambiente_do_agente():
    env = dict(os.environ)
    cam = f"{LACO}/var/kimi.env" if "LACO" in globals() else "/home/dev/plataforma/laco/var/kimi.env"
    try:
        for linha in open(cam, encoding="utf-8"):
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, _, v = linha.partition("=")
                env[k.strip()] = v.strip()
        env.pop("ANTHROPIC_API_KEY", None)  # a chave da conta anularia a do dono
    except OSError:
        pass
    return env


def agora_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def sh(cmd, cwd=None, timeout=30):
    try:
        return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout).stdout
    except Exception:
        return ""


def stat_proc(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            b = f.read()
    except (OSError, ValueError):
        return None
    fim = b.rfind(")")
    try:
        return int(b[fim + 2:].split()[19])
    except (IndexError, ValueError):
        return None


def vivo_mesmo(pid, starttime):
    """Vivo E é o MESMO processo. Sem o starttime, um pid reciclado viraria agente fantasma."""
    if not pid:
        return False
    s = stat_proc(pid)
    return s is not None and (not starttime or s == int(starttime))


def le_json(caminho, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return padrao


def grava_json(caminho, dado):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


def tail(caminho, n=8000):
    try:
        with open(caminho, "rb") as f:
            f.seek(max(0, os.path.getsize(caminho) - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def slug(caminho):
    return re.sub(r"[^A-Za-z0-9]+", "_", caminho).strip("_")


class Supervisor:
    def __init__(self, seco=False, teto=TETO_SESSAO, sem_estado=False):
        self.seco = seco
        self.teto_pedido = min(teto, TETO_SESSAO)
        self.sem_estado = sem_estado or seco
        self.mem = le_json(MEMORIA, {}) or {}
        self.mem.setdefault("tentativas", {})       # item -> nº de falhas que CONTAM
        self.mem.setdefault("envenenados", {})      # item -> motivo
        self.mem.setdefault("causas", {})           # item -> [causas]
        self.mem.setdefault("cota", {"passo": 0, "ate": 0, "fase": "normal", "teste": None})
        self.mem.setdefault("ultimo_lancamento", 0)
        self.diario = []

    def diz(self, txt):
        linha = f"[{agora_iso()}] {txt}"
        self.diario.append(linha)
        print(linha, flush=True)

    def salva(self):
        if self.seco:
            return
        grava_json(MEMORIA, self.mem)
        c = self.mem["cota"]
        if c["fase"] != "normal":
            grava_json(PAUSA, {"fase": c["fase"], "ate": c["ate"], "passo": c["passo"],
                               "motivo": c.get("motivo", "cota da API"),
                               "faltam_s": max(0, int(c["ate"] - time.time()))})
        elif os.path.exists(PAUSA):
            os.remove(PAUSA)

    # ------------------------------------------------------------- leitura
    def estado(self):
        for _ in range(3):
            e = le_json(ESTADO)
            if e:
                return e
            time.sleep(0.2)
        return {"backlog": [], "turno": 0}

    def recursos(self):
        m = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for l in f:
                p = l.split()
                m[p[0].rstrip(":")] = int(p[1]) // 1024
        conex = None
        dsn = None
        try:  # 06/09: cofre primeiro (segredos saíram do .env no conserto G6), .env de reserva
            import subprocess
            dsn = subprocess.run(["sudo", "cat", "/etc/plat/segredos/PLAT_DSN"], capture_output=True, text=True, timeout=5).stdout.strip() or None
        except Exception:
            dsn = None
        if not dsn:
            try:
                for l in open(f"{REPO}/.env", encoding="utf-8"):
                    if l.startswith("PLAT_DSN="):
                        dsn = l.split("=", 1)[1].strip()
            except OSError:
                pass
        if dsn:
            try:
                import psycopg2
                if not getattr(self, "_con", None) or self._con.closed:
                    self._con = psycopg2.connect(dsn, connect_timeout=5,
                                                 application_name="supervisor")
                    self._con.autocommit = True
                with self._con.cursor() as c:
                    c.execute("select count(*) from pg_stat_activity")
                    conex = c.fetchone()[0]
            except Exception:
                self._con = None
        if conex is None:
            s = sh("sudo -n -u postgres psql -d iagro_sat -tAc "
                   "\"select count(*) from pg_stat_activity\"", timeout=10).strip()
            conex = int(s) if s.isdigit() else None
        return {"mem_disponivel_mb": m.get("MemAvailable", 0),
                "conexoes": conex, "carga": os.getloadavg()[0]}

    def registro_agentes(self):
        saida = []
        if not os.path.isdir(AGENTES):
            return saida
        for nome in sorted(os.listdir(AGENTES)):
            if nome.endswith(".json"):
                a = le_json(f"{AGENTES}/{nome}")
                if a:
                    a["_arquivo"] = f"{AGENTES}/{nome}"
                    saida.append(a)
        return saida

    def commits_recentes_s(self):
        s = sh("git log --all -1 --format=%ct", cwd=REPO, timeout=20).strip()
        return int(time.time() - int(s)) if s.isdigit() else 10 ** 9

    # -------------------------------------------------- reconciliação
    def causa_da_morte(self, a, entregou):
        txt = tail(a.get("log", ""))
        dur = time.time() - (a.get("inicio_ts") or 0)
        if RE_COTA.search(txt) and dur < CURTO_S:
            return "cota"
        if RE_COTA.search(txt[-2000:]) and dur < 2 * CURTO_S:
            return "cota"
        if RE_MEMORIA.search(txt):
            return "memoria"
        if entregou:
            return "entregue"
        return "outra"

    def entregou(self, a, backlog_por_id):
        it = backlog_por_id.get(a.get("item"))
        if it and it["estado"] in ("entregue", "parcial"):
            return True
        h = f"{BASE}/handoffs/T{a.get('turno', 3)}/{a.get('item')}.md"
        return os.path.exists(h) and os.path.getmtime(h) > (a.get("inicio_ts") or 0)

    def reconcilia(self, backlog_por_id):
        """Quem morreu sai do registro, larga os arrendamentos e deixa a causa registrada."""
        vivos, mortos = [], []
        for a in self.registro_agentes():
            if vivo_mesmo(a.get("pid"), a.get("starttime")):
                vivos.append(a)
            else:
                mortos.append(a)
        cota_agora = False
        for a in mortos:
            ent = self.entregou(a, backlog_por_id)
            causa = self.causa_da_morte(a, ent)
            item = a.get("item")
            self.mem["causas"].setdefault(item, []).append(causa)
            if causa == "cota":
                cota_agora = True
                self.diz(f"morreu {a['id']} · item {item} · causa COTA (não conta tentativa)")
            elif causa == "memoria":
                self.diz(f"morreu {a['id']} · item {item} · causa MEMÓRIA (não conta tentativa)")
            elif causa == "entregue":
                self.diz(f"terminou {a['id']} · item {item} · entregou")
                self.mem["tentativas"].pop(item, None)
            else:
                n = self.mem["tentativas"].get(item, 0) + 1
                self.mem["tentativas"][item] = n
                self.diz(f"morreu {a['id']} · item {item} · causa outra · tentativa {n}/{MAX_TENTATIVAS}")
                if not self.sem_estado:
                    self.marca(item, "pendente", f"agente {a['id']} morreu sem entregar ({causa})")
            if not self.seco:
                self.larga_arrendamentos(a["id"])
                try:
                    os.remove(a["_arquivo"])
                except OSError:
                    pass
        return vivos, cota_agora

    # -------------------------------------------------- veneno
    def envenena(self, backlog):
        por_id = {x["id"]: x for x in backlog}
        novos = []
        for item, n in list(self.mem["tentativas"].items()):
            if n >= MAX_TENTATIVAS and item not in self.mem["envenenados"] and item in por_id:
                motivo = (f"{n} tentativas com causa que não é cota nem falta de memória "
                          f"({', '.join(self.mem['causas'].get(item, [])[-3:])})")
                self.mem["envenenados"][item] = motivo
                novos.append((item, motivo))
        # arrasta quem dependia (fecho transitivo)
        mudou = True
        while mudou:
            mudou = False
            for x in backlog:
                if x["id"] in self.mem["envenenados"]:
                    continue
                deps = [d for d in (x.get("dependencias") or []) if d in self.mem["envenenados"]]
                if deps:
                    motivo = "depende de " + ", ".join(deps) + " (pendência declarada)"
                    self.mem["envenenados"][x["id"]] = motivo
                    novos.append((x["id"], motivo))
                    mudou = True
        # medido em 06/09: um único item envenenado arrasta 177 dos 506 (L2-01-mapa-web). Escrever
        # isso no estado.json sozinho seria apagar metade do backlog sem ninguém decidir. Por isso:
        # todos saem da fila (ficam em self.mem), mas a GRAVAÇÃO no estado.json só acontece se o
        # arrasto for pequeno; acima do limite, só a raiz é gravada e o resto vira aviso.
        raizes = {i for i, m in novos if not m.startswith("depende de")}
        grava_tudo = len(novos) <= LIMITE_CASCATA
        for item, motivo in novos:
            self.diz(f"VENENO: {item} -> pendencia_declarada · {motivo}")
            if self.sem_estado:
                continue
            if grava_tudo or item in raizes:
                self.marca(item, "pendencia_declarada", motivo)
        if novos and not grava_tudo:
            self.diz(f"AVISO: o arrasto tem {len(novos)} itens (limite {LIMITE_CASCATA}). "
                     f"Só as raízes {sorted(raizes)} foram gravadas no estado.json; os outros "
                     "saíram da fila mas continuam com o estado que tinham — quem decide o "
                     "cancelamento em massa é o dono, não o supervisor.")
        return novos

    def marca(self, item, estado, nota):
        if self.seco or self.sem_estado:
            return
        subprocess.run([sys.executable, MARCAR, item, estado, nota[:400]],
                       capture_output=True, text=True, timeout=60)

    # -------------------------------------------------- arrendamentos
    def arrendamentos(self):
        d = {}
        if not os.path.isdir(LEASES):
            return d
        for nome in os.listdir(LEASES):
            a = le_json(f"{LEASES}/{nome}")
            if a:
                d[a["arquivo"]] = a
        return d

    def larga_arrendamentos(self, agente_id):
        if not os.path.isdir(LEASES):
            return
        for nome in os.listdir(LEASES):
            cam = f"{LEASES}/{nome}"
            a = le_json(cam)
            if a and a.get("agente") == agente_id:
                try:
                    os.remove(cam)
                except OSError:
                    pass

    def quentes_do_item(self, item):
        txt = " ".join(str(item.get(k) or "") for k in
                       ("hipotese", "portao_de_pronto", "refutacao"))
        return [q for q in QUENTES if q in txt or os.path.basename(q) in txt]

    def pega_arrendamentos(self, item, agente_id, pid):
        for q in self.quentes_do_item(item):
            grava_json(f"{LEASES}/{slug(q)}.json",
                       {"arquivo": q, "agente": agente_id, "item": item["id"],
                        "pid": pid, "desde": agora_iso(), "desde_ts": time.time()})

    # -------------------------------------------------- teto
    def teto_efetivo(self, rec, vivos):
        c = self.mem["cota"]
        agora = time.time()
        motivos = {}
        motivos["memoria"] = max(0, int((rec["mem_disponivel_mb"] - RESERVA_MB) / MB_POR_AGENTE))
        cx = rec["conexoes"]
        motivos["conexoes"] = 0 if (cx is not None and cx > TETO_CONEXOES_LANCAR) else TETO_SESSAO
        if c["fase"] == "pausa":
            motivos["cota"] = 0 if agora < c["ate"] else 1
            if agora >= c["ate"]:
                c["fase"] = "teste"
                self.diz("espera da cota cumprida: volta em modo TESTE, um agente só")
        elif c["fase"] == "teste":
            motivos["cota"] = 1
        else:
            motivos["cota"] = TETO_SESSAO
        sem_commit = self.commits_recentes_s()
        motivos["rendimento"] = (len(vivos) if (len(vivos) >= 2 and sem_commit > SEM_COMMIT_S)
                                 else TETO_SESSAO)
        motivos["sessao"] = self.teto_pedido
        teto = min(motivos.values())
        return teto, motivos, sem_commit

    def pausa_por_cota(self):
        c = self.mem["cota"]
        espera = ESPERAS_MIN[min(c["passo"], len(ESPERAS_MIN) - 1)]
        c["fase"] = "pausa"
        c["ate"] = time.time() + espera * 60
        c["motivo"] = f"cota da API; espera de {espera} min (passo {c['passo'] + 1})"
        c["passo"] = min(c["passo"] + 1, len(ESPERAS_MIN) - 1)
        c["teste"] = None
        self.diz(f"COTA: falha correlacionada. PAUSA TOTAL de {espera} min. "
                 f"Nenhum lançamento até {datetime.datetime.fromtimestamp(c['ate']):%H:%M}.")

    def confere_teste(self, vivos):
        c = self.mem["cota"]
        if c["fase"] != "teste":
            return
        alvo = [a for a in vivos if a["id"] == c.get("teste")]
        if c.get("teste") and alvo:
            if time.time() - (alvo[0].get("inicio_ts") or 0) > TESTE_OK_S:
                self.diz(f"agente de teste {c['teste']} passou de {TESTE_OK_S // 60} min: "
                         "corrida reaberta, espera de cota zerada")
                c.update({"fase": "normal", "passo": 0, "teste": None, "ate": 0})
        elif c.get("teste"):
            c["teste"] = None      # morreu: a reconciliação já classificou a causa

    # -------------------------------------------------- fila
    def fila(self, backlog, vivos):
        por_id = {x["id"]: x for x in backlog}
        ocupados = {a.get("item") for a in vivos}
        arrendados = set(self.arrendamentos())
        saida = []
        for x in backlog:
            if x["estado"] != "pendente" or x["id"] in ocupados:
                continue
            if x["id"] in self.mem["envenenados"]:
                continue
            if self.mem["tentativas"].get(x["id"], 0) >= MAX_TENTATIVAS:
                continue
            abertas = [d for d in (x.get("dependencias") or [])
                       if d not in por_id or por_id[d]["estado"] not in ("entregue", "parcial")]
            if abertas:
                continue
            choque = [q for q in self.quentes_do_item(x) if q in arrendados]
            if choque:
                continue
            saida.append(x)
        saida.sort(key=lambda x: (x.get("prioridade", 99), x["id"]))
        return saida

    def prompt_de(self, item, gerar=True):
        cam = f"{PROMPTS}/{item['id']}.md"
        if os.path.exists(cam):
            return cam
        if not gerar:
            return None
        r = subprocess.run([sys.executable, GERA_PROMPT, item["id"]],
                           capture_output=True, text=True, timeout=180)
        return cam if os.path.exists(cam) else None

    def lanca(self, item):
        cam = self.prompt_de(item)
        if not cam:
            self.diz(f"não lancei {item['id']}: prompt não pôde ser gerado")
            self.mem["tentativas"][item["id"]] = self.mem["tentativas"].get(item["id"], 0) + 1
            return None
        tentativa = self.mem["tentativas"].get(item["id"], 0) + 1
        aid = f"{item['id']}-t{tentativa}-{datetime.datetime.now():%H%M%S}"
        os.makedirs(LOGS, exist_ok=True)
        log = f"{LOGS}/{aid}.log"
        prompt = open(cam, encoding="utf-8").read()
        with open(log, "w", encoding="utf-8") as saida_log:
            p = subprocess.Popen([CLAUDE, "-p", prompt, "--dangerously-skip-permissions"],
                                 cwd="/home/dev/plataforma", stdout=saida_log,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 start_new_session=True, env=ambiente_do_agente())
        reg = {"id": aid, "item": item["id"], "pid": p.pid,
               "starttime": stat_proc(p.pid), "inicio": agora_iso(),
               "inicio_ts": time.time(), "log": log, "prompt": cam,
               "tentativa": tentativa, "papel": "construtor",
               "turno": self.turno, "quentes": self.quentes_do_item(item)}
        grava_json(f"{AGENTES}/{aid}.json", reg)
        self.pega_arrendamentos(item, aid, p.pid)
        self.marca(item["id"], "tentando", f"supervisor lançou {aid}")
        if self.mem["cota"]["fase"] == "teste":
            self.mem["cota"]["teste"] = aid
        self.mem["ultimo_lancamento"] = time.time()
        self.diz(f"lancei {aid} · pid {p.pid} · log {log}")
        return reg

    # -------------------------------------------------- publicação
    def publica(self):
        if self.seco:
            return
        subprocess.run([sys.executable, f"{BASE}/painel_vivo.py", "--uma-vez"],
                       capture_output=True, timeout=90)

    # -------------------------------------------------- volta
    def volta(self):
        e = self.estado()
        backlog = e.get("backlog", [])
        self.turno = e.get("turno", 3)
        por_id = {x["id"]: x for x in backlog}
        rec = self.recursos()

        vivos, cota_agora = self.reconcilia(por_id)
        if cota_agora:
            self.pausa_por_cota()
            for a in vivos:                      # pausa TUDO: nada de continuar queimando cota
                self.diz(f"deixo {a['id']} terminar sozinho; nenhum lançamento novo na pausa")
        self.confere_teste(vivos)
        self.envenena(backlog)

        teto, motivos, sem_commit = self.teto_efetivo(rec, vivos)
        vagas = max(0, teto - len(vivos))
        f = self.fila(backlog, vivos)

        cx = rec["conexoes"]
        self.diz(f"vivos {len(vivos)} · teto {teto} "
                 f"(memória {motivos['memoria']} · conexões {motivos['conexoes']} "
                 f"· cota {motivos['cota']} · rendimento {motivos['rendimento']} "
                 f"· sessão {motivos['sessao']}) · vagas {vagas} · fila {len(f)} · "
                 f"RAM {rec['mem_disponivel_mb']} MB · conexões {cx}/{TETO_CONEXOES} · "
                 f"último commit há {sem_commit // 60} min · fase da cota {self.mem['cota']['fase']}")

        if e.get("estado") != "ATIVO":
            self.diz(f"laço em estado {e.get('estado')}: não lanço nada")
            vagas = 0

        lancados = []
        if vagas > 0 and f:
            alvo = f[0]                          # 1 por volta = escalonado 1 a cada 20 s
            if self.seco:
                cam = self.prompt_de(alvo, gerar=False)
                self.diz(f"SECO: lançaria {alvo['id']} ({alvo.get('linha')}) · "
                         f"prompt {'pronto' if cam else 'seria gerado agora'} · "
                         f"arrendaria {self.quentes_do_item(alvo) or 'nenhum arquivo quente'}")
                self.diz("SECO: próximos da fila -> " + ", ".join(x["id"] for x in f[1:6]))
            else:
                time.sleep(random.uniform(0, 6))   # variação, para não bater tudo no mesmo segundo
                r = self.lanca(alvo)
                if r:
                    lancados.append(r)
        elif not f:
            self.diz("fila vazia: nada elegível (dependência aberta, veneno ou arquivo quente arrendado)")
        elif vagas == 0:
            self.diz("sem vaga: teto atingido")

        self.salva()
        self.publica()
        return {"vivos": len(vivos), "teto": teto, "vagas": vagas, "fila": len(f),
                "lancados": [r["id"] for r in lancados]}


def main():
    ap = argparse.ArgumentParser(description="supervisor do laço")
    ap.add_argument("--seco", action="store_true", help="decide e mostra, sem lançar nem escrever")
    ap.add_argument("--uma-volta", action="store_true")
    ap.add_argument("--teto", type=int, default=TETO_SESSAO)
    ap.add_argument("--sem-estado", action="store_true",
                    help="não escreve no estado.json nem por marcar_item.py")
    a = ap.parse_args()

    if not a.seco:
        trava = open(TRAVA, "a+")
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("já existe supervisor rodando (instância única)")
        os.makedirs(AGENTES, exist_ok=True)
        os.makedirs(LEASES, exist_ok=True)
        os.makedirs(LOGS, exist_ok=True)

    s = Supervisor(seco=a.seco, teto=a.teto, sem_estado=a.sem_estado)
    if a.seco or a.uma_volta:
        s.volta()
        return
    s.diz(f"supervisor no ar · teto de sessão {a.teto} · volta a cada {INTERVALO} s")
    while True:
        try:
            s.volta()
        except Exception as erro:
            s.diz(f"volta falhou: {type(erro).__name__}: {str(erro)[:200]}")
        time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
