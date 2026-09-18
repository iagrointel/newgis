-- L2-03-e-anexos: o varredor de órfãos zera `chave`/`mini_chave` depois de remover o objeto do Garage
-- (fica o sha256 para auditoria; a próxima passada não revarre o que já foi físico). A coluna `chave`
-- nasceu NOT NULL na 20260907T1035 — sem este DROP o `plat.feicao_anexo_chave_limpar` da migração
-- 20260918T1700 não consegue limpar. Linha viva NUNCA tem chave nula: quem escreve é o INSERT do envio
-- (sempre com chave) e a limpeza só toca linha com apagado_em marcado (o próprio WHERE da função).
ALTER TABLE plat.feicao_anexo ALTER COLUMN chave DROP NOT NULL;
