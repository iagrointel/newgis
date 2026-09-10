# ADR — recurso partilhado precisa de dimensão de inquilino (ou de instalação)

Data: 06/09/2026 (turno 3). Ramo `wt/partilha`. Nome por carimbo de tempo (ADR 0014): dois ADRs nasceram
`0015`/`0016` no mesmo turno em ramos ainda não juntados.

## Contexto

Cinco adversários independentes (laudos `laco/handoffs/T3/ataque-g2|g3|g4|g6-ADVERSARIO.md`) atacaram
cinco grupos diferentes da plataforma e escreveram o mesmo veredito: o que é protegido POR LINHA (RLS,
filtro de dono, contexto de inquilino no `SET LOCAL`) aguentou o ataque inteiro. O que é um RECURSO
PARTILHADO — algo que existe uma vez só por banco, por processo ou pela máquina — não tinha dimensão de
inquilino nenhuma, e às vezes nem de INSTALAÇÃO (produção × homologação × as N trilhas do laço, todas no
mesmo Postgres `iagro_sat`).

No grupo G3 (fila de trabalhos e ingestão), sete pontos caíram assim:

1. a chave do trinco de um trabalho (`plat.job.chave`) sem `tenant_id` — inquilino B congelado pela chave
   escolhida por A;
2. a fila (`plat.job_pegar`) ordenada só por prioridade/data, global — quem chegou primeiro foi servido
   em 21º porque outro inquilino criou 20 trabalhos de prioridade mais alta depois;
3. a ceifa de trabalho morto (`plat.job_ceifar`) só existia dentro do laço do worker — sem NENHUM
   executor vivo, ninguém ceifava;
4. a mesma ceifa devolvia sem consumir tentativa (`p_conta_tentativa = false`) — 3 SIGKILL seguidos no
   mesmo trabalho terminavam `concluído` em vez de `falhou`;
5. o contador de cota (`plat.tenant.uso_bytes`) só subia — soma no código de carga, nenhum caminho de
   devolução;
6. o nome do schema de dado do inquilino (`'d_' || slug`) sem prefixo de instalação — produção,
   homologação e as trilhas do laço escreviam todas no MESMO `d_demo`;
7. o orçamento de conexões SSE guardado em memória de PROCESSO — o teto publicado valia N vezes quando a
   unidade sobe `uvicorn --workers N`, e não havia teto nenhum por inquilino.

Medindo o conserto do ponto 1 e 2 apareceu um OITAVO ponto, fora do laudo original: o advisory lock
"1 pesado por vez" (`app/jobs/worker.py::LOCK_PESADO`) é global ao BANCO inteiro (não ao schema), e tinha
um defeito de disciplina próprio que deixava um worker ocioso segurando o lock para sempre.

## Decisão

Todo recurso que não é isolado POR LINHA (RLS) — uma chave de trinco, um contador em memória de processo,
um nome de objeto derivado só do apelido do inquilino, uma fila global, um orçamento, um lock de sessão —
tem de carregar explicitamente:

- **dimensão de INQUILINO**, quando o recurso é do banco de uma instalação (a chave do trinco, a fila, o
  contador de cota, o teto de conexões por inquilino);
- **dimensão de INSTALAÇÃO**, quando o recurso é da máquina/processo e pode ser MULTIPLICADO por
  produção + homologação + trilha (o nome do schema de dado, o advisory lock de "1 pesado por vez"), e
  ainda assim **dimensão de trabalho em curso** quando o mesmo processo tem mais de um "slot" (o
  `pesado_ok` de `_pegar()` não pode pedir um segundo trabalho pesado enquanto já tem um em voo — advisory
  lock é reentrante na mesma sessão, então "eu já seguro o lock" não implica "posso pedir mais um").

Onde o teto é fisicamente de PROCESSO (contador em memória, sem canal entre processos), o teto publicado é
da INSTALAÇÃO e cada processo aplica `teto_instalacao // PLAT_API_PROCESSOS` (ou o equivalente) — nunca o
valor bruto. `app/jobs/eventos.py::cota_por_processo` é o padrão de referência.

## Trava de classe

`tests/unit/test_recurso_partilhado_por_inquilino.py` varre a FONTE (migrações e módulos, sem banco) e
reprova se qualquer um dos pontos perder a dimensão de inquilino/instalação. `tests/unit/
test_worker_lock_pesado.py` cobre as três metades do achado do lock de pesado direto contra a classe
`Worker`, sem banco nem processo. Quem acrescentar um recurso partilhado novo (mais um contador em
memória, mais um nome de objeto derivado, mais uma fila, mais um orçamento, mais um lock de sessão)
acrescenta uma linha em `PONTOS` no primeiro arquivo — a trava é viva, não uma lista fechada.

## Consequência aceita

O advisório de "1 pesado por vez" ficou mais conservador: um worker com `PLAT_WORKER_PROCESSOS > 1` que já
tem um trabalho pesado em curso não tenta mais um segundo (mesmo que o lock, por ser reentrante na mesma
sessão, deixasse). Isso é exatamente o que "1 pesado por vez" sempre quis dizer — só ficou visível ao medir
o conserto do namespace com um worker de dois processos de verdade.

## Referências

`laco/handoffs/T3/ataque-g3-ADVERSARIO.md` (laudo atacado); `laco/handoffs/T3/PARTILHA-CONSERTO.md`
(conserto, prova por cláusula); `db/migracoes/20260906T1615a3f_recurso_partilhado_por_inquilino.sql`;
commit `9eb88b917fbcedaf7effef939e0909b635193862` de `wt/stac` (namespace do lock de pesado, cherry-pick).
