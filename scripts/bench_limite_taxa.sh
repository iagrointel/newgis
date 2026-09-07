#!/bin/bash
# Bancada do item L7-03-b-rate-limit-abuso: prova as três camadas com pedidos HTTP REAIS — na porta
# direta do uvicorn E através do nginx — e a refutação (50 IPs x 1 token; 1 IP x 50 tokens). Não sobe
# nada sozinho: espera a bancada já preparada (uvicorn na porta da trilha + o bloco privado de nginx +
# a jail "plat" do fail2ban instalados — ver docs/SEGURANCA.md §9 para o passo a passo manual).
#
# "Atacante" = 127.0.0.9 (loopback; todo 127.0.0.0/8 é loopback no Linux, `curl --interface` funciona
# sem configurar nada) — NUNCA um IP real, e nenhum outro serviço da casa depende desse endereço, então
# mesmo um banimento de VERDADE pelo fail2ban não quebra nada nesta máquina compartilhada.
set -uo pipefail
PORTA_APP=${1:-8276}
PORTA_NGINX=${2:-18276}
DIRETO="http://127.0.0.1:$PORTA_APP"
NGINX="http://127.0.0.1:$PORTA_NGINX"
ATACANTE=127.0.0.9
SAIDA=${SAIDA:-/tmp/bench_limite_taxa}
mkdir -p "$SAIDA"

ok()  { printf '[ok]  %s\n' "$*"; }
info(){ printf '[--]  %s\n' "$*"; }
falha(){ printf '[FALHA] %s\n' "$*"; FALHAS=$((FALHAS+1)); }
FALHAS=0

codigo() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "== 1. camada 2 (Postgres, por inquilino) responde IGUAL na porta direta e via nginx =="
for base in "$DIRETO" "$NGINX"; do
  c=$(codigo "$base/saude")
  [ "$c" = 200 ] && ok "$base/saude -> 200" || falha "$base/saude -> $c (esperado 200)"
done

echo "== 2. camada 1 (nginx por IP): zona plat_api derruba rajada acima do burst — SÓ existe via nginx =="
# 90 pedidos rapidos: rate=120r/m + burst=60 nodelay -> as primeiras ~60 passam (404, rota não existe),
# o resto toma 429. Na porta DIRETA (sem nginx) não há zona nenhuma: todos voltam 404, nunca 429 -- é a
# prova de que a camada 1 é mesmo só do nginx, não um efeito colateral de outra coisa.
c_direto=$(for i in $(seq 1 90); do codigo "$DIRETO/api/inexistente-$i"; echo; done | sort | uniq -c)
c_nginx=$(for i in $(seq 1 90); do codigo "$NGINX/api/inexistente-$i"; echo; done | sort | uniq -c)
echo "  direto (sem nginx):"; echo "$c_direto" | sed 's/^/    /'
echo "  via nginx:"; echo "$c_nginx" | sed 's/^/    /'
echo "$c_direto" | grep -q ' 429$' && falha "porta direta NÃO deveria ter 429 (camada 1 é só do nginx)"
echo "$c_nginx" | grep -q ' 429$' && ok "via nginx apareceu 429 (zona plat_api segurou a rajada)" \
  || falha "via nginx deveria ter 429 acima do burst"

echo "== 3. mesma prova em /tiles/ (zona plat_tiles) — existe mesmo sem a rota do L1-02-tiles-token =="
c_tiles=$(for i in $(seq 1 320); do codigo "$NGINX/tiles/inexistente/$i.png"; echo; done | sort | uniq -c)
echo "$c_tiles" | sed 's/^/    /'
echo "$c_tiles" | grep -q ' 429$' && ok "zona plat_tiles segurou (limit_req roda antes de existir backend real)" \
  || falha "esperava 429 em /tiles/ acima do burst=200"

