'use strict';

process.on('uncaughtException', (err) => {
  console.error('[FATAL UNCAUGHT EXCEPTION]', err && err.stack ? err.stack : err);
});

process.on('unhandledRejection', (reason) => {
  console.error('[FATAL UNHANDLED REJECTION]', reason && reason.stack ? reason.stack : reason);
});

require('dotenv').config();
const express = require('express');
const path    = require('path');
const { executeQuery, executeQueries } = require('./config/db');

const app = express();
const PORT = parseInt(process.env.DATABRICKS_APP_PORT || process.env.PORT || '8080', 10);
const IS_PRODUCTION = process.env.NODE_ENV === 'production' || process.env.DATABRICKS_APP_PORT !== undefined;

app.set('trust proxy', 1);

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ─── Healthcheck Endpoints para Container Proxy Databricks Apps ───────────────
app.get('/health', (_req, res) => res.status(200).send('OK'));
app.get('/_health', (_req, res) => res.status(200).send('OK'));

// ─── Helper para Extração do Access Token OBO (x-forwarded-access-token) ──────
function getUserToken(req) {
  return req.headers['x-forwarded-access-token'] || 
         (req.headers['authorization'] ? req.headers['authorization'].replace(/^Bearer\s+/i, '') : null);
}

// ─── Helper de Autenticação Estrita (Aceita APENAS x-forwarded-email com @) ───────
function getAuthenticatedUser(req) {
  // Aqui eu exijo unicamente o header oficial de e-mail do Databricks Apps, sem fallbacks silenciosos
  let email = req.headers['x-forwarded-email'];

  if (!email && !IS_PRODUCTION) {
    email = 'ana.ferraz@grupobimbo.com'; // Fallback apenas para desenvolvimento local
  }

  if (!email) {
    return null;
  }

  const cleanEmail = String(email).toLowerCase().trim();
  if (!cleanEmail.includes('@')) {
    return null;
  }

  return cleanEmail;
}

// Middleware de Autenticação SSO & Validação RLS Estrita
async function requireSSO(req, res, next) {
  const email = getAuthenticatedUser(req);
  const userToken = getUserToken(req);

  if (!email) {
    const rawHeader = req.headers['x-forwarded-email'] || 'NULO';
    console.error(`[Auth 403] Acesso negado: Header x-forwarded-email ausente ou inválido (recebido: '${rawHeader}')`);
    if (req.path.startsWith('/api/')) {
      return res.status(403).json({ error: `Acesso Negado: Header x-forwarded-email ausente ou inválido ('${rawHeader}')` });
    }
    return res.status(403).send(`<h1>403 - Acesso Negado</h1><p>Header SSO de e-mail ausente ou inválido ('${rawHeader}').</p>`);
  }

  // Validação de RLS: Se o e-mail não possui nenhum distribuidor cadastrado no mapping -> HTTP 403 Explícito
  const mappedCnpjs = await getUserMappedCnpjs(email, userToken);
  if (!mappedCnpjs || mappedCnpjs.length === 0) {
    console.error(`[Auth 403] Usuário '${email}' autenticado via SSO mas sem vínculo em tbl_dim_distributor_user_mapping`);
    if (req.path.startsWith('/api/')) {
      return res.status(403).json({ error: `Acesso Negado: Usuário '${email}' não possui nenhum distribuidor cadastrado no mapping` });
    }
    return res.status(403).send(`<h1>403 - Acesso Negado</h1><p>Usuário '${email}' não possui nenhum distribuidor associado.</p>`);
  }

  req.userEmail = email;
  req.userMappedCnpjs = mappedCnpjs;
  return next();
}

