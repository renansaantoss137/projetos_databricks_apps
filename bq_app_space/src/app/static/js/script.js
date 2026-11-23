document.addEventListener('DOMContentLoaded', () => {
    // 0. THEME SWITCHER
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    if (themeToggleBtn) {
        const sunIcon = themeToggleBtn.querySelector('.theme-icon-sun');
        const moonIcon = themeToggleBtn.querySelector('.theme-icon-moon');

        // Check saved theme (default to dark mode if not explicitly set to light)
        const savedTheme = localStorage.getItem('theme');
        const isDark = savedTheme ? (savedTheme === 'dark') : true;

        if (isDark) {
            document.body.classList.add('dark-theme');
            if (sunIcon) sunIcon.style.display = 'block';
            if (moonIcon) moonIcon.style.display = 'none';
        } else {
            document.body.classList.remove('dark-theme');
            if (sunIcon) sunIcon.style.display = 'none';
            if (moonIcon) moonIcon.style.display = 'block';
        }

        themeToggleBtn.addEventListener('click', () => {
            document.body.classList.toggle('dark-theme');
            const isDark = document.body.classList.contains('dark-theme');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');

            if (isDark) {
                if (sunIcon) sunIcon.style.display = 'block';
                if (moonIcon) moonIcon.style.display = 'none';
            } else {
                if (sunIcon) sunIcon.style.display = 'none';
                if (moonIcon) moonIcon.style.display = 'block';
            }
        });
    }

    // Helper to normalize strings for accent-insensitive and case-insensitive comparison
    function normalizeStr(str) {
        if (!str) return '';
        return str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
    }

    // 1. INSTANT SEARCH AUTOCOMPLETE
    const searchInput = document.getElementById('search-input');
    const suggestionsList = document.getElementById('search-suggestions');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const rawQuery = e.target.value;
            const queryNorm = normalizeStr(rawQuery);

            if (!suggestionsList) return;

            if (queryNorm === '') {
                suggestionsList.innerHTML = '';
                suggestionsList.style.display = 'none';
                return;
            }

            suggestionsList.innerHTML = '';
            const allDashboards = window.ALL_DASHBOARDS || [];
            const matches = allDashboards.filter(dash => {
                const titleNorm = normalizeStr(dash.title);
                const areaNorm = normalizeStr(dash.area_key);
                const areaCleanNorm = normalizeStr((dash.area_key || '').replace(/_/g, ' '));
                const titleKeyNorm = normalizeStr(dash.title_key);
                const titleKeyCleanNorm = normalizeStr((dash.title_key || '').replace(/_/g, ' '));
                return titleNorm.includes(queryNorm) || 
                       areaNorm.includes(queryNorm) || 
                       areaCleanNorm.includes(queryNorm) || 
                       titleKeyNorm.includes(queryNorm) ||
                       titleKeyCleanNorm.includes(queryNorm);
            }).slice(0, 10);

            if (matches.length === 0) {
                suggestionsList.style.display = 'none';
                return;
            }

            matches.forEach(dash => {
                const li = document.createElement('li');

                const nameSpan = document.createElement('span');
                nameSpan.className = 'sugg-name';
                nameSpan.textContent = dash.title;

                const areaSpan = document.createElement('span');
                areaSpan.className = 'sugg-area';
                areaSpan.textContent = (dash.area_key || '').replace(/_/g, ' ');

                li.appendChild(nameSpan);
                li.appendChild(areaSpan);

                li.addEventListener('click', () => {
                    suggestionsList.innerHTML = '';
                    suggestionsList.style.display = 'none';
                    searchInput.value = '';

                    if (dash.link && dash.link !== '#' && dash.link !== '' && typeof openDashViewer === 'function') {
                        if (openDashViewer.length === 0 || openDashViewer.length > 1) {
                            openDashViewer(dash.link, dash.title, (dash.area_key || '').replace(/_/g, ' '), dash.area_key);
                        } else {
                            const syntheticBtn = document.createElement('button');
                            syntheticBtn.setAttribute('data-url', dash.link);
                            syntheticBtn.setAttribute('data-url-mobile', dash.link_mobile || '');
                            syntheticBtn.setAttribute('data-label', dash.title);
                            syntheticBtn.setAttribute('data-area-key', dash.area_key || '');
                            openDashViewer(syntheticBtn);
                        }
                    } else {
                        window.location.href = dash.url || `/area/${dash.area_key}`;
                    }
                });
                suggestionsList.appendChild(li);
            });
            suggestionsList.style.display = 'block';
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (suggestionsList && !searchInput.contains(e.target) && !suggestionsList.contains(e.target)) {
                suggestionsList.style.display = 'none';
            }
        });

        // Re-open suggestions on focus if query exists
        searchInput.addEventListener('focus', () => {
            if (suggestionsList && searchInput.value.trim() !== '' && suggestionsList.children.length > 0) {
                suggestionsList.style.display = 'block';
            }
        });

        // Close suggestions on Escape key
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && suggestionsList) {
                suggestionsList.style.display = 'none';
                searchInput.blur();
            }
        });
    }

    // 2. INTERNATIONALIZATION (I18N) ENGINE
    const translations = {
        pt: {
            general: "Geral",
            suggested_dashboards: "Dashboards Sugeridos",
            favorites: "Favoritos",
            areas: "Áreas",
            apps: "Aplicativos",
            general_kpis: "Operational Discipline",
            unified_sales_report: "Relatório de Vendas Unificado",
            fill_rate_unified: "Fill Rate Unificado",
            results: "Resultados",
            space_access: "Acesso Space",
            dna: "DNA",
            people: "Pessoas",
            commercial: "Comercial",
            marketing: "Marketing",
            adm_finances: "ADM & Finanças",
            logistics: "Logística",
            rgm: "RGM",
            supply_chain: "Supply Chain",
            purchase: "Compras",
            industrial: "Industrial",
            transformation: "Transformação",
            fpa: "FP&A",
            legal: "Jurídico",
            audit: "Auditoria",
            quality: "Qualidade",
            wickbold: "Wickbold",
            search_placeholder: "Pesquisar Dashboard",
            menu_title: "Menu",
            support: "Suporte",
            admin_panel: "Administração",
            new_component: "Novo Componente",
            type_label: "Tipo",
            target_area: "Área Alvo",
            title_label: "Título / Nome",
            embed_url: "URL de Embed (iframe)",
            embed_url_mobile: "URL de Embed Mobile (opcional)",
            icon_label: "Ícone",
            add_component_btn: "Adicionar Componente",
            registered_components: "Componentes Cadastrados",
            all_areas_option: "Todas as Áreas",
            all_types_option: "Todos os Tipos",
            clear_btn: "Limpar",
            area_th: "Área",
            type_th: "Tipo",
            name_th: "Nome",
            link_th: "Link",
            visible_th: "Visível",
            actions_th: "Ações",
            no_components_found: "Nenhum componente encontrado para os filtros selecionados.",
            new_area: "Nova Área",
            area_key_label: "Chave da Área (ID único em minúsculo)",
            area_title_label: "Título da Área",
            create_area_btn: "Criar Área",
            areas_visibility: "Visibilidade das Áreas",
            areas_visibility_desc: "Ocultar uma área remove ela da página inicial e impede acesso direto via URL.",
            search_name_placeholder: "Buscar por nome...",
            placeholder_title_example: "Ex: Relatório Mensal",
            placeholder_url_example: "Ex: https://app.powerbi.com/reportEmbed?reportId=...",
            placeholder_key_example: "Ex: faturamento",
            placeholder_area_title_example: "Ex: Faturamento",
            hint_component_url: "Para dashboards: use a URL de embed do Power BI.<br>Para aplicativos: URL da aplicação web (abre em nova aba).",
            hint_component_mobile_url: "Opcional. Usado automaticamente quando o portal for acessado de um celular.",
            hint_area_key: "Apenas letras minúsculas, números e sublinhados.",
            status_visible: "Visível",
            status_hidden: "Oculta",
            action_delete: "Excluir",
            action_hide: "Ocultar",
            action_show: "Exibir",
            about_area_label: "Sobre a Área",
            pillars_title: "Pilares & Atuação Estratégica",
            area_badge_dna: "Data & Analytics",
            area_tagline_dna: "Data & Analytics — Transformando dados em decisões inteligentes no Grupo Bimbo",
            about_desc_dna: "A área de Data & Analytics (DNA) é responsável por estruturar, governar e potencializar o ecossistema de dados da empresa. Combinando a arquitetura moderna de Databricks Lakehouse, Unity Catalog e ferramentas avançadas de self-service BI, o time de DNA gera inteligência estratégica para todas as operações do Grupo Bimbo.",
            pillar_title_dna_1: "Lakehouse & Engenharia",
            pillar_desc_dna_1: "Pipelines de dados escaláveis, processamento em tempo real com Delta Lake e arquitetura moderna.",
            pillar_title_dna_2: "Governança & Qualidade",
            pillar_desc_dna_2: "Curadoria de dados, gestão de acessos via Unity Catalog e conformidade com políticas de segurança.",
            pillar_title_dna_3: "Analytics & Self-Service BI",
            pillar_desc_dna_3: "Dashboards de alta performance, indicadores estratégicos e democratização no uso dos dados.",
            pillar_title_dna_4: "IA & Ciência de Dados",
            pillar_desc_dna_4: "Modelagem preditiva e inteligência artificial para otimização comercial, logística e industrial.",
            stat_label_dna_1: "Pipelines de Dados",
            stat_label_dna_2: "Qualidade & Uptime",
            stat_label_dna_3: "Engine Analítica",
            stat_label_dna_4: "Usuários Conectados",
            btn_saber_mais: "Saber Mais",
            area_badge_people: "Pessoas & Cultura",
            area_tagline_people: "Gestão de Talentos, Cultura e Desenvolvimento de Pessoas no Grupo Bimbo",
            about_desc_people: "A área de Pessoas (Recursos Humanos) é responsável por atrair, desenvolver e valorizar os colaboradores do Grupo Bimbo. Focada em cultura organizacional, gestão do conhecimento e experiência do colaborador, a equipe impulsiona o crescimento contínuo de nossos talentos.",
            pillar_title_people_1: "Gestão de Talentos & Atração",
            pillar_desc_people_1: "Recrutamento estratégico, programas de onboarding e desenvolvimento de planos de carreira.",
            pillar_title_people_2: "T&D e Cultura Organizacional",
            pillar_desc_people_2: "Capacitações contínuas, universidade corporativa e fortalecimento da cultura Grupo Bimbo.",
            pillar_title_people_3: "Experiência & Bem-Estar",
            pillar_desc_people_3: "Clima organizacional, gestão de benefícios, saúde e qualidade de vida dos colaboradores.",
            stat_label_people_1: "Colaboradores",
            stat_label_people_2: "Satisfação & Clima",
            stat_label_people_3: "Capacitações/Ano",
            first_access_badge: "Primeiro Acesso",
            welcome_title: "Seja bem-vindo ao SPACE! 👋",
            welcome_subtitle: "Identificamos que este é o seu primeiro acesso ao portal. Para você começar com o pé direito, preparamos alguns dashboards sugeridos especialmente para você:",
            confirm_btn: "Confirmar",
            no_favorites_text: "Nenhum favorito. Clique na estrela <i data-lucide=\"star\"></i> para adicionar!"
        },
        en: {
            general: "General",
            suggested_dashboards: "Suggested Dashboards",
            favorites: "Favorites",
            areas: "Areas",
            apps: "Apps",
            general_kpis: "Operational Discipline",
            unified_sales_report: "Unified Sales Report",
            fill_rate_unified: "Fill Rate Unified",
            results: "Results",
            space_access: "Space Access",
            dna: "DNA",
            people: "People",
            commercial: "Commercial",
            marketing: "Marketing",
            adm_finances: "ADM & Finances",
            logistics: "Logistics",
            rgm: "RGM",
            supply_chain: "Supply Chain",
            purchase: "Purchase",
            industrial: "Industrial",
            transformation: "Transformation",
            fpa: "FP&A",
            legal: "Legal",
            audit: "Audit",
            quality: "Quality",
            wickbold: "Wickbold",
            search_placeholder: "Search Dashboard",
            menu_title: "Menu",
            support: "Support",
            admin_panel: "Administration",
            new_component: "New Component",
            type_label: "Type",
            target_area: "Target Area",
            title_label: "Title / Name",
            embed_url: "Embed URL (iframe)",
            embed_url_mobile: "Mobile Embed URL (optional)",
            icon_label: "Icon",
            add_component_btn: "Add Component",
            registered_components: "Registered Components",
            all_areas_option: "All Areas",
            all_types_option: "All Types",
            clear_btn: "Clear",
            area_th: "Area",
            type_th: "Type",
            name_th: "Name",
            link_th: "Link",
            visible_th: "Visible",
            actions_th: "Actions",
            no_components_found: "No components found for the selected filters.",
            new_area: "New Area",
            area_key_label: "Area Key (lowercase unique ID)",
            area_title_label: "Area Title",
            create_area_btn: "Create Area",
            areas_visibility: "Areas Visibility",
            areas_visibility_desc: "Hiding an area removes it from the home page and prevents direct URL access.",
            search_name_placeholder: "Search by name...",
            placeholder_title_example: "Ex: Monthly Report",
            placeholder_url_example: "Ex: https://app.powerbi.com/reportEmbed?reportId=...",
            placeholder_key_example: "Ex: billing",
            placeholder_area_title_example: "Ex: Billing",
            hint_component_url: "For dashboards: use Power BI embed URL.<br>For apps: Web application URL (opens in a new tab).",
            hint_component_mobile_url: "Optional. Automatically used when the portal is accessed from a mobile device.",
            hint_area_key: "Only lowercase letters, numbers, and underscores.",
            status_visible: "Visible",
            status_hidden: "Hidden",
            action_delete: "Delete",
            action_hide: "Hide",
            action_show: "Show",
            about_area_label: "About Area",
            pillars_title: "Strategic Pillars & Scope",
            area_badge_dna: "Data & Analytics",
            area_tagline_dna: "Data & Analytics — Turning data into intelligent decisions at Grupo Bimbo",
            about_desc_dna: "The Data & Analytics (DNA) team structures, governs, and empowers the company's data ecosystem. Combining modern Databricks Lakehouse architecture, Unity Catalog, and advanced self-service BI tools, DNA generates strategic intelligence for all Grupo Bimbo operations.",
            pillar_title_dna_1: "Lakehouse & Engineering",
            pillar_desc_dna_1: "Scalable data pipelines, real-time processing with Delta Lake, and modern architecture.",
            pillar_title_dna_2: "Governance & Quality",
            pillar_desc_dna_2: "Data curation, access management via Unity Catalog, and compliance with security policies.",
            pillar_title_dna_3: "Analytics & Self-Service BI",
            pillar_desc_dna_3: "High-performance dashboards, strategic KPIs, and data usage democratization.",
            pillar_title_dna_4: "AI & Data Science",
            pillar_desc_dna_4: "Predictive modeling and artificial intelligence for commercial, logistics, and industrial optimization.",
            stat_label_dna_1: "Data Pipelines",
            stat_label_dna_2: "Quality & Uptime",
            stat_label_dna_3: "Analytics Engine",
            stat_label_dna_4: "Connected Users",
            btn_saber_mais: "Learn More",
            area_badge_people: "People & Culture",
            area_tagline_people: "Talent Management, Culture, and People Development at Grupo Bimbo",
            about_desc_people: "The People (HR) area is responsible for attracting, developing, and empowering Grupo Bimbo employees. Focused on organizational culture, knowledge management, and employee experience, the team drives continuous talent growth.",
            pillar_title_people_1: "Talent Management & Attraction",
            pillar_desc_people_1: "Strategic recruitment, onboarding programs, and career path development.",
            pillar_title_people_2: "L&D & Organizational Culture",
            pillar_desc_people_2: "Continuous training, corporate university, and strengthening Grupo Bimbo culture.",
            pillar_title_people_3: "Employee Experience & Well-being",
            pillar_desc_people_3: "Organizational climate, benefits management, health, and employee well-being.",
            stat_label_people_1: "Employees",
            stat_label_people_2: "Satisfaction & Climate",
            stat_label_people_3: "Trainings/Year",
            first_access_badge: "First Access",
            welcome_title: "Welcome to SPACE! 👋",
            welcome_subtitle: "We identified this is your first access to the portal. To get you started on the right foot, we prepared these suggested dashboards specially for you:",
            confirm_btn: "Confirm",
            no_favorites_text: "No favorites yet. Click the star <i data-lucide=\"star\"></i> to add!"
        },
        es: {
            general: "General",
            suggested_dashboards: "Cuadros de Mando Sugeridos",
            favorites: "Favoritos",
            areas: "Áreas",
            apps: "Aplicaciones",
            general_kpis: "Operational Discipline",
            unified_sales_report: "Informe Unificado de Ventas",
            fill_rate_unified: "Tasa de Llenado Unificada",
            results: "Resultados",
            space_access: "Acceso Space",
            dna: "DNA",
            people: "Personas",
            commercial: "Comercial",
            marketing: "Marketing",
            adm_finances: "ADM y Finanzas",
            logistics: "Logística",
            rgm: "RGM",
            supply_chain: "Cadena de Suministro",
            purchase: "Compras",
            industrial: "Industrial",
            transformation: "Transformación",
            fpa: "FP&A",
            legal: "Legal",
            audit: "Auditoría",
            quality: "Calidad",
            wickbold: "Wickbold",
            search_placeholder: "Buscar Dashboard",
            menu_title: "Menú",
            support: "Soporte",
            admin_panel: "Administración",
            new_component: "Nuevo Componente",
            type_label: "Tipo",
            target_area: "Área de Destino",
            title_label: "Título / Nombre",
            embed_url: "URL de Embed (iframe)",
            embed_url_mobile: "URL de Embed Móvil (opcional)",
            icon_label: "Icono",
            add_component_btn: "Agregar Componente",
            registered_components: "Componentes Registrados",
            all_areas_option: "Todas las Áreas",
            all_types_option: "Todos los Tipos",
            clear_btn: "Limpiar",
            area_th: "Área",
            type_th: "Tipo",
            name_th: "Nombre",
            link_th: "Enlace",
            visible_th: "Visible",
            actions_th: "Acciones",
            no_components_found: "No se encontraron componentes para los filtros seleccionados.",
            new_area: "Nueva Área",
            area_key_label: "Clave del Área (ID único en minúsculas)",
            area_title_label: "Título del Área",
            create_area_btn: "Crear Área",
            areas_visibility: "Visibilidad de Áreas",
            areas_visibility_desc: "Ocultar un área la elimina de la página de inicio y evita el acceso directo por URL.",
            search_name_placeholder: "Buscar por nombre...",
            placeholder_title_example: "Ej: Informe Mensual",
            placeholder_url_example: "Ej: https://app.powerbi.com/reportEmbed?reportId=...",
            placeholder_key_example: "Ej: facturacion",
            placeholder_area_title_example: "Ej: Facturación",
            hint_component_url: "Para dashboards: use la URL de embed de Power BI.<br>Para aplicaciones: URL de la aplicación web (se abre en una nueva pestaña).",
            hint_component_mobile_url: "Opcional. Se usa automáticamente cuando se accede al portal desde un móvil.",
            hint_area_key: "Solo letras minúsculas, números y guiones bajos.",
            status_visible: "Visible",
            status_hidden: "Oculta",
            action_delete: "Eliminar",
            action_hide: "Ocultar",
            action_show: "Exhibir",
            about_area_label: "Sobre el Área",
            pillars_title: "Pilares y Actuación Estratégica",
            area_badge_dna: "Data & Analytics",
            area_tagline_dna: "Data & Analytics — Transformando datos en decisiones inteligentes en Grupo Bimbo",
            about_desc_dna: "El área de Data & Analytics (DNA) es responsável de estruturar, gobernar y potenciar el ecosistema de datos de la empresa. Combinando la arquitectura moderna de Databricks Lakehouse, Unity Catalog y herramientas avanzadas de self-service BI, el equipo de DNA genera inteligencia estratégica para todas las operaciones de Grupo Bimbo.",
            pillar_title_dna_1: "Lakehouse e Ingeniería",
            pillar_desc_dna_1: "Pipelines de datos escalables, procesamiento en tiempo real con Delta Lake y arquitectura moderna.",
            pillar_title_dna_2: "Gobernanza y Calidad",
            pillar_desc_dna_2: "Curaduría de datos, gestión de accesos mediante Unity Catalog y cumplimiento de políticas de seguridad.",
            pillar_title_dna_3: "Analytics y Self-Service BI",
            pillar_desc_dna_3: "Cuadros de mando de alto rendimiento, indicadores estratégicos y democratización en el uso de datos.",
            pillar_title_dna_4: "IA y Ciencia de Datos",
            pillar_desc_dna_4: "Modelado predictivo e inteligencia artificial para optimización comercial, logística e industrial.",
            stat_label_dna_1: "Pipelines de Datos",
            stat_label_dna_2: "Calidad y Uptime",
            stat_label_dna_3: "Motor Analítico",
            stat_label_dna_4: "Usuarios Conectados",
            btn_saber_mais: "Saber Más",
            area_badge_people: "Personas & Cultura",
            area_tagline_people: "Gestión del Talento, Cultura y Desarrollo de Personas en Grupo Bimbo",
            about_desc_people: "El área de Personas (Recursos Humanos) es responsable de atraer, desarrollar y potenciar a los colaboradores de Grupo Bimbo. Enfocada en la cultura organizacional, gestión del conocimiento y experiencia del colaborador, el equipo impulsa el crecimiento continuo de nuestros talentos.",
            pillar_title_people_1: "Gestión de Talento & Atracción",
            pillar_desc_people_1: "Reclutamiento estratégico, programas de onboarding y desarrollo de planes de carrera.",
            pillar_title_people_2: "Cultura y Capacitación",
            pillar_desc_people_2: "Formación continua, universidad corporativa y fortalecimiento de la cultura Grupo Bimbo.",
            pillar_title_people_3: "Experiencia & Bienestar",
            pillar_desc_people_3: "Clima organizacional, gestión de beneficios, salud y calidad de vida de los colaboradores.",
            stat_label_people_1: "Colaboradores",
            stat_label_people_2: "Satisfacción & Clima",
            stat_label_people_3: "Capacitaciones/Año",
            first_access_badge: "Primer Acceso",
            welcome_title: "¡Bienvenido a SPACE! 👋",
            welcome_subtitle: "Identificamos que este es su primer acceso al portal. Para comenzar con el pie derecho, preparamos estos cuadros de mando sugeridos especialmente para usted:",
            confirm_btn: "Confirmar",
            no_favorites_text: "Sin favoritos aún. ¡Haz clic en la estrella <i data-lucide=\"star\"></i> para agregar!"
        }
    };
    window.SPACE_TRANSLATIONS = translations;

    const langSelector = document.getElementById('lang-selector');
    const langDropdown = document.getElementById('lang-dropdown');
    const i18nElements = document.querySelectorAll('[data-i18n]');

    function setLanguage(lang) {
        lang = lang.toLowerCase();
        if (!translations[lang]) lang = 'en'; // fallback

        // Save selection
        localStorage.setItem('language', lang);

        // Translate text elements
        i18nElements.forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (translations[lang][key]) {
                el.textContent = translations[lang][key];
            }
        });

        // Translate search placeholder
        if (searchInput) {
            searchInput.placeholder = translations[lang]['search_placeholder'];
        }

        // Translate admin search name placeholder
        const filterTextEl = document.getElementById('filterText');
        if (filterTextEl && translations[lang]['search_name_placeholder']) {
            filterTextEl.placeholder = translations[lang]['search_name_placeholder'];
        }

        // Translate admin placeholders
        const placeholderTargets = [
            { id: 'title', key: 'placeholder_title_example' },
            { id: 'link', key: 'placeholder_url_example' },
            { id: 'link_mobile', key: 'placeholder_url_example' },
            { id: 'area_key', key: 'placeholder_key_example' },
            { id: 'area_title', key: 'placeholder_area_title_example' }
        ];
        placeholderTargets.forEach(target => {
            const el = document.getElementById(target.id);
            if (el && translations[lang][target.key]) {
                el.placeholder = translations[lang][target.key];
            }
        });

        // Translate HTML hints/descriptions
        const hintTargets = document.querySelectorAll('[data-i18n-html]');
        hintTargets.forEach(el => {
            const key = el.getAttribute('data-i18n-html');
            if (translations[lang][key]) {
                el.innerHTML = translations[lang][key];
            }
        });

        // Translate Tooltips (titles)
        const titleTargets = document.querySelectorAll('[data-i18n-title]');
        titleTargets.forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            if (translations[lang][key]) {
                el.setAttribute('title', translations[lang][key]);
            }
        });

        // Update active anchor visual states in dropdown
        if (langDropdown) {
            const anchors = langDropdown.querySelectorAll('a');
            anchors.forEach(a => {
                const targetLang = a.getAttribute('data-lang');
                if (targetLang === lang) {
                    a.classList.add('active');
                } else {
                    a.classList.remove('active');
                }
            });
        }

        // Update topbar badge
        if (langSelector) {
            const badge = langSelector.querySelector('.lang-badge');
            if (badge) badge.textContent = lang.toUpperCase();
        }
    }

    // Toggle Dropdown Menu
    if (langSelector && langDropdown) {
        langSelector.addEventListener('click', (e) => {
            e.stopPropagation();
            langDropdown.classList.toggle('show');
            const chevron = langSelector.querySelector('.chevron-icon');
            if (chevron) {
                chevron.style.transform = langDropdown.classList.contains('show') ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    }

    // Toggle Mock User Dropdown
    const mockUserBtn = document.getElementById('mock-user-btn');
    const mockUserDropdown = document.getElementById('mock-user-dropdown');
    if (mockUserBtn && mockUserDropdown) {
        mockUserBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            mockUserDropdown.classList.toggle('show');
        });
    }

    // Close on clicking outside
    document.addEventListener('click', (e) => {
        if (langDropdown && langDropdown.classList.contains('show')) {
            langDropdown.classList.remove('show');
            if (langSelector) {
                const chevron = langSelector.querySelector('.chevron-icon');
                if (chevron) chevron.style.transform = 'rotate(0deg)';
            }
        }
        if (mockUserDropdown && mockUserDropdown.classList.contains('show')) {
            if (!mockUserDropdown.contains(e.target) && e.target !== mockUserBtn && !mockUserBtn.contains(e.target)) {
                mockUserDropdown.classList.remove('show');
            }
        }
    });

    // Handle selection changes
    if (langDropdown) {
        const langOptions = langDropdown.querySelectorAll('a');
        langOptions.forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const targetLang = opt.getAttribute('data-lang');
                setLanguage(targetLang);
                
                // Close dropdown
                langDropdown.classList.remove('show');
                if (langSelector) {
                    const chevron = langSelector.querySelector('.chevron-icon');
                    if (chevron) chevron.style.transform = 'rotate(0deg)';
                }
            });
        });
    }

    // Initialize Language (Check Cache or Browser Settings)
    const cachedLang = localStorage.getItem('language');
    if (cachedLang) {
        setLanguage(cachedLang);
    } else {
        const browserLang = navigator.language || navigator.userLanguage;
        if (browserLang && browserLang.startsWith('pt')) {
            setLanguage('pt');
        } else if (browserLang && browserLang.startsWith('es')) {
            setLanguage('es');
        } else {
            setLanguage('en');
        }
    }

    // 3. HAMBURGER MENU & SIDE DRAWER INTERACTIVE TRANSITION
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const sideDrawer = document.getElementById('side-drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');

    function toggleDrawer() {
        if (hamburgerBtn) hamburgerBtn.classList.toggle('open');
        if (sideDrawer) sideDrawer.classList.toggle('open');
        if (drawerOverlay) drawerOverlay.classList.toggle('active');
        
        if (hamburgerBtn) {
            const bars = hamburgerBtn.querySelectorAll('.bar');
            if (bars && bars.length >= 3) {
                if (hamburgerBtn.classList.contains('open')) {
                    // Morph hamburger icon to 'X' icon
                    bars[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
                    bars[1].style.opacity = '0';
                    bars[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
                } else {
                    // Morph back to three bars
                    bars[0].style.transform = 'none';
                    bars[1].style.opacity = '1';
                    bars[2].style.transform = 'none';
                }
            }
        }
    }

    if (hamburgerBtn) {
        hamburgerBtn.addEventListener('click', toggleDrawer);
    }
    if (drawerOverlay) {
        drawerOverlay.addEventListener('click', toggleDrawer);
    }

    // 4. CLICK AESTHETICS (Ripple effect simulation on cards)
    const allClickables = document.querySelectorAll('.card-item, .app-card');
    allClickables.forEach(element => {
        element.addEventListener('click', () => {
            element.style.transform = 'scale(0.95)';
            setTimeout(() => {
                element.style.transform = '';
            }, 150);
        });
    });

    // 5. FAVORITES INTEGRATION SETUP
    if (typeof renderFavorites === 'function') renderFavorites();
    if (typeof updateCardStars === 'function') updateCardStars();

    const favExpandBtn = document.getElementById('favorites-expand-btn');
    const favModal = document.getElementById('favoritesModal');
    const closeFavModalBtn = document.getElementById('closeFavoritesModalBtn');
    const favScrollContainer = document.getElementById('favorites-container');

    if (favScrollContainer) {
        favScrollContainer.addEventListener('wheel', (e) => {
            if (e.deltaY !== 0 && favScrollContainer.scrollWidth > favScrollContainer.clientWidth) {
                e.preventDefault();
                favScrollContainer.scrollLeft += e.deltaY;
            }
        }, { passive: false });
    }

    if (favExpandBtn && favModal) {
        favExpandBtn.addEventListener('click', () => {
            if (typeof renderFavorites === 'function') renderFavorites();
            favModal.style.display = 'flex';
            document.body.classList.add('modal-open');
        });
    }

    if (closeFavModalBtn && favModal) {
        closeFavModalBtn.addEventListener('click', () => {
            favModal.style.display = 'none';
            document.body.classList.remove('modal-open');
        });
    }

    if (favModal) {
        favModal.addEventListener('click', (e) => {
            if (e.target === favModal) {
                favModal.style.display = 'none';
                document.body.classList.remove('modal-open');
            }
        });
    }
});

