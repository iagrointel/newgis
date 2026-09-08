# Atualização viva de painel e mapa: um só mecanismo de empurrão

Data: setembro de 2026. Item: L2-06-d-atualizacao-viva-sse. Estado: aceita.

## Contexto

O painel (L2-06-a) já sabia refazer a consulta por intervalo: cada fonte declara `atualizacao_s` e a tela
repete o pedido de tantos em tantos segundos. Isso resolve mal os dois extremos. Com intervalo curto, a
tela consulta o banco o tempo todo mesmo quando nada mudou. Com intervalo longo, quem edita um dado fica
olhando um número velho e não sabe disso.

A plataforma já tinha um caminho de empurrão pronto e em uso: o progresso de tarefa (`app/jobs/eventos.py`,
ADR 0003 seção 5) usa gatilho no Postgres, `pg_notify`, um `LISTEN` por processo da aplicação e
Server-Sent Events até o navegador.

## Decisão

Estender esse mesmo caminho às camadas, em vez de criar um segundo mecanismo (WebSocket, fila externa,
sondagem no servidor).

1. **Gatilho por comando, não por linha.** `plat.camada_notificar()` roda `AFTER INSERT OR UPDATE OR DELETE
   ... FOR EACH STATEMENT`. Uma edição em lote que toca dez mil linhas gera UM evento. Por linha, a mesma
   edição geraria dez mil notificações e o navegador refaria a consulta dez mil vezes.
2. **Contador por camada e registro curto de eventos.** `plat.camada_versao` guarda a versão corrente;
   `plat.camada_evento` guarda os eventos dos últimos quinze minutos, e é essa janela que o cabeçalho
   `Last-Event-ID` recupera quando a conexão cai e volta. Não é histórico de edição: o histórico é o
   versionamento da camada. Quem some por mais que a janela recarrega a tela.
3. **Instalação do gatilho sob demanda.** `plat.camada_observar(uuid)` cria o gatilho na tabela física da
   camada e não faz DDL nenhuma quando ele já existe. A rota do fluxo chama essa função ao abrir a conexão:
   assinar uma camada é o que a coloca sob observação. Assim nenhuma camada carrega gatilho que ninguém usa,
   e nenhuma rota de ingestão precisa lembrar de instalar nada.
4. **Uma conexão por tela, não por elemento.** `GET /api/eventos/camadas?camadas=a,b` assina a lista inteira.
   O navegador agrupa os eventos numa janela de um segundo e refaz uma consulta por FONTE afetada.
5. **Intervalo como reserva, não como padrão.** Com o fluxo de pé, o intervalo de cada fonte fica desligado.
   Ele volta quando o fluxo se declara indisponível — proxy sem suporte a conexão longa, ou
   `PLAT_SSE_LIGADO=false`, que faz a rota responder 503 na hora. O cabeçalho do painel diz qual dos dois
   caminhos está em uso, para ninguém achar que a tela está viva quando ela está apenas repetindo.

## Consequências

O painel reflete a edição em menos de um segundo (medido: 0,0005 s do COMMIT ao quadro no consumidor) sem
recarregar a página, e o custo de "estar atualizado" passa a ser proporcional ao que muda, não ao tempo que
a tela fica aberta.

Em troca, cada aba aberta prende uma conexão. Por isso há dois tetos, por inquilino e por usuário, contados
na memória de cada processo da aplicação (`app/limites.py`), e a conexão fecha sozinha em trinta minutos —
o navegador reabre e recupera o que passou.

O que este ADR NÃO decide: o mapa ainda não assina camadas (o painel assina). O caminho é o mesmo módulo
`web/js/vivo/assinatura.js`, e a rota já aceita a lista de camadas que o mapa precisaria.
