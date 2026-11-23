let paginaAtual = 1;
const porPagina = 20;
let termoBusca = "";
let debounceTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
    carregarMetricas();
    carregarTabela();

    // Eventos de busca
    const searchInput = document.getElementById("search-input");
    searchInput.addEventListener("input", (e) => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            termoBusca = e.target.value.trim();
            paginaAtual = 1;
            carregarTabela();
        }, 350);
    });

    // Botão recarregar
    document.getElementById("btn-refresh").addEventListener("click", () => {
        carregarMetricas();
        carregarTabela();
    });

    // Paginação
    document.getElementById("btn-prev-page").addEventListener("click", () => {
        if (paginaAtual > 1) {
            paginaAtual--;
            carregarTabela();
        }
    });

    document.getElementById("btn-next-page").addEventListener("click", () => {
        paginaAtual++;
        carregarTabela();
    });
});

async function carregarMetricas() {
    try {
        const res = await fetch("/api/metricas");
        const data = await res.json();
        if (data.sucesso) {
            document.getElementById("kpi-total-linhas").textContent = data.total_linhas;
            document.getElementById("kpi-total-colunas").textContent = data.total_colunas;
            document.getElementById("last-sync-time").textContent = data.ultima_atualizacao;
            document.getElementById("kpi-origem").textContent = data.origem;
        }
    } catch (err) {
        console.error("Erro ao carregar métricas:", err);
    }
}

async function carregarTabela() {
    const loader = document.getElementById("table-loader");
    const tableHeaders = document.getElementById("table-headers");
    const tableBody = document.getElementById("table-body");
    const infoCounter = document.getElementById("table-info-counter");
    const btnPrev = document.getElementById("btn-prev-page");
    const btnNext = document.getElementById("btn-next-page");

    loader.style.display = "flex";

    try {
        const url = `/api/dados?pagina=${paginaAtual}&por_pagina=${porPagina}&busca=${encodeURIComponent(termoBusca)}`;
        const res = await fetch(url);
        const data = await res.json();

        if (data.sucesso) {
            // Renderiza cabeçalhos
            tableHeaders.innerHTML = "";
            data.colunas.forEach(col => {
                const th = document.createElement("th");
                th.textContent = col.titulo;
                tableHeaders.appendChild(th);
            });

            // Renderiza linhas
            tableBody.innerHTML = "";
            if (data.registros.length === 0) {
                const tr = document.createElement("tr");
                const td = document.createElement("td");
                td.colSpan = Math.max(data.colunas.length, 1);
                td.style.textAlign = "center";
                td.style.padding = "32px";
                td.style.color = "#94a3b8";
                td.textContent = "Nenhum registro encontrado para os filtros selecionados.";
                tr.appendChild(td);
                tableBody.appendChild(tr);
            } else {
                data.registros.forEach(row => {
                    const tr = document.createElement("tr");
                    data.colunas.forEach(col => {
                        const td = document.createElement("td");
                        const valor = row[col.campo];
                        td.textContent = (valor !== null && valor !== undefined) ? valor : "-";
                        tr.appendChild(td);
                    });
                    tableBody.appendChild(tr);
                });
            }

            // Atualiza paginação e contadores
            document.getElementById("current-page").textContent = data.pagina_atual;
            document.getElementById("total-pages").textContent = data.total_paginas || 1;
            infoCounter.textContent = `Exibindo ${data.registros.length} de ${data.total_registros} registros (Base total: ${data.total_geral})`;

            btnPrev.disabled = data.pagina_atual <= 1;
            btnNext.disabled = data.pagina_atual >= data.total_paginas;
        } else {
            tableBody.innerHTML = `<tr><td colspan="100%" style="color: red; padding: 20px;">Erro: ${data.erro}</td></tr>`;
        }
    } catch (err) {
        tableBody.innerHTML = `<tr><td colspan="100%" style="color: red; padding: 20px;">Erro de conexão com o servidor.</td></tr>`;
        console.error("Erro ao carregar tabela:", err);
    } finally {
        loader.style.display = "none";
    }
}
