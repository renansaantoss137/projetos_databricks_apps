# Instruções para Criar a Aba "GUIA" em Databricks Apps

> **Padrão de referência:** App [compras-360](https://compras-360-8674310331778219.19.azure.databricksapps.com)
> **Criado em:** Setembro/2026 | **Autor:** Renan Ferreira

---

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Estrutura de Arquivos](#2-estrutura-de-arquivos)
3. [Anatomia da Aba Guia](#3-anatomia-da-aba-guia)
4. [Passo a Passo de Implementação](#4-passo-a-passo-de-implementação)
5. [Tab 1 — Consulta Rápida](#5-tab-1--consulta-rápida)
6. [Tab 2 — Apresentação (Slide Deck)](#6-tab-2--apresentação-slide-deck)
7. [Tab 3 — Documentação Técnica](#7-tab-3--documentação-técnica)
8. [CSS e Design System](#8-css-e-design-system)
9. [JavaScript Necessário](#9-javascript-necessário)
10. [Integração com Navbar e App Principal](#10-integração-com-navbar-e-app-principal)
11. [Checklist de Lançamento](#11-checklist-de-lançamento)
12. [Template Completo (Copie e Adapte)](#12-template-completo-copie-e-adapte)

---

## 1. Visão Geral

A aba **GUIA** é uma página HTML independente dentro do Databricks App que serve como **central de documentação** para os usuários. Ela contém **3 sub-abas** internas:

| Sub-aba | Objetivo | Público-alvo |
|---------|----------|--------------|
| **Consulta Rápida** | Manual do usuário: como acessar, módulos, filtros, FAQ, contatos | Usuários finais |
| **Apresentação** | Deck de slides navegável (com modo fullscreen) para reuniões | Gestores / Stakeholders |
| **Documentação Técnica** | Arquitetura, modelo de dados, regras de negócio, runbook | Desenvolvedores / Suporte |

A página é **100% estática** (sem chamadas de API), usa o **mesmo design system** (CSS) do app principal, e suporta **dark/light mode**.

---

## 2. Estrutura de Arquivos

```
app/
├── app.py                # Backend Flask (serve arquivos estáticos)
├── app.yaml              # Configuração do Databricks App
├── styles.css            # CSS global compartilhado
├── i18n.js               # (Opcional) Internacionalização
├── filters-shared.js     # (Opcional) Filtros cascateados
├── index.html            # Home page
├── guia.html             # ★ A ABA GUIA (este documento explica como criar)
├── modulo1.html          # Outros módulos do app...
├── modulo2.html
└── logo.png              # Assets visuais
```

**Ponto-chave:** O `guia.html` é servido pelo Flask como arquivo estático. No `app.py`, basta ter:

```python
app = Flask(__name__, static_folder='.')
```

E qualquer `.html` na raiz do app fica acessível via URL diretamente (ex: `/guia.html`).

---

## 3. Anatomia da Aba Guia

A página `guia.html` tem esta estrutura macro:

```
┌─────────────────────────────────────────────┐
│  NAVBAR (igual a todas as páginas do app)     │
├─────────────────────────────────────────────┤
│  TAB BAR                                      │
│  ┌──────────────┬───────────────┬───────────┐│
│  │Consulta Ráp. │ Apresentação  │ Doc Técn. ││
│  └──────────────┴───────────────┴───────────┘│
├─────────────────────────────────────────────┤
│                                               │
│  CONTEÚDO DA TAB ATIVA                        │
│  (Referência / Slides / Técnica)              │
│                                               │
└─────────────────────────────────────────────┘
```

---

## 4. Passo a Passo de Implementação

### 4.1. Criar o arquivo `guia.html`

Crie o arquivo na raiz do diretório do app (ao lado de `app.py`).

### 4.2. Estrutura HTML base

```html
<!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Guia do Usuário | SEU APP</title>
  <link rel="stylesheet" href="styles.css">
  <!-- Opcional: i18n e filtros compartilhados -->
  <script src="i18n.js"></script>
  <script src="filters-shared.js"></script>
  <style>
    /* Estilos específicos da página Guia — veja seção 8 */
  </style>
</head>
<body class="fr-page">

  <!-- NAVBAR (copie a navbar padrão do seu app) -->
  <nav class="navbar">
    <!-- ... conteúdo da navbar ... -->
  </nav>

  <div class="fr-content">

    <!-- TAB BAR -->
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('ref')" id="tab-ref">
        <!-- Ícone SVG livro -->
        Consulta Rápida
      </button>
      <button class="tab-btn" onclick="switchTab('pres')" id="tab-pres">
        <!-- Ícone SVG monitor -->
        Apresentação
      </button>
      <button class="tab-btn" onclick="switchTab('tech')" id="tab-tech">
        <!-- Ícone SVG engrenagem -->
        Documentação Técnica
      </button>
    </div>

    <!-- CONTEÚDO DAS TABS -->
    <div class="tab-content active" id="content-ref">
      <!-- Tab 1: Consulta Rápida -->
    </div>

    <div class="tab-content" id="content-pres">
      <!-- Tab 2: Apresentação -->
    </div>

    <div class="tab-content" id="content-tech">
      <!-- Tab 3: Documentação Técnica -->
    </div>

  </div>

  <script>
    /* Theme toggle + Tab switcher + Presentation controls */
  </script>
</body>
</html>
```

### 4.3. Adicionar link na Home e Navbar

**Na `index.html`** (Home), adicione um botão no header:

```html
<a href="guia.html" class="guia-btn" title="Guia do Usuário">
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
       stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="10"/>
    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/>
    <line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
  <span>Guia do Usuário</span>
</a>
```

**Na navbar de todas as páginas**, adicione o link:

```html
<a href="guia.html" class="nav-link">Guia</a>
```

E no `guia.html`, marque como ativo:

```html
<a href="guia.html" class="nav-link active">Guia</a>
```

---

## 5. Tab 1 — Consulta Rápida

Essa é a aba padrão (visível ao abrir a página). Contém 6 seções:

### 5.1. Introdução (Banner)

Card destacado com ícone + descrição curta do app:

```html
<div class="guide-intro">
  <div class="guide-intro-icon">📘</div>
  <p>Descrição curta do seu portal/app. O que ele faz,
     de onde vêm os dados, o que o usuário encontra aqui.</p>
</div>
```

### 5.2. Como Acessar (Seção 1)

Lista numerada com passos de acesso:

```html
<div class="guide-section">
  <h2><span class="sec-num">1</span> Como Acessar</h2>
  <ol class="steps">
    <li>Abra o navegador <strong>(Chrome ou Edge recomendado)</strong></li>
    <li>Acesse: <strong>https://SEU-APP.azure.databricksapps.com</strong></li>
    <li>Faça login com seu e-mail corporativo <strong>(@grupobimbo.com)</strong></li>
    <li>Escolha um dos módulos na tela inicial</li>
  </ol>
</div>
```

> **Padrão:** A classe `steps` usa `counter-increment` CSS para criar círculos numerados azuis automaticamente.

### 5.3. Módulos (Seção 2)

Grid de cards descrevendo cada módulo do app:

```html
<div class="guide-section">
  <h2><span class="sec-num">2</span> Os Módulos</h2>
  <div class="mod-grid">
    <div class="mod-card">
      <span class="mod-num">01</span>
      <div class="mod-info">
        <div class="mod-name">Nome do Módulo</div>
        <div class="mod-desc">Descrição curta do que esse módulo faz</div>
      </div>
    </div>
    <!-- Repita para cada módulo -->
  </div>
</div>
```

### 5.4. Como Usar os Filtros (Seção 3)

Lista dos filtros disponíveis com descrição:

```html
<div class="guide-section">
  <h2><span class="sec-num">3</span> Como Usar os Filtros</h2>
  <p>Descrição geral de como funcionam os filtros...</p>
  <ul>
    <li><strong>Filtro 1</strong> — o que filtra</li>
    <li><strong>Filtro 2</strong> — o que filtra</li>
  </ul>
  <p>💡 <strong>Dica:</strong> Informação útil sobre os filtros.</p>
</div>
```

### 5.5. Exemplos de Perguntas (Seção 4)

Cards de pergunta/resposta organizados por módulo:

```html
<div class="guide-section">
  <h2><span class="sec-num">4</span> Exemplos de Perguntas</h2>
  <h3>Nome do Módulo</h3>
  <div class="q-card">
    <div class="q-text">Pergunta que o usuário pode ter?</div>
    <div class="q-answer">→ Onde encontrar a resposta no app</div>
  </div>
</div>
```

> **Padrão:** A classe `q-card` aplica um ícone 💬 automaticamente via CSS `::before`.

### 5.6. FAQ (Seção 5)

Perguntas frequentes com respostas:

```html
<div class="guide-section">
  <h2><span class="sec-num">5</span> FAQ</h2>
  <div class="faq-item">
    <div class="faq-q">Pergunta frequente?</div>
    <div class="faq-a">Resposta clara e objetiva.</div>
  </div>
</div>
```

> **Padrão:** A classe `faq-q` aplica o ícone ❓ via CSS `::before`.

### 5.7. Contatos (Seção 6)

Grid de contatos por assunto:

```html
<div class="guide-section">
  <h2><span class="sec-num">6</span> A Quem Recorrer</h2>
  <div class="contact-grid">
    <div class="contact-card">
      <div class="cc-subject">Problemas técnicos no app</div>
      <div class="cc-who">
        <a href="mailto:email@grupobimbo.com">Nome do Responsável</a>
      </div>
    </div>
    <!-- Repita para cada tipo de contato -->
  </div>
</div>
```

---

## 6. Tab 2 — Apresentação (Slide Deck)

Deck de slides embutido na página com **navegação por setas**, **barra de progresso** e **modo fullscreen**.

### 6.1. Estrutura do Container

```html
<div class="tab-content" id="content-pres">
  <div class="pres-container" id="presContainer">

    <!-- Controles -->
    <div class="pres-controls">
      <button class="pres-nav-btn" onclick="presNav(-1)" id="presBack" title="Anterior">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <span class="pres-counter" id="presCounter">1 / 8</span>
      <button class="pres-nav-btn" onclick="presNav(1)" id="presNext" title="Próximo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <button class="pres-fullscreen-btn" onclick="toggleFullscreen()" id="presFS" title="Tela cheia">
        <!-- Ícone fullscreen SVG -->
        Tela cheia
      </button>
    </div>
    <div class="pres-progress">
      <div class="pres-progress-fill" id="presProgress" style="width:12.5%"></div>
    </div>

    <!-- SLIDES -->
    <div class="slide active" data-slide="1">
      <div class="slide-inner slide-hero">
        <!-- Slide de título -->
      </div>
    </div>

    <div class="slide" data-slide="2">
      <div class="slide-inner">
        <!-- Slide de conteúdo -->
      </div>
    </div>

    <!-- ... mais slides ... -->

  </div>
</div>
```

### 6.2. Tipos de Slide Disponíveis

| Tipo | Classe CSS | Uso |
|------|-----------|-----|
| **Hero** (título) | `.slide-inner.slide-hero` | Slide de abertura e fechamento (texto centralizado, título grande com gradiente) |
| **Conteúdo** | `.slide-inner` | Slide padrão com tag, título, subtítulo e corpo |
| **Split** | `.slide-split` dentro de `.slide-inner` | Conteúdo dividido em 2 colunas |

### 6.3. Elementos Visuais dos Slides

```html
<!-- Tag superior (categoria do slide) -->
<div class="slide-tag">Contexto</div>

<!-- Título do slide -->
<div class="slide-title">Título Principal</div>

<!-- Subtítulo -->
<div class="slide-subtitle">Descrição complementar do slide.</div>

<!-- Corpo do slide -->
<div class="slide-body">
  <p>Conteúdo com <strong>destaque</strong> e listas:</p>
  <ul>
    <li>Item 1</li>
    <li>Item 2</li>
  </ul>
</div>
```

### 6.4. Componentes Especiais para Slides

**Grid de KPIs:**
```html
<div class="slide-kpi-grid">
  <div class="slide-kpi">
    <div class="sk-val">📄</div>
    <div class="sk-lbl">Nome do KPI</div>
  </div>
</div>
```

**Lista de módulos:**
```html
<div class="slide-mod-list">
  <div class="slide-mod">
    <span class="sm-num">01</span>
    <div>
      <span class="sm-name">Nome</span>
      <span class="sm-desc">Descrição</span>
    </div>
  </div>
</div>
```

**Grid de benefícios:**
```html
<div class="slide-benefit-grid">
  <div class="slide-benefit">
    <div class="sb-icon">⏱️</div>
    <div class="sb-title">Título do Benefício</div>
    <div class="sb-desc">Descrição do benefício.</div>
  </div>
</div>
```

### 6.5. Roteiro Sugerido de Slides (8 slides)

| # | Título | Conteúdo |
|---|--------|----------|
| 1 | **Título do App** (Hero) | Nome do app + tagline |
| 2 | **O Problema** | Por que o app foi criado? Quais dores resolve? |
| 3 | **A Solução** | O que é o app, de onde vêm os dados |
| 4 | **Módulos** | Grid visual com todos os módulos |
| 5 | **Filtros** | Como funciona a interatividade |
| 6 | **Governança/Destaque** | Funcionalidade principal em detalhe |
| 7 | **Benefícios** | 4 cards com os ganhos obtidos |
| 8 | **Próximos Passos** (Hero) | CTA para começar a usar + contato |

---

## 7. Tab 3 — Documentação Técnica

Seções técnicas com estilo diferenciado (badges roxos em vez de azuis):

### 7.1. Seções Recomendadas

| # | Seção | Conteúdo |
|---|-------|----------|
| 1 | **Visão Geral** | Resumo técnico do app (stack, fonte de dados) |
| 2 | **Arquitetura** | Tabela de etapas (Extração → Carga → Consumo) + diagrama ASCII |
| 3 | **Modelo de Dados** | Tabelas principais e de lookup com colunas-chave |
| 4 | **Regras de Negócio** | Classificações, cálculos, comparações |
| 5 | **Módulos e APIs** | Mapeamento módulo → tabela → endpoints |
| 6 | **Governança e Segurança** | Permissões, OAuth, Service Principal |
| 7 | **Runbook** | Procedimentos para problemas comuns |

### 7.2. Componentes Específicos

**Seção técnica:**
```html
<div class="tech-section">
  <h2><span class="sec-num">1</span> Visão Geral</h2>
  <p>Descrição técnica...</p>
</div>
```

**Tabela técnica:**
```html
<table class="tech-table">
  <tr><th>Coluna 1</th><th>Coluna 2</th></tr>
  <tr><td><strong>Valor</strong></td><td><code>codigo</code></td></tr>
</table>
```

**Diagrama ASCII:**
```html
<div class="tech-diagram">Oracle Cloud
       │
       ▼
Lakebase PostgreSQL ──▶ Flask API ──▶ Frontend
</div>
```

**Alerta/Aviso:**
```html
<div class="tech-alert">
  ⚠️ <span>Texto do aviso importante.</span>
</div>
```

---

## 8. CSS e Design System

### 8.1. CSS Inline no `<style>` do `guia.html`

Todo o CSS específico da aba Guia fica dentro de um `<style>` no próprio `guia.html`. Isso evita poluir o `styles.css` global.

### 8.2. Variáveis CSS Utilizadas

O design system usa variáveis CSS definidas no `styles.css` global. As principais:

```css
/* Dark mode (padrão) */
--fr-bg:        #1e2433;      /* Fundo da página */
--fr-surface:   #282f3f;      /* Fundo de cards */
--fr-border:    rgba(100,116,139,0.2);  /* Bordas */
--fr-txt:       #E8F4FD;      /* Texto principal */
--fr-txt-soft:  #7a9dba;      /* Texto secundário */
--fr-input-bg:  #282f3f;      /* Fundo de inputs */
--fr-th-bg:     #323a4e;      /* Header de tabela */
--fr-th-txt:    #ffffff;      /* Texto do header */

/* Light mode (aplicado via [data-theme="light"]) */
--fr-bg:        #f0f4f8;
--fr-surface:   #ffffff;
--fr-txt:       #1e2433;
--fr-txt-soft:  #475569;
--fr-th-bg:     #263576;
```

### 8.3. CSS Essencial — Tab Switcher

```css
.tab-bar {
  display: flex; gap: 0;
  margin-bottom: 1.8rem;
  border-radius: 12px;
  overflow: hidden;
  border: 1.5px solid var(--fr-border);
  background: var(--fr-surface);
}
.tab-btn {
  flex: 1;
  padding: .7rem 1.2rem;
  font-size: .82rem; font-weight: 700;
  background: transparent; border: none;
  color: var(--fr-txt-soft);
  cursor: pointer;
  transition: all .2s;
  display: flex; align-items: center; justify-content: center; gap: .5rem;
}
.tab-btn:hover { background: rgba(59,130,246,.06); color: var(--fr-txt); }
.tab-btn.active {
  background: rgba(29,78,216,.15);
  color: #60a5fa;
  border-bottom: 2px solid #3b82f6;
}
.tab-btn svg { width: 18px; height: 18px; }
.tab-content { display: none; }
.tab-content.active { display: block; }
[data-theme="light"] .tab-btn.active {
  background: rgba(29,78,216,.08);
  color: #1d4ed8;
}
```

### 8.4. CSS Essencial — Consulta Rápida

```css
/* Seções do guia */
.guide-section { margin-bottom: 2rem; }
.guide-section h2 {
  font-size: 1.1rem; font-weight: 800;
  color: var(--fr-txt);
  border-bottom: 2px solid rgba(59,130,246,.3);
  padding-bottom: .4rem; margin-bottom: 1rem;
  display: flex; align-items: center; gap: .5rem;
}
.guide-section h2 .sec-num {
  background: #1d4ed8; color: #fff;
  font-size: .65rem; font-weight: 800;
  width: 24px; height: 24px;
  border-radius: 6px;
  display: inline-flex; align-items: center; justify-content: center;
}
.guide-section p, .guide-section li {
  font-size: .82rem; color: var(--fr-txt-soft); line-height: 1.7;
}
.guide-section strong { color: var(--fr-txt); }

/* Banner de introdução */
.guide-intro {
  background: linear-gradient(135deg, rgba(29,78,216,.12), rgba(59,130,246,.06));
  border: 1px solid rgba(59,130,246,.2);
  border-radius: 14px;
  padding: 1.2rem 1.5rem;
  margin-bottom: 2rem;
  display: flex; align-items: center; gap: 1rem;
}
.guide-intro-icon { font-size: 2rem; }
.guide-intro p { font-size: .88rem; color: var(--fr-txt); margin: 0; font-weight: 500; }

/* Steps numerados */
.steps { counter-reset: step; list-style: none; padding-left: 0; }
.steps li {
  counter-increment: step;
  position: relative; padding-left: 2.5rem;
  margin-bottom: .8rem; font-size: .82rem;
}
.steps li::before {
  content: counter(step);
  position: absolute; left: 0; top: 0;
  width: 24px; height: 24px; border-radius: 50%;
  background: #1d4ed8; color: #fff;
  font-size: .7rem; font-weight: 800;
  display: flex; align-items: center; justify-content: center;
}

/* Cards de módulo */
.mod-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: .8rem; }
.mod-card {
  background: var(--fr-surface); border: 1px solid var(--fr-border);
  border-radius: 10px; padding: .8rem 1rem;
  display: flex; align-items: flex-start; gap: .6rem;
}
.mod-num {
  background: #1d4ed8; color: #fff;
  font-size: .6rem; font-weight: 800;
  width: 22px; height: 22px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
.mod-info .mod-name { font-size: .78rem; font-weight: 700; color: var(--fr-txt); }
.mod-info .mod-desc { font-size: .68rem; color: var(--fr-txt-soft); }

/* Cards de pergunta */
.q-card {
  background: var(--fr-surface); border: 1px solid var(--fr-border);
  border-radius: 10px; padding: .8rem 1rem; margin-bottom: .6rem;
  transition: border-color .2s;
}
.q-card:hover { border-color: rgba(59,130,246,.4); }
.q-card .q-text {
  font-size: .82rem; font-weight: 600; color: var(--fr-txt);
  display: flex; align-items: flex-start; gap: .5rem;
}
.q-card .q-text::before { content: "\1F4AC"; flex-shrink: 0; }
.q-card .q-answer {
  font-size: .72rem; color: var(--fr-txt-soft);
  margin-top: .3rem; padding-left: 1.6rem;
}

/* FAQ */
.faq-item { margin-bottom: 1rem; }
.faq-q {
  font-size: .82rem; font-weight: 700; color: var(--fr-txt);
  display: flex; align-items: flex-start; gap: .4rem;
}
.faq-q::before { content: "\2753"; flex-shrink: 0; font-size: .75rem; }
.faq-a {
  font-size: .78rem; color: var(--fr-txt-soft);
  margin-top: .3rem; padding: .6rem .8rem .6rem 1.4rem;
  background: rgba(59,130,246,.04); border-radius: 8px;
}

/* Contatos */
.contact-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; }
.contact-card {
  background: var(--fr-surface); border: 1px solid var(--fr-border);
  border-radius: 10px; padding: .8rem 1rem;
}
.contact-card .cc-subject { font-size: .72rem; font-weight: 700; color: var(--fr-txt); }
.contact-card .cc-who { font-size: .72rem; color: var(--fr-txt-soft); }
.contact-card .cc-who a { color: #60a5fa; text-decoration: none; }
```

### 8.5. CSS Essencial — Documentação Técnica

```css
.tech-section { margin-bottom: 2rem; }
.tech-section h2 {
  font-size: 1.05rem; font-weight: 800; color: var(--fr-txt);
  border-bottom: 2px solid rgba(139,92,246,.3);  /* Roxo para diferenciar */
  padding-bottom: .4rem; margin-bottom: 1rem;
  display: flex; align-items: center; gap: .5rem;
}
.tech-section h2 .sec-num {
  background: #7c3aed; color: #fff;  /* Badge roxo */
  font-size: .65rem; font-weight: 800;
  width: 24px; height: 24px; border-radius: 6px;
  display: inline-flex; align-items: center; justify-content: center;
}
.tech-section h3 {
  font-size: .85rem; font-weight: 700; color: var(--fr-txt);
  margin: 1rem 0 .5rem; padding-left: .5rem;
  border-left: 3px solid #7c3aed;
}

/* Tabela técnica */
.tech-table {
  width: 100%; border-collapse: collapse;
  margin: .6rem 0 1rem; font-size: .75rem;
}
.tech-table th {
  text-align: left; padding: .5rem .6rem;
  font-size: .65rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .04em;
  color: var(--fr-th-txt); background: var(--fr-th-bg);
}
.tech-table th:first-child { border-radius: 6px 0 0 0; }
.tech-table th:last-child { border-radius: 0 6px 0 0; }
.tech-table td {
  padding: .5rem .6rem; color: var(--fr-txt-soft);
  border-bottom: 1px solid var(--fr-border);
}
.tech-table code {
  background: rgba(139,92,246,.1); color: #a78bfa;
  padding: 1px 5px; border-radius: 4px;
  font-size: .72rem; font-family: 'Fira Code', monospace;
}
[data-theme="light"] .tech-table th { background: #263576; }
[data-theme="light"] .tech-table code { background: rgba(139,92,246,.08); color: #6d28d9; }

/* Diagrama ASCII */
.tech-diagram {
  background: rgba(139,92,246,.05);
  border: 1px solid rgba(139,92,246,.15);
  border-radius: 10px;
  padding: 1rem 1.2rem;
  font-family: 'Fira Code', monospace;
  font-size: .72rem; color: var(--fr-txt-soft);
  line-height: 1.8; white-space: pre; overflow-x: auto;
}

/* Alerta técnico */
.tech-alert {
  background: rgba(251,191,36,.06);
  border: 1px solid rgba(251,191,36,.2);
  border-radius: 10px;
  padding: .7rem 1rem;
  font-size: .78rem; color: var(--fr-txt-soft);
  display: flex; align-items: flex-start; gap: .5rem;
}
.tech-alert strong { color: var(--fr-txt); }
```

### 8.6. CSS Essencial — Slides (Apresentação)

```css
/* Container e controles */
.pres-controls {
  display: flex; align-items: center; justify-content: center;
  gap: 1rem; margin-bottom: 1.2rem;
}
.pres-controls .pres-counter {
  font-size: .78rem; font-weight: 700;
  color: var(--fr-txt-soft); min-width: 80px; text-align: center;
}
.pres-nav-btn {
  width: 40px; height: 40px; border-radius: 50%;
  border: 1.5px solid var(--fr-border);
  background: var(--fr-surface); color: var(--fr-txt);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.pres-nav-btn:hover { background: rgba(59,130,246,.15); border-color: #3b82f6; }
.pres-nav-btn:disabled { opacity: .3; cursor: not-allowed; }
.pres-fullscreen-btn {
  padding: .4rem .9rem; border-radius: 8px;
  border: 1px solid rgba(59,130,246,.3);
  background: rgba(59,130,246,.1); color: #60a5fa;
  font-size: .72rem; font-weight: 700; cursor: pointer;
}
.pres-progress { height: 3px; background: var(--fr-border); border-radius: 3px; overflow: hidden; }
.pres-progress-fill {
  height: 100%; background: linear-gradient(90deg, #1d4ed8, #3b82f6);
  transition: width .4s ease; border-radius: 3px;
}

/* Slides */
.slide { display: none; animation: slideFadeIn .4s ease; }
.slide.active { display: flex; flex-direction: column; }
@keyframes slideFadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
.slide-inner {
  background: var(--fr-surface);
  border: 1px solid var(--fr-border);
  border-radius: 16px;
  padding: 2.5rem 3rem;
  min-height: 420px;
  display: flex; flex-direction: column; justify-content: center;
  box-shadow: 0 4px 24px rgba(0,0,0,.2);
}
.slide-tag {
  font-size: .6rem; font-weight: 800;
  text-transform: uppercase; letter-spacing: .12em;
  color: #3b82f6; margin-bottom: .6rem;
}
.slide-title { font-size: 1.8rem; font-weight: 900; line-height: 1.2; margin-bottom: .8rem; }
.slide-subtitle { font-size: 1rem; font-weight: 500; color: var(--fr-txt-soft); margin-bottom: 1.5rem; }

/* Hero slides */
.slide-hero { text-align: center; align-items: center; }
.slide-hero .slide-title {
  font-size: 2.5rem;
  background: linear-gradient(135deg, #60a5fa, #3b82f6, #1d4ed8);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}

/* Fullscreen */
.pres-container.fullscreen {
  position: fixed; inset: 0; z-index: 9999;
  background: var(--fr-bg);
  padding: 1.5rem 3rem; overflow-y: auto;
  display: flex; flex-direction: column;
}
.pres-container.fullscreen .slide-inner { min-height: calc(100vh - 140px); padding: 3rem 4rem; }
.pres-container.fullscreen .slide-hero .slide-title { font-size: 3.2rem; }

/* Light mode overrides */
[data-theme="light"] .slide-inner { background: #fff; border-color: rgba(38,53,118,.1); }
```

---

## 9. JavaScript Necessário

Cole este bloco `<script>` antes do `</body>` do `guia.html`:

```javascript
/* ═══ Theme Toggle ═══ */
const saved = localStorage.getItem('theme');
if (saved) document.documentElement.setAttribute('data-theme', saved);
function toggleTheme() {
  const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
}

/* ═══ Tab Switcher ═══ */
function switchTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  document.getElementById('content-' + id).classList.add('active');
}

/* ═══ Presentation Controls ═══ */
let currentSlide = 1;
const totalSlides = 8;  // Ajuste conforme o número de slides

function presNav(dir) {
  const next = currentSlide + dir;
  if (next < 1 || next > totalSlides) return;
  document.querySelector(`.slide[data-slide="${currentSlide}"]`).classList.remove('active');
  currentSlide = next;
  document.querySelector(`.slide[data-slide="${currentSlide}"]`).classList.add('active');
  updatePresUI();
}

function updatePresUI() {
  document.getElementById('presCounter').textContent = `${currentSlide} / ${totalSlides}`;
  document.getElementById('presProgress').style.width = `${(currentSlide / totalSlides) * 100}%`;
  document.getElementById('presBack').disabled = currentSlide === 1;
  document.getElementById('presNext').disabled = currentSlide === totalSlides;
}

function toggleFullscreen() {
  const c = document.getElementById('presContainer');
  c.classList.toggle('fullscreen');
  const isFS = c.classList.contains('fullscreen');
  document.getElementById('presFS').innerHTML = isFS
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg> Sair'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg> Tela cheia';
}

/* Keyboard navigation for presentation */
document.addEventListener('keydown', function(e) {
  if (!document.getElementById('content-pres').classList.contains('active')) return;
  if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); presNav(1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); presNav(-1); }
  if (e.key === 'Escape') {
    const c = document.getElementById('presContainer');
    if (c.classList.contains('fullscreen')) toggleFullscreen();
  }
});

updatePresUI();
```

---

## 10. Integração com Navbar e App Principal

### 10.1. O Flask serve a página automaticamente

Desde que `app.py` tenha `static_folder='.'`:
```python
app = Flask(__name__, static_folder='.')
```
A URL `https://SEU-APP.azure.databricksapps.com/guia.html` já funciona.

### 10.2. Navbar compartilhada

Copie exatamente a mesma navbar usada nas outras páginas do app. A estrutura padrão:

```html
<nav class="navbar">
  <a href="index.html" class="nav-logo"><img src="logo-dna.png" alt="Logo"></a>
  <div class="nav-title-area">
    <span class="nav-crumb">NOME DO APP</span>
    <span class="nav-page-title">Guia do Usuário</span>
  </div>
  <div class="nav-links">
    <a href="modulo1.html" class="nav-link">Módulo 1</a>
    <a href="modulo2.html" class="nav-link">Módulo 2</a>
    <!-- ... outros módulos ... -->
    <a href="guia.html" class="nav-link active">Guia</a>
  </div>
  <div class="nav-actions">
    <button class="theme-toggle" onclick="toggleTheme()" title="Alternar tema">
      <!-- SVGs de lua/sol para dark/light toggle -->
    </button>
  </div>
</nav>
```

### 10.3. Botão "Guia do Usuário" na Home

Adicione um botão estilizado no header da `index.html`:

```css
.guia-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: .35rem .8rem; border-radius: 8px;
  background: rgba(59,130,246,.1);
  border: 1px solid rgba(59,130,246,.25);
  color: #60a5fa; font-size: .72rem; font-weight: 600;
  text-decoration: none; transition: all .2s;
}
.guia-btn:hover {
  background: rgba(59,130,246,.2);
  border-color: rgba(59,130,246,.4);
}
```

---

## 11. Checklist de Lançamento

- [ ] Arquivo `guia.html` criado na raiz do app
- [ ] CSS inline no `<style>` do guia.html com todas as classes necessárias
- [ ] JavaScript de tabs, theme toggle e apresentação incluído
- [ ] **Tab 1 (Consulta Rápida):**
  - [ ] Banner de introdução com descrição do app
  - [ ] Seção "Como Acessar" com URL correta
  - [ ] Seção "Módulos" com todos os módulos listados
  - [ ] Seção "Filtros" com descrição de cada filtro
  - [ ] Seção "Exemplos de Perguntas" com Q&A por módulo
  - [ ] Seção "FAQ" com as 5+ perguntas mais comuns
  - [ ] Seção "Contatos" com responsáveis por assunto
- [ ] **Tab 2 (Apresentação):**
  - [ ] 6-8 slides cobrindo: problema, solução, módulos, interatividade, benefícios
  - [ ] Navegação por setas funcionando
  - [ ] Barra de progresso atualizada
  - [ ] Modo fullscreen funcionando (F11 ou botão)
  - [ ] Navegação por teclado (← → Space Esc)
- [ ] **Tab 3 (Documentação Técnica):**
  - [ ] Visão geral do stack
  - [ ] Arquitetura com diagrama
  - [ ] Modelo de dados com tabelas e colunas
  - [ ] Regras de negócio documentadas
  - [ ] Runbook para problemas comuns
- [ ] Link "Guia" adicionado na navbar de todas as páginas
- [ ] Botão "Guia do Usuário" adicionado na home page
- [ ] Dark/Light mode testado em todas as 3 tabs
- [ ] Deploy executado: `databricks apps deploy <app-name> --source-code-path <path>`

---

## 12. Template Completo (Copie e Adapte)

O template completo está no arquivo `guia.html` do app **compras-360**:

```
/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/app/guia.html
```

**Para usar como base para um novo app:**

1. **Copie** `guia.html` para o diretório do seu novo app
2. **Substitua** todo o conteúdo textual (nomes de módulos, perguntas, contatos, etc.)
3. **Adapte** a navbar para os links do seu app
4. **Atualize** os slides da apresentação para o contexto do novo app
5. **Reescreva** a documentação técnica (arquitetura, modelo de dados, regras)
6. **Teste** dark/light mode e navegação dos slides
7. **Deploy** o app

> **Dica:** Comece pela Tab 1 (Consulta Rápida) — é a mais simples e a que o
> usuário mais usa. A Tab 2 (Apresentação) é a mais impactante em reuniões.
> A Tab 3 (Documentação Técnica) pode ser preenchida aos poucos.

---

## Referência Visual (Paleta de Cores)

| Elemento | Cor (Dark) | Cor (Light) | Variável CSS |
|----------|-----------|-------------|--------------|
| Fundo da página | `#1e2433` | `#f0f4f8` | `--fr-bg` |
| Fundo de cards | `#282f3f` | `#ffffff` | `--fr-surface` |
| Texto principal | `#E8F4FD` | `#1e2433` | `--fr-txt` |
| Texto secundário | `#7a9dba` | `#475569` | `--fr-txt-soft` |
| Badge seção (Guia) | `#1d4ed8` | — | Azul |
| Badge seção (Técnica) | `#7c3aed` | — | Roxo |
| Destaque/ativo | `#3b82f6` / `#60a5fa` | `#1d4ed8` | — |
| Header de tabela | `#323a4e` | `#263576` | `--fr-th-bg` |

---

*Documento gerado a partir do app compras-360 — Bimbo Brasil / DNA*
