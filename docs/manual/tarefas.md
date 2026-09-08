---
id: tarefas
titulo: Tarefas
titulo_en: Tasks
titulo_es: Tareas
resumo: "fila de jobs: executados, em curso e falhos; agendas e periódicos; log e repetição"
resumo_en: "job queue: done, running and failed; schedules and periodic jobs; log and retry"
resumo_es: "fila de trabajos: ejecutados, en curso y fallidos; agendas y periódicos; registro y repetición"
classe: tela
pagina: tarefas.html
caminho: /tarefas
e2e: tests/e2e/test_tarefas.py
captura: L0-05-jobs_lista.png
e2e_captura: "{ITEM}_lista.png"
palavras: [tarefas, jobs, fila, agenda, periodico, log, repetir, cancelar, worker]
palavras_en: [tasks, jobs, queue, schedule, periodic, log, retry, cancel, worker]
palavras_es: [tareas, jobs, fila, agenda, periodico, registro, repetir, cancelar, worker]
---

## Tarefas

A tela Tarefas é a fila de trabalho do inquilino: cargas de dados, ingestões e rotinas aparecem
aqui como jobs. Exige o privilégio `jobs.executar`.

### Lista e detalhe

A lista mostra cada job com tipo, estado (pendente, em execução, concluído, falho) e tempo. O
detalhe traz o log completo do worker, linha por linha, e os parâmetros do job.

### Cancelar e repetir

Um job pendente ou em execução pode ser cancelado; um job concluído ou falho pode ser repetido com
os mesmos parâmetros. O log do job anterior fica guardado.

### Agendas

A seção Agendas cria repetição por expressão cron (fuso do inquilino) e a seção Periódicos mostra
as rotinas de fábrica da plataforma. Cada agenda lista as próximas execuções e pode ser pausada.

A captura desta seção é produzida pelo teste de ponta a ponta da própria tela
(`tests/e2e/test_tarefas.py`) contra a versão atual.
