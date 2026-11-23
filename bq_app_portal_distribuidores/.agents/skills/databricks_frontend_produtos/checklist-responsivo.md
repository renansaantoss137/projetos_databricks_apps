# Verificação responsiva e de acabamento

Use antes de concluir. A verificação renderizada vale quando o ambiente permitir abrir o app; a estática é sempre obrigatória. Na entrega, registre o tipo de cada verificação (seção D).

## A. Renderizada

**Larguras:** 360 ou 390 (celular), 768 (tablet) e 1280 ou 1440 (desktop). Inclua 320 se o público usar aparelhos pequenos, e 844 × 390 (celular deitado) em telas com formulário ou gráfico.

Em cada largura:
- [ ] Sem rolagem horizontal da página (`document.documentElement.scrollWidth <= window.innerWidth`)
- [ ] Navegação alcançável e destino atual identificável
- [ ] Nenhum texto ou valor essencial truncado; nomes longos e valores grandes tratados
- [ ] Filtros, menus, modais e drawers abrem, cabem, rolam e fecham, e o foco volta ao gatilho
- [ ] Último conteúdo visível acima das barras fixas
- [ ] Gráficos legíveis, com valor acessível por toque ou teclado

Também confira:
- **Estados:** carregamento, vazio, erro, sem permissão, conteúdo longo, tema claro e escuro.
- **Teclado:** Tab percorre em ordem lógica, o foco fica sempre visível e Esc fecha overlays.
- **Zoom de 200%:** sem perda de conteúdo ou função.

## A2. Conferência de dados e rotas (sempre que houver app rodando)

- [ ] **Console limpo** em todas as telas: nenhum erro de JavaScript nem requisição falhando.
- [ ] **Mesmos valores de antes:** para os mesmos filtros, os KPIs de cada tela batem com a versão anterior à reformulação. Compare as duas versões no mesmo momento, porque os dados atualizam, e registre na matriz.
- [ ] **Componentes compartilhados em todas as rotas:** menu do app, trilho de navegação, logotipo e painel de filtros abrem e funcionam em cada tela, não só na Home. Teste clicando em cada rota.
- [ ] **Tema inteiro:** em cada tela, nos dois temas, nenhum trecho com cor do outro tema.

## B. Estática (sempre)

Rode o script abaixo sobre a pasta de frontend do app (HTML, CSS, JS e templates). Ele aponta **suspeitas, não veredictos**: confira cada achado no contexto antes de alterar.

- **Num notebook Databricks:** cole numa célula e chame `varrer("/Workspace/Users/<usuario>/<app>")`.
- **Num terminal:** salve como `varredura_frontend.py` e rode `python varredura_frontend.py <pasta>`.

```python
import re, sys
from pathlib import Path

EXTENSOES = {".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".vue", ".jinja", ".j2"}
IGNORAR = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}

# (regex por linha, mensagem)
POR_LINHA = [
    (r"(?<![\w-])(?:min-)?width\s*:\s*(\d{3,})px", "largura fixa >= 360px: confira se não estoura a página no celular"),
    (r"overflow-x\s*:\s*hidden", "overflow-x: hidden: confirme que não esconde overflow da página (html/body)"),
    (r"(?<![\d.])100vh", "100vh: em tela cheia e modais prefira 100dvh (com 100vh como fallback)"),
    (r"outline\s*:\s*(?:none|0)\b", "outline removido: garanta substituto em :focus-visible"),
    (r"user-scalable\s*=\s*no|maximum-scale\s*=\s*1(?:\.0)?\b", "viewport bloqueia zoom: remova user-scalable=no / maximum-scale=1"),
    (r"@latest", "CDN com @latest: fixe a versão"),
    (r"\.toFixed\(", "toFixed: se for exibição, use Intl.NumberFormat com o locale"),
    (r"toLocaleString\(\s*\)", "toLocaleString() sem locale: passe o locale explicitamente"),
    (r"R\$\s*['\"`]\s*\+|\+\s*['\"`]\s*R\$|R\$\s*\$\{", "moeda concatenada: use Intl.NumberFormat com style: 'currency'"),
    (r"<img(?![^>]*\balt=)[^>]*>", "<img> sem alt"),
    (r"<img(?![^>]*\bwidth=)[^>]*>", "<img> sem width/height declarados"),
    (r"<canvas(?![^>]*aria-label)[^>]*>", "<canvas> sem aria-label (gráfico sem descrição acessível)"),
    (r"<button(?![^>]*aria-label)[^>]*>\s*<(?:i|svg)\b[^>]*>\s*(?:</(?:i|svg)>\s*)?</button>", "botão só com ícone sem aria-label"),
]

CONTROLE = re.compile(r"\b(?:input|select|textarea)\b")
ALVO = re.compile(r"\b(?:button|btn|icon|nav|tab)\b", re.I)

