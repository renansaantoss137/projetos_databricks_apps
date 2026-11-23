#!/bin/bash
# =============================================================================
# SCRIPT DE TESTE AUTOMATIZADO / COMANDOS CURL PARA TESTE DE RLS E SESSÃO
# =============================================================================

SERVER_URL="http://localhost:8080"
COOKIE_FILE="cookie_session.txt"

echo "====================================================================="
echo "TESTE 1: Tentativa de Acesso ao /api/kpi sem sessão (Esperado: HTTP 401)"
echo "====================================================================="
curl -i -X GET "${SERVER_URL}/api/kpi"
echo -e "\n"

echo "====================================================================="
echo "TESTE 2: Login com E-mail Fora do Domínio (Esperado: HTTP 400)"
echo "====================================================================="
curl -i -X POST "${SERVER_URL}/api/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "usuario@gmail.com"}'
echo -e "\n"

echo "====================================================================="
echo "TESTE 3: Login com E-mail Sem Cadastro / Não Mapeado (Esperado: HTTP 403)"
echo "====================================================================="
curl -i -X POST "${SERVER_URL}/api/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "naocadastrado@grupobimbo.com"}'
echo -e "\n"

echo "====================================================================="
echo "TESTE 4: Login Válido com E-mail de Distribuidor (Esperado: HTTP 200 + Cookie)"
echo "====================================================================="
curl -i -X POST "${SERVER_URL}/api/login" \
  -H "Content-Type: application/json" \
  -c "${COOKIE_FILE}" \
  -d '{"email": "lucas.silva01@grupobimbo.com"}'
echo -e "\n"

echo "====================================================================="
echo "TESTE 5: Consulta ao /api/me usando a Sessão Ativa (Esperado: Filiais do Usuário)"
echo "====================================================================="
curl -i -X GET "${SERVER_URL}/api/me" \
  -b "${COOKIE_FILE}"
echo -e "\n"

echo "====================================================================="
echo "TESTE 6: Consulta ao /api/kpi com Filtro RLS Aplicado (Esperado: Apenas CNPJ 46780581000122)"
echo "====================================================================="
curl -i -X GET "${SERVER_URL}/api/kpi" \
  -b "${COOKIE_FILE}"
echo -e "\n"

echo "====================================================================="
echo "TESTE 7: Logout e Destruição da Sessão"
echo "====================================================================="
curl -i -X POST "${SERVER_URL}/api/logout" \
  -b "${COOKIE_FILE}"
rm -f "${COOKIE_FILE}"
echo -e "\n"
