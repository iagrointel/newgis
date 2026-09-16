-- 20260916T0135f2a_auth_sessao_suspenso_sem_apagar: sessão viva de inquilino suspenso devolvia 401
-- sessao_expirada em vez de 503 inquilino_suspenso.
--
-- Defeito reproduzido pelo gerente: tests/api/test_login.py::test_usuario_desabilitado_e_inquilino_suspenso
-- (comentário do próprio teste, linha ~131: "suspensão do inquilino demo2 pelo superadmin: login 503,
-- sessão viva 503 (item L0-07-f: mesma mensagem do operador, nada apagado); reativação restaura"). Passo a
-- passo reproduzido fora do pytest (app/db.py, plat.auth_login/plat.auth_sessao chamados direto): login novo
-- contra o inquilino suspenso já devolvia 503 corretamente (app/auth/rotas_login.py checa `r["ativo_tenant"]`
-- explicitamente); só a SESSÃO JÁ ABERTA (cookie válido, criada antes da suspensão) não.
--
-- Causa: `plat.auth_sessao()` (003_identidade_acesso.sql) exige `s.t_ativo` na MESMA condição que checa
-- expiração/ociosidade e usuário ativo — `IF NOT (... AND s.u_ativo AND s.t_ativo) THEN RETURN; END IF;` —
-- e um RETURN sem linha é indistinguível de sessão inexistente: `resolver()` (app/auth/sessao.py) só sabe
-- fazer `if r is None: raise ErroAPI(401, "sessao_expirada", ...)`. Suspender o inquilino não apaga a linha
-- de `plat.sessao` (comentário do teste "nada apagado" está certo sobre o banco), mas o SINAL de "existe mas
-- o inquilino está suspenso" se perdia dentro da função — o Python nunca tinha como saber que era o caso 503
-- e não o 401 genérico.
--
-- Correção: `t.ativo` sai da condição de RETURN vazio (que continua barrando sessão expirada/ociosa/usuário
-- inativo — usuário inativo tem sessões apagadas por outro caminho ao ser desabilitado, então isso não muda
-- nenhum teste existente) e passa a vir como coluna `tenant_ativo` na linha devolvida. `resolver()` decide:
-- linha ausente = 401 sessao_expirada (sem mudança); linha presente com tenant_ativo = false = 503
-- inquilino_suspenso, sem tocar a sessão (ela continua viva; reativar o inquilino volta a autenticar com o
-- mesmo cookie, exatamente como o teste espera na última linha).
--
-- Teste de refutação: tests/api/test_login.py::test_usuario_desabilitado_e_inquilino_suspenso (marca serial).

-- adiciona coluna tenant_ativo ao TABLE de retorno: Postgres recusa CREATE OR REPLACE quando o tipo de
-- retorno muda, então a função sai e entra de novo (mesmo nome/assinatura de parâmetros, sem quebrar
-- nenhum GRANT — não há REVOKE específico dela nas migrações anteriores; o padrão de SECURITY DEFINER
-- desta família fica igual).
DROP FUNCTION IF EXISTS plat.auth_sessao(text, numeric);

CREATE FUNCTION plat.auth_sessao(p_hash text, p_ociosa_horas numeric)
RETURNS TABLE(usuario_id integer, tenant_id integer, login text, perfil text, nome text, email text,
              tenant_slug text, tenant_nome text, superadmin boolean, config jsonb, privilegios text[],
              trocar_senha boolean, totp_ativo boolean, origem text, papel_id integer,
              expira_em timestamp with time zone, ultimo_uso timestamp with time zone,
              criado_em timestamp with time zone, ip text, ociosa_horas numeric, tenant_ativo boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'plat', 'public' AS $$
DECLARE s record; ociosa numeric;
BEGIN
  SELECT x.token_hash, x.expira_em, x.ultimo_uso, x.criado_em, x.ip, u.ativo AS u_ativo, t.ativo AS t_ativo,
         t.config AS cfg
  INTO s
  FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
  WHERE x.token_hash = p_hash;
  IF NOT FOUND THEN RETURN; END IF;
  -- GREATEST/LEAST ignoram NULL no PostgreSQL: sem a chave no config, vale p_ociosa_horas (padrão da plataforma
  -- ou o valor de teste em dev); com a chave, corta para 1–24 h
  ociosa := CASE WHEN nullif(s.cfg #>> '{auth,sessao_ociosa_horas}', '') IS NULL THEN p_ociosa_horas
                 ELSE least(greatest((s.cfg #>> '{auth,sessao_ociosa_horas}')::numeric, 1), 24) END;
  -- t_ativo (inquilino suspenso) NÃO entra aqui: sessão suspensa continua "encontrada", só com
  -- tenant_ativo=false na linha devolvida — quem decide 401 x 503 é o chamador (app/auth/sessao.py::resolver).
  IF NOT (s.expira_em > now() AND coalesce(s.ultimo_uso, s.criado_em) >= now() - make_interval(secs => ociosa * 3600)
          AND s.u_ativo) THEN
    RETURN;
  END IF;
  IF s.t_ativo THEN
    UPDATE plat.sessao SET ultimo_uso = now() WHERE token_hash = p_hash;
  END IF;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, t.slug, t.nome, u.superadmin, t.config,
           plat.privilegios_de(u.id), u.trocar_senha, u.totp_ativo, u.origem, u.papel_id, x.expira_em, x.ultimo_uso,
           x.criado_em, x.ip, ociosa, t.ativo
    FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
    WHERE x.token_hash = p_hash;
END $$;
