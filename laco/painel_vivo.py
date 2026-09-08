#!/usr/bin/env python3
"""Coletor do painel vivo do laço PLATAFORMA ENTERPRISE.

Grava `laco/vivo/agora.json` (escrita atômica) com o retrato da corrida: placar, itens,
agentes vivos, fila de merge, commits, achados de adversário abertos e recursos da máquina.

NUNCA escreve no estado.json. Um processo só, leve: cada fonte tem a sua cadência, porque
cada uma tem o seu preço.
    recursos            5 s   (leitura de /proc, statvfs)
    estado.json        só quando o mtime muda (arquivo de 1 MB)
    git dos worktrees  30 s
    conexões do banco  15 s   (UMA conexão psycopg2 mantida aberta)

Uso:
    python3 painel_vivo.py --uma-vez        colhe uma vez, imprime o instantâneo
    python3 painel_vivo.py                  laço no terminal (Ctrl-C para sair)
    python3 painel_vivo.py --servir         laço + servidor mínimo em 127.0.0.1:8159
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import datetime

BASE = "/home/dev/plataforma/laco"
REPO = "/home/dev/plataforma/enterprise"
WT = "/home/dev/plataforma/wt"
ESTADO = f"{BASE}/estado.json"
VIVO = f"{BASE}/vivo"
SAIDA = f"{VIVO}/agora.json"
AGENTES = f"{VIVO}/agentes"
LEASES = f"{VIVO}/leases"
TRAVA = f"{BASE}/.painel.lock"

PORTA = 8159
TETO_CONEXOES = 100

# arquivos que a árvore principal também mexe: colisão de merge é aqui
QUENTES = [
    "app/main.py", "app/jobs/tipos.py", "CHANGELOG.md", "docs/PARIDADE.md",
    "MANUAL.md", "ARQUITETURA.md", "install.sh", "docs/openapi.json",
    "tests/api/cruzado_casos.py", "tests/api/eventos_esperados.py",
]

ID_ITEM = re.compile(r"\bL[0-7]-\d{2}(?:-[a-z0-9]+)*\b")


def sh(cmd, cwd=None, timeout=25):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def agora_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- processos
def leitura_stat(pid):
    """(starttime em jiffies, comm) do /proc/<pid>/stat, ou None se o processo sumiu."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            bruto = f.read()
    except (OSError, ValueError):
        return None
    # o comm vem entre parênteses e pode conter espaços
    fim = bruto.rfind(")")
    comm = bruto[bruto.find("(") + 1:fim]
    campos = bruto[fim + 2:].split()
    try:
        return int(campos[19]), comm     # campo 22 do proc(5) = starttime
    except (IndexError, ValueError):
        return None


def processo_vivo(pid, starttime=None):
    """Vivo E é o mesmo processo: número de processo é reciclado pelo núcleo."""
    s = leitura_stat(pid)
    if s is None:
        return False
    return True if starttime in (None, 0) else s[0] == int(starttime)


