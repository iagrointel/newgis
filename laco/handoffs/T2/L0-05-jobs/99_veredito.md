# T2 · L0-05-jobs — veredito do gerente (provisório até P3 e os consertos)

Testador: 40_testes.md + medidas 5fe53c0 (25 medidas). Adversário: refutacao.json = PASSA (4 reproduções da refutação literal).

| cláusula do portão | evidência | veredito |
|---|---|---|
| job de 5 min mostra progresso em tempo real | SSE público, 62 eventos, 1º em 6 ms, latência banco→cliente 5 ms, 300,2 s | passa |
| pode ser cancelado | 0,426 s por API, 0,24 s pela tela (portão ≤ 2 s) | passa |
| sobrevive a reinício (retoma ou marca falha, nunca some) | restart, kill -9 do filho, kill -9 do worker e restart duplo: volta a pendente com reinicios/erro registrados, reexecuta e só chega a concluido com marcador; 5×kill -9 → falhou | passa |
| 1 worker por padrão com limite de RAM declarado | unidade MemoryMax=2G/KillMode=mixed/OOMPolicy=continue/TimeoutStopSec=40 igual ao ADR; pico 27,3 MB; job de 3 GB morre e o worker sobrevive (NRestarts=0) | passa |
| tela Tarefas por inquilino | RLS 15/15 rotas + SSE; 17/17 sem sessão = 401; Last-Event-ID não atravessa job nem inquilino | passa |
| teste automatizado | suíte do item verde sob flock; vazão 1.614 jobs/min (1 worker) contra portão de 600 | passa |

Achados corrigidos no próprio turno: 006 (transição forjável por SQL como plat_app) e 012/013 (worker homônimo devolvia jobs alheios), ambos com teste.

Portões gerais: P1 reprova só no perfil visualizador (403 + 4 erros de console) — conserto em curso · P2 0 placeholder · **P3 pendente** (suíte inteira depende do commit do catálogo) · P4 12 linhas de paridade em docs/PARIDADE.md · P5 install do zero exercitado na reinstalação da trilha A · P6 passa · P7 passa · **P8 PASSA** · P9 documentado pelo cronista.

Estado: **parcial** — mecanismo provado de ponta a ponta; faltam os 3 consertos (semeadura do e2e, perfil visualizador, Cache-Control) e P3.

Fraquezas registradas pelo adversário, que viram itens/portões e não bloqueiam este:
1. `plat_trabalho.passos/marcadores` sem RLS (scratch cruza inquilino) → portão do L0-05 e do L7-03.
2. `PLAT_DSN_WORKER` dá autoridade total sobre estado de job de todos os inquilinos com nome de worker público → modelo de ameaça no L7-03 (segredo por unidade, LoadCredential).
3. `plat_app` com DELETE em `plat.job` (over-grant confinado por RLS) → grant mínimo.
