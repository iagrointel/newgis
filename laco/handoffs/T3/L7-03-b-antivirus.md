# Handoff — item L7-03-b-antivirus-anexos (arquiteto + backend, passagem única)

**Objetivo.** Pedido do dono: antivírus em upload de anexo — L0-11 (arquivos/objetos) e L0-03 (miniatura do
catálogo) hoje aceitam upload sem varredura. ClamAV se couber (`clamd`, conferindo disco antes); senão,
scanner de assinatura básica (magic bytes/extensão coerente com conteúdo real, polyglot óbvio) como camada
mínima, com gancho pronto para trocar por ClamAV depois. Teste: `.jpg` com conteúdo de script recusado.

O item no `estado.json` (`L7-03-b-antivirus-anexos`) tinha `portao_de_pronto`: **"portão a fixar pelo
arquiteto no turno em que o item que a pediu entrar (registrar aqui antes de construir)"** — este turno é
esse turno; o portão fixado é o que este handoff descreve (recomendo ao gerente atualizar o campo no
`estado.json` com o texto abaixo, e o `estado` do item para `parcial`, não `entregue` — ver "Riscos").

## Decisão D21: ClamAV NÃO instalado nesta passagem

Medido ANTES de decidir (não presumido):
```
$ df -h / /mnt/pgdata
/dev/vda2  469G  452G   13G  98% /
/dev/vdb   688G  675G   14G  99% /mnt/pgdata
$ free -h
Mem:  23Gi total · 323Mi livre · swap 8,0Gi CHEIO (8,0Gi usado)
```
`clamav-daemon` (pacote) é pequeno (~1 MB), mas a base de assinaturas do `freshclam` fica residente em RAM
no `clamd` (~1,3-1,5 GiB, mesma estimativa da hipótese original do item). Com 323 MiB livres e swap cheio,
subir isso agora tem risco real de repetir o incidente de OOM já registrado na casa
(`reference_oom-derrubou-postgres`). D21 (`laco/estado.json`, aberta desde 05/09) já cobre exatamente esta
tensão disco×funcionalidade — não é uma decisão nova, é a mesma D21 aplicada a este item. **Documentado, não
instalado**; ver `docs/SEGURANCA.md` §8.1.

## O que fiz

1. **`app/varredura_conteudo.py`** (novo): camada mínima. `MotorAssinaturaBasica` usa `python-magic`
   (`libmagic`, já dpkg nesta máquina — `python3-magic`, e já citado em `deploy/pacotes_apt.txt` por outra
   trilha, L7-14/L0-04-a, pelo MESMO motivo) para identificar o tipo REAL dos primeiros 8 KiB e recusa quando
   não bate com a família esperada do `Content-Type` declarado (`TIPOS_PERMITIDOS`, mesmas chaves de
   `app/objetos.EXTENSOES`). Interface `Motor` (`Protocol`) + `MOTOR_ATIVO`: um `MotorClamAV` futuro
   implementa o mesmo `escanear(cabecalho, content_type) -> Resultado` e substitui `MOTOR_ATIVO`, sem tocar
   nenhuma rota.
2. **Decisão medida e testada: SEM denylist "tipo perigoso independente do declarado"** para
   `application/octet-stream` (upload genérico sem família fixa). Medi ANTES de escrever a regra:
   `libmagic` classifica ~0,9% de bytes PURAMENTE ALEATÓRIOS (18/2000 amostras de 4 KiB) como algo diferente
   de `application/octet-stream`, inclusive `application/x-dosexec` por coincidência de assinatura. Um
   denylist que valesse mesmo sob `Content-Type` genérico reprovaria upload binário legítimo (CAD, dado
   proprietário) **ao acaso** — quebraria P3 (suíte sempre verde) e P5 (reprodutível), inclusive os testes
   JÁ EXISTENTES de `tests/api/test_arquivos.py` que usam `os.urandom()` sob `application/octet-stream`.
   Escolhi checar só a família declarada×detectada; o genérico passa sem exame de assinatura nesta camada
   (é exatamente onde ClamAV faria a diferença de verdade). Prova permanente da medição:
   `tests/unit/test_varredura_conteudo.py::test_binario_generico_aleatorio_nunca_e_recusado_por_assinatura`
   (200 amostras, `assert r.permitido is True` em todas).
3. **Integração — na BORDA (`app/rotas_arquivos.py`), nunca dentro de `objetos.guardar()`** (nunca depois de
   já ter gasto uma chamada ao Garage): **primeira tentativa foi colocar `escanear_cabecalho()` dentro de
   `objetos.guardar()`** (cobriria todo chamador de uma vez, inclusive a miniatura) — **quebrou um teste
   pré-existente** (`tests/api/catalogo/test_miniatura.py::test_adaptador_de_objetos_e_url_assinada`, que
   grava `b"abc"` sob `image/png` de propósito para testar só o contrato de armazenamento do adaptador, sem
   ser uma imagem de verdade). Corrigido: `objetos.guardar()` **não varre** (é adaptador genérico, também
   chamado com conteúdo já validado por outro meio ou sintético de teste — documentado no seu próprio
   docstring); a varredura entra só em `app/rotas_arquivos.py::enviar()`, nos dois caminhos de
   `POST /api/arquivos` (1 PUT direto, e a 1ª parte do multipart, ANTES de `objetos.parte_iniciar`).
   `POST /api/itens/{id}/miniatura` (L0-03) não precisou de nenhum código novo: `miniatura.normalizar()` já
   decodifica com Pillow e só aceita PNG/JPEG/GIF de verdade, reencodando para PNG limpo sem metadado —
   barreira mais forte que checar assinatura de bytes, existia antes deste item.
