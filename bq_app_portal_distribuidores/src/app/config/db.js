'use strict';

const { DBSQLClient } = require('@databricks/sql');

/**
 * Executes a set of queries using a SINGLE DBSQLClient connection & session per request.
 * Attempts On-Behalf-Of User Authorization (x-forwarded-access-token) first.
 * If OBO token encounters a 403 authorization error from SQL Warehouse, falls back to Service Principal token.
 * 
 * @param {Object<string, {queryText: string, params: Object}>} queriesMap - Object mapping query names to SQL definitions.
 * @param {string|null} userToken - User access token from x-forwarded-access-token header.
 * @returns {Promise<Object<string, Array<Object>>>} - Object mapping query names to result row arrays.
 */
async function executeQueries(queriesMap, userToken = null) {
  const rawHost = process.env.MY_DATABRICKS_HOST || process.env.DATABRICKS_HOST || 'adb-8674310331778219.19.azuredatabricks.net';
  const host = rawHost.replace(/^https?:\/\//i, '').replace(/\/$/, '');
  const path = process.env.MY_DATABRICKS_PATH || process.env.DATABRICKS_PATH || process.env.DATABRICKS_HTTP_PATH || '/sql/1.0/warehouses/f4a2e26b8410f1e3';
  const servicePrincipalToken = process.env.MY_DATABRICKS_TOKEN || process.env.DATABRICKS_TOKEN || '';

  let token = userToken || servicePrincipalToken;
  let tokenPrefix = token ? `${token.substring(0, 10)}...` : 'NULO';

  console.log(`[DB] Connecting to SQL Warehouse (${host}) with token prefix: ${tokenPrefix} (OBO: ${!!userToken})`);

  // Log de Diagnóstico JWT (sub, scope, aud, exp)
  if (userToken && userToken.includes('.')) {
    try {
      const parts = userToken.split('.');
      if (parts.length >= 2) {
        const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf8'));
        console.log('[Token Debug]', {
          sub: payload.sub,
          scope: payload.scope || payload.scp,
          aud: payload.aud,
          exp: payload.exp ? new Date(payload.exp * 1000).toISOString() : undefined
        });
      }
    } catch (e) {
      console.log('[Token Debug] Não foi possível decodificar o token JWT');
    }
  }

  let client = new DBSQLClient();
  const results = {};
  let session = null;

  const isAuthError = (err) => {
    if (!err || !err.message) return false;
    const msg = err.message.toLowerCase();
    return msg.includes('403') || msg.includes('401') || msg.includes('bad http status code') || msg.includes('unauthorized') || msg.includes('permission_denied');
  };

  try {
    // Tentativa inicial de conexão (OBO ou Service Principal)
    try {
      await client.connect({ host, path, token });
      session = await client.openSession();
    } catch (connError) {
      if (isAuthError(connError) && token !== servicePrincipalToken) {
        console.warn(`[DB Auth Fallback] Token OBO rejeitado pelo Databricks (${connError.message}). Alternando para o Service Principal.`);
        token = servicePrincipalToken;
        tokenPrefix = `${token.substring(0, 10)}...`;
        client = new DBSQLClient();
        await client.connect({ host, path, token });
        session = await client.openSession();
      } else {
        throw connError;
      }
    }

    const entries = Object.entries(queriesMap);
    await Promise.all(entries.map(async ([queryName, { queryText, params }]) => {
      try {
        const options = { runAsync: true };
        if (params && Object.keys(params).length > 0) {
          options.namedParameters = params;
        }

        const queryOperation = await session.executeStatement(queryText, options);
        await queryOperation.status();
        const rows = await queryOperation.fetchAll();
        await queryOperation.close();

        results[queryName] = rows || [];
      } catch (err) {
        console.error(`[DB Query Error] Query '${queryName}' falhou. Token Prefix: ${tokenPrefix}. Erro: ${err.message}`, {
          queryName: queryName,
          tokenPrefix: tokenPrefix,
          statusCode: err.status || err.statusCode,
          detail: err.response || err.message
        });
        results[queryName] = [];
      }
    }));

    return results;
  } catch (error) {
    console.error(`[DB Connection Error] Falha ao conectar/abrir sessão no Databricks. Token Prefix: ${tokenPrefix}. Erro: ${error.message}`, {
      tokenPrefix: tokenPrefix,
      statusCode: error.status || error.statusCode,
      detail: error.response || error.message
    });
    throw error;
  } finally {
    if (session) {
      try { await session.close(); } catch (e) {}
    }
    try {
      await client.close();
    } catch (e) {}
  }
}

/**
 * Executes a single SQL query (wraps executeQueries).
 * @param {string} queryText - The SQL query string.
 * @param {Object} [params] - Parameters to pass to the query (named parameters).
 * @param {string|null} [userToken] - Per-request user access token.
 * @param {string} [queryName] - Query identifier for logging.
 * @returns {Promise<Array<Object>>} - The rows returned by the query.
 */
async function executeQuery(queryText, params = {}, userToken = null, queryName = 'query') {
  const map = { [queryName]: { queryText, params } };
  const res = await executeQueries(map, userToken);
  return res[queryName] || [];
}

module.exports = { executeQuery, executeQueries };
