# Vídeos por tarefa (item L7-04-d-videos-por-tarefa)

Data: 08/09/2026. Estado: aceito. Par: `MANUAL.md` seção 22; `tests/medidas/L7-04-d-videos-por-tarefa.json`.

## Contexto

O portão do item pede: `make videos` produz 10 ou mais vídeos com legenda e áudio, cada um ligado à
seção do manual, duração medida de até 3 minutos, playback no navegador do e2e e captura de um quadro
conferida contra a tela real. A refutação é direta: um adversário assiste 3 vídeos e executa a tarefa
em paralelo; qualquer passo do vídeo que não existe na versão instalada refuta o item. A dependência
L7-04-a (site do manual gerado) não está no master, então a parte "ligado à seção do manual" precisa
de uma decisão própria em vez de depender da tela daquela trilha.

## Decisão

1. **O vídeo não é uma animação sobre a tela; é a SESSÃO REAL gravada.** Playwright executa cada
   roteiro (`scripts/videos/roteiros.py`) contra a instalação viva e grava o webm da própria sessão
   (`record_video_dir`); o ffmpeg só monta o mp4 com a narração. Um passo que a tela não executa
   derruba a geração com o erro real na saída — não existe caminho em que o vídeo mostre algo que a
   instalação não fez, porque o vídeo É a instalação fazendo.
2. **Legenda registrada só DEPOIS da ação acontecer.** `executa_passos` mede a janela `[inicio, fim]`
   de cada passo com relógio desde a criação do contexto (a mesma referência do gravador) e a legenda
   WebVTT nasce dessa janela medida. Um passo cuja ação falhou nunca ganha janela, porque a execução
   interrompe antes. Isso é a resposta estrutural à refutação: texto sobre passo inexistente exigiria
   falsificar o registro de janelas, e esse registro vem do mesmo relógio da gravação.
3. **Narração sintética livre, fora do git.** Voz piper (`pt_BR-faber-medium`, licença livre, sem voz
   clonada de pessoa real) com binário e modelo em `~/tools/piper` (fora do repositório, caminho
   sobreponível por `PLAT_PIPER`); a geração falha com mensagem escrita se não houver piper, nunca
   produz vídeo mudo passando por completo. Cada fala é deslocada para a janela do passo
   (`adelay` por entrada); se a fala passar do vídeo, o último quadro é congelado (`tpad`) e o mp4
   cresce o necessário — a duração final é medida por ffprobe e o `--validar` reprova acima de 180 s.
4. **Vínculo com o manual pela SEÇÃO, verificado contra `MANUAL.md` no momento de gerar.** Cada
   tarefa declara o prefixo do título de uma seção de nível 2 do `MANUAL.md`; `confere_secoes_manual`
   derruba a geração se a seção sair do manual, e o `--validar` reprova de novo. A página `/videos`
   mostra a seção em cada cartão e a seção 22 do `MANUAL.md` aponta de volta para `/videos` — o laço
   manual ↔ vídeo fica fechado nos dois sentidos sem depender do site gerado da L7-04-a, que segue
   pendente como dependência (registrado no handoff, não escondido).
5. **O acervo de vídeos é dado derivado, não fonte.** `web/videos/` está fora do git (`.gitignore`);
   o manifesto `web/videos/manifesto.json` registra versão do produto (arquivo `VERSAO`), duração,
   bytes, janelas de passos e sha256 de cada mp4. `make videos` regenera sozinho quando a versão
   menor muda; `--forcar` regenera à mão; `--validar` só confere (10+ vídeos, vídeo+áudio, 3
   legendas com marca de tempo, duração por ffprobe, seções). O servidor entrega por
   `GET /videos/arquivo/{caminho}` COM sessão e lista fechada de sufixos (`.mp4`, `.vtt`, `.json`),
   e o nginx da bancada bloqueia o atalho estático `/static/videos/` — vídeo de treinamento é
   conteúdo do inquilino, não arquivo público.
6. **Confronto quadro × tela real no MESMO estado de sessão.** O e2e captura um quadro do vídeo
   `saude` por canvas no tempo médio do primeiro passo, desloga, abre a mesma página pública, espera
   o painel de saúde preencher e fotografa a tela; as duas imagens passam por escala de cinza 32×20
   e a diferença média por pixel (0-255) tem teto 24,0. A primeira rodada comparou o quadro com a
   página LOGADA — o teste passava com teto frouxo, mas era prova fraca (layout diferente); corrigido
   para o mesmo estado, a diferença medida foi 0,20, e o que resta de diferença são os números vivos
   da saúde (carimbo de tempo, latência). As duas capturas ficam em
   `tests/e2e/capturas/L7-04-d-videos-por-tarefa_*.png` para conferência a olho.
7. **Reexecução idempotente.** Toda rodada cria seus dados de prova com sufixo aleatório (usuário
   `video_<hex>`, grupo/token/conexão "do video <hex>") e apaga por API o que criou; uma
   pré-limpeza no início da geração remove resíduos de rodadas interrompidas (nomes com prefixo
   "do video" e o nome-literal de versões antigas do roteiro). Nada do inquilino de demonstração
   fora do prefixo de vídeo é tocado.
8. **Texto narrado sob a regra de escrita de 03/09, com teste.** Os roteiros passam por teste
   unitário que reprova exclamação, travessão interno, os verbetes proibidos da casa e a frase
   "você recebe"; a narração é pt-BR e as legendas pt-BR/en/es carregam o mesmo texto por passo.

## Consequências

- O portão "playback no navegador do e2e" é provado pelos 3 testes de `tests/e2e/test_videos.py`
  (lista do manifesto com manual e 3 legendas; reprodução com duração ≤ 180 s e cues carregando;
  quadro contra tela real), todos contra a instalação viva — rodada 08/09: 3/3 verdes, maior
  duração 17,7 s, 11 vídeos, 4,6 MB, carga 1 min 5,29, RAM livre 7,0 GB.
- A dependência L7-04-a (site do manual gerado) segue aberta em relação à TELA do manual; o vínculo
  seção ↔ vídeo exigido por este item está entregue por `MANUAL.md` + `/videos` (decisão 4). Quando a
  L7-04-a entrar no master, o custo é trocar o texto da seção 22 pelo link do site gerado.
- O piper e a voz ficam fora do git de propósito (112 MB); uma máquina nova precisa de
  `~/tools/piper/piper` + `vozes/pt_BR-faber-medium.onnx` para regenerar — a mensagem de falha diz
  exatamente isso.
- Os mp4 são h264+aac 22050 Hz (`faststart`), que o chromium do e2e reproduz; legendas WebVTT com
  `srclang` pt-BR/en/es e a pt-BR por padrão.
