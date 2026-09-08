# Entrada de eventos em tempo real (item L2-14-a-ingestao-de-fluxos)

Data: 2026-09-08. Estado: aceito nesta passagem. Contexto: decisão C14 de `laco/decomposicao/L2_CONCEITO.md`
(processo `plat-fluxo` na porta 8155, tabela particionada por mês, escrita em lote); paridade com os tipos de
feed do ArcGIS Velocity e do GeoEvent Server, escrita em `docs/PARIDADE.md`.

## 1. COPY não escreve em tabela com segurança de linha — o lote virou um INSERT com `unnest`

A decisão C14 dizia "escrita em lote (COPY, 1/s)". Medido nesta trilha, com a role `plat_app`:

    psycopg2.errors.FeatureNotSupported: COPY FROM not supported with row-level security
    HINT:  Use INSERT statements instead.

O isolamento entre inquilinos é cláusula do portão e não se abre mão dele; escrever como uma role sem
segurança de linha para poder usar COPY seria trocar o isolamento por velocidade. O substituto é UM
`INSERT ... SELECT ... FROM unnest(<um array por coluna>)` por lote: uma ida ao servidor, uma análise de
comando, e a política de linha aplicada pelo Postgres.

Medido antes de escolher, na mesma máquina e sob carga 9: **10.000 linhas em 160 ms = 62.419 linhas/s**, seis
vezes o alvo de 10 mil eventos/s do portão. Medido depois, contra o processo inteiro e por 60 s: 600.000
eventos, perda zero, atraso mediano 30,9 ms (`tests/medidas/L2-14-a-ingestao-de-fluxos.json`).

Consequência para quem vier depois: **nenhuma tabela deste produto ganha carga por COPY enquanto tiver RLS**.
Quem precisar de COPY de verdade (ingestão de arquivo grande, item L0-04) já escreve em schema de dado por
inquilino, sem política de linha, e é lá que ele continua valendo.

## 2. Esquema de destino é GERADO e declarado; não é DDL por fonte

"Esquema de destino gerado" podia significar uma tabela com colunas tipadas por fonte. Recusado: cada fonte
exigiria `CREATE TABLE` + política de linha + partição + índices criados em tempo de execução a partir de
dado do inquilino, com uma role que teria de poder fazer DDL. É superfície de ataque nova para resolver um
problema de tipagem.

O que se faz: `mapeamento` → `esquema_destino` (nome, tipo e origem por campo), guardado na fonte e devolvido
pela API; os valores JÁ CONVERTIDOS ao tipo declarado vão em `atributos jsonb` da tabela particionada. Quem
consome (camada, painel, API) lê o esquema declarado em vez de adivinhar o tipo. O custo é uma consulta por
atributo mais cara que uma coluna nativa; quando isso pesar, a saída é uma vista materializada por fonte, que
não muda o modelo de escrita. Está declarado como `parcial` na paridade.

## 3. O receptor é outro processo, com outra aplicação ASGI

O evento não passa pelo middleware da API. Uma linha em `plat.log_acesso` por evento, a 10 mil eventos/s, é
mais escrita de registro do que de dado. O receptor (`app/fluxo/receptor.py`) é uma aplicação Starlette
própria com três rotas, e a API da plataforma guarda só a GESTÃO da fonte (`/api/fluxos`).

O que NÃO muda por isso: a autenticação. O receptor verifica o token de serviço pela MESMA função de banco
`plat.auth_token` que a API usa (`app/fluxo/autenticacao.py`) — sem segunda implementação de token, sem chave
própria, sem tabela paralela. Escopo novo `fluxo:escrever` (e `fluxo:ler` para a gestão), aceitando o sufixo
`:<uuid>` de uma fonte: é assim que se entrega um token a um veículo sem lhe dar as outras fontes da casa.

Consequência: o registro de auditoria do fluxo é a MÉTRICA (contadores por fonte, por motivo de descarte),
não uma linha por evento. Está escrito em `tests/api/eventos_esperados.py`, ao lado das rotas de gestão.

## 4. O processo atende todos os inquilinos, mas continua debaixo da segurança de linha

`plat_app` sem contexto de inquilino não enxerga nem `plat.tenant` nem `plat.fluxo_fonte`. Para descobrir
QUAIS inquilinos têm fonte existe `plat.fluxo_inquilinos()`, definidora e restrita a `plat_app`, que devolve
só identificadores — nenhum nome, nenhuma configuração, nenhuma credencial. As fontes de cada inquilino são
lidas em seguida com o contexto daquele inquilino, sob a política normal. A alternativa (conectar com uma
role sem RLS, como o worker faz para estado de job) daria ao processo de ingestão autoridade sobre o dado de
todos os inquilinos, que é exatamente o que o portão deste item proíbe.

## 5. Cliente MQTT escrito com a biblioteca padrão

A casa não tem `paho-mqtt`, o disco está a 96 % e a corrida proíbe dependência nova. O subconjunto que uma
fonte ASSINANTE usa cabe em um arquivo: CONNECT, CONNACK, SUBSCRIBE, SUBACK, PUBLISH (QoS 0 e 1), PUBACK,
PINGREQ/PINGRESP, DISCONNECT. Está exercido contra um servidor que fala o protocolo no fio
(`tests/apoio/broker_mqtt.py`), não contra ele mesmo, e os pontos de virada da tabela de "Remaining Length"
da seção 2.2.3 da especificação são teste próprio.

Fora, declarado: QoS 2, sessão persistente, retenção, última vontade, MQTT 5. Broker PRÓPRIO (mosquitto nesta
máquina) é a decisão **D31**, do dono, ainda aberta — enquanto ela não vier, a fonte `mqtt` é sempre cliente
assinante de um broker de terceiro, com TLS verificado.

## 6. Pausa guarda, não descarta; e o buffer tem teto declarado

Fonte pausada mantém a conexão do conector (desconectar perderia o que chega) e o evento vai para um buffer
em memória com teto declarado: `limite_eventos_s × FLUXO_BUFFER_PAUSA_S` (30 s), nunca acima de
`FLUXO_BUFFER_PAUSA_MAX`. Retomada, o buffer é drenado na ordem de chegada. Cheio, o evento novo é descartado
e contado como `buffer_de_pausa_cheio` — pausa não é armazenamento.

O buffer vive na memória do processo: **uma parada do `plat-fluxo` com fonte pausada perde o buffer**. Está
declarado no manual. Persistir o buffer significaria gravar no banco o que a pausa existe para não gravar.

## 7. O teto por segundo é por processo, e isso é declarado

O balde de fichas é do processo. Com N processos `plat-fluxo`, o teto efetivo do inquilino é N vezes
`limite_eventos_s`. Um teto exato entre processos exigiria um contador central consultado por evento, que
custa mais que o próprio evento. Hoje o serviço é um processo só; o dia em que forem dois, o número no manual
tem de mudar junto.

## 8. Ordem das etapas: teto antes do mapeamento

Numa rajada acima do teto, converter o evento é justamente o trabalho que não se quer gastar. O preço é que
um evento descartado por teto não é conferido, então a contagem de inválidos vale só sobre o que passou pelo
teto. Está escrito em `app/fluxo/entrada.py` e no manual.

## 9. Atraso é `bigint`

O atraso é o intervalo entre o tempo do evento e o recebimento. Uma carga histórica legítima tem meses de
atraso, o que estoura `int4` em 24 dias. Achado pelo teste do receptor, com um evento de janeiro.