// ─── Helper para Construção de Cláusulas WHERE por Tabela (Previne Colunas Inexistentes) ──
function buildWhereConditionsTable(queryParams, dateCol, extraCondition = null, options = {}) {
  const { semana, mes, ano, dia, sku, pedido, produto } = queryParams;
  const { hasOrders = false, hasCalendarJoin = false, ignoreMes = false } = options;
  const conditions = [];
  const params = {};

  if (extraCondition) {
    if (typeof extraCondition === 'string') {
      conditions.push(extraCondition);
    } else if (extraCondition.condition) {
      conditions.push(extraCondition.condition);
      if (extraCondition.params) {
        Object.assign(params, extraCondition.params);
      }
    }
  }

  if (ano) {
    const arr = ano.split(',').map(a => a.trim()).filter(Boolean);
    if (arr.length > 0) {
      const yearExpr = hasCalendarJoin ? `CAST(c.ANO as STRING)` : `CAST(YEAR(f.${dateCol}) as STRING)`;
      conditions.push(`${yearExpr} IN (${arr.map((_, i) => `:ano_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`ano_${i}`] = val; });
    }
  }

  if (mes && !ignoreMes) {
    const arr = mes.split(',').map(m => parseInt(m.trim(), 10)).filter(v => !isNaN(v));
    if (arr.length > 0) {
      const mesExpr = hasCalendarJoin ? `c.MES` : `MONTH(f.${dateCol})`;
      conditions.push(`${mesExpr} IN (${arr.map((_, i) => `:mes_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`mes_${i}`] = val; });
    }
  }

  if (semana && hasCalendarJoin) {
    const arr = semana.split(',').map(s => parseInt(s.trim(), 10)).filter(v => !isNaN(v));
    if (arr.length > 0) {
      conditions.push(`c.SEMANA IN (${arr.map((_, i) => `:sem_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`sem_${i}`] = val; });
    }
  }

  if (dia && hasCalendarJoin) {
    const arr = dia.split(',').map(d => d.trim()).filter(Boolean);
    if (arr.length > 0) {
      conditions.push(`c.DIA IN (${arr.map((_, i) => `:dia_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`dia_${i}`] = val; });
    }
  }

  if (produto) {
    const arr = produto.split(',').map(p => p.trim()).filter(Boolean);
    if (arr.length > 0) {
      conditions.push(`f.DESC_PROD_BQ IN (${arr.map((_, i) => `:prod_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`prod_${i}`] = val; });
    }
  }

  if (sku) {
    const arr = sku.split(',').map(s => (s.includes(' - ') ? s.split(' - ')[0].trim() : s.trim())).filter(Boolean);
    if (arr.length > 0) {
      conditions.push(`(f.SKU_PROD_BQ IN (${arr.map((_, i) => `:sku_${i}`).join(', ')}) OR CAST(f.SKU_PROD_DIST as STRING) IN (${arr.map((_, i) => `:sku_${i}`).join(', ')}))`);
      arr.forEach((val, i) => { params[`sku_${i}`] = val; });
    }
  }

  if (pedido && hasOrders) {
    const arr = pedido.split(',').map(p => p.trim()).filter(Boolean);
    if (arr.length > 0) {
      conditions.push(`CAST(f.NUMERO_PEDIDO as STRING) IN (${arr.map((_, i) => `:ped_${i}`).join(', ')})`);
      arr.forEach((val, i) => { params[`ped_${i}`] = val; });
    }
  }

  return { where: conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '', params };
}

// ─── Arquivos Estáticos ──────────────────────────────────────────────────────
app.use('/css', express.static(path.join(__dirname, 'css')));
app.use('/js',  express.static(path.join(__dirname, 'js')));
app.use('/img', express.static(path.join(__dirname, 'img')));

