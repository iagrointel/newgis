# Identidade e numeração de ativos da rede de utilidades (item L4-28-identificadores-e-numeracao)

Status: aceita. Turno 4, 06/09/2026.

## Contexto

Um ativo de rede de utilidades precisa de três identidades ao mesmo tempo, com garantias diferentes:

1. uma **identidade interna estável** que a feição, o traçado e as regras referenciam e que nunca muda,
   nem quando o cliente troca o código que enxerga;
2. um **código externo** (o código do cliente — ex.: `COD_ID` da BDGD) que não pode se repetir dentro da
   mesma rede, senão a carga de um sistema legado mistura dois ativos num só;
3. uma **numeração automática por tipo de ativo** que funcione também para quem cria ativo em campo sem
   conexão: a equipe sai com um bloco de números reservado e consome offline, sem colidir com quem está
   criando conectado nem com outra equipe. É o conceito que a Esri chama *unit identifiers* no
   UtilityNetworkServer 12.1 (fonte do item).

A hipótese do item só se sustenta se as três garantias viverem **no banco**, não só na aplicação: dois
clientes concorrentes passam pelo mesmo código de rota, e a refutação exigida é exatamente essa corrida.

## Decisão

Quatro tabelas novas (`db/migracoes/20260906T2121_rede_identificadores.sql`), todas com FK composta por
inquilino (ADR 20260906T1839) e RLS no padrão das demais `plat.rede_*`:

- **`plat.rede_numeracao`** — uma linha por tipo de ativo, com `proximo` = primeiro número livre. A
  alocação de um bloco de N números é uma só instrução
  `INSERT ... ON CONFLICT (tenant_id, tipo_id) DO UPDATE SET proximo = proximo + N RETURNING proximo - N`,
  que trava a linha do contador até o commit da transação do chamador. Duas alocações concorrentes do
  mesmo tipo recebem blocos disjuntos por construção — não há leitura-modificação-escrita em duas
  instruções para correr. O contador **nunca anda para trás**: reservar faz o contador pular a faixa,
  então a criação conectada nunca recebe um número já entregue a uma faixa, e liberar uma faixa não
  devolve números (número entregue nunca é reutilizado, mesmo nunca tendo virado ativo).
- **`plat.rede_faixa`** — bloco `[inicio, fim]` contíguo, de propriedade de **um usuário**, com
  `consumidos` e `liberada_em`. Prova independente no banco contra sobreposição: restrição de EXCLUSÃO
  `EXCLUDE USING gist (tipo_id WITH =, int8range(inicio, fim, '[]') WITH &&) WHERE (liberada_em IS NULL)`
  — mesmo que a alocação atômica falhasse, o banco recusaria duas faixas abertas sobrepostas no mesmo
  tipo.
- **`plat.rede_ativo`** — a identidade: `global_id` uuid (chave primária, nasce na criação e nunca muda),
  `numero` bigint único por tipo (`ux_rede_ativo_tipo_numero`) e `codigo_externo` texto único por rede
  (índice único parcial `WHERE codigo_externo IS NOT NULL`). A linha não é a feição — a feição vive na
  camada (item L4-01-b) e aponta para cá pelo `global_id`.
- **`plat.rede_ativo_renomeacao`** — cada troca de `codigo_externo` grava uma linha (anterior, novo,
  autor, instante). Renomear é PATCH no código; o `global_id` é intocável pelo contrato da rota.

Regras de consumo da numeração, na aplicação (`app/rede_utilidades/identificadores.py`):

- criação **conectada** (sem `numero` no corpo): o servidor aloca o próximo número do tipo;
- criação **desconectada sincronizada** (com `numero`): o número tem de estar dentro de uma faixa aberta
  do **próprio usuário** (travada `FOR UPDATE`, `consumidos` incrementado na mesma transação); fora de
  faixa própria = 422 `numero_fora_de_faixa`; número já usado = 409 (o índice único por tipo é a última
  linha de defesa);
- `codigo_externo` duplicado na rede = 409 `codigo_externo_existente` (o nome da restrição do índice
  decide a mensagem, não a ordem do SQL);
- renomear para o mesmo código é idempotente (200, sem linha de histórico); renomear para código em uso =
  409; o código liberado por uma renomeação volta a poder ser usado.

Fachada Esri (`app/rede_utilidades/rotas_esri_un.py`): `GET`/`POST`
`/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers` com `query` e `reserve`, GET e POST com
corpo `application/x-www-form-urlencoded` (o protocolo dela), `?token=` além do cabeçalho normal, e o nome
do serviço resolvendo uuid **ou nome exato** da rede — o mesmo desenho do GeocodeServer compatível. O
"unit-identifiable object" dela mapeia para o nosso tipo de ativo (`plat.rede_tipo`); o inteiro dela, para
o nosso `numero`. Divergências declaradas no cabeçalho do módulo e em `docs/PARIDADE.md`: erro no contrato
da plataforma (não no envelope `{"success": false}`); `gdbVersion`/`sessionID`/`moment` aceitos e
ignorados (não há versionamento de geodatabase); `reset`/`resize` não existem (o contador nunca anda para
trás e o tamanho de uma faixa não muda — libera-se e reserva-se outra); a resposta do `reserve` usa a
forma do `query`, não o envelope `serviceEdits`, que é interno da tabela de UN deles. A extensão `count`
(sem `firstUnit`/`lastUnit`) aloca o próximo bloco livre — a forma documentada para campo.

## Alternativas consideradas

- **Sequência do Postgres por tipo**: descartada. Sequência não pode ser criada por tabela-filha dinâmica
  sem DDL por inquilino, e `nextval` não devolve o "primeiro do bloco" com a mesma atomicidade de uma
  linha travada. A linha-contador em `rede_numeracao` dá os dois com SQL puro.
- **Reserva por intervalo livre (reaproveitar lacunas)**: descartada. Complexidade de coalescência sem
  ganho para o caso de uso (campo consome para a frente) e quebra a garantia "número entregue nunca é
  reutilizado", que é o que torna o histórico auditável. As lacunas ficam expostas como `gaps` no `query`
  da fachada, como na Esri.
- **Faixa por equipe/dispositivo em vez de por usuário**: descartada neste item. A chave do dono é o
  usuário da sessão porque é a identidade que a autenticação prova; equipe é agrupamento de apresentação
  que pode vir depois sem mudar a tabela (o dono continua existindo).

## Consequências

- Quem cria em campo reserva antes (`POST /api/rede/{id}/faixas` ou o `reserve` da fachada), vai offline,
  e sincroniza depois com `numero` informado. Colisão é impossível por construção, e a refutação do item
  (10 reservas concorrentes em duas sessões) está em teste permanente.
- O teto de uma reserva é 100 mil números (`QUANTIDADE_MAX_FAIXA`): uma turma inteira de campo não passa
  disso, e o teto impede um pedido malicioso de empurrar o contador para o infinito.
- O `codigo_externo` é opcional: ativo criado pela numeração pura (sem importação de código legado) vive
  só com `numero` e `global_id`.
- `docs/openapi.json` ganhou as rotas; `docs/PARIDADE.md` ganhou a seção da fachada.
