# ADR — varredura de segurança contínua no portão (item HARD-01)

Estado: aceito (líder de endurecimento, 07/09/2026). Motivos MEDIDOS nesta máquina ou LIDOS em código, como o ADR 0001 exige.

## Decisões

1. **Um só comando, cinco ferramentas, uma política.** `make seguranca` (`scripts/varredura_seguranca.py`) roda
   bandit, pip-audit (delegado ao item L7-03-f, que fica intacto), `npm audit`, gitleaks e trivy, normaliza os
   achados num formato único e aplica UMA política de bloqueio por ferramenta (docs/SEGURANCA.md §9.2). Entra em
   `make check` — o portão da fila — e não em `check-rapido` (o driver de 30 min não precisa de rede).
   MEDIDO 07/09: 17 s no total (bandit 1,8 s · pip-audit 6,8 s · npm 0,9 s · gitleaks 2,5 s sobre 851 commits ·
   trivy 4,7 s), o que cabe no portão sem mudar o tempo da suíte.
2. **Exceção sempre com prazo e responsável, num arquivo só.** `docs/excecoes_seguranca.json` (ferramenta, id,
   arquivo/pacote opcionais, motivo, prazo, registrado_em, quem). Sem prazo, a lista inteira reprova (código 2). Prazo
   vencido = a exceção some sozinha. Recusado o `# nosec` do bandit e o `.trivyignore` do trivy como mecanismo de
   exceção: escondem o achado dentro da ferramenta, sem prazo, e ninguém os lê no relatório. Fica UMA exceção do
   `# nosec` no próprio orquestrador (o `urlopen` que espera a instância de teste subir) — e ela é contada no laudo.
3. **Ferramentas binárias fixadas por sha256, instaladas no cache do usuário.** gitleaks, trivy e ZAP não têm pacote
   apt nesta distribuição (deploy/pacotes_apt.txt já registrava). `deploy/ferramentas_binarias.txt` fixa versão, URL
   de release e sha256 do pacote; `scripts/ferramentas_seguranca.sh` confere o sha antes de extrair (sha diferente =
   pacote apagado, saída 3) e instala em `~/.cache/plat/ferramentas` — como `~/.cache/pip`, nunca `/usr/local`, nunca
   no PATH. Recusado `var/ferramentas` dentro da árvore: cada worktree da fila baixaria 300 MB de novo.
4. **ZAP em pacote Linux sobre o OpenJDK 21 já instalado, não em docker.** MEDIDO: a imagem `zaproxy:bare` tem 505 MB
   só de camadas comprimidas (acima do teto de 500 MB por download da regra 6 do brief); o pacote Linux tem 244 MB e
   traz spider, regras passivas, automação e relatórios. Só regras PASSIVAS (baseline): nunca varredura ativa.
5. **O baseline roda contra instância PRÓPRIA, com o nginx de verdade.** `rodar_zap` sobe uvicorn no ambiente da
   trilha corrente + um nginx renderizado de `deploy/nginx.conf` (o mesmo modelo que o install.sh usa, em porta alta,
   sem TLS) e derruba os dois pelo PID. Sem o nginx o ZAP acusaria a falta de cabeçalhos que o nginx acrescenta; com
   ele, o que o ZAP vê é o que o cliente vê. Recusa `PLAT_SCHEMA=plat`. Fica fora de `make check` (precisa de uma
   trilha no ar): é `make seguranca-zap` / `make seguranca-gravar`.
6. **O relatório versionado é GERADO, e a fila confere que não está desatualizado.** A seção 9 de docs/SEGURANCA.md
   entre marcadores é renderizada de `tests/medidas/HARD-01-seguranca.json` + lista de exceções + lista de binários;
   `make seguranca` roda `--check-doc` (mesmo desenho do `docs/gerar_limites.py --check`). O que NÃO entra no
   cotejo: as contagens da varredura corrente (mudam a cada commit e reprovariam todo ramo) — entra a última varredura
   REGISTRADA, com data e commit. A coluna "dias até o prazo" é relativa e é ignorada no cotejo.
7. **Consertos mecânicos feitos na primeira rodada, o resto vira item.** `xml.etree` → `defusedxml` em `app/garage.py`
   (B314, já era dependência); `server_tokens off` (ZAP 10036); `X-Frame-Options` nos blocos `/static/` e PMTiles do
   nginx, que repetiam o conjunto de cabeçalhos sem ele (ZAP 10020); **Content-Security-Policy** em todos os blocos
   (ZAP 10038), verificada com a suíte e2e (playwright) contra o nginx renderizado — `/api/docs` tem CSP própria
   porque o arranque do swagger-ui é inline. Os 36 `B608` (SQL montado por texto, confiança média) não bloqueiam e
   são a lista de trabalho do adversário (item HARD-03).

## Consequências

- Rede no portão: OSV.dev (cache por id), registry.npmjs.org (1 s), e o download único das binárias. Rede fora =
  código 2 = reprova com a mensagem — nunca "0 achado".
- Os padrões do gitleaks acham 21 falsos positivos estruturais no histórico (ids de item, i18n, agulhas de teste,
  impressão digital de chave pública, variável vazia): ficam em `.gitleaks.toml`, com o motivo, porque não são achado
  — a lista com prazo é para achado real ou duvidoso.
