# ADR 0007 — Pacotes apt da linha e assinatura de pacote de atualização (itens L7-14-instalacoes-apt-desta-linha e L7-16-assinatura-pacote)

Estado: aceito (arquiteto+backend, passagem única, turno avulso, 06/09/2026).

## 1. Pacotes apt (L7-14)

O `install.sh` já conferia por nome, com `dpkg -s`, quatro pacotes do sistema (ADR 0001 seção 2.1:
`python3-uvicorn`, `python3-psycopg2`, `python3-venv`, `python3-cryptography`) — e falhava se algum
faltasse, sem instalar nada. Este item automatiza essa etapa e fecha a lista com o que os ADRs já
tinham decidido, mas ainda não estava declarado num único lugar: `gdal-bin`/`python3-gdal` (`ogrinfo`
chamado por subprocesso em `app/jobs/worker.py:_versao_gdal`, ADR 0003 seção 8, e o módulo `osgeo` da
venv `--system-site-packages`, ADR 0001 seção 2.1) e `python3-magic` (sniff de tipo por conteúdo, ADR
0005 seção 0.5, item L0-04-a). Os sete estão MEDIDOS instalados nesta máquina em 06/09/2026 (`dpkg -s`).

`deploy/pacotes_apt.txt` é a lista fechada (um pacote por linha, comentários com `#`, versão medida só
como rótulo — quem fixa versão de verdade é o apt do repositório da distribuição, e as bibliotecas
Python continuam fixadas com `==` em `requirements.txt`, ADR 0001 seção 2.1). `install.sh` passo "e2"
lê o arquivo, roda `dpkg -s` em cada pacote e só chama `apt-get install -y` para o que faltar —
idempotente por construção: rodar duas vezes não tenta reinstalar o que já está lá, e a segunda
conferência (depois do `apt-get install`) pega o caso de um pacote sem candidato no repositório
configurado. `tests/unit/test_pacotes_apt.py` confere a lista (sem duplicata, com os sete pacotes
esperados) e que cada um está de fato instalado nesta máquina.

**Fora de escopo de propósito** (evita colisão com item que já é dono):
- `postgresql-16-pgrouting`, `pgstac`, `pg_partman`, FDW de terceiro (`tds_fdw`/`oracle_fdw`) — são do
  item `L7-14-extensoes-fdw` (portão e adversário próprios, dependente de `L7-01-a-compose-perfis`;
  MEDIDO 05/09/2026 no `estado.json`: `postgresql-16-pgrouting` NÃO instalada, candidato apt
  `postgresql-16-pgrouting 4.0.1-1.pgdg24.04+1`). Um `pgRouting` instalado por dois itens diferentes,
  cada um achando que é dono, é o tipo de duplicação que este ADR evita registrar.
- `ezdxf` (biblioteca Python pura, não é pacote apt) e o binário `dwg2dxf`/`dxf2dwg` do LibreDWG (só
  existe no GPU box, outra máquina) — ADR 0005 seção 12.4 mediu que o LibreDWG perde entidades na volta
  DWG→DXF e deixou a decisão D23 (ODA File Converter) em aberto; sem decisão tomada, não entram como
  "vai precisar", porque ainda não se sabe se vão ser precisos (metodologia da casa: ausência de decisão
  nunca vira pacote na lista).
- `gitleaks`/`pip-audit`/`osv-scanner`/`trivy` — item de varredura de CVE/segredo (linha L7 de
  segurança, trilha própria em andamento neste mesmo turno: `scripts/varredura_dependencias.py`).
  `gitleaks` em particular também não tem pacote apt nesta distribuição (é um binário Go distribuído só
  como release do GitHub); por isso o item L7-16 (seção 3 abaixo) não depende dele.

## 2. Assinatura de pacote de atualização (L7-16) — desenho

Ed25519 via `cryptography` (pacote dpkg `python3-cryptography`, já na lista da seção 1; a mesma
biblioteca que o ADR 0002 usa para AES-GCM do segredo TOTP). Ed25519 foi escolhido em vez de RSA por
ser o par que a própria hipótese do item já fixava e por não exigir parâmetro de curva/tamanho de chave
(uma decisão a menos, uma forma a menos de errar); `cosign`/Sigstore ficou fora porque o modo keyless
exige rede no momento da assinatura E da verificação (Fulcio/Rekor), e o público deste item é
exatamente o appliance sem internet (item L7-11-b).

