# Revisão Codex 001 — evidência e coordenação

Data: 2026-09-06T00:48:59.947245+00:00. HEAD observado: `94a669c6601f119a240648f5dad6e7db37049f93`.
Escopo: leitura de estado, handoffs, histórico da sessão e situação do git.
Não é aprovação funcional, revisão completa de segurança ou medição nova.

## Achados

1. Estado vivo: 505 itens. O painel ainda declara 501 itens e geração
   em 05/09 17:55 UTC. Não usar esse painel para afirmar o avanço atual. Após
   reconciliar o estado, o integrador deve executar os geradores existentes.
2. O catálogo está `pendente` no estado, com evento de órfão no ledger às 23:30,
   mas há alterações locais em `app/catalogo/comum.py`, `rotas_itens.py` e migrações
   019/020. `trilhas.json` ainda informa etapas antigas. Reconciliar a titularidade
   antes de outro gerente/driver assumir o item; a existência das mudanças sozinha
   não prova que um agente continua vivo.
3. O último `40_testes.md` registra 610 passed/2 failed no check e 633 passed/4 failed
   em medidas; `lista_tipo_p95_ms` foi 161,8/198,2/203,0 ms contra <100 ms. P3 e o
   portão de desempenho não estão demonstrados como aprovados por essa evidência.
   A atribuição da causa ao ambiente é hipótese, não resultado estabelecido.
4. Os testes citados no handoff referem `65a9fc2c0869`; HEAD atual é `94a669c6601f119a240648f5dad6e7db37049f93` e há
   mudanças locais. Uma aprovação antiga não cobre automaticamente as mudanças
   posteriores. Identificar o diff final antes da nova validação serializada.
5. D38 consta como decidida no estado: GNM, L8 separada, infraestrutura privada
   combinada com parcelas/BIM. Isso confirma o registro da decisão; não confirma
   implementação, conformidade INSPIRE, demanda comercial ou afirmações jurídicas.

## Evidência reproduzível

- `tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_current_path}'`
  não listou uma sessão plataforma.
- `git -C /home/dev/plataforma/enterprise rev-parse HEAD`: `94a669c6601f119a240648f5dad6e7db37049f93`.
- `git -C /home/dev/plataforma/enterprise status --short`: catálogo e medidas
  modificados; migrações 019/020 e scratchpad não rastreados na leitura inicial.
- Valores dos testes acima transcritos de `handoffs/T2/L0-03-catalogo/40_testes.md`.
- Hashes e horários dos arquivos lidos: `snapshot_inicial.json`.

## Para o próximo papel

Claude: confirmar recebimento, reconciliar os estados e publicar o commit final
e evidência de correção. Codex: revisar o diff identificado e pedir medições que
resolvam as cláusulas pendentes. Veredito desta revisão: PARCIAL, sem fechamento
de itens. Nenhum teste pesado ou serviço foi iniciado/reiniciado nesta revisão.
