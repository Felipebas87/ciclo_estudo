const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

// Configuração global padrão do Chart.js para visual SaaS de Alto Contraste
if (typeof Chart !== 'undefined') {
    const isDarkInit = (localStorage.getItem('app_theme') || 'dark') === 'dark';
    Chart.defaults.font.family = "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.color = isDarkInit ? '#94A3B8' : '#64748b';
    Chart.defaults.borderColor = isDarkInit ? '#24324A' : '#e2e8f0';
    if (Chart.defaults.plugins?.tooltip) {
        Chart.defaults.plugins.tooltip.backgroundColor = isDarkInit ? '#141D2E' : 'rgba(15, 23, 42, 0.92)';
        Chart.defaults.plugins.tooltip.borderColor = isDarkInit ? '#24324A' : 'transparent';
        Chart.defaults.plugins.tooltip.borderWidth = isDarkInit ? 1 : 0;
        Chart.defaults.plugins.tooltip.titleColor = isDarkInit ? '#F1F5F9' : '#ffffff';
        Chart.defaults.plugins.tooltip.bodyColor = isDarkInit ? '#94A3B8' : '#cbd5e1';
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
        Chart.defaults.plugins.tooltip.titleFont = { size: 12, weight: 'bold' };
        Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
    }
}

const app = createApp({
    setup() {
        // ==========================================
        // 0. TEMA ESCURO / CLARO & SIDEBAR MOBILE
        // ==========================================
        const tema = ref(localStorage.getItem('app_theme') || 'dark');
        const sidebarMobileAberta = ref(false);

        const aplicarTema = (novoTema) => {
            tema.value = novoTema;
            localStorage.setItem('app_theme', novoTema);
            const isDark = novoTema === 'dark';
            if (isDark) {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
            if (typeof Chart !== 'undefined') {
                Chart.defaults.color = isDark ? '#94A3B8' : '#475569';
                Chart.defaults.borderColor = isDark ? '#24324A' : '#e2e8f0';
                if (Chart.defaults.plugins?.tooltip) {
                    Chart.defaults.plugins.tooltip.backgroundColor = isDark ? '#141D2E' : 'rgba(15, 23, 42, 0.92)';
                    Chart.defaults.plugins.tooltip.borderColor = isDark ? '#24324A' : 'transparent';
                    Chart.defaults.plugins.tooltip.borderWidth = isDark ? 1 : 0;
                    Chart.defaults.plugins.tooltip.titleColor = isDark ? '#F1F5F9' : '#ffffff';
                    Chart.defaults.plugins.tooltip.bodyColor = isDark ? '#94A3B8' : '#cbd5e1';
                }
            }
        };

        const alternarTema = () => {
            aplicarTema(tema.value === 'dark' ? 'light' : 'dark');
            if (abaAtiva.value === 'dashboard') {
                setTimeout(renderCharts, 100);
            } else if (abaAtiva.value === 'heatmap') {
                setTimeout(renderCalendarioAnalytics, 100);
            } else if (abaAtiva.value === 'ciclo') {
                setTimeout(renderDonut, 100);
            }
        };

        const navegarPara = (aba) => {
            sidebarMobileAberta.value = false;
            if (aba === 'dashboard') {
                abrirDashboard();
            } else if (aba === 'resultados') {
                abrirResultados();
            } else {
                abaAtiva.value = aba;
            }
        };

        // Aplica o tema imediatamente
        aplicarTema(tema.value);

        // ==========================================
        // 1. ESTADO GLOBAL E NAVEGAÇÃO
        // ==========================================
        const estadoAplicacao = ref('app'); // 'wizard' ou 'app'
        const abaAtiva = ref('ciclo');
        const abaVerticalizado = ref('basicos'); // Corrigido: antes era ref({}) e deixava a tela vazia ao abrir
        const abaRaizResultados = ref('registrar'); // 'registrar' | 'historico'
        const abaRegistrar = ref('antiga'); // 'antiga' | 'encerramento'
        const abaHistorico = ref('avulsos'); // 'avulsos' | 'encerrados'

        // Estados de Carregamento e Prevenção de Duplo Clique
        const carregandoDados = ref(false);
        const carregandoResultados = ref(false);
        const processandoEdital = ref(false);
        const salvandoSessao = ref(false);
        const salvandoAvulso = ref(false);
        const salvandoEncerramento = ref(false);

        // Sistema de Notificações (Toast)
        const mensagemAlerta = ref('');
        const tipoAlerta = ref('sucesso'); // 'sucesso' | 'erro' | 'aviso'
        let alertaTimeout = null;

        function mostrarAlerta(msg, tipo = 'sucesso') {
            mensagemAlerta.value = msg;
            tipoAlerta.value = tipo;
            if (alertaTimeout) clearTimeout(alertaTimeout);
            alertaTimeout = setTimeout(() => {
                if (mensagemAlerta.value === msg) mensagemAlerta.value = '';
            }, 4500);
        }

        // ==========================================
        // 2. DADOS DO DOMÍNIO (BACK-END)
        // ==========================================
        const cicloAtivo = ref(null);
        const editais = ref([]);
        const sessoes = ref([]);
        const dashboardData = ref(null);
        const matrizSemanalData = ref({});
        const calendarioData = ref([]);
        const editalVerticalizadoData = ref({});

        // Wizard de Criação
        const wizardPasso = ref(0);
        const wizardDados = ref({
            nome: '',
            bancas: '',
            data: '',
            descricao: '',
            texto_basicos: '',
            texto_especificos: ''
        });
        const wizardEditalGerado = ref(null);
        const cicloForm = ref({ carga_horaria_semanal: 20, duracao_bloco_minutos: 60 });

        // Timer de Estudo
        const timerSegundos = ref(0);
        const timerRodando = ref(false);
        let timerInterval = null;

        // Utilitário de Data Local (YYYY-MM-DD)
        const getDataHojeLocal = () => {
            const d = new Date();
            const ano = d.getFullYear();
            const mes = String(d.getMonth() + 1).padStart(2, '0');
            const dia = String(d.getDate()).padStart(2, '0');
            return `${ano}-${mes}-${dia}`;
        };

        // Modais e Formulário de Sessão (Check-in)
        const modalCheckinAberto = ref(false);
        const modalResumoAberto = ref(false);
        const resumoSessaoAtual = ref(null);
        const verticalizadoAberto = ref({});
        const filtroVerticalizado = ref({}); // { [discId]: 'todos' | 'mais_cobrados' | 'prioritarios' | 'pendentes' }
        const ordenacaoVerticalizado = ref({}); // { [discId]: 'edital' | 'trilha' }

        const formSessao = ref({
            id: null,
            disciplina_id: '',
            bloco_ciclo_id: null,
            topico_id: '',
            data: getDataHojeLocal(),
            tempo_estudado_minutos: 60,
            duracao_minutos: 60,
            qtd_questoes_total: 0,
            qtd_acertos: 0,
            qtd_erros: 0,
            acertos: 0,
            erros: 0,
            questoes_totais: 0,
            nivel_concentracao: 3,
            desempenho_subjetivo: 3,
            material_utilizado: '',
            is_revisao_anki: false,
            avancar_ciclo: true,
            notas_observacoes: ''
        });

        // Módulo de Resultados & Raio-X
        const resultadoAtual = ref(null);
        const editandoCiclo = ref(false);
        const disciplinasEncerramento = ref([]);
        const insightsRaioX = ref([]);
        const resultadosEncerrados = ref([]);
        const resultadosAvulsos = ref([]);
        const avulsoSelecionado = ref(null);
        const idEmEdicaoAvulso = ref(null);

        const formResultado = ref({
            edital_id: null,
            nome_prova: '',
            data_prova: getDataHojeLocal(),
            nota_final: 0,
            nota_corte: 0,
            total_pontos_prova: '',
            nota_minima_aprovados: '',
            nota_maxima_aprovados: '',
            posicao: 0,
            total_vagas: 0,
            nota_discursiva: 0,
            resultado_final: 'Aprovado'
        });

        const formAvulso = ref({
            nome_prova: '',
            banca: '',
            data_prova: '',
            nota_final: '',
            nota_corte: '',
            total_pontos_prova: '',
            acertos_basicos: '',
            erros_basicos: '',
            nota_basicos: '',
            acertos_especificos: '',
            erros_especificos: '',
            nota_especificos: '',
            nota_discursiva: '',
            posicao: '',
            resultado_final: 'Aprovado'
        });

        // ==========================================
        // 2.1 INFORMAÇÕES DA PROVA / TESTE LOCAL
        // ==========================================
        const dadosProvaPadrao = {
            concurso: 'SEFAZ ALAGOAS',
            cargo: 'Auditor Fiscal da Receita Estadual',
            especialidade: 'Tecnologia da Informação',
            banca: 'Cebraspe',
            estilo_banca: 'Certo / Errado (1 anula 1)',
            data_prova: '2026-11-29',
            nota_corte: 78.5,
            total_vagas: '35 vagas (28 AC | 7 Cotas)',
            local_prova: 'Maceió - AL',
            formato_prova: '160 itens + Discursiva',
            status_edital: 'Pós-Edital (Edital Publicado)'
        };

        const carregarDadosProva = () => {
            try {
                const salvo = localStorage.getItem('orbis_painel_prova');
                if (salvo) {
                    return { ...dadosProvaPadrao, ...JSON.parse(salvo) };
                }
            } catch (e) {
                console.warn('Erro ao carregar dadosProva do localStorage:', e);
            }
            return { ...dadosProvaPadrao };
        };

        const dadosProva = ref(carregarDadosProva());
        const modalConfigProvaAberto = ref(false);
        const modalAlertaMarcoAberto = ref(false);
        const formConfigProva = ref({ ...dadosProva.value });

        const carregarDadosProvaServidor = async () => {
            try {
                const res = await fetch('/api/configuracao-prova');
                if (res.ok) {
                    const data = await res.json();
                    const dadosAtualizados = {
                        concurso: data.concurso || dadosProvaPadrao.concurso,
                        cargo: data.cargo || dadosProvaPadrao.cargo,
                        especialidade: data.especialidade || dadosProvaPadrao.especialidade,
                        banca: data.banca || dadosProvaPadrao.banca,
                        estilo_banca: data.estilo_banca || dadosProvaPadrao.estilo_banca,
                        data_prova: data.data_prova || dadosProvaPadrao.data_prova,
                        nota_corte: (data.nota_corte !== null && data.nota_corte !== undefined) ? data.nota_corte : dadosProvaPadrao.nota_corte,
                        total_vagas: data.total_vagas || dadosProvaPadrao.total_vagas,
                        local_prova: data.local_prova || dadosProvaPadrao.local_prova,
                        formato_prova: data.formato_prova || dadosProvaPadrao.formato_prova,
                        status_edital: data.status_edital || dadosProvaPadrao.status_edital
                    };
                    dadosProva.value = dadosAtualizados;
                    try {
                        localStorage.setItem('orbis_painel_prova', JSON.stringify(dadosAtualizados));
                    } catch (e) {}

                    if (data.marcos_alertados) {
                        try {
                            const marcosObj = typeof data.marcos_alertados === 'string' ? JSON.parse(data.marcos_alertados) : data.marcos_alertados;
                            localStorage.setItem('orbis_marcos_alertados', JSON.stringify(marcosObj));
                        } catch (e) {}
                    }
                }
            } catch (e) {
                console.warn('Erro ao carregar dadosProva do servidor:', e);
            }
        };

        const getMarcosAlertados = () => {
            try {
                const salvo = localStorage.getItem('orbis_marcos_alertados');
                return salvo ? JSON.parse(salvo) : {};
            } catch (e) {
                return {};
            }
        };

        const registrarMarcoAlertado = (marco, dataProva) => {
            try {
                const chave = dataProva || dadosProva.value?.data_prova || 'padrao';
                const dados = getMarcosAlertados();
                if (!dados[chave]) dados[chave] = {};
                dados[chave][marco] = true;
                // Ao alertar marco menor (ex: 60d), marcar também marcos maiores para não alertar retroativamente
                if (marco <= 60) dados[chave][90] = true;
                if (marco <= 30) dados[chave][60] = true;
                localStorage.setItem('orbis_marcos_alertados', JSON.stringify(dados));

                // Sincronizar marco alertado com o backend
                fetch('/api/configuracao-prova/marcar-alerta', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ marco, data_prova: chave })
                }).catch(e => console.warn('Erro ao sincronizar marco alertado:', e));
            } catch (e) {
                console.warn(e);
            }
        };

        const marcoJaAlertado = (marco, dataProva) => {
            try {
                const chave = dataProva || dadosProva.value?.data_prova || 'padrao';
                const dados = getMarcosAlertados();
                return !!(dados[chave] && dados[chave][marco]);
            } catch (e) {
                return false;
            }
        };

        const resetarMarcosAlertados = async () => {
            try {
                localStorage.removeItem('orbis_marcos_alertados');
                await fetch('/api/configuracao-prova/resetar-alertas', { method: 'POST' }).catch(() => {});
                mostrarAlerta('Histórico de avisos de marcos resetado com sucesso!', 'info');
            } catch (e) {}
        };

        const abrirModalConfigProva = () => {
            formConfigProva.value = { ...dadosProva.value };
            modalConfigProvaAberto.value = true;
        };

        const abrirAlertaMarco = () => {
            modalAlertaMarcoAberto.value = true;
        };

        const fecharAlertaMarco = () => {
            if (marcoAlerta.value) {
                registrarMarcoAlertado(marcoAlerta.value.diasMarco, dadosProva.value?.data_prova);
            }
            modalAlertaMarcoAberto.value = false;
        };

        const definirDataProvaAtalho = (dias) => {
            const d = new Date();
            d.setDate(d.getDate() + dias);
            const ano = d.getFullYear();
            const mes = String(d.getMonth() + 1).padStart(2, '0');
            const dia = String(d.getDate()).padStart(2, '0');
            formConfigProva.value.data_prova = `${ano}-${mes}-${dia}`;
        };

        const salvarDadosProva = async () => {
            const dataAntiga = dadosProva.value.data_prova;
            dadosProva.value = { ...formConfigProva.value };
            try {
                localStorage.setItem('orbis_painel_prova', JSON.stringify(dadosProva.value));
            } catch (e) {
                console.warn(e);
            }
            modalConfigProvaAberto.value = false;

            // Sincronizar com o servidor backend
            try {
                const res = await fetch('/api/configuracao-prova', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dadosProva.value)
                });
                if (res.ok) {
                    mostrarAlerta('Dados da prova sincronizados no servidor!', 'sucesso');
                } else {
                    mostrarAlerta('Dados salvos localmente, erro na sincronização.', 'aviso');
                }
            } catch (e) {
                console.warn(e);
                mostrarAlerta('Dados salvos localmente (offline).', 'aviso');
            }

            // Se estiver em um dos marcos (<= 90 dias):
            if (marcoAlerta.value) {
                const marco = marcoAlerta.value.diasMarco;
                const dataNova = dadosProva.value.data_prova;
                // Se a data mudou ou se o marco ainda não foi alertado
                if (dataNova !== dataAntiga || !marcoJaAlertado(marco, dataNova)) {
                    registrarMarcoAlertado(marco, dataNova);
                    setTimeout(() => {
                        modalAlertaMarcoAberto.value = true;
                    }, 350);
                }
            }
        };

        const restaurarDadosProvaPadrao = async () => {
            dadosProva.value = { ...dadosProvaPadrao };
            formConfigProva.value = { ...dadosProvaPadrao };
            try {
                localStorage.removeItem('orbis_painel_prova');
                localStorage.removeItem('orbis_marcos_alertados');
            } catch (e) {}
            try {
                await fetch('/api/configuracao-prova', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dadosProvaPadrao)
                });
                await fetch('/api/configuracao-prova/resetar-alertas', { method: 'POST' });
            } catch (e) {}
            modalConfigProvaAberto.value = false;
            mostrarAlerta('Dados da prova restaurados para o padrão!', 'info');
        };

        // ==========================================
        // 2.2 INSIGHTS DE IA (COACH DE ESTUDOS)
        // ==========================================
        const modalInsightsIAAberto = ref(false);
        const carregandoInsightsIA = ref(false);
        const insightsIA = ref(null);
        const statusChaveGemini = ref({ configurada: false, chave_mascarada: null, origem: 'nenhuma' });
        const mostrarConfigChaveIA = ref(false);
        const chaveGeminiInput = ref('');
        const salvandoChaveIA = ref(false);

        const verificarStatusChaveIA = async () => {
            try {
                const res = await fetch('/api/ia/status-chave');
                if (res.ok) {
                    statusChaveGemini.value = await res.json();
                }
            } catch (e) {
                console.warn(e);
            }
        };

        const carregarInsightsIA = async (forcar = false) => {
            carregandoInsightsIA.value = true;
            try {
                const endpoint = forcar ? '/api/ia/insights/recarregar' : '/api/ia/insights';
                const method = forcar ? 'POST' : 'GET';
                const res = await fetch(endpoint, { method });
                if (res.ok) {
                    insightsIA.value = await res.json();
                }
            } catch (e) {
                console.warn('Erro ao carregar Insights de IA:', e);
            } finally {
                carregandoInsightsIA.value = false;
            }
        };

        const salvarChaveGemini = async () => {
            salvandoChaveIA.value = true;
            try {
                const res = await fetch('/api/ia/config-chave', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: chaveGeminiInput.value })
                });
                if (res.ok) {
                    const data = await res.json();
                    insightsIA.value = data.insight;
                    mostrarConfigChaveIA.value = false;
                    chaveGeminiInput.value = '';
                    await verificarStatusChaveIA();
                    mostrarAlerta(data.configurada ? 'Chave Gemini conectada! Análise viva gerada com sucesso.' : 'Chave removida. Modo heurístico ativo.', 'sucesso');
                }
            } catch (e) {
                mostrarAlerta('Erro ao conectar chave do Gemini.', 'erro');
            } finally {
                salvandoChaveIA.value = false;
            }
        };

        const abrirModalInsightsIA = async () => {
            modalInsightsIAAberto.value = true;
            verificarStatusChaveIA();
            if (!insightsIA.value) {
                await carregarInsightsIA();
            }
        };

        const formatarTextoIA = (texto) => {
            if (!texto) return '';
            let safe = String(texto)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            // Formata **negrito** com classe destacada
            safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-slate-900 dark:text-white">$1</strong>');
            // Formata *itálico*
            safe = safe.replace(/\*(.*?)\*/g, '<em class="italic text-slate-700 dark:text-slate-300">$1</em>');
            // Formata `código`
            safe = safe.replace(/`(.*?)`/g, '<code class="px-1 py-0.5 rounded bg-amber-500/15 text-amber-700 dark:text-amber-300 font-mono text-[11px]">$1</code>');
            return safe;
        };

        // Instâncias de Gráficos (Chart.js)
        let chartCicloDonutInstance = null;
        let chartEvolucaoInstance = null;
        let chartEvolucaoSemanalInstance = null;
        let chartDiscInstance = null;
        let chartAderenciaInstance = null;
        let chartDiaSemanaInstance = null;
        let chartIntensidadeInstance = null;
        let chartEvolucaoRiscoInstance = null;
        let chartEvolucaoAvulsosInstance = null;
        let chartDesempenhoAvulsosInstance = null;

        // ==========================================
        // 3. PROPRIEDADES COMPUTADAS (COMPUTED)
        // ==========================================
        const diasAteProva = computed(() => {
            if (!dadosProva.value?.data_prova) return null;
            const hoje = new Date();
            hoje.setHours(0, 0, 0, 0);
            const dataP = new Date(dadosProva.value.data_prova + 'T00:00:00');
            if (isNaN(dataP.getTime())) return null;
            const diffMs = dataP.getTime() - hoje.getTime();
            return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
        });

        const dataProvaFormatada = computed(() => {
            if (!dadosProva.value?.data_prova) return 'Data a definir';
            try {
                const partes = String(dadosProva.value.data_prova).split('-');
                if (partes.length === 3) {
                    return `${partes[2]}/${partes[1]}/${partes[0]}`;
                }
            } catch (e) {}
            return dadosProva.value.data_prova;
        });

        const comparativoCorte = computed(() => {
            const corte = Number(dadosProva.value?.nota_corte) || 0;
            const acerto = Number(dashboardData.value?.metricas_gerais?.percentual_acerto_geral) || 79.9;
            const diff = acerto - corte;
            return {
                corte,
                acerto,
                diff: Number(diff.toFixed(1)),
                acima: diff >= 0
            };
        });

        const zonaProva = computed(() => {
            const dias = diasAteProva.value;
            if (dias === null || dias === undefined) return null;

            if (dias >= 90) {
                return {
                    zona: 'cadencia',
                    tag: 'Cadência & Constância',
                    icone: 'fa-solid fa-shield-halved',
                    corBadge: 'bg-blue-500/15 text-blue-600 dark:text-[#60A5FA] border-blue-500/30',
                    corAlerta: 'from-blue-500/10 to-indigo-500/10 border-blue-400/30 text-blue-900 dark:text-blue-100',
                    iconeAlerta: 'fa-regular fa-compass text-blue-500 dark:text-[#60A5FA]',
                    mensagemMotivacional: 'Construa sua base com firmeza e ritmo sustentável. A constância diária nos ciclos é o que constrói os primeiros lugares!',
                    orientacoes: [
                        'Mantenha a regularidade semanal sem pular matérias da esteira.',
                        'Avance pela teoria e resumos estruturados dos tópicos mais densos.',
                        'Alimente diariamente seus cards no Anki para retenção a longo prazo.'
                    ]
                };
            } else if (dias >= 31 && dias <= 89) { // 89 até 31
                return {
                    zona: 'consolidacao',
                    tag: 'Consolidação & Aceleração',
                    icone: 'fa-solid fa-bolt',
                    corBadge: 'bg-indigo-500/15 text-indigo-600 dark:text-[#C4B5FD] border-indigo-500/30',
                    corAlerta: 'from-indigo-500/10 to-purple-500/10 border-indigo-400/30 text-indigo-900 dark:text-indigo-100',
                    iconeAlerta: 'fa-solid fa-gauge-high text-indigo-500 dark:text-[#C4B5FD]',
                    mensagemMotivacional: 'Acelere o ritmo e feche as lacunas! Intensifique as questões da banca e transforme horas líquidas em velocidade e retenção máxima.',
                    orientacoes: [
                        'Aumente o volume de questões comentadas e simulados da banca.',
                        'Ataque diretamente os tópicos com menor percentual de acerto no Raio-X.',
                        'Calibre o tempo de resposta por questão visando a dinâmica da prova.'
                    ]
                };
            } else if (dias > 0 && dias <= 30) { // ultimos 30 dias
                return {
                    zona: 'reta_final',
                    tag: 'Ajuste Fino & Reta Final',
                    icone: 'fa-solid fa-fire',
                    corBadge: 'bg-amber-500/15 text-amber-600 dark:text-[#FBBF24] border-amber-500/30 animate-pulse',
                    corAlerta: 'from-amber-500/15 to-rose-500/10 border-amber-400/40 text-amber-950 dark:text-amber-100',
                    iconeAlerta: 'fa-solid fa-triangle-exclamation text-amber-500 dark:text-[#FBBF24]',
                    mensagemMotivacional: 'Reta final decisiva! Foco cirúrgico em revisões ativas no Anki, simulados cronometrados e blindagem emocional. A sua vaga está próxima!',
                    orientacoes: [
                        'Revisão intensiva de lei seca, fórmulas e decorebas essenciais.',
                        'Simulados nos horários exatos da aplicação para controle de tempo e ritmo.',
                        'Priorize o sono e a saúde mental para chegar com energia máxima no domingo.'
                    ]
                };
            } else if (dias === 0) {
                return {
                    zona: 'dia_prova',
                    tag: '🌟 Dia da Prova!',
                    icone: 'fa-solid fa-star',
                    corBadge: 'bg-emerald-500/15 text-emerald-600 dark:text-[#34D399] border-emerald-500/30 animate-bounce',
                    corAlerta: 'from-emerald-500/15 to-teal-500/10 border-emerald-400/40 text-emerald-950 dark:text-emerald-100',
                    iconeAlerta: 'fa-solid fa-trophy text-emerald-500 dark:text-[#34D399]',
                    mensagemMotivacional: 'Chegou o grande momento! Confie no seu preparo e em cada bloco cumprido. Dê o seu melhor e conquiste a sua vaga!',
                    orientacoes: [
                        'Leia atentamente cada enunciado e controle o tempo por questão.',
                        'Em itens de dúvida extrema, confie na estratégia treinada da banca.',
                        'Você está preparado. Boa prova!'
                    ]
                };
            } else {
                return {
                    zona: 'realizada',
                    tag: '✓ Prova Realizada',
                    icone: 'fa-solid fa-check',
                    corBadge: 'bg-slate-500/15 text-slate-600 dark:text-[#94A3B8] border-slate-500/30',
                    corAlerta: 'from-slate-500/10 to-slate-600/10 border-slate-400/30 text-slate-800 dark:text-slate-200',
                    iconeAlerta: 'fa-solid fa-flag-checkered text-slate-500',
                    mensagemMotivacional: 'Etapa cumprida! Acesse a aba Resultados & Raio-X para registrar o desempenho oficial e conferir os dados.',
                    orientacoes: [
                        'Registre seus acertos oficiais por disciplina na aba Resultados.',
                        'Gere o diagnóstico do Raio-X para consolidar seus aprendizados.'
                    ]
                };
            }
        });

        const marcoAlerta = computed(() => {
            const dias = diasAteProva.value;
            if (dias === null || dias === undefined || dias < 0) return null;

            if (dias <= 30 && dias > 0) {
                const exato = dias === 30;
                return {
                    diasMarco: 30,
                    diasRestantes: dias,
                    exato,
                    titulo: exato
                        ? '🔥 Alerta Reta Final: Faltam 30 Dias para a Prova!'
                        : `🔥 Alerta Reta Final: Faltam menos de 30 dias para a prova (${dias} ${dias === 1 ? 'dia restante' : 'dias restantes'})!`,
                    subtitulo: exato
                        ? 'Entramos na reta final decisiva! Hora do ajuste fino, revisões ativas e controle de tempo.'
                        : `Entramos na reta finalíssima! Faltam menos de 30 dias para a prova (restam ${dias} ${dias === 1 ? 'dia' : 'dias'}): foco cirúrgico em revisões ativas no Anki e simulados cronometrados!`,
                    badgeTexto: exato ? 'Alerta dos 30 Dias (Reta Final)' : `Alerta: Menos de 30 Dias (${dias}d)`,
                    badgeClasse: 'bg-rose-500/20 text-rose-600 dark:text-[#F87171] border-rose-500/40'
                };
            } else if (dias <= 60 && dias > 30) {
                const exato = dias === 60;
                return {
                    diasMarco: 60,
                    diasRestantes: dias,
                    exato,
                    titulo: exato
                        ? '⚡ Alerta de Aceleração: Faltam 60 Dias para a Prova!'
                        : `⚡ Alerta de Aceleração: Faltam menos de 60 dias para a prova (${dias} dias restantes)!`,
                    subtitulo: exato
                        ? 'Dois meses para o grande dia: aumente o ritmo nas questões e consolide o edital!'
                        : `Faltam menos de 60 dias para a prova! Restam exatamente ${dias} dias: intensifique baterias de questões da banca e ataque as lacunas!`,
                    badgeTexto: exato ? 'Alerta dos 60 Dias' : `Alerta: Menos de 60 Dias (${dias}d)`,
                    badgeClasse: 'bg-indigo-500/20 text-indigo-600 dark:text-[#C4B5FD] border-indigo-500/40'
                };
            } else if (dias <= 90 && dias > 60) {
                const exato = dias === 90;
                return {
                    diasMarco: 90,
                    diasRestantes: dias,
                    exato,
                    titulo: exato
                        ? '🔔 Alerta de Transição: Faltam 90 Dias para a Prova!'
                        : `🔔 Alerta de Transição: Faltam menos de 90 dias para a prova (${dias} dias restantes)!`,
                    subtitulo: exato
                        ? 'Início do trimestre da prova: consolidação teórica e foco massivo em questões da banca!'
                        : `Faltam menos de 90 dias para a prova! Restam exatamente ${dias} dias: momento decisivo para consolidar a base teórica e manter ritmo constante nos ciclos!`,
                    badgeTexto: exato ? 'Alerta dos 90 Dias' : `Alerta: Menos de 90 Dias (${dias}d)`,
                    badgeClasse: 'bg-blue-500/20 text-blue-600 dark:text-[#60A5FA] border-blue-500/40'
                };
            }
            return null;
        });

        const blocoAtual = computed(() => {
            if (!cicloAtivo.value || !cicloAtivo.value.blocos || cicloAtivo.value.blocos.length === 0) return null;
            return cicloAtivo.value.blocos[cicloAtivo.value.bloco_atual_index || 0];
        });

        const todasDisciplinas = computed(() => {
            const list = [];
            const editalId = cicloAtivo.value?.edital_id || (editais.value.length > 0 ? editais.value[0].id : null);
            if (editalId) {
                const ed = editais.value.find(e => e.id === editalId);
                if (ed && ed.disciplinas) {
                    ed.disciplinas.forEach(d => {
                        if (d.categoria !== 'REVISAO_ANKI') list.push(d);
                    });
                }
            }
            return list;
        });

        const topicosDaDisciplina = computed(() => {
            const discId = formSessao.value?.disciplina_id;
            if (!discId) return [];
            const numId = Number(discId);

            let disc = todasDisciplinas.value ? todasDisciplinas.value.find(d => Number(d.id) === numId) : null;

            if (!disc && editais.value) {
                for (const ed of editais.value) {
                    if (ed.disciplinas) {
                        const encontrada = ed.disciplinas.find(d => Number(d.id) === numId);
                        if (encontrada) {
                            disc = encontrada;
                            break;
                        }
                    }
                }
            }

            if ((!disc || !disc.topicos || disc.topicos.length === 0) && editalVerticalizadoData.value) {
                const todas = [
                    ...(editalVerticalizadoData.value.BASICOS || []),
                    ...(editalVerticalizadoData.value.ESPECIFICOS || [])
                ];
                const found = todas.find(d => Number(d.id) === numId);
                if (found && found.topicos) disc = found;
            }

            if (!disc && blocoAtual.value && Number(blocoAtual.value.disciplina_id) === numId) {
                disc = blocoAtual.value.disciplina;
            }

            if (disc && disc.topicos && Array.isArray(disc.topicos)) {
                const lista = [...disc.topicos];
                return lista.sort((a, b) => {
                    const getPeso = (t) => {
                        if (t.prioridade === 1) return 1;
                        if (t.prioridade === 2) return 2;
                        if (t.prioridade === 3) return 3;
                        if (t.mais_cobrado) return 4;
                        return 5;
                    };
                    const pa = getPeso(a);
                    const pb = getPeso(b);
                    if (pa !== pb) return pa - pb;
                    return (a.ordem || 0) - (b.ordem || 0);
                });
            }
            return [];
        });

        const percentualGlobalEdital = computed(() => {
            if (!cicloAtivo.value || !editais.value) return 0;
            const ed = editais.value.find(e => e.id === cicloAtivo.value.edital_id);
            if (!ed) return 0;
            return getEstatisticasEdital(ed).perc_visto.toFixed(0);
        });

        const totaisEncerramento = computed(() => {
            let acertosBasicos = 0, errosBasicos = 0, acertosEspec = 0, errosEspec = 0;
            disciplinasEncerramento.value.forEach(d => {
                const a = Number(d.acertos) || 0;
                const e = Number(d.erros) || 0;
                if (d.grupo === 'BASICOS') {
                    acertosBasicos += a;
                    errosBasicos += e;
                } else {
                    acertosEspec += a;
                    errosEspec += e;
                }
            });
            return { acertosBasicos, errosBasicos, acertosEspec, errosEspec };
        });

        const rankingRevisoes = computed(() => {
            if (!resultadoAtual.value || !resultadoAtual.value.desempenho_disciplinas) return [];
            return [...resultadoAtual.value.desempenho_disciplinas].sort((a, b) => (b.revisoes || 0) - (a.revisoes || 0));
        });

        const quadrantesRaioX = computed(() => {
            const quad = {
                dominado: [],
                eficienciaAlta: [],
                eficienciaBaixa: [],
                lacuna: []
            };

            if (!resultadoAtual.value || !resultadoAtual.value.desempenho_disciplinas) return quad;

            const tempos = resultadoAtual.value.desempenho_disciplinas.map(d => d.horas_dedicadas).sort((a, b) => a - b);
            const medianaTempo = tempos.length > 0 ? tempos[Math.floor(tempos.length / 2)] : 0;
            const tempoCorte = medianaTempo > 0 ? medianaTempo : 5.0;

            resultadoAtual.value.desempenho_disciplinas.forEach(d => {
                if (d.horas_dedicadas === 0 && d.questoes_resolvidas === 0 && (!d.acertos_prova_perc || d.acertos_prova_perc === 0)) return;
                const acerto = (d.acertos_prova_perc !== undefined && d.acertos_prova_perc !== null && d.acertos_prova_perc > 0)
                    ? d.acertos_prova_perc
                    : (d.percentual_acerto || 0);

                if (d.horas_dedicadas >= tempoCorte && acerto >= 70) quad.dominado.push(d);
                else if (d.horas_dedicadas < tempoCorte && acerto >= 70) quad.eficienciaAlta.push(d);
                else if (d.horas_dedicadas >= tempoCorte && acerto < 70) quad.eficienciaBaixa.push(d);
                else quad.lacuna.push(d);
            });
            return quad;
        });

        const resumoProvasAvulsas = computed(() => {
            const list = resultadosAvulsos.value || [];
            if (list.length === 0) {
                return {
                    ultimaNota: { valor: '-', sub: 'Nenhuma prova registrada', status: 'neutro' },
                    distanciaCorte: { valor: '-', sub: 'Sem dados de corte', status: 'neutro' },
                    melhorDesempenho: { valor: '-', sub: 'Aguardando registros', status: 'neutro' },
                    pontoMelhoria: { valor: '-', sub: 'Aguardando registros', status: 'neutro' }
                };
            }

            const ordenadas = [...list].sort((a, b) => {
                const dA = a.data_prova ? String(a.data_prova).trim() : '';
                const dB = b.data_prova ? String(b.data_prova).trim() : '';
                if (!dA && !dB) return (a.id || 0) - (b.id || 0);
                if (!dA) return -1;
                if (!dB) return 1;
                return dA.localeCompare(dB);
            });

            const ultima = ordenadas[ordenadas.length - 1];
            const notaUltima = Number(ultima.nota_final) || 0;
            const totalPtsUltima = Number(ultima.total_pontos_prova) || 0;
            let ultimaPerc = totalPtsUltima > 0 ? ((notaUltima / totalPtsUltima) * 100).toFixed(1).replace('.', ',') + '%' : `${notaUltima} pts`;
            const ultimaSub = ultima.nome_prova || (ultima.data_prova ? formatarData(ultima.data_prova) : 'Prova recente');

            let distCorteVal = '-';
            let distCorteSub = 'Corte não informado';
            let distStatus = 'neutro';
            if (ultima.nota_corte !== null && ultima.nota_corte !== undefined && ultima.nota_corte !== '') {
                const corte = Number(ultima.nota_corte);
                if (totalPtsUltima > 0) {
                    const diff = ((notaUltima - corte) / totalPtsUltima) * 100;
                    distCorteVal = (diff >= 0 ? '+' : '') + diff.toFixed(1).replace('.', ',') + '%';
                    distStatus = diff >= 0 ? 'positivo' : 'negativo';
                    distCorteSub = diff >= 0 ? 'Acima da nota de corte' : 'Abaixo da nota de corte';
                } else if (corte > 0) {
                    const diff = ((notaUltima / corte) - 1) * 100;
                    distCorteVal = (diff >= 0 ? '+' : '') + diff.toFixed(1).replace('.', ',') + '%';
                    distStatus = diff >= 0 ? 'positivo' : 'negativo';
                    distCorteSub = diff >= 0 ? 'Acima da nota de corte' : 'Abaixo da nota de corte';
                }
            }

            let melhor = null;
            let melhorPerc = -1;
            ordenadas.forEach(p => {
                const n = Number(p.nota_final) || 0;
                const tot = Number(p.total_pontos_prova) || 0;
                const perc = tot > 0 ? (n / tot) * 100 : n;
                if (perc > melhorPerc) {
                    melhorPerc = perc;
                    melhor = p;
                }
            });
            const melhorVal = melhor ? (Number(melhor.total_pontos_prova) > 0 ? melhorPerc.toFixed(1).replace('.', ',') + '%' : `${melhorPerc} pts`) : '-';
            const melhorSub = melhor ? melhor.nome_prova : '-';

            let totalAcBas = 0, totalErBas = 0, totalAcEsp = 0, totalErEsp = 0;
            ordenadas.forEach(p => {
                totalAcBas += Number(p.acertos_basicos) || 0;
                totalErBas += Number(p.erros_basicos) || 0;
                totalAcEsp += Number(p.acertos_especificos) || 0;
                totalErEsp += Number(p.erros_especificos) || 0;
            });
            const basTotal = totalAcBas + totalErBas;
            const espTotal = totalAcEsp + totalErEsp;
            const percBas = basTotal > 0 ? (totalAcBas / basTotal) * 100 : null;
            const percEsp = espTotal > 0 ? (totalAcEsp / espTotal) * 100 : null;

            let pontoMelhoriaVal = '-';
            let pontoMelhoriaSub = 'Dados insuficientes';
            if (percBas !== null && percEsp !== null) {
                if (percBas < percEsp) {
                    pontoMelhoriaVal = `Básicos (${percBas.toFixed(0)}%)`;
                    pontoMelhoriaSub = `Abaixo de Específicos (${percEsp.toFixed(0)}%)`;
                } else if (percEsp < percBas) {
                    pontoMelhoriaVal = `Específicos (${percEsp.toFixed(0)}%)`;
                    pontoMelhoriaSub = `Abaixo de Básicos (${percBas.toFixed(0)}%)`;
                } else {
                    pontoMelhoriaVal = `Equilibrado (${percBas.toFixed(0)}%)`;
                    pontoMelhoriaSub = 'Básicos e Específicos equilibrados';
                }
            } else if (percBas !== null) {
                pontoMelhoriaVal = `Básicos (${percBas.toFixed(0)}%)`;
                pontoMelhoriaSub = 'Apenas básicos informados';
            } else if (percEsp !== null) {
                pontoMelhoriaVal = `Específicos (${percEsp.toFixed(0)}%)`;
                pontoMelhoriaSub = 'Apenas específicos informados';
            }

            return {
                ultimaNota: { valor: ultimaPerc, sub: ultimaSub, status: 'info' },
                distanciaCorte: { valor: distCorteVal, sub: distCorteSub, status: distStatus },
                melhorDesempenho: { valor: melhorVal, sub: melhorSub, status: 'positivo' },
                pontoMelhoria: { valor: pontoMelhoriaVal, sub: pontoMelhoriaSub, status: 'alerta' }
            };
        });

        // ==========================================
        // 4. FORMATADORES E HELPERS VISUAIS
        // ==========================================
        const formatarTempoTimer = (s) => {
            const hrs = Math.floor(s / 3600);
            const mins = Math.floor((s % 3600) / 60);
            const secs = s % 60;
            return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        };

        const formatarHorasDecimais = (h) => {
            if (!h) return '0h';
            return Number(h).toFixed(1) + 'h';
        };

        const formatarData = (isoStr) => {
            if (!isoStr) return '';
            const p = String(isoStr).split('-');
            if (p.length >= 3) return `${p[2].substring(0, 2)}/${p[1]}`;
            return isoStr;
        };

        const formatarDataCurta = (isoStr) => {
            if (!isoStr) return '';
            const p = String(isoStr).split('-');
            if (p.length >= 3) {
                const day = p[2].includes('T') ? p[2].split('T')[0] : p[2].substring(0, 2);
                return `${day}/${p[1]}/${p[0]}`;
            }
            return isoStr;
        };

        const formatarTituloTopico = (t) => {
            if (!t) return '';
            const tit = (t.titulo || '').trim();
            let base = tit;
            if (!/^\d+(\.\d+)*\.\s+/.test(tit)) {
                const m = tit.match(/^(\d+(\.\d+)*)\s+(.*)$/);
                if (m) base = `${m[1]}. ${m[3]}`;
            }
            const badges = [];
            if (t.prioridade === 1) badges.push('⚡ P1');
            else if (t.prioridade === 2) badges.push('⭐ P2');
            else if (t.prioridade === 3) badges.push('🔹 P3');
            if (t.mais_cobrado) badges.push('🔥');

            return badges.length > 0 ? `[${badges.join(' ')}] ${base}` : base;
        };

        const formatarPercentualBR = (val) => {
            if (val === null || val === undefined || isNaN(val)) return '-';
            const num = Number(val);
            const s = num.toFixed(2);
            if (s.endsWith('.00')) return num.toFixed(0) + '%';
            if (s.endsWith('0')) return num.toFixed(1).replace('.', ',') + '%';
            return num.toFixed(2).replace('.', ',') + '%';
        };

        const badgeTaxaAcertoBg = (perc) => {
            if (perc >= 80) return 'bg-emerald-50 dark:bg-[#34D399]/15 text-emerald-700 dark:text-[#34D399] border-emerald-200 dark:border-[#34D399]/30';
            if (perc >= 60) return 'bg-amber-50 dark:bg-[#FBBF24]/15 text-amber-700 dark:text-[#FBBF24] border-amber-200 dark:border-[#FBBF24]/30';
            return 'bg-rose-50 dark:bg-[#F87171]/15 text-rose-700 dark:text-[#F87171] border-rose-200 dark:border-[#F87171]/30';
        };

        const badgeTextTaxa = (perc) => {
            if (perc >= 80) return 'text-emerald-600 dark:text-[#34D399] font-extrabold';
            if (perc >= 60) return 'text-amber-600 dark:text-[#FBBF24] font-extrabold';
            return 'text-rose-600 dark:text-[#F87171] font-extrabold';
        };

        const getAproveitamentoClasses = (perc) => {
            if (perc >= 80) return { bg: 'from-emerald-500/20 to-emerald-600/20', text: 'text-emerald-500 dark:text-[#34D399]', border: 'border-emerald-500/30 dark:border-[#34D399]/40' };
            if (perc >= 60) return { bg: 'from-blue-500/20 to-blue-600/20', text: 'text-blue-500 dark:text-[#60A5FA]', border: 'border-blue-500/30 dark:border-[#60A5FA]/40' };
            if (perc >= 40) return { bg: 'from-amber-500/20 to-amber-600/20', text: 'text-amber-500 dark:text-[#FBBF24]', border: 'border-amber-500/30 dark:border-[#FBBF24]/40' };
            return { bg: 'from-rose-500/20 to-rose-600/20', text: 'text-rose-500 dark:text-[#F87171]', border: 'border-rose-500/30 dark:border-[#F87171]/40' };
        };

        const getNomeDisciplina = (id) => {
            const d = todasDisciplinas.value.find(x => x.id === id);
            if (d) return d.nome;
            for (const ed of editais.value) {
                const found = (ed.disciplinas || []).find(x => x.id === id);
                if (found) return found.nome;
            }
            return `ID: ${id}`;
        };

        const toggleVerticalizado = (id) => {
            verticalizadoAberto.value[id] = !verticalizadoAberto.value[id];
        };

        const getTopicosFiltradosEOrdenados = (disc) => {
            if (!disc || !disc.topicos) return [];
            let lista = [...disc.topicos];
            
            // Filtro (se o usuário selecionou apenas Mais Cobrados, Prioritários, P1 ou Pendentes)
            const f = filtroVerticalizado.value[disc.id] || 'todos';
            if (f === 'mais_cobrados') {
                lista = lista.filter(t => t.mais_cobrado);
            } else if (f === 'prioritarios') {
                lista = lista.filter(t => t.prioridade !== null && t.prioridade !== undefined);
            } else if (f === 'p1') {
                lista = lista.filter(t => t.prioridade === 1);
            } else if (f === 'pendentes') {
                lista = lista.filter(t => !t.visto && !t.concluido);
            }

            // Preserva rigorosamente a ordem original do edital (t.ordem e comparação numérica natural)
            lista.sort((a, b) => {
                const oa = (a.ordem !== undefined && a.ordem !== null) ? Number(a.ordem) : Number(a.id || 0);
                const ob = (b.ordem !== undefined && b.ordem !== null) ? Number(b.ordem) : Number(b.id || 0);
                if (oa !== ob) return oa - ob;
                return (a.titulo || '').localeCompare(b.titulo || '', undefined, { numeric: true, sensitivity: 'base' });
            });

            return lista;
        };

        const setFiltroVerticalizado = (discId, tipo) => {
            filtroVerticalizado.value[discId] = tipo;
        };

        const setOrdenacaoVerticalizado = (discId, modo) => {
            ordenacaoVerticalizado.value[discId] = modo;
        };

        const toggleMaisCobrado = async (topico) => {
            const novoValor = !topico.mais_cobrado;
            topico.mais_cobrado = novoValor;

            sincronizarTopicoEmEstado(topico.id, { mais_cobrado: novoValor });

            try {
                const res = await fetch(`/api/editais/topicos/${topico.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mais_cobrado: novoValor })
                });
                if (!res.ok) throw new Error('Falha ao salvar no banco');
                mostrarAlerta(novoValor ? 'Tópico destacado como Mais Cobrado 🔥' : 'Destaque de Mais Cobrado removido', 'sucesso');
            } catch (e) {
                console.error(e);
                topico.mais_cobrado = !novoValor;
                sincronizarTopicoEmEstado(topico.id, { mais_cobrado: !novoValor });
                mostrarAlerta('Erro ao salvar alteração no banco.', 'erro');
            }
        };

        const alterarPrioridadeTopico = async (topico, valor) => {
            const novaPrioridade = (valor === '' || valor === null || valor === undefined) ? null : parseInt(valor);
            const prioridadeAnterior = topico.prioridade;
            topico.prioridade = novaPrioridade;

            sincronizarTopicoEmEstado(topico.id, { prioridade: novaPrioridade });

            try {
                const res = await fetch(`/api/editais/topicos/${topico.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prioridade: novaPrioridade })
                });
                if (!res.ok) throw new Error('Falha ao salvar no banco');
                mostrarAlerta(novaPrioridade ? `Prioridade P${novaPrioridade} definida para o tópico!` : 'Prioridade removida.', 'sucesso');
            } catch (e) {
                console.error(e);
                topico.prioridade = prioridadeAnterior;
                sincronizarTopicoEmEstado(topico.id, { prioridade: prioridadeAnterior });
                mostrarAlerta('Erro ao persistir prioridade no banco.', 'erro');
            }
        };

        const toggleConcluidoTopico = async (topico) => {
            const novoValor = !topico.concluido;
            topico.concluido = novoValor;
            if (novoValor) topico.visto = true;

            sincronizarTopicoEmEstado(topico.id, { concluido: novoValor, visto: topico.visto });

            try {
                const res = await fetch(`/api/editais/topicos/${topico.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ concluido: novoValor })
                });
                if (!res.ok) throw new Error('Falha ao salvar');
                mostrarAlerta(novoValor ? 'Tópico marcado como concluído! ✅' : 'Tópico marcado como pendente.', 'sucesso');
            } catch (e) {
                console.error(e);
                topico.concluido = !novoValor;
                mostrarAlerta('Erro ao persistir status.', 'erro');
            }
        };

        const sincronizarTopicoEmEstado = (topicoId, updates) => {
            const atualizarEmLista = (lista) => {
                if (!lista) return;
                const item = lista.find(t => t.id === topicoId);
                if (item) Object.assign(item, updates);
            };

            if (todasDisciplinas.value) {
                todasDisciplinas.value.forEach(d => atualizarEmLista(d.topicos));
            }
            if (editais.value) {
                editais.value.forEach(ed => (ed.disciplinas || []).forEach(d => atualizarEmLista(d.topicos)));
            }
            if (editalVerticalizadoData.value) {
                (editalVerticalizadoData.value.BASICOS || []).forEach(d => atualizarEmLista(d.topicos));
                (editalVerticalizadoData.value.ESPECIFICOS || []).forEach(d => atualizarEmLista(d.topicos));
            }
        };

        const getProximoTopicoTrilha = (discId) => {
            if (!discId) return null;
            const numId = Number(discId);
            let topicos = [];
            if (editalVerticalizadoData.value) {
                const todosDiscs = [
                    ...(editalVerticalizadoData.value.BASICOS || []),
                    ...(editalVerticalizadoData.value.ESPECIFICOS || [])
                ];
                const d = todosDiscs.find(x => Number(x.id) === numId);
                if (d && d.topicos && d.topicos.length > 0) {
                    topicos = d.topicos;
                }
            }

            if (!topicos || topicos.length === 0) {
                const d = (todasDisciplinas.value || []).find(x => Number(x.id) === numId);
                if (d && d.topicos) topicos = d.topicos;
            }

            if ((!topicos || topicos.length === 0) && editais.value) {
                for (const ed of editais.value) {
                    if (ed.disciplinas) {
                        const d = ed.disciplinas.find(x => Number(x.id) === numId);
                        if (d && d.topicos) {
                            topicos = d.topicos;
                            break;
                        }
                    }
                }
            }

            if (!topicos || topicos.length === 0) return null;

            const pendentes = topicos.filter(t => !t.visto && !t.concluido);
            const pool = pendentes.length > 0 ? pendentes : topicos;

            const p1 = pool.find(t => t.prioridade === 1);
            if (p1) return p1;
            const p2 = pool.find(t => t.prioridade === 2);
            if (p2) return p2;
            const p3 = pool.find(t => t.prioridade === 3);
            if (p3) return p3;
            const mc = pool.find(t => t.mais_cobrado);
            if (mc) return mc;

            return pool[0] || null;
        };

        const proximoTopicoBlocoAtual = computed(() => {
            if (!blocoAtual.value || !blocoAtual.value.disciplina_id) return null;
            if (blocoAtual.value.disciplina && blocoAtual.value.disciplina.categoria === 'REVISAO_ANKI') return null;
            return getProximoTopicoTrilha(blocoAtual.value.disciplina_id);
        });

        const iniciarEstudoDoTopico = (disc, topico) => {
            let discId = null;
            if (typeof disc === 'number' || (typeof disc === 'string' && /^\d+$/.test(disc))) {
                discId = Number(disc);
            } else if (disc && disc.id) {
                discId = Number(disc.id);
            } else if (disc && disc.disciplina_id) {
                discId = Number(disc.disciplina_id);
            } else if (topico && topico.disciplina_id) {
                discId = Number(topico.disciplina_id);
            } else if (blocoAtual.value && blocoAtual.value.disciplina_id) {
                discId = Number(blocoAtual.value.disciplina_id);
            } else {
                discId = todasDisciplinas.value[0]?.id || '';
            }

            let topicoId = '';
            if (topico && topico.id) {
                topicoId = topico.id;
            } else if (typeof topico === 'number' || (typeof topico === 'string' && /^\d+$/.test(topico))) {
                topicoId = Number(topico);
            } else {
                const prox = getProximoTopicoTrilha(discId);
                topicoId = prox ? prox.id : '';
            }

            const blocoCorrespondente = (blocoAtual.value && Number(blocoAtual.value.disciplina_id) === Number(discId)) ? blocoAtual.value : null;

            formSessao.value = {
                id: null,
                disciplina_id: discId,
                bloco_ciclo_id: blocoCorrespondente ? blocoCorrespondente.id : null,
                topico_id: topicoId,
                tempo_estudado_minutos: timerSegundos.value >= 60 ? Math.round(timerSegundos.value / 60) : 60,
                qtd_questoes_total: 0,
                qtd_acertos: 0,
                qtd_erros: 0,
                is_revisao_anki: false,
                avancar_ciclo: !!blocoCorrespondente,
                data: getDataHojeLocal()
            };
            modalCheckinAberto.value = true;
        };

        const onDisciplinaSessaoChange = () => {
            const dId = formSessao.value.disciplina_id;
            if (!dId) {
                formSessao.value.topico_id = '';
                return;
            }
            const prox = getProximoTopicoTrilha(Number(dId));
            formSessao.value.topico_id = prox ? prox.id : '';
        };

        const getTopicoRowClass = (topico) => {
            if (topico.mais_cobrado && topico.prioridade === 1) {
                return 'bg-gradient-to-r from-amber-500/15 via-rose-500/10 to-transparent border-l-4 border-l-rose-500 dark:from-amber-500/25 dark:via-rose-500/20';
            }
            if (topico.mais_cobrado) {
                return 'bg-amber-500/10 dark:bg-amber-500/15 border-l-4 border-l-amber-500';
            }
            if (topico.prioridade === 1) {
                return 'bg-rose-500/10 dark:bg-rose-500/15 border-l-4 border-l-rose-500';
            }
            if (topico.prioridade === 2) {
                return 'bg-amber-500/5 dark:bg-amber-500/10 border-l-4 border-l-amber-400';
            }
            if (topico.prioridade === 3) {
                return 'bg-sky-500/5 dark:bg-sky-500/10 border-l-4 border-l-sky-400';
            }
            return 'border-l-4 border-l-transparent hover:bg-slate-50 dark:hover:bg-[#1B2638]/50';
        };

        const badgePrioridadeSelectClass = (p) => {
            if (p === 1) return 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/40';
            if (p === 2) return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/40';
            if (p === 3) return 'bg-sky-100 text-sky-800 border-sky-300 dark:bg-sky-500/20 dark:text-sky-300 dark:border-sky-500/40';
            return 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-[#1E293B] dark:text-[#94A3B8] dark:border-[#334155]';
        };

        // ==========================================
        // 5. CONTROLE DO TIMER
        // ==========================================
        const toggleTimer = () => {
            if (timerRodando.value) {
                if (timerInterval) {
                    clearInterval(timerInterval);
                    timerInterval = null;
                }
                timerRodando.value = false;
            } else {
                timerRodando.value = true;
                if (timerInterval) clearInterval(timerInterval);
                timerInterval = setInterval(() => {
                    timerSegundos.value++;
                }, 1000);
            }
        };

        const resetTimer = () => {
            if (timerInterval) {
                clearInterval(timerInterval);
                timerInterval = null;
            }
            timerRodando.value = false;
            timerSegundos.value = 0;
        };

        // ==========================================
        // 6. CÁLCULOS E ESTATÍSTICAS LOCAIS
        // ==========================================
        function getEstatisticasDisciplina(id) {
            if (!dashboardData.value) return { qtd: 0, perc: 0, perc_vistos: 0 };
            const stats = dashboardData.value.rendimento_disciplinas || [];
            const d = stats.find(x => x.disciplina_id === id);

            let perc_vistos = 0;
            let disciplina = null;
            for (const ed of editais.value) {
                const found = (ed.disciplinas || []).find(x => x.id === id);
                if (found) {
                    disciplina = found;
                    break;
                }
            }
            if (disciplina && disciplina.topicos && disciplina.topicos.length > 0) {
                const topicosId = disciplina.topicos.map(t => t.id);
                const sessoesDisc = sessoes.value.filter(s => s.disciplina_id === id && s.topico_id !== null);
                const topicosVistos = new Set(sessoesDisc.map(s => s.topico_id));
                perc_vistos = (topicosVistos.size / topicosId.length) * 100;
            }

            if (d && d.total_questoes > 0) {
                return { qtd: d.total_questoes, perc: d.percentual_acerto, perc_vistos };
            }
            return { qtd: 0, perc: 0, perc_vistos };
        }

        function getEstatisticasEdital(ed) {
            if (!ed) return { horas: '0h', topicos_vistos: 0, topicos_total: 0, perc_visto: 0 };
            let topicos_total = 0;
            const topicosVistos = new Set();

            const discIds = (ed.disciplinas || []).map(d => d.id);
            const sessoesEdital = (sessoes.value || []).filter(s => discIds.includes(s.disciplina_id));
            const horas = sessoesEdital.reduce((acc, s) => acc + (s.tempo_estudado_minutos || 0), 0) / 60;

            (ed.disciplinas || []).forEach(d => {
                if (d.categoria !== 'REVISAO_ANKI' && d.topicos) {
                    topicos_total += d.topicos.length;
                }
            });

            sessoesEdital.forEach(s => {
                if (s.topico_id !== null && s.topico_id !== undefined) topicosVistos.add(s.topico_id);
            });

            const perc_visto = topicos_total > 0 ? (topicosVistos.size / topicos_total) * 100 : 0;
            return {
                horas: formatarHorasDecimais(horas),
                topicos_vistos: topicosVistos.size,
                topicos_total,
                perc_visto
            };
        }

        function getTempoEstudadoCicloAtual() {
            if (!cicloAtivo.value) return '00:00:00';
            const sessoesCiclo = sessoes.value.filter(
                s => s.ciclo_id === cicloAtivo.value.id && s.volta_ciclo === cicloAtivo.value.voltas_completas
            );
            const totalMins = sessoesCiclo.reduce((acc, s) => acc + s.tempo_estudado_minutos, 0);
            return formatarTempoTimer(totalMins * 60);
        }

        function getTempoTotalCicloAtual() {
            if (!cicloAtivo.value) return '0h';
            const sessoesCiclo = sessoes.value.filter(s => s.ciclo_id === cicloAtivo.value.id);
            const totalMins = sessoesCiclo.reduce((acc, s) => acc + s.tempo_estudado_minutos, 0);
            return formatarHorasDecimais(totalMins / 60);
        }

        function getTotaisMatrizSemanal() {
            if (!matrizSemanalData.value || !matrizSemanalData.value.labels) return null;

            const numSemanas = matrizSemanalData.value.labels.length;
            const totaisSemanas = Array.from({ length: numSemanas }, () => ({ certas: 0, resolvidas: 0 }));
            let totalGeralCertas = 0;
            let totalGeralResolvidas = 0;

            const processarGrupo = (grupo) => {
                if (!grupo) return;
                grupo.forEach(disc => {
                    (disc.semanas || []).forEach((sem, idx) => {
                        if (totaisSemanas[idx]) {
                            totaisSemanas[idx].certas += sem.certas;
                            totaisSemanas[idx].resolvidas += sem.resolvidas;
                        }
                    });
                    totalGeralCertas += disc.total_certas;
                    totalGeralResolvidas += disc.total_resolvidas;
                });
            };

            if (matrizSemanalData.value.dados) {
                processarGrupo(matrizSemanalData.value.dados.BASICOS);
                processarGrupo(matrizSemanalData.value.dados.ESPECIFICOS);
            }

            const semanasProcessadas = totaisSemanas.map(t => {
                const perc = t.resolvidas > 0 ? ((t.certas / t.resolvidas) * 100).toFixed(1) : 0;
                return { ...t, percentual: perc };
            });

            const percGeral = totalGeralResolvidas > 0 ? ((totalGeralCertas / totalGeralResolvidas) * 100).toFixed(1) : 0;

            return {
                semanas: semanasProcessadas,
                totalGeral: {
                    certas: totalGeralCertas,
                    resolvidas: totalGeralResolvidas,
                    percentual: percGeral
                }
            };
        }

        function getRankingDisciplinas() {
            if (!dashboardData.value || !dashboardData.value.rendimento_disciplinas) {
                return { melhores: [], piores: [] };
            }

            const arr = [...dashboardData.value.rendimento_disciplinas].filter(a => a.total_questoes > 0);

            const piores = [...arr].sort((a, b) => {
                if (a.percentual_acerto !== b.percentual_acerto) return a.percentual_acerto - b.percentual_acerto;
                return b.total_questoes - a.total_questoes;
            }).slice(0, 3);

            const melhores = [...arr].sort((a, b) => {
                if (b.percentual_acerto !== a.percentual_acerto) return b.percentual_acerto - a.percentual_acerto;
                return b.total_questoes - a.total_questoes;
            }).slice(0, 3);

            return { piores, melhores };
        }

        // ==========================================
        // 7. CÁLCULOS DE RESULTADOS E RAIO-X
        // ==========================================
        const calcularPercentualTotal = (a) => {
            if (!a) return '-';
            const ac = (Number(a.acertos_basicos) || 0) + (Number(a.acertos_especificos) || 0);
            const er = (Number(a.erros_basicos) || 0) + (Number(a.erros_especificos) || 0);
            if (ac + er === 0) return '-';
            return ((ac / (ac + er)) * 100).toFixed(1) + '%';
        };

        const calcularPercentualRendimento = (av) => {
            if (!av) return '-';
            const totalPts = Number(av.total_pontos_prova);
            const nota = Number(av.nota_final);
            if (totalPts > 0) return formatarPercentualBR((nota / totalPts) * 100);
            return calcularPercentualTotal(av);
        };

        const calcularPercentualCorte = (av) => {
            if (!av) return '-';
            const totalPts = Number(av.total_pontos_prova);
            const corte = Number(av.nota_corte);
            if (totalPts > 0 && av.nota_corte !== null && av.nota_corte !== undefined && av.nota_corte !== '') {
                return formatarPercentualBR((corte / totalPts) * 100);
            }
            return '-';
        };

        const calcularRendimentoRaioX = (res) => {
            if (!res) return '-';
            const totalPts = Number(res.total_pontos_prova);
            const nota = Number(res.nota_final);
            if (totalPts > 0) return formatarPercentualBR((nota / totalPts) * 100);

            let totalQ = 0;
            if (res.disciplinas_resultado && res.disciplinas_resultado.length > 0) {
                totalQ = res.disciplinas_resultado.reduce((acc, d) => acc + (Number(d.acertos) || 0) + (Number(d.erros) || 0), 0);
            }
            if (totalQ > 0) return formatarPercentualBR((nota / totalQ) * 100);
            if (res.acerto_geral_perc > 0) return formatarPercentualBR(res.acerto_geral_perc);
            return '-';
        };

        const calcularCorteRaioX = (res) => {
            if (!res) return '-';
            const totalPts = Number(res.total_pontos_prova);
            const corte = Number(res.nota_corte);
            if (corte === null || corte === undefined || corte === 0) return '-';
            if (totalPts > 0) return formatarPercentualBR((corte / totalPts) * 100);

            let totalQ = 0;
            if (res.disciplinas_resultado && res.disciplinas_resultado.length > 0) {
                totalQ = res.disciplinas_resultado.reduce((acc, d) => acc + (Number(d.acertos) || 0) + (Number(d.erros) || 0), 0);
            }
            if (totalQ > 0) return formatarPercentualBR((corte / totalQ) * 100);
            return '-';
        };

        const calcularComparativoInfo = (av) => {
            if (!av) return { texto: '-', classes: 'bg-slate-100 dark:bg-[#243247] text-slate-600 dark:text-[#B8C4D6] border border-slate-200 dark:border-[#2D3D54]' };
            const totalPts = Number(av.total_pontos_prova);
            const nota = Number(av.nota_final) || 0;
            const temCorte = (av.nota_corte !== null && av.nota_corte !== undefined && av.nota_corte !== '');
            const corte = temCorte ? Number(av.nota_corte) : null;

            if (totalPts > 0 && corte !== null) {
                const diff = ((nota - corte) / totalPts) * 100;
                const diffFmt = (diff >= 0 ? '+' : '') + diff.toFixed(2).replace('.', ',') + '%';
                const isAprovado = diff >= 0;
                let icone = isAprovado ? '✓ ' : '✗ ';
                let statusTexto = isAprovado ? 'Aprovado' : 'Reprovado';
                let isEspera = false;
                if (av.resultado_final === 'Lista de Espera' || av.resultado_final === 'Cadastro Reserva') {
                    statusTexto = av.resultado_final;
                    icone = '⏳ ';
                    isEspera = true;
                }
                return {
                    texto: `${icone}${statusTexto} (${diffFmt})`,
                    classes: isAprovado
                        ? 'bg-emerald-50 dark:bg-[#34D399]/15 text-emerald-700 dark:text-[#34D399] border border-emerald-200 dark:border-[#34D399]/30'
                        : (isEspera
                            ? 'bg-amber-50 dark:bg-[#FBBF24]/15 text-amber-700 dark:text-[#FBBF24] border border-amber-200 dark:border-[#FBBF24]/30'
                            : 'bg-rose-50 dark:bg-[#F87171]/15 text-rose-700 dark:text-[#F87171] border border-rose-200 dark:border-[#F87171]/30')
                };
            } else if (corte !== null && corte > 0) {
                const diff = ((nota / corte) - 1) * 100;
                const diffFmt = (diff >= 0 ? '+' : '') + diff.toFixed(2).replace('.', ',') + '%';
                const isAprovado = diff >= 0;
                let icone = isAprovado ? '✓ ' : '✗ ';
                let statusTexto = isAprovado ? 'Aprovado' : 'Reprovado';
                let isEspera = false;
                if (av.resultado_final === 'Lista de Espera' || av.resultado_final === 'Cadastro Reserva') {
                    statusTexto = av.resultado_final;
                    icone = '⏳ ';
                    isEspera = true;
                }
                return {
                    texto: `${icone}${statusTexto} (${diffFmt})`,
                    classes: isAprovado
                        ? 'bg-emerald-50 dark:bg-[#34D399]/15 text-emerald-700 dark:text-[#34D399] border border-emerald-200 dark:border-[#34D399]/30'
                        : (isEspera
                            ? 'bg-amber-50 dark:bg-[#FBBF24]/15 text-amber-700 dark:text-[#FBBF24] border border-amber-200 dark:border-[#FBBF24]/30'
                            : 'bg-rose-50 dark:bg-[#F87171]/15 text-rose-700 dark:text-[#F87171] border border-rose-200 dark:border-[#F87171]/30')
                };
            }

            const isAprovado = av.resultado_final === 'Aprovado';
            const isEspera = av.resultado_final === 'Lista de Espera' || av.resultado_final === 'Cadastro Reserva';
            const icone = isAprovado ? '✓ ' : (isEspera ? '⏳ ' : (av.resultado_final ? '✗ ' : ''));
            return {
                texto: (icone ? icone : '') + (av.resultado_final || '-'),
                classes: isAprovado
                    ? 'bg-emerald-50 dark:bg-[#34D399]/15 text-emerald-700 dark:text-[#34D399] border border-emerald-200 dark:border-[#34D399]/30'
                    : (isEspera
                        ? 'bg-amber-50 dark:bg-[#FBBF24]/15 text-amber-700 dark:text-[#FBBF24] border border-amber-200 dark:border-[#FBBF24]/30'
                        : (av.resultado_final
                            ? 'bg-rose-50 dark:bg-[#F87171]/15 text-rose-700 dark:text-[#F87171] border border-rose-200 dark:border-[#F87171]/30'
                            : 'bg-slate-100 dark:bg-[#243247] text-slate-600 dark:text-[#B8C4D6] border border-slate-200 dark:border-[#2D3D54]'))
            };
        };

        const gerarInsightsRaioX = () => {
            insightsRaioX.value = [];
            const q = quadrantesRaioX.value;

            if (resultadoAtual.value?.total_dias_estudados > 0) {
                insightsRaioX.value.push(`<b>Constância da Preparação:</b> Você dedicou <b>${resultadoAtual.value.total_dias_estudados} dias</b> com estudo registrado para este concurso, totalizando <b>${(resultadoAtual.value.total_horas || 0).toFixed(1)} horas líquidas</b>.`);
            }

            if (q.eficienciaBaixa.length > 0) {
                const nomes = q.eficienciaBaixa.map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Alerta de Retorno:</b> Você investiu muito tempo em <b>${nomes}</b> mas o acerto ficou abaixo de 70%. É recomendado mudar o material base ou o método (ex: trocar vídeo por PDF e focar em questões comentadas).`);
            }
            if (q.eficienciaAlta.length > 0) {
                const nomes = q.eficienciaAlta.slice(0, 2).map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Alta Retenção:</b> <b>${nomes}</b> tiveram excelente desempenho com poucas horas. Provavelmente você tem base forte; mantenha apenas via revisões rápidas e baterias de questões.`);
            }
            if (q.lacuna.length > 0) {
                const nomes = q.lacuna.slice(0, 2).map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Prioridade Urgente:</b> <b>${nomes}</b> estão com baixo tempo e baixo rendimento. Devem receber peso maior no seu próximo ciclo de estudos.`);
            }
            if (insightsRaioX.value.length === 0) {
                insightsRaioX.value.push('Sua preparação está equilibrada entre os blocos. Continue mantendo a constância nos estudos e revisões no Anki.');
            }
        };

        // ==========================================
        // 8. INTEGRAÇÕES COM A API (FETCH)
        // ==========================================
        const ordenarPorDataDesc = (lista) => {
            if (!Array.isArray(lista)) return [];
            return [...lista].sort((a, b) => {
                const dataA = a.data_prova ? String(a.data_prova).trim() : '';
                const dataB = b.data_prova ? String(b.data_prova).trim() : '';
                if (!dataA && !dataB) return (b.id || 0) - (a.id || 0);
                if (!dataA) return 1;
                if (!dataB) return -1;
                if (dataB !== dataA) return dataB.localeCompare(dataA);
                return (b.id || 0) - (a.id || 0);
            });
        };

        const carregarEditais = async () => {
            try {
                const res = await fetch('/api/editais');
                if (res.ok) editais.value = await res.json();
            } catch (e) {
                console.error('Erro ao carregar editais:', e);
            }
        };

        async function carregarDashboardData(edital_id) {
            if (!edital_id) return;
            try {
                const [rDash, rMat, rCal, rVert] = await Promise.all([
                    fetch('/api/dashboard'),
                    fetch(`/api/dashboard/matriz-semanal?edital_id=${edital_id}`),
                    fetch(`/api/dashboard/calendario-estudos?edital_id=${edital_id}&dias=30`),
                    fetch(`/api/dashboard/edital-verticalizado?edital_id=${edital_id}`)
                ]);

                if (rDash.ok) dashboardData.value = await rDash.json();
                if (rMat.ok) matrizSemanalData.value = await rMat.json();
                if (rCal.ok) calendarioData.value = await rCal.json();
                if (rVert.ok) {
                    editalVerticalizadoData.value = await rVert.json();
                    if (!abaVerticalizado.value || typeof abaVerticalizado.value !== 'string') {
                        abaVerticalizado.value = 'basicos';
                    }
                }

                if (abaAtiva.value === 'dashboard') {
                    nextTick(() => setTimeout(renderCharts, 80));
                }
            } catch (e) {
                console.error('Erro ao carregar indicadores do dashboard:', e);
            }
        }

        const carregarResultadosAvulsos = async () => {
            try {
                const response = await fetch('/api/resultados_avulsos');
                if (response.ok) {
                    const dados = await response.json();
                    resultadosAvulsos.value = ordenarPorDataDesc(dados);
                }
            } catch (e) {
                console.error('Erro ao carregar resultados avulsos:', e);
            }
        };

        const carregarResultadosEncerrados = async () => {
            try {
                const res = await fetch('/api/resultados/encerrados');
                if (res.ok) {
                    resultadosEncerrados.value = await res.json();
                }
            } catch (e) {
                console.error('Erro ao carregar ciclos encerrados:', e);
            }
        };

        async function loadAllData() {
            carregandoDados.value = true;
            try {
                await carregarDadosProvaServidor();

                const rEd = await fetch('/api/editais');
                if (rEd.ok) {
                    editais.value = await rEd.json();
                    if (editais.value.length === 0) {
                        estadoAplicacao.value = 'wizard';
                        wizardPasso.value = 0;
                        return;
                    } else {
                        estadoAplicacao.value = 'app';
                    }
                }

                const [rCiclo, rSess] = await Promise.all([
                    fetch('/api/ciclos/ativo'),
                    fetch('/api/sessoes?limite=100')
                ]);

                if (rCiclo.ok) cicloAtivo.value = await rCiclo.json();
                if (rSess.ok) sessoes.value = await rSess.json();

                await Promise.all([
                    carregarResultadosAvulsos(),
                    carregarResultadosEncerrados()
                ]);

                const targetEditalId = cicloAtivo.value?.edital_id || (editais.value.length > 0 ? editais.value[0].id : null);
                if (targetEditalId) {
                    await carregarDashboardData(targetEditalId);
                }

                if (abaAtiva.value === 'ciclo') {
                    renderDonut();
                    scrollToCurrentBlock();
                }

                // Carrega status da IA e insights em segundo plano sem travar a inicialização do app
                verificarStatusChaveIA().catch(() => {});
                carregarInsightsIA().catch(() => {});
            } catch (e) {
                console.error('Erro ao inicializar dados:', e);
                mostrarAlerta('Não foi possível sincronizar todos os dados com o servidor.', 'erro');
            } finally {
                carregandoDados.value = false;
            }
        }

        // ==========================================
        // 9. AÇÕES DO WIZARD E EDITAIS
        // ==========================================
        const preencherExemploWizard = () => {
            wizardDados.value.nome = 'TSE Unificado - Analista Judiciário (TI)';
            wizardDados.value.texto_basicos = 'LÍNGUA PORTUGUESA: 1 Compreensão e interpretação de textos de gêneros variados. 2 Ortografia oficial. 3 Domínio dos mecanismos de coesão textual.\nDIREITO ADMINISTRATIVO: 1 Noções de organização administrativa. 2 Ato administrativo. 3 Agentes públicos. 4 Lei nº 14.133/2021.';
            wizardDados.value.texto_especificos = 'ENGENHARIA DE SOFTWARE: 1 Ciclo de vida do software. 2 Metodologias ágeis (Scrum, Kanban). 3 Arquitetura de microsserviços.\nBANCO DE DADOS: 1 Projeto de banco de dados relacional. 2 Linguagem SQL e PL/SQL. 3 SGBDs Oracle e PostgreSQL.\nSEGURANÇA DA INFORMAÇÃO: 1 OAuth 2.0, OpenID Connect e JWT. 2 OWASP Top 10.';
        };

        const processarEditalWizard = async () => {
            if (!wizardDados.value.texto_basicos && !wizardDados.value.texto_especificos) {
                mostrarAlerta('Informe ao menos os conhecimentos básicos ou específicos.', 'aviso');
                return;
            }
            processandoEdital.value = true;
            try {
                const res = await fetch('/api/editais/texto', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(wizardDados.value)
                });
                if (res.ok) {
                    const data = await res.json();
                    const rEd = await fetch(`/api/editais/${data.edital_id}`);
                    if (rEd.ok) {
                        wizardEditalGerado.value = await rEd.json();
                        wizardPasso.value = 3;
                    }
                } else {
                    const err = await res.json().catch(() => ({}));
                    mostrarAlerta(err.detail || 'Falha ao processar o texto do edital.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de conexão ao processar edital.', 'erro');
            } finally {
                processandoEdital.value = false;
            }
        };

        const salvarPesoDisciplina = async (disc) => {
            try {
                const res = await fetch(`/api/editais/disciplinas/${disc.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        peso_prova: disc.peso_prova,
                        relevancia_dificuldade: disc.relevancia_dificuldade,
                        categoria: disc.categoria,
                        incluir_no_ciclo: disc.incluir_no_ciclo,
                        qtd_questoes_prova: disc.qtd_questoes_prova
                    })
                });
                if (!res.ok) {
                    mostrarAlerta('Não foi possível salvar a alteração da disciplina.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de rede ao atualizar disciplina.', 'erro');
            }
        };

        const finalizarWizard = async () => {
            if (!wizardEditalGerado.value?.id) return;
            try {
                const res = await fetch('/api/ciclos/gerar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        edital_id: wizardEditalGerado.value.id,
                        carga_horaria_semanal: cicloForm.value.carga_horaria_semanal,
                        duracao_bloco_minutos: cicloForm.value.duracao_bloco_minutos
                    })
                });
                if (res.ok) {
                    await loadAllData();
                    estadoAplicacao.value = 'app';
                    abaAtiva.value = 'ciclo';
                    mostrarAlerta('Ciclo inteligente gerado com sucesso! Bons estudos.', 'sucesso');
                } else {
                    const err = await res.json().catch(() => ({}));
                    mostrarAlerta(err.detail || 'Falha ao gerar o ciclo.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de conexão ao finalizar configuração.', 'erro');
            }
        };

        async function gerarCicloNovoComEdital(edital_id) {
            if (!confirm('Deseja regerar o ciclo de estudos com os novos parâmetros? O ciclo atual será substituído.')) return;
            try {
                // Corrigido: antes usava `method: method` (ReferenceError)
                const res = await fetch('/api/ciclos/gerar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        edital_id,
                        carga_horaria_semanal: cicloAtivo.value?.carga_horaria_semanal || cicloForm.value.carga_horaria_semanal || 20,
                        duracao_bloco_minutos: cicloForm.value.duracao_bloco_minutos || 60
                    })
                });
                if (res.ok) {
                    mostrarAlerta('Novo ciclo recalculado e gerado com sucesso!', 'sucesso');
                    await loadAllData();
                    abaAtiva.value = 'ciclo';
                } else {
                    const err = await res.json().catch(() => ({}));
                    mostrarAlerta(err.detail || 'Erro ao regerar ciclo.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de rede ao regerar ciclo.', 'erro');
            }
        }

        async function excluirEdital(id) {
            if (!confirm('Tem certeza que deseja excluir este edital e TODOS os seus ciclos e sessões? Esta ação é irreversível.')) return;
            try {
                const res = await fetch(`/api/editais/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    mostrarAlerta('Edital removido com sucesso!', 'sucesso');
                    await loadAllData();
                } else {
                    mostrarAlerta('Erro ao excluir edital.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de rede ao excluir edital.', 'erro');
            }
        }

        const carregarEditalVerticalizado = async (id) => {
            await carregarDashboardData(id);
            abaAtiva.value = 'verticalizado';
            mostrarAlerta('Relatório verticalizado sincronizado!', 'sucesso');
        };

        // ==========================================
        // 10. AÇÕES DO CICLO E SESSÕES DE ESTUDO
        // ==========================================
        function triggerConfetti() {
            if (typeof confetti !== 'undefined') {
                confetti({
                    particleCount: 140,
                    spread: 75,
                    origin: { y: 0.6 },
                    colors: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6']
                });
            }
        }

        async function avancarBloco() {
            if (!cicloAtivo.value && !editandoCiclo.value) return;
            try {
                const oldVoltas = cicloAtivo.value.voltas_completas;
                const res = await fetch(`/api/ciclos/${cicloAtivo.value.id}/avancar`, { method: 'POST' });
                if (res.ok) {
                    await loadAllData();
                    if (cicloAtivo.value.voltas_completas > oldVoltas) {
                        triggerConfetti();
                        mostrarAlerta('Parabéns! Você completou mais um giro completo no ciclo!', 'sucesso');
                    } else {
                        mostrarAlerta('Bloco avançado na fila.', 'sucesso');
                    }
                    resetTimer();
                }
            } catch (e) {
                mostrarAlerta('Erro ao avançar bloco.', 'erro');
            }
        }

        async function selecionarBlocoManual(idx) {
            if (!cicloAtivo.value && !editandoCiclo.value) return;
            const currentIdx = cicloAtivo.value.bloco_atual_index;
            const blocoClicado = cicloAtivo.value.blocos[idx];

            if (idx > currentIdx) {
                mostrarAlerta('Você ainda não chegou nesta fase! Conclua ou pule a fase atual.', 'aviso');
                return;
            }
            if (idx === currentIdx) {
                abrirModalCheckinComBloco(blocoClicado);
                return;
            }

            const sessoesBloco = sessoes.value.filter(s => s.bloco_ciclo_id === blocoClicado.id);
            if (sessoesBloco.length > 0) {
                const ultimaSessao = sessoesBloco.reduce((a, b) => (new Date(a.data_criacao) > new Date(b.data_criacao) ? a : b));
                resumoSessaoAtual.value = {
                    sessao: ultimaSessao,
                    bloco: blocoClicado
                };
                modalResumoAberto.value = true;
            } else {
                mostrarAlerta('Nenhuma sessão registrada para este bloco na volta atual (bloco pulado).', 'aviso');
            }
        }

        function abrirModalCheckin() {
            const tempoCronometrado = timerSegundos.value >= 60 ? Math.round(timerSegundos.value / 60) : 60;
            const isRevisao = blocoAtual.value && blocoAtual.value.disciplina && blocoAtual.value.disciplina.categoria === 'REVISAO_ANKI';
            const dId = (!isRevisao && blocoAtual.value && blocoAtual.value.disciplina_id) ? blocoAtual.value.disciplina_id : (todasDisciplinas.value[0]?.id || '');
            const topicoSugerido = getProximoTopicoTrilha(dId);
            formSessao.value = {
                id: null,
                disciplina_id: dId,
                bloco_ciclo_id: blocoAtual.value ? blocoAtual.value.id : null,
                topico_id: topicoSugerido ? topicoSugerido.id : '',
                tempo_estudado_minutos: tempoCronometrado,
                qtd_questoes_total: 0,
                qtd_acertos: 0,
                qtd_erros: 0,
                is_revisao_anki: isRevisao,
                avancar_ciclo: true,
                data: getDataHojeLocal()
            };
            modalCheckinAberto.value = true;
        }

        function abrirModalCheckinComBloco(b) {
            const bloco = b || blocoAtual.value;
            const isRevisao = bloco && bloco.disciplina && bloco.disciplina.categoria === 'REVISAO_ANKI';
            const tempoSugerido = timerSegundos.value >= 60
                ? Math.round(timerSegundos.value / 60)
                : 60; // 60 min por padrão conforme solicitado
            const dId = (bloco && !isRevisao) ? bloco.disciplina_id : (todasDisciplinas.value[0]?.id || '');
            const topicoSugerido = getProximoTopicoTrilha(dId);

            formSessao.value = {
                id: null,
                is_revisao_anki: isRevisao,
                disciplina_id: dId,
                bloco_ciclo_id: bloco ? bloco.id : (blocoAtual.value ? blocoAtual.value.id : null),
                topico_id: topicoSugerido ? topicoSugerido.id : '',
                tempo_estudado_minutos: tempoSugerido,
                qtd_questoes_total: 0,
                qtd_acertos: 0,
                qtd_erros: 0,
                avancar_ciclo: true,
                data: getDataHojeLocal()
            };
            modalCheckinAberto.value = true;
        }

        async function salvarSessaoEstudo() {
            if (salvandoSessao.value) return;

            if (!formSessao.value.is_revisao_anki && topicosDaDisciplina.value.length > 0 && !formSessao.value.topico_id) {
                mostrarAlerta('Selecione o Tópico Estudado para contabilizar a cobertura do edital.', 'erro');
                return;
            }

            if (!formSessao.value.is_revisao_anki && formSessao.value.qtd_acertos === 0 && formSessao.value.qtd_erros === 0) {
                mostrarAlerta('Registre pelo menos 1 questão (acerto ou erro) na sessão.', 'erro');
                return;
            }

            if (!formSessao.value.data) {
                formSessao.value.data = getDataHojeLocal();
            }

            const hoje = getDataHojeLocal();
            if (formSessao.value.data > hoje) {
                mostrarAlerta('Não é permitido registrar sessões em datas futuras.', 'erro');
                return;
            }

            let total_q = formSessao.value.qtd_questoes_total;
            const a = Number(formSessao.value.qtd_acertos) || 0;
            const e = Number(formSessao.value.qtd_erros) || 0;
            if (total_q === 0 && (a > 0 || e > 0)) {
                formSessao.value.qtd_questoes_total = a + e;
            }

            const oldVoltas = cicloAtivo.value ? (cicloAtivo.value.voltas_completas || 0) : 0;
            let oldPerc = 0;
            try {
                if (cicloAtivo.value && editais.value) {
                    const ed = editais.value.find(item => item.id === cicloAtivo.value.edital_id);
                    if (ed) oldPerc = getEstatisticasEdital(ed).perc_visto;
                }
            } catch (err) {
                console.warn(err);
            }

            const method = formSessao.value.id ? 'PUT' : 'POST';
            const url = formSessao.value.id ? `/api/sessoes/${formSessao.value.id}` : '/api/sessoes';

            const payload = { ...formSessao.value };
            if (payload.topico_id === '' || payload.topico_id === null || payload.topico_id === undefined) {
                payload.topico_id = null;
            } else {
                payload.topico_id = parseInt(payload.topico_id, 10);
            }
            if (payload.bloco_ciclo_id === '' || payload.bloco_ciclo_id === undefined) {
                payload.bloco_ciclo_id = null;
            } else if (payload.bloco_ciclo_id !== null) {
                payload.bloco_ciclo_id = parseInt(payload.bloco_ciclo_id, 10);
            }
            if (!payload.id && !payload.bloco_ciclo_id && blocoAtual.value) {
                payload.bloco_ciclo_id = blocoAtual.value.id;
            }
            if (payload.avancar_ciclo === undefined) {
                payload.avancar_ciclo = true;
            }

            salvandoSessao.value = true;
            let res;
            try {
                res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (netErr) {
                console.error('Erro de rede no fetch:', netErr);
                mostrarAlerta('Erro de rede ao salvar sessão.', 'erro');
                salvandoSessao.value = false;
                return;
            }

            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                mostrarAlerta(errJson.detail || 'Erro ao salvar sessão.', 'erro');
                salvandoSessao.value = false;
                return;
            }

            modalCheckinAberto.value = false;
            resetTimer();

            try {
                await loadAllData();

                let newPerc = 0;
                if (cicloAtivo.value && editais.value) {
                    const ed = editais.value.find(item => item.id === cicloAtivo.value.edital_id);
                    if (ed) newPerc = getEstatisticasEdital(ed).perc_visto;
                }

                const oldDecile = Math.floor(oldPerc / 10);
                const newDecile = Math.floor(newPerc / 10);

                if (newDecile > oldDecile && newDecile > 0) {
                    triggerConfetti();
                    mostrarAlerta(`Parabéns! Você atingiu ${newDecile * 10}% de cobertura do edital!`, 'sucesso');
                } else if (cicloAtivo.value && cicloAtivo.value.voltas_completas > oldVoltas) {
                    triggerConfetti();
                    mostrarAlerta('Sessão registrada! Parabéns, você completou uma volta inteira do ciclo!', 'sucesso');
                } else {
                    mostrarAlerta('Sessão de estudo registrada com sucesso!', 'sucesso');
                }

                renderDonut();
                scrollToCurrentBlock();
            } catch (uiErr) {
                console.error('Erro pós-salvamento na interface:', uiErr);
                mostrarAlerta('Sessão registrada com sucesso!', 'sucesso');
            } finally {
                salvandoSessao.value = false;
            }
        }

        function editarSessao(s) {
            formSessao.value = {
                id: s.id,
                disciplina_id: s.disciplina_id,
                bloco_ciclo_id: s.bloco_ciclo_id,
                topico_id: s.topico_id || '',
                tempo_estudado_minutos: s.tempo_estudado_minutos,
                qtd_questoes_total: s.qtd_questoes_total,
                qtd_acertos: s.qtd_acertos,
                qtd_erros: s.qtd_erros,
                is_revisao_anki: s.is_revisao_anki,
                avancar_ciclo: false,
                data: s.data
            };
            modalCheckinAberto.value = true;
        }

        async function excluirSessao(id) {
            if (!confirm('Deseja realmente excluir este registro de sessão?')) return;
            try {
                const res = await fetch(`/api/sessoes/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    mostrarAlerta('Sessão excluída com sucesso!', 'sucesso');
                    await loadAllData();
                } else {
                    mostrarAlerta('Erro ao excluir sessão.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de conexão ao excluir sessão.', 'erro');
            }
        }

        async function excluirTodasSessoes() {
            if (!confirm('Tem certeza que deseja apagar TODAS as sessões de estudo? Esta ação não pode ser desfeita e as métricas serão zeradas.')) return;
            try {
                const r = await fetch('/api/sessoes/todas', { method: 'DELETE' });
                if (r.ok) {
                    sessoes.value = [];
                    mostrarAlerta('Todas as sessões foram excluídas!', 'sucesso');
                    await loadAllData();
                } else {
                    mostrarAlerta('Erro ao excluir sessões.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de conexão.', 'erro');
            }
        }

        // ==========================================
        // 11. AÇÕES DE RESULTADOS E PROVAS AVULSAS
        // ==========================================
        const abrirResultados = async () => {
            abaAtiva.value = 'resultados';
            abaRaizResultados.value = 'registrar';
            await Promise.all([
                carregarResultadosAvulsos(),
                carregarResultadosEncerrados()
            ]);
        };

        const carregarResultados = async () => { };
        const salvarResultado = async () => { };

        const abrirModalDetalhesAvulso = (av) => {
            avulsoSelecionado.value = av;
        };

        const fecharModalDetalhesAvulso = () => {
            avulsoSelecionado.value = null;
        };

        const mudarAbaHistorico = (aba) => {
            abaHistorico.value = aba;
            nextTick(() => {
                setTimeout(() => {
                    if (aba === 'avulsos') renderGraficosAvulsos();
                    if (aba === 'encerrados') renderizarGraficosResultados();
                }, 120);
            });
        };

        const editarResultadoAvulso = (av) => {
            if (!av) return;
            idEmEdicaoAvulso.value = av.id;
            formAvulso.value = {
                nome_prova: av.nome_prova || '',
                banca: av.banca || '',
                data_prova: av.data_prova || '',
                acertos_basicos: (av.acertos_basicos !== null && av.acertos_basicos !== undefined) ? av.acertos_basicos : '',
                erros_basicos: (av.erros_basicos !== null && av.erros_basicos !== undefined) ? av.erros_basicos : '',
                nota_basicos: (av.nota_basicos !== null && av.nota_basicos !== undefined) ? av.nota_basicos : '',
                acertos_especificos: (av.acertos_especificos !== null && av.acertos_especificos !== undefined) ? av.acertos_especificos : '',
                erros_especificos: (av.erros_especificos !== null && av.erros_especificos !== undefined) ? av.erros_especificos : '',
                nota_especificos: (av.nota_especificos !== null && av.nota_especificos !== undefined) ? av.nota_especificos : '',
                nota_discursiva: (av.nota_discursiva !== null && av.nota_discursiva !== undefined) ? av.nota_discursiva : '',
                nota_final: (av.nota_final !== null && av.nota_final !== undefined) ? av.nota_final : '',
                total_pontos_prova: (av.total_pontos_prova !== null && av.total_pontos_prova !== undefined) ? av.total_pontos_prova : '',
                nota_corte: (av.nota_corte !== null && av.nota_corte !== undefined) ? av.nota_corte : '',
                posicao: (av.posicao !== null && av.posicao !== undefined) ? av.posicao : '',
                resultado_final: av.resultado_final || 'Aprovado'
            };
            abaAtiva.value = 'resultados';
            abaRaizResultados.value = 'registrar';
            abaRegistrar.value = 'antiga';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        };

        const cancelarEdicaoAvulso = () => {
            idEmEdicaoAvulso.value = null;
            formAvulso.value = {
                nome_prova: '',
                banca: '',
                data_prova: '',
                total_pontos_prova: '',
                acertos_basicos: '',
                erros_basicos: '',
                nota_basicos: '',
                acertos_especificos: '',
                erros_especificos: '',
                nota_especificos: '',
                nota_discursiva: '',
                nota_final: '',
                nota_corte: '',
                posicao: '',
                resultado_final: 'Aprovado'
            };
        };

        const salvarResultadoAvulso = async () => {
            if (salvandoAvulso.value) return;
            salvandoAvulso.value = true;
            try {
                const toNumOrNull = (v) => (v === '' || v === null || v === undefined) ? null : Number(v);
                const toIntOrNull = (v) => (v === '' || v === null || v === undefined) ? null : parseInt(v, 10);

                const payload = {
                    nome_prova: formAvulso.value.nome_prova,
                    banca: formAvulso.value.banca || null,
                    data_prova: formAvulso.value.data_prova || null,
                    nota_final: Number(formAvulso.value.nota_final) || 0,
                    nota_corte: toNumOrNull(formAvulso.value.nota_corte),
                    total_pontos_prova: toNumOrNull(formAvulso.value.total_pontos_prova),
                    acertos_basicos: toIntOrNull(formAvulso.value.acertos_basicos),
                    erros_basicos: toIntOrNull(formAvulso.value.erros_basicos),
                    nota_basicos: toNumOrNull(formAvulso.value.nota_basicos),
                    acertos_especificos: toIntOrNull(formAvulso.value.acertos_especificos),
                    erros_especificos: toIntOrNull(formAvulso.value.erros_especificos),
                    nota_especificos: toNumOrNull(formAvulso.value.nota_especificos),
                    nota_discursiva: toNumOrNull(formAvulso.value.nota_discursiva),
                    posicao: toIntOrNull(formAvulso.value.posicao) || 0,
                    resultado_final: formAvulso.value.resultado_final || 'Aprovado'
                };

                const isEdicao = Boolean(idEmEdicaoAvulso.value);
                const url = isEdicao ? `/api/resultados_avulsos/${idEmEdicaoAvulso.value}` : '/api/resultados_avulsos';
                const method = isEdicao ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    mostrarAlerta(isEdicao ? 'Prova antiga atualizada com sucesso!' : 'Prova antiga cadastrada com sucesso!', 'sucesso');
                    cancelarEdicaoAvulso();
                    await carregarResultadosAvulsos();
                    abaRaizResultados.value = 'historico';
                    abaHistorico.value = 'avulsos';
                    setTimeout(renderGraficosAvulsos, 150);
                } else {
                    const errData = await response.json().catch(() => ({}));
                    mostrarAlerta(errData.detail || 'Erro ao salvar prova avulsa.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de rede ao salvar prova avulsa.', 'erro');
            } finally {
                salvandoAvulso.value = false;
            }
        };

        const deletarResultadoAvulso = async (id) => {
            if (!confirm('Tem certeza que deseja excluir este registro de prova?')) return;
            try {
                const response = await fetch('/api/resultados_avulsos/' + id, { method: 'DELETE' });
                if (response.ok) {
                    mostrarAlerta('Registro excluído com sucesso.', 'sucesso');
                    await carregarResultadosAvulsos();
                    setTimeout(renderGraficosAvulsos, 120);
                } else {
                    mostrarAlerta('Erro ao excluir prova avulsa.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro de conexão.', 'erro');
            }
        };

        const prepararFormEncerramento = () => {
            const editalId = cicloAtivo.value?.edital_id || (editais.value.length > 0 ? editais.value[0].id : null);
            if (!editalId) return;

            const edital = editais.value.find(e => e.id === editalId);
            if (!edital || !edital.disciplinas) return;

            const discValidas = edital.disciplinas.filter(d => d.categoria !== 'REVISAO_ANKI');

            disciplinasEncerramento.value = discValidas.map(d => ({
                disciplina_id: d.id,
                nome: d.nome,
                grupo: d.grupo_conhecimento || (d.categoria === 'ESPECIFICAS' ? 'ESPECIFICOS' : 'BASICOS'),
                acertos: 0,
                erros: 0
            }));

            if (cicloAtivo.value) {
                formResultado.value.nome_prova = cicloAtivo.value.nome;
            } else if (edital) {
                formResultado.value.nome_prova = edital.nome;
            }
            if (!formResultado.value.data_prova) {
                formResultado.value.data_prova = getDataHojeLocal();
            }
        };

        const encerrarPreparacaoAvulsa = async () => {
            if (!confirm('Tem certeza que deseja encerrar esta preparação e registrá-la como Resultado Oficial?')) return;

            formResultado.value.nota_final = formAvulso.value.nota_final || 0;
            formResultado.value.nota_corte = formAvulso.value.nota_corte || 0;
            formResultado.value.nota_minima_aprovados = 0;
            formResultado.value.nota_maxima_aprovados = 0;
            formResultado.value.posicao = formAvulso.value.posicao || 0;
            formResultado.value.total_vagas = 0;
            formResultado.value.resultado_final = formAvulso.value.resultado_final || 'Aprovado';

            try {
                const response = await fetch('/api/resultados/' + cicloAtivo.value.edital_id + '/encerrar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formResultado.value)
                });
                if (response.ok) {
                    resultadoAtual.value = await response.json();
                    mostrarAlerta('Preparação encerrada com sucesso!', 'sucesso');
                    setTimeout(() => { renderGraficosAvulsos(); }, 100);
                } else {
                    const errorData = await response.json().catch(() => ({}));
                    mostrarAlerta(errorData.detail || 'Erro ao encerrar preparação.', 'erro');
                }
            } catch (error) {
                console.error('Erro ao encerrar:', error);
                mostrarAlerta('Erro de conexão ao encerrar a preparação.', 'erro');
            }
        };

        const encerrarCicloOficial = async () => {
            if (salvandoEncerramento.value) return;

            const editalId = editandoCiclo.value
                ? (formResultado.value?.edital_id || resultadoAtual.value?.edital_id || cicloAtivo.value?.edital_id)
                : (cicloAtivo.value?.edital_id || (editais.value.length > 0 ? editais.value[0].id : null));

            if (!editalId) {
                mostrarAlerta('Nenhum edital selecionado ou ativo.', 'erro');
                return;
            }

            const totais = totaisEncerramento.value;

            const payload = {
                nota_final: Number(formResultado.value.nota_final) || 0,
                nota_corte: Number(formResultado.value.nota_corte) || 0,
                total_pontos_prova: formResultado.value.total_pontos_prova ? Number(formResultado.value.total_pontos_prova) : null,
                nota_minima_aprovados: Number(formResultado.value.nota_minima_aprovados) || 0,
                nota_maxima_aprovados: Number(formResultado.value.nota_maxima_aprovados) || 0,
                posicao: Number(formResultado.value.posicao) || 0,
                total_vagas: Number(formResultado.value.total_vagas) || 0,
                resultado_final: formResultado.value.resultado_final || 'Aprovado',
                acertos_basicos: totais.acertosBasicos,
                erros_basicos: totais.errosBasicos,
                nota_basicos: totais.acertosBasicos,
                acertos_especificos: totais.acertosEspec,
                erros_especificos: totais.errosEspec,
                nota_especificos: totais.acertosEspec,
                nota_discursiva: Number(formResultado.value.nota_discursiva) || 0,
                disciplinas: disciplinasEncerramento.value.map(d => ({
                    disciplina_id: d.disciplina_id,
                    acertos: Number(d.acertos) || 0,
                    erros: Number(d.erros) || 0
                }))
            };

            salvandoEncerramento.value = true;
            try {
                const url = editandoCiclo.value
                    ? `/api/resultados/${editalId}`
                    : `/api/resultados/${editalId}/encerrar`;
                const method = editandoCiclo.value ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    resultadoAtual.value = await response.json();
                    mostrarAlerta(editandoCiclo.value ? 'Ciclo atualizado com sucesso!' : 'Preparação encerrada e Raio-X gerado!', 'sucesso');
                    editandoCiclo.value = false;
                    abaRaizResultados.value = 'historico';
                    abaHistorico.value = 'encerrados';
                    await carregarResultadosEncerrados();
                    await visualizarDashboardEncerrado(editalId);
                } else {
                    const data = await response.json().catch(() => ({}));
                    mostrarAlerta(data.detail || 'Erro ao encerrar preparação.', 'erro');
                }
            } catch (error) {
                console.error(error);
                mostrarAlerta('Erro de conexão ao salvar encerramento.', 'erro');
            } finally {
                salvandoEncerramento.value = false;
            }
        };

        const visualizarDashboardEncerrado = async (edital_id) => {
            carregandoResultados.value = true;
            try {
                const response = await fetch('/api/resultados/' + edital_id);
                if (response.ok) {
                    resultadoAtual.value = await response.json();
                    abaRaizResultados.value = 'historico';
                    abaHistorico.value = 'encerrados';
                    nextTick(() => {
                        setTimeout(() => { renderizarGraficosResultados(); }, 150);
                    });
                } else {
                    mostrarAlerta('Erro ao carregar o Raio-X deste ciclo.', 'erro');
                }
            } catch (error) {
                console.error(error);
                mostrarAlerta('Erro de conexão ao carregar Raio-X.', 'erro');
            } finally {
                carregandoResultados.value = false;
            }
        };

        const editarCicloEncerrado = async (res) => {
            await visualizarDashboardEncerrado(res.edital_id);

            editandoCiclo.value = true;
            abaAtiva.value = 'resultados';
            abaRaizResultados.value = 'registrar';
            abaRegistrar.value = 'encerramento';

            const edital = editais.value.find(e => e.id === res.edital_id);
            if (edital && edital.disciplinas) {
                const discValidas = edital.disciplinas.filter(d => d.categoria !== 'REVISAO_ANKI');
                const salvas = (resultadoAtual.value?.disciplinas_resultado) || [];

                disciplinasEncerramento.value = discValidas.map(d => {
                    const encontrada = salvas.find(s => s.disciplina_id === d.id);
                    return {
                        disciplina_id: d.id,
                        nome: d.nome,
                        grupo: d.grupo_conhecimento || (d.categoria === 'ESPECIFICAS' ? 'ESPECIFICOS' : 'BASICOS'),
                        acertos: encontrada ? encontrada.acertos : 0,
                        erros: encontrada ? encontrada.erros : 0
                    };
                });
            }

            formResultado.value = {
                edital_id: res.edital_id,
                nome_prova: res.nome_edital || (edital ? edital.nome : ''),
                data_prova: res.data_encerramento ? res.data_encerramento.split('T')[0] : getDataHojeLocal(),
                nota_final: res.nota_final || '',
                total_pontos_prova: (res.total_pontos_prova !== null && res.total_pontos_prova !== undefined) ? res.total_pontos_prova : (resultadoAtual.value?.total_pontos_prova || ''),
                nota_corte: res.nota_corte || '',
                nota_minima_aprovados: res.nota_minima_aprovados || '',
                nota_maxima_aprovados: res.nota_maxima_aprovados || '',
                posicao: res.posicao || '',
                total_vagas: res.total_vagas || '',
                resultado_final: res.resultado_final || 'Aprovado'
            };

            window.scrollTo({ top: 0, behavior: 'smooth' });
        };

        const deletarCicloEncerrado = async (edital_id) => {
            if (!confirm('Tem certeza que deseja excluir o encerramento deste ciclo? Ele voltará a ficar ativo.')) return;
            try {
                const res = await fetch(`/api/resultados/${edital_id}`, { method: 'DELETE' });
                if (res.ok) {
                    mostrarAlerta('Encerramento removido. O ciclo voltou a ficar ativo.', 'sucesso');
                    await carregarEditais();
                    if (resultadoAtual.value && resultadoAtual.value.edital_id === edital_id) {
                        resultadoAtual.value = null;
                    }
                    await carregarResultadosEncerrados();
                }
            } catch (e) {
                console.error(e);
                mostrarAlerta('Erro ao remover encerramento.', 'erro');
            }
        };

        const exportarPDF = () => {
            const element = document.getElementById('pdf-content');
            if (!element || typeof html2pdf === 'undefined') {
                mostrarAlerta('Biblioteca de PDF indisponível no momento.', 'erro');
                return;
            }
            const nomeArquivo = cicloAtivo.value?.nome ? `raio_x_${cicloAtivo.value.nome}.pdf` : 'raio_x_resultado.pdf';
            const opt = {
                margin: 10,
                filename: nomeArquivo,
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2 },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            };
            html2pdf().set(opt).from(element).save();
        };

        // ==========================================
        // 12. RENDERIZAÇÃO DE GRÁFICOS (CHART.JS)
        // ==========================================
        function renderDonut() {
            nextTick(() => {
                const ctxD = document.getElementById('chartCicloDonut');
                if (!ctxD) return;

                if (chartCicloDonutInstance) {
                    chartCicloDonutInstance.destroy();
                    chartCicloDonutInstance = null;
                }

                if (!cicloAtivo.value || !cicloAtivo.value.blocos) return;

                const isDark = tema.value === 'dark';
                // Paleta de alta luminosidade para contraste ótimo em fundo escuro (WCAG AA)
                const palette = isDark
                    ? ['#60A5FA', '#34D399', '#FBBF24', '#F87171', '#C4B5FD', '#22D3EE', '#38BDF8', '#A78BFA']
                    : ['#2563EB', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316'];

                const discColors = {};
                let cIdx = 0;

                const labels = [];
                const data = [];
                const colors = [];
                const borderColors = [];

                const currentIndex = cicloAtivo.value.bloco_atual_index;

                cicloAtivo.value.blocos.forEach((b, idx) => {
                    const nome = b.disciplina ? b.disciplina.nome : (getNomeDisciplina(b.disciplina_id) || `Fase ${idx + 1}`);
                    if (!discColors[nome]) {
                        discColors[nome] = palette[cIdx % palette.length];
                        cIdx++;
                    }

                    labels.push(`Fase ${idx + 1}: ${nome}`);
                    data.push(b.duracao_minutos);

                    const baseColor = discColors[nome];
                    if (idx === currentIndex) {
                        colors.push(isDark ? '#22D3EE' : baseColor);
                    } else if (idx < currentIndex) {
                        colors.push(baseColor);
                    } else {
                        // Trilho escuro para blocos futuros do ciclo em fundo azul-ardósia
                        colors.push(isDark ? '#162335' : '#E2E8F0');
                    }
                    borderColors.push(isDark ? '#2b4162' : '#ffffff');
                });

                chartCicloDonutInstance = new Chart(ctxD, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: data,
                            backgroundColor: colors,
                            borderColor: borderColors,
                            borderWidth: data.map((_, i) => i === currentIndex ? 4 : 2),
                            hoverOffset: 6,
                            offset: data.map((_, i) => i === currentIndex ? 12 : 0)
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '72%',
                        layout: { padding: 42 },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        let label = context.label || '';
                                        if (label) label += ': ';
                                        label += context.parsed + ' min';
                                        return label;
                                    }
                                }
                            }
                        }
                    },
                    plugins: [{
                        id: 'activeSlicePointer',
                        afterDraw(chart) {
                            if (!cicloAtivo.value && !editandoCiclo.value) return;
                            const ctx = chart.ctx;
                            const activeIdx = cicloAtivo.value.bloco_atual_index;
                            const isDark = tema.value === 'dark';

                            const meta = chart.getDatasetMeta(0);
                            if (!meta || !meta.data[activeIdx]) return;

                            const arc = meta.data[activeIdx];
                            const centerAngle = (arc.startAngle + arc.endAngle) / 2;

                            const distance = 18;
                            const offset = arc.options.offset || 0;
                            const targetRadius = arc.outerRadius + offset + 6;
                            const targetX = arc.x + Math.cos(centerAngle) * targetRadius;
                            const targetY = arc.y + Math.sin(centerAngle) * targetRadius;

                            const startRadius = targetRadius + distance;
                            const startX = arc.x + Math.cos(centerAngle) * startRadius;
                            const startY = arc.y + Math.sin(centerAngle) * startRadius;

                            ctx.save();
                            ctx.shadowColor = isDark ? 'rgba(34, 211, 238, 0.45)' : 'rgba(37, 99, 235, 0.35)';
                            ctx.shadowBlur = 8;

                            ctx.beginPath();
                            ctx.moveTo(startX, startY);
                            ctx.lineTo(targetX, targetY);
                            ctx.strokeStyle = isDark ? '#22D3EE' : '#334155';
                            ctx.lineWidth = 2.5;
                            ctx.stroke();

                            ctx.beginPath();
                            ctx.arc(startX, startY, 3.5, 0, 2 * Math.PI);
                            ctx.fillStyle = isDark ? '#22D3EE' : '#ffffff';
                            ctx.fill();
                            ctx.lineWidth = 2;
                            ctx.stroke();

                            const angle = Math.atan2(targetY - startY, targetX - startX);
                            ctx.beginPath();
                            ctx.moveTo(targetX, targetY);
                            ctx.lineTo(targetX - 12 * Math.cos(angle - Math.PI / 7), targetY - 12 * Math.sin(angle - Math.PI / 7));
                            ctx.lineTo(targetX - 7 * Math.cos(angle), targetY - 7 * Math.sin(angle));
                            ctx.lineTo(targetX - 12 * Math.cos(angle + Math.PI / 7), targetY - 12 * Math.sin(angle + Math.PI / 7));
                            ctx.closePath();
                            ctx.fillStyle = isDark ? '#22D3EE' : '#334155';
                            ctx.fill();

                            ctx.restore();
                        }
                    }]
                });
            });
        }

        function renderCharts() {
            const ctxD = document.getElementById('chartDisciplinas');
            const ctxES = document.getElementById('chartEvolucaoSemanal');
            const ctxE = document.getElementById('chartEvolucao');
            if (!ctxD || !ctxES || !ctxE || !dashboardData.value) return;

            const discData = dashboardData.value.rendimento_disciplinas || [];
            if (chartDiscInstance) chartDiscInstance.destroy();
            chartDiscInstance = new Chart(ctxD, {
                type: 'bar',
                data: {
                    labels: discData.map(d => d.disciplina_nome.substring(0, 16)),
                    datasets: [{
                        label: '% Acerto',
                        data: discData.map(d => d.percentual_acerto),
                        backgroundColor: discData.map(d => d.percentual_acerto >= 80 ? '#10b981' : (d.percentual_acerto >= 60 ? '#f59e0b' : '#f43f5e')),
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, max: 100 } }
                }
            });

            const totaisSemanais = getTotaisMatrizSemanal();
            if (chartEvolucaoSemanalInstance) chartEvolucaoSemanalInstance.destroy();
            chartEvolucaoSemanalInstance = new Chart(ctxES, {
                type: 'line',
                data: {
                    labels: (matrizSemanalData.value && matrizSemanalData.value.labels) ? matrizSemanalData.value.labels : [],
                    datasets: [{
                        label: '% Acertos na Semana',
                        data: (totaisSemanais && totaisSemanais.semanas) ? totaisSemanais.semanas.map(s => parseFloat(s.percentual)) : [],
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.12)',
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointBackgroundColor: '#6366f1',
                        pointRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { min: 0, max: 100 } }
                }
            });

            const hist = dashboardData.value.rendimento_historico_diario || [];
            if (chartEvolucaoInstance) chartEvolucaoInstance.destroy();
            chartEvolucaoInstance = new Chart(ctxE, {
                type: 'line',
                data: {
                    labels: hist.map(h => formatarData(h.data)),
                    datasets: [{
                        label: '% Acertos no Dia',
                        data: hist.map(h => h.percentual_acerto),
                        borderColor: '#2563eb',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2.5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, max: 100 } }
                }
            });
        }

        function renderCalendarioAnalytics() {
            nextTick(() => {
                if (!calendarioData.value || !calendarioData.value.analytics) return;
                const analytics = calendarioData.value.analytics;
                const isDark = document.documentElement.classList.contains('dark') || (typeof tema !== 'undefined' && tema.value === 'dark');

                const ctxAd = document.getElementById('chartAderencia');
                if (ctxAd) {
                    if (chartAderenciaInstance) chartAderenciaInstance.destroy();
                    chartAderenciaInstance = new Chart(ctxAd, {
                        type: 'doughnut',
                        data: {
                            labels: ['Estudados', 'Não Estudados'],
                            datasets: [{
                                data: [analytics.taxa_aderencia, Math.max(0, 100 - analytics.taxa_aderencia)],
                                backgroundColor: ['#38BDF8', isDark ? '#1E293B' : '#e2e8f0'],
                                borderWidth: 0
                            }]
                        },
                        options: {
                            cutout: '76%',
                            plugins: { legend: { display: false }, tooltip: { enabled: false } }
                        },
                        plugins: [{
                            id: 'textCenter',
                            beforeDraw: function (chart) {
                                const width = chart.width, height = chart.height, ctx = chart.ctx;
                                ctx.restore();
                                const fontSize = (height / 85).toFixed(2);
                                ctx.font = '800 ' + fontSize + 'em "Plus Jakarta Sans", sans-serif';
                                ctx.textBaseline = 'middle';
                                ctx.fillStyle = isDark ? '#F1F5F9' : '#0f172a';
                                const text = analytics.taxa_aderencia + '%';
                                const textX = Math.round((width - ctx.measureText(text).width) / 2);
                                const textY = height / 2;
                                ctx.fillText(text, textX, textY);
                                ctx.save();
                            }
                        }]
                    });
                }

                const ctxDS = document.getElementById('chartDiaSemana');
                if (ctxDS) {
                    if (chartDiaSemanaInstance) chartDiaSemanaInstance.destroy();
                    const dsMap = analytics.media_horas_dsemana || {};
                    const dsValues = [
                        Number(dsMap[0] !== undefined ? dsMap[0] : (dsMap['0'] || 0)),
                        Number(dsMap[1] !== undefined ? dsMap[1] : (dsMap['1'] || 0)),
                        Number(dsMap[2] !== undefined ? dsMap[2] : (dsMap['2'] || 0)),
                        Number(dsMap[3] !== undefined ? dsMap[3] : (dsMap['3'] || 0)),
                        Number(dsMap[4] !== undefined ? dsMap[4] : (dsMap['4'] || 0)),
                        Number(dsMap[5] !== undefined ? dsMap[5] : (dsMap['5'] || 0)),
                        Number(dsMap[6] !== undefined ? dsMap[6] : (dsMap['6'] || 0))
                    ];
                    chartDiaSemanaInstance = new Chart(ctxDS, {
                        type: 'bar',
                        data: {
                            labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                            datasets: [{
                                label: 'Média de Horas',
                                data: dsValues,
                                backgroundColor: dsValues.map(v => v < 2 ? '#f43f5e' : (isDark ? '#60A5FA' : '#2563EB')),
                                borderRadius: 5
                            }]
                        },
                        options: {
                            maintainAspectRatio: false,
                            indexAxis: 'y',
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: isDark ? '#111827' : '#ffffff',
                                    titleColor: isDark ? '#F3F4F6' : '#0f172a',
                                    bodyColor: isDark ? '#B8C4D6' : '#334155',
                                    borderColor: isDark ? '#2D3D54' : '#cbd5e1',
                                    borderWidth: 1
                                }
                            },
                            scales: {
                                x: {
                                    beginAtZero: true,
                                    ticks: { color: isDark ? '#cbd5e1' : '#64748b' },
                                    grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }
                                },
                                y: {
                                    ticks: { color: isDark ? '#cbd5e1' : '#334155', font: { weight: 'bold' } },
                                    grid: { display: false }
                                }
                            }
                        }
                    });
                }

                const ctxI = document.getElementById('chartIntensidade');
                if (ctxI) {
                    if (chartIntensidadeInstance) chartIntensidadeInstance.destroy();
                    const bins = { '0-1h': 0, '1-2h': 0, '2-3h': 0, '3-4h': 0, '4-5h': 0, '5h+': 0 };
                    (analytics.distribuicao_horas || []).forEach(h => {
                        if (h <= 1) bins['0-1h']++;
                        else if (h <= 2) bins['1-2h']++;
                        else if (h <= 3) bins['2-3h']++;
                        else if (h <= 4) bins['3-4h']++;
                        else if (h <= 5) bins['4-5h']++;
                        else bins['5h+']++;
                    });
                    chartIntensidadeInstance = new Chart(ctxI, {
                        type: 'bar',
                        data: {
                            labels: Object.keys(bins),
                            datasets: [{
                                label: 'Dias',
                                data: Object.values(bins),
                                backgroundColor: isDark ? '#818CF8' : '#6366f1',
                                borderRadius: 6,
                                categoryPercentage: 0.85,
                                barPercentage: 0.9
                            }]
                        },
                        options: {
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: isDark ? '#111827' : '#ffffff',
                                    titleColor: isDark ? '#F3F4F6' : '#0f172a',
                                    bodyColor: isDark ? '#B8C4D6' : '#334155',
                                    borderColor: isDark ? '#2D3D54' : '#cbd5e1',
                                    borderWidth: 1
                                }
                            },
                            scales: {
                                x: {
                                    ticks: { color: isDark ? '#cbd5e1' : '#64748b' },
                                    grid: { display: false }
                                },
                                y: {
                                    beginAtZero: true,
                                    ticks: { color: isDark ? '#cbd5e1' : '#64748b' },
                                    grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }
                                }
                            }
                        }
                    });
                }

                const ctxER = document.getElementById('chartEvolucaoRisco');
                if (ctxER) {
                    if (chartEvolucaoRiscoInstance) chartEvolucaoRiscoInstance.destroy();
                    const evolucao = analytics.evolucao_diaria || [];
                    const ma7 = [];
                    const ma30 = [];
                    for (let i = 0; i < evolucao.length; i++) {
                        let sum7 = 0, c7 = 0;
                        for (let j = Math.max(0, i - 6); j <= i; j++) { sum7 += evolucao[j].horas; c7++; }
                        ma7.push(Number((sum7 / c7).toFixed(2)));

                        let sum30 = 0, c30 = 0;
                        for (let j = Math.max(0, i - 29); j <= i; j++) { sum30 += evolucao[j].horas; c30++; }
                        ma30.push(Number((sum30 / c30).toFixed(2)));
                    }
                    chartEvolucaoRiscoInstance = new Chart(ctxER, {
                        type: 'line',
                        data: {
                            labels: evolucao.map(e => e.data.substring(5, 10).replace('-', '/')),
                            datasets: [
                                { type: 'bar', label: 'Horas no Dia', data: evolucao.map(e => e.horas), backgroundColor: isDark ? '#334155' : '#cbd5e1', borderRadius: 4, order: 3 },
                                { type: 'line', label: 'Média Móvel 7d', data: ma7, borderColor: isDark ? '#60A5FA' : '#2563eb', borderWidth: 2.5, tension: 0.3, pointRadius: 0, order: 2 },
                                { type: 'line', label: 'Média Móvel 30d', data: ma30, borderColor: isDark ? '#FBBF24' : '#f59e0b', borderWidth: 2, borderDash: [5, 5], tension: 0.3, pointRadius: 0, order: 1 }
                            ]
                        },
                        options: {
                            maintainAspectRatio: false,
                            scales: {
                                x: {
                                    ticks: { color: isDark ? '#cbd5e1' : '#64748b' },
                                    grid: { display: false }
                                },
                                y: {
                                    beginAtZero: true,
                                    suggestedMax: 7,
                                    ticks: { color: isDark ? '#cbd5e1' : '#64748b' },
                                    grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }
                                }
                            },
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    labels: {
                                        color: isDark ? '#F1F5F9' : '#1E293B',
                                        font: { weight: '600', size: 11 }
                                    }
                                },
                                tooltip: {
                                    backgroundColor: isDark ? '#111827' : '#ffffff',
                                    titleColor: isDark ? '#F3F4F6' : '#0f172a',
                                    bodyColor: isDark ? '#B8C4D6' : '#334155',
                                    borderColor: isDark ? '#2D3D54' : '#cbd5e1',
                                    borderWidth: 1
                                }
                            }
                        },
                        plugins: [{
                            id: 'burnoutZone',
                            beforeDraw: function (chart) {
                                const yAxis = chart.scales.y;
                                const ctx = chart.ctx;
                                if (yAxis.max > 6) {
                                    const yTop = yAxis.getPixelForValue(yAxis.max);
                                    const yBottom = yAxis.getPixelForValue(6);
                                    ctx.save();
                                    ctx.fillStyle = isDark ? 'rgba(244, 63, 94, 0.15)' : 'rgba(244, 63, 94, 0.08)';
                                    ctx.fillRect(chart.chartArea.left, yTop, chart.chartArea.right - chart.chartArea.left, yBottom - yTop);
                                    ctx.fillStyle = isDark ? '#F87171' : 'rgba(225, 29, 72, 0.75)';
                                    ctx.font = 'bold 10px "Plus Jakarta Sans", sans-serif';
                                    ctx.fillText('ZONA DE FADIGA / BURNOUT (>6h)', chart.chartArea.left + 10, yBottom - 6);
                                    ctx.restore();
                                }
                            }
                        }]
                    });
                }
            });
        }

        const renderGraficosAvulsos = () => {
            setTimeout(() => {
                if (chartEvolucaoAvulsosInstance) {
                    chartEvolucaoAvulsosInstance.destroy();
                    chartEvolucaoAvulsosInstance = null;
                }
                if (chartDesempenhoAvulsosInstance) {
                    chartDesempenhoAvulsosInstance.destroy();
                    chartDesempenhoAvulsosInstance = null;
                }

                const canvasEv = document.getElementById('chartEvolucaoAvulsos');
                const canvasDes = document.getElementById('chartDesempenhoAvulsos');
                if (!canvasEv || !canvasDes) return;

                const isDark = tema.value === 'dark';
                const dadosOrdenados = [...resultadosAvulsos.value].sort((a, b) => {
                    const dataA = a.data_prova ? String(a.data_prova).trim() : '';
                    const dataB = b.data_prova ? String(b.data_prova).trim() : '';
                    if (!dataA && !dataB) return (a.id || 0) - (b.id || 0);
                    if (!dataA) return -1;
                    if (!dataB) return 1;
                    if (dataA !== dataB) return dataA.localeCompare(dataB);
                    return (a.id || 0) - (b.id || 0);
                });
                const labels = dadosOrdenados.map(a => a.nome_prova);

                const ctxEv = canvasEv.getContext('2d');
                chartEvolucaoAvulsosInstance = new Chart(ctxEv, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Distância do Corte (%)',
                                data: dadosOrdenados.map(a => {
                                    if (a.nota_corte === null || a.nota_corte === undefined || a.nota_final === null || a.nota_final === undefined) return null;
                                    const nota = Number(a.nota_final);
                                    const corte = Number(a.nota_corte);
                                    const totalPts = Number(a.total_pontos_prova);
                                    if (totalPts > 0) return Number((((nota - corte) / totalPts) * 100).toFixed(2));
                                    if (corte > 0) return Number((((nota / corte) - 1) * 100).toFixed(2));
                                    return null;
                                }),
                                borderColor: isDark ? '#60A5FA' : '#2563EB',
                                backgroundColor: isDark ? 'rgba(96, 165, 250, 0.15)' : 'rgba(37, 99, 235, 0.12)',
                                fill: true,
                                tension: 0.3,
                                pointRadius: 5,
                                pointHoverRadius: 8,
                                pointBackgroundColor: isDark ? '#60A5FA' : '#2563EB',
                                pointBorderColor: isDark ? '#111827' : '#ffffff',
                                pointBorderWidth: 2
                            },
                            {
                                label: 'Linha de Corte (0%)',
                                data: dadosOrdenados.map(() => 0),
                                borderColor: isDark ? '#F87171' : '#EF4444',
                                borderDash: [6, 4],
                                borderWidth: 2,
                                fill: false,
                                tension: 0,
                                pointRadius: 0,
                                pointHoverRadius: 0
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                ticks: {
                                    color: isDark ? '#B8C4D6' : '#64748B',
                                    font: { size: 12 },
                                    maxRotation: 0,
                                    autoSkip: true
                                },
                                grid: {
                                    color: isDark ? 'rgba(45, 61, 84, 0.4)' : 'rgba(226, 232, 240, 0.8)'
                                }
                            },
                            y: {
                                ticks: {
                                    color: isDark ? '#B8C4D6' : '#64748B',
                                    font: { size: 12 },
                                    callback: function (val) {
                                        return (val >= 0 ? '+' : '') + val + '%';
                                    }
                                },
                                grid: {
                                    color: isDark ? 'rgba(45, 61, 84, 0.4)' : 'rgba(226, 232, 240, 0.8)'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    color: isDark ? '#F3F4F6' : '#1E293B',
                                    font: { size: 12, weight: '600' }
                                }
                            },
                            tooltip: {
                                backgroundColor: isDark ? '#111827' : '#ffffff',
                                titleColor: isDark ? '#F3F4F6' : '#0f172a',
                                bodyColor: isDark ? '#B8C4D6' : '#334155',
                                borderColor: isDark ? '#2D3D54' : '#e2e8f0',
                                borderWidth: 1,
                                padding: 10,
                                callbacks: {
                                    label: function (context) {
                                        let label = context.dataset.label || '';
                                        if (label) label += ': ';
                                        if (context.parsed.y !== null) {
                                            const yVal = Number(context.parsed.y);
                                            label += (yVal >= 0 ? '+' : '') + yVal.toFixed(2).replace('.', ',') + '%';
                                        }
                                        return label;
                                    }
                                }
                            }
                        }
                    }
                });

                const ctxDes = canvasDes.getContext('2d');
                chartDesempenhoAvulsosInstance = new Chart(ctxDes, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Básicos (% Acerto)',
                                data: dadosOrdenados.map(a => {
                                    const ac = Number(a.acertos_basicos) || 0;
                                    const er = Number(a.erros_basicos) || 0;
                                    return (ac + er > 0) ? Number(((ac / (ac + er)) * 100).toFixed(1)) : 0;
                                }),
                                backgroundColor: isDark ? '#60A5FA' : '#2563EB',
                                borderRadius: 6
                            },
                            {
                                label: 'Específicos (% Acerto)',
                                data: dadosOrdenados.map(a => {
                                    const ac = Number(a.acertos_especificos) || 0;
                                    const er = Number(a.erros_especificos) || 0;
                                    return (ac + er > 0) ? Number(((ac / (ac + er)) * 100).toFixed(1)) : 0;
                                }),
                                backgroundColor: isDark ? '#C4B5FD' : '#8B5CF6',
                                borderRadius: 6
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                ticks: {
                                    color: isDark ? '#B8C4D6' : '#64748B',
                                    font: { size: 12 },
                                    maxRotation: 0,
                                    autoSkip: true
                                },
                                grid: { display: false }
                            },
                            y: {
                                min: 0,
                                max: 100,
                                ticks: {
                                    color: isDark ? '#B8C4D6' : '#64748B',
                                    font: { size: 12 },
                                    callback: function (value) { return value + '%'; }
                                },
                                grid: {
                                    color: isDark ? 'rgba(45, 61, 84, 0.4)' : 'rgba(226, 232, 240, 0.8)'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    color: isDark ? '#F3F4F6' : '#1E293B',
                                    font: { size: 12, weight: '600' }
                                }
                            },
                            tooltip: {
                                backgroundColor: isDark ? '#111827' : '#ffffff',
                                titleColor: isDark ? '#F3F4F6' : '#0f172a',
                                bodyColor: isDark ? '#B8C4D6' : '#334155',
                                borderColor: isDark ? '#2D3D54' : '#e2e8f0',
                                borderWidth: 1,
                                padding: 10,
                                callbacks: {
                                    label: function (context) {
                                        let label = context.dataset.label || '';
                                        if (label) label += ': ';
                                        if (context.parsed.y !== null) label += context.parsed.y + '%';
                                        return label;
                                    }
                                }
                            }
                        }
                    }
                });
            }, 100);
        };

        const renderizarGraficosResultados = () => {
            if (!resultadoAtual.value) return;

            gerarInsightsRaioX();

            const ctxScatter = document.getElementById('scatterRaioX');
            const ctxRadar = document.getElementById('radarChartNotas');
            if (!ctxScatter && !ctxRadar) {
                setTimeout(renderizarGraficosResultados, 100);
                return;
            }

            if (ctxRadar) {
                if (window.radarChartInstance) window.radarChartInstance.destroy();
                window.radarChartInstance = new Chart(ctxRadar, {
                    type: 'radar',
                    data: {
                        labels: ['Sua Nota', 'Nota Corte', 'Mín. Aprovado', 'Máx. Aprovado'],
                        datasets: [{
                            label: 'Pontuação',
                            data: [
                                Number(resultadoAtual.value.nota_final) || 0,
                                Number(resultadoAtual.value.nota_corte) || 0,
                                Number(resultadoAtual.value.nota_minima_aprovados) || 0,
                                Number(resultadoAtual.value.nota_maxima_aprovados) || 0
                            ],
                            backgroundColor: 'rgba(99, 102, 241, 0.2)',
                            borderColor: 'rgba(99, 102, 241, 1)',
                            pointBackgroundColor: 'rgba(99, 102, 241, 1)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: { r: { beginAtZero: true } }
                    }
                });
            }

            const ctxBar = document.getElementById('barChartDisciplinas');
            if (ctxBar && resultadoAtual.value.desempenho_disciplinas) {
                if (window.barChartInstance) window.barChartInstance.destroy();

                const labels = resultadoAtual.value.desempenho_disciplinas.map(d => d.nome);
                const dataAcerto = resultadoAtual.value.desempenho_disciplinas.map(d => d.percentual_acerto);
                const dataVisto = resultadoAtual.value.desempenho_disciplinas.map(d => d.percentual_visto);

                window.barChartInstance = new Chart(ctxBar, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            { label: '% Acerto', data: dataAcerto, backgroundColor: 'rgba(16, 185, 129, 0.8)', borderRadius: 4 },
                            { label: '% Edital Visto', data: dataVisto, backgroundColor: 'rgba(99, 102, 241, 0.8)', borderRadius: 4 }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        indexAxis: 'y',
                        scales: { x: { max: 100 } }
                    }
                });
            }

            if (ctxScatter && resultadoAtual.value.desempenho_disciplinas) {
                if (window.scatterRaioXInstance) {
                    window.scatterRaioXInstance.destroy();
                    window.scatterRaioXInstance = null;
                }

                const quad = quadrantesRaioX.value;
                const getPontoCor = (d) => {
                    if (quad.dominado.some(x => x.disciplina_id === d.disciplina_id)) return '#34D399';
                    if (quad.eficienciaAlta.some(x => x.disciplina_id === d.disciplina_id)) return '#22D3EE';
                    if (quad.eficienciaBaixa.some(x => x.disciplina_id === d.disciplina_id)) return '#FBBF24';
                    return '#F87171';
                };

                const dadosScatter = resultadoAtual.value.desempenho_disciplinas.map(d => {
                    const acerto = (d.acertos_prova_perc !== undefined && d.acertos_prova_perc !== null && d.acertos_prova_perc > 0)
                        ? d.acertos_prova_perc
                        : (d.percentual_acerto || 0);
                    return {
                        x: Number((d.horas_dedicadas || 0).toFixed(1)),
                        y: Number((acerto || 0).toFixed(1)),
                        nome: d.nome,
                        revisoes: d.revisoes || 0,
                        cor: getPontoCor(d)
                    };
                });

                window.scatterRaioXInstance = new Chart(ctxScatter, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: 'Disciplinas',
                            data: dadosScatter,
                            backgroundColor: dadosScatter.map(d => d.cor),
                            borderColor: dadosScatter.map(d => d.cor),
                            pointRadius: 8,
                            pointHoverRadius: 11
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        const p = context.raw;
                                        return `${p.nome}: ${p.x}h estudadas | ${p.y}% acerto`;
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                title: { display: true, text: 'Tempo Dedicado (horas)', color: '#64748b', font: { weight: 'bold', size: 11 } },
                                beginAtZero: true
                            },
                            y: {
                                title: { display: true, text: 'Rendimento (%)', color: '#64748b', font: { weight: 'bold', size: 11 } },
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            }
        };

        // ==========================================
        // 13. NAVEGAÇÃO DE TELAS E SCROLL AUTOMÁTICO
        // ==========================================
        function voltarAoWizard() {
            estadoAplicacao.value = 'wizard';
            wizardPasso.value = 0;
        }

        function iniciarApp() {
            estadoAplicacao.value = 'app';
            if (abaAtiva.value === 'ciclo') {
                nextTick(() => {
                    renderDonut();
                    scrollToCurrentBlock();
                });
            }
        }

        const abrirDashboard = () => {
            abaAtiva.value = 'dashboard';
            setTimeout(renderCharts, 100);
        };

        function scrollToHojeHeatmap() {
            nextTick(() => {
                const container = document.getElementById('heatmap-container');
                const labelHoje = document.getElementById('heatmap-hoje-label');
                if (container && labelHoje) {
                    const scrollPos = labelHoje.offsetLeft - container.offsetLeft - (container.clientWidth / 2) + (labelHoje.clientWidth / 2);
                    container.scrollTo({ left: scrollPos, behavior: 'smooth' });
                }
            });
        }

        function scrollToCurrentBlock() {
            nextTick(() => {
                if (!cicloAtivo.value && !editandoCiclo.value) return;
                const idx = cicloAtivo.value.bloco_atual_index;
                const container = document.getElementById('esteira-container');
                const card = document.getElementById('bloco-' + idx);
                if (container && card) {
                    const scrollPos = card.offsetLeft - container.offsetLeft - (container.clientWidth / 2) + (card.clientWidth / 2);
                    container.scrollTo({ left: scrollPos, behavior: 'smooth' });
                }
            });
        }

        // ==========================================
        // 14. WATCHERS E LIFECYCLE
        // ==========================================
        watch(abaRaizResultados, (newVal) => {
            if (newVal === 'historico') {
                setTimeout(() => {
                    if (abaHistorico.value === 'avulsos') renderGraficosAvulsos();
                    if (abaHistorico.value === 'encerrados') renderizarGraficosResultados();
                }, 100);
            }
        });

        watch(abaHistorico, (newVal) => {
            if (newVal === 'avulsos') {
                renderGraficosAvulsos();
            }
        });

        watch(abaAtiva, (newVal) => {
            if (newVal === 'resultados' && abaRaizResultados.value === 'historico' && abaHistorico.value === 'avulsos') {
                renderGraficosAvulsos();
            }
            if (newVal === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
            } else if (newVal === 'dashboard') {
                setTimeout(renderCharts, 100);
            } else if (newVal === 'heatmap') {
                setTimeout(renderCalendarioAnalytics, 100);
                setTimeout(scrollToHojeHeatmap, 300);
            }
        });

        watch(() => cicloAtivo.value?.bloco_atual_index, () => {
            if (abaAtiva.value === 'ciclo') {
                scrollToCurrentBlock();
                renderDonut();
            }
        });

        watch(cicloAtivo, (newCiclo) => {
            if (newCiclo && abaAtiva.value === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
            }
            if (newCiclo && newCiclo.nome && !localStorage.getItem('orbis_painel_prova')) {
                const nomeLower = newCiclo.nome.toLowerCase();
                if (nomeLower.includes('inss')) {
                    dadosProva.value.concurso = 'INSS';
                    dadosProva.value.cargo = 'Técnico do Seguro Social';
                    dadosProva.value.especialidade = 'Geral / Previdenciário';
                    dadosProva.value.banca = 'Cebraspe';
                    dadosProva.value.estilo_banca = 'Certo / Errado (1 anula 1)';
                    dadosProva.value.nota_corte = 82.0;
                    dadosProva.value.total_vagas = '1.000 vagas';
                    dadosProva.value.local_prova = 'Nacional';
                } else if (nomeLower.includes('sefaz')) {
                    dadosProva.value.concurso = 'SEFAZ ALAGOAS';
                    dadosProva.value.cargo = 'Auditor Fiscal da Receita Estadual';
                    dadosProva.value.especialidade = 'Tecnologia da Informação';
                    dadosProva.value.banca = 'Cebraspe';
                    dadosProva.value.estilo_banca = 'Certo / Errado (1 anula 1)';
                    dadosProva.value.nota_corte = 78.5;
                    dadosProva.value.total_vagas = '35 vagas';
                    dadosProva.value.local_prova = 'Maceió - AL';
                } else {
                    dadosProva.value.concurso = newCiclo.nome;
                }
            }
        });

        onMounted(async () => {
            // Fechar modais com tecla ESC para melhor acessibilidade
            window.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    if (modalCheckinAberto.value) modalCheckinAberto.value = false;
                    if (modalResumoAberto.value) modalResumoAberto.value = false;
                    if (avulsoSelecionado.value) avulsoSelecionado.value = null;
                    if (modalConfigProvaAberto.value) modalConfigProvaAberto.value = false;
                    if (modalAlertaMarcoAberto.value) modalAlertaMarcoAberto.value = false;
                    if (modalInsightsIAAberto.value) modalInsightsIAAberto.value = false;
                }
            });

            await loadAllData();
            if (abaAtiva.value === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
            }

            // Exibir alerta do marco (90d, 60d, 30d) automaticamente APENAS UMA VEZ por marco para a data da prova
            try {
                if (marcoAlerta.value) {
                    const marco = marcoAlerta.value.diasMarco;
                    const dataProva = dadosProva.value?.data_prova;
                    if (!marcoJaAlertado(marco, dataProva)) {
                        registrarMarcoAlertado(marco, dataProva);
                        setTimeout(() => {
                            modalAlertaMarcoAberto.value = true;
                        }, 700);
                    }
                }
            } catch (e) {
                console.warn('Erro ao verificar alerta de marco:', e);
            }
        });

        // ==========================================
        // 15. EXPOSIÇÃO DE PROPRIEDADES PARA O TEMPLATE
        // ==========================================
        return {
            // Estado Geral e Navegação
            estadoAplicacao,
            abaAtiva,
            abaVerticalizado,
            abaRaizResultados,
            abaRegistrar,
            abaHistorico,
            carregandoDados,
            carregandoResultados,
            processandoEdital,
            salvandoSessao,
            salvandoAvulso,
            salvandoEncerramento,

            // Alertas
            mensagemAlerta,
            tipoAlerta,
            mostrarAlerta,

            // Dados Principais
            editais,
            cicloAtivo,
            sessoes,
            dashboardData,
            matrizSemanalData,
            calendarioData,
            editalVerticalizadoData,

            // Wizard
            wizardPasso,
            wizardDados,
            wizardEditalGerado,
            cicloForm,
            preencherExemploWizard,
            processarEditalWizard,
            salvarPesoDisciplina,
            finalizarWizard,
            voltarAoWizard,
            iniciarApp,

            // Timer e Ciclo
            timerSegundos,
            timerRodando,
            toggleTimer,
            resetTimer,
            blocoAtual,
            todasDisciplinas,
            topicosDaDisciplina,
            percentualGlobalEdital,
            avancarBloco,
            selecionarBlocoManual,
            gerarCicloNovoComEdital,
            excluirEdital,

            // Sessões e Modais
            modalCheckinAberto,
            modalResumoAberto,
            resumoSessaoAtual,
            formSessao,
            abrirModalCheckin,
            abrirModalCheckinComBloco,
            salvarSessaoEstudo,
            editarSessao,
            excluirSessao,
            excluirTodasSessoes,

            // Verticalizado e Trilha de Estudos
            verticalizadoAberto,
            toggleVerticalizado,
            filtroVerticalizado,
            ordenacaoVerticalizado,
            setFiltroVerticalizado,
            setOrdenacaoVerticalizado,
            getTopicosFiltradosEOrdenados,
            toggleMaisCobrado,
            alterarPrioridadeTopico,
            toggleConcluidoTopico,
            iniciarEstudoDoTopico,
            onDisciplinaSessaoChange,
            getTopicoRowClass,
            badgePrioridadeSelectClass,
            getProximoTopicoTrilha,
            proximoTopicoBlocoAtual,
            abrirDashboard,
            carregarEditalVerticalizado,

            // Formatadores e Estatísticas
            formatarTempoTimer,
            formatarHorasDecimais,
            formatarData,
            formatarDataCurta,
            formatarTituloTopico,
            formatarPercentualBR,
            badgeTaxaAcertoBg,
            badgeTextTaxa,
            getAproveitamentoClasses,
            getNomeDisciplina,
            getEstatisticasDisciplina,
            getEstatisticasEdital,
            getTempoEstudadoCicloAtual,
            getTempoTotalCicloAtual,
            getTotaisMatrizSemanal,
            getRankingDisciplinas,
            getDataHojeLocal,

            // Resultados, Provas Avulsas e Raio-X
            resultadoAtual,
            formResultado,
            resultadosAvulsos,
            formAvulso,
            avulsoSelecionado,
            idEmEdicaoAvulso,
            editandoCiclo,
            disciplinasEncerramento,
            totaisEncerramento,
            insightsRaioX,
            rankingRevisoes,
            quadrantesRaioX,
            resumoProvasAvulsas,
            resultadosEncerrados,
            abrirResultados,
            carregarResultados,
            salvarResultado,
            salvarResultadoAvulso,
            editarResultadoAvulso,
            cancelarEdicaoAvulso,
            deletarResultadoAvulso,
            abrirModalDetalhesAvulso,
            fecharModalDetalhesAvulso,
            mudarAbaHistorico,
            prepararFormEncerramento,
            encerrarPreparacaoAvulsa,
            encerrarCicloOficial,
            visualizarDashboardEncerrado,
            carregarResultadosEncerrados,
            deletarCicloEncerrado,
            editarCicloEncerrado,
            renderGraficosAvulsos,
            renderizarGraficosResultados,
            exportarPDF,
            calcularPercentualTotal,
            calcularPercentualRendimento,
            calcularPercentualCorte,
            calcularRendimentoRaioX,
            calcularCorteRaioX,
            calcularComparativoInfo,

            // Tema e Navegação Moderna
            tema,
            alternarTema,
            sidebarMobileAberta,
            navegarPara,

            // Painel da Prova Alvo (Teste Local)
            dadosProva,
            modalConfigProvaAberto,
            modalAlertaMarcoAberto,
            formConfigProva,
            abrirModalConfigProva,
            salvarDadosProva,
            restaurarDadosProvaPadrao,
            abrirAlertaMarco,
            fecharAlertaMarco,
            definirDataProvaAtalho,
            resetarMarcosAlertados,
            diasAteProva,
            dataProvaFormatada,
            comparativoCorte,
            zonaProva,
            marcoAlerta,

            // Insights de IA (Coach de Concursos)
            modalInsightsIAAberto,
            carregandoInsightsIA,
            insightsIA,
            abrirModalInsightsIA,
            carregarInsightsIA,
            statusChaveGemini,
            mostrarConfigChaveIA,
            chaveGeminiInput,
            salvandoChaveIA,
            salvarChaveGemini,
            verificarStatusChaveIA,
            formatarTextoIA
        };
    }
});

app.config.errorHandler = (err, instance, info) => {
    console.error('Vue Error:', err, info);
};

app.mount('#app');