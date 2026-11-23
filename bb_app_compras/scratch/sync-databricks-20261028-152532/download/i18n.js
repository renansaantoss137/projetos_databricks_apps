/**
 * PORTAL COMPRAS — Internationalization Module (i18n)
 * Supports: PT (default), EN, ES
 *
 * Include BEFORE other scripts in <head>.
 * Static HTML is translated via selector-based text matching.
 * Dynamic JS content: use t('Portuguese text') to get translated text.
 * Months: use getMonths() instead of hardcoded MONTHS array.
 * Format: use fmtI18n(value, type) for localized formatting.
 * Language change: listen for 'langChange' event on document.
 */

/* ═══════════════════════════════════════════════════════════════════
   STATE
   ═══════════════════════════════════════════════════════════════════ */
var _currentLang = localStorage.getItem('portalCompras_lang') || 'pt';

/* ═══════════════════════════════════════════════════════════════════
   TRANSLATION DICTIONARY
   Key = Portuguese text, Value = { en, es }
   ═══════════════════════════════════════════════════════════════════ */
var _DICT = {
  // ── Navigation ──
  'Performance':                  { en: 'Performance',        es: 'Rendimiento' },
  'Gastos':                       { en: 'Expenses',           es: 'Gastos' },
  'Ordens':                       { en: 'Orders',             es: 'Órdenes' },
  'Comercial':                    { en: 'Commercial',         es: 'Comercial' },
  'Governança':                   { en: 'Governance',         es: 'Gobernanza' },
  'Relatórios':                   { en: 'Reports',            es: 'Informes' },
  'Cadastros':                    { en: 'Master Data',        es: 'Catálogos' },
  'Guia':                         { en: 'Guide',              es: 'Guía' },
  'PORTAL COMPRAS':               { en: 'PROCUREMENT PORTAL', es: 'PORTAL COMPRAS' },
  'Portal Compras':               { en: 'Procurement Portal', es: 'Portal Compras' },
  'Guia do Usuário':              { en: 'User Guide',         es: 'Guía del Usuario' },
  'Cadastro Planilhas':           { en: 'Master Data Sheets', es: 'Registro Planillas' },
  // ── Breadcrumbs ──
  'PORTAL COMPRAS / Módulo 01':   { en: 'PROCUREMENT PORTAL / Module 01', es: 'PORTAL COMPRAS / Módulo 01' },
  'PORTAL COMPRAS / Módulo 02':   { en: 'PROCUREMENT PORTAL / Module 02', es: 'PORTAL COMPRAS / Módulo 02' },
  'PORTAL COMPRAS / Módulo 03':   { en: 'PROCUREMENT PORTAL / Module 03', es: 'PORTAL COMPRAS / Módulo 03' },
  'PORTAL COMPRAS / Módulo 04':   { en: 'PROCUREMENT PORTAL / Module 04', es: 'PORTAL COMPRAS / Módulo 04' },
  'PORTAL COMPRAS / Módulo 05':   { en: 'PROCUREMENT PORTAL / Module 05', es: 'PORTAL COMPRAS / Módulo 05' },
  'PORTAL COMPRAS / Módulo 06':   { en: 'PROCUREMENT PORTAL / Module 06', es: 'PORTAL COMPRAS / Módulo 06' },
  // ── Page titles ──
  'Performance de Compras':       { en: 'Purchasing Performance',   es: 'Rendimiento de Compras' },
  'Análise de Gastos':            { en: 'Spend Analysis',           es: 'Análisis de Gastos' },
  'Pedidos e Prazos':             { en: 'Orders & Deadlines',       es: 'Pedidos y Plazos' },
  'Condições Comerciais':         { en: 'Commercial Conditions',    es: 'Condiciones Comerciales' },
  'Gestão de Ordens':             { en: 'Order Management',         es: 'Gestión de Órdenes' },
  // ── Document titles ──
  'Performance de Compras | PORTAL COMPRAS': { en: 'Purchasing Performance | PROCUREMENT PORTAL', es: 'Rendimiento de Compras | PORTAL COMPRAS' },
  'Spend & Oportunidades | PORTAL COMPRAS':  { en: 'Spend & Opportunities | PROCUREMENT PORTAL',  es: 'Gasto y Oportunidades | PORTAL COMPRAS' },
  'Pedidos e Prazos | PORTAL COMPRAS':       { en: 'Orders & Deadlines | PROCUREMENT PORTAL',     es: 'Pedidos y Plazos | PORTAL COMPRAS' },
  'Condições Comerciais | PORTAL COMPRAS':   { en: 'Commercial Conditions | PROCUREMENT PORTAL',  es: 'Condiciones Comerciales | PORTAL COMPRAS' },
  'Governança | PORTAL COMPRAS':             { en: 'Governance | PROCUREMENT PORTAL',              es: 'Gobernanza | PORTAL COMPRAS' },
  'Relatórios | PORTAL COMPRAS':             { en: 'Reports | PROCUREMENT PORTAL',                 es: 'Informes | PORTAL COMPRAS' },
  'Guia do Usuário | PORTAL COMPRAS':        { en: 'User Guide | PROCUREMENT PORTAL',              es: 'Guía del Usuario | PORTAL COMPRAS' },
  'PORTAL COMPRAS | Bimbo Brasil':           { en: 'PROCUREMENT PORTAL | Bimbo Brasil',            es: 'PORTAL COMPRAS | Bimbo Brasil' },
  'Gestão de Ordens | PORTAL COMPRAS':       { en: 'Order Management | PROCUREMENT PORTAL',        es: 'Gestión de Órdenes | PORTAL COMPRAS' },
  'Temos {qty} pedidos em aberto com mais de {days} dias de atraso, somando {val} entre eles.': { en: 'We have {qty} open orders with more than {days} days of delay, totaling {val}.', es: 'Tenemos {qty} pedidos abiertos con más de {days} días de retraso, sumando {val}.' },
  'Nenhum pedido em aberto com mais de 90 dias de atraso.': { en: 'No open orders with more than 90 days of delay.', es: 'Ningún pedido abierto con más de 90 días de retraso.' },
  'Atraso (dias)':                           { en: 'Delay (days)',       es: 'Retraso (días)' },
  'No prazo':                                { en: 'On time',            es: 'A tiempo' },
  'Tema do Sistema':                         { en: 'System Theme',       es: 'Tema del Sistema' },
  'Tema Claro':                              { en: 'Light Theme',        es: 'Tema Claro' },
  'Tema Escuro':                             { en: 'Dark Theme',         es: 'Tema Oscuro' },
  // ── Filter labels ──
  'Empresa':             { en: 'Company',            es: 'Empresa' },
  'Ano':                 { en: 'Year',               es: 'Año' },
  'Mês':                 { en: 'Month',              es: 'Mes' },
  'Dia':                 { en: 'Day',                es: 'Día' },
  'Direto/Indireto':     { en: 'Direct/Indirect',    es: 'Directo/Indirecto' },
  'Fornecedor':          { en: 'Supplier',            es: 'Proveedor' },
  'Centralizado':        { en: 'Centralized',         es: 'Centralizado' },
  'Unidade':             { en: 'Plant',               es: 'Unidad' },
  'Descrição Item':      { en: 'Item Description',    es: 'Descripción Ítem' },
  'NF com OC?':          { en: 'Invoice w/ PO?',      es: 'NF con OC?' },
  'Status Pagamento':    { en: 'Payment Status',      es: 'Estado de Pago' },
  'Tipo NF':             { en: 'Invoice Type',         es: 'Tipo NF' },
  'Forn. Especial':      { en: 'Special Supplier',     es: 'Prov. Especial' },
  'Forn. Negociável':    { en: 'Negotiable Supplier',  es: 'Prov. Negociable' },
  // ── Filter controls ──
  'Aplicar':             { en: 'Apply',               es: 'Aplicar' },
  'Atualizando...':      { en: 'Updating...',         es: 'Actualizando...' },
  'Atualizado!':         { en: 'Updated!',            es: '¡Actualizado!' },
  'Atualizando dados com os filtros aplicados...': { en: 'Updating data with applied filters...', es: 'Actualizando datos con los filtros aplicados...' },
  'Limpar':              { en: 'Clear',               es: 'Limpiar' },
  'Mais Filtros':        { en: 'More Filters',        es: 'Más Filtros' },
  'Todos':               { en: 'All',                 es: 'Todos' },
  'Nenhum':              { en: 'None',                es: 'Ninguno' },
  'Pesquisar...':        { en: 'Search...',           es: 'Buscar...' },
  'Selecionar tudo':     { en: 'Select all',          es: 'Seleccionar todo' },
  'selecionados':        { en: 'selected',            es: 'seleccionados' },
  'Alternar tema':       { en: 'Toggle theme',        es: 'Cambiar tema' },
  // ── Home page modules ──
  'Visão consolidada: gastos, savings, lead time, centralização e prazo de pagamento.':            { en: 'Consolidated view: expenses, savings, lead time, centralization and payment terms.',       es: 'Visión consolidada: gastos, ahorros, lead time, centralización y plazo de pago.' },
  'KPIs com variação temporal':                { en: 'KPIs with time variation',       es: 'KPIs con variación temporal' },
  'Spend YoY + Savings mensais':               { en: 'YoY Spend + Monthly Savings',    es: 'Gasto YoY + Ahorros mensuales' },
  'Itens que requerem atenção':                { en: 'Items requiring attention',       es: 'Ítems que requieren atención' },
  'Abrir módulo':                              { en: 'Open module',                    es: 'Abrir módulo' },
  'Onde o gasto está concentrado: por item, fornecedor, planta, categoria e classificação ABC.': { en: 'Where spending is concentrated: by item, supplier, plant, category and ABC classification.', es: 'Donde está concentrado el gasto: por ítem, proveedor, planta, categoría y clasificación ABC.' },
  'Top itens e fornecedores':                  { en: 'Top items and suppliers',         es: 'Top ítems y proveedores' },
  'ABC dinâmico recalculado por filtro':        { en: 'Dynamic ABC recalculated per filter', es: 'ABC dinámico recalculado por filtro' },
  'Tabela de centralização':                   { en: 'Centralization table',            es: 'Tabla de centralización' },
  'Exposição de ordens abertas, atrasos e planejado vs. realizado.': { en: 'Open orders, delays and planned vs. actual.', es: 'Exposición de órdenes abiertas, atrasos y planificado vs. realizado.' },
  'Valor aberto e OCs atrasadas':              { en: 'Open value and late POs',         es: 'Valor abierto y OCs retrasadas' },
  'Atraso por fornecedor':                     { en: 'Delay by supplier',               es: 'Atraso por proveedor' },
  'Tabela de OCs abertas':                     { en: 'Open POs table',                  es: 'Tabla de OCs abiertas' },
  'Evolução do prazo de pagamento, savings e oportunidades de renegociação.': { en: 'Payment term evolution, savings and renegotiation opportunities.', es: 'Evolución del plazo de pago, ahorros y oportunidades de renegociación.' },
  'Prazo médio ponderado':                     { en: 'Weighted average term',           es: 'Plazo medio ponderado' },
  'Distribuição por faixa':                    { en: 'Distribution by range',           es: 'Distribución por rango' },
  'Tabela de renegociação':                    { en: 'Renegotiation table',             es: 'Tabla de renegociación' },
  'Exceções de processo: OC pós-fatura, emergenciais, sem OC e descentralizadas.': { en: 'Process exceptions: post-invoice PO, emergency, no PO and decentralized.', es: 'Excepciones de proceso: OC post-factura, emergenciales, sin OC y descentralizadas.' },
  'Impacto por tipo de desvio':                { en: 'Impact by deviation type',        es: 'Impacto por tipo de desvío' },
  'Concentração por comprador':                { en: 'Concentration by buyer',          es: 'Concentración por comprador' },
  'Tabela de exceções com filtro local':        { en: 'Exceptions table with local filter', es: 'Tabla de excepciones con filtro local' },
  'Exploração detalhada: requisições, ordens de compra e notas fiscais com paginação e export.': { en: 'Detailed exploration: requisitions, purchase orders and invoices with pagination and export.', es: 'Exploración detallada: requisiciones, órdenes de compra y facturas con paginación y exportación.' },
  'Seletor de dataset':                        { en: 'Dataset selector',                es: 'Selector de dataset' },
  'Busca, paginação e ordenação':              { en: 'Search, pagination and sorting',  es: 'Búsqueda, paginación y ordenación' },
  'Export CSV / Excel':                        { en: 'Export CSV / Excel',              es: 'Exportar CSV / Excel' },
  // ── Performance KPIs ──
  'Spend Líquido':          { en: 'Net Spend',              es: 'Gasto Neto' },
  '% Centralização':        { en: '% Centralization',       es: '% Centralización' },
  'Prazo Médio Pagamento':  { en: 'Avg Payment Term',       es: 'Plazo Medio de Pago' },
  'Descontos':              { en: 'Discounts',              es: 'Descuentos' },
  'Aumentos':               { en: 'Increases',              es: 'Aumentos' },
  'Meta ≥ 80%':             { en: 'Target ≥ 80%',           es: 'Meta ≥ 80%' },
  'Meta ≥ 60 dias':         { en: 'Target ≥ 60 days',       es: 'Meta ≥ 60 días' },
  'Negativo = economia · Positivo = aumento de preço': { en: 'Negative = savings · Positive = price increase', es: 'Negativo = economía · Positivo = aumento de precio' },
  // ── Performance charts ──
  'Spend Líquido vs. Ano Anterior':            { en: 'Net Spend vs. Previous Year',                  es: 'Gasto Neto vs. Año Anterior' },
  'Desconto Financeiro Obtido Acumulado':       { en: 'Accumulated Financial Discount',                es: 'Descuento Financiero Obtenido Acumulado' },
  'Spend Líquido':                             { en: 'Net Spend',                                    es: 'Gasto Neto' },
  'Spend Líq. Ano Anterior':                   { en: 'Net Spend Prev. Year',                         es: 'Gasto Neto Año Anterior' },
  'O que exige atenção agora':                 { en: 'What requires attention now',                   es: 'Lo que requiere atención ahora' },
  'Alerta de Aumento de Preço — Oportunidade de Renegociação': { en: 'Price Increase Alert — Renegotiation Opportunity', es: 'Alerta de Aumento de Precio — Oportunidad de Renegociación' },
  'Carregando alertas...':                     { en: 'Loading alerts...',                             es: 'Cargando alertas...' },
  // ── Lead time ──
  'O maior tempo do processo está entre Requisição e Pedido': { en: 'The longest process time is between Requisition and Order', es: 'El mayor tiempo del proceso está entre Requisición y Pedido' },
  'Requisições':        { en: 'Requisitions',      es: 'Requisiciones' },
  'Aprovadas':          { en: 'Approved',           es: 'Aprobadas' },
  'Pedidos':            { en: 'Orders',             es: 'Pedidos' },
  'Emitidos':           { en: 'Issued',             es: 'Emitidos' },
  'Aprovados':          { en: 'Approved',           es: 'Aprobados' },
  'NF':                 { en: 'Invoice',            es: 'NF' },
  'requisições':        { en: 'requisitions',       es: 'requisiciones' },
  'emitidos':           { en: 'issued',             es: 'emitidos' },
  'aprovados':          { en: 'approved',           es: 'aprobados' },
  'notas fiscais':      { en: 'invoices',           es: 'facturas' },
  // ── Units & format ──
  'dias':               { en: 'days',               es: 'días' },
  'Mi':                 { en: 'M',                  es: 'M' },
  'mil':                { en: 'K',                  es: 'mil' },
  // ── Dynamic comparison labels ──
  'vs mesmo período mês anterior':  { en: 'vs same period prev. month',  es: 'vs mismo período mes anterior' },
  'vs mesmo período ano anterior':  { en: 'vs same period prev. year',   es: 'vs mismo período año anterior' },
  'acima':              { en: 'above',              es: 'por encima' },
  'abaixo':             { en: 'below',              es: 'por debajo' },
  'do Spend':           { en: 'of Spend',           es: 'del Gasto' },
  'pp vs meta':         { en: 'pp vs target',       es: 'pp vs meta' },
  'dias vs meta':       { en: 'days vs target',     es: 'días vs meta' },
  // ── Spend page ──
  'Spend por item do pedido':      { en: 'Spend by order item',        es: 'Gasto por ítem del pedido' },
  'Spend por fornecedor':          { en: 'Spend by supplier',          es: 'Gasto por proveedor' },
  'Análise ABC do Spend Líquido':  { en: 'ABC Analysis of Net Spend',  es: 'Análisis ABC del Gasto Neto' },
  'Valor':                         { en: 'Value',                      es: 'Valor' },
  'Spend (R$)':                    { en: 'Spend (R$)',                 es: 'Gasto (R$)' },
  '% var. vs. período anterior':   { en: '% var. vs. prev. period',    es: '% var. vs. período anterior' },
  '% do spend total':              { en: '% of total spend',           es: '% del gasto total' },
  'Itens/fornecedores A representam a maior oportunidade de gestão e negociação.': { en: 'A items/suppliers represent the greatest management and negotiation opportunity.', es: 'Ítems/proveedores A representan la mayor oportunidad de gestión y negociación.' },
  'Spend por Planta':              { en: 'Spend by Plant',             es: 'Gasto por Planta' },
  'Onde a operação concentra volume': { en: 'Where operations concentrate volume', es: 'Donde la operación concentra volumen' },
  'Evolução Spend (12 meses)':     { en: 'Spend Evolution (12 months)', es: 'Evolución Gasto (12 meses)' },
  'Tendência mensal do Spend Líquido': { en: 'Monthly net spend trend', es: 'Tendencia mensual del Gasto Neto' },
  'Centralização por Grupo de Compras': { en: 'Centralization by Purchasing Group', es: 'Centralización por Grupo de Compras' },
  'Categoria':                     { en: 'Category',                   es: 'Categoría' },
  'Tipo':                          { en: 'Type',                       es: 'Tipo' },
  // ── Orders page ──
  'Valor em OCs Abertas':          { en: 'Open PO Value',              es: 'Valor en OCs Abiertas' },
  'OCs em Atraso':                 { en: 'Late POs',                   es: 'OCs en Atraso' },
  'Dias Médios de Atraso':         { en: 'Average Days Late',          es: 'Días Promedio de Atraso' },
  'OCs no Prazo':                  { en: 'On-time POs',                es: 'OCs a Tiempo' },
  'Previsto vs Realizado':         { en: 'Planned vs Actual',          es: 'Previsto vs Realizado' },
  'Entregas por mês (quantidades previstas vs recebidas)': { en: 'Deliveries by month (planned vs received quantities)', es: 'Entregas por mes (cantidades previstas vs recibidas)' },
  'Previsto':                      { en: 'Planned',                    es: 'Previsto' },
  'Realizado':                     { en: 'Actual',                     es: 'Realizado' },
  'Atraso por Fornecedor (Top 10)':{ en: 'Delay by Supplier (Top 10)', es: 'Atraso por Proveedor (Top 10)' },
  'Fornecedores com maior valor em atraso': { en: 'Suppliers with highest overdue value', es: 'Proveedores con mayor valor en atraso' },
  'Dias Méd.':                     { en: 'Avg Days',                   es: 'Días Prom.' },
  'Faixas de Atraso':              { en: 'Delay Ranges',               es: 'Rangos de Atraso' },
  'No prazo':                      { en: 'On time',                    es: 'A tiempo' },
  '1–7 dias':                      { en: '1–7 days',                   es: '1–7 días' },
  '8–15 dias':                     { en: '8–15 days',                  es: '8–15 días' },
  '16–30 dias':                    { en: '16–30 days',                 es: '16–30 días' },
  '31–60 dias':                    { en: '31–60 days',                 es: '31–60 días' },
  '> 60 dias':                     { en: '> 60 days',                  es: '> 60 días' },
  'OCs Abertas':                   { en: 'Open POs',                   es: 'OCs Abiertas' },
  'Tabela com todas as OCs em aberto': { en: 'Table with all open POs', es: 'Tabla con todas las OCs abiertas' },
  // ── Commercial page ──
  'Evolução do Prazo Médio de Pagamento': { en: 'Average Payment Term Evolution', es: 'Evolución del Plazo Medio de Pago' },
  'Prazo médio ponderado por valor de NF': { en: 'Weighted average term by invoice value', es: 'Plazo medio ponderado por valor de NF' },
  'Distribuição por Faixa de Prazo':       { en: 'Distribution by Term Range',    es: 'Distribución por Rango de Plazo' },
  'Concentração do valor por faixa':       { en: 'Value concentration by range',  es: 'Concentración del valor por rango' },
  'Top Fornecedores por Prazo':            { en: 'Top Suppliers by Term',         es: 'Top Proveedores por Plazo' },
  'Maiores prazos médios ponderados':      { en: 'Highest weighted average terms', es: 'Mayores plazos medios ponderados' },
  'Savings Acumulado':                     { en: 'Accumulated Savings',           es: 'Ahorros Acumulados' },
  'Economia obtida no período selecionado': { en: 'Savings obtained in selected period', es: 'Economía obtenida en el período seleccionado' },
  'Oportunidades de Renegociação':         { en: 'Renegotiation Opportunities',   es: 'Oportunidades de Renegociación' },
  'Fornecedores com maior potencial de melhoria de prazo': { en: 'Suppliers with highest term improvement potential', es: 'Proveedores con mayor potencial de mejora de plazo' },
  // ── Governance page ──
  'Visão Geral':                   { en: 'Overview',                   es: 'Visión General' },
  'OC Pós-Fatura':                 { en: 'Post-Invoice PO',            es: 'OC Post-Factura' },
  'Emergencial':                   { en: 'Emergency',                  es: 'Emergencial' },
  'Sem OC':                        { en: 'No PO',                      es: 'Sin OC' },
  'Descentralizada':               { en: 'Decentralized',              es: 'Descentralizada' },
  'Total de Exceções':             { en: 'Total Exceptions',           es: 'Total de Excepciones' },
  'Valor Impactado':               { en: 'Impacted Value',             es: 'Valor Impactado' },
  '% sobre Spend':                 { en: '% of Spend',                 es: '% sobre Gasto' },
  'NFs Pós-Fatura':                { en: 'Post-Invoice Invoices',      es: 'NFs Post-Factura' },
  'NFs Emergenciais':              { en: 'Emergency Invoices',         es: 'NFs Emergenciales' },
  'Impacto por Tipo de Exceção':   { en: 'Impact by Exception Type',   es: 'Impacto por Tipo de Excepción' },
  'Concentração por Comprador':    { en: 'Concentration by Buyer',     es: 'Concentración por Comprador' },
  'Compradores com maior volume de exceções': { en: 'Buyers with highest exception volume', es: 'Compradores con mayor volumen de excepciones' },
  'Detalhe de Exceções':           { en: 'Exception Details',          es: 'Detalle de Excepciones' },
  'Qtde':                          { en: 'Qty',                        es: 'Cant.' },
  // ── Reports page ──
  'Notas Fiscais & Ordens de Compra': { en: 'Invoices & Purchase Orders',   es: 'Facturas y Órdenes de Compra' },
  'Notas Fiscais':                 { en: 'Invoices',                   es: 'Facturas' },
  'Ordens de Compra':              { en: 'Purchase Orders',            es: 'Órdenes de Compra' },
  'Colunas':                       { en: 'Columns',                    es: 'Columnas' },
  'Comprador Sugerido':            { en: 'Suggested Buyer',            es: 'Comprador Sugerido' },
  'Selecionar Todas':              { en: 'Select All',                 es: 'Seleccionar Todas' },
  'linhas':                        { en: 'rows',                       es: 'líneas' },
  'Exportar XLSX':                 { en: 'Export XLSX',                es: 'Exportar XLSX' },
  'Exportar CSV':                  { en: 'Export CSV',                 es: 'Exportar CSV' },
  'Carregando...':                 { en: 'Loading...',                 es: 'Cargando...' },
  'Nenhum registro encontrado':    { en: 'No records found',           es: 'Ningún registro encontrado' },
  // ── Deviation / Process bar ──
  'Regular':                       { en: 'Regular',                    es: 'Regular' },
  'Pós-Fatura':                    { en: 'Post-Invoice',               es: 'Post-Factura' },
  'Sem OC / Emergencial':          { en: 'No PO / Emergency',          es: 'Sin OC / Emergencial' },
  // ── Guide tabs ──
  'Consulta Rápida':               { en: 'Quick Reference',            es: 'Consulta Rápida' },
  'Documentação Técnica':          { en: 'Technical Documentation',    es: 'Documentación Técnica' },
  'Apresentação':                  { en: 'Presentation',               es: 'Presentación' },
  'Tela cheia':                    { en: 'Fullscreen',                 es: 'Pantalla completa' },
  'Sair':                          { en: 'Exit',                       es: 'Salir' },
  'Próximo':                       { en: 'Next',                       es: 'Siguiente' },
  // ── Orders page KPIs ──
  'Valor em Aberto':               { en: 'Open Value',                 es: 'Valor Abierto' },
  'Pedidos em Aberto':             { en: 'Open Orders',                es: 'Pedidos Abiertos' },
  'Pedidos Atrasados':             { en: 'Late Orders',                es: 'Pedidos Retrasados' },
  'Atraso M\u00e9dio (Dias)':          { en: 'Avg Delay (Days)',           es: 'Atraso Medio (D\u00edas)' },
  'Comprador':                     { en: 'Buyer',                      es: 'Comprador' },
  'Macro Categoria':               { en: 'Macro Category',             es: 'Macro Categoría' },
  'Sub-categoria':                 { en: 'Sub-category',               es: 'Subcategoría' },
  'Sub-Categoria':                 { en: 'Sub-category',               es: 'Subcategoría' },
  'Categoria Item':                { en: 'Item Category',              es: 'Categoría Ítem' },
  'Tipo OC':                       { en: 'PO Type',                    es: 'Tipo OC' },
  'Status Fechamento':             { en: 'Closing Status',             es: 'Estado de Cierre' },
  'Spend Previsto x Realizado por M\u00eas': { en: 'Planned vs Actual Spend by Month', es: 'Gasto Previsto vs Realizado por Mes' },
  'Valor Atrasado por Fornecedor': { en: 'Overdue Value by Supplier',  es: 'Valor Atrasado por Proveedor' },
  'Pedidos em Aberto por Faixa de Atraso': { en: 'Open Orders by Delay Range', es: 'Pedidos Abiertos por Rango de Atraso' },
  'Pedidos em Aberto – Prioritários para Ação': { en: 'Open Orders – Priorities for Action', es: 'Pedidos Abiertos – Prioritarios para Acción' },
  'Conversão de Volume':           { en: 'Volume Conversion',          es: 'Conversión de Volumen' },
  'Conversão de volume vs etapa anterior': { en: 'Volume conversion vs previous stage', es: 'Conversión de volumen vs etapa anterior' },
  'Conversão de volume (quantidade) vs etapa anterior': { en: 'Volume (quantity) conversion vs previous stage', es: 'Conversión de volumen (cantidad) vs etapa anterior' },
  'Conversão de quantidade':       { en: 'Quantity conversion',        es: 'Conversión de cantidad' },
  'Base 100% de volume inicial':   { en: '100% baseline volume',       es: 'Base 100% de volumen inicial' },
  'Retenção da base inicial':      { en: 'Initial baseline retention', es: 'Retención de la base inicial' },
  'Retenção da Base':              { en: 'Baseline Retention',         es: 'Retención de la Base' },
  'Avanço vs etapa anterior':      { en: 'Progress vs previous stage', es: 'Avance vs etapa anterior' },
  'Avanço vs Anterior':            { en: 'Progress vs Previous',       es: 'Avance vs Anterior' },
  'Etapa':                         { en: 'Stage',                      es: 'Etapa' },
  'Volume & Spend':                { en: 'Volume & Spend',             es: 'Volumen y Gasto' },
  'Avanço (Qtd)':                  { en: 'Progress (Qty)',             es: 'Avance (Cant)' },
  'qtd':                           { en: 'qty',                        es: 'cant' },
  'base':                          { en: 'base',                       es: 'base' },
  'Faturamento':                   { en: 'Invoicing',                  es: 'Facturación' },
  'Iniciado':                      { en: 'Initiated',                  es: 'Iniciado' },
  'Totalmente Concluído':          { en: 'Fully Completed',            es: 'Totalmente Concluido' },
  'pedidos faturados':             { en: 'invoiced orders',            es: 'pedidos facturados' },
  'pedidos concluídos':            { en: 'completed orders',           es: 'pedidos concluidos' },
  '1ª NF e Conclusão do Faturamento': { en: '1st Invoice and Invoicing Completion', es: '1ª Factura y Conclusión de Facturación' },
  'Pedidos Parciais':              { en: 'Partial Orders',             es: 'Pedidos Parciales' },
  'Pedidos com faturamento parcial em andamento': { en: 'Orders with partial invoicing in progress', es: 'Pedidos con facturación parcial en curso' },
  'ATENÇÃO':                       { en: 'ATTENTION',                  es: 'ATENCIÓN' },
  'Anterior':                      { en: 'Previous',                   es: 'Anterior' },
  '\u2190 Anterior':                 { en: '\u2190 Previous',             es: '\u2190 Anterior' },
  'Pr\u00f3xima \u2192':                  { en: 'Next \u2192',                 es: 'Siguiente \u2192' },
  'Pr\u00f3xima':                       { en: 'Next',                       es: 'Siguiente' },
  'Spend L\u00edquido por Empresa':     { en: 'Net Spend by Company',       es: 'Gasto Neto por Empresa' },
  'Spend por Categoria':           { en: 'Spend by Category',          es: 'Gasto por Categor\u00eda' },
  'Item':                          { en: 'Item',                       es: '\u00cdtem' },
  // ── Misc ──
  'Bi':                            { en: 'B',                          es: 'B' },
  'Mi':                            { en: 'M',                          es: 'M' },
  'mil':                           { en: 'k',                          es: 'k' },
  'Detalhe':                       { en: 'Detail',                     es: 'Detalle' },
  'XLSX':                          { en: 'XLSX',                       es: 'XLSX' },
  'CSV':                           { en: 'CSV',                        es: 'CSV' },
  'Cross-filter ativo:':           { en: 'Cross-filter active:',       es: 'Cross-filter activo:' },
  'Remover filtro':                { en: 'Remove filter',              es: 'Remover filtro' },
  // ── Relatórios page ──
  'Dados Relatório':              { en: 'Report Data',                es: 'Datos del Informe' },
  'Selecionar Todas':              { en: 'Select All',                 es: 'Seleccionar Todas' },
  'Digite para buscar...':         { en: 'Type to search...',          es: 'Escriba para buscar...' },
  'Digite ao menos 2 caracteres...': { en: 'Type at least 2 characters...', es: 'Escriba al menos 2 caracteres...' },
  'Buscando...':                   { en: 'Searching...',               es: 'Buscando...' },
  'Erro na busca':                 { en: 'Search error',               es: 'Error en la búsqueda' },
  'Carregando dados...':           { en: 'Loading data...',            es: 'Cargando datos...' },
  'registros':                     { en: 'records',                    es: 'registros' },
  'Página':                        { en: 'Page',                       es: 'Página' },
  'de':                            { en: 'of',                         es: 'de' },
  // ── Filters & Table operators ──
  'Contém':                        { en: 'Contains',                   es: 'Contiene' },
  'Igual':                         { en: 'Equals',                     es: 'Igual' },
  'É igual a':                     { en: 'Equals',                     es: 'Es igual a' },
  'Começa com':                    { en: 'Starts with',                es: 'Empieza con' },
  'Termina com':                   { en: 'Ends with',                  es: 'Termina con' },
  'Filtrar Coluna':                { en: 'Filter Column',              es: 'Filtrar Columna' },
  'Busca rápida...':               { en: 'Quick search...',            es: 'Búsqueda rápida...' },
  // ── Governance KPI labels ──
  'OC PÓS-FATURA':                  { en: 'POST-INVOICE PO',               es: 'OC POST-FACTURA' },
  'OCs DESCENTR. >30K':            { en: 'DECENTRAL. POs >30K',            es: 'OCs DESCENTR. >30K' },
  'NOTA SEM OC':                   { en: 'INVOICE W/O PO',                 es: 'NOTA SIN OC' },
  'ACORDOS DE COMPRA >180 DIAS':   { en: 'PURCHASE AGREEMENTS >180 DAYS',  es: 'ACUERDOS DE COMPRA >180 DÍAS' },
  'ACORDO COMPRA >180 DIAS':       { en: 'PURCHASE AGREEMENT >180 DAYS',   es: 'ACUERDO DE COMPRA >180 DÍAS' },
  'OC EMERGENCIAL':                { en: 'EMERGENCY PO',                   es: 'OC EMERGENCIAL' },
  // ── Governance KPI delta phrases ──
  '(qtd) das OCs faturadas':       { en: '(qty) of invoiced POs',          es: '(cant.) de las OCs facturadas' },
  '(qtd) das Notas Fiscais':       { en: '(qty) of Invoices',              es: '(cant.) de las Facturas' },
  '(R$) do Spend Líquido Total':    { en: '(R$) of Total Net Spend',        es: '(R$) del Spend Neto Total' },
  // ── Governance card titles ──
  'Qual Desvio Tem Maior Impacto?':{ en: 'Which Deviation Has the Most Impact?', es: '¿Qué Desviación Tiene Mayor Impacto?' },
  'Quem Concentra os Desvios?':    { en: 'Who Concentrates the Deviations?', es: '¿Quién Concentra las Desviaciones?' },
  'Exceções que Requerem Ação':    { en: 'Exceptions Requiring Action',    es: 'Excepciones que Requieren Acción' },
  // ── Governance exc tab buttons ──
  'Todas':                         { en: 'All',                            es: 'Todas' },
  'OCs Pós-Fatura':               { en: 'Post-Invoice POs',               es: 'OCs Post-Factura' },
  'OC Descentr. >30k':             { en: 'Decentral. PO >30k',             es: 'OC Descentr. >30k' },
  'OCs Sucessivas':                { en: 'Successive POs',                 es: 'OCs Sucesivas' },
  'OC >90 dias':                   { en: 'PO >90 days',                    es: 'OC >90 días' },
  'OCS ABERTAS >90 DIAS':          { en: 'OPEN POs >90 DAYS',              es: 'OCs ABIERTAS >90 DÍAS' },
  '(qtd) das OCs abertas':         { en: '(qty) of open POs',              es: '(cant) de las OCs abiertas' },
  'Acordos de Compra >180 dias':   { en: 'Purchase Agreements >180 days',  es: 'Acuerdos de Compra >180 días' },
  // ── Governance impact/deviation labels (API values) ──
  'OCs abertas >90 dias':          { en: 'Open POs >90 days',              es: 'OCs abiertas >90 días' },
  'OCs pós-fatura':                { en: 'Post-invoice POs',               es: 'OCs post-factura' },
  'OCs Descentr. >30K':            { en: 'Decentral. POs >30K',            es: 'OCs Descentr. >30K' },
  'OCs Sucessivas':                { en: 'Successive POs',                 es: 'OCs Sucesivas' },
  // ── Governance tipo_excecao values (API) ──
  'OCs Pós-Fatura':               { en: 'Post-Invoice POs',               es: 'OCs Post-Factura' },
  'OC Descentr. >30K':             { en: 'Decentral. PO >30K',             es: 'OC Descentr. >30K' },
  'OCs sucessivas':                { en: 'Successive POs',                 es: 'OCs sucesivas' },
  'OCs SUCESSIVAS':                { en: 'SUCCESSIVE POs',                 es: 'OCs SUCESIVAS' },
  'Descentralizada':               { en: 'Decentralized',                  es: 'Descentralizada' },
  'Notas sem OC':                  { en: 'Invoices without PO',            es: 'Notas sin OC' },
  // ── Governance dynamic title templates ──
  '{top} representa {pct}% do valor de exceções de governança': { en: '{top} represents {pct}% of governance exceptions value', es: '{top} representa {pct}% del valor de excepciones de gobernanza' },
  'Três compradores concentram {pct}% do valor de exceções': { en: 'Top 3 buyers concentrate {pct}% of exceptions value', es: 'Tres compradores concentran {pct}% del valor de excepciones' },
  // ── Governance exception table columns ──
  'Tipo Exceção':                  { en: 'Exception Type',                 es: 'Tipo Excepción' },
  'Nº OC':                          { en: 'PO #',                           es: 'Nº OC' },
  'Nº Acordo':                      { en: 'Agreement #',                    es: 'Nº Acuerdo' },
  'Data OC':                       { en: 'PO Date',                        es: 'Fecha OC' },
  'Dias Aberto':                   { en: 'Days Open',                      es: 'Días Abierto' },
  'Início Acordo':                  { en: 'Agreement Start',                es: 'Inicio Acuerdo' },
  'Fim Acordo':                    { en: 'Agreement End',                  es: 'Fin Acuerdo' },
  'Status':                        { en: 'Status',                         es: 'Estado' },
  'Descrição':                     { en: 'Description',                    es: 'Descripción' },
  'Valor Liberado (R$)':           { en: 'Released Value (R$)',             es: 'Valor Liberado (R$)' },
  'Valor do Acordo (R$)':          { en: 'Agreement Value (R$)',            es: 'Valor del Acuerdo (R$)' },
  'Valor (R$)':                    { en: 'Value (R$)',                      es: 'Valor (R$)' },
  'Qtd NFs':                       { en: 'Invoice Qty',                    es: 'Cant. NFs' },
  'Nota Fiscal':                   { en: 'Invoice',                        es: 'Factura' },
  'Data Lançamento':               { en: 'Post Date',                      es: 'Fecha Lanzamiento' },
  'Acordo Compra':                 { en: 'Purchase Agreement',             es: 'Acuerdo Compra' },
  'ACORDO COMPRA':                 { en: 'PURCHASE AGREEMENT',             es: 'ACUERDO COMPRA' },
  'DT Criação NF':                 { en: 'Invoice Creation Date',          es: 'Fecha Creación Factura' },
  'DT CRIAÇÃO NF':                 { en: 'INVOICE CREATION DATE',          es: 'FECHA CREACIÓN FACTURA' },
  'BT Criação NF':                 { en: 'Invoice Creation Date',          es: 'Fecha Creación Factura' },
  'BT CRIAÇÃO NF':                 { en: 'INVOICE CREATION DATE',          es: 'FECHA CREACIÓN FACTURA' },
  'DT Criação OC':                 { en: 'PO Creation Date',               es: 'Fecha Creación OC' },
  'DT CRIAÇÃO OC':                 { en: 'PO CREATION DATE',               es: 'FECHA CREACIÓN OC' },
  'DT Aprov OC':                   { en: 'PO Approval Date',               es: 'Fecha Aprobación OC' },
  'DT APROV OC':                   { en: 'PO APPROVAL DATE',               es: 'FECHA APROBACIÓN OC' },
  'Dias Pós-Fat':                  { en: 'Days Post-Inv',                  es: 'Días Post-Fact' },
  'DIAS PÓS-FAT':                  { en: 'DAYS POST-INV',                  es: 'DÍAS POST-FACT' },
  'Data Criação NF':               { en: 'Invoice Creation Date',          es: 'Fecha Creación Factura' },
  'Data NF Mais Antiga':           { en: 'Oldest Invoice Date',            es: 'Fecha NF Más Antigua' },
  'Data Aprovação':               { en: 'Approval Date',                  es: 'Fecha Aprobación' },
  'Dias Pós-Fatura':               { en: 'Days Post-Invoice',              es: 'Días Post-Factura' },
  'Área':                           { en: 'Area',                           es: 'Área' },
  '% Exceções':                     { en: '% Exceptions',                   es: '% Excepciones' },
  'Quantidade':                    { en: 'Quantity',                       es: 'Cantidad' },
  'Tipo Exceção':                  { en: 'Exception Type',                 es: 'Tipo Excepción' },
  'ID Grupo':                      { en: 'Group ID',                       es: 'ID Grupo' },
  'Compradores':                   { en: 'Buyers',                         es: 'Compradores' },
  'Exceções':                      { en: 'Exceptions',                     es: 'Excepciones' },
  'Data Fatura':                   { en: 'Invoice Date',                   es: 'Fecha Factura' },
  'Cód. Fornecedor':               { en: 'Supplier Code',                  es: 'Cód. Proveedor' },
  'Item Aquisição':                { en: 'Procurement Item',               es: 'Artículo Adquisición' },
  'OCs no Mês':                    { en: 'POs in Month',                   es: 'OCs en el Mes' },
  'Dispersão de Valor':            { en: 'Value Dispersion',               es: 'Dispersión de Valor' },
  'Total Mês (Grupo)':             { en: 'Month Total (Group)',            es: 'Total Mes (Grupo)' },
  'Valor OC':                      { en: 'PO Value',                       es: 'Valor OC' },
  'Valores Próximos (±10%)':       { en: 'Similar Values (±10%)',          es: 'Valores Cercanos (±10%)' },
  'Valores Idênticos':             { en: 'Identical Values',               es: 'Valores Idénticos' },
  'Todas (2+ OCs)':                { en: 'All (2+ POs)',                   es: 'Todas (2+ OCs)' },
  '(R$) do Spend Líquido Total':   { en: '(R$) of Total Net Spend',        es: '(R$) del Gasto Neto Total' },
  '(R$) das OCs do Período':       { en: '(R$) of Period POs',             es: '(R$) de las OCs del Período' },
  '(R$) do Valor Total de OCs':     { en: '(R$) of Total PO Value',         es: '(R$) del Valor Total de OCs' },
  'grupos/casos de OCs sucessivas': { en: 'successive PO groups/cases',    es: 'grupos/casos de OCs sucesivas' },
  'OCs envolvidas':                { en: 'POs involved',                   es: 'OCs involucradas' },
  'OCs':                           { en: 'POs',                            es: 'OCs' },
  // ── Commercial page KPIs & dynamic ──
  '% do Spend Pago < 60 Dias':     { en: '% of Spend Paid < 60 Days',   es: '% del Gasto Pagado < 60 Días' },
  'Desconto Financeiro Obtido':    { en: 'Financial Discount Obtained',  es: 'Descuento Financiero Obtenido' },
  'Desc. médio:':                   { en: 'Avg disc.:',                   es: 'Desc. medio:' },
  'Prazo médio de pagamento no período': { en: 'Average payment term in the period', es: 'Plazo medio de pago en el período' },
  'Meta Prazo ≥ 60 dias':           { en: 'Target Term ≥ 60 days',        es: 'Meta Plazo ≥ 60 días' },
  'Prazo médio acumulado (dias)':   { en: 'Accumulated avg term (days)',  es: 'Plazo medio acumulado (días)' },
  'Prazo mensal (dias)':           { en: 'Monthly term (days)',           es: 'Plazo mensual (días)' },
  'Spend líquido (R$)':             { en: 'Net spend (R$)',               es: 'Gasto neto (R$)' },
  'Demais fornecedores':           { en: 'Other suppliers',              es: 'Demás proveedores' },
  'À vista':                        { en: 'Cash',                         es: 'Al contado' },
  'Até 15 dias':                    { en: 'Up to 15 days',                es: 'Hasta 15 días' },
  '16 a 30 dias':                  { en: '16 to 30 days',                es: '16 a 30 días' },
  '31 a 59 dias':                  { en: '31 to 59 days',                es: '31 a 59 días' },
  'Meta: 60 dias':                 { en: 'Target: 60 days',              es: 'Meta: 60 días' },
  'Acima de 60 dias':              { en: 'Above 60 days',                es: 'Superior a 60 días' },
  '{pct}% do spend está em prazos superiores a 60 dias': { en: '{pct}% of spend is in terms above 60 days', es: '{pct}% del gasto está en plazos superiores a 60 días' },
  'Os {n} principais fornecedores representam {pct}% do spend pago em menos de 60 dias': { en: 'The top {n} suppliers represent {pct}% of spend paid in under 60 days', es: 'Los {n} principales proveedores representan {pct}% del gasto pagado en menos de 60 días' },
  'Pedidos com maior oportunidade de renegociação': { en: 'Orders with highest renegotiation opportunity', es: 'Pedidos con mayor oportunidad de renegociación' },
  'N° Pedido':                      { en: 'Order #',                      es: 'N° Pedido' },
  'Spend líquido':                   { en: 'Net spend',                    es: 'Gasto neto' },
  'Prazo (dias)':                  { en: 'Term (days)',                   es: 'Plazo (días)' },
  'Renegociação':                   { en: 'Renegotiation',                es: 'Renegociación' },
  'Mensal':                        { en: 'Monthly',                      es: 'Mensual' },
  'Acumulado':                     { en: 'Accumulated',                  es: 'Acumulado' },
  'Página {page} de {pages}':       { en: 'Page {page} of {pages}',       es: 'Página {page} de {pages}' },
  // ── ABC drill-down modal ──
  'Classe A (80% do Spend)':       { en: 'Class A (80% of Spend)',       es: 'Clase A (80% del Gasto)' },
  'Classe B (80-95%)':             { en: 'Class B (80-95%)',              es: 'Clase B (80-95%)' },
  'Classe C (cauda, 95-100%)':     { en: 'Class C (tail, 95-100%)',      es: 'Clase C (cola, 95-100%)' },
  'Itens':                         { en: 'Items',                        es: 'Ítems' },
  'Categorias':                    { en: 'Categories',                   es: 'Categorías' },
  'Fornecedores':                  { en: 'Suppliers',                    es: 'Proveedores' },
  // ── Price alerts table ──
  'Ds Item':                       { en: 'Item Desc',              es: 'Desc Ítem' },
  'Nome Fornecedor':               { en: 'Supplier Name',          es: 'Nombre Proveedor' },
  'Local Forn.':                   { en: 'Supplier Site',          es: 'Sitio Proveedor' },
  'Local Fornecedor':              { en: 'Supplier Site',          es: 'Sitio Proveedor' },
  'Preço Ant':                     { en: 'Prev Price',             es: 'Precio Ant' },
  'Preço Atual':                   { en: 'Current Price',          es: 'Precio Actual' },
  'Var %':                         { en: 'Var %',                  es: 'Var %' },
  'Impacto':                       { en: 'Impact',                 es: 'Impacto' },
  'Dt Lanç. Ant':                  { en: 'Prev Post Date',         es: 'Fecha Lanc. Ant' },
  'Dt Lanç. Atual':                { en: 'Current Post Date',      es: 'Fecha Lanc. Actual' },
  'NF Ant':                        { en: 'Prev Invoice',           es: 'NF Ant' },
  'NF Atual':                      { en: 'Current Invoice',        es: 'NF Actual' },
  'Nenhum alerta de preço no período': { en: 'No price alerts in the period', es: 'Ninguna alerta de precio en el período' },
  'Alertas Preço':                 { en: 'Price Alerts',           es: 'Alertas Precio' },
  // ── Chart legends & axis ──
  'Desconto Financeiro':           { en: 'Financial Discount',          es: 'Descuento Financiero' },
  'Desconto mensal':               { en: 'Monthly discount',            es: 'Descuento mensual' },
  'Aumento mensal':                { en: 'Monthly increase',            es: 'Aumento mensual' },
  'Aumento de Preço Acumulado':     { en: 'Accumulated Price Increase',  es: 'Aumento de Precio Acumulado' },
  // ── Lead time legs ──
  'horas':                         { en: 'hours',                       es: 'horas' },
  'Requisição Aprovada e Pedido Emitido': { en: 'Approved Requisition and Issued Order', es: 'Requisición Aprobada y Pedido Emitido' },
  'Pedido Emitido e Pedido Aprovado':     { en: 'Issued Order and Approved Order',       es: 'Pedido Emitido y Pedido Aprobado' },
  'Pedido Aprovado e NF':                 { en: 'Approved Order and Invoice',            es: 'Pedido Aprobado y NF' },
  // ── Deviation process bar ──
  'Compra regular':                { en: 'Regular purchase',            es: 'Compra regular' },
  'OC pós-fatura':                 { en: 'Post-invoice PO',             es: 'OC post-factura' },
  'Nota sem OC':                   { en: 'Invoice without PO',          es: 'Nota sin OC' },
  // ── Attention alerts ──
  'Requisições aguardando OC há mais de 5 dias': { en: 'Requisitions waiting for PO over 5 days', es: 'Requisiciones esperando OC hace más de 5 días' },
  'OCs aprovadas após fatura':     { en: 'POs approved after invoice',  es: 'OCs aprobadas después de factura' },
  'OCs emitidas após fatura':      { en: 'POs issued after invoice',    es: 'OCs emitidas después de factura' },
  'OCs descentralizadas acima de R$30.000': { en: 'Decentralized POs over R$30,000', es: 'OCs descentralizadas superior a R$30.000' },
  'OCs abertas há mais de 90 dias': { en: 'POs open for over 90 days',  es: 'OCs abiertas hace más de 90 días' },
  'Acordos de Compra abertos há mais de 180 dias': { en: 'Purchase Agreements open over 180 days', es: 'Acuerdos de Compra abiertos hace más de 180 días' },
  'Notas sem OCs':                 { en: 'Invoices without POs',        es: 'Notas sin OCs' },
  'Alerta':                        { en: 'Alert',                       es: 'Alerta' },
  'Qtd':                           { en: 'Qty',                         es: 'Cant.' },
  'das OCs faturadas':             { en: 'of invoiced POs',             es: 'de las OCs facturadas' },
  'das Notas Fiscais':             { en: 'of Invoices',                 es: 'de las Notas Fiscales' },
  '(qtd) do total de NFs':         { en: '(qty) of total invoices',     es: '(cant) del total de facturas' },
  '(qtd) das NFs com OC':          { en: '(qty) of invoices with PO',   es: '(cant) de facturas con OC' },
  'Requisições Aguardando OC (>5 dias)': { en: 'Requisitions Waiting for PO (>5 days)', es: 'Requisiciones Esperando OC (>5 días)' },
  // ── Dynamic templates (use with tt()) ──
  'Desvios de processo representam {pct}% do Spend Líquido no período selecionado': { en: 'Process deviations represent {pct}% of Net Spend in the selected period', es: 'Desvíos de proceso representan {pct}% del Gasto Neto en el período seleccionado' },
  'O maior tempo do processo está entre {leg}.': { en: 'The longest process time is between {leg}.', es: 'El mayor tiempo del proceso está entre {leg}.' },
  'No período selecionado, Spend Líquido está {pct}% {dir} do mesmo período do ano anterior': { en: 'In the selected period, Net Spend is {pct}% {dir} the same period of the previous year', es: 'En el período seleccionado, el Gasto Neto está {pct}% {dir} del mismo período del año anterior' },
  'No período selecionado, Centralização está em {val}% ({diff} pp {dir} do mesmo período do ano anterior)': { en: 'In the selected period, Centralization is at {val}% ({diff} pp {dir} the same period of the previous year)', es: 'En el período seleccionado, la Centralización está en {val}% ({diff} pp {dir} del mismo período del año anterior)' },
  '% Centraliz. Ano Anterior':     { en: '% Centraliz. Previous Year',  es: '% Centraliz. Año Anterior' },
  'Valores negativos representam economia obtida · Valores positivos representam aumento de preço': { en: 'Negative values represent savings obtained · Positive values represent price increase', es: 'Valores negativos representan economía obtenida · Valores positivos representan aumento de precio' },
  'Os {n} maiores itens representam {pct}% do Spend': { en: 'The top {n} items represent {pct}% of Spend', es: 'Los {n} mayores ítems representan {pct}% del Gasto' },
  'Os {n} maiores fornecedores representam {pct}% do Spend': { en: 'The top {n} suppliers represent {pct}% of Spend', es: 'Los {n} mayores proveedores representan {pct}% del Gasto' },
  'Os 5 maiores fornecedores concentram {pct}% do valor atrasado': { en: 'The top 5 suppliers concentrate {pct}% of overdue value', es: 'Los 5 mayores proveedores concentran {pct}% del valor atrasado' },
  'Quais categorias concentram o gasto?': { en: 'Which categories concentrate the spend?', es: '¿Qué categorías concentran el gasto?' },
  'Onde o gasto está concentrado?': { en: 'Where is the spend concentrated?', es: '¿Dónde está concentrado el gasto?' },
  'Comparação BB vs BQ (ignora filtro de empresa)': { en: 'BB vs BQ comparison (ignores company filter)', es: 'Comparación BB vs BQ (ignora filtro de empresa)' },
  'Considera pedidos com data prometida vencida': { en: 'Considers orders with overdue promised date', es: 'Considera pedidos con fecha prometida vencida' },
  'Realizado (Recebido/Faturado)': { en: 'Actual (Received/Invoiced)', es: 'Realizado (Recibido/Facturado)' },
  'A Realizar (Restante)': { en: 'Remaining', es: 'A Realizar (Restante)' },
  '% Realizado vs Previsto': { en: '% Actual vs Planned', es: '% Realizado vs Previsto' },
  'Spend líquido atrasado': { en: 'Overdue net spend', es: 'Gasto neto atrasado' },
  'Qtd pedidos': { en: 'Order qty', es: 'Cant. pedidos' },
  'Valor (R$)': { en: 'Value (R$)', es: 'Valor (R$)' },
  'Média dias': { en: 'Avg days', es: 'Media días' },
  'As {n} maiores plantas representam {pct}% do Spend': { en: 'The top {n} plants represent {pct}% of Spend', es: 'Las {n} mayores plantas representan {pct}% del Gasto' },
  'As {n} maiores categorias representam {pct}% do Spend': { en: 'The top {n} categories represent {pct}% of Spend', es: 'Las {n} mayores categorías representan {pct}% del Gasto' },
  'Os {n} maiores tipos representam {pct}% do Spend': { en: 'The top {n} types represent {pct}% of Spend', es: 'Los {n} mayores tipos representan {pct}% del Gasto' },
  '{emp} representa {pct}% do Spend Líquido': { en: '{emp} represents {pct}% of Net Spend', es: '{emp} representa {pct}% del Gasto Neto' },
  'Spend líquido por tipo de fornecedor': { en: 'Net spend by supplier type', es: 'Gasto neto por tipo de proveedor' },
  'Código': { en: 'Code', es: 'Código' },
  'Total': { en: 'Total', es: 'Total' },
  '% Acum': { en: '% Cum.', es: '% Acum' },
  'Sem dados': { en: 'No data', es: 'Sin datos' },
  // ── Orders dynamic ──
  'em atraso': { en: 'overdue', es: 'en atraso' },
  'do valor em aberto': { en: 'of open value', es: 'del valor abierto' },
  'do total em aberto': { en: 'of total open', es: 'del total abierto' },
  '1-30 dias': { en: '1-30 days', es: '1-30 días' },
  '31-60 dias': { en: '31-60 days', es: '31-60 días' },
  '61-90 dias': { en: '61-90 days', es: '61-90 días' },
  '91-120 dias': { en: '91-120 days', es: '91-120 días' },
  '>120 dias': { en: '>120 days', es: '>120 días' },
  'atraso': { en: 'delay', es: 'atraso' },
  'Dt Prometida': { en: 'Promised Date', es: 'Fecha Prometida' },
  'R$ em Aberto': { en: 'Open Value (R$)', es: 'R$ Abierto' },
  'Atraso (dias)': { en: 'Delay (days)', es: 'Atraso (días)' },
  'OC': { en: 'PO', es: 'OC' },
  'Pedidos em Atraso': { en: 'Overdue Orders', es: 'Pedidos en Atraso' },
  'Temos {qty} pedidos abertos a mais de {days} dias, somando {val} entre eles.': { en: 'There are {qty} open orders over {days} days, totaling {val}.', es: 'Hay {qty} pedidos abiertos de más de {days} días, sumando {val} entre ellos.' },
  '{val} previstos ainda não foram recebidos no prazo.': { en: '{val} planned have not yet been received on time.', es: '{val} previstos aún no se han recibido a tiempo.' },
  '{total} registros \u2014 Página {page} de {pages}': { en: '{total} records \u2014 Page {page} of {pages}', es: '{total} registros \u2014 Página {page} de {pages}' },
  '* Valores considerados com base na data prometida da OC para o previsto e na data de recebimento/faturamento (NF) para o realizado. \u00a0 Fonte: ERP': { en: '* Values based on PO promised date for planned and receipt/invoice (NF) date for actual. \u00a0 Source: ERP', es: '* Valores basados en la fecha prometida de la OC para lo previsto y la fecha de recepción/facturación (NF) para lo realizado. \u00a0 Fuente: ERP' }
};

/* ═══════════════════════════════════════════════════════════════════
   HTML I18N — Full innerHTML translations for [data-i18n] elements
   Used for Guide > Consulta Rápida tab content.
   ═══════════════════════════════════════════════════════════════════ */
var _HTML_I18N = {
  // ── Navigation & Common Buttons ──
  'nav_performance':  { en: 'Performance',        es: 'Rendimiento' },
  'nav_spend':        { en: 'Expenses',           es: 'Gastos' },
  'nav_ordens':       { en: 'Orders',             es: 'Órdenes' },
  'nav_comercial':    { en: 'Commercial',         es: 'Comercial' },
  'nav_governanca':   { en: 'Governance',         es: 'Gobernanza' },
  'nav_relatorios':   { en: 'Reports',            es: 'Informes' },
  'btn_mais_filtros': { en: 'More Filters',       es: 'Más Filtros' },
  'btn_aplicar':      { en: 'Apply',              es: 'Aplicar' },
  'btn_limpar':       { en: 'Clear',              es: 'Limpiar' },
  'lbl_atencao':      { en: 'ATTENTION',          es: 'ATENCIÓN' },
  'guide_intro':{en:'Bimbo Brasil procurement intelligence portal. Invoice data, purchase orders and requisitions from Oracle Cloud in one place \u2014 charts, KPIs and exportable tables.',es:'Portal de inteligencia de compras de Bimbo Brasil. Datos de facturas, \u00f3rdenes de compra y requisiciones del Oracle Cloud en un solo lugar \u2014 gr\u00e1ficos, KPIs y tablas exportables.'},
  'guide_s1_title':{en:'<span class="sec-num">1</span> How to Access',es:'<span class="sec-num">1</span> C\u00f3mo Acceder'},
  'guide_s1_step1':{en:'Open your browser <strong>(Chrome or Edge recommended)</strong>',es:'Abra el navegador <strong>(Chrome o Edge recomendado)</strong>'},
  'guide_s1_step2':{en:'Go to: <strong>https://compras-360-8674310331778219.19.azure.databricksapps.com</strong>',es:'Acceda a: <strong>https://compras-360-8674310331778219.19.azure.databricksapps.com</strong>'},
  'guide_s1_step3':{en:'Log in with your corporate email <strong>(@grupobimbo.com)</strong>',es:'Inicie sesi\u00f3n con su correo corporativo <strong>(@grupobimbo.com)</strong>'},
  'guide_s1_step4':{en:'Choose one of the 6 modules on the home screen',es:'Elija uno de los 6 m\u00f3dulos en la pantalla inicial'},
  'guide_s2_title':{en:'<span class="sec-num">2</span> The 6 Modules',es:'<span class="sec-num">2</span> Los 6 M\u00f3dulos'},
  'guide_mod1_name':{en:'Purchasing Performance',es:'Rendimiento de Compras'},
  'guide_mod1_desc':{en:'How much we spend, how much we save, payment terms and processing time',es:'Cu\u00e1nto gastamos, cu\u00e1nto ahorramos, plazo de pago y tiempo de procesamiento'},
  'guide_mod2_name':{en:'Spend Analysis',es:'An\u00e1lisis de Gastos'},
  'guide_mod2_desc':{en:'Where money is concentrated: by item, supplier, plant and ABC classification',es:'D\u00f3nde est\u00e1 concentrado el dinero: por \u00edtem, proveedor, planta y clasificaci\u00f3n ABC'},
  'guide_mod3_name':{en:'Order Management',es:'Gesti\u00f3n de \u00d3rdenes'},
  'guide_mod3_desc':{en:'Open orders, late orders and planned vs. actual comparison',es:'\u00d3rdenes abiertas, atrasadas y comparaci\u00f3n entre previsto y realizado'},
  'guide_mod4_name':{en:'Commercial Conditions',es:'Condiciones Comerciales'},
  'guide_mod4_desc':{en:'Payment terms, savings by supplier and renegotiation opportunities',es:'Plazos de pago, ahorros por proveedor y oportunidades de renegociaci\u00f3n'},
  'guide_mod5_name':{en:'Governance',es:'Gobernanza'},
  'guide_mod5_desc':{en:'Exceptions: post-invoice PO, emergency, invoices without PO and decentralized purchases &gt; R$ 30K',es:'Excepciones: OC post-factura, emergenciales, notas sin OC y compras descentralizadas &gt; R$ 30 mil'},
  'guide_mod6_name':{en:'Reports',es:'Informes'},
  'guide_mod6_desc':{en:'Detailed exploration with search, advanced filters and Excel export',es:'Exploraci\u00f3n detallada con b\u00fasqueda, filtros avanzados y exportaci\u00f3n a Excel'},
  'guide_s3_title':{en:'<span class="sec-num">3</span> How to Use Filters',es:'<span class="sec-num">3</span> C\u00f3mo Usar los Filtros'},
  'guide_s3_intro':{en:'All modules have a <strong>filter bar</strong> at the top. Filters are <strong>cascaded</strong>: when you select a value, the others show only compatible options.',es:'Todos los m\u00f3dulos tienen una <strong>barra de filtros</strong> en la parte superior. Los filtros son <strong>en cascada</strong>: al seleccionar un valor, los dem\u00e1s muestran solo opciones compatibles.'},
  'guide_s3_f1':{en:'<strong>Year / Month</strong> \u2014 analysis period',es:'<strong>A\u00f1o / Mes</strong> \u2014 per\u00edodo de an\u00e1lisis'},
  'guide_s3_f2':{en:'<strong>Company</strong> \u2014 BB (Bimbo Brasil) or BQ (Bimbo QSR)',es:'<strong>Empresa</strong> \u2014 BB (Bimbo Brasil) o BQ (Bimbo QSR)'},
  'guide_s3_f3':{en:'<strong>Purchasing Group</strong> \u2014 DIRECT or INDIRECT',es:'<strong>Grupo de Compras</strong> \u2014 DIRECTOS o INDIRECTOS'},
  'guide_s3_f4':{en:'<strong>Supplier</strong> \u2014 search by name',es:'<strong>Proveedor</strong> \u2014 buscar por nombre'},
  'guide_s3_f5':{en:'<strong>Plant / Location</strong> \u2014 filter by location',es:'<strong>Unidad / Planta</strong> \u2014 filtre por localidad'},
  'guide_s3_tip':{en:'\ud83d\udca1 <strong>Tip:</strong> Click \"Clear\" to remove all filters. In the Reports module, use text search to find a specific invoice or PO.',es:'\ud83d\udca1 <strong>Consejo:</strong> Haga clic en \"Limpiar\" para eliminar todos los filtros. En el m\u00f3dulo Informes, use la b\u00fasqueda textual para encontrar una factura u OC espec\u00edfica.'},
  'guide_s4_title':{en:'<span class="sec-num">4</span> Example Questions',es:'<span class="sec-num">4</span> Ejemplos de Preguntas'},
  'guide_s4_h_perf':{en:'Performance (Module 01)',es:'Rendimiento (M\u00f3dulo 01)'},
  'guide_s4_q1':{en:'How much did we spend in 2026 vs. 2025?',es:'\u00bfCu\u00e1nto gastamos en 2026 vs. 2025?'},
  'guide_s4_a1':{en:'\u2192 KPI \"Net Spend\" + chart \"Spend YoY\" in the Performance module',es:'\u2192 KPI \"Gasto Neto\" + gr\u00e1fico \"Gasto YoY\" en el m\u00f3dulo Rendimiento'},
  'guide_s4_q2':{en:'What is the accumulated savings for 2026?',es:'\u00bfCu\u00e1l es el ahorro acumulado de 2026?'},
  'guide_s4_a2':{en:'\u2192 KPI \"Savings\" in the Performance module. Filter the desired year.',es:'\u2192 KPI \"Ahorros\" en el m\u00f3dulo Rendimiento. Filtre el a\u00f1o deseado.'},
  'guide_s4_q3':{en:'How long does it take from requisition to invoice?',es:'\u00bfCu\u00e1nto tiempo tarda de la requisici\u00f3n a la factura?'},
  'guide_s4_a3':{en:'\u2192 \"Lead Time\" panel with the 3 stages in the Performance module',es:'\u2192 Panel \"Lead Time\" con las 3 etapas en el m\u00f3dulo Rendimiento'},
  'guide_s4_h_spend':{en:'Expenses (Module 02)',es:'Gastos (M\u00f3dulo 02)'},
  'guide_s4_q4':{en:'What are the top 10 items by spend?',es:'\u00bfCu\u00e1les son los 10 \u00edtems con mayor gasto?'},
  'guide_s4_a4':{en:'\u2192 \"Top Items\" card in the Expenses module',es:'\u2192 Card \"Top \u00cdtems\" en el m\u00f3dulo Gastos'},
  'guide_s4_q5':{en:'Which suppliers account for 80% of spend?',es:'\u00bfQu\u00e9 proveedores concentran el 80% del gasto?'},
  'guide_s4_a5':{en:'\u2192 \"ABC Curve\" table \u2014 class A \u2248 80% of value',es:'\u2192 Tabla \"Curva ABC\" \u2014 clase A \u2248 80% del valor'},
  'guide_s4_h_orders':{en:'Orders (Module 03)',es:'\u00d3rdenes (M\u00f3dulo 03)'},
  'guide_s4_q6':{en:'How many POs are overdue?',es:'\u00bfCu\u00e1ntas OCs est\u00e1n atrasadas?'},
  'guide_s4_a6':{en:'\u2192 KPI \"Late POs\" + detailed table in the Orders module',es:'\u2192 KPI \"OCs Atrasadas\" + tabla detallada en el m\u00f3dulo \u00d3rdenes'},
  'guide_s4_h_gov':{en:'Governance (Module 05)',es:'Gobernanza (M\u00f3dulo 05)'},
  'guide_s4_q7':{en:'How much do we have in decentralized purchases over R$ 30K?',es:'\u00bfCu\u00e1nto tenemos en compras descentralizadas superiores a R$ 30 mil?'},
  'guide_s4_a7':{en:'\u2192 Select \"Decentralized PO > 30K\" in the Governance module',es:'\u2192 Seleccione \"OC Descentralizada > 30K\" en el m\u00f3dulo Gobernanza'},
  'guide_s4_h_reports':{en:'Reports (Module 06)',es:'Informes (M\u00f3dulo 06)'},
  'guide_s4_q8':{en:'I need all invoices from supplier X in January/2026',es:'Necesito todas las facturas del proveedor X en enero/2026'},
  'guide_s4_a8':{en:'\u2192 Dataset \"Invoices\", filter Supplier and Month, export to Excel',es:'\u2192 Dataset \"Facturas\", filtre Proveedor y Mes, exporte a Excel'},
  'guide_s5_title':{en:'<span class="sec-num">5</span> FAQ',es:'<span class="sec-num">5</span> Preguntas Frecuentes'},
  'guide_faq1_q':{en:'How often is the data updated?',es:'\u00bfCon qu\u00e9 frecuencia se actualizan los datos?'},
  'guide_faq1_a':{en:'Data comes from Oracle Cloud via ETL (ideally daily). If it seems outdated, contact the data team.',es:'Los datos provienen del Oracle Cloud v\u00eda ETL (idealmente diario). Si parecen desactualizados, contacte al equipo de datos.'},
  'guide_faq2_q':{en:'Why does savings show as zero for some suppliers?',es:'\u00bfPor qu\u00e9 el ahorro aparece como cero para algunos proveedores?'},
  'guide_faq2_a':{en:'If there is no previous price or the percentage is outside 0\u2013100%, the system disregards it.',es:'Si no hay precio anterior o el porcentaje est\u00e1 fuera de 0\u2013100%, el sistema lo descarta.'},
  'guide_faq3_q':{en:'What does \"Invoice without PO\" mean?',es:'\u00bfQu\u00e9 significa \"Nota sin OC\"?'},
  'guide_faq3_a':{en:'Invoices posted without a linked purchase order \u2014 may be an emergency purchase.',es:'Facturas lanzadas sin orden de compra vinculada \u2014 puede ser una compra de emergencia.'},
  'guide_faq4_q':{en:'Can I export to Excel?',es:'\u00bfPuedo exportar a Excel?'},
  'guide_faq4_a':{en:'Yes! In the Reports module use the download button. Other modules also have export options in their tables.',es:'\u00a1S\u00ed! En el m\u00f3dulo Informes use el bot\u00f3n de descarga. Otros m\u00f3dulos tambi\u00e9n tienen exportaci\u00f3n en las tablas.'},
  'guide_faq5_q':{en:'What is \"Centralized\" vs. \"Decentralized\"?',es:'\u00bfQu\u00e9 es \"Centralizado\" vs. \"Descentralizado\"?'},
  'guide_faq5_a':{en:'<strong>Centralized</strong> = purchase via Procurement area (agreement, PO \u2265 R$ 30K or functional buyer). <strong>Decentralized</strong> = direct purchase by the business unit.',es:'<strong>Centralizado</strong> = compra v\u00eda \u00e1rea de Compras (acuerdo, OC \u2265 R$ 30K o comprador funcional). <strong>Descentralizado</strong> = compra directa por la unidad.'},
  'guide_s6_title':{en:'<span class="sec-num">6</span> Who to Contact',es:'<span class="sec-num">6</span> A Qui\u00e9n Contactar'},
  'guide_c1_subj':{en:'Technical issues with the app',es:'Problemas t\u00e9cnicos en la app'},
  'guide_c2_subj':{en:'Incorrect or outdated data',es:'Datos incorrectos o desactualizados'},
  'guide_c3_subj':{en:'Business rules',es:'Reglas de negocio'},
  'guide_c3_who':{en:'Procurement / Supplier Management',es:'\u00c1rea de Compras / Gesti\u00f3n de Proveedores'},
  'guide_c4_subj':{en:'Oracle Cloud data (source)',es:'Datos Oracle Cloud (fuente)'},
  'guide_c4_who':{en:'Oracle Cloud / IT Team',es:'Equipo Oracle Cloud / TI'},
  'pres_fs_btn': { en: "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><polyline points=\"15 3 21 3 21 9\"/><polyline points=\"9 21 3 21 3 15\"/><line x1=\"21\" y1=\"3\" x2=\"14\" y2=\"10\"/><line x1=\"3\" y1=\"21\" x2=\"10\" y2=\"14\"/></svg> Fullscreen", es: "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><polyline points=\"15 3 21 3 21 9\"/><polyline points=\"9 21 3 21 3 15\"/><line x1=\"21\" y1=\"3\" x2=\"14\" y2=\"10\"/><line x1=\"3\" y1=\"21\" x2=\"10\" y2=\"14\"/></svg> Pantalla completa" },
  'pres_s1_tag': { en: "Bimbo Brasil — DNA", es: "Bimbo Brasil — DNA" },
  'pres_s1_ttl': { en: "PROCUREMENT PORTAL", es: "PORTAL COMPRAS" },
  'pres_s1_sub': { en: "All procurement intelligence centralized in a single interactive portal.", es: "Toda la inteligencia de compras centralizada en un único portal interactivo." },
  'pres_s2_tag': { en: "Context", es: "Contexto" },
  'pres_s2_title': { en: "Why do we need this?", es: "¿Por qué necesitamos esto?" },
  'pres_s2_banner': { en: "Process exceptions that, without this portal, are simply not tracked.", es: "Excepciones de proceso que, sin este portal, simplemente no son rastreadas." },
  'pres_s2_c1_ttl': { en: "Fragmented Data", es: "Datos Fragmentados" },
  'pres_s2_c1_desc': { en: "<strong style=\"color:var(--fr-txt)\">Multiple isolated sources</strong> — matching invoices with purchase orders requires manual work", es: "<strong style=\"color:var(--fr-txt)\">Múltiples fuentes aisladas</strong> — cruzar facturas con órdenes de compra requiere trabajo manual" },
  'pres_s2_c2_ttl': { en: "No Consolidated View", es: "Sin Visión Consolidada" },
  'pres_s2_c2_desc': { en: "<strong style=\"color:var(--fr-txt)\">Thousands of suppliers, dozens of plants</strong> — each spend question generates a new manual report", es: "<strong style=\"color:var(--fr-txt)\">Miles de proveedores, decenas de plantas</strong> — cada pregunta sobre gasto genera un nuevo informe manual" },
  'pres_s2_c3_ttl': { en: "Uncontrolled Savings", es: "Ahorros Sin Control" },
  'pres_s2_c3_desc': { en: "Without continuous and standardized measurement, savings opportunities go unnoticed", es: "Sin medición continua y estandarizada, las oportunidades de ahorro pasan desapercibidas" },
  'pres_s2_c4_ttl': { en: "Invisible Exceptions", es: "Excepciones Invisibles" },
  'pres_s2_c4_desc': { en: "<strong style=\"color:var(--fr-txt)\">Post-invoice POs, invoices without PO, decentralized purchases</strong> — process deviations without tracking", es: "<strong style=\"color:var(--fr-txt)\">OCs post-factura, facturas sin OC, compras descentralizadas</strong> — desvíos de proceso sin seguimiento" },
  'pres_s3_tag': { en: "Solution", es: "Solución" },
  'pres_s3_title': { en: "What is the Procurement Portal", es: "¿Qué es el Portal Compras?" },
  'pres_s3_p1': { en: "An <strong>interactive web portal</strong> that automatically consolidates Oracle Cloud data and presents it in ready-to-use visual dashboards.", es: "Un <strong>portal web interactivo</strong> que consolida automáticamente los datos de Oracle Cloud y los presenta en paneles visuales listos para usar." },
  'pres_s3_k1': { en: "Invoices", es: "Facturas" },
  'pres_s3_k2': { en: "Purchase Orders", es: "Órdenes de Compra" },
  'pres_s3_k3': { en: "Requisitions", es: "Requisiciones" },
  'pres_s3_p2': { en: "Data updated automatically via daily ETL. Access via any browser, no installation required.", es: "Datos actualizados automáticamente mediante ETL diario. Acceso desde cualquier navegador, sin instalación." },
  'pres_s4_tag': { en: "Features", es: "Funcionalidades" },
  'pres_s4_title': { en: "6 Specialized Modules", es: "6 Módulos Especializados" },
  'pres_s4_m1_ttl': { en: "★ Performance", es: "★ Rendimiento" },
  'pres_s4_m1_desc': { en: "Spend, centralization and YoY comparison KPIs", es: "KPIs de gasto, centralización y comparación YoY" },
  'pres_s4_m2_ttl': { en: "Expenses", es: "Gastos" },
  'pres_s4_m2_desc': { en: "ABC curve, top items and suppliers, cross-filter", es: "Curva ABC, top ítems y proveedores, cross-filter" },
  'pres_s4_m3_ttl': { en: "Orders", es: "Órdenes" },
  'pres_s4_m3_desc': { en: "Open value, overdue POs, planned vs. actual", es: "Valor abierto, OCs retrasadas, previsto vs. realizado" },
  'pres_s4_m4_ttl': { en: "Commercial", es: "Comercial" },
  'pres_s4_m4_desc': { en: "Payment terms and renegotiation opportunities", es: "Plazos de pago y oportunidades de renegociación" },
  'pres_s4_m5_ttl': { en: "★ Governance", es: "★ Gobernanza" },
  'pres_s4_m5_desc': { en: "Process exceptions tracked automatically", es: "Excepciones de proceso rastreadas automáticamente" },
  'pres_s4_m6_ttl': { en: "Reports", es: "Informes" },
  'pres_s4_m6_desc': { en: "Free search, Excel export", es: "Búsqueda libre, exportación Excel" },
  'pres_s5_tag': { en: "Experience", es: "Experiencia" },
  'pres_s5_title': { en: "Smart Filters", es: "Filtros Inteligentes" },
  'pres_s5_sub': { en: "Cascaded filters across <strong style=\"color:var(--fr-txt)\">all suppliers</strong> and <strong style=\"color:var(--fr-txt)\">all plants</strong> — selecting a value adjusts all dashboards.", es: "Filtros en cascada entre <strong style=\"color:var(--fr-txt)\">todos los proveedores</strong> y <strong style=\"color:var(--fr-txt)\">todas las plantas</strong> — al seleccionar un valor, todos los paneles se ajustan." },
  'pres_s5_f1_lbl': { en: "Year / Month", es: "Año / Mes" },
  'pres_s5_f1_sub': { en: "Flexible period", es: "Período flexible" },
  'pres_s5_f2_lbl': { en: "Company", es: "Empresa" },
  'pres_s5_f2_sub': { en: "BB or BQ", es: "BB o BQ" },
  'pres_s5_f3_lbl': { en: "Group", es: "Grupo" },
  'pres_s5_f3_sub': { en: "Direct / Indirect", es: "Directo / Indirecto" },
  'pres_s5_f4_lbl': { en: "Supplier", es: "Proveedor" },
  'pres_s5_f4_sub': { en: "Search by name", es: "Búsqueda por nombre" },
  'pres_s5_f5_lbl': { en: "Unit", es: "Unidad" },
  'pres_s5_f5_sub': { en: "Plant / Location", es: "Planta / Localidad" },
  'pres_s5_tip': { en: "One click on filters and all 6 modules adjust instantly — <strong style=\"color:var(--fr-txt)\">multiple sources, zero rework</strong>. Click on chart bars for cross-filter.", es: "Un clic en los filtros y los 6 módulos se ajustan al instante — <strong style=\"color:var(--fr-txt)\">múltiples fuentes, cero retrabajo</strong>. Haga clic en las barras de los gráficos para cross-filter." },
  'pres_s6_tag': { en: "Control", es: "Control" },
  'pres_s6_title': { en: "Governance and Visibility", es: "Gobernanza y Visibilidad" },
  'pres_s6_sub': { en: "All process exceptions tracked automatically", es: "Todas las excepciones de proceso rastreadas automáticamente" },
  'pres_s6_c1_ttl': { en: "Post-Invoice PO", es: "OC Post-Factura" },
  'pres_s6_c1_sub': { en: "Quantity and value of POs created after invoice", es: "Cantidad y valor de OCs creadas después de la factura" },
  'pres_s6_c2_ttl': { en: "Emergency", es: "Emergencial" },
  'pres_s6_c2_sub': { en: "Urgent purchases outside the standard process", es: "Compras de urgencia fuera del proceso estándar" },
  'pres_s6_c3_ttl': { en: "Invoice without PO", es: "Nota sin OC" },
  'pres_s6_c3_sub': { en: "Invoices posted without a linked purchase order", es: "Facturas ingresadas sin orden de compra vinculada" },
  'pres_s6_c4_ttl': { en: "Decentralized >30K", es: "Descentralizada >30K" },
  'pres_s6_c4_sub': { en: "POs over R$ 30K issued outside Procurement", es: "OCs de más de R$ 30 mil emitidas fuera de Compras" },
  'pres_s6_c5_ttl': { en: "Open POs >90 days", es: "OCs Abiertas >90 días" },
  'pres_s6_c5_sub': { en: "POs with pending receipt for over 90 days", es: "OCs con recepción pendiente hace más de 90 días" },
  'pres_s6_c6_ttl': { en: "Agreements >180 days", es: "Acuerdos >180 días" },
  'pres_s6_c6_sub': { en: "Purchase agreements without recent renewal or review", es: "Acuerdos de compra sin renovación o revisión reciente" },
  'pres_s6_foot': { en: "Each exception shows value, supplier, buyer concentration and an exportable table", es: "Cada excepción muestra valor, proveedor, concentración por comprador y tabla exportable" },
  'pres_s7_tag': { en: "Results", es: "Resultados" },
  'pres_s7_title': { en: "What We Gain With This", es: "¿Qué Ganamos con Esto?" },
  'pres_s7_banner': { en: "Exceptions that were once invisible now have a name, value, and owner.", es: "Las excepciones que antes eran invisibles ahora tienen nombre, valor y responsable." },
  'pres_s7_b1_ttl': { en: "Time Savings", es: "Ahorro de Tiempo" },
  'pres_s7_b1_desc': { en: "<strong style=\"color:var(--fr-txt)\">6 ready modules</strong> replace manual extraction from multiple sources — daily automatic updates", es: "<strong style=\"color:var(--fr-txt)\">6 módulos</strong> listos reemplazan la extracción manual de múltiples fuentes — actualización automática diaria" },
  'pres_s7_b2_ttl': { en: "Total Visibility", es: "Visibilidad Total" },
  'pres_s7_b2_desc': { en: "100% of spend consolidated from multiple sources, monitored in a single portal with daily updates", es: "100% del gasto consolidado de múltiples fuentes, monitoreado en un único portal con actualización diaria" },
  'pres_s7_b3_ttl': { en: "Targeted Action", es: "Acción Dirigida" },
  'pres_s7_b3_desc': { en: "Identify key suppliers and buyers in each exception type — <strong style=\"color:var(--fr-txt)\">targeted action with real data</strong>", es: "Identifique los principales proveedores y compradores en cada tipo de excepción — <strong style=\"color:var(--fr-txt)\">acción dirigida con datos reales</strong>" },
  'pres_s7_b4_ttl': { en: "Data-Driven Decisions", es: "Decisiones Basadas en Datos" },
  'pres_s7_b4_desc': { en: "Compare spend across periods with <strong style=\"color:var(--fr-txt)\">automatic YoY comparison</strong> — always on the same time base", es: "Compare gastos entre períodos con <strong style=\"color:var(--fr-txt)\">comparación YoY automática</strong> — siempre sobre la misma base temporal" },
  'pres_s8_tag': { en: "Next Steps", es: "Próximos Pasos" },
  'pres_s8_title': { en: "Start Using It Now", es: "Comience a Usarlo Ahora" },
  'pres_s8_sub': { en: "Access via browser, explore the modules, and bring your questions.<br>The complete guide is available inside the app — \"Guide\" tab.", es: "Acceda desde el navegador, explore los módulos y plantee sus preguntas.<br>La guía completa está disponible dentro de la propia app — pestaña \"Guía\"." },
  'pres_s8_contact': { en: "<strong style=\"color:var(--fr-txt);\">Questions?</strong> → <a href=\"mailto:renan.ferreira@grupobimbo.com\" style=\"color:#60a5fa;\">renan.ferreira@grupobimbo.com</a>", es: "<strong style=\"color:var(--fr-txt);\">¿Dudas?</strong> → <a href=\"mailto:renan.ferreira@grupobimbo.com\" style=\"color:#60a5fa;\">renan.ferreira@grupobimbo.com</a>" },
  'tech_s1_ttl': { en: "<span class=\"sec-num\">1</span> Overview", es: "<span class=\"sec-num\">1</span> Visión General" },
  'tech_s1_p': { en: "The <strong>PROCUREMENT PORTAL</strong> consolidates invoice, purchase order and requisition data from Oracle Cloud into an interactive web portal. Backend in Flask + Lakebase PostgreSQL, frontend in HTML/JS with Chart.js.", es: "El <strong>PORTAL DE COMPRAS</strong> consolida datos de facturas, órdenes de compra y requisiciones de Oracle Cloud en un portal web interactivo. Backend en Flask + Lakebase PostgreSQL, frontend en HTML/JS con Chart.js." },
  'tech_s2_ttl': { en: "<span class=\"sec-num\">2</span> Metrics, Formulas & Tab Segmentations Manual", es: "<span class=\"sec-num\">2</span> Manual de Métricas, Fórmulas y Segmentaciones por Pestaña" },
  'tech_s3_ttl': { en: "<span class=\"sec-num\">3</span> Architecture", es: "<span class=\"sec-num\">3</span> Arquitectura" },
  'tech_s3_tbl': { en: "<tr><th>Stage</th><th>Source</th><th>Target</th><th>Mechanism</th></tr>\n<tr><td><strong>Extraction</strong></td><td>Oracle Cloud (<code>cat_ocloud_r5_dv.rg5glofsn_cz</code>)</td><td>Spark temp views</td><td>SQL via ETL notebook</td></tr>\n<tr><td><strong>Lookups (Base Files)</strong></td><td>Unity Catalog Volume (<code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>)</td><td>Spark DataFrames / Lakebase</td><td>Pandas / Databricks Files SDK + psycopg2</td></tr>\n<tr><td><strong>Daily Load</strong></td><td>Spark temp views</td><td>Lakebase PostgreSQL (<code>compras</code>)</td><td>COPY blue-green swap</td></tr>\n<tr><td><strong>App Consumption</strong></td><td>Lakebase PostgreSQL (fallback: Volume)</td><td>Flask API → Frontend</td><td>psycopg2 + REST</td></tr>\n<tr><td><strong>Management & Editing (Master Data)</strong></td><td>Web Portal (Authorized User)</td><td>Unity Catalog Volume + Lakebase (real time)</td><td>REST API → Files SDK + PostgreSQL (zero deploy)</td></tr>", es: "<tr><th>Etapa</th><th>Origen</th><th>Destino</th><th>Mecanismo</th></tr>\n<tr><td><strong>Extracción</strong></td><td>Oracle Cloud (<code>cat_ocloud_r5_dv.rg5glofsn_cz</code>)</td><td>Spark temp views</td><td>SQL vía notebook ETL</td></tr>\n<tr><td><strong>Lookups (Archivos Base)</strong></td><td>Volumen Unity Catalog (<code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>)</td><td>Spark DataFrames / Lakebase</td><td>Pandas / Databricks Files SDK + psycopg2</td></tr>\n<tr><td><strong>Carga Diaria</strong></td><td>Spark temp views</td><td>Lakebase PostgreSQL (<code>compras</code>)</td><td>COPY blue-green swap</td></tr>\n<tr><td><strong>Consumo de la App</strong></td><td>Lakebase PostgreSQL (fallback: Volumen)</td><td>Flask API → Frontend</td><td>psycopg2 + REST</td></tr>\n<tr><td><strong>Gestión y Edición (Catálogos)</strong></td><td>Portal Web (Usuario Autorizado)</td><td>Volumen Unity Catalog + Lakebase (tiempo real)</td><td>API REST → Files SDK + PostgreSQL (sin deploy)</td></tr>" },
  'tech_s3_diag': { en: "Oracle Cloud (cat_ocloud_r5_dv)\n          │\n          ▼\n          SQL Views (vw_notas_ri, vw_ordens_compra, vw_requisicoes)\n          + Unity Catalog Volume (cat_dnabb_dv.grobbcompr_cz.compras_360)\n          │\n          ▼\n          Lakebase PostgreSQL ─▶ schema \"compras_staging\" (blue-green)\n          │ │\n          │ validation + atomic swap\n          ▼ │\n          schema \"compras\" ◄────────────┘\n          ▲\n          │ (real-time bi-directional sync)\n          ▼\n          Flask API (app.py) ◄═══ Save Master Data (Volume + Lakebase)\n          │\n          ▼\n          Frontend HTML/JS (Dashboard, Analytics, Guide and Master Data)", es: "Oracle Cloud (cat_ocloud_r5_dv)\n          │\n          ▼\n          SQL Views (vw_notas_ri, vw_ordens_compra, vw_requisicoes)\n          + Volumen Unity Catalog (cat_dnabb_dv.grobbcompr_cz.compras_360)\n          │\n          ▼\n          Lakebase PostgreSQL ─▶ schema \"compras_staging\" (blue-green)\n          │ │\n          │ validación + swap atómico\n          ▼ │\n          schema \"compras\" ◄────────────┘\n          ▲\n          │ (sincronización bidireccional en tiempo real)\n          ▼\n          Flask API (app.py) ◄═══ Guardar Catálogos (Volumen + Lakebase)\n          │\n          ▼\n          Frontend HTML/JS (Dashboard, Análisis, Guía y Catálogos)" },
  'tech_s3_job_ttl': { en: "Automatic Update Job", es: "Job de Actualización Automática" },
  'tech_s3_job_tbl': { en: "<tr><th>Property</th><th>Value</th></tr>\n<tr><td>Name</td><td><strong>ETL Compras 360 - Lakebase Daily</strong> (Job ID: <code>357960921780603</code>)</td></tr>\n<tr><td>Schedule</td><td><strong>Daily at 06:00</strong> (America/Sao_Paulo)</td></tr>\n<tr><td>Status</td><td>Active (<code>UNPAUSED</code>)</td></tr>\n<tr><td>Average duration</td><td>∼6 minutes</td></tr>\n<tr><td>Failure notification</td><td><code>renan.ferreira@grupobimbo.com</code></td></tr>\n<tr><td>Executed notebook</td><td><code>compras_360_lakebase_etl</code></td></tr>", es: "<tr><th>Propiedad</th><th>Valor</th></tr>\n<tr><td>Nombre</td><td><strong>ETL Compras 360 - Lakebase Daily</strong> (Job ID: <code>357960921780603</code>)</td></tr>\n<tr><td>Horario</td><td><strong>Diariamente a las 06:00</strong> (America/Sao_Paulo)</td></tr>\n<tr><td>Estado</td><td>Activo (<code>UNPAUSED</code>)</td></tr>\n<tr><td>Duración promedio</td><td>∼6 minutos</td></tr>\n<tr><td>Notificación de fallo</td><td><code>renan.ferreira@grupobimbo.com</code></td></tr>\n<tr><td>Notebook ejecutado</td><td><code>compras_360_lakebase_etl</code></td></tr>" },
  'tech_s4_ttl': { en: "<span class=\"sec-num\">4</span> Data Model", es: "<span class=\"sec-num\">4</span> Modelo de Datos" },
  'tech_s4_p1_ttl': { en: "Main Tables (schema <code>compras</code>)", es: "Tablas Principales (schema <code>compras</code>)" },
  'tech_s4_p1_tbl': { en: "<tr><th>Table</th><th>Records</th><th>Description</th><th>Key columns</th></tr>\n<tr><td><code>notas_ri</code></td><td>∼400K</td><td>Goods receipt invoices</td><td><code>numero_ri</code>, <code>nota_fiscal</code>, <code>numero_oc</code>, <code>empresa</code>, <code>macro_categoria</code>, <code>valor_liquido_brl</code>, <code>saving_total</code>, <code>data_lancamento</code>, <code>grupo_compras</code>, <code>centralizado</code></td></tr>\n<tr><td><code>ordens_compra</code></td><td>∼260K</td><td>Purchase orders (lines)</td><td><code>numero_oc</code>, <code>numero_acordo</code>, <code>chave_oc_linha</code>, <code>macro_categoria</code>, <code>data_oc</code>, <code>status_aprovacao</code>, <code>status_fechamento</code>, <code>valor_original_brl</code></td></tr>\n<tr><td><code>requisicoes</code></td><td>∼90K</td><td>Purchase requisitions</td><td><code>requisicao</code>, <code>numero_oc</code>, <code>dt_criacao</code>, <code>dt_aprovacao</code>, <code>valor_requisicao</code>, <code>status</code></td></tr>", es: "<tr><th>Tabla</th><th>Registros</th><th>Descripción</th><th>Columnas clave</th></tr>\n<tr><td><code>notas_ri</code></td><td>∼400K</td><td>Facturas de recepción</td><td><code>numero_ri</code>, <code>nota_fiscal</code>, <code>numero_oc</code>, <code>empresa</code>, <code>macro_categoria</code>, <code>valor_liquido_brl</code>, <code>saving_total</code>, <code>data_lancamento</code>, <code>grupo_compras</code>, <code>centralizado</code></td></tr>\n<tr><td><code>ordens_compra</code></td><td>∼260K</td><td>Órdenes de compra (líneas)</td><td><code>numero_oc</code>, <code>numero_acordo</code>, <code>chave_oc_linha</code>, <code>macro_categoria</code>, <code>data_oc</code>, <code>status_aprovacao</code>, <code>status_fechamento</code>, <code>valor_original_brl</code></td></tr>\n<tr><td><code>requisicoes</code></td><td>∼90K</td><td>Requisiciones de compra</td><td><code>requisicao</code>, <code>numero_oc</code>, <code>dt_criacao</code>, <code>dt_aprovacao</code>, <code>valor_requisicao</code>, <code>status</code></td></tr>" },
  'tech_s4_p2_ttl': { en: "Lookup Tables (Master Support Data)", es: "Tablas de Lookup (Catálogos de Apoyo)" },
  'tech_s4_p2_tbl': { en: "<tr><th>Table</th><th>Records</th><th>Description</th><th>Source & Management</th></tr>\n<tr><td><code>fornecedores_especiais</code></td><td>∼54</td><td>Suppliers marked as special</td><td>Master Data Module / Lakebase</td></tr>\n<tr><td><code>fornecedores_nao_negociaveis</code></td><td>∼349</td><td>Non-negotiable suppliers</td><td>Master Data Module / Lakebase</td></tr>\n<tr><td><code>fornecedores_sem_oc</code></td><td>∼85</td><td>Suppliers permitted without PO (no procurement actuation)</td><td>Master Data Module / Lakebase</td></tr>\n<tr><td><code>compradores_funcionais</code></td><td>∼690</td><td>Buyer mapping → area/unit</td><td>Master Data Module / Lakebase</td></tr>", es: "<tr><th>Tabla</th><th>Registros</th><th>Descripción</th><th>Fuente y Gestión</th></tr>\n<tr><td><code>fornecedores_especiais</code></td><td>∼54</td><td>Proveedores marcados como especiales</td><td>Módulo Catálogos / Lakebase</td></tr>\n<tr><td><code>fornecedores_nao_negociaveis</code></td><td>∼349</td><td>Proveedores no negociables</td><td>Módulo Catálogos / Lakebase</td></tr>\n<tr><td><code>fornecedores_sem_oc</code></td><td>∼85</td><td>Proveedores autorizados sin OC (sin actuación de compras)</td><td>Módulo Catálogos / Lakebase</td></tr>\n<tr><td><code>compradores_funcionais</code></td><td>∼690</td><td>Mapeo comprador → área/unidad</td><td>Módulo Catálogos / Lakebase</td></tr>" },
  'tech_s4_joins_ttl': { en: "Main Joins", es: "Joins Principales" },
  'tech_s4_joins_p': { en: "<p>• <code>notas_ri</code> ↔ <code>ordens_compra</code> via <code>CHAVE_OC_LINHA</code> (composite: NUMERO_OC + LINHA_OC)</p>\n<p>• <code>requisicoes</code> ↔ <code>ordens_compra</code> via <code>NUMERO_OC</code> or <code>REQUISICAO</code></p>\n<p>• <code>ordens_compra</code> ↔ <code>compradores_funcionais</code> via <code>usuario</code> = <code>usuario_oracle</code></p>", es: "<p>• <code>notas_ri</code> ↔ <code>ordens_compra</code> vía <code>CHAVE_OC_LINHA</code> (compuesta: NUMERO_OC + LINHA_OC)</p>\n<p>• <code>requisicoes</code> ↔ <code>ordens_compra</code> vía <code>NUMERO_OC</code> o <code>REQUISICAO</code></p>\n<p>• <code>ordens_compra</code> ↔ <code>compradores_funcionais</code> vía <code>usuario</code> = <code>usuario_oracle</code></p>" },
  'tech_s4_vol_ttl': { en: "Corporate Unity Catalog Volume (<code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>)", es: "Volumen Corporativo Unity Catalog (<code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>)" },
  'tech_s4_vol_p': { en: "Following Grupo Bimbo governance and corporate architecture standards, CSV master files no longer reside in local workspace folders and now reside in the <strong>Managed Unity Catalog Volume</strong>:", es: "Siguiendo el estándar de gobernanza y arquitectura corporativa de Grupo Bimbo, las bases de apoyo en CSV dejaron de residir en carpetas locales del Workspace y pasaron a residir en el <strong>Volumen Administrado del Unity Catalog</strong>:" },
  'tech_s4_vol_tbl': { en: "<tr><th>File in Volume</th><th>Lakebase Table</th><th>Purpose</th><th>Primary Key</th></tr>\n<tr><td><code>fornecedores_especiais.csv</code></td><td><code>fornecedores_especiais</code></td><td>Suppliers with special procurement terms</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>fornecedores_nao_negociaiveis.csv</code></td><td><code>fornecedores_nao_negociaveis</code></td><td>Non-negotiable suppliers (automatic orders)</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>fornecedores_sem_oc.csv</code></td><td><code>fornecedores_sem_oc</code></td><td>Suppliers permitted without PO</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv</code></td><td><code>compradores_funcionais</code></td><td>Official buyer mapping by area and unit</td><td><code>usuario_oracle</code></td></tr>\n<tr><td><code>backups/*.csv</code></td><td>—</td><td>Timestamped change history generated on each save</td><td>—</td></tr>", es: "<tr><th>Archivo en el Volumen</th><th>Tabla Lakebase</th><th>Finalidad</th><th>Clave Primaria</th></tr>\n<tr><td><code>fornecedores_especiais.csv</code></td><td><code>fornecedores_especiais</code></td><td>Proveedores con tratamiento especial de compras</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>fornecedores_nao_negociaiveis.csv</code></td><td><code>fornecedores_nao_negociaveis</code></td><td>Proveedores no negociables (compras automáticas)</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>fornecedores_sem_oc.csv</code></td><td><code>fornecedores_sem_oc</code></td><td>Proveedores autorizados sin OC</td><td><code>cod_fornecedor_oracle</code></td></tr>\n<tr><td><code>COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv</code></td><td><code>compradores_funcionais</code></td><td>Mapeo oficial de compradores por área y unidad</td><td><code>usuario_oracle</code></td></tr>\n<tr><td><code>backups/*.csv</code></td><td>—</td><td>Historial de cambios con marca de tiempo generado en cada guardado</td><td>—</td></tr>" },
  'tech_s4_vol_flow_ttl': { en: "How Real-Time Updates Work (Zero Deploy)", es: "Cómo Funciona la Actualización en Tiempo Real (Zero Deploy)" },
  'tech_s4_vol_flow_diag': { en: "1. User edits / registers in \"Master Data Sheets\" tab and clicks \"Save\"\n   │\n   ├─▶ 2. Timestamped backup write to /Volumes/.../backups/{table}_backup_{ts}.csv\n   ├─▶ 3. Official CSV overwrite in Volume (/Volumes/.../{table}.csv)\n   ├─▶ 4. Atomic sync to corresponding Lakebase table (TRUNCATE + INSERT)\n   └─▶ 5. Background recalculation of business flags (without locking UI)\n   │\n   ▼\nResult: The App reflects new data IMMEDIATELY (without code redeployment!)", es: "1. Usuario edita / registra en la pestaña \"Registro Planillas\" y hace clic en \"Guardar\"\n   │\n   ├─▶ 2. Grabación de Backup con fecha/hora en /Volumes/.../backups/{tabla}_backup_{ts}.csv\n   ├─▶ 3. Sobrescritura del CSV oficial en el Volumen (/Volumes/.../{tabla}.csv)\n   ├─▶ 4. Sincronización atómica en la tabla correspondiente de Lakebase (TRUNCATE + INSERT)\n   └─▶ 5. Recálculo en segundo plano de los flags de negocio (sin congelar la pantalla)\n   │\n   ▼\nResultado: ¡La App refleja los nuevos datos INMEDIATAMENTE (sin necesidad de deploy de código!)" },
  'tech_s4_vol_flow_p': { en: "<strong>Why is no deploy required?</strong> Bundle deployment (<code>databricks bundle deploy</code> / <code>databricks apps deploy</code>) serves exclusively to update application source code (Python/HTML/JS). Portal data is read dynamically from Lakebase and Volume on every web request, ensuring instant synchronization.", es: "<strong>¿Por qué no requiere deploy?</strong> El deploy de bundles (<code>databricks bundle deploy</code> / <code>databricks apps deploy</code>) sirve exclusivamente para actualizar el código fuente de la aplicación (Python/HTML/JS). Los datos consumidos por el portal se leen dinámicamente de Lakebase y del Volumen en cada solicitud web, garantizando sincronización instantánea." },
  'tech_s5_ttl': { en: "<span class=\"sec-num\">5</span> Business Rules", es: "<span class=\"sec-num\">5</span> Reglas de Negocio" },
  'tech_s5_cent_ttl': { en: "Centralization Classification", es: "Clasificación de Centralización" },
  'tech_s5_cent_tbl': { en: "<tr><th>Condition</th><th>Result</th></tr>\n<tr><td>PO type <code>BLANKET</code></td><td><strong>CENTRALIZED</strong></td></tr>\n<tr><td>PO type <code>STANDARD</code> with line value ≥ R$ 30,000 made by Procurement buyers</td><td><strong>CENTRALIZED</strong></td></tr>\n<tr><td>PO with referenced purchase agreement (or source agreement)</td><td><strong>CENTRALIZED</strong></td></tr>\n<tr><td>None of the above</td><td><strong>DECENTRALIZED</strong></td></tr>", es: "<tr><th>Condición</th><th>Resultado</th></tr>\n<tr><td>OC tipo <code>BLANKET</code></td><td><strong>CENTRALIZADO</strong></td></tr>\n<tr><td>OC tipo <code>STANDARD</code> con valor de línea ≥ R$ 30.000 realizada por compradores de Compras</td><td><strong>CENTRALIZADO</strong></td></tr>\n<tr><td>OC con acuerdo de compra (o acuerdo de origen) referenciado</td><td><strong>CENTRALIZADO</strong></td></tr>\n<tr><td>Ninguna de las anteriores</td><td><strong>DESCENTRALIZADO</strong></td></tr>" },
  'tech_s5_cent_alert': { en: "⚠️ <span>The current code uses exact equality (<code>= 'Compras'</code>), not <code>LIKE</code>. Currently only the value <code>'Compras'</code> exists (93 records). If new values containing \"Compras\" are registered, evaluate updating <code>app.py</code> (<code>_EXCL_COMPRAS_OCS</code>).</span>", es: "⚠️ <span>El código actual utiliza igualdad exacta (<code>= 'Compras'</code>), no <code>LIKE</code>. Hoy solo existe el valor <code>'Compras'</code> (93 registros). Si se registran nuevos valores que contengan \"Compras\", evaluar la actualización en <code>app.py</code> (<code>_EXCL_COMPRAS_OCS</code>).</span>" },
  'tech_s5_grp_ttl': { en: "Purchasing Group", es: "Grupo de Compras" },
  'tech_s5_grp_tbl': { en: "<tr><th>Condition</th><th>Group</th></tr>\n<tr><td>Item starts with \"A\" or \"B\"</td><td><strong>DIRECT</strong></td></tr>\n<tr><td>No item + created by <code>BBAPPA0001</code></td><td><strong>COMMERCIAL</strong></td></tr>\n<tr><td>No item (others)</td><td><strong>INDIRECT</strong></td></tr>", es: "<tr><th>Condición</th><th>Grupo</th></tr>\n<tr><td>Ítem comienza con \"A\" o \"B\"</td><td><strong>DIRECTOS</strong></td></tr>\n<tr><td>Sin ítem + creado por <code>BBAPPA0001</code></td><td><strong>COMERCIAL</strong></td></tr>\n<tr><td>Sin ítem (demás)</td><td><strong>INDIRECTOS</strong></td></tr>" },
  'tech_s5_bu_ttl': { en: "Company", es: "Empresa" },
  'tech_s5_bu_tbl': { en: "<tr><th>Oracle BU Code</th><th>Company</th></tr>\n<tr><td><code>300000002033035</code></td><td>BB (Bimbo Brasil)</td></tr>\n<tr><td><code>300000002033048</code></td><td>BQ (Bimbo QSR)</td></tr>", es: "<tr><th>Código BU Oracle</th><th>Empresa</th></tr>\n<tr><td><code>300000002033035</code></td><td>BB (Bimbo Brasil)</td></tr>\n<tr><td><code>300000002033048</code></td><td>BQ (Bimbo QSR)</td></tr>" },
  'tech_s5_sav_ttl': { en: "Price Variance / Savings Calculation", es: "Cálculo de Aumento/Descuento (Savings)" },
  'tech_s5_sav_p': { en: "<p>• <strong>Unit Price Variance</strong> = previous price − current invoice price</p>\n<p>• <strong>Price Variance %</strong> = (Unit Variance / previous price) × 100</p>\n<p>• Sanity filter: only considers <code>variances in the 0% to 100% range</code></p>\n<p>• <strong>Total Savings</strong> = <code>Net Value × Variance % / 100</code></p>", es: "<p>• <strong>Aumento/Descuento unitario</strong> = precio anterior − precio actual de la factura</p>\n<p>• <strong>Aumento/Descuento %</strong> = (Aumento/Descuento unitario / precio anterior) × 100</p>\n<p>• Filtro de cordura: solo considera <code>aumentos o descuentos en el rango de 0% a 100%</code></p>\n<p>• <strong>Saving total</strong> = <code>Valor Neto × Aumento/Descuento / 100</code></p>" },
  'tech_s5_term_ttl': { en: "Weighted Payment Terms", es: "Plazo de Pago Ponderado" },
  'tech_s5_term_p': { en: "<p><code>Average term = SUM(Term X Net Value) / SUM(Net Value)</code></p>", es: "<p><code>Plazo promedio = SUM(Plazo X Valor neto) / SUM(Valor neto)</code></p>" },
  'tech_s5_yoy_ttl': { en: "YoY Comparison in KPIs", es: "Comparación YoY en los KPIs" },
  'tech_s5_yoy_p': { en: "<p>• <strong>Year + Month</strong>: compares with previous month, capped at the same day (if current month)</p>\n<p>• <strong>Year only</strong>: compares current year to date vs. previous year to the same date</p>", es: "<p>• <strong>Año + Mes</strong>: compara con el mes anterior, limitado al mismo día (si es mes en curso)</p>\n<p>• <strong>Solo año</strong>: compara el año actual hasta hoy vs. año anterior hasta la misma fecha</p>" },
  'tech_s5_lt_ttl': { en: "Lead Time & Invoicing Milestones (4 stages)", es: "Lead Time y Fases de Facturación (4 etapas)" },
  'tech_s5_lt_tbl': { en: "<tr><th>Stage / Milestone</th><th>From → To</th></tr>\n<tr><td>1. Approved Requisition → Order Issued</td><td><code>requisicoes.DT_APROVACAO</code> → <code>ordens_compra.DATA_OC</code></td></tr>\n<tr><td>2. Order Issued → Order Approved</td><td><code>ordens_compra.DATA_OC</code> → <code>ordens_compra.DT_APROVACAO</code></td></tr>\n<tr><td>3. Order Approved → 1st Invoice (Invoicing Initiated)</td><td><code>ordens_compra.DT_APROVACAO</code> → <code>MIN(notas_ri.DATA_LANCAMENTO)</code></td></tr>\n<tr><td>4. 1st Invoice → Invoicing Completion (100% Invoiced)</td><td><code>MIN(notas_ri.DATA_LANCAMENTO)</code> → <code>MAX(notas_ri.DATA_LANCAMENTO)</code></td></tr>", es: "<tr><th>Etapa / Hito</th><th>De → Para</th></tr>\n<tr><td>1. Requisición Aprobada → Pedido Emitido</td><td><code>requisicoes.DT_APROVACAO</code> → <code>ordens_compra.DATA_OC</code></td></tr>\n<tr><td>2. Pedido Emitido → Pedido Aprobado</td><td><code>ordens_compra.DATA_OC</code> → <code>ordens_compra.DT_APROVACAO</code></td></tr>\n<tr><td>3. Pedido Aprobado → 1ª Factura (Facturación Iniciada)</td><td><code>ordens_compra.DT_APROVACAO</code> → <code>MIN(notas_ri.DATA_LANCAMENTO)</code></td></tr>\n<tr><td>4. 1ª Factura → Conclusión de Facturación (100% Facturado)</td><td><code>MIN(notas_ri.DATA_LANCAMENTO)</code> → <code>MAX(notas_ri.DATA_LANCAMENTO)</code></td></tr>" },
  'tech_s5_excl_ttl': { en: "Exclusion of Employee Expenses/Advances (RGB / ADVRGB) and Payroll (FOPAG)", es: "Exclusión de Gastos/Anticipos de Empleados (RGB / ADVRGB) y Nómina (FOPAG)" },
  'tech_s5_excl_p': { en: "<p>Expense and advance invoices from <strong>Oracle Expenses (EXM / RDV)</strong> and payroll invoices are <strong>excluded at the source</strong> from the procurement database (<code>vw_notas_ri.sql</code>, ETL pipeline, and backend):</p>\n<p>• <strong>Employee Reimbursements</strong>: <code>NOTA_FISCAL NOT LIKE '%RGB%'</code> (e.g. <code>RGBRBBR0007...</code>, <code>RGBRQSR...</code> — no commercial vendor, no PO).</p>\n<p>• <strong>Travel Cash Advances</strong>: <code>NOTA_FISCAL NOT LIKE 'ADV%'</code> (e.g. <code>ADVRGBRBBR0008...</code>, <code>ADVRGBRQSR0006...</code> — cash advances to employees).</p>\n<p>• <strong>Payroll</strong>: <code>NOTA_FISCAL NOT LIKE '%FOPAG%'</code>.</p>\n<p><em>Rationale:</em> Employee travel and operational expenses (meals, mileage, tolls, cash advances) and payroll are disbursements to physical persons/employees, not corporate procurement managed by Compras. Retaining them distorts Net Spend, inflates \"Notas sem OC\", and skews \"Decentralized\" spend.</p>", es: "<p>Las facturas de gastos y anticipos de empleados originadas en <strong>Oracle Expenses (EXM / RDV)</strong> y las de nómina están <strong>excluidas en el origen</strong> de la base de compras (<code>vw_notas_ri.sql</code>, pipeline ETL y backend):</p>\n<p>• <strong>Reembolsos de Empleados</strong>: <code>NOTA_FISCAL NOT LIKE '%RGB%'</code> (ej: <code>RGBRBBR0007...</code>, <code>RGBRQSR...</code> — sin proveedor comercial y sin OC).</p>\n<p>• <strong>Anticipos de Viaje</strong>: <code>NOTA_FISCAL NOT LIKE 'ADV%'</code> (ej: <code>ADVRGBRBBR0008...</code>, <code>ADVRGBRQSR0006...</code> — anticipos de caja para viajes a colaboradores).</p>\n<p>• <strong>Nómina</strong>: <code>NOTA_FISCAL NOT LIKE '%FOPAG%'</code>.</p>\n<p><em>Motivo:</em> Los gastos de viaje/personales de colaboradores (comidas, kilometraje, peajes, anticipos) y nómina son pagos a personas físicas que no constituyen compras corporativas administradas por Compras. Mantenerlas distorsionaría el Spend Neto, inflaría \"Notas sem OC\" y generaría un falso volumen \"Descentralizado\".</p>" },
  'tech_s6_ttl': { en: "<span class=\"sec-num\">6</span> Governance and Security", es: "<span class=\"sec-num\">6</span> Gobernanza y Seguridad" },
  'tech_s6_tbl': { en: "<tr><th>Component</th><th>Access</th><th>Type</th></tr>\n<tr><td>App compras-360 (URL)</td><td>Databricks Apps Permissions</td><td>OAuth via Databricks</td></tr>\n<tr><td>Lakebase PostgreSQL</td><td>Service Principal <code>872976ee-3cee-44ca-b379-b95ca3c728e0</code></td><td>OAuth Token (refresh 45 min)</td></tr>\n<tr><td>ETL Notebook</td><td>Users with access to shared folder</td><td>Workspace permissions</td></tr>\n<tr><td>Oracle Cloud (source)</td><td>Catalog <code>cat_ocloud_r5_dv</code></td><td>Unity Catalog ACL</td></tr>\n<tr><td>Unity Catalog Volume</td><td>Volume <code>cat_dnabb_dv.grobbcompr_cz.compras_360</code></td><td>READ_VOLUME / WRITE_VOLUME ACL</td></tr>", es: "<tr><th>Componente</th><th>Acceso</th><th>Tipo</th></tr>\n<tr><td>App compras-360 (URL)</td><td>Permisos Databricks Apps</td><td>OAuth vía Databricks</td></tr>\n<tr><td>Lakebase PostgreSQL</td><td>Service Principal <code>872976ee-3cee-44ca-b379-b95ca3c728e0</code></td><td>Token OAuth (refresh 45 min)</td></tr>\n<tr><td>Notebook ETL</td><td>Usuarios con acceso a carpeta compartida</td><td>Permisos de Workspace</td></tr>\n<tr><td>Oracle Cloud (fuente)</td><td>Catálogo <code>cat_ocloud_r5_dv</code></td><td>Unity Catalog ACL</td></tr>\n<tr><td>Volumen Unity Catalog</td><td>Volumen <code>cat_dnabb_dv.grobbcompr_cz.compras_360</code></td><td>READ_VOLUME / WRITE_VOLUME ACL</td></tr>" },
  'tech_s7_ttl': { en: "<span class=\"sec-num\">7</span> Runbook", es: "<span class=\"sec-num\">7</span> Runbook" },
  'tech_s7_p1_ttl': { en: "Outdated Data", es: "Datos desactualizados" },
  'tech_s7_p1_body': { en: "<p>The <strong>ETL Compras 360 - Lakebase Daily</strong> job runs automatically at 06:00 (Brasilia). If data looks outdated:</p>\n<p>1. Check in Jobs if last run succeeded (Job ID <code>357960921780603</code>) → 2. If failed: open notebook <code>compras_360_lakebase_etl</code> and run manually → 3. Check for \"ETL COMPLETO\" in output → 4. If extraction fails: verify access to <code>cat_ocloud_r5_dv</code></p>", es: "<p>El job <strong>ETL Compras 360 - Lakebase Daily</strong> se ejecuta automáticamente a las 06:00 (Brasilia). Si los datos parecen antiguos:</p>\n<p>1. Verificar en Jobs si la última ejecución fue exitosa (Job ID <code>357960921780603</code>) → 2. Si falló: abrir el notebook <code>compras_360_lakebase_etl</code> y ejecutar manualmente → 3. Verificar \"ETL COMPLETO\" en la salida → 4. Si falla en la extracción: verificar acceso a <code>cat_ocloud_r5_dv</code></p>" },
  'tech_s7_p2_ttl': { en: "App won't open / 5xx error", es: "App no abre / error 5xx" },
  'tech_s7_p2_body': { en: "<p>1. Apps → compras-360 → check status → 2. If STOPPED: Start → 3. If RUNNING with error: check logs → 4. Error \"Token refresh failed\": re-run cell 6 of ETL (grants)</p>", es: "<p>1. Apps → compras-360 → verificar estado → 2. Si STOPPED: Start → 3. Si RUNNING con error: verificar logs → 4. Error \"Token refresh failed\": re-ejecutar celda 6 del ETL (grants)</p>" },
  'tech_s7_p3_ttl': { en: "Data looks incorrect", es: "Datos parecen incorrectos" },
  'tech_s7_p3_body': { en: "<p>Connect to Lakebase and validate: <code>SELECT COUNT(*) FROM compras.notas_ri</code> (∼400K), <code>compras.ordens_compra</code> (∼260K), <code>compras.requisicoes</code> (∼90K). If discrepant: re-run ETL.</p>", es: "<p>Conectar a Lakebase y validar: <code>SELECT COUNT(*) FROM compras.notas_ri</code> (∼400K), <code>compras.ordens_compra</code> (∼260K), <code>compras.requisicoes</code> (∼90K). Si es discrepante: re-ejecutar ETL.</p>" },
  'tech_s7_p4_ttl': { en: "New special / non-negotiable supplier", es: "Nuevo proveedor especial / no negociable" },
  'tech_s7_p4_body': { en: "<p>Edit in \"Master Data Sheets\" tab directly in web app (or update Volume CSV in <code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>) → Changes apply in real time without restart.</p>", es: "<p>Editar en la pestaña \"Registro Planillas\" directamente en la app web (o actualizar el CSV en el Volumen <code>cat_dnabb_dv.grobbcompr_cz.compras_360</code>) → Cambios en tiempo real sin reiniciar.</p>" },
  'tech_s7_p5_ttl': { en: "Deploying a new version", es: "Deploy de nueva versión" },
  'tech_s7_p5_body': { en: "<p>Edit code in <code>/src/app/</code> → CLI: <code>databricks bundle deploy -t prod && databricks apps deploy compras-360</code></p>", es: "<p>Editar código en <code>/src/app/</code> → CLI: <code>databricks bundle deploy -t prod && databricks apps deploy compras-360</code></p>" }
};

/* ═══════════════════════════════════════════════════════════════════
   MONTH NAMES
   ═══════════════════════════════════════════════════════════════════ */
var _MONTHS_I18N = {
  pt: ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'],
  en: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  es: ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
};

/** Returns localized month abbreviations array. */
function getMonths() { return _MONTHS_I18N[_currentLang] || _MONTHS_I18N.pt; }

/* ═══════════════════════════════════════════════════════════════════
   CORE TRANSLATION API
   ═══════════════════════════════════════════════════════════════════ */

/**
 * Translate a Portuguese text string to the current language.
 * Returns the original text if no translation is found or lang is PT.
 */
function t(ptText) {
  if (_currentLang === 'pt') return ptText;
  var entry = _DICT[ptText];
  return (entry && entry[_currentLang]) ? entry[_currentLang] : ptText;
}

/**
 * Translate a template string with {placeholder} replacements.
 * Usage: tt('Spend está {pct}% {dir}', {pct: 5.2, dir: t('acima')})
 */
function tt(ptTemplate, replacements) {
  var text = t(ptTemplate);
  if (replacements) {
    Object.keys(replacements).forEach(function(k) {
      text = text.replace('{' + k + '}', replacements[k]);
    });
  }
  return text;
}

/** Get current language code. */
function getLang() { return _currentLang; }

/** Get locale string for number formatting. */
function _getLocale() {
  return _currentLang === 'en' ? 'en-US' : _currentLang === 'es' ? 'es-MX' : 'pt-BR';
}

/**
 * Localized number formatter (replaces per-page fmt function).
 * Handles currency, percentage, days, and plain numbers.
 */
function fmtI18n(v, type) {
  if (type === undefined) type = 'currency';
  if (v == null || isNaN(v)) return '--';
  var abs = Math.abs(v);
  var loc = _getLocale();
  var bi = t('Bi');
  var mi = t('Mi');
  var k  = t('mil');
  var d  = t('dias');
  if (type === 'currency') {
    if (abs >= 1e9) return 'R$ ' + (v/1e9).toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + ' ' + bi;
    if (abs >= 1e6) return 'R$ ' + (v/1e6).toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + ' ' + mi;
    if (abs >= 1e3) return 'R$ ' + (v/1e3).toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + ' ' + k;
    return 'R$ ' + v.toLocaleString(loc,{minimumFractionDigits:0,maximumFractionDigits:0});
  }
  if (type === 'pct') return v.toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + '%';
  if (type === 'pp') {
    var sign = v > 0 ? '+' : '';
    return sign + v.toLocaleString(loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + ' pp';
  }
  if (type === 'days') return Math.round(v) + ' ' + d;
  return v.toLocaleString(loc);
}

/** Localized percentage formatter (e.g. 93,4% in PT, 93.4% in EN). */
function fmtPct(v, decimals) {
  if (v == null || isNaN(v)) return '--';
  var dec = decimals !== undefined ? decimals : 1;
  var loc = _getLocale();
  return Number(v).toLocaleString(loc, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + '%';
}

/** Localized percentage-point variation formatter (e.g. +13,4 pp in PT, +13.4 pp in EN). */
function fmtPp(v, decimals) {
  if (v == null || isNaN(v)) return '--';
  var dec = decimals !== undefined ? decimals : 1;
  var loc = _getLocale();
  var num = Number(v);
  var sign = num > 0 ? '+' : '';
  return sign + num.toLocaleString(loc, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + ' pp';
}

/* ═══════════════════════════════════════════════════════════════════
   SET LANGUAGE
   ═══════════════════════════════════════════════════════════════════ */
function setLang(lang) {
  if (['pt','en','es'].indexOf(lang) === -1) return;
  _currentLang = lang;
  localStorage.setItem('portalCompras_lang', lang);
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : lang;
  _translateStaticContent();
  _updateLangButtons();
  // Notify page scripts to rebuild dynamic content (charts, KPIs)
  document.dispatchEvent(new CustomEvent('langChange', { detail: { lang: lang } }));
}

/* ═══════════════════════════════════════════════════════════════════
   STATIC CONTENT TRANSLATION
   Uses selector-based text matching. Stores originals in
   data-i18n-orig so switching back to PT restores perfectly.
   ═══════════════════════════════════════════════════════════════════ */
var _SELECTORS = [
  '.nav-link', '.nav-crumb', '.nav-page-title',
  '.fr-kpi-lbl', '.fr-chart-ttl', '.card-title', '.card-subtitle',
  '.fg label',
  '.mc-title', '.mc-desc', '.mc-features li span:last-child', '.mc-open',
  '.hero-page-title', '.portal-badge span:last-child', '.guia-btn span', '.cadastros-btn span',
  '.lt-node-label', '.lt-node-sub', '.lt-count-lbl', '.lt-dur-unit',
  '.tbl thead th',
  '.kpi-month-delta', '.kpi-meta-line', '.kpi-sub',
  '.exc-btn', '.rpt-btn',
  '.tab-btn',
  '.spend-toggle-btn', '.cat-tipo-btn',
  '.dev-legend-item',
  '.abc-info span',
  '.abc-table th',
  '.hbar-legend-item',
  '.pvr-header span', '.pvr-legend-item',
  '.overdue-header span',
  '.bucket-label',
  '.attention-title',
  '.impact-header span', '.impact-legend',
  '.card-note span',
  '.det-panel-title-txt', '.det-card-ttl', '.det-card-sub',
  '.det-check-item.all-item',
  '.ms-sel-all', '.ms-desel-all',
  '.i18n-text'
];

/** Selectors for button elements whose textContent should be translated. */
var _BTN_SELECTORS = [
  'button',
  '.orders-tbl thead th'
];

function _translateElementTextPreservingChildren(el) {
  var nodes = el.childNodes;
  var changed = false;
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].nodeType !== 3) continue;
    var raw = nodes[i].textContent;
    var txt = raw.trim();
    if (!txt || txt === '--') continue;
    var translated = t(txt);
    if (translated !== txt) {
      if (!el.hasAttribute('data-i18n-orig')) {
        el.setAttribute('data-i18n-orig', el.innerHTML);
      }
      nodes[i].textContent = raw.replace(txt, translated);
      changed = true;
    }
  }
  return changed;
}