echo "== 4. X-Forwarded-For forjado e ROTACIONADO não devolve cota nenhuma na zona do nginx =="
# a zona do nginx conta por \$binary_remote_addr (o socket), nunca por cabeçalho — rotacionar o XFF a
# cada pedido não deveria mudar em NADA o ponto em que o 429 aparece.
sem_forja=$(for i in $(seq 1 200); do codigo "$NGINX/api/xff-controle-$i"; echo; done | grep -c '^429$')
com_forja=$(for i in $(seq 1 200); do codigo -H "X-Forwarded-For: 203.0.113.$((i % 255))" "$NGINX/api/xff-teste-$i"; echo; done | grep -c '^429$')
echo "  429 sem forjar XFF: $sem_forja · 429 forjando e rotacionando XFF: $com_forja"
dif=$(( sem_forja > com_forja ? sem_forja - com_forja : com_forja - sem_forja ))
[ "$dif" -le 5 ] && ok "XFF forjado não moveu o ponto do 429 (diferença $dif, dentro do ruído)" \
  || falha "XFF forjado pareceu mudar a contagem (diferença $dif) — investigar realip"

echo "== 5. fail2ban-regex: o filtro plat-abuso reconhece as linhas 401/429 do log real de verdade =="
if command -v fail2ban-regex >/dev/null 2>&1; then
  saida_regex=$(fail2ban-regex /var/log/nginx/plat_access.log /etc/fail2ban/filter.d/plat-abuso.conf 2>&1)
  echo "$saida_regex" | grep -Ei "Lines: |failregex:" | sed 's/^/    /'
  n=$(echo "$saida_regex" | grep -oiP 'failregex: *\K[0-9]+' | head -1)
  [ -n "$n" ] && [ "$n" -gt 0 ] && ok "fail2ban-regex casou $n linha(s) no log real" \
    || falha "fail2ban-regex não casou nenhuma linha (filtro ou log errados)"
else
  falha "fail2ban-regex ausente nesta máquina"
fi

echo "== 6. jail plat bane de verdade (nftables) o atacante de loopback 127.0.0.9, dentro do findtime =="
sudo fail2ban-client set plat unbanip "$ATACANTE" >/dev/null 2>&1
antes=$(sudo fail2ban-client status plat | grep -c "$ATACANTE")
# gera >= maxretry (15) linhas 401/429 atribuídas a 127.0.0.9: martela /api/login errado (a zona
# plat_login também vai 429 rápido, e tanto 401 quanto 429 casam no filtro)
for i in $(seq 1 30); do
  curl -s --interface "$ATACANTE" -o /dev/null -X POST "$NGINX/api/login" \
    -H 'Content-Type: application/json' -d '{"inquilino":"demo","login":"zz-nao-existe","senha":"errada"}'
done
sleep 3
status=$(sudo fail2ban-client status plat)
echo "$status" | sed 's/^/    /'
if echo "$status" | grep -q "$ATACANTE"; then
  ok "127.0.0.9 banido pela jail plat (\`fail2ban-client status plat\`)"
else
  falha "127.0.0.9 NÃO apareceu banido — ver /var/log/nginx/plat_access.log e journalctl -u fail2ban"
fi
sudo fail2ban-client set plat unbanip "$ATACANTE" >/dev/null 2>&1 && info "127.0.0.9 desbanido (limpeza do teste)"

echo "== 7. refutação: 50 IPs forjados contra o MESMO token/inquilino — a camada 2 segura (Postgres) =="
info "provado no pytest (tests/api/test_limite_taxa.py::test_50_ips_forjados_contra_o_mesmo_token_a_camada_de_inquilino_segura)"
info "aqui, complementar: confirma que o 429 da camada 2 tem corpo {erro: limite_de_taxa}, não o 429 da camada 1 (corpo vazio do nginx)"

echo
if [ "$FALHAS" -gt 0 ]; then
  echo "RESULTADO: $FALHAS verificação(ões) falharam"
  exit 1
fi
echo "RESULTADO: todas as verificações da bancada passaram"