Dois papéis:
- **Assinar** (`scripts/assinar_pacote.sh`) roda na máquina de quem corta o release, nunca no
  appliance do cliente. Se a chave privada ainda não existe no caminho de `PLAT_CHAVE_PRIVADA`, gera um
  par novo (`Ed25519PrivateKey.generate()`), grava a privada em PEM PKCS8 sem senha, modo 0600, criada
  com `O_EXCL` (nunca sobrescreve uma chave existente por acidente), e registra a pública em
  `deploy/chaves_publicas_release.txt`. Esse arquivo de confiança **é** o que se versiona no git; a
  privada não passa perto do repositório — o padrão de caminho é `/etc/plat/chaves/…` quando root (mesma
  convenção do `CRED_DIR` de segredos do item L7-19) ou `$HOME/.config/plat/chaves/…` como usuário
  comum, nunca dentro de `APP_DIR`. `.gitignore` ganhou `*_priv.pem` e `chaves_privadas/` como defesa em
  profundidade, para o caso de alguém apontar a variável para dentro do repositório por engano.
- **Verificar** (`scripts/verificar_pacote.sh`) roda no appliance, sem rede: lê o `.sig` (JSON com
  `algoritmo`, `chave_id`, `assinatura_b64`), busca `chave_id` em `deploy/chaves_publicas_release.txt`
  (fixado nesta versão do repositório) e recusa se a chave não é conhecida, se o algoritmo não é
  `ed25519`, ou se `Ed25519PublicKey.verify()` levantar `InvalidSignature` — três causas de recusa
  distintas (pacote de origem desconhecida × versão comprometida do formato × pacote alterado),
  três códigos de saída diferentes (3, 2, 4) para quem automatiza a leitura do resultado.

`chave_id` é `"k" + sha256(chave_pública_crua)[:16]` — nunca um contador, para duas chaves diferentes
nunca colidirem por acaso e para o id ser calculável por quem só tem a chave pública (não depende de um
registro central). A assinatura cobre os bytes do arquivo inteiro (Ed25519 já faz o hash internamente;
não há um passo de hash separado a esquecer).

## 3. Cláusulas do portão e como foram provadas

- **Sem rede**: nenhum dos três arquivos (`assinar_pacote.sh`, `verificar_pacote.sh`,
  `plat_assinatura.py`) chama `curl`/`wget`/`requests`/`httpx`/`urllib`/`socket`
  (`test_scripts_nao_chamam_rede`) — e estruturalmente não há porque chamar: gerar chave, assinar e
  verificar são só leitura/escrita de arquivo e conta em Ed25519.
- **1 byte alterado ⇒ recusa**: `test_um_byte_alterado_recusa` inverte 1 bit do primeiro byte do
  pacote assinado, confere que `verificar_pacote.sh` sai ≠ 0 com "assinatura inválida", e restaura o
  byte para prova de que o `.sig` em si continua válido (não foi o arquivo de assinatura que quebrou).
- **Chave privada nunca no git nem em argv**: os dois scripts só passam CAMINHOS como argumento de
  linha de comando, nunca o conteúdo da chave; `plat_assinatura.py` só lê a privada de um arquivo.
  `test_chave_privada_nunca_aparece_em_arquivo_produzido` confere que os bytes PEM da chave privada não
  aparecem em nenhum `.sig`, no arquivo de confiança, nem em stdout/stderr de nenhum dos dois comandos.
  `test_chave_privada_nunca_apareceu_no_historico_do_git` substitui o binário `gitleaks` (não é pacote
  apt nesta distribuição — ver seção 1) por uma varredura direta de `git log --all -p -- deploy/
  scripts/` procurando o cabeçalho de uma chave privada PEM; ficou registrado como o que este item
  cobre, e a varredura mais ampla (histórico inteiro, todos os tipos de segredo) é o item de CVE/segredo
  já em construção noutra trilha deste turno.
- **Rotação com período de dupla chave**: `test_rotacao_chave_nova_so_e_aceita_depois_de_distribuida`
  reproduz a pergunta do portão ao pé da letra — gera chave nova, assina um pacote com ela, e confere
  que um appliance cujo arquivo de confiança só tem a chave antiga **recusa** esse pacote (a resposta é
  NÃO, como o portão exige). Só depois de acrescentar a linha da chave nova ao arquivo de confiança
  (simulando uma atualização anterior, assinada com a chave antiga, que já trazia essa linha) é que o
  mesmo pacote passa a ser aceito — a ordem segura é sempre "distribuir a chave pública nova, só depois
  assinar com ela de verdade", nunca o contrário.

## 4. Limite conhecido deste turno

`deploy/chaves_publicas_release.txt` fica vazio de propósito — nenhuma chave de demonstração foi
fixada nele. O primeiro release real precisa rodar `scripts/assinar_pacote.sh` uma vez (gera o par,
escreve a linha no arquivo) e alguém commitar essa linha antes de distribuir qualquer pacote assinado
de verdade; até lá, `verificar_pacote.sh` recusa todo pacote por "chave não confiável", que é o
comportamento seguro por padrão (nunca aceitar por ausência de configuração).
