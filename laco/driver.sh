#!/bin/bash
# DRIVER do laço PLATAFORMA ENTERPRISE — nível MEDIÇÃO (sem modelo, custo zero):
#  1. integridade do estado.json; itens 'tentando' órfãos (> 4 h) voltam a pendente;
#  2. varredura de placeholder no repositório (TODO/FIXME/mock/em breve/lorem) -> laco/placeholders.txt;
#  3. saúde dos serviços plat-* e da API (/saude);
#  4. pytest rápido (se existir) -> laco/ultimo_check.txt;
#  5. AUTOTURNO: se estado ATIVO, autoturno=true, nenhum turno ativo, último ledger > 90 min,
#     RAM disponível >= 5 GB e disco < 99 %, lança UM turno de modelo em segundo plano (claude -p)
#     para o laço sobreviver à morte da sessão interativa. Nunca dois turnos ao mesmo tempo.
set -u
B=/home/dev/plataforma/laco
R=/home/dev/plataforma/enterprise
exec 9>"$B/.trava"; flock -n 9 || exit 0
E="$B/estado.json"; [ -f "$E" ] || exit 1
AG=$(date '+%Y-%m-%d %H:%M')
LOG="$B/driver.log"

# --- 1. estado + órfãos
python3 - "$E" "$AG" >> "$LOG" 2>&1 <<'PY'
import json, sys, time, datetime
E, ag = sys.argv[1], sys.argv[2]
e = json.load(open(E))
if e["estado"] != "ATIVO":
    print(f"[{ag}] terminal {e['estado']}"); raise SystemExit
mud = False
agora = datetime.datetime.now()
import os
ta = f"{B}/.turno_ativo" if False else "/home/dev/plataforma/laco/.turno_ativo"
gerente_vivo = os.path.exists(ta) and (time.time() - os.path.getmtime(ta)) < 3*3600
for x in e["backlog"]:
    if x["estado"] == "tentando" and x.get("tentando_desde") and not gerente_vivo:
        t0 = datetime.datetime.fromisoformat(x["tentando_desde"])
        if (agora - t0).total_seconds() > 4*3600:
            x["estado"] = "pendente"; x["bloqueio"] = f"órfão devolvido pelo driver em {ag}"; mud = True
            e["ledger"].append({"turno": e["turno"], "quando": ag, "item": x["id"], "evento": "interrompido (sessão morta), devolvido a pendente"})
pend = sum(1 for x in e["backlog"] if x["estado"] == "pendente")
tent = [x["id"] for x in e["backlog"] if x["estado"] == "tentando"]
ent = sum(1 for x in e["backlog"] if x["estado"] == "entregue")
par = sum(1 for x in e["backlog"] if x["estado"] == "parcial")
e["placar"] = {"entregues": ent, "parciais": par, "refutados": sum(1 for x in e["backlog"] if x["estado"]=="refutado"), "total": len(e["backlog"]), "turnos": e["turno"]}
if mud: json.dump(e, open(E, "w"), ensure_ascii=False, indent=1)
print(f"[{ag}] turno {e['turno']} · entregues {ent} · parciais {par} · pendentes {pend} / {len(e['backlog'])} · tentando {tent}")
PY

# --- 2. placeholders (só código entregue: app/, web/, db/, docs/; ignora tests/ e vendor/)
if [ -d "$R" ]; then
  grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv \
    -E 'TODO|FIXME|XXX|lorem ipsum|em breve|coming soon|placeholder|mock[A-Z_(]|not implemented|NotImplemented' "$R" 2>/dev/null \
    | grep -v 'laco/' > "$B/placeholders.txt" || true
  NP=$(wc -l < "$B/placeholders.txt"); echo "[$AG] placeholders no repositório: $NP" >> "$LOG"
fi

# --- 3. saúde
for u in plat-api plat-martin plat-titiler plat-worker; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^$u.service"; then
    echo "[$AG] $u: $(systemctl is-active $u)" >> "$LOG"
  fi
done
if curl -fsS -m 5 http://127.0.0.1:8150/saude >/dev/null 2>&1; then echo "[$AG] api /saude OK" >> "$LOG"; else echo "[$AG] api /saude SEM RESPOSTA" >> "$LOG"; fi

