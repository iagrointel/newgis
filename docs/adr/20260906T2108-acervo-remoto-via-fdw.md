# ADR 20260906T2108 — camadas do acervo em OUTRO servidor da casa, via postgres_fdw só-leitura (L6-01-j)

Estado: aceito (turno T4, setembro de 2026). Base: `laco/estado.json` item `L6-01-j-multi-servidor`, filho
de `L6-01-acervo-casa`. Migração `db/migracoes/20260906T2108_acervo_remoto_fdw.sql`. Script
`scripts/acervo_fdw_sync.py`.

## Contexto

`plat.acervo_camada` (item L6-01-a-registro, migração 027) registra tabelas canônicas com geometria que
vivem NESTE servidor Postgres. A hipótese do item-pai já media que 412 tabelas do acervo da casa vivem em
mais de uma máquina (`acervo.objeto`, campo `servidor`: vultr/hetzner/gpu, 06/09/2026), e muitas só existem
no segundo ou terceiro servidor — nunca chegam a `acervo_camada` porque `acervo_sync.py` só enxerga a
própria instância local. Sem este item, a ficha do acervo (`GET /api/acervo/{fonte_id}`) mente por omissão
sobre uma fonte cujas tabelas moram noutra máquina: parece que a fonte não tem camada nenhuma.

A regra D21 (disco a 98% nos dois servidores principais) proíbe copiar dado sem decisão explícita — a
opção "replicar tudo para cá" está fora de cogitação. `postgres_fdw` já vem instalado na base da casa
(`CREATE EXTENSION IF NOT EXISTS postgres_fdw`, verificado 06/09/2026) e resolve exatamente o caso: lê a
tabela remota SEM copiar uma linha, com credencial de leitura própria.

## Decisão

1. **Espelho de definição, nunca de dado.** `IMPORT FOREIGN SCHEMA ... LIMIT TO (...)` cria foreign tables
   num schema-espelho local (`<schema_plat>_rm_<servidor>_<schema_remoto>`); nenhuma linha é copiada. O
   `COUNT(*)` que grava `linhas_exatas` atravessa a rede a cada rodada — é sempre uma leitura ao vivo do
   remoto, nunca um cache que pode ficar velho sem ninguém perceber.
2. **`plat.acervo_servidor`** registra host/porta/banco/usuário de leitura + `segredo_ref` (nome do
   arquivo de senha no cofre da instalação — a senha NUNCA fica em tabela). Global, sem tenant, mesmo
   padrão de `plat.acervo_camada`. Só leitura para a API; escrita é do operador/script.
3. **`plat.acervo_servidor_tabela`** complementa `acervo.objeto` (a fonte primária e compartilhada de
   candidatas) com declarações manuais — é também como a suíte de teste monta a fixture sem escrever no
   registro global do acervo.
4. **`plat.acervo_camada` ganha `modo_acesso`** (`local`/`fdw`/`indisponivel`), `fdw_tabela`, `aviso`,
   `fdw_verificado_em`, `fdw_latencia_ms`. `local` continua sendo a canônica: uma candidata remota que
   colide com uma linha `local` já registrada é tratada como cópia e pulada (nunca sobrescreve o local).
5. **Falha de rede vira aviso, nunca "0 feições".** Quando o `IMPORT`, o `COUNT(*)` ou a conexão caem, a
   camada muda para `modo_acesso = 'indisponivel'` com `aviso` explicando — `linhas_exatas` conserva a
   ÚLTIMA contagem boa (a coluna nunca é zerada por uma falha de rede). É a refutação do item: "adversário
   derruba a rede da fixture e confere que a camada não aparece como '0 feições'" — provado em
   `tests/api/test_acervo_fdw.py::test_falha_de_rede_vira_aviso_nao_camada_vazia`.
6. **`connect_timeout` sempre gravado no `SERVER`** (10 s) para que um servidor morto falhe em segundos,
   nunca pendure a rodada; prazo duro de 270 s por rodada inteira (mesmo padrão de `acervo_sync.py`).