def _blocos_css(texto):
    """Blocos CSS simples (seletor { corpo }) com a linha inicial."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", texto):
        yield m.group(1).strip(), m.group(2), texto.count("\n", 0, m.start(2)) + 1

def _arquivo(caminho):
    achados = []
    texto = caminho.read_text(encoding="utf-8", errors="ignore")
    for n, linha in enumerate(texto.splitlines(), 1):
        if "@media" in linha:
            continue
        for padrao, msg in POR_LINHA:
            m = re.search(padrao, linha, re.I)
            if not m:
                continue
            if "largura fixa" in msg and int(m.group(1)) < 360:
                continue
            achados.append((n, msg))
    for seletor, corpo, n in _blocos_css(texto):
        seletor = seletor.split("\n")[-1]
        fonte = re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", corpo)
        if CONTROLE.search(seletor) and fonte and float(fonte.group(1)) < 16:
            achados.append((n, f"campo com fonte {fonte.group(1)}px: use 16px no celular para evitar zoom automático"))
        altura = re.search(r"(?<![\w-])height\s*:\s*(\d+)px", corpo)
        if ALVO.search(seletor) and altura and int(altura.group(1)) < 44:
            achados.append((n, f"alvo '{seletor[:40]}' com {altura.group(1)}px: garanta >= 44px em toque"))
    # verificações por arquivo
    if caminho.suffix in {".html", ".htm", ".jinja", ".j2"} and re.search(r"<head", texto, re.I):
        if 'name="viewport"' not in texto and "name='viewport'" not in texto:
            achados.append((1, "sem <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"))
    if re.search(r":hover", texto) and not re.search(r":focus", texto):
        achados.append((1, ":hover sem :focus/:focus-visible equivalente no arquivo"))
    if re.search(r"transition|animation|@keyframes", texto) and "prefers-reduced-motion" not in texto:
        achados.append((1, "animações sem @media (prefers-reduced-motion: reduce)"))
    if re.search(r"backdrop-filter", texto) and "prefers-reduced-transparency" not in texto:
        achados.append((1, "vidro sem fallback para prefers-reduced-transparency"))
    if re.search(r"position\s*:\s*fixed", texto) and re.search(r"bottom\s*:\s*0", texto) and "safe-area-inset" not in texto:
        achados.append((1, "barra fixa no rodapé sem env(safe-area-inset-bottom)"))
    if re.search(r"<table", texto, re.I) and not re.search(r"overflow(?:-x)?\s*:\s*auto", texto):
        achados.append((1, "tabela sem contêiner com overflow-x: auto (confira o celular)"))
    return sorted(set(achados))

def varrer(pasta):
    raiz = Path(pasta)
    total = 0
    for caminho in sorted(raiz.rglob("*")):
        if caminho.suffix.lower() not in EXTENSOES or any(p in IGNORAR for p in caminho.parts):
            continue
        achados = _arquivo(caminho)
        if achados:
            print(f"\n{caminho.relative_to(raiz)}")
            for n, msg in achados:
                print(f"  linha {n}: {msg}")
            total += len(achados)
    print(f"\n{total} suspeita(s) para conferir." if total else "Nenhuma suspeita encontrada.")

# Contraste WCAG: contraste("#5D657C", compor("#FFFFFF", 0.55, "#DDD9F7"))
def _rgb(h):
    h = h.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def compor(cor, alfa, fundo):
    """Cor final de uma camada translúcida (ex.: vidro) sobre um fundo sólido."""
    c, f = _rgb(cor), _rgb(fundo)
    return "#%02X%02X%02X" % tuple(round(c[i] * alfa + f[i] * (1 - alfa)) for i in range(3))

def contraste(a, b):
    def lum(h):
        def canal(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, bl = (canal(v) for v in _rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return round((x + 0.05) / (y + 0.05), 2)

if __name__ == "__main__" and len(sys.argv) > 1:
    varrer(sys.argv[1])
```

Confira também, à mão, o que o script não pega:
- [ ] **Contraste dos pares de tokens usados** (texto ≥ 4,5:1; texto grande e gráficos essenciais ≥ 3:1). Para vidro, meça contra o fundo mais desfavorável com `compor()`.
- [ ] Toda capacidade que existia antes continua com um caminho até ela.
- [ ] Nenhuma lógica de negócio foi duplicada ou alterada.
- [ ] Números, moeda e datas são formatados pelo locale do produto.

## C. Roteiro manual para o usuário

Quando o ambiente não permitir renderizar, inclua na entrega este roteiro, adaptado às telas alteradas:

1. Abra o app no Chrome ou no Edge e pressione F12.
2. Ative o modo dispositivo (Ctrl+Shift+M) e teste 390, 768 e 1440 px.
3. Em cada largura, percorra as telas alteradas e confira os itens da seção A.
4. Abra num celular real (Android e iPhone, se o público usar os dois) e teste filtros, formulários com o teclado aberto e gráficos por toque.

## D. Registro na entrega

### Matriz de conformidade (obrigatória)

Um item para cada requisito numerado do diagnóstico, incluindo os critérios dos componentes de referência (ex.: F1 a F11 do painel de filtros, H1 a H7 da Home, G1 a G8 dos gráficos). Entregue só quando todos tiverem status, e nenhum "Não atendido" ficar sem motivo e plano.

| # | Requisito | Status | Onde (arquivo e trecho) | Como foi verificado |
|---|---|---|---|---|
| R1 | Painel de filtros recolhe para trilho de 48 px | Atendido | `static/js/filtros.js`, `static/css/app.css` (.fp-lateral) | Renderizado a 1440 px: 320 px aberto, 48 px recolhido |
| R2 | … | Bloqueado | n/a | Falta o código da referência X; pedido ao usuário |

### Verificações

| Verificação | Tipo | Resultado |
|---|---|---|
| 390 px: tela X | Renderizada (viewport emulado) | OK, ou problema e correção |
| CSS: larguras fixas | Estática (script) | achados e o que foi feito |
| iPhone real | Pendente (manual) | n/a |

Tipos possíveis: renderizada em viewport emulado, renderizada em aparelho físico, estática, pendente de teste manual. Nunca registre como validado o que não foi executado.