// =============================================
// FAVORITES FEATURE GLOBAL HELPERS
// =============================================
const CURRENT_USER = window.CURRENT_USER_EMAIL || "default_user";
const FAV_KEY = `space_favorites_${CURRENT_USER}`;

function getFavorites() {
    try {
        return JSON.parse(localStorage.getItem(FAV_KEY)) || [];
    } catch(e) {
        return [];
    }
}
window.getFavorites = getFavorites;

function saveFavorites(favs) {
    localStorage.setItem(FAV_KEY, JSON.stringify(favs));
}
window.saveFavorites = saveFavorites;

function toggleFavorite(item) {
    let favs = getFavorites();
    const idx = favs.findIndex(f => f.title.toLowerCase() === item.title.toLowerCase() && f.area_key === item.area_key);
    if (idx > -1) {
        favs.splice(idx, 1);
        showToast("Removido dos favoritos!", "info");
    } else {
        if (favs.length >= 9) {
            showToast("Limite de 9 favoritos atingido!", "warning");
            return false;
        }
        favs.push(item);
        showToast("Adicionado aos favoritos!", "success");
    }
    saveFavorites(favs);
    renderFavorites();
    updateCardStars();
    return true;
}
window.toggleFavorite = toggleFavorite;

function resolveFavoriteLive(fav) {
    const all = window.ALL_DASHBOARDS || [];
    if (!all.length || !fav || !fav.title) return fav;

    const titleLower = fav.title.toLowerCase().trim();
    const areaLower = (fav.area_key || '').toLowerCase().trim();

    let match = all.find(d =>
        (d.title || '').toLowerCase().trim() === titleLower &&
        (d.area_key || '').toLowerCase().trim() === areaLower &&
        d.link && d.link !== '#'
    );
    if (!match) {
        match = all.find(d =>
            (d.title || '').toLowerCase().trim() === titleLower &&
            d.link && d.link !== '#'
        );
    }
    if (!match) {
        match = all.find(d =>
            (d.title || '').toLowerCase().trim() === titleLower &&
            (d.area_key || '').toLowerCase().trim() === areaLower
        );
    }
    if (!match) {
        match = all.find(d => (d.title || '').toLowerCase().trim() === titleLower);
    }
    if (!match) return fav;

    const liveLink = (match.link && match.link !== '#') ? match.link : (fav.link || '#');
    const liveMobile = match.link_mobile || fav.link_mobile || '';
    return {
        ...fav,
        area_key: match.area_key || fav.area_key,
        icon: match.icon || fav.icon,
        link: liveLink,
        link_mobile: liveMobile,
        has_access: typeof match.has_access === 'boolean' ? match.has_access : fav.has_access
    };
}

