# laco/ — a máquina que constrói este repositório

Cópia versionada do laço de construção (o original vive em `/home/dev/plataforma/laco` no servidor).
Com este diretório, outra pessoa ou outra máquina consegue RETOMAR a construção, não só ler o produto.

Ordem de leitura: `README.md` (ponto de retomada) → `SKILL_plataforma-enterprise.md` (o turno, os papéis, os
portões P1-P9) → `BRIEF_WORKTREES.md` (as regras que custaram caro, uma por incidente) → `estado.json`
(506 itens com portão de pronto e refutação) → `decomposicao/*_CONCEITO.md` (decisões que obrigam a não refazer)
→ `handoffs/T3/` (um repasse por item, com comando e saída) → `RETOMADA_20260906.md`.

Ferramentas: `prompt_item.py` (prompt pronto por item), `trilha_ambiente.sh` (base de banco por trilha),
`fila_merge.sh` (junção em lote com bisseção), `supervisor.py` (laço contínuo), `vigia.sh` (sobe/segura/desce),
`checklist.py` (lista viva), `painel_vivo.py` (painel), `sem_adversario.py` (fila de varredura por risco),
`marcar_item.py` (escreve o estado sob trava), `publica_github.sh` (envia lote verde para cá).

Fora daqui, de propósito: `var/` (segredos e credenciais de trilha) e `vivo/` (instantâneos, arrendamentos, logs).
Nomes de cliente e parceiro foram substituídos por descrição genérica nesta cópia (regra da casa).