# --- 4. pytest rápido (marcador 'rapido'), só se existir
if [ -f "$R/pytest.ini" ] || [ -d "$R/tests" ]; then
  # 06/09: o driver rodava a suite SEM os segredos (sempre ErroConfiguracao: sinal de saude
  # permanentemente vermelho e sem significado) e SEM a trava (competia com os agentes a cada
  # 30 min, violando a regra do proprio laco). Corrigido: segredos exportados + flock com espera
  # curta (se a fila estiver ocupada, o driver desiste em vez de furar a fila).
  ( cd "$R" \
    && PLAT_SECRET=$(sudo cat /etc/plat/segredos/PLAT_SECRET 2>/dev/null) \
       PLAT_DSN_WORKER=$(sudo cat /etc/plat/segredos/PLAT_DSN_WORKER 2>/dev/null) \
       timeout 600 flock -w 120 "$B/.pytest.lock" ./venv/bin/python -m pytest -q -x -m "not lento" tests 2>&1 | tail -3 \
    || echo "fila do pytest ocupada ou suite falhou (ver acima)" ) > "$B/ultimo_check.txt" 2>&1
  echo "[$AG] pytest: $(grep -E "passed|failed|error" "$B/ultimo_check.txt" | tail -1)" >> "$LOG"
fi

# --- 5. AUTOTURNO
python3 - "$E" >/dev/null 2>&1 <<'PY' || exit 0
import json, sys, datetime, os, subprocess
e = json.load(open(sys.argv[1]))
if not e.get("autoturno"): raise SystemExit(1)
B = "/home/dev/plataforma/laco"
if os.path.exists(f"{B}/.turno_ativo"):
    t = json.load(open(f"{B}/.turno_ativo"))
    if (datetime.datetime.now() - datetime.datetime.fromisoformat(t["inicio"])).total_seconds() < 4*3600: raise SystemExit(1)
    os.remove(f"{B}/.turno_ativo")
ult = None
for l in e["ledger"]:
    try: ult = datetime.datetime.strptime(l["quando"], "%Y-%m-%d %H:%M")
    except Exception: pass
if ult and (datetime.datetime.now() - ult).total_seconds() < 90*60: raise SystemExit(1)
free = [l for l in open("/proc/meminfo") if l.startswith("MemAvailable")][0].split()[1]
if int(free) < 5*1024*1024: raise SystemExit(1)
st = os.statvfs("/"); uso = 1 - st.f_bavail/st.f_blocks
if uso > 0.99: raise SystemExit(1)
raise SystemExit(0)
PY
echo "[$AG] AUTOTURNO: lançando turno de modelo em segundo plano" >> "$LOG"
cd /home/dev/plataforma
# 06/09: o AUTOTURNO NUNCA disparou uma vez. Os dois unicos registros (05:00 e 05:30) dizem
# "bash: line 1: claude: command not found" — o cron nao tem /home/dev/.local/bin no PATH e o
# script chamava o binario pelo nome. Caminho absoluto resolve, e e a mesma regra que o proprio
# SKILL.md ja manda seguir para setsid/nohup.
CLAUDE=/home/dev/.local/bin/claude
# 06/09: se laco/var/kimi.env existir, o turno autônomo roda no modelo do dono (Kimi K3, janela de 1 Mi)
# em vez de consumir a cota da conta Anthropic — foi ela que derrubou agentes em massa 3x hoje.
if [ -f "$B/var/kimi.env" ]; then set -a; . "$B/var/kimi.env"; set +a; unset ANTHROPIC_API_KEY
  echo "[$AG] AUTOTURNO: modelo $ANTHROPIC_MODEL via $ANTHROPIC_BASE_URL" >> "$LOG"; fi
if [ ! -x "$CLAUDE" ]; then echo "[$AG] AUTOTURNO abortado: $CLAUDE nao existe" >> "$LOG"; exit 0; fi
setsid nohup "$CLAUDE" -p "Execute UM turno do laço PLATAFORMA ENTERPRISE seguindo à risca /home/dev/.claude/skills/plataforma-enterprise/SKILL.md (você é o GERENTE). Ao terminar o turno, pare." --dangerously-skip-permissions \
  > "$B/autoturno_$(date +%Y%m%d_%H%M).log" 2>&1 < /dev/null &