4. **`docs/SEGURANCA.md` §8** (novo): D21, mecânica, tabela dos 3 pontos de integração, gancho ClamAV, e o
   que fica de fora.
5. **Testes**:
   - `tests/unit/test_varredura_conteudo.py` (10 testes): cláusula literal do portão (jpg-declarado +
     script → recusado, `tipo_detectado: text/x-shellscript`), PNG/JPEG reais passam, SVG-com-script
     declarado como imagem recusado (polyglot), zip declarado como PDF recusado, KMZ real (que é um zip)
     passa, CSV passa, conteúdo vazio recusado, `Content-Type` com `; charset=` normalizado, e o teste de
     não-flakiness do item 2 acima.
   - `tests/api/test_arquivos.py` (+2 testes): `test_api_recusa_script_disfarcado_de_jpeg` (fim a fim, real,
     `POST /api/arquivos` com `Content-Type: image/jpeg` e corpo `#!/bin/sh...` → 415
     `conteudo_recusado`/`tipo_detectado`) e `test_api_recusa_script_grande_disfarcado_de_png_antes_do_
     multipart` (mesma coisa acima do teto de uma parte, provando que o multipart nem abre).

## Evidência

```
$ venv/bin/ruff check app/varredura_conteudo.py app/objetos.py app/rotas_arquivos.py app/catalogo/rotas_miniatura.py tests/unit/test_varredura_conteudo.py tests/api/test_arquivos.py
All checks passed!
$ flock .../.pytest.lock venv/bin/pytest tests/api/test_arquivos.py tests/unit/test_varredura_conteudo.py tests/unit/test_varredura_dependencias.py tests/api/catalogo/test_miniatura.py -m "not lento" -q
...........................................                              [100%]
43 passed
$ flock .../.pytest.lock make check-rapido      # suíte inteira, com o trabalho concorrente de outras trilhas
lint + sem-marcador + limites + teste: 742 passed, 28 deselected (208.38s)
```

A primeira rodada de `test_miniatura.py` (antes da correção do item 3) reprovou 1 de 43 —
`test_adaptador_de_objetos_e_url_assinada` (FAILED: `ConteudoRecusado: conteúdo real (text/plain) não bate
com o Content-Type declarado (image/png)`). Corrigido movendo a varredura para `rotas_arquivos.py`; segunda
rodada: 43/43 verdes, `make check-rapido` completo também verde (742 testes, incluindo tudo que as outras
trilhas tinham no repositório no momento).

## Riscos e o que fica de fora (não esquecido)

- **ClamAV real não instalado** (D21) — a camada de hoje pega disfarce óbvio de tipo declarado × conteúdo
  real, não assinatura de malware conhecido. Por isso recomendo `estado: parcial`, não `entregue`, no
  `estado.json`.
- Conteúdo genérico (`application/octet-stream`) não é examinado por assinatura nesta camada (justificado
  acima) — upload binário arbitrário passa sem exame até ClamAV existir.
- Não abre contêineres compostos (não varre dentro do zip do KMZ, entrada por entrada).
- A rota de sincronização da PWA de campo (L2-07) ainda não existe; quando existir e receber byte cru de
  fora (não vindo de `POST /api/arquivos`), PRECISA chamar `escanear_cabecalho()` explicitamente antes de
  gravar — `objetos.guardar()` não varre mais (decisão deste turno, ver item 3), então a barreira não é
  automática para rota nova nenhuma.
- **Não toquei `CHANGELOG.md`/`ARQUITETURA.md`/`MANUAL.md`** — mesma razão do handoff irmão (L7-03-f):
  outra trilha (L7-14/L7-16) tinha edições staged não comitadas nesses três arquivos quando comecei;
  evitei misturar. `docs/SEGURANCA.md` (não tocado por ninguém além de mim, conferido por `git diff --stat`
  antes de escrever) carrega a documentação completa dos dois itens. A outra trilha comitou sozinha
  (`3302f56`) enquanto eu ainda trabalhava; meu commit (`d69f417`) ficou limpo, só com os 12 arquivos dos
  meus dois itens — nada da trilha `mapa`/pmtiles (`web/mapa.html` e afins, ainda não comitada) foi tocado.

## Para o próximo turno

- Quando D21 resolver (disco/RAM, ou servidor dedicado do D37): instalar `clamd`, escrever `MotorClamAV`
  (mesma interface `Motor`), trocar `MOTOR_ATIVO`, sem mexer em `objetos.py`/rotas.
- Reconciliar CHANGELOG/ARQUITETURA/MANUAL do turno 3 com esta passagem (a de L7-14/L7-16 já está em `3302f56`).