# ---------------------------------------------------------------- coletor
class Coletor:
    def __init__(self):
        self.cache = {}
        self.quando = {}
        self.estado_mtime = 0
        self.estado = None
        self.conexao = None
        self.dsn = self._dsn()

    # --- utilitário de cadência
    def cada(self, chave, segundos, funcao):
        t = time.time()
        if chave not in self.cache or t - self.quando.get(chave, 0) >= segundos:
            try:
                self.cache[chave] = funcao()
            except Exception as erro:                       # nunca derruba o painel
                self.cache[chave] = self.cache.get(chave) or {"erro": str(erro)[:200]}
            self.quando[chave] = t
        return self.cache[chave]

    # --- estado.json: relê só quando o mtime muda
    def le_estado(self):
        try:
            m = os.path.getmtime(ESTADO)
        except OSError:
            return self.estado
        if m != self.estado_mtime or self.estado is None:
            for _ in range(3):                              # pode pegar a escrita no meio
                try:
                    with open(ESTADO, encoding="utf-8") as f:
                        self.estado = json.load(f)
                    self.estado_mtime = m
                    break
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.2)
        return self.estado

    # --- recursos (5 s)
    def recursos(self):
        mem = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for l in f:
                p = l.split()
                mem[p[0].rstrip(":")] = int(p[1]) // 1024   # MB
        r1 = os.statvfs("/")
        try:
            r2 = os.statvfs("/mnt/pgdata")
            pg = round(100 * (1 - r2.f_bavail / r2.f_blocks), 1)
            pg_livre = round(r2.f_bavail * r2.f_frsize / 2**30, 1)
        except OSError:
            pg, pg_livre = None, None
        return {
            "mem_disponivel_mb": mem.get("MemAvailable", 0),
            "mem_total_mb": mem.get("MemTotal", 0),
            "troca_usada_mb": mem.get("SwapTotal", 0) - mem.get("SwapFree", 0),
            "troca_total_mb": mem.get("SwapTotal", 0),
            "disco_raiz_pct": round(100 * (1 - r1.f_bavail / r1.f_blocks), 1),
            "disco_raiz_livre_gb": round(r1.f_bavail * r1.f_frsize / 2**30, 1),
            "disco_pgdata_pct": pg,
            "disco_pgdata_livre_gb": pg_livre,
            "carga": [round(x, 2) for x in os.getloadavg()],
        }

    # --- conexões (15 s, UMA conexão mantida aberta)
    def _dsn(self):
        try:
            for l in open(f"{REPO}/.env", encoding="utf-8"):
                if l.startswith("PLAT_DSN="):
                    return l.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
        return os.environ.get("PLAT_DSN")

    def conexoes(self):
        if self.dsn:
            try:
                import psycopg2
                if self.conexao is None or self.conexao.closed:
                    self.conexao = psycopg2.connect(self.dsn, connect_timeout=5,
                                                    application_name="painel_vivo")
                    self.conexao.autocommit = True
                with self.conexao.cursor() as c:
                    c.execute("select count(*), count(*) filter (where state='active') "
                              "from pg_stat_activity")
                    total, ativas = c.fetchone()
                return {"total": total, "ativas": ativas, "teto": TETO_CONEXOES,
                        "fonte": "psycopg2"}
            except Exception as erro:
                try:
                    if self.conexao:
                        self.conexao.close()
                except Exception:
                    pass
                self.conexao = None
                falha = str(erro)[:120]
        else:
            falha = "sem PLAT_DSN"
        s = sh("sudo -n -u postgres psql -d iagro_sat -tAc "
               "\"select count(*) from pg_stat_activity\"", timeout=10).strip()
        if s.isdigit():
            return {"total": int(s), "ativas": None, "teto": TETO_CONEXOES, "fonte": "psql"}
        return {"total": None, "ativas": None, "teto": TETO_CONEXOES, "erro": falha}

    # --- git (30 s)
    def git(self):
        bruto = sh("git log --all --date=iso-strict --since='7 days ago' "
                   "--format='\x01%h\x02%cI\x02%s\x02%b'", cwd=REPO, timeout=40)
        commits = []
        por_item = {}
        for pedaco in bruto.split("\x01"):
            if not pedaco.strip():
                continue
            partes = pedaco.split("\x02")
            if len(partes) < 3:
                continue
            sha, quando, assunto = partes[0], partes[1], partes[2]
            corpo = partes[3] if len(partes) > 3 else ""
            commits.append({"sha": sha, "quando": quando, "assunto": assunto.strip()})
            for iid in set(ID_ITEM.findall(assunto + " " + corpo)):
                if iid not in por_item:                     # log já vem do mais novo
                    por_item[iid] = {"sha": sha, "quando": quando,
                                     "assunto": assunto.strip()[:110]}
        # commits por hora nas últimas 24 h
        agora = datetime.datetime.now().astimezone()
        baldes = {}
        for c in commits:
            try:
                t = datetime.datetime.fromisoformat(c["quando"])
            except ValueError:
                continue
            h = int((agora - t).total_seconds() // 3600)
            if 0 <= h < 24:
                baldes[h] = baldes.get(h, 0) + 1
        por_hora = [{"horas_atras": h, "n": baldes.get(h, 0)} for h in range(23, -1, -1)]

        # fila de merge: ramos de worktree à frente do master
        fila = []
        if os.path.isdir(WT):
            for nome in sorted(os.listdir(WT)):
                cam = f"{WT}/{nome}"
                if not os.path.isdir(f"{cam}/.git") and not os.path.exists(f"{cam}/.git"):
                    continue
                ramo = sh("git rev-parse --abbrev-ref HEAD", cwd=cam, timeout=15).strip()
                n = sh(f"git rev-list --count master..{ramo or 'HEAD'}", cwd=cam, timeout=20).strip()
                arq = [x for x in sh(f"git diff --name-only master...{ramo or 'HEAD'}",
                                     cwd=cam, timeout=20).splitlines() if x.strip()]
                sujo = len([x for x in sh("git status --porcelain", cwd=cam,
                                          timeout=20).splitlines() if x.strip()])
                ult = sh("git log -1 --format='%h %cI %s'", cwd=cam, timeout=15).strip()
                if not n.isdigit():
                    continue
                fila.append({
                    "trilha": nome, "ramo": ramo, "commits_a_frente": int(n),
                    "arquivos": len(arq), "sujos": sujo,
                    "quentes": sorted(set(arq) & set(QUENTES)),
                    "ultimo_commit": ult,
                })
        return {"ultimos_commits": commits[:12], "por_item": por_item,
                "commits_por_hora": por_hora, "commits_24h": sum(b["n"] for b in por_hora),
                "fila_merge": fila}

    # --- agentes registrados pelo supervisor (a cada volta: são poucos arquivos)
    def agentes(self):
        saida = []
        if not os.path.isdir(AGENTES):
            return saida
        for nome in sorted(os.listdir(AGENTES)):
            if not nome.endswith(".json"):
                continue
            try:
                with open(f"{AGENTES}/{nome}", encoding="utf-8") as f:
                    a = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            vivo = processo_vivo(a.get("pid", 0), a.get("starttime"))
            t0 = a.get("inicio_ts") or 0
            ultima = ""
            log = a.get("log")
            if log and os.path.exists(log):
                try:
                    with open(log, "rb") as f:
                        f.seek(max(0, os.path.getsize(log) - 4096))
                        linhas = [l for l in f.read().decode("utf-8", "replace").splitlines()
                                  if l.strip()]
                    ultima = linhas[-1][:160] if linhas else ""
                except OSError:
                    pass
            saida.append({
                "id": a.get("id", nome[:-5]), "item": a.get("item"), "pid": a.get("pid"),
                "trilha": a.get("trilha"), "papel": a.get("papel", "construtor"),
                "inicio": a.get("inicio"), "vivo": vivo,
                "decorrido_s": int(time.time() - t0) if t0 else None,
                "log": log, "ultima_linha": ultima, "tentativa": a.get("tentativa"),
            })
        return saida

    def leases(self):
        saida = []
        if not os.path.isdir(LEASES):
            return saida
        for nome in sorted(os.listdir(LEASES)):
            try:
                with open(f"{LEASES}/{nome}", encoding="utf-8") as f:
                    saida.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                pass
        return saida

    # --- achados de adversário abertos (60 s: mexe em disco)
    def adversario(self, backlog):
        por_id = {x["id"]: x for x in backlog}
        abertos = []
        for x in backlog:
            if x["estado"] == "refutado":
                abertos.append({"item": x["id"], "linha": x.get("linha"),
                                "motivo": (x.get("bloqueio") or "refutado pelo adversário")[:220],
                                "fonte": "estado.json"})
        vistos = {a["item"] for a in abertos}
        raiz = f"{BASE}/handoffs"
        for pasta, _, arquivos in os.walk(raiz):
            for nome in arquivos:
                if "ADVERS" not in nome.upper():
                    continue
                cam = os.path.join(pasta, nome)
                try:
                    txt = open(cam, encoding="utf-8", errors="ignore").read(8000)
                except OSError:
                    continue
                if not re.search(r"REPROV|FALH|NÃO PASSA|NAO PASSA|VETO", txt, re.I):
                    continue
                for iid in dict.fromkeys(ID_ITEM.findall(nome + " " + txt[:2500])):
                    it = por_id.get(iid)
                    if not it or iid in vistos or it["estado"] == "entregue":
                        continue
                    vistos.add(iid)
                    abertos.append({
                        "item": iid, "linha": it.get("linha"),
                        "motivo": "laudo com reprovação e item ainda não entregue",
                        "fonte": os.path.relpath(cam, BASE)})
        return abertos

    # ------------------------------------------------------------- retrato
    def retrato(self):
        rec = self.cada("recursos", 5, self.recursos)
        con = self.cada("conexoes", 15, self.conexoes)
        g = self.cada("git", 30, self.git)
        e = self.le_estado() or {}
        backlog = e.get("backlog", [])
        adv = self.cada("adversario", 60, lambda: self.adversario(backlog))
        ags = self.agentes()

        por_item_agente = {}
        for a in ags:
            if a["vivo"] and a.get("item"):
                por_item_agente.setdefault(a["item"], a)

        estados = {}
        linhas = {}
        for x in backlog:
            estados[x["estado"]] = estados.get(x["estado"], 0) + 1
            L = (x.get("linha") or "?").split()[0]
            d = linhas.setdefault(L, {"linha": L, "titulo": x.get("linha"), "total": 0})
            d["total"] += 1
            d[x["estado"]] = d.get(x["estado"], 0) + 1

        por_id = {x["id"]: x for x in backlog}
        itens = []
        for x in backlog:
            ag = por_item_agente.get(x["id"])
            interessante = (x["estado"] != "pendente" or ag or x.get("bloqueio"))
            if not interessante:
                continue
            abertas = [d for d in (x.get("dependencias") or [])
                       if d not in por_id or por_id[d]["estado"] != "entregue"]
            itens.append({
                "id": x["id"], "linha": (x.get("linha") or "?").split()[0],
                "estado": x["estado"], "tentativas": x.get("tentativas", 0),
                "bloqueio": (x.get("bloqueio") or "")[:240] or None,
                "dependencias_abertas": abertas,
                "agente": ag["id"] if ag else None,
                "agente_pid": ag["pid"] if ag else None,
                "agente_ha_s": ag["decorrido_s"] if ag else None,
                "ultimo_commit": g.get("por_item", {}).get(x["id"]),
            })
        itens.sort(key=lambda i: ({"tentando": 0, "refutado": 1, "parcial": 2,
                                   "pendente": 3, "entregue": 4}.get(i["estado"], 5), i["id"]))

        sup = f"{BASE}/.supervisor.lock"
        sup_estado = None
        pausa = f"{VIVO}/pausa.json"
        if os.path.exists(pausa):
            try:
                sup_estado = json.load(open(pausa, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                sup_estado = None

        return {
            "gerado_em": agora_iso(),
            "gerado_ts": round(time.time(), 1),
            "estado_do_laco": e.get("estado"), "turno": e.get("turno"),
            "placar": e.get("placar", {}),
            "estados": estados,
            "linhas": [linhas[k] for k in sorted(linhas)],
            "itens": itens,
            "agentes": ags,
            "leases": self.leases(),
            "fila_merge": g.get("fila_merge", []),
            "ultimos_commits": g.get("ultimos_commits", []),
            "commits_por_hora": g.get("commits_por_hora", []),
            "commits_24h": g.get("commits_24h", 0),
            "adversario_aberto": adv,
            "recursos": dict(rec, conexoes=con),
            "supervisor": {
                "trava": os.path.exists(sup),
                "pausa": sup_estado,
            },
            "cadencias": {k: round(time.time() - v, 1) for k, v in self.quando.items()},
        }


def grava(retrato):
    os.makedirs(VIVO, exist_ok=True)
    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(retrato, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, SAIDA)


def serve():
    """Servidor mínimo, só em 127.0.0.1, servindo laco/vivo/."""
    import http.server
    import socketserver

    class Mao(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=VIVO, **k)

        def do_GET(self):
            if self.path in ("/", ""):
                self.path = "/painel.html"
            return super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            super().end_headers()

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORTA), Mao) as s:
        s.daemon_threads = True
        s.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="coletor do painel vivo")
    ap.add_argument("--uma-vez", action="store_true", help="colhe uma vez e sai")
    ap.add_argument("--servir", action="store_true",
                    help="laço + servidor em 127.0.0.1:%d" % PORTA)
    ap.add_argument("--intervalo", type=float, default=5.0)
    a = ap.parse_args()

    c = Coletor()
    if a.uma_vez:
        r = c.retrato()
        grava(r)
        print(SAIDA)
        return

    trava = open(TRAVA, "a+")
    try:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("já existe um painel_vivo rodando (o painel não pode disputar recurso)")

    if a.servir:
        import threading
        threading.Thread(target=serve, daemon=True).start()
        print(f"painel em http://127.0.0.1:{PORTA}/  (só localhost)")
    while True:
        try:
            grava(c.retrato())
        except Exception as erro:
            print("volta falhou:", str(erro)[:200], file=sys.stderr)
        time.sleep(a.intervalo)


if __name__ == "__main__":
    main()