function syncFavoritesWithLiveData() {
    const favs = getFavorites();
    if (!favs.length || !(window.ALL_DASHBOARDS || []).length) return favs;

    let changed = false;
    const synced = favs.map(fav => {
        const updated = resolveFavoriteLive(fav);
        if (updated.link !== fav.link ||
            (updated.link_mobile || '') !== (fav.link_mobile || '') ||
            updated.area_key !== fav.area_key ||
            updated.icon !== fav.icon) {
            changed = true;
        }
        return updated;
    });
    if (changed) {
        saveFavorites(synced);
    }
    return synced;
}

window.handleCardFavClick = function(event, el) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    const rawItem = {
        title: el.getAttribute('data-title'),
        type: el.getAttribute('data-type'),
        area_key: el.getAttribute('data-area-key'),
        icon: el.getAttribute('data-icon') || 'link',
        link: el.getAttribute('data-link') || '#',
        link_mobile: el.getAttribute('data-link-mobile') || '',
        has_access: el.getAttribute('data-has-access') === 'true'
    };
    toggleFavorite(resolveFavoriteLive(rawItem));
};

window.handleFavoriteCardClick = function(event, title, type, areaKey, link, hasAccess, icon, linkMobile) {
    if (event.target.closest('.card-fav-btn')) {
        return;
    }

    const live = resolveFavoriteLive({
        title,
        type,
        area_key: areaKey,
        link,
        link_mobile: linkMobile || '',
        has_access: hasAccess,
        icon
    });
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth < 768;
    const targetUrl = (isMobile && live.link_mobile && live.link_mobile !== '#') ? live.link_mobile : live.link;

    if (type === 'dashboard') {
        if (typeof openDashViewer === 'function') {
            if (openDashViewer.length === 0 || openDashViewer.length > 1) {
                let areaLabel = (live.area_key || '').replace(/_/g, ' ').toUpperCase();
                openDashViewer(targetUrl, live.title, areaLabel, live.area_key);
            } else {
                const syntheticBtn = document.createElement('button');
                syntheticBtn.setAttribute('data-url', live.link || '');
                syntheticBtn.setAttribute('data-url-mobile', live.link_mobile || '');
                syntheticBtn.setAttribute('data-label', live.title);
                syntheticBtn.setAttribute('data-area-key', live.area_key || '');
                openDashViewer(syntheticBtn);
            }
        } else {
            window.location.href = `/area/${live.area_key}`;
        }
    } else {
        if (targetUrl && targetUrl !== '#') {
            window.open(targetUrl, '_blank');
        } else {
            alert('Nenhum link configurado para este aplicativo.');
        }
    }
};

