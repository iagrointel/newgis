# ADR 0024 — Geocodificar uma tabela enviada pelo usuário

Item `L2-11-a-geocodificacao-csv`. Estado: aceito, setembro de 2026.

## 1. Problema

A planilha de endereços é o formato mais comum de dado que chega de um cliente: CSV ou XLSX com logradouro,
número, bairro, município, UF e CEP, e nenhuma coordenada. No ArcGIS isso é resolvido na publicação — o
Portal geocodifica a tabela ao publicá-la como camada hospedada, consumindo crédito por endereço no ArcGIS
Online ou um locator instalado no Enterprise. A plataforma já tem o motor de UM endereço (item
`L2-11-b-geocodificador-brasil`, ADR 0013, sobre o CNEFE 2022 do IBGE) e a importação de arquivo como tabela
(item `L0-04-d`). Falta o meio: pegar a tabela, mapear as colunas, rodar o motor linha a linha e devolver uma
camada de pontos que diga, ponto a ponto, quanto se pode confiar nela.

## 2. Decisões

### 2.1 O resultado é uma tabela de linhas, e a camada é derivada dela

`plat.geocodificacao_linha` tem UMA linha por linha do arquivo — inclusive as que não deram em nada. A camada
de pontos é reescrita a partir dessa tabela a cada execução. A alternativa (gravar direto na camada e tratar
o não-resolvido como ausência) foi descartada: a linha que não resolveu é justamente a que a pessoa precisa
ver, e ela não tem geometria, então não cabe numa camada.

Consequência aceita: os dados ficam em dois lugares e é preciso um passo de sincronização
(`_sincronizar_camada`). A regra que evita divergência é que a sincronização é sempre de mão única, da tabela
de linhas para a camada, e todo caminho de escrita passa pela tabela de linhas primeiro.

### 2.2 Três estados de linha, não dois

`resolvida`, `pendente` e `malformada`. "Malformada" é problema do ARQUIVO (coluna faltando, célula gigante,
número sem dígito, linha em branco) e não melhora com uma base de endereços melhor; "pendente" é problema de
COBERTURA (a UF não está instalada, o logradouro não casou) e melhora. É a diferença entre "conserte a
planilha" e "instale a UF e mande refazer", e ela precisa estar no dado, não na cabeça de quem lê.

### 2.3 Linha ruim nunca derruba o lote

O leitor (`app/geocodificador/tabela.py`) devolve a linha ruim com o motivo em português em vez de levantar
exceção. Só três coisas derrubam o lote inteiro, e todas são conferidas antes de começar: arquivo acima do
teto de bytes, arquivo sem cabeçalho legível e mapeamento que não bate com o cabeçalho. O teto de LINHAS é
conferido durante a leitura, com a contagem real, e aí sim interrompe (o trabalho já gravado fica).

### 2.4 `origem` separa coordenada medida de coordenada arrastada

`origem = 'automatica'` quando o motor resolveu, `'manual'` quando alguém arrastou o ponto na tela de
revisão. A coluna vai para a camada publicada (`geo_origem`), e a linha manual perde a pontuação (`score`
nulo) de propósito: não existe pontuação de máquina para um ponto que uma pessoa escolheu. Uma execução
automática NUNCA sobrescreve linha de origem manual — a cláusula está no `ON CONFLICT ... WHERE` do próprio
INSERT, não numa checagem em Python que alguém possa esquecer de repetir.

### 2.5 Re-geocodificar é só o que está pendente

`POST /api/geocodificacoes/{id}/regeocodificar` enfileira o mesmo job com `so_pendentes=true`: relê o arquivo
(a fonte da verdade continua sendo ele), mas só geocodifica as linhas que não estão resolvidas e não são
manuais. Serve para depois de instalar uma UF nova. Reprocessar tudo custaria o lote inteiro de novo e
apagaria a revisão manual.

### 2.6 O lote usa o MESMO motor, com cache, não um segundo motor

`motor.buscar(..., cache=CacheLote())`. O cache guarda as três consultas caras (resolução de município,
busca de logradouro por trigram, pontos de um logradouro) enquanto o lote dura. Escrever um caminho de lote
separado — por exemplo uma consulta em massa com `JOIN` sobre uma tabela temporária — daria mais velocidade e
uma segunda implementação da hierarquia de recuo, que divergiria da primeira no primeiro ajuste. A medição
que sustenta a escolha está em `tests/medidas/L2-11-a.json`.

### 2.7 A leitura da planilha prefere cp1252 ao palpite estatístico

Medido nesta sessão: um CSV latin-1 de 39 linhas com "Rua São João" foi decodificado pelo `charset_normalizer`
(usado pela ingestão vetorial) como codificação asiática. Para o caminho da planilha de endereço a ordem é
marca de ordem de byte, UTF-8 estrito, Windows-1252, e só então o palpite. A ingestão vetorial mantém a ordem
dela, porque lá o arquivo pode vir de qualquer origem.

## 3. O que fica de fora desta passagem

- **Geocodificar uma tabela JÁ IMPORTADA** (item `L0-04-d`, parcial): a entrada aqui é o item `arquivo`. Ligar
  a entrada a uma tabela do inquilino é uma rota a mais sobre o mesmo job, quando o `L0-04-d` fechar.
- **Cobertura nacional**: só as UFs instaladas por `scripts/geocodificador_instalar_uf.py` existem. Nesta
  máquina, Roraima. Endereço de UF não instalada vira linha pendente com o motivo escrito.
- **Mapa-base fora de Guarulhos**: a tela de revisão desenha os pontos sobre o PMTiles local do item
  `L2-01-a`, que cobre Guarulhos-SP. Fora dali o arrasto funciona e grava a coordenada certa, mas não há
  imagem de referência embaixo; a tela diz isso na barra de instrução em vez de fingir.
- **Geocodificação reversa em lote** (coluna de coordenada -> endereço): o motor tem `reverso`, o lote não o
  usa.