app.get('/', requireSSO, (_req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/index.html', requireSSO, (_req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/login.html', (_req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/dashboard.html', requireSSO, (_req, res) => {
  res.sendFile(path.join(__dirname, 'dashboard.html'));
});

// ─── Helpers de Perfil & RLS (Row Level Security) ────────────────────────────
const ADMIN_EMAILS = ['bruno.fellipe@grupobimbo.com', 'ana.ferraz@grupobimbo.com', 'daniel.moreira@grupobimbo.com'];

function isUserAdmin(email) {
  return ADMIN_EMAILS.includes((email || '').toLowerCase().trim());
}

async function getUserMappedCnpjs(email, userToken) {
  try {
    const query = `
      SELECT distributor_cnpj_code
      FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping
      WHERE LOWER(user_email) = LOWER(:email)
        AND is_active = TRUE
        AND (valid_to_date IS NULL OR valid_to_date >= CURRENT_DATE())
    `;
    const rows = await executeQuery(query, { email: email }, userToken, 'mapping_cnpjs');
    return (rows || []).map(r => String(r.distributor_cnpj_code || r.DISTRIBUTOR_CNPJ_CODE || '').trim()).filter(Boolean);
  } catch (err) {
    console.error(`[RLS Helper Fail] Erro ao buscar CNPJs para ${email}:`, err.message);
    return [];
  }
}

// ─── GET /api/me (Identidade & Mapeamento de Distribuidor) ────────────────────
app.get('/api/me', requireSSO, async (req, res) => {
  const email = getAuthenticatedUser(req);
  const userToken = getUserToken(req);

  const isAdmin = isUserAdmin(email);
  const perfil = isAdmin ? 'admin' : 'distribuidor';

  let distribuidores = [];
  let descDistribuidor = null;
  try {
    const query = `
      SELECT 
        distributor_cnpj_code,
        distributor_name
      FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping
      WHERE LOWER(user_email) = LOWER(:email)
        AND is_active = TRUE
        AND (valid_to_date IS NULL OR valid_to_date >= CURRENT_DATE())
    `;
    const rows = await executeQuery(query, { email: email }, userToken, 'mapping_user');
    distribuidores = (rows || []).map(r => ({
      cnpj: r.distributor_cnpj_code || r.DISTRIBUTOR_CNPJ_CODE,
      nome: r.distributor_name || r.DISTRIBUTOR_NAME
    }));
    if (distribuidores.length > 0 && distribuidores[0].nome) {
      descDistribuidor = distribuidores[0].nome;
    }
  } catch (err) {
    console.error(`[API /me Fail] Erro ao buscar mapeamento para ${email}:`, err.message);
  }

  res.json({
    email,
    admin: isAdmin,
    perfil,
    distribuidores,
    desc_distribuidor: descDistribuidor
  });
});

// ─── GET /_diag/headers (Inspeção dos Headers do Proxy Databricks Apps) ─────────
app.get('/_diag/headers', (req, res) => {
  // Aqui eu só quero enxergar o que o proxy do Databricks Apps está realmente injetando
  const forwardedHeaders = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (key.toLowerCase().startsWith('x-forwarded') || key.toLowerCase().startsWith('x-databricks')) {
      if (key.toLowerCase().includes('token') || key.toLowerCase().includes('authorization')) {
        forwardedHeaders[key] = value ? `${value.substring(0, 10)}...` : null;
      } else {
        forwardedHeaders[key] = value;
      }
    }
  }
  res.json(forwardedHeaders);
});

// ─── API Diagnóstico ─────────────────────────────────────────────────────────
app.get('/api/diagnostico', requireSSO, async (req, res) => {
  const email = getAuthenticatedUser(req);
  const userToken = getUserToken(req);
  const tokenPrefix = userToken ? `${userToken.substring(0, 10)}...` : 'NULO';

  try {
    const sessionUserResult = await executeQuery('SELECT session_user() as su', {}, userToken, 'diag_session');
    res.json({
      session_user: sessionUserResult,
      email_sso: email,
      token_presente: !!userToken,
      token_prefix: tokenPrefix
    });
  } catch (err) {
    res.status(500).json({ error: err.message, token_presente: !!userToken, token_prefix: tokenPrefix });
  }
});

// ─── GET /api/kpi (Execução OBO usando userToken com Guarda de RLS Estrita) ───────
const kpiCache = new Map();
const CACHE_TTL_MS = 60 * 1000;