function renderFavorites() {
    const container = document.getElementById('favorites-container');
    const modalGrid = document.getElementById('favorites-modal-grid');
    const favs = syncFavoritesWithLiveData();

    if (container) {
        container.innerHTML = '';
        // Toggle compact class on parent section
        const favSection = container.closest('.favorites-section');
        if (favs.length === 0) {
            const currentLang = localStorage.getItem('language') || 'pt';
            const trans = window.SPACE_TRANSLATIONS || (typeof translations !== 'undefined' ? translations : {});
            const emptyText = trans[currentLang]?.no_favorites_text || trans['pt']?.no_favorites_text || 'Nenhum favorito. Clique na estrela <i data-lucide="star"></i> para adicionar!';
            container.innerHTML = `
                <div class="no-favorites-placeholder">
                    <p data-i18n-html="no_favorites_text">${emptyText}</p>
                </div>
            `;
            if (favSection) favSection.classList.add('favorites-empty');
        } else {
            if (favSection) favSection.classList.remove('favorites-empty');
            const visibleFavs = favs.slice(0, 9);
            visibleFavs.forEach(fav => {
                const card = document.createElement('div');
                card.className = 'card-item tile-card';
                card.style.cursor = 'pointer';
                card.setAttribute('data-title', fav.title.toLowerCase());
                card.onclick = (e) => handleFavoriteCardClick(e, fav.title, fav.type, fav.area_key, fav.link, fav.has_access, fav.icon, fav.link_mobile);
                
                card.innerHTML = `
                    <span class="card-fav-btn is-active" 
                          data-title="${fav.title}" 
                          data-type="${fav.type}" 
                          data-area-key="${fav.area_key}" 
                          data-icon="${fav.icon}" 
                          data-link="${fav.link}" 
                          data-link-mobile="${fav.link_mobile || ''}"
                          data-has-access="${fav.has_access}" 
                          onclick="handleCardFavClick(event, this)" 
                          role="button" 
                          title="Remover dos favoritos">
                        <i data-lucide="star"></i>
                    </span>
                    <div class="card-icon-wrapper">
                        <i data-lucide="${fav.icon}" class="card-icon"></i>
                    </div>
                    <span class="card-label">${fav.title}</span>
                `;
                container.appendChild(card);
            });
        }
        lucide.createIcons({ nodes: [container] });
    }

    if (modalGrid) {
        modalGrid.innerHTML = '';
        for (let i = 0; i < 9; i++) {
            const slot = document.createElement('div');
            slot.className = 'favorites-slot';
            
            if (i < favs.length) {
                const fav = favs[i];
                slot.innerHTML = `
                    <div class="card-item tile-card" style="cursor: pointer; width: 100%; max-width: 100%; margin: 0;">
                        <span class="card-fav-btn is-active" 
                              data-title="${fav.title}" 
                              data-type="${fav.type}" 
                              data-area-key="${fav.area_key}" 
                              data-icon="${fav.icon}" 
                              data-link="${fav.link}" 
                              data-link-mobile="${fav.link_mobile || ''}"
                              data-has-access="${fav.has_access}" 
                              onclick="handleCardFavClick(event, this)" 
                              role="button" 
                              title="Remover dos favoritos">
                            <i data-lucide="star"></i>
                        </span>
                        <div class="card-icon-wrapper">
                            <i data-lucide="${fav.icon}" class="card-icon"></i>
                        </div>
                        <span class="card-label">${fav.title}</span>
                    </div>
                `;
                const slotCard = slot.querySelector('.card-item');
                slotCard.onclick = (e) => {
                    handleFavoriteCardClick(e, fav.title, fav.type, fav.area_key, fav.link, fav.has_access, fav.icon, fav.link_mobile);
                    const favModal = document.getElementById('favoritesModal');
                    if (favModal && !e.target.closest('.card-fav-btn')) {
                        favModal.style.display = 'none';
                        document.body.classList.remove('modal-open');
                    }
                };
            } else {
                slot.className = 'favorites-slot empty';
                slot.innerHTML = `
                    <i data-lucide="plus"></i>
                    <span>Slot Vazio</span>
                `;
            }
            modalGrid.appendChild(slot);
        }
        lucide.createIcons({ nodes: [modalGrid] });
    }
}
window.renderFavorites = renderFavorites;

window.addEventListener('pageshow', (e) => {
    if (e.persisted) {
        if (typeof renderFavorites === 'function') renderFavorites();
        if (typeof updateCardStars === 'function') updateCardStars();
    }
});

function updateCardStars() {
    const favs = getFavorites();
    const starButtons = document.querySelectorAll('.card-fav-btn');
    starButtons.forEach(btn => {
        const title = btn.getAttribute('data-title');
        const areaKey = btn.getAttribute('data-area-key');
        
        const isFav = favs.some(f => f.title.toLowerCase() === title.toLowerCase() && f.area_key === areaKey);
        if (isFav) {
            btn.classList.add('is-active');
            btn.setAttribute('title', 'Remover dos favoritos');
        } else {
            btn.classList.remove('is-active');
            btn.setAttribute('title', 'Adicionar aos favoritos');
        }
    });
}
window.updateCardStars = updateCardStars;

function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle';
    if (type === 'warning') iconName = 'alert-triangle';
    
    toast.innerHTML = `
        <i data-lucide="${iconName}" style="width:18px; height:18px;"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    lucide.createIcons({ nodes: [toast] });
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}
window.showToast = showToast;
