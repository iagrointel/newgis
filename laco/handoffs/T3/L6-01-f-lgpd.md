# Handoff — item L6-01-f-lgpd (arquiteto + backend, passagem única)

**Objetivo (do pedido desta passagem, mais estreito que a hipótese completa do backlog).** Gate de
LGPD para camadas do acervo que possam ter dado pessoal identificável: conferir se existe campo de
classificação em `acervo.fonte`; se não, somar coluna/flag curada à mão (nunca automática) e
bloquear `POST /api/acervo/{fonte_id}/adicionar` para fonte marcada sem confirmação explícita.

## O que fiz

1. **Conferido**: `\d acervo.fonte` não tem nenhum campo de classificação (`cliente_ve`, o mais
   próximo, é sobre visibilidade comercial, não LGPD). `acervo.*` só é escrito pelos scripts da
   casa — decisão já registrada três vezes no ADR 0012 — então a classificação NÃO foi para
   `acervo.fonte`; foi para `plat.acervo_lgpd` (migração 041), tabela própria da plataforma,
   `fonte_id` PK com FK de leitura, `risco_pii boolean NOT NULL`, `motivo`/`decidido_por NOT NULL`
   (`CHECK` — nunca marcado ou limpo sem razão escrita), sem GRANT de escrita a `plat_app`.

2. **Curadoria por evidência, não suposição**: varri `information_schema.columns` das 219 tabelas
   canônicas ligadas às 68 fontes licenciadas (`acervo.objeto`, `canonico`) contra um padrão amplo
   de nome de coluna (cpf/cnpj/nome/email/telefone/endereço/titular/proprietário/...). 114 colunas
   bateram; li cada uma (`\d` da tabela + contagem de preenchimento quando havia dúvida real).
   Quase todas eram nome de LUGAR, CNPJ de FUNDO (pessoa jurídica) ou endereço de imóvel já público
   por natureza (leilão/edital). Um caso quase enganou: `cbre.cad_gu_face_pgv.telefone`/
   `telefone_p` — são flags de infraestrutura de rua (a rua tem rede telefônica?), não contato de
   pessoa (`id_responsavel` preenchido em 1 de 25.436 linhas). **Único achado real: `onr`**
   (matrículas) — a tabela ingerida não guarda nome do titular, mas `url_mat` aponta para o
   documento de matrícula no cartório, que guarda.

3. **Gate na rota**: `POST /api/acervo/{fonte_id}/adicionar` agora aceita corpo opcional
   `{"confirma_risco_pii": bool}`; fonte com `risco_pii = true` em `plat.acervo_lgpd` e sem
   confirmação recusa com **409 `confirmacao_pii_exigida`** antes de tocar `plat.item`. A recusa
   é registrada como evento (`acervo/adicionar_recusado_pii`, novo em `plat.evento_tipo`) — **em
   transação PRÓPRIA**, separada do bloco que levanta o erro (achado ao testar: registrar e
   levantar no mesmo `with db.db()` faz o rollback apagar o próprio evento da auditoria; copiei o
   padrão de `app/auth/rotas_login.py::_falhou`/`_bloqueado`, que já resolve exatamente isso).

## Evidência (comando + saída literal)

```
$ sudo -u postgres psql -d iagro_sat -c "SELECT fonte_id, risco_pii, decidido_por FROM plat.acervo_lgpd;"
 fonte_id | risco_pii |               decidido_por
----------+-----------+------------------------------------------
 onr      | t         | arquiteto+backend T3 (item L6-01-f-lgpd)
```

```
$ sudo -u postgres psql -d iagro_sat -c "\dp plat.acervo_lgpd"
 plat   | acervo_lgpd | table | postgres=arwdDxt/postgres+
        |             |       | plat_app=r/postgres          -- só leitura pela API
```

