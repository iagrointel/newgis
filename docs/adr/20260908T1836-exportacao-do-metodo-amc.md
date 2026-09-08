# ADR 20260908T1836 — exportação do método do motor AMC (item L3-01-i-exportacao-metodo)

Contexto: o motor AMC já combina fatores (`app/amc/combinacao.py`, ADR 20260907T1013), mas o MÉTODO —
o que foi decidido, sobre que dado, com que pesos — vive só no estado da aplicação. O item pede a
exportação dele em duas peças amarradas: um JSON canônico e um PDF gerado por script no desenho da
casa (molde Suitability Modeler: resumo, diagrama do fluxo, uma página por fator, pesos, resultado,
ressalvas). O portão fixa a regra de verdade: páginas = seções; TODO número extraído do PDF tem de
existir no JSON; o JSON reimportado recria o modelo com o MESMO hash; e o adversário que alterar um
peso no JSON exportado muda o hash e não pode reapresentar o PDF antigo como do modelo novo.

## Decisão

`app/amc/metodo.py` é o contrato do documento `plat/amc_metodo` (versão 1): nome, data (entra por
parâmetro — módulo puro, sem relógio), motor (versão e sha do git), modelo normalizado (fatores,
contagem, pesos e pesos normalizados a 4 decimais, vetos, combinador e política COM as descrições
dentro do documento, gama, escala), transformações declaradas por fator (opcionais — o executor ainda
não juntado é quem as produz; o formato já tem o lugar delas), camadas de entrada com nome e sha256
por fator, a entrada bruta avaliada (matriz unidade × fator com `null`), o resultado quando houve
(cobertura, veto, motivo) e as ressalvas obrigatórias (pesos escolhidos, triagem: sinal não prova,
camada é proxy declarado). O `sha256` do documento é o hash da serialização canônica (chaves
ordenadas, separadores mínimos) DELE MESMO sem o campo — `importar_metodo` recalcula e recusa com
`documento_alterado` (gravado × recalculado) qualquer diferença; formato e versão desconhecidos são
recusados com código estável antes disso.

`app/amc/relatorio.py` gera o PDF DESTE documento e só dele, com reportlab em modo determinístico
(`invariant=1`): o mesmo documento produz exatamente os mesmos bytes, sem relógio em metadado. Cada
seção é uma página (portão: páginas = seções). A regra de ouro contra número digitado tem três
guardas: o PDF imprime os números na MESMA normalização do documento (`_num_txt` sobre `_num` de 4
casas); os gráficos não têm rótulo numérico próprio e não há numeração de página (o número da página
não estaria no JSON); e contagens, ids de unidade, descrições de combinador/política e o sha256 do
motor entraram no DOCUMENTO justamente para o relatório não precisar inventar nada. O teste extrai as
PALAVRAS do PDF com pdfplumber e confere cada palavra que é só número contra
`metodo.numeros_do_documento` — que varre valores, TEXTOS (datas, sha do motor) e CHAVES (o "256" de
"sha256") —; palavras hexa longas (as duas metades de 32 do hash) saem dessa conta porque o hash é
conferido à parte: o relatório imprime o sha256 do documento e `metodo.confere_pdf` procura ele no
texto extraído, o que é o que impede o PDF antigo de valer pelo modelo novo.

`scripts/metodo_exportar.py` é a linha de comando do produto: entrada JSON (nome, modelo, camadas,
transformações, entrada, resultado opcional), saída `<slug>.metodo.json` + `<slug>.relatorio.pdf` e o
sha256 na saída padrão.

## Por que o documento carrega a entrada bruta e o resultado, e não só o modelo

Custo: o arquivo cresce (a matriz é O(unidades × fatores)). Vale porque o portão do item torna o PDF
auditável contra o JSON — e a página de fator do relatório mostra o histograma bruto e a tabela de
valores por unidade; sem a matriz no documento, esses números seriam exatamente os "digitados" que o
portão proíbe. Pelo mesmo motivo o resultado entra com cobertura e veto por unidade. Tabelas de
fator e de resultado listam no máximo 30 unidades por página (a página é única por seção); quando há
mais, o PDF o diz e o JSON é a referência completa.

## O que ficou de fora e por quê

Mapa final e curva de transformação por fator não são gerados: dependem das camadas geográficas e do
módulo de transformações (worktree irmão ainda não juntado à master). O relatório registra isso como
ressalva impressa na própria página de ressalvas, e o fator aparece como histograma bruto — que é o
que o portão do item pede. Regiões idem (dependem de geometria de análise que o documento não
carrega). Importação por API e tela não faz parte deste item: o portão pede JSON reimportado com o
mesmo hash (feito em teste automatizado sobre `importar_metodo`), não rota.

## Conserto de infra que o item exigiu

`app/versao.py` não sabia ler o sha num worktree do git: lá `.git` é um ARQUIVO ("gitdir: …"), a ref
do ramo vive no diretório comum do repositório principal e o arquivo `commidir` dentro do gitdir diz
onde ele fica. Sem isso, qualquer execução fora da árvore principal (o script de exportação entre
elas) falhava sem `PLAT_GIT_SHA` no ambiente. Corrigido para seguir o apontador e o `commidir`, com
teste.

## Medição

`tests/medidas/L3-01-i-exportacao-metodo.json`: geração do PDF 6,871 ms (carga 1 min 5,35), 8 páginas
= 8 seções (pypdf), 23 números extraídos do PDF e todos presentes no JSON, e a verificação visual
página a página (pdftoppm → leitura de agente) registrada como cláusula do portão.
