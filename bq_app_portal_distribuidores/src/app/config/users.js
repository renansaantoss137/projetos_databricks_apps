'use strict';

/**
 * Mapeamento simples de E-mail x Senha (sem RLS/restrições de dados por usuário).
 * O filtro de segurança Row Filter é aplicado externamente pelo Databricks.
 */
const USERS = [
  { email: 'bruno.fellipe@grupobimbo.com',     senha: 'Bruno@Bimbo2026!', perfil: 'distribuidor', desc_distribuidor: 'DISTRIB DE PROD ALIMENTICIOS DISBOM LTDA', cnpj_distribuidor: '00121362000130' },
  { email: 'ana.ferraz@grupobimbo.com',        senha: 'Ana@Bimbo2026!',   perfil: 'distribuidor', desc_distribuidor: 'BUY FOOD SERVICE DISTRIBUIDORA DE ALIMENTOS LTDA', cnpj_distribuidor: '55794744000117' },
  { email: 'matheus.quiarati@grupobimbo.com',  senha: 'Matheus@Bimbo2026!', perfil: 'distribuidor', desc_distribuidor: 'FOCATTO', cnpj_distribuidor: '46780581000122' },
  { email: 'lucas.silva01@grupobimbo.com',      senha: 'Lucas@Bimbo2026!', perfil: 'distribuidor', desc_distribuidor: 'ALPI DISTRIBUIDORA DE PRODUTOS ALIMENTICIOS LTDA', cnpj_distribuidor: '46780581000122' },
  { email: 'shirlei.cheles@grupobimbo.com',     senha: 'Shirlei@Bimbo2026!', perfil: 'distribuidor', desc_distribuidor: 'CASTRO DISTRIBUIDORA', cnpj_distribuidor: '24378897000150' },
  { email: 'pedro.madureira@grupobimbo.com',    senha: 'Pedro@Bimbo2026!',  perfil: 'distribuidor', desc_distribuidor: 'GARDEN FOODS', cnpj_distribuidor: '02152891000127' },
  { email: 'admin@grupobimbo.com',             senha: 'Admin@123',        perfil: 'admin', desc_distribuidor: null, cnpj_distribuidor: null },
  { email: 'admin.qsr@grupobimbo.com',         senha: 'Admin@123',        perfil: 'admin', desc_distribuidor: null, cnpj_distribuidor: null }
];

async function findUser(email, senha) {
  if (!email || !senha) return null;
  const emailLower = email.toLowerCase().trim();

  const match = USERS.find(
    u => u.email.toLowerCase() === emailLower && u.senha === senha
  );

  if (match) {
    return {
      email: match.email,
      perfil: match.perfil,
      desc_distribuidor: match.desc_distribuidor,
      cnpj_distribuidor: match.cnpj_distribuidor
    };
  }

  return null;
}

module.exports = { USERS, findUser };