function _translateStaticContent() {
  // ALWAYS restore originals first (fixes EN→ES by going PT→target)
  document.querySelectorAll('[data-i18n-orig]').forEach(function(el) {
    var orig = el.getAttribute('data-i18n-orig');
    // Use innerHTML when original contains HTML tags (SVG icons, etc.)
    if (orig.indexOf('<') !== -1) { el.innerHTML = orig; } else { el.textContent = orig; }
    el.removeAttribute('data-i18n-orig');
  });
  document.querySelectorAll('[data-i18n-html-orig]').forEach(function(el) {
    el.innerHTML = el.getAttribute('data-i18n-html-orig');
    el.removeAttribute('data-i18n-html-orig');
  });
  document.querySelectorAll('[data-i18n-title-orig]').forEach(function(el) {
    el.setAttribute('title', el.getAttribute('data-i18n-title-orig'));
    el.removeAttribute('data-i18n-title-orig');
  });
  document.querySelectorAll('[data-i18n-ph-orig]').forEach(function(el) {
    el.setAttribute('placeholder', el.getAttribute('data-i18n-ph-orig'));
    el.removeAttribute('data-i18n-ph-orig');
  });
  // If PT, we're done (originals restored)
  if (_currentLang === 'pt') return;

  // Translate [data-i18n] elements (full innerHTML replacement)
  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    var key = el.getAttribute('data-i18n');
    var entry = _HTML_I18N[key];
    if (entry && entry[_currentLang]) {
      if (!el.hasAttribute('data-i18n-html-orig')) {
        el.setAttribute('data-i18n-html-orig', el.innerHTML);
      }
      el.innerHTML = entry[_currentLang];
    }
  });

  // Translate elements matching safe selectors
  _SELECTORS.forEach(function(sel) {
    document.querySelectorAll(sel).forEach(function(el) {
      var hasElementChildren = Array.prototype.some.call(el.childNodes, function(node) {
        return node.nodeType === 1;
      });
      if (hasElementChildren) {
        if (_translateElementTextPreservingChildren(el)) return;
      }
      var text = el.textContent.trim();
      if (!text || text === '--') return;
      var translated = t(text);
      if (translated !== text) {
        if (!el.hasAttribute('data-i18n-orig')) {
          el.setAttribute('data-i18n-orig', el.textContent);
        }
        el.textContent = translated;
      }
    });
  });

  // Translate inline button text (skip buttons that only contain SVGs)
  _BTN_SELECTORS.forEach(function(sel) {
    document.querySelectorAll(sel).forEach(function(btn) {
      _translateElementTextPreservingChildren(btn);
    });
  });

  // Translate title attribute
  document.querySelectorAll('[title]').forEach(function(el) {
    var title = el.getAttribute('title');
    var translated = t(title);
    if (translated !== title) {
      if (!el.hasAttribute('data-i18n-title-orig')) {
        el.setAttribute('data-i18n-title-orig', title);
      }
      el.setAttribute('title', translated);
    }
  });

  // Translate page <title>
  var titleEl = document.querySelector('title');
  if (titleEl) {
    var titleText = titleEl.textContent.trim();
    var translatedTitle = t(titleText);
    if (translatedTitle !== titleText) {
      if (!titleEl.hasAttribute('data-i18n-orig')) {
        titleEl.setAttribute('data-i18n-orig', titleText);
      }
      titleEl.textContent = translatedTitle;
    }
  }

  // Translate search placeholders
  document.querySelectorAll('.ms-search, .ms-search-input, .det-search').forEach(function(el) {
    var ph = el.getAttribute('placeholder');
    if (ph) {
      var translated = t(ph);
      if (translated !== ph) {
        if (!el.hasAttribute('data-i18n-ph-orig')) {
          el.setAttribute('data-i18n-ph-orig', ph);
        }
        el.setAttribute('placeholder', translated);
      }
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════
   LANGUAGE SELECTOR INJECTION
   ═══════════════════════════════════════════════════════════════════ */
function _injectLangSelector() {
  var target = document.querySelector('.nav-actions') || document.querySelector('.hh-right');
  if (!target || target.querySelector('.lang-switcher')) return;

  var div = document.createElement('div');
  div.className = 'lang-switcher';
  div.innerHTML = ['pt','en','es'].map(function(l) {
    return '<button class="lang-btn' + (_currentLang === l ? ' active' : '') + '" onclick="setLang(\'' + l + '\')">' + l.toUpperCase() + '</button>';
  }).join('');
  target.insertBefore(div, target.firstChild);
}

function _updateLangButtons() {
  document.querySelectorAll('.lang-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.textContent.trim().toLowerCase() === _currentLang);
  });
}

/* ═══════════════════════════════════════════════════════════════════
   CHART.JS TRANSLATION HELPER
   After lang change, translate chart axis labels (month names).
   ═══════════════════════════════════════════════════════════════════ */
function translateChartMonths() {
  if (typeof Chart === 'undefined') return;
  var ptMonths = _MONTHS_I18N.pt;
  var newMonths = getMonths();
  document.querySelectorAll('canvas').forEach(function(canvas) {
    var chart = Chart.getChart(canvas);
    if (!chart || !chart.data.labels) return;
    chart.data.labels = chart.data.labels.map(function(label) {
      var idx = ptMonths.indexOf(label);
      if (idx !== -1) return newMonths[idx];
      // Also check other language months
      for (var lang in _MONTHS_I18N) {
        var mi = _MONTHS_I18N[lang].indexOf(label);
        if (mi !== -1) return newMonths[mi];
      }
      return label;
    });
    chart.update('none');
  });
}

/* ═══════════════════════════════════════════════════════════════════
   CSS INJECTION (language selector styles)
   ═══════════════════════════════════════════════════════════════════ */
(function() {
  var style = document.createElement('style');
  style.textContent = [
    '.lang-switcher { display:flex; gap:2px; margin-right:.6rem; border-radius:6px; overflow:hidden; border:1px solid rgba(148,163,184,.35); }',
    '.lang-btn { padding:.25rem .5rem; font-size:.65rem; font-weight:700; letter-spacing:.04em; background:transparent; border:none; color:rgba(203,213,225,.75); cursor:pointer; transition:all .15s; min-width:30px; text-align:center; }',
    '.lang-btn:hover { color:#f1f5f9; background:rgba(148,163,184,.15); }',
    '.lang-btn.active { background:rgba(59,130,246,.3); color:#93c5fd; }',
    '[data-theme="light"] .lang-switcher { border-color:rgba(38,53,118,.2); }',
    '[data-theme="light"] .lang-btn { color:#475569; }',
    '[data-theme="light"] .lang-btn:hover { color:#1e2433; background:rgba(38,53,118,.08); }',
    '[data-theme="light"] .lang-btn.active { background:rgba(29,78,216,.12); color:#1d4ed8; }',
    '[data-theme="light"] .navbar .lang-switcher { border-color:rgba(38,53,118,.2); background:rgba(38,53,118,.04); }',
    '[data-theme="light"] .navbar .lang-btn { color:#475569; }',
    '[data-theme="light"] .navbar .lang-btn:hover { color:#1e2433; background:rgba(38,53,118,.08); }',
    '[data-theme="light"] .navbar .lang-btn.active { background:#ffffff; color:#1d4ed8; box-shadow:0 1px 3px rgba(0,0,0,.12); }',
    '[data-theme="light"] .home-header .lang-switcher { border-color:rgba(148,163,184,.35); }',
    '[data-theme="light"] .home-header .lang-btn { color:rgba(203,213,225,.75); }',
    '[data-theme="light"] .home-header .lang-btn:hover { color:#f1f5f9; background:rgba(148,163,184,.15); }',
    '[data-theme="light"] .home-header .lang-btn.active { background:rgba(59,130,246,.3); color:#93c5fd; }'
  ].join('\n');
  document.head.appendChild(style);
})();

/* ═══════════════════════════════════════════════════════════════════
   AUTO-INIT
   ═══════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', function() {
  _injectLangSelector();
  if (_currentLang !== 'pt') {
    _translateStaticContent();
  }
});

// Also re-translate after dynamic content loads
document.addEventListener('langChange', function() {
  // Small delay to let page scripts rebuild their content first
  setTimeout(function() {
    _translateStaticContent();
    translateChartMonths();
    // Re-render filter dropdown trigger labels (Todos/Nenhum/N selecionados)
    if (typeof filters !== 'undefined') {
      try {
        Object.values(filters).forEach(function(ms) {
          if (ms && ms.updateLabel) ms.updateLabel();
        });
      } catch(e) {}
    }
  }, 350);
});