7. **A ficha mostra a origem em texto literal.** `GET /api/acervo/{fonte_id}` ganhou o campo `camadas`
   (`app/acervo/modelos.py::AcervoCamadaResumo`), com `origem` = `"local"` | `"servidor remoto (<nome>)"` |
   `"servidor remoto indisponível (<nome>)"` — nunca escondido atrás de um código que só quem já conhece o
   esquema do banco entende.
8. **Poda só com o servidor vivo na rodada** (nunca às cegas): se o servidor respondeu, o script remove do
   registro e do espelho o que deixou de ser candidata; se não respondeu, nada é removido — a ausência de
   resposta não pode ser lida como "a tabela sumiu". `scripts/acervo_sync.py` (script IRMÃO, que cuida das
   tabelas LOCAIS) também foi ajustado para nunca podar linha de `modo_acesso` remoto — a poda de cada
   script é escopada ao seu próprio `servidor` (achado ao rodar a suíte deste item: sem o filtro, uma
   rodada de `acervo_sync.py` no servidor local apagava as linhas `fdw`/`indisponivel` de OUTRO servidor).

## Dois defeitos corrigidos no turno T4 (achados pela suíte, não pela leitura)

- `SQL_INSERIR_INDISPONIVEL` usava `'{}'` literal (array vazio) dentro de uma string passada a
  `str.format()` — `.format()` lê qualquer `{}` como marcador posicional de substituição e estourava `IndexError`
  assim que a primeira falha de rede acontecia. Corrigido para `'{{}}'` (escape do literal).
- A query de poda do espelho usava `pg_foreign_table.ftgrelid`, coluna que não existe (o nome real é
  `ftrelid`) — toda rodada com pelo menos 1 servidor vivo quebrava na hora de podar. Sem essa correção,
  `test_tres_tabelas_remotas_lidas_por_fdw_com_tempo_medido` falhava com `UndefinedColumn`.
- `IMPORT FOREIGN SCHEMA` não é idempotente por si só: uma segunda rodada contra o MESMO servidor batia em
  "relation already exists" no espelho e a rodada inteira virava "servidor indisponível" — o pior tipo de
  falso negativo (rede boa relatada como rede morta). Corrigido com `DROP FOREIGN TABLE IF EXISTS` de cada
  tabela do grupo antes do `IMPORT` — reimportar a cada rodada também é o que mantém o espelho fiel a uma
  mudança de coluna na tabela remota, em vez de herdar a definição congelada da primeira vez.

## Testado

`tests/api/test_acervo_fdw.py`: fixture em LOOPBACK (postgres_fdw não distingue loopback de máquina de
verdade — o mecanismo é idêntico) com 3 tabelas geométricas reais e um servidor real declarado em
`acervo_servidor`. As 3 cláusulas do portão do item, cada uma com prova por comando:
1. 3 tabelas lidas por FDW com `fdw_latencia_ms` medido e `linhas_exatas` batendo com o `COUNT(*)` real.
2. `GET /api/acervo/{fonte_id}` mostra `"origem": "servidor remoto (<nome>)"` nas 3 camadas.
3. Porta do servidor trocada para uma que ninguém escuta (conexão recusada, sem esperar timeout) → as 3
   camadas viram `indisponivel` com `aviso`, e `linhas_exatas` continua com o valor da última leitura boa.

## O que fica de fora (fronteira honesta)

- Não há UI: a ficha devolve o campo `camadas`, mas nenhuma tela consome `origem`/`aviso` ainda (a tela do
  catálogo é outro item, L6-01-b, ainda não construído para camadas remotas).
- O cofre de segredos real (`/etc/plat/segredos`) não foi testado neste turno — só o mecanismo de leitura
  (`_senha_do_cofre`, com o mesmo teste de fronteira contra `..`/`/` embutido). Provisionar o arquivo real
  em produção (host/porta/usuário dos outros dois servidores da casa) é passo humano, fora do escopo do
  código: a migração e o script já aceitam qualquer servidor declarado, mas nenhum servidor de PRODUÇÃO
  foi declarado por este turno.
- `acervo.objeto` (origem "registro_acervo" das candidatas) não foi exercitado neste turno — só a origem
  "manual" (`acervo_servidor_tabela`), que é também o caminho que a suíte usa para não escrever no
  registro global. A união das duas origens está no código (`_candidatas`) mas sem teste dedicado.
