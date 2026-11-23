-- =============================================================================
-- SCRIPT SQL DE CONFIGURAÇÃO DE SEGURANÇA RLS E AUDITORIA NA CAMADA DE APLICAÇÃO
-- Catálogo: cat_dnabb_dv | Schema: seguranca
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS cat_dnabb_dv.seguranca;

-- 1. Tabela de Mapeamento de Usuários e Filiais / CNPJs (RLS na Aplicação)
CREATE TABLE IF NOT EXISTS cat_dnabb_dv.seguranca.rls_usuarios (
  email STRING NOT NULL,
  filial STRING NOT NULL,
  ativo BOOLEAN DEFAULT true,
  dt_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
USING DELTA;

-- 2. Tabela de Log de Auditoria de Acessos e Consultas
CREATE TABLE IF NOT EXISTS cat_dnabb_dv.seguranca.rls_auditoria (
  email STRING,
  acao STRING,
  detalhe STRING,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
USING DELTA;

-- 3. Carga Inicial de Teste / DML Seed
-- Observação: filial = '*' concede Acesso Total (Perfil Admin)
INSERT OVERWRITE cat_dnabb_dv.seguranca.rls_usuarios (email, filial, ativo)
VALUES
  ('bruno.fellipe@grupobimbo.com', '*', true),
  ('ana.ferraz@grupobimbo.com', '*', true),
  ('daniel.moreira@grupobimbo.com', '*', true),
  ('lucas.silva01@grupobimbo.com', '46780581000122', true),
  ('shirlei.cheles@grupobimbo.com', '24378897000150', true),
  ('pedro.madureira@grupobimbo.com', '02152891000127', true),
  ('matheus.quiarati@grupobimbo.com', '04902760000145', true);
