import json, time, collections
e=json.load(open('/home/dev/plataforma/laco/estado.json')); b=e['backlog']; p=e['placar']; tot=p['total']
LIN={'L0':'L0 fundação','L1':'L1 imagens','L2':'L2 plataforma','L3':'L3 motor multicritério','L4':'L4 rede de utilidades','L5':'L5 construtores','L6':'L6 conectores','L7':'L7 operação'}
c=collections.defaultdict(collections.Counter)
for x in b:
    l=x['id'].split('-')[0]
    if l in LIN: c[l][x['estado']]+=1
def barra(ent,par,ref,t,w=40):
    n=lambda v: round(v*w/t) if t else 0
    return '#'*n(ent)+'~'*n(par)+'!'*n(ref)+'.'*max(0,w-n(ent)-n(par)-n(ref))
q=time.strftime('%d/%m/%Y %H:%M UTC', time.gmtime())
out=[f"# Status da corrida — {q}\n",
"Gerado de `laco/estado.json` pelo supervisor. `#` provado (portão passou e adversário não refutou) · `~` parcial (cláusula pendente nomeada) · `!` refutado pelo adversário, conserto em curso · `.` não iniciado.\n",
f"**{p['entregues']} provados · {p['parciais']} parciais · {p['refutados']} refutados · {tot-p['entregues']-p['parciais']-p['refutados']} na fila · {tot} itens**\n","```"]
for l in sorted(LIN):
    d=c[l]; t=sum(d.values())
    out.append(f"{LIN[l]:<24} {barra(d['entregue'],d['parcial'],d['refutado'],t)}  {d['entregue']:3}/{t}")
out.append("```\n")
out.append("## Como um item vira \"provado\"\n\n```\nFABLE dirige · elege itens · junta os ramos · arbitra\n   |\n   +--> SONNET constrói ou conserta em worktree próprio, base de banco própria\n   |          |  commit no ramo wt/<item>\n   v          v\nFILA DE JUNÇÃO  lote de 6-11 ramos · suíte inteira uma vez por lote · bisseção acha o culpado\n   |\n   v\nADVERSÁRIO  agente separado que não viu a construção · suposições transversais da linha primeiro\n   |         · achado vira teste xfail(strict=True)\n   +--> achou? volta para SONNET consertar --> fila --> até o adversário não achar nada\n```\n")
out.append("## Leitura honesta\n\nO vermelho não é trabalho perdido. São itens que estavam marcados como prontos e caíram quando um adversário independente os verificou: de 60 itens declarados entregues ou parciais no início de 06/09, só 8 tinham laudo; dos verificados, 7 em 8 caíram, com achados de segurança reais. Cada conserto entra com o teste do ataque junto.\n\nO padrão que explica quase tudo o que caiu: **o que é protegido por linha aguentou todos os ataques; o que é recurso partilhado (fila, trinco, schema de dados, contador de cota, porta, nome de tarefa agendada, permissão de função) não tinha dimensão de inquilino nenhuma.**\n")
out.append("## Onde está cada coisa\n\n- `PLANO_DA_CORRIDA.md` — o plano aprovado pelo dono.\n- `docs/adr/` — decisões de arquitetura, uma por arquivo.\n- `CHANGELOG.md` — o que mudou, por item.\n- `db/migracoes/` — as novas usam carimbo de tempo; o legado numérico é imutável.\n- Ramos `wt/<item>` — um worktree por item; entram em `master` só pela fila de junção.\n")
open('/home/dev/plataforma/enterprise/STATUS.md','w').write('\n'.join(out))
