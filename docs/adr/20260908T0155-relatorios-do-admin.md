# Relatórios do admin como job e painel Atividade (item L0-07-e-relatorios)

Data: 08/09/2026. Estado: aceito. Par: ADR 0003 (fila de jobs), ADR 0004 seção 11.4 (exportação do catálogo como
objeto), `laco/decomposicao/L0_CONCEITO.md`.

## Contexto

O admin do inquilino não tinha relatório nenhum: só o log de acesso e os eventos em CSV (L0-02). A Esri entrega
relatórios de uso (membros, itens, grupos, atividade, uso) gerados em segundo plano, baixáveis, agendáveis e
entregues por e-mail, com limites declarados (12 meses, 10 mil itens, um por tipo por hora).

## Decisões

1. **Relatório é um job** (`relatorios.gerar`, `app/relatorios/tarefas.py`), não uma rota síncrona: uma consulta
   SQL sob a RLS do inquilino do job, CSV no armazenamento de objetos (classe `relatorio`, referência = id do job),
   exatamente o caminho de `catalogo.exportar_lista`. Download por `GET /api/relatorios/{job_id}/csv`, que lê o
   job pela fila (404 para outro inquilino, 409 antes de concluir).
2. **Cabeçalho documentado no código e na API**: `CABECALHOS` é a fonte única; `GET /api/relatorios/tipos`
   publica as colunas e os limites, e o teste compara o CSV gerado com a lista.
3. **Limites iguais aos da Esri, em `app/limites.py`** (`RELATORIO_JANELA_DIAS` 366, `RELATORIO_LINHAS_MAX`
   10 000, `RELATORIO_POR_TIPO_HORA` 1): a janela acima do teto é 422 antes de enfileirar; o CSV é cortado nas
   10 mil linhas e o resultado diz `truncado`; o segundo pedido do mesmo tipo na mesma hora é 429. O disparo por
   agenda (worker) não passa pela API e não conta no limite horário.
4. **Agendamento reaproveita `plat.agenda`**: `POST /api/relatorios/agendas` traduz diário/semanal/mensal em cron
   (`0 H * * *`, `0 H * * 1`, `0 H 1 * *`) e a janela de cada execução em `dias` (1/7/31); pausar, rodar agora e
   apagar continuam nas rotas de agenda do L0-05.
5. **Entrega por e-mail sem novo tipo de job**: o próprio job envia o link assinado do CSV (7 dias) ao e-mail do
   solicitante pelo SMTP efetivo do inquilino (`app/correio/cliente.py`); falha de envio vai ao log do job e ao
   resultado, nunca invalida o relatório. Não anexa o CSV (o link já é privado e o tamanho é livre).
6. **Dado pessoal**: o CSV de membros só carrega e-mail cujo domínio está em `auth.dominios_email` quando a lista
   está configurada (senão sai vazio); não existe CPF nem telefone no modelo. Adversário coberto por teste.
7. **Acessos por item vêm do log de acesso** (`plat.log_acesso.rota` guarda o caminho real, só a query string é
   redigida): contagem de `/api/itens/{id}` por id na janela, agregada uma vez por relatório e no painel.
8. **Uso é a série do que já é medido em master** (bytes registrados em `plat.arquivo`, itens, jobs, membros
   ativos por dia); a série medida do L0-07-c (`wt/il007ccotas`, ainda fora da fila) substitui quando entrar.
9. **Painel `/admin/atividade`** com gráficos SVG desenhados no próprio módulo (sem biblioteca), 10 itens mais
   acessados, pedidos de relatório e agendas; privilégio `org.exportar` (já semeado na 003 para isso).

## Consequências

- Os testes de fila rodam com um worker em subprocesso na base de trilha (`WorkerExtra` de
  `tests/api/jobs/conftest.py`), num inquilino temporário: o limite de um pedido por tipo por hora não colide com
  rodadas repetidas da suíte.
- `docs/openapi.json` ganha 8 rotas (`/api/relatorios*`, `/api/atividade`); casos cruzados e eventos declarados.