app.get('/api/kpi', requireSSO, async (req, res) => {
  const email = req.userEmail || getAuthenticatedUser(req);
  const userToken = getUserToken(req);

  const cacheKey = `kpi_${req.originalUrl}_${userToken ? userToken.slice(-10) : email}`;
  if (kpiCache.has(cacheKey)) {
    const cached = kpiCache.get(cacheKey);
    if (Date.now() - cached.time < CACHE_TTL_MS) {
      return res.json(cached.data);
    }
  }

  // RLS Enforcement: A coluna f.CNPJ_DISTRIBUIDOR fica 100% intocada para preservar o Data Skipping do Delta Engine
  const mappedCnpjs = req.userMappedCnpjs || await getUserMappedCnpjs(email, userToken);
  const rlsObj = { condition: '', params: {} };
  if (!mappedCnpjs || mappedCnpjs.length === 0) {
    rlsObj.condition = '1 = 0';
  } else {
    const placeholders = mappedCnpjs.map((cnpj, idx) => {
      const paramKey = `rls_cnpj_${idx}`;
      rlsObj.params[paramKey] = String(cnpj).trim();
      return `:${paramKey}`;
    });
    rlsObj.condition = `f.CNPJ_DISTRIBUIDOR IN (${placeholders.join(', ')})`;
  }

  const { semana, mes, ano, dia, sku, pedido } = req.query;
  const catalog  = process.env.DATABRICKS_CATALOG || 'cat_dnabb_dv';
  const schema   = process.env.DATABRICKS_SCHEMA  || 'opebrapodis_sz';
  const hasCalJoin = !!(semana || dia);

  const whereSellIn  = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DT_SELL_IN', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin, ignoreMes: true });
  const whereSellOut = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DATA_SELL_OUT', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin, ignoreMes: true });
  const whereStock   = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DATA_ESTOQUE', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin });
  const wherePositiv = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DATA_SELL_OUT', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin });
  const wherePositivMonthly = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DATA_SELL_OUT', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin, ignoreMes: true });
  const whereOrders  = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido }, 'DATA_PREVISAO_ENTREGA', rlsObj, { hasOrders: true, hasCalendarJoin: hasCalJoin });
  const whereTracking = buildWhereConditionsTable({ semana, mes, ano, dia, sku, pedido, produto }, 'DATA_SELL_OUT', rlsObj, { hasOrders: false, hasCalendarJoin: hasCalJoin });

  let results = { sellin: [], sellout: [], stock: [], positiv: [], orders: [], order_metrics: [], positiv_monthly: [], tracking: [] };
  let errorMsg = null;

  try {
    const sellinQuery = `
      SELECT 
        SUM(f.VL_SELL_IN)      as total_vl_sell_in,
        SUM(f.VL_FORECAST)     as total_vl_forecast,
        SUM(f.QTDE_SELL_IN)    as total_qty_sell_in,
        SUM(f.QTDE_FORECAST)   as total_qty_forecast,
        MONTH(f.DT_SELL_IN)    as MES,
        YEAR(f.DT_SELL_IN)     as ANO
      FROM ${catalog}.${schema}.tbl_factdy_sellin f
      ${whereSellIn.where}
      GROUP BY MONTH(f.DT_SELL_IN), YEAR(f.DT_SELL_IN)
      ORDER BY ANO, MES
    `;

    const selloutQuery = `
      WITH meta_agg AS (
        SELECT 
          MONTH(f.DATA_SELL_OUT) as MES,
          YEAR(f.DATA_SELL_OUT)  as ANO,
          SUM(f.VL_META)         as total_vl_meta
        FROM ${catalog}.${schema}.tbl_factdy_sellout f
        ${whereSellOut.where}
        AND (f.SKU_PROD_BQ = 'META' OR f.VL_SELL_OUT = 0)
        AND f.VL_META IS NOT NULL AND f.VL_META > 0
        GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
      ),
      realizado_agg AS (
        SELECT 
          MONTH(f.DATA_SELL_OUT)         as MES,
          YEAR(f.DATA_SELL_OUT)          as ANO,
          SUM(f.VL_SELL_OUT)            as total_vl_sell_out,
          SUM(f.QTDE_UNITARIO_SELL_OUT) as total_qty_sell_out,
          SUM(f.QTDE_DUZIA_SELL_OUT)    as total_qty_dz_sell_out
        FROM ${catalog}.${schema}.tbl_factdy_sellout f
        ${whereSellOut.where}
        AND (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)
        GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
      )
      SELECT 
        COALESCE(r.ANO, m.ANO)                 as ANO,
        COALESCE(r.MES, m.MES)                 as MES,
        COALESCE(r.total_vl_sell_out, 0)       as total_vl_sell_out,
        COALESCE(r.total_qty_sell_out, 0)      as total_qty_sell_out,
        COALESCE(r.total_qty_dz_sell_out, 0)   as total_qty_dz_sell_out,
        COALESCE(m.total_vl_meta, 0)           as total_vl_meta
      FROM realizado_agg r
      FULL OUTER JOIN meta_agg m ON r.ANO = m.ANO AND r.MES = m.MES
      ORDER BY ANO, MES
    `;

    const stockQuery = `
      WITH latest_stock AS (
        SELECT 
          f.CNPJ_DISTRIBUIDOR,
          COALESCE(f.DESC_DISTRIBUIDOR, 'Distribuidor') as desc_distribuidor,
          COALESCE(f.SKU_PROD_BQ, f.SKU_PROD_DIST)    as sku_prod_dist,
          COALESCE(f.DESC_PROD_BQ, f.DESC_PROD_ARQUIVO_DIST, 'Produto') as DESC_PROD_ARQUIVO_DIST,
          f.DATA_ESTOQUE,
          f.QTDE_ESTOQUE,
          f.MEDIA_VENDA,
          f.GIRO_ESTOQUE,
          ROW_NUMBER() OVER (
            PARTITION BY f.CNPJ_DISTRIBUIDOR, COALESCE(f.SKU_PROD_BQ, f.SKU_PROD_DIST) 
            ORDER BY f.DATA_ESTOQUE DESC
          ) as rn
        FROM ${catalog}.${schema}.tbl_factdy_stock f
        ${whereStock.where}
      )
      SELECT 
        DATA_ESTOQUE,
        ROUND(COALESCE(GIRO_ESTOQUE, CASE WHEN MEDIA_VENDA > 0 THEN QTDE_ESTOQUE / MEDIA_VENDA ELSE 0 END), 0) as dias_estoque,
        desc_distribuidor,
        'SP' as uf_cliente,
        sku_prod_dist,
        DESC_PROD_ARQUIVO_DIST,
        GIRO_ESTOQUE as giro_estoque,
        MEDIA_VENDA as media_venda,
        QTDE_ESTOQUE as total_qty_stock,
        MONTH(DATA_ESTOQUE) as MES,
        YEAR(DATA_ESTOQUE) as ANO
      FROM latest_stock
      WHERE rn = 1
      ORDER BY dias_estoque DESC
      LIMIT 200
    `;

    const wherePositivMeta = wherePositiv.where 
      ? `${wherePositiv.where} AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)` 
      : `WHERE (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)`;

    const positivQuery = `
      SELECT 
        CASE 
          WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BRIOCHE%' THEN 'Linha Gourmet & Brioche'
          WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HB%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HAMB%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%TRADICIONAL%' THEN 'Pães de Hambúrguer Tradicionais'
          WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HOT DOG%' THEN 'Pães de Hot Dog'
          WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%AUSTRALIANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ARTESANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%NUVEM%' THEN 'Pães Especiais & Artesanais'
          WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ANA MARIA%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BOLO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BISNAG%' THEN 'Bolos, Snacks & Doces'
          ELSE 'Outros Produtos'
        END as grupo_produto_desc_bq,
        COALESCE(f.DESC_CLIENTE, f.DESC_DISTRIBUIDOR, 'Cliente') as razao_social_cliente,
        COALESCE(f.CNPJ_CLIENTE, f.CNPJ_DISTRIBUIDOR) as cnpj_cliente,
        COUNT(DISTINCT f.DATA_SELL_OUT) as compras_mes_atual,
        COUNT(DISTINCT f.DATA_SELL_OUT) as total_compras_periodo,
        SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) as volume_duzia,
        SUM(COALESCE(f.VL_SELL_OUT, 0)) as valor_total,
        'POSITIVADO' as status,
        TRUE as isPositivado
      FROM ${catalog}.${schema}.tbl_factdy_sellout f
      ${wherePositivMeta}
      GROUP BY 1, 2, 3
      ORDER BY grupo_produto_desc_bq, volume_duzia DESC
      LIMIT 500
    `;

    const orderQuery = `
      SELECT 
        CAST(f.NUMERO_PEDIDO as STRING)                      as numero_pedido,
        f.DATA_EMISSAO_PEDIDO                                as data_emissao_pedido,
        f.DATA_PREVISAO_ENTREGA                             as data_previsao_entrega,
        f.DATA_ENTREGA                                      as data_entrega,
        COALESCE(f.DESC_STATUS_PEDIDO, 'ENTREGUE')           as desc_status_pedido,
        f.SKU_PROD_BQ                                        as sku,
        COALESCE(f.DESC_PROD_BQ, 'Produto')                  as produto,
        SUM(COALESCE(f.QTDE_PEDIDO_UN, 0))                   as qtde_pedido_un,
        SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_UN, 0))          as qtde_pedido_atendido_un,
        SUM(COALESCE(f.QTDE_PEDIDO_CX, 0))                   as qtde_pedido_cx,
        SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_CX, 0))          as qtde_pedido_atendido_cx,
        SUM(COALESCE(f.VL_PEDIDO_BRUTO, 0))                  as vl_pedido_bruto,
        SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_BRUTO, 0))         as vl_pedido_atendido_bruto,
        SUM(COALESCE(f.VL_PEDIDO_LIQUIDO, f.VL_PEDIDO_BRUTO * 0.8, 0)) as vl_pedido_liquido,
        SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0)) as vl_pedido_atendido_liquido,
        SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0)) as vl_pedido_aberto_liquido
      FROM ${catalog}.${schema}.tbl_factdy_order f
      ${whereOrders.where}
      GROUP BY
        f.NUMERO_PEDIDO, f.DATA_EMISSAO_PEDIDO, f.DATA_PREVISAO_ENTREGA, f.DATA_ENTREGA,
        f.DESC_STATUS_PEDIDO, f.SKU_PROD_BQ, f.DESC_PROD_BQ
      ORDER BY f.DATA_EMISSAO_PEDIDO DESC
      LIMIT 200
    `;

    const orderMetricsQuery = `
      SELECT 
        SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0)) as total_vl_invoiced,
        SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0))       as total_vl_open,
        SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0) + 
            COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0))       as total_vl_total,
        SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_BRUTO, 0))                                     as total_vl_invoiced_bruto,
        SUM(COALESCE(f.VL_PEDIDO_ABERTO_BRUTO, 0))                                       as total_vl_open_bruto,
        SUM(COALESCE(f.VL_PEDIDO_BRUTO, 0))                                              as total_vl_total_bruto,
        SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_DZ, 0))                                      as total_qty_invoiced_dz,
        SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_DZ, 0))                                        as total_qty_open_dz,
        SUM(COALESCE(f.QTDE_PEDIDO_DZ, 0))                                               as total_qty_total_dz,
        SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_UN, 0))                                      as total_qty_invoiced_un,
        SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_UN, 0))                                        as total_qty_open_un,
        SUM(COALESCE(f.QTDE_PEDIDO_UN, 0))                                               as total_qty_total_un
      FROM ${catalog}.${schema}.tbl_factdy_order f
      ${whereOrders.where}
    `;

    const wPmRealizado = wherePositivMonthly.where 
      ? `${wherePositivMonthly.where} AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)`
      : `WHERE (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)`;

    const wPmMeta = wherePositivMonthly.where
      ? `${wherePositivMonthly.where} AND (f.SKU_PROD_BQ = 'META_POSITIVACAO' OR (f.POSITIVACAO_META IS NOT NULL AND f.POSITIVACAO_META > 0))`
      : `WHERE (f.SKU_PROD_BQ = 'META_POSITIVACAO' OR (f.POSITIVACAO_META IS NOT NULL AND f.POSITIVACAO_META > 0))`;

    const positivMonthlyQuery = `
      WITH base_ano AS (
        SELECT 
          YEAR(f.DATA_SELL_OUT) as ANO,
          COUNT(DISTINCT f.CNPJ_CLIENTE) as total_base_clientes
        FROM ${catalog}.${schema}.tbl_factdy_sellout f
        ${wPmRealizado}
        GROUP BY YEAR(f.DATA_SELL_OUT)
      ),
      realizado_mes AS (
        SELECT
          MONTH(f.DATA_SELL_OUT) as MES,
          YEAR(f.DATA_SELL_OUT)  as ANO,
          COUNT(DISTINCT f.CNPJ_CLIENTE) as clientes_positivados
        FROM ${catalog}.${schema}.tbl_factdy_sellout f
        ${wPmRealizado}
        GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
      ),
      meta_mes AS (
        SELECT
          MONTH(f.DATA_SELL_OUT) as MES,
          YEAR(f.DATA_SELL_OUT)  as ANO,
          CAST(COALESCE(SUM(f.POSITIVACAO_META), 0) AS INT) as meta_positivacao
        FROM ${catalog}.${schema}.tbl_factdy_sellout f
        ${wPmMeta}
        GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
      )
      SELECT
        COALESCE(r.MES, m.MES) as MES,
        COALESCE(r.ANO, m.ANO) as ANO,
        COALESCE(r.clientes_positivados, 0) as clientes_positivados,
        COALESCE(m.meta_positivacao, 0)     as meta_positivacao,
        COALESCE(b.total_base_clientes, 0)  as total_base_clientes,
        ROUND((COALESCE(r.clientes_positivados, 0) * 100.0) / NULLIF(b.total_base_clientes, 0), 1) as pct_positivacao
      FROM realizado_mes r
      FULL OUTER JOIN meta_mes m ON r.ANO = m.ANO AND r.MES = m.MES
      LEFT JOIN base_ano b ON COALESCE(r.ANO, m.ANO) = b.ANO
      ORDER BY ANO, MES
    `;

    const trackingQuery = `
      SELECT 
        CAST(f.DATA_SELL_OUT as STRING) as data_sell_out,
        DAY(f.DATA_SELL_OUT)            as dia,
        MONTH(f.DATA_SELL_OUT)          as mes,
        YEAR(f.DATA_SELL_OUT)           as ano,
        COUNT(DISTINCT f.CNPJ_CLIENTE)  as total_clientes,
        SUM(COALESCE(f.VL_SELL_OUT, 0)) as total_vl_sell_out,
        SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) as total_qty_dz_sell_out
      FROM ${catalog}.${schema}.tbl_factdy_sellout f
      ${whereTracking.where}
      AND (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)
      GROUP BY f.DATA_SELL_OUT
      ORDER BY f.DATA_SELL_OUT ASC
    `;

    const queriesMap = {
      sellin:          { queryText: sellinQuery,          params: whereSellIn.params },
      sellout:         { queryText: selloutQuery,         params: whereSellOut.params },
      stock:           { queryText: stockQuery,           params: whereStock.params },
      positiv:         { queryText: positivQuery,         params: wherePositiv.params },
      orders:          { queryText: orderQuery,           params: whereOrders.params },
      order_metrics:   { queryText: orderMetricsQuery,   params: whereOrders.params },
      positiv_monthly: { queryText: positivMonthlyQuery, params: wherePositivMonthly.params },
      tracking:        { queryText: trackingQuery,        params: whereTracking.params }
    };

    results = await executeQueries(queriesMap, userToken);
  } catch (err) {
    console.error('[API KPI Fail]', err.message);
    errorMsg = err.message;
  }

  const payload = {
    usuario: email,
    dados:   results,
    error:   errorMsg
  };

  if (!errorMsg) {
    kpiCache.set(cacheKey, { time: Date.now(), data: payload });
  }

  res.json(payload);
});

