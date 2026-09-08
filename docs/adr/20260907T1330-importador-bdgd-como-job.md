# ADR 20260907T1330 — Importador BDGD como job: contrato antes, contagem depois, COMP pela razão geodésica

Item L4-01-c-importador-bdgd. Turno 4, setembro de 2026. Estado: aceita.

## Contexto

O item irmão L4-01-modelo-rede deixou o importador BDGD (`app/rede_utilidades/bdgd.py`) funcionando
contra um recorte de um alimentador, com duas pendências medidas e registradas: a cooperativa de
teste inteira (cerca de 127 mil feições nas nove camadas do modelo) passava de 13 minutos sob carga
e foi abortada, e a associação de cada dispositivo com a junção era uma consulta por linha. O
portão deste item exige a distribuidora inteira importada por job com progresso, contagem igual ao
arquivo camada a camada, quilometragem de média tensão igual à soma do COMP convertido, relatório de
contrato de dado com pelo menos 30 expectativas, e os três órfãos contados e listados.

## Decisões

1. **Associação de dispositivo em lote.** `_gravar_dispositivos` deixa de fazer duas consultas por
   dispositivo (subrede de nível 3 e associação) e passa a fazer um `execute_values` para cada uma,
   no mesmo padrão que `_gravar_consumidores` já usava. A régua continua sendo a do gatilho
   `rede_associacao_validar` (existe aresta incidente na junção com regra de conectividade para o
   tipo), avaliada em conjunto por `EXISTS` sobre `VALUES`. Na cooperativa de teste isso tira cerca
   de 17 mil idas ao banco da carga.

2. **`comprimento_m` é o COMP declarado, convertido; o geodésico vai para `atributos`.** A BDGD traz o
   comprimento do trecho no campo COMP sem declarar a unidade. O importador mede a razão
   Σ COMP / Σ comprimento geodésico (pyproj, WGS84) da própria camada: entre 0,5 e 2 é metro (a
   casa mediu 1,024 — flecha e caminho real deixam o ativo mais longo que a reta); entre 0,0005 e
   0,002 é quilômetro (fator 1000); fora disso a unidade é declarada indeterminada, o desvio é
   contado e a aresta fica com o geodésico. A decisão de gravar o COMP convertido em `comprimento_m`
   é o que faz a cláusula "km de MT = Σ COMP ± 0,1 %" ser verdadeira por construção: o comprimento
   do ativo é o que a distribuidora declara, não a reta entre os pontos. A refutação do item troca
   a unidade num arquivo de teste e espera o fator mudar por esta medida, sem configuração.

3. **Contrato de dado antes da carga, avaliado sobre os dataframes.** O YAML da casa
   (`contrato_bdgd.yaml`, cópia fiel de `rs-coop/edp_es/contrato`, a origem não é editada daqui)
   tem 61 expectativas em três severidades. `app/rede_utilidades/contrato.py` avalia as de nível
   camada que cabem numa leitura por camada: 30 têm avaliador; as 17 de nível transformador
   (séries por trafo, fronteira de safra) e as que dependem de safra anterior ou censo ficam como
   `nao_avaliada` com o motivo escrito. Não avaliar é declarado, nunca aproximado. O relatório vai
   inteiro para `plat.rede_importacao.contrato`. Por padrão, expectativa `bloqueia` em falha NÃO
   impede a carga (`seguir_com_bloqueio=True`): a topologia é útil mesmo com dado a corrigir, e a
   decisão de bloquear a entrega à ANEEL é do operador, que lê o relatório.

4. **Órfãos por SQL de conjunto sobre o que foi gravado.** UC sem transformador (UNI_TR_MT sem
   dispositivo carregado), transformador sem alimentador (já contado como desvio na carga) e ponto
   de acoplamento sem trecho (junção sem aresta incidente), cada um com quantidade, exemplos e
   explicação, em `plat.rede_importacao.orfaos`.

5. **Caminho local, nunca download.** O job `rede.importar_bdgd` recebe um caminho e o aceita só
   dentro de `PLAT_BDGD_RAIZ` (configuração nova, opcional; vazia = job desligado). Zip é extraído
   no diretório de trabalho do job, com defesa contra caminho que escapa da pasta. D21 (disco a
   95 %): o pacote da ANEEL não é baixado pelo job; importação "pelo nome da distribuidora" fica
   registrada como pendente de decisão do dono.

6. **Arquivo único (GPKG) além de pasta .gdb.** `inspecionar` e `sha256_gdb` passam a aceitar um
   arquivo de camadas, porque o GDAL lê os dois por camada e a refutação precisa gravar uma cópia
   alterada (o FileGDB não é regravável por pyogrio).

## Consequências

- Progresso do job: 1–9 % contrato, 10–98 % carga (proporcional ao `progresso` do importador),
  100 % ao gravar.
- `memoria_mb=1024` (teto do worker): a maior camada de uma distribuidora média cabe (medido na
  distribuidora de referência, abaixo de 100 mil linhas com geometria). Distribuidora grande (ES, 476 MB) precisa de
  medida própria de RAM antes de subir o teto — refutação do item, pendente de máquina calma.
- Migração `20260907T1330_rede_importacao_contrato.sql`: três colunas jsonb opcionais.
- A medida da cooperativa inteira fica em `tests/medidas/L4-01-c-importador-bdgd.json`, com a
  carga da máquina ao lado do número (regra de 07/09: número de tempo sem carga não é prova).

## Fora deste item (declarado)

- Nível transformador do contrato (F01–F17), balanço por alimentador (CTMT-04/07), CAR_INST
  (UCBT-10), mínimos de faturamento (UCBT-11 completo), safra anterior (UNTRMT-07).
- Distância UC–transformador (UCBT-15): avaliável sobre a topologia montada, não sobre o arquivo.
- Ramal de ligação como aresta: RAMLIG não declara `PN_CON_2` (achado do item irmão, §4 de
  `docs/rede/MODELO_REDE.md`); segue como desvio nomeado.
