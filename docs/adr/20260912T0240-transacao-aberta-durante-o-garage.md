# Transação aberta enquanto o objeto sobe ao Garage

Data: 12/09/2026 · Estado: **contornado no ponto certo; conserto estrutural em aberto**

## O que aconteceu

A ingestão de uma ortofoto de 3,70 GB (12 km² a 10 cm, 1,2 gigapixel) falhou com

    OperationalError: SSL connection has been closed unexpectedly

depois de 37 minutos, no passo 75 %. A conversão inteira tinha dado certo: os dois COG e a
miniatura estavam no disco de trabalho. Só a gravação no catálogo morreu.

## Por que

`app/objetos.py:538`, `parte_concluir`, roda DENTRO da transação de quem a chamou e, entre a
primeira e a última consulta, faz três coisas longas sem tocar no banco:

1. fecha o multipart no Garage;
2. **relê o objeto inteiro em stream para calcular o sha256 real** (o ETag de multipart do S3 não é
   sha256 do conteúdo);
3. copia o objeto para a chave definitiva por conteúdo e apaga o temporário.

Para o COG científico de 1,5 GB, num disco medido em 25 MB/s, esse intervalo passa de 60 segundos.
O servidor tem `idle_in_transaction_session_timeout = 60s` e derruba a sessão.

Consequência, e é o que importa: **nenhum raster cujos COG passem de ~1,5 GB conseguia ser
catalogado.** A cena Sentinel da demonstração passa porque o COG dela tem 869 MB, que cabe nos 60
segundos. É o mesmo padrão dos outros defeitos achados no mesmo dia: o limite só aparece quando o
arquivo é de cliente, não na demonstração.

A regra violada está escrita na própria casa, em `app/jobs/contexto_job.py:4`: *"Regra para toda
tarefa: trabalho longo FORA do bloco `with ctx.db()`"*. O autor da ingestão tentou cumpri-la — o
comentário em `app/imagens/ingestao.py` diz "objetos sobem um por transação curta" — mas 1,5 GB não
é curto.

## O que está no ar

`app/imagens/ingestao.py` afrouxa o teto **só dentro das transações que sobem COG**, com `SET LOCAL`:

    cur.execute("SET LOCAL idle_in_transaction_session_timeout = %s",
                (limites.RASTER_UPLOAD_TRANSACAO_PARADA,))   # 10min

`SET LOCAL` reverte no commit, então a folga não escapa daquelas duas transações: nenhuma rota da API
herda permissão de segurar transação por minutos.

### A primeira tentativa de conserto estava errada, e por quê

Primeiro foi `ALTER ROLE plat_tuniao_worker SET idle_in_transaction_session_timeout = '5min'`. Não
surtiu efeito nenhum e o job falhou de novo no mesmo ponto, aos 45 minutos. Motivo, escrito no
cabeçalho de `app/jobs/worker.py`: a role `plat_worker` serve **só para mudar estado de job** ("nunca
o pool de `app.db`"). A TAREFA abre transação pelo pool de `app.db`, ou seja, pela role da
**aplicação**, que seguia com os 60 s globais. O `ALTER ROLE` foi desfeito com `RESET`.

⛔ Não trocar o `SET LOCAL` por `ALTER ROLE`, nem na role da aplicação nem na do trabalhador.
Transação parada por minutos segura o horizonte de limpeza do Postgres, e o horizonte é do
**SERVIDOR**: atrasa o `VACUUM` de todos os bancos, inclusive os de cliente que dividem esta
máquina. Com `SET LOCAL` o custo existe só enquanto um COG sobe; com `ALTER ROLE` passa a existir em
qualquer transação daquele papel, inclusive numa rota web com defeito.

## O conserto de verdade

O trabalho no Garage tem de ficar fora da transação, com o banco tocado só nas pontas:

    abre transação curta  -> lê a linha do upload e o balde -> fecha
    trabalha no Garage    -> conclui multipart, confere sha256, copia, apaga    (sem banco)
    abre transação curta  -> apaga a linha do upload e registra o metadado -> fecha

Hoje as funções de `app/objetos.py` recebem `cur`, ou seja, quem manda na transação é o chamador.
Mudar isso é mudar o contrato de um módulo compartilhado por três caminhos: a exportação de camada
(`L0-04-h`), o envio por partes (`app/uploads/rotas.py`) e a ingestão de imagem. O caminho sugerido é
um parâmetro opcional `abrir` (invocável que devolve um contexto de transação), com o comportamento
atual como padrão, para nenhum chamador existente mudar de comportamento.

⛔ Não remover a releitura do objeto para conferir o sha256. Ela não é desperdício: é a conferência de
integridade que torna a proveniência verificável em vez de prometida, e está declarada no docstring
de `parte_enviar_arquivo` como "a conferência de verdade". Quem quiser cortar o custo, calcule o
sha256 no mesmo passe do envio e trate a releitura como auditoria periódica, não como o único
mecanismo — mas isso é decisão de produto, não ajuste de desempenho.

## Como reproduzir

    # um raster cujos COG somem mais de ~1,5 GB
    python3 /mnt/pgdata/plat-orto/enviar_e_ingerir.py <arquivo.tif> "<titulo>" medida.json
    # sem o remendo: falha em "gerando a miniatura" com SSL connection has been closed
