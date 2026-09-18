#!/usr/bin/env python3
"""Atualiza um item do estado.json (read-modify-write curto, com lock). Uso:
marcar_item.py <id> <estado: entregue|parcial|pendente> "<bloqueio ou nota>" [commit_sha]

HARD-03 (laudo T9 linha-L7-2): 'entregue' é RECUSADO quando nenhum laudo adversário em
handoffs/ cita o item — cinco itens ficaram entregues por turnos sem laudo porque este script
não conferia. Escape só do dono: PLAT_MARCAR_SEM_LAUDO="<motivo>" no ambiente; o motivo fica
gravado na nota do ledger como SEM-LAUDO(dono) e o lote (adversario_lote.py) o lista em alto
relevo até o laudo existir. A base inteira pode ser trocada com PLAT_LACO (testes)."""
import fcntl, json, os, sys, datetime
BASE = os.environ.get('PLAT_LACO', '/home/dev/plataforma/laco')
p = f'{BASE}/estado.json'
TRAVA = f'{BASE}/.estado.lock'  # combinado com a outra sessão em 06/09: TODA
# leitura-modifica-escrita do estado.json passa por esta trava externa. A trava no próprio arquivo
# não bastava: só protege contra quem também trava, e a outra sessão escrevia sem trava nenhuma
# (uma escrita minha foi perdida assim). Quem não usa a trava continua podendo sobrescrever.
iid, estado, nota = sys.argv[1], sys.argv[2], sys.argv[3]
sha = sys.argv[4] if len(sys.argv) > 4 else None
if estado == 'entregue':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from adversario_lote import itens_com_laudo
    if not itens_com_laudo(BASE, [iid]):
        motivo = os.environ.get('PLAT_MARCAR_SEM_LAUDO')
        if not motivo:
            sys.exit(f"RECUSADO (HARD-03): '{iid}' não pode virar entregue — nenhum laudo "
                     f"adversário em {BASE}/handoffs o cita. Marque 'parcial', chame o adversário "
                     f"(prompt_adversario) e só depois de escrito o laudo marque entregue.")
        nota = f'SEM-LAUDO(dono): {motivo} | {nota}'
_trava = open(TRAVA, 'a+')
fcntl.flock(_trava, fcntl.LOCK_EX)
with open(p, 'r+', encoding='utf-8') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    e = json.load(f)
    it = next(x for x in e['backlog'] if x['id'] == iid)
    it['estado'] = estado
    it['bloqueio'] = None if estado == 'entregue' else nota
    it['turno'] = e.get('turno', 3)
    it['tentativas'] = it.get('tentativas', 0) + 1
    e.setdefault('ledger', []).append({
        'quando': datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'item': iid, 'estado': estado, 'nota': nota, 'commit': sha, 'sessao': 'worktrees-2'})
    b = e['backlog']
    e['placar'] = {'entregues': sum(x['estado'] == 'entregue' for x in b),
                   'parciais': sum(x['estado'] == 'parcial' for x in b),
                   'refutados': sum(x['estado'] == 'refutado' for x in b),
                   'total': len(b), 'turnos': e['placar'].get('turnos', 3)}
    # escrita ATÔMICA (achado 06/09): seek+truncate+dump deixa um leitor concorrente ver JSON
    # pela metade — o painel vivo e a outra sessão leem este arquivo o tempo todo. Grava em
    # temporário no MESMO diretório (os.replace só é atômico dentro do mesmo sistema de arquivos)
    # e substitui. A trava externa continua valendo para quem escreve.
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as g:
        json.dump(e, g, ensure_ascii=False, indent=1)
        g.flush(); os.fsync(g.fileno())
    os.replace(tmp, p)
print(iid, '->', estado, e['placar'])
