"""Linha de comando de administração da plataforma (item L0-14-cli-admin).

Um ponto de entrada só (`scripts/plat`, ligado em `venv/bin/plat` pelo install.sh) para tudo o que o
console e o painel de administração fazem pela tela: inquilino, usuário, token, camada, job, evento,
segredo e saúde. Serve ao install.sh, ao laço agêntico da operação e a quem instala em casa.

Regra de desenho (ADR do item): **todo subcomando fala com a MESMA API que o navegador usa**, por HTTP,
com a mesma sessão, os mesmos privilégios e os mesmos eventos gravados. Nenhum comando abre conexão com
o banco nem repete SQL da rota — o que a tela não pode fazer, a linha de comando também não pode.

Só biblioteca padrão (`argparse`, `urllib`, `http.cookiejar`, `json`); a única importação do resto do
repositório é `app.auth.totp`, e só quando o login exige o segundo fator.
"""