// ─── GET /api/filtros (Cache + Execução em Sessão Única Concorrente) ─────────────
let filtersCache = null;
let filtersCacheTime = 0;
const FILTERS_TTL_MS = 10 * 60 * 1000; // Cache de 10 minutos

app.get('/api/filtros', requireSSO, async (req, res) => {
  const userToken = getUserToken(req);
  const calTable = process.env.DATABRICKS_CALENDAR_TABLE || 'cat_dnabb_dv.bracatlg_cz.calendario_bimbo';
  const catalog  = process.env.DATABRICKS_CATALOG || 'cat_dnabb_dv';
  const schema   = process.env.DATABRICKS_SCHEMA  || 'opebrapodis_sz';

  if (filtersCache && (Date.now() - filtersCacheTime < FILTERS_TTL_MS)) {
    return res.json(filtersCache);
  }

  let anos = [], semanas = [], meses = [], dias = [], produtos = [], skus = [], pedidos = [];
  let erro = null;

  try {
    const filterQueriesMap = {
      anos:    { queryText: `SELECT DISTINCT ANO FROM ${calTable} WHERE CAST(ANO as int) >= 2025 ORDER BY ANO` },
      meses:   { queryText: `SELECT DISTINCT MES FROM ${calTable} WHERE CAST(ANO as int) >= 2025 ORDER BY CAST(MES as int)` },
      semanas: { queryText: `SELECT DISTINCT SEMANA FROM ${calTable} WHERE CAST(ANO as int) >= 2025 ORDER BY CAST(SEMANA as int)` },
      dias:    { queryText: `SELECT DISTINCT DIA FROM ${calTable} WHERE CAST(ANO as int) >= 2025 ORDER BY CAST(DIA as int)` },
      prods:   { queryText: `SELECT DISTINCT DESC_PROD_BQ as desc_produto FROM ${catalog}.${schema}.tbl_factdy_order WHERE DESC_PROD_BQ IS NOT NULL AND TRIM(DESC_PROD_BQ) != '' ORDER BY desc_produto LIMIT 1000` },
      skus:    { queryText: `SELECT DISTINCT SKU_DISTRIB as sku FROM cat_dnabb_dv.bracatlg_lz.produtos_distribuidores WHERE SKU_DISTRIB IS NOT NULL AND TRIM(SKU_DISTRIB) != '' ORDER BY sku LIMIT 1000` },
      pedidos: { queryText: `SELECT DISTINCT CAST(f.NUMERO_PEDIDO as STRING) as numero_pedido FROM ${catalog}.${schema}.tbl_factdy_order f WHERE f.NUMERO_PEDIDO IS NOT NULL ORDER BY numero_pedido LIMIT 500` }
    };

    const resultsMap = await executeQueries(filterQueriesMap, userToken);

    anos     = (resultsMap.anos    || []).map(r => String(r.ANO || r.ano || '')).filter(Boolean);
    meses    = (resultsMap.meses   || []).map(r => String(r.MES || r.mes || '')).filter(Boolean);
    semanas  = (resultsMap.semanas || []).map(r => String(r.SEMANA || r.semana || '')).filter(Boolean);
    dias     = (resultsMap.dias    || []).map(r => String(r.DIA || r.dia || '')).filter(Boolean);
    produtos = (resultsMap.prods   || []).map(r => String(r.desc_produto || '')).filter(Boolean);
    skus     = (resultsMap.skus    || []).map(r => String(r.sku || '')).filter(Boolean);
    pedidos  = (resultsMap.pedidos || []).map(r => String(r.numero_pedido || '')).filter(Boolean);
  } catch (err) {
    console.error('Erro ao buscar opções de filtro:', err.message);
    erro = err.message;
  }

  const payload = { anos, semanas, meses, dias, produtos, skus, pedidos, erro };
  if (!erro) {
    filtersCache = payload;
    filtersCacheTime = Date.now();
  }

  res.json(payload);
});

const HOST = process.env.HOST || '0.0.0.0';

app.listen(PORT, HOST, () => {
  console.log(`[Server] Portal de Distribuidores rodando na porta ${PORT} em ${HOST} (Prod: ${IS_PRODUCTION})`);
});