Suíte (sob `flock laco/.pytest.lock`), testes do gate em `tests/api/test_acervo.py`:
```
test_ficha_de_fonte_marcada_mostra_risco_pii_e_motivo ................ PASSED
test_fonte_sem_curadoria_lgpd_nao_e_marcada_por_padrao ................ PASSED
test_adicionar_fonte_marcada_risco_pii_sem_confirmacao_recusa ......... PASSED
test_adicionar_fonte_marcada_risco_pii_com_confirmacao_explicita_confirmacao_falsa_ainda_recusa . PASSED
test_adicionar_fonte_marcada_risco_pii_com_confirmacao_cria_item ...... PASSED
test_adicionar_fonte_sem_risco_pii_nao_exige_confirmacao (regressão) .. PASSED
```
(14 testes no arquivo inteiro, 0 falhas — rodada isolada `pytest tests/api/test_acervo.py -q`
→ `..............` [100%]; uma rodada anterior de `pytest tests/api -q` mostrou uma onda grande de
`ERROR` em rotas TOTALMENTE alheias — login, sessão, papéis — reproduzida como falsa: re-rodei
`test_acervo.py` + `test_eu.py::test_objeto_eu_sob_token` isolados logo depois e os dois passaram;
é ruído do banco compartilhado sob 4+ trilhas concorrentes migrando/reiniciando ao mesmo tempo,
não uma regressão desta mudança).

## Riscos

`plat.acervo_lgpd` sem GRANT de escrita para `plat_app` — só migração/acesso direto ao banco marca
ou desmarca uma fonte; isto é deliberado (curadoria manual, nunca automática, por pedido do item),
mas significa que uma fonte licenciada NOVA com dado pessoal só fica protegida se alguém rodar essa
curadoria de novo. Não há cron/gatilho hoje que force essa revisão periódica.

## Pendências (por que o item ficou `parcial`, não `entregue`)

O portão COMPLETO do backlog (`estado.json`) é maior que o pedido desta passagem: "teste
automatizado percorre TODAS as views expostas e falha se existir coluna cujo nome case com a lista
negra ou cujo conteúdo case com regex de CPF/CNPJ em amostra de 1.000 linhas". O que entreguei
cobre só o fluxo de "adicionar fonte" pedido explicitamente. Fica de fora, registrado como
pendência real (não fingido como feito):

- Varredura AUTOMÁTICA de toda view exposta (incluindo `plat.acervo_camada`, que já tem
  `colunas_bloqueadas` por NOME desde o item L6-01-a-registro, nunca por conteúdo).
- Regex de CPF/CNPJ sobre amostra de 1.000 linhas de conteúdo real.
- `make check` ainda não tem esse teste (o que existe é o teste do GATE específico, não a
  varredura genérica).
- Revisão periódica de `plat.acervo_lgpd` quando fontes novas ganharem licença.
- **Sem adversário independente do turno** — nenhum agente separado tentou expor uma fonte
  marcada pela tela (não há tela) ou achar coluna de identidade nas views expostas.

## Para o próximo papel

Quem pegar a varredura automática completa: a lição desta passagem é que uma regex genérica de
NOME sozinha produz mais ruído que sinal (114 candidatas, 1 achado real) — qualquer versão
automática vai precisar de uma segunda etapa (conteúdo real, amostra) ou vai bloquear
`cad_gu_face_pgv` e uma dúzia de tabelas de nome de lugar por engano, exatamente o erro que a
leitura manual evitou aqui.

## Resumo (6 linhas)

`acervo.fonte` não tinha classificação de PII; criei `plat.acervo_lgpd` (migração 041), curada à
mão, sem escrita pela API. Varri 219 tabelas das 68 fontes licenciadas por nome de coluna suspeito
e li cada achado; só `onr` (matrículas, via `url_mat` para documento de cartório) ficou marcada.
`POST /adicionar` agora recusa com 409 sem `confirma_risco_pii`, registrando a recusa como evento
em transação própria (senão o rollback apaga a auditoria). Estado: `parcial` — cobre o gate pedido,
não a varredura automática de toda view exposta que o backlog completo do item ainda pede.
