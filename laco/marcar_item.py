#!/usr/bin/env python3
"""Atualiza um item do estado.json (read-modify-write curto, com lock). Uso:
marcar_item.py <id> <estado: entregue|parcial|pendente> "<bloqueio ou nota>" [commit_sha]"""
import fcntl, json, os, sys, datetime
p = '/home/dev/plataforma/laco/estado.json'
TRAVA = '/home/dev/plataforma/laco/.estado.lock'  # combinado com a outra sessão em 06/09: TODA
# leitura-modifica-escrita do estado.json passa por esta trava externa. A trava no próprio arquivo
# não bastava: só protege contra quem também trava, e a outra sessão escrevia sem trava nenhuma
# (uma escrita minha foi perdida assim). Quem não usa a trava continua podendo sobrescrever.
_trava = open(TRAVA, 'a+')
fcntl.flock(_trava, fcntl.LOCK_EX)
iid, estado, nota = sys.argv[1], sys.argv[2], sys.argv[3]
sha = sys.argv[4] if len(sys.argv) > 4 else None
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
