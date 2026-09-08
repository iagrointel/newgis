# Coordenação plataforma1 (Claude) e plataforma2 (Codex)

Atualizado em 2026-09-06T00:48:59.947245+00:00.
Estado: canal por arquivos preparado; ciência de plataforma1 AINDA NÃO CONFIRMADA.

## Mandato do dono

O dono autorizou as duas sessões a trabalhar no mesmo fluxo e designou plataforma2
como responsável por arquitetura, revisão crítica e verificação das afirmações.
Não existe garantia de verdade absoluta: cada conclusão deve indicar evidência,
revisão do código, limitações e o que ainda não foi verificado.

## Sessões identificadas

- plataforma1: Claude, conversa `a44f35ad-ead9-4a5b-9329-6c154aa35f9e`.
  A identificação foi confirmada pelo texto sobre D38/L8 colado pelo dono e
  pelo registro local em `.claude/projects/-home-dev/`.
- plataforma2: Codex, conversa `01a07425-201b-7063-b5d6-c4f345d53dfb`, cwd `/home/dev`.
- Nenhuma sessão plataforma/plataforma1/plataforma2 apareceu em `tmux list-panes -a`
  na verificação inicial. Não houve envio direto ao terminal nem reinício.

## Divisão proposta, pendente de confirmação por plataforma1

- Claude continua integrador da implementação e dos agentes já ativos. Mantém a
  escrita de `estado.json`, `trilhas.json`, ledger e painéis gerados.
- Codex conduz a revisão arquitetural e de evidência. Publica achados nesta pasta;
  não aprova o próprio código nem substitui os portões P1–P9.
- Antes de Codex alterar código, combinar por mensagem item, arquivos, responsável
  e revisão-base. Até então, o trabalho de Codex no produto é leitura e revisão.
- Decisão comercial ou de produto continua pertencendo ao dono. D38 é preservada;
  alinhamento pretendido ao INSPIRE não equivale a conformidade já demonstrada.
- Não alterar projetos vizinhos. Todo teste de máquina usa o flock já exigido:
  `flock /home/dev/plataforma/laco/.pytest.lock <comando>`.
- Nenhum teste pesado novo é iniciado enquanto os trabalhos ativos não forem
  coordenados. Não tomar `.turno_ativo` nem abrir um turno concorrente.

## Troca de mensagens

1. Codex escreve apenas `codex_para_claude.md` e suas revisões `REVISAO_CODEX_*.md`.
2. Claude escreve apenas `claude_para_codex.md`, incluindo recebimento explícito,
   agentes ativos, áreas ocupadas, revisões prontas e mudanças pedidas ao Codex.
3. Cada sessão lê a mensagem da outra ao retomar e antes de atribuir novos trabalhos
   ou fechar um item. Arquivo existente não significa mensagem recebida.
4. Handoff de revisão: item, portão literal, commit e mudanças não commitadas,
   comandos e saídas, caminho das medidas, pendências e decisão solicitada.
5. Codex responde por cláusula: PASSA, PARCIAL, REFUTADO ou NÃO VERIFICADO, com
   evidência. Quem integra registra a conclusão no estado depois de conferir P1–P9.

Este canal é persistente, mas não cria notificação, agendamento nem memória
compartilhada automaticamente. A primeira leitura por Claude precisa ser solicitada.
