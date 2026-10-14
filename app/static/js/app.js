const { createApp, ref, computed, onMounted, nextTick } = Vue;

const app = createApp({
    setup() {
        // Estado Global
        const estadoAplicacao = ref('app'); // 'wizard' ou 'app'
        const abaAtiva = ref('ciclo');
        const resultadoAtual = ref(null);
        const carregandoResultados = ref(false);

        const abaRaizResultados = ref('registrar'); // 'registrar', 'historico'
        const abaRegistrar = ref('antiga'); // 'antiga', 'encerramento'
        const abaHistorico = ref('avulsos'); // 'avulsos', 'encerrados'

        const cicloAtivo = ref(null);
        const editandoCiclo = ref(false);
        const formResultado = ref({ nota_final: 0, nota_corte: 0, total_pontos_prova: '', nota_minima_aprovados: '', nota_maxima_aprovados: '', posicao: 0, total_vagas: 0, resultado_final: 'Aprovado' });
        const editais = ref([]);
        const sessoes = ref([]);
        const dashboardData = ref(null);
        const matrizSemanalData = ref({});
        const calendarioData = ref([]);
        const editalVerticalizadoData = ref({});
        const wizardPasso = ref(0);
        const wizardDados = ref({ nome: '', bancas: '', data: '', descricao: '' });
        const wizardEditalGerado = ref(null);
        const processandoEdital = ref(false);
        const cicloForm = ref({ carga_horaria_semanal: 20, duracao_bloco_minutos: 60 });
        const timerSegundos = ref(0);
        const timerRodando = ref(false);
        const getDataHojeLocal = () => {
            const d = new Date();
            const ano = d.getFullYear();
            const mes = String(d.getMonth() + 1).padStart(2, '0');
            const dia = String(d.getDate()).padStart(2, '0');
            return `${ano}-${mes}-${dia}`;
        };
        const modalCheckinAberto = ref(false);
        const formSessao = ref({
            id: null,
            disciplina_id: '',
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
            notas_observacoes: ''
        });
        const verticalizadoAberto = ref({});
        const modalResumoAberto = ref(false);
        const resumoSessaoAtual = ref(null);


        const rankingRevisoes = computed(() => {
            if (!resultadoAtual.value || !resultadoAtual.value.desempenho_disciplinas) return [];
            return [...resultadoAtual.value.desempenho_disciplinas].sort((a, b) => b.revisoes - a.revisoes);
        });

        const quadrantesRaioX = computed(() => {
            const quad = {
                dominado: [],
                eficienciaAlta: [],
                eficienciaBaixa: [],
                lacuna: []
            };

        

            if (!resultadoAtual.value || !resultadoAtual.value.desempenho_disciplinas) return quad;
            
            // Mediana de tempo para dividir alto/baixo tempo
            const tempos = resultadoAtual.value.desempenho_disciplinas.map(d => d.horas_dedicadas).sort((a,b)=>a-b);
            const medianaTempo = tempos.length > 0 ? tempos[Math.floor(tempos.length/2)] : 0;
            const tempoCorte = medianaTempo > 0 ? medianaTempo : 5.0; // fallback para 5h se não houver mediana boa
            
            resultadoAtual.value.desempenho_disciplinas.forEach(d => {
                if (d.horas_dedicadas === 0 && d.questoes_resolvidas === 0 && (!d.acertos_prova_perc || d.acertos_prova_perc === 0)) return; // ignorar se não houve estudo nem prova
                const acerto = (d.acertos_prova_perc !== undefined && d.acertos_prova_perc !== null && d.acertos_prova_perc > 0) ? d.acertos_prova_perc : (d.percentual_acerto || 0);
                
                if (d.horas_dedicadas >= tempoCorte && acerto >= 70) quad.dominado.push(d);
                else if (d.horas_dedicadas < tempoCorte && acerto >= 70) quad.eficienciaAlta.push(d);
                else if (d.horas_dedicadas >= tempoCorte && acerto < 70) quad.eficienciaBaixa.push(d);
                else quad.lacuna.push(d);
            });
            return quad;
        });

        const gerarInsightsRaioX = () => {
            insightsRaioX.value = [];
            const q = quadrantesRaioX.value;
            
            if (q.eficienciaBaixa.length > 0) {
                const nomes = q.eficienciaBaixa.map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Alerta de Retorno:</b> Você investiu muito tempo em <b>${nomes}</b> mas o acerto ficou abaixo de 70%. É recomendado mudar o material base ou o método (ex: trocar vídeo por PDF).`);
            }
            if (q.eficienciaAlta.length > 0) {
                const nomes = q.eficienciaAlta.slice(0, 2).map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Alta Retenção:</b> <b>${nomes}</b> tiveram excelente desempenho com poucas horas. Provavelmente você tem base forte; mantenha apenas via revisões e questões.`);
            }
            if (q.lacuna.length > 0) {
                const nomes = q.lacuna.slice(0, 2).map(d => d.nome).join(', ');
                insightsRaioX.value.push(`<b>Prioridade Urgente:</b> <b>${nomes}</b> estão com baixo tempo e baixo rendimento. Devem ser o foco principal no seu próximo ciclo de estudos.`);
            }
            if (insightsRaioX.value.length === 0) {
                insightsRaioX.value.push("Sua preparação está equilibrada. Continue mantendo a constância nos estudos e revisões.");
            }
        };

        let chartRaioX = null;

        const disciplinasEncerramento = ref([]);
        const insightsRaioX = ref([]);
        const resultadosEncerrados = ref([]);
        const resultadosAvulsos = ref([]);
        const avulsoSelecionado = ref(null);
        const idEmEdicaoAvulso = ref(null);
        const abrirModalDetalhesAvulso = (av) => { avulsoSelecionado.value = av; };
        
        const mudarAbaHistorico = (aba) => {
            abaHistorico.value = aba;
            nextTick(() => {
                setTimeout(() => {
                    if (aba === 'avulsos') renderGraficosAvulsos();
                    if (aba === 'encerrados') renderizarGraficosResultados();
                }, 150);
            });
        };

        const fecharModalDetalhesAvulso = () => { avulsoSelecionado.value = null; };

        const formAvulso = ref({
            nome_prova: '', banca: '', data_prova: '', nota_final: '', nota_corte: '', total_pontos_prova: '',
            acertos_basicos: '', erros_basicos: '', nota_basicos: '',
            acertos_especificos: '', erros_especificos: '', nota_especificos: '',
            nota_discursiva: '', posicao: '', resultado_final: 'Aprovado'
        });

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
                nome_prova: '', banca: '', data_prova: '', total_pontos_prova: '',
                acertos_basicos: '', erros_basicos: '', nota_basicos: '',
                acertos_especificos: '', erros_especificos: '', nota_especificos: '',
                nota_discursiva: '', nota_final: '', nota_corte: '', posicao: '', resultado_final: 'Aprovado'
            };
        };

// Gráficos Avulsos
let chartEvolucaoAvulsosInstance = null;
let chartDesempenhoAvulsosInstance = null;


const formatarPercentualBR = (val) => {
    if (val === null || val === undefined || isNaN(val)) return '-';
    const num = Number(val);
    const s = num.toFixed(2);
    if (s.endsWith('.00')) {
        return num.toFixed(0) + '%';
    } else if (s.endsWith('0')) {
        return num.toFixed(1).replace('.', ',') + '%';
    }
    return num.toFixed(2).replace('.', ',') + '%';
};

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
    if (totalPts > 0) {
        return formatarPercentualBR((nota / totalPts) * 100);
    }
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
    if (totalPts > 0) {
        return formatarPercentualBR((nota / totalPts) * 100);
    }
    let totalQ = 0;
    if (res.disciplinas_resultado && res.disciplinas_resultado.length > 0) {
        totalQ = res.disciplinas_resultado.reduce((acc, d) => acc + (Number(d.acertos) || 0) + (Number(d.erros) || 0), 0);
    }
    if (totalQ > 0) {
        return formatarPercentualBR((nota / totalQ) * 100);
    }
    if (res.acerto_geral_perc > 0) return formatarPercentualBR(res.acerto_geral_perc);
    return '-';
};

const calcularCorteRaioX = (res) => {
    if (!res) return '-';
    const totalPts = Number(res.total_pontos_prova);
    const corte = Number(res.nota_corte);
    if (corte === null || corte === undefined || corte === 0) return '-';
    if (totalPts > 0) {
        return formatarPercentualBR((corte / totalPts) * 100);
    }
    let totalQ = 0;
    if (res.disciplinas_resultado && res.disciplinas_resultado.length > 0) {
        totalQ = res.disciplinas_resultado.reduce((acc, d) => acc + (Number(d.acertos) || 0) + (Number(d.erros) || 0), 0);
    }
    if (totalQ > 0) {
        return formatarPercentualBR((corte / totalQ) * 100);
    }
    return '-';
};

const calcularComparativoInfo = (av) => {
    if (!av) return { texto: '-', classes: 'bg-slate-100 text-slate-600' };
    const totalPts = Number(av.total_pontos_prova);
    const nota = Number(av.nota_final) || 0;
    const temCorte = (av.nota_corte !== null && av.nota_corte !== undefined && av.nota_corte !== '');
    const corte = temCorte ? Number(av.nota_corte) : null;
    
    if (totalPts > 0 && corte !== null) {
        const diff = ((nota - corte) / totalPts) * 100;
        const diffFmt = (diff >= 0 ? '+' : '') + diff.toFixed(2).replace('.', ',') + '%';
        const isAprovado = diff >= 0;
        let statusTexto = isAprovado ? 'Aprovado' : 'Reprovado';
        if (av.resultado_final === 'Lista de Espera' || av.resultado_final === 'Cadastro Reserva') {
            statusTexto = av.resultado_final;
        }
        return {
            texto: `${statusTexto} (${diffFmt})`,
            classes: isAprovado ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-rose-100 text-rose-800 border border-rose-200'
        };
    } else if (corte !== null && corte > 0) {
        const diff = ((nota / corte) - 1) * 100;
        const diffFmt = (diff >= 0 ? '+' : '') + diff.toFixed(2).replace('.', ',') + '%';
        const isAprovado = diff >= 0;
        let statusTexto = isAprovado ? 'Aprovado' : 'Reprovado';
        if (av.resultado_final === 'Lista de Espera' || av.resultado_final === 'Cadastro Reserva') {
            statusTexto = av.resultado_final;
        }
        return {
            texto: `${statusTexto} (${diffFmt})`,
            classes: isAprovado ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-rose-100 text-rose-800 border border-rose-200'
        };
    }
    
    const isAprovado = av.resultado_final === 'Aprovado';
    return {
        texto: av.resultado_final || '-',
        classes: isAprovado ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-rose-100 text-rose-800 border border-rose-200'
    };
};

const renderGraficosAvulsos = () => {
    setTimeout(() => {
        if(chartEvolucaoAvulsosInstance) { chartEvolucaoAvulsosInstance.destroy(); chartEvolucaoAvulsosInstance = null; }
        if(chartDesempenhoAvulsosInstance) { chartDesempenhoAvulsosInstance.destroy(); chartDesempenhoAvulsosInstance = null; }
        
        const canvasEv = document.getElementById('chartEvolucaoAvulsos');
        const canvasDes = document.getElementById('chartDesempenhoAvulsos');
        if(!canvasEv || !canvasDes) return;
        
        // Ordenar cronologicamente para a linha do tempo (da mais antiga para a mais nova)
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
                            if (totalPts > 0) {
                                return (((nota - corte) / totalPts) * 100).toFixed(2);
                            }
                            if (corte > 0) {
                                return (((nota / corte) - 1) * 100).toFixed(2);
                            }
                            return null;
                        }),
                        borderColor: '#4f46e5',
                        backgroundColor: '#4f46e520',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        pointBackgroundColor: '#ffffff',
                        pointBorderWidth: 2
                    },
                    {
                        label: 'Nota de Corte (0%)',
                        data: dadosOrdenados.map(a => 0),
                        borderColor: '#ef4444',
                        borderDash: [5, 5],
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
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) { label += ': '; }
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
                            return (ac + er > 0) ? ((ac / (ac + er)) * 100).toFixed(1) : 0;
                        }),
                        backgroundColor: '#0ea5e9'
                    },
                    {
                        label: 'Específicos (% Acerto)',
                        data: dadosOrdenados.map(a => {
                            const ac = Number(a.acertos_especificos) || 0;
                            const er = Number(a.erros_especificos) || 0;
                            return (ac + er > 0) ? ((ac / (ac + er)) * 100).toFixed(1) : 0;
                        }),
                        backgroundColor: '#8b5cf6'
                    }
                ]
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false, 
                scales: { 
                    y: { min: 0, max: 100, ticks: { callback: function(value) { return value + "%" } } }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) { label += ': '; }
                                if (context.parsed.y !== null) { label += context.parsed.y + '%'; }
                                return label;
                            }
                        }
                    }
                }
            }
        });
    }, 100);
};

        
        
        const toggleVerticalizado = (id) => {
            verticalizadoAberto.value[id] = !verticalizadoAberto.value[id];
        };
        const formatarHorasDecimais = (h) => {
            if (!h) return "0h";
            return h.toFixed(1) + "h";
        };
        const getAproveitamentoClasses = (perc) => {
            if (perc >= 80) return { bg: "from-emerald-500/20 to-emerald-600/20", text: "from-emerald-400 to-emerald-200", border: "border-emerald-500/30" };
            if (perc >= 60) return { bg: "from-blue-500/20 to-blue-600/20", text: "from-blue-400 to-blue-200", border: "border-blue-500/30" };
            if (perc >= 40) return { bg: "from-amber-500/20 to-amber-600/20", text: "from-amber-400 to-amber-200", border: "border-amber-500/30" };
            return { bg: "from-rose-500/20 to-rose-600/20", text: "from-rose-400 to-rose-200", border: "border-rose-500/30" };
        };
        const abrirResultados = async () => {
            abaAtiva.value = 'resultados';
            abaRaizResultados.value = 'registrar';
            await carregarResultadosAvulsos();
            await carregarResultadosEncerrados();
        };
        const carregarResultados = async () => {};
        const salvarResultado = async () => {};


// formatarDataCurta
const formatarDataCurta = (isoStr) => {
            if (!isoStr) return '';
            const p = isoStr.split('-');
            if (p.length >= 3) {
                const day = p[2].includes('T') ? p[2].split('T')[0] : p[2].substring(0,2);
                return `${day}/${p[1]}/${p[0]}`;
            }
            return isoStr;
        }

// encerrarPreparacaoAvulsa
const encerrarPreparacaoAvulsa = async () => {
            if (!confirm("Tem certeza que deseja encerrar esta preparação e registrá-la como Resultado Oficial? Esta ação travará a inserção de novas horas de estudo para este edital.")) return;
            
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
                    alert("Preparação encerrada com sucesso!");
                    setTimeout(() => { renderGraficosAvulsos(); }, 100);
                } else {
                    const errorData = await response.json();
                    alert(errorData.detail || "Erro ao encerrar.");
                }
            } catch (error) {
                console.error("Erro ao encerrar:", error);
                alert("Erro de conexão ao encerrar a preparação.");
            }
        }

// salvarResultadoAvulso
const salvarResultadoAvulso = async () => {
            try {
                const toNumOrNull = (v) => (v === '' || v === null || v === undefined) ? null : Number(v);
                const toIntOrNull = (v) => (v === '' || v === null || v === undefined) ? null : parseInt(v);

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
                    mostrarAlerta(isEdicao ? "Prova antiga atualizada com sucesso!" : "Prova antiga cadastrada com sucesso!", "sucesso");
                    cancelarEdicaoAvulso();
                    await carregarResultadosAvulsos();
                    abaRaizResultados.value = 'historico';
                    abaHistorico.value = 'avulsos';
                    setTimeout(renderGraficosAvulsos, 150);
                } else {
                    const errData = await response.json();
                    mostrarAlerta(errData.detail || "Erro ao salvar", "erro");
                }
            } catch(e) {
                mostrarAlerta("Erro de rede", "erro");
            }
        };

// toggleTimer
const toggleTimer = () => {
            if (timerRodando.value) {
                clearInterval(timerInterval);
                timerRodando.value = false;
            } else {
                timerRodando.value = true;
                timerInterval = setInterval(() => { timerSegundos.value++; }, 1000);
            }
        }

// resetTimer
const resetTimer = () => {
            if (timerInterval) clearInterval(timerInterval);
            timerRodando.value = false;
            timerSegundos.value = 0;
        }

// formatarTempoTimer
const formatarTempoTimer = (s) => {
            const hrs = Math.floor(s / 3600);
            const mins = Math.floor((s % 3600) / 60);
            const secs = s % 60;
            return `${String(hrs).padStart(2,'0')}:${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
        }

// formatarData
const formatarData = (isoStr) => {
            if (!isoStr) return '';
            const p = isoStr.split('-');
            if (p.length >= 3) return `${p[2].substring(0,2)}/${p[1]}`;
            return isoStr;
        }

// badgeTaxaAcertoBg
const badgeTaxaAcertoBg = (perc) => {
            if (perc >= 80) return 'bg-emerald-100 text-emerald-800';
            if (perc >= 60) return 'bg-amber-100 text-amber-800';
            return 'bg-rose-100 text-rose-800';
        }

// badgeTextTaxa
const badgeTextTaxa = (perc) => {
            if (perc >= 80) return 'text-emerald-600';
            if (perc >= 60) return 'text-amber-500';
            return 'text-rose-500';
        }

// getNomeDisciplina
const getNomeDisciplina = (id) => {
            const d = todasDisciplinas.value.find(x => x.id === id);
            return d ? d.nome : `ID: ${id}`;
        }

// preencherExemploWizard
const preencherExemploWizard = () => {
            wizardDados.value.nome = "TSE Unificado 2024 - Analista TI";
            wizardDados.value.texto_basicos = "LÍNGUA PORTUGUESA: 1 Compreensão de texto. 2 Ortografia.\nDIREITO CONSTITUCIONAL: 1 Organização dos poderes.";
            wizardDados.value.texto_especificos = "TECNOLOGIA DA INFORMAÇÃO: 1 Banco de Dados Relacional. 2 Engenharia de Software.\nRACIOCÍNIO LÓGICO: 1 Probabilidade.";
        }

// processarEditalWizard
const processarEditalWizard = async () => {
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
                    mostrarAlerta("Falha ao processar edital", "erro");
                }
            } catch(e) {
                mostrarAlerta("Erro de rede", "erro");
            } finally {
                processandoEdital.value = false;
            }
        }

// salvarPesoDisciplina
const salvarPesoDisciplina = async (disc) => {
            try {
                await fetch(`/api/editais/disciplinas/${disc.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        peso_prova: disc.peso_prova,
                        relevancia_dificuldade: disc.relevancia_dificuldade,
                        categoria: disc.categoria
                    })
                });
            } catch(e) {}
        }

// finalizarWizard
const finalizarWizard = async () => {
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
                    mostrarAlerta("Ciclo inteligente gerado com sucesso! Bons estudos.");
                } else {
                    mostrarAlerta("Falha ao gerar o ciclo", "erro");
                }
            } catch(e) {
                mostrarAlerta("Erro ao finalizar", "erro");
            }
        }

// abrirDashboard
const abrirDashboard = () => {
            abaAtiva.value = 'dashboard';
            setTimeout(renderCharts, 100);
        }

// carregarEditalVerticalizado
const carregarEditalVerticalizado = (id) => {
            carregarDashboardData(id);
            mostrarAlerta("Relatório verticalizado atualizado!");
        }

// prepararFormEncerramento
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
        };

// encerrarCicloOficial
const encerrarCicloOficial = async () => {
            const editalId = editandoCiclo.value
                ? (formResultado.value?.edital_id || resultadoAtual.value?.edital_id || cicloAtivo.value?.edital_id)
                : (cicloAtivo.value?.edital_id || (editais.value.length > 0 ? editais.value[0].id : null));
                
            if (!editalId) {
                alert("Nenhum edital selecionado ou ativo.");
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
                    alert(editandoCiclo.value ? "Ciclo atualizado com sucesso!" : "Preparação encerrada com sucesso!");
                    editandoCiclo.value = false;
                    abaRaizResultados.value = 'historico';
                    abaHistorico.value = 'encerrados';
                    await carregarResultadosEncerrados();
                    await visualizarDashboardEncerrado(editalId);
                } else {
                    const data = await response.json();
                    alert(data.detail || "Erro ao encerrar preparação.");
                }
            } catch (error) {
                console.error(error);
                alert("Erro de conexão ao salvar encerramento.");
            }
        };


        const carregarResultadosEncerrados = async () => {
            try {
                const res = await fetch('/api/resultados/encerrados');
                if (res.ok) {
                    resultadosEncerrados.value = await res.json();
                }
            } catch (e) {
                console.error(e);
            }
        };

        const deletarCicloEncerrado = async (edital_id) => {
            if(!confirm('Tem certeza que deseja excluir o encerramento deste ciclo? Ele voltar a ficar ativo.')) return;
            try {
                const res = await fetch(`/api/resultados/${edital_id}`, { method: 'DELETE' });
                if (res.ok) {
                    await carregarEditais();
                    if (resultadoAtual.value && resultadoAtual.value.edital_id === edital_id) {
                        window.location.reload();
                    } else {
                        await carregarResultadosEncerrados();
                    }
                }
            } catch (e) {
                console.error(e);
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
                data_prova: res.data_encerramento ? res.data_encerramento.split('T')[0] : '',
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

        const renderizarGraficosResultados = () => {
            if (!resultadoAtual.value) return;
            
            // Gerar Insights do Raio-X
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
                            pointBackgroundColor: 'rgba(99, 102, 241, 1)',
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: { r: { beginAtZero: true } }
                    }
                });
            }

            // BAR
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
                            {
                                label: '% Acerto',
                                data: dataAcerto,
                                backgroundColor: 'rgba(16, 185, 129, 0.7)'
                            },
                            {
                                label: '% Visto',
                                data: dataVisto,
                                backgroundColor: 'rgba(99, 102, 241, 0.7)'
                            }
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

            // SCATTER RAIO-X: Tempo x Acerto na Prova
            if (ctxScatter && resultadoAtual.value.desempenho_disciplinas) {
                if (window.scatterRaioXInstance) {
                    window.scatterRaioXInstance.destroy();
                    window.scatterRaioXInstance = null;
                }
                
                const quad = quadrantesRaioX.value;
                const getPontoCor = (d) => {
                    if (quad.dominado.some(x => x.disciplina_id === d.disciplina_id)) return '#10b981'; // verde
                    if (quad.eficienciaAlta.some(x => x.disciplina_id === d.disciplina_id)) return '#3b82f6'; // azul
                    if (quad.eficienciaBaixa.some(x => x.disciplina_id === d.disciplina_id)) return '#f59e0b'; // laranja/âmbar
                    return '#f43f5e'; // rosa/vermelho
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
                                    label: function(context) {
                                        const p = context.raw;
                                        return `${p.nome}: ${p.x}h estudadas | ${p.y}% acerto na prova`;
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Tempo Estudado (horas)',
                                    color: '#64748b',
                                    font: { weight: 'bold', size: 11 }
                                },
                                beginAtZero: true
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Acerto na Prova (%)',
                                    color: '#64748b',
                                    font: { weight: 'bold', size: 11 }
                                },
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            }
        };
const exportarPDF = () => {
            const element = document.getElementById('pdf-content');
            const opt = {
                margin: 10,
                filename: 'resultado_concurso_' + cicloAtivo.value.nome + '.pdf',
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2 },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            };
            html2pdf().set(opt).from(element).save();
        };

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

        // Interação do Ciclo
        function triggerConfetti() {
            if (typeof confetti !== 'undefined') {
                confetti({
                    particleCount: 150,
                    spread: 70,
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
                        mostrarAlerta("Parabéns! Você completou mais um ciclo inteiro!");
                    }
                    resetTimer();
                }
            } catch(e){}
        }

        async function selecionarBlocoManual(idx) {
            if (!cicloAtivo.value && !editandoCiclo.value) return;
            const currentIdx = cicloAtivo.value.bloco_atual_index;
            const blocoClicado = cicloAtivo.value.blocos[idx];
            
            if (idx > currentIdx) {
                mostrarAlerta("Você ainda não chegou nesta fase! Conclua ou pule a fase atual.", "aviso");
                return;
            }
            if (idx === currentIdx) {
                // Abre o modal de checkin do atual
                abrirModalCheckinComBloco(blocoClicado);
                return;
            }
            
            // idx < currentIdx (Já estudou)
            // Encontrar a última sessão logada para este bloco
            const sessoesBloco = sessoes.value.filter(s => s.bloco_ciclo_id === blocoClicado.id);
            if (sessoesBloco.length > 0) {
                const ultimaSessao = sessoesBloco.reduce((a, b) => (new Date(a.data_criacao) > new Date(b.data_criacao) ? a : b));
                resumoSessaoAtual.value = {
                    sessao: ultimaSessao,
                    bloco: blocoClicado
                };
                modalResumoAberto.value = true;
            } else {
                mostrarAlerta("Nenhuma sessão logada encontrada para este bloco na rodada atual.", "aviso");
            }
        }

        async function gerarCicloNovoComEdital(edital_id) {
            if(!confirm("Gerar um novo ciclo com estes pesos? O ciclo anterior será desativado.")) return;
            try {
                const res = await fetch('/api/ciclos/gerar', {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ edital_id, carga_horaria_semanal: 20, duracao_bloco_minutos: 60 })
                });
                if(res.ok) {
                    mostrarAlerta("Novo ciclo gerado!");
                    await loadAllData();
                    abaAtiva.value = 'ciclo';
                }
            } catch(e){}
        }

        // Helper para Estatísticas na listagem
        function getEstatisticasDisciplina(id) {
            if (!dashboardData.value) return { qtd: 0, perc: 0, perc_vistos: 0 };
        const stats = dashboardData.value.rendimento_disciplinas || [];
            const d = stats.find(x => x.disciplina_id === id);
            
            // Calcula % Visto localmente
            let perc_vistos = 0;
            let disciplina = null;
            for (const ed of editais.value) {
                const found = ed.disciplinas.find(x => x.id === id);
                if (found) { disciplina = found; break; }
            }
            if (disciplina && disciplina.topicos && disciplina.topicos.length > 0) {
                const topicosId = disciplina.topicos.map(t => t.id);
                const sessoesDisc = sessoes.value.filter(s => s.disciplina_id === id && s.topico_id !== null);
                const topicosVistos = new Set(sessoesDisc.map(s => s.topico_id));
                perc_vistos = (topicosVistos.size / topicosId.length) * 100;
            }

            if (d && d.total_questoes > 0) {
                
        return {
qtd: d.total_questoes, perc: d.percentual_acerto, perc_vistos };
            }
            return {
qtd: 0, perc: 0, perc_vistos };
        }

        function getEstatisticasEdital(ed) {
            if (!ed) return { horas: "0h", topicos_vistos: 0, topicos_total: 0, perc_visto: 0 };
            let horas = 0;
            let topicos_total = 0;
            const topicosVistos = new Set();
            
            // Horas estudadas: soma do tempo de todas as sessoes desse edital
            const discIds = (ed.disciplinas || []).map(d => d.id);
            const sessoesEdital = (sessoes.value || []).filter(s => discIds.includes(s.disciplina_id));
            horas = sessoesEdital.reduce((acc, s) => acc + (s.tempo_estudado_minutos || 0), 0) / 60;
            
            // Topicos vistos vs totais
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

        async function excluirEdital(id) {
            if (!confirm("Tem certeza que deseja apagar este edital e TODOS os seus ciclos e sessões? Esta ação não pode ser desfeita.")) return;
            try {
                const res = await fetch(`/api/editais/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    mostrarAlerta("Edital excluído com sucesso!");
                    await loadAllData();
                } else {
                    mostrarAlerta("Erro ao excluir edital", "erro");
                }
            } catch (e) {
                mostrarAlerta("Erro de rede ao excluir", "erro");
            }
        }

        // Sessão Manual
        function abrirModalCheckin() {
            formSessao.value = {
                id: null,
                disciplina_id: (blocoAtual.value && blocoAtual.value.disciplina_id) ? blocoAtual.value.disciplina_id : (todasDisciplinas.value[0]?.id || ''),
                bloco_ciclo_id: blocoAtual.value ? blocoAtual.value.id : null,
                topico_id: '',
                tempo_estudado_minutos: 60,
                qtd_questoes_total: 0,
                qtd_acertos: 0,
                qtd_erros: 0,
                is_revisao_anki: false,
                avancar_ciclo: true,
                data: getDataHojeLocal()
            };
            modalCheckinAberto.value = true;
        }

        function abrirModalCheckinComBloco(b) {
            const bloco = b || blocoAtual.value;
            const isRevisao = bloco && bloco.disciplina && bloco.disciplina.categoria === 'REVISAO_ANKI';
            formSessao.value = {
                id: null,
                is_revisao_anki: isRevisao,
                disciplina_id: isRevisao ? (todasDisciplinas.value[0]?.id || '') : (bloco ? bloco.disciplina_id : (todasDisciplinas.value[0]?.id || '')),
                bloco_ciclo_id: bloco ? bloco.id : (blocoAtual.value ? blocoAtual.value.id : null),
                topico_id: '',
                tempo_estudado_minutos: timerSegundos.value > 0 ? Math.max(1, Math.round(timerSegundos.value / 60)) : (bloco?.duracao_minutos || 60),
                qtd_questoes_total: 0,
                qtd_acertos: 0,
                qtd_erros: 0,
                avancar_ciclo: true,
                data: getDataHojeLocal()
            };
            modalCheckinAberto.value = true;
        }

        async function salvarSessaoEstudo() {
            if (!formSessao.value.is_revisao_anki && topicosDaDisciplina.value.length > 0 && !formSessao.value.topico_id) {
                mostrarAlerta('Você precisa selecionar o Tópico Estudado para contabilizar o rendimento do edital.', 'erro');
                return;
            }

            if (!formSessao.value.is_revisao_anki && formSessao.value.qtd_acertos === 0 && formSessao.value.qtd_erros === 0) {
                mostrarAlerta('Você deve registrar pelo menos 1 acerto ou erro nas questões.', 'erro');
                return;
            }

            if (!formSessao.value.data) {
                formSessao.value.data = getDataHojeLocal();
            }

            const hoje = getDataHojeLocal();
            if (formSessao.value.data > hoje) {
                mostrarAlerta('Não é possível registrar uma sessão em uma data futura.', 'erro');
                return;
            }

            let total_q = formSessao.value.qtd_questoes_total;
            let a = formSessao.value.qtd_acertos;
            let e = formSessao.value.qtd_erros;
            if(total_q === 0 && (a > 0 || e > 0)) formSessao.value.qtd_questoes_total = a + e;
            
            const oldVoltas = cicloAtivo.value ? (cicloAtivo.value.voltas_completas || 0) : 0;
            let oldPerc = 0;
            try {
                if (cicloAtivo.value && editais.value) {
                    const ed = editais.value.find(item => item.id === cicloAtivo.value.edital_id);
                    if (ed) oldPerc = getEstatisticasEdital(ed).perc_visto;
                }
            } catch(e) {
                console.warn(e);
            }
            
            const method = formSessao.value.id ? 'PUT' : 'POST';
            const url = formSessao.value.id ? `/api/sessoes/${formSessao.value.id}` : '/api/sessoes';

            const payload = { ...formSessao.value };
            if (payload.topico_id === "" || payload.topico_id === null || payload.topico_id === undefined) {
                payload.topico_id = null;
            } else {
                payload.topico_id = parseInt(payload.topico_id, 10);
            }
            if (payload.bloco_ciclo_id === "" || payload.bloco_ciclo_id === undefined) {
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

            let res;
            try {
                res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch(netErr) {
                console.error("Erro de rede no fetch:", netErr);
                mostrarAlerta("Erro de rede ao salvar sessão", "erro");
                return;
            }

            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                mostrarAlerta(errJson.detail || "Erro ao salvar sessão", "erro");
                return;
            }

            // Sessão gravada com sucesso! Fechar modal e resetar timer
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
                    mostrarAlerta(`Parabéns! Você já bateu ${newDecile * 10}% do edital!`);
                } else if (cicloAtivo.value && cicloAtivo.value.voltas_completas > oldVoltas) {
                    triggerConfetti();
                    mostrarAlerta("Sessão registrada! Parabéns, você completou uma volta do ciclo!");
                } else {
                    mostrarAlerta("Sessão registrada com sucesso!");
                }

                renderDonut();
                scrollToCurrentBlock();
            } catch(uiErr) {
                console.error("Erro pós-salvamento na interface:", uiErr);
                mostrarAlerta("Sessão registrada com sucesso!");
            }
        }

        function editarSessao(s) {
            formSessao.value = {
                id: s.id,
                disciplina_id: s.disciplina_id,
                bloco_ciclo_id: s.bloco_ciclo_id,
                topico_id: s.topico_id || "",
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

        
        async function excluirTodasSessoes() {
            if (confirm("Tem certeza que deseja apagar TODAS as sessões de estudo? Esta ação não pode ser desfeita e os seus gráficos serão zerados.")) {
                try {
                    const r = await fetch('/api/sessoes/todas', { method: 'DELETE' });
                    if (r.ok) {
                        sessoes.value = [];
                        mostrarAlerta('Todas as sessões foram excluídas!', 'sucesso');
                        if (abaAtiva.value === 'dashboard' || abaAtiva.value === 'calendario') {
                            // Reload to empty charts
                            window.location.reload();
                        }
                    } else {
                        mostrarAlerta('Erro ao excluir sessões', 'erro');
                    }
                } catch (e) {
                    mostrarAlerta('Erro de conexão', 'erro');
                }
            }
        }

        async function excluirSessao(id) {
            if (!confirm('Deseja realmente excluir esta sessão?')) return;
            try {
                const res = await fetch(`/api/sessoes/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    mostrarAlerta('Sessão excluída com sucesso!', 'sucesso');
                    await loadAllData();
                } else {
                    mostrarAlerta('Erro ao excluir sessão.', 'erro');
                }
            } catch (e) {
                mostrarAlerta('Erro ao excluir sessão.', 'erro');
            }
        }

        function getTempoEstudadoCicloAtual() {
            if (!cicloAtivo.value) return "00:00:00";
            const sessoesCiclo = sessoes.value.filter(s => s.ciclo_id === cicloAtivo.value.id && s.volta_ciclo === cicloAtivo.value.voltas_completas);
            const totalMins = sessoesCiclo.reduce((acc, s) => acc + s.tempo_estudado_minutos, 0);
            return formatarTempoTimer(totalMins * 60);
        }

        function getTempoTotalCicloAtual() {
            if (!cicloAtivo.value) return "0h";
            const sessoesCiclo = sessoes.value.filter(s => s.ciclo_id === cicloAtivo.value.id);
            const totalMins = sessoesCiclo.reduce((acc, s) => acc + s.tempo_estudado_minutos, 0);
            return formatarHorasDecimais(totalMins / 60);
        }

        let chartEvolucaoInstance = null; let chartDiscInstance = null; let barChartInstance = null; let radarChartInstance = null;
        let chartCicloDonutInstance = null;
        function renderDonut() {
            nextTick(() => {
                const ctxD = document.getElementById('chartCicloDonut');
                if (!ctxD) return;
                
                if (chartCicloDonutInstance) chartCicloDonutInstance.destroy();
                
                if (!cicloAtivo.value || !cicloAtivo.value.blocos) return;
                
                // Map disciplines to colors
                const palette = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
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
                    
                    labels.push(`Fase ${idx+1}: ${nome}`);
                    data.push(b.duracao_minutos);
                    
                    const baseColor = discColors[nome];
                    if (idx === currentIndex) {
                        colors.push(baseColor);
                    } else if (idx < currentIndex) {
                        colors.push(baseColor + '40'); // 25% opacity for past
                    } else {
                        colors.push(baseColor + '99'); // 60% opacity for future
                    }
                    borderColors.push('#ffffff');
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
                        cutout: '70%',
                        layout: { padding: 45 }, // Extra padding for the arrow
                        plugins: { 
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        let label = context.label || '';
                                        if (label) { label += ': '; }
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
                            
                            const meta = chart.getDatasetMeta(0);
                            if (!meta || !meta.data[activeIdx]) return;
                            
                            const arc = meta.data[activeIdx];
                            
                            // Find the angle of the center of the active slice
                            const centerAngle = (arc.startAngle + arc.endAngle) / 2;
                            
                            // Draw an arrow outside the arc pointing inwards
                            const distance = 20; // Length of arrow
                            const offset = arc.options.offset || 0;
                            const targetRadius = arc.outerRadius + offset + 6; 
                            const targetX = arc.x + Math.cos(centerAngle) * targetRadius;
                            const targetY = arc.y + Math.sin(centerAngle) * targetRadius;
                            
                            const startRadius = targetRadius + distance;
                            const startX = arc.x + Math.cos(centerAngle) * startRadius;
                            const startY = arc.y + Math.sin(centerAngle) * startRadius;
                            
                            ctx.save();
                            
                            // Add glowing effect (graphite/slate theme)
                            ctx.shadowColor = 'rgba(71, 85, 105, 0.4)';
                            ctx.shadowBlur = 10;
                            
                            // Draw line (tail of the pointer)
                            ctx.beginPath();
                            ctx.moveTo(startX, startY);
                            ctx.lineTo(targetX, targetY);
                            ctx.strokeStyle = '#475569'; // slate-600 (graphite)
                            ctx.lineWidth = 3;
                            ctx.stroke();
                            
                            // Draw a futuristic glowing dot at the base of the arrow
                            ctx.beginPath();
                            ctx.arc(startX, startY, 4, 0, 2 * Math.PI);
                            ctx.fillStyle = '#ffffff';
                            ctx.fill();
                            ctx.lineWidth = 2;
                            ctx.stroke();
                            
                            // Draw technological chevron (arrow head)
                            const angle = Math.atan2(targetY - startY, targetX - startX);
                            ctx.beginPath();
                            ctx.moveTo(targetX, targetY);
                            ctx.lineTo(targetX - 14 * Math.cos(angle - Math.PI / 7), targetY - 14 * Math.sin(angle - Math.PI / 7));
                            ctx.lineTo(targetX - 8 * Math.cos(angle), targetY - 8 * Math.sin(angle)); // Indent the back of the arrow head
                            ctx.lineTo(targetX - 14 * Math.cos(angle + Math.PI / 7), targetY - 14 * Math.sin(angle + Math.PI / 7));
                            ctx.closePath();
                            ctx.fillStyle = '#475569';
                            ctx.fill();
                            
                            ctx.restore();
                        }
                    }]
                });
            });
        }

        // Charts
        let chartEvolucaoSemanalInstance = null;
        

        let chartAderenciaInstance = null;
        let chartDiaSemanaInstance = null;
        let chartIntensidadeInstance = null;
        let chartEvolucaoRiscoInstance = null;

        function renderCalendarioAnalytics() {
            nextTick(() => {
                if (!calendarioData.value || !calendarioData.value.analytics) return;
                const analytics = calendarioData.value.analytics;

                // 1. Aderência
                const ctxAd = document.getElementById('chartAderencia');
                if (ctxAd) {
                    if (chartAderenciaInstance) chartAderenciaInstance.destroy();
                    chartAderenciaInstance = new Chart(ctxAd, {
                        type: 'doughnut',
                        data: {
                            labels: ['Estudados', 'Não Estudados'],
                            datasets: [{
                                data: [analytics.taxa_aderencia, 100 - analytics.taxa_aderencia],
                                backgroundColor: ['#2563eb', '#e2e8f0'],
                                borderWidth: 0
                            }]
                        },
                        options: {
                            cutout: '75%',
                            plugins: { legend: { display: false }, tooltip: { enabled: false } }
                        },
                        plugins: [{
                            id: 'textCenter',
                            beforeDraw: function(chart) {
                                var width = chart.width, height = chart.height, ctx = chart.ctx;
                                ctx.restore();
                                var fontSize = (height / 80).toFixed(2);
                                ctx.font = "bold " + fontSize + "em sans-serif";
                                ctx.textBaseline = "middle";
                                ctx.fillStyle = "#1e293b";
                                var text = analytics.taxa_aderencia + "%",
                                    textX = Math.round((width - ctx.measureText(text).width) / 2),
                                    textY = height / 2;
                                ctx.fillText(text, textX, textY);
                                ctx.save();
                            }
                        }]
                    });
                }

                // 2. Dia da Semana
                const ctxDS = document.getElementById('chartDiaSemana');
                if (ctxDS) {
                    if (chartDiaSemanaInstance) chartDiaSemanaInstance.destroy();
                    const dsValues = [
                        analytics.media_horas_dsemana[0],
                        analytics.media_horas_dsemana[1],
                        analytics.media_horas_dsemana[2],
                        analytics.media_horas_dsemana[3],
                        analytics.media_horas_dsemana[4],
                        analytics.media_horas_dsemana[5],
                        analytics.media_horas_dsemana[6]
                    ];
                    chartDiaSemanaInstance = new Chart(ctxDS, {
                        type: 'bar',
                        data: {
                            labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                            datasets: [{
                                label: 'Média de Horas',
                                data: dsValues,
                                backgroundColor: dsValues.map(v => v < 2 ? '#ef4444' : '#3b82f6'),
                                borderRadius: 4
                            }]
                        },
                        options: { maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
                    });
                }

                // 3. Intensidade
                const ctxI = document.getElementById('chartIntensidade');
                if (ctxI) {
                    if (chartIntensidadeInstance) chartIntensidadeInstance.destroy();
                    const bins = {'0-1h':0, '1-2h':0, '2-3h':0, '3-4h':0, '4-5h':0, '5h+':0};
                    analytics.distribuicao_horas.forEach(h => {
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
                                label: 'Dias', data: Object.values(bins), backgroundColor: '#60a5fa',
                                borderRadius: 4, categoryPercentage: 1.0, barPercentage: 0.95
                            }]
                        },
                        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
                    });
                }

                // 4. Evolução
                const ctxER = document.getElementById('chartEvolucaoRisco');
                if (ctxER) {
                    if (chartEvolucaoRiscoInstance) chartEvolucaoRiscoInstance.destroy();
                    const evolucao = analytics.evolucao_diaria;
                    const ma7 = []; const ma30 = [];
                    for(let i=0; i<evolucao.length; i++) {
                        let sum7 = 0; let c7 = 0;
                        for(let j=Math.max(0, i-6); j<=i; j++) { sum7 += evolucao[j].horas; c7++; }
                        ma7.push(sum7/c7);
                        let sum30 = 0; let c30 = 0;
                        for(let j=Math.max(0, i-29); j<=i; j++) { sum30 += evolucao[j].horas; c30++; }
                        ma30.push(sum30/c30);
                    }
                    chartEvolucaoRiscoInstance = new Chart(ctxER, {
                        type: 'line',
                        data: {
                            labels: evolucao.map(e => e.data.substring(5,10).replace('-','/')),
                            datasets: [
                                { type: 'bar', label: 'Horas no Dia', data: evolucao.map(e => e.horas), backgroundColor: '#94a3b8', borderRadius: 4, order: 3 },
                                { type: 'line', label: 'Média Móvel 7d', data: ma7, borderColor: '#1e3a8a', borderWidth: 2, tension: 0.3, pointRadius: 0, order: 2 },
                                { type: 'line', label: 'Média Móvel 30d', data: ma30, borderColor: '#f59e0b', borderWidth: 2, borderDash: [5, 5], tension: 0.3, pointRadius: 0, order: 1 }
                            ]
                        },
                        options: {
                            maintainAspectRatio: false,
                            scales: { y: { beginAtZero: true, suggestedMax: 7 } },
                            plugins: { legend: { position: 'bottom' } }
                        },
                        plugins: [{
                            id: 'burnoutZone',
                            beforeDraw: function(chart) {
                                const yAxis = chart.scales.y;
                                const ctx = chart.ctx;
                                if (yAxis.max > 6) {
                                    const yTop = yAxis.getPixelForValue(yAxis.max);
                                    const yBottom = yAxis.getPixelForValue(6);
                                    ctx.save();
                                    ctx.fillStyle = 'rgba(239, 68, 68, 0.1)';
                                    ctx.fillRect(chart.chartArea.left, yTop, chart.chartArea.right - chart.chartArea.left, yBottom - yTop);
                                    ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
                                    ctx.font = 'bold 11px sans-serif';
                                    ctx.fillText('ZONA DE BURNOUT', chart.chartArea.left + 10, yBottom - 5);
                                    ctx.restore();
                                }
                            }
                        }]
                    });
                }
            });
        }

        function renderCharts() {
            const ctxD = document.getElementById('chartDisciplinas');
            const ctxES = document.getElementById('chartEvolucaoSemanal');
            const ctxE = document.getElementById('chartEvolucao');
            if(!ctxD || !ctxES || !ctxE) return;

            if (!dashboardData.value) return;
            const discData = dashboardData.value.rendimento_disciplinas || [];
            if (chartDiscInstance) chartDiscInstance.destroy();
            chartDiscInstance = new Chart(ctxD, {
                type: 'bar',
                data: {
                    labels: discData.map(d => d.disciplina_nome.substring(0,15)),
                    datasets: [{
                        data: discData.map(d => d.percentual_acerto),
                        backgroundColor: discData.map(d => d.percentual_acerto >= 80 ? '#10b981' : (d.percentual_acerto >= 60 ? '#f59e0b' : '#f43f5e')),
                        borderRadius: 6
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { max: 100 } } }
            });

            const totaisSemanais = getTotaisMatrizSemanal();
            if (chartEvolucaoSemanalInstance) chartEvolucaoSemanalInstance.destroy();
            chartEvolucaoSemanalInstance = new Chart(ctxES, {
                type: 'line',
                data: {
                    labels: (matrizSemanalData.value && matrizSemanalData.value.labels) ? matrizSemanalData.value.labels : [],
                    datasets: [{
                        label: '% Acertos',
                        data: (totaisSemanais && totaisSemanais.semanas) ? totaisSemanais.semanas.map(s => parseFloat(s.percentual)) : [],
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true, tension: 0.4, borderWidth: 3, pointBackgroundColor: '#8b5cf6', pointRadius: 4
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
                        label: '% Acertos',
                        data: hist.map(h => h.percentual_acerto),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true, tension: 0.3
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { max: 100 } } }
            });
        }

        
        Vue.watch(abaRaizResultados, (newVal) => {
            if (newVal === 'historico') {
                setTimeout(() => {
                    if (abaHistorico.value === 'avulsos') renderGraficosAvulsos();
                    if (abaHistorico.value === 'encerrados') renderizarGraficosResultados();
                }, 100);
            }
        });

        Vue.watch(abaHistorico, (newVal) => {
            if (newVal === 'avulsos') {
                renderGraficosAvulsos();
            }
        });

        Vue.watch(abaAtiva, (newVal) => {
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

        Vue.watch(() => cicloAtivo.value?.bloco_atual_index, () => {
            if (abaAtiva.value === 'ciclo') {
                scrollToCurrentBlock();
                renderDonut();
            }
        });

        Vue.watch(cicloAtivo, (newCiclo) => {
            if (newCiclo && abaAtiva.value === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
            }
        });

        onMounted(async () => {
            await loadAllData();
            if (abaAtiva.value === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
            }
        });

        function getTotaisMatrizSemanal() {
            if (!matrizSemanalData.value || !matrizSemanalData.value.labels) return null;
            
            const numSemanas = matrizSemanalData.value.labels.length;
            const totaisSemanas = Array.from({length: numSemanas}, () => ({ certas: 0, resolvidas: 0 }));
            let totalGeralCertas = 0;
            let totalGeralResolvidas = 0;

            const processarGrupo = (grupo) => {
                if (!grupo) return;
                grupo.forEach(disc => {
                    disc.semanas.forEach((sem, idx) => {
                        totaisSemanas[idx].certas += sem.certas;
                        totaisSemanas[idx].resolvidas += sem.resolvidas;
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
                return {
...t, percentual: perc };
            });

            const percGeral = totalGeralResolvidas > 0 ? ((totalGeralCertas / totalGeralResolvidas) * 100).toFixed(1) : 0;

            return {
                                    renderGraficosAvulsos,
            calcularPercentualTotal, abrirModalDetalhesAvulso, fecharModalDetalhesAvulso, mudarAbaHistorico, avulsoSelecionado,
                semanas: semanasProcessadas,
                totalGeral: { certas: totalGeralCertas, resolvidas: totalGeralResolvidas, percentual: percGeral }
            };
        }

        function getRankingDisciplinas() {
            if (!dashboardData.value || !dashboardData.value.rendimento_disciplinas) {
                return {
melhores: [], piores: [] };
            }
            
            const arr = [...dashboardData.value.rendimento_disciplinas];
            
            const piores = [...arr].filter(a => a.total_questoes > 0).sort((a, b) => {
                if (a.percentual_acerto !== b.percentual_acerto) {
                    return a.percentual_acerto - b.percentual_acerto; 
                }
                return b.total_questoes - a.total_questoes; 
            }).slice(0, 3);
            
            const melhores = [...arr].filter(a => a.total_questoes > 0).sort((a, b) => {
                if (b.percentual_acerto !== a.percentual_acerto) {
                    return b.percentual_acerto - a.percentual_acerto; 
                }
                return b.total_questoes - a.total_questoes; 
            }).slice(0, 3);
            
            return {
piores, melhores };
        }

        
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
                    alert("Erro ao carregar o dashboard deste ciclo.");
                }
            } catch (error) {
                console.error(error);
                alert("Erro de conexão.");
            } finally {
                carregandoResultados.value = false;
            }
        };

        
        const carregarEditais = async () => {
            try {
                const res = await fetch('/api/editais');
                if (res.ok) {
                    editais.value = await res.json();
                }
            } catch (e) { console.error(e); }
        };

        const abaVerticalizado = ref({});


async function carregarDashboardData(edital_id) {
            const rDash = await fetch('/api/dashboard');
            if (rDash.ok) dashboardData.value = await rDash.json();

            const rMat = await fetch(`/api/dashboard/matriz-semanal?edital_id=${edital_id}`);
            if (rMat.ok) matrizSemanalData.value = await rMat.json();

            const rCal = await fetch(`/api/dashboard/calendario-estudos?edital_id=${edital_id}&dias=30`);
            if (rCal.ok) calendarioData.value = await rCal.json();

            const rVert = await fetch(`/api/dashboard/edital-verticalizado?edital_id=${edital_id}`);
            if (rVert.ok) editalVerticalizadoData.value = await rVert.json();

            renderCharts();
        }

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

const carregarResultadosAvulsos = async () => {
    try {
        const response = await fetch('/api/resultados_avulsos');
        if (response.ok) {
            const dados = await response.json();
            resultadosAvulsos.value = ordenarPorDataDesc(dados);
        }
    } catch (e) {
        console.error(e);
    }
};

const deletarResultadoAvulso = async (id) => {
            if (!confirm("Tem certeza que deseja excluir este resultado?")) return;
            try {
                const response = await fetch('/api/resultados_avulsos/' + id, { method: 'DELETE' });
                if (response.ok) {
                    mostrarAlerta("Resultado excluído", "sucesso");
                    await carregarResultadosAvulsos();
                }
            } catch (e) {}
        }

async function loadAllData() {
            try {
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

                const rCiclo = await fetch('/api/ciclos/ativo');
                if (rCiclo.ok) cicloAtivo.value = await rCiclo.json();

                const rSess = await fetch('/api/sessoes?limite=100');
                if (rSess.ok) sessoes.value = await rSess.json();

                await carregarResultadosAvulsos();
                await carregarResultadosEncerrados();

                if (cicloAtivo.value) {
                    await carregarDashboardData(cicloAtivo.value.edital_id);
                } else if (editais.value.length > 0) {
                    await carregarDashboardData(editais.value[0].id);
                }

                if (abaAtiva.value === 'ciclo') {
                    renderDonut();
                    scrollToCurrentBlock();
                }
            } catch (e) {
                console.error(e);
            }
        }

const mensagemAlerta = ref('');
        

function mostrarAlerta(msg, tipo = 'sucesso') {
            mensagemAlerta.value = msg;
            tipoAlerta.value = tipo;
            setTimeout(() => { if (mensagemAlerta.value === msg) mensagemAlerta.value = ''; }, 4000);
        }

const tipoAlerta = ref('sucesso');
        
        

const totaisEncerramento = computed(() => {
            let acertosBasicos = 0, errosBasicos = 0, acertosEspec = 0, errosEspec = 0;
            disciplinasEncerramento.value.forEach(d => {
                const a = Number(d.acertos) || 0;
                const e = Number(d.erros) || 0;
                if (d.grupo === 'BASICOS') { acertosBasicos += a; errosBasicos += e; }
                else { acertosEspec += a; errosEspec += e; }
            });
            return { acertosBasicos, errosBasicos, acertosEspec, errosEspec };
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

            let disc = todasDisciplinas.value ? todasDisciplinas.value.find(d => d.id === discId) : null;

            if (!disc && editais.value) {
                for (const ed of editais.value) {
                    if (ed.disciplinas) {
                        const encontrada = ed.disciplinas.find(d => d.id === discId);
                        if (encontrada) {
                            disc = encontrada;
                            break;
                        }
                    }
                }
            }

            if (!disc && blocoAtual.value && blocoAtual.value.disciplina_id === discId) {
                disc = blocoAtual.value.disciplina;
            }

            if (disc && disc.topicos && Array.isArray(disc.topicos)) {
                return disc.topicos;
            }
            return [];
        });

        
        const percentualGlobalEdital = computed(() => {
            if (!cicloAtivo.value || !editais.value) return 0;
            const ed = editais.value.find(e => e.id === cicloAtivo.value.edital_id);
            if (!ed) return 0;
            return getEstatisticasEdital(ed).perc_visto.toFixed(0);
        });

        return { 
            visualizarDashboardEncerrado,
            formatarPercentualBR,
            calcularPercentualRendimento,
            calcularPercentualCorte,
            calcularRendimentoRaioX,
            calcularCorteRaioX,
            calcularComparativoInfo,
            calcularPercentualTotal, 
            abrirModalDetalhesAvulso, 
            fecharModalDetalhesAvulso, 
            avulsoSelecionado, 
            renderGraficosAvulsos, 
            mudarAbaHistorico,
            resultadoAtual, carregandoResultados, formResultado, abrirResultados, carregarResultados, salvarResultado, renderizarGraficosResultados, exportarPDF, resultadosAvulsos, formAvulso, salvarResultadoAvulso, encerrarPreparacaoAvulsa, deletarResultadoAvulso,
            estadoAplicacao, abaAtiva, abaVerticalizado, mensagemAlerta, tipoAlerta, editais, cicloAtivo, sessoes,
            dashboardData, matrizSemanalData, calendarioData, editalVerticalizadoData,
            wizardPasso, wizardDados, wizardEditalGerado, processandoEdital, cicloForm,
            timerSegundos, timerRodando, modalCheckinAberto, formSessao, blocoAtual, todasDisciplinas, topicosDaDisciplina, percentualGlobalEdital,
            verticalizadoAberto, toggleVerticalizado, modalResumoAberto, resumoSessaoAtual,
            toggleTimer, resetTimer, formatarTempoTimer, formatarHorasDecimais, formatarData, formatarDataCurta, badgeTaxaAcertoBg, badgeTextTaxa, getAproveitamentoClasses, getNomeDisciplina, getEstatisticasDisciplina, getEstatisticasEdital, excluirEdital, getTempoEstudadoCicloAtual, getTempoTotalCicloAtual, getTotaisMatrizSemanal, getRankingDisciplinas,
            preencherExemploWizard, processarEditalWizard, salvarPesoDisciplina, finalizarWizard,
            avancarBloco, selecionarBlocoManual, gerarCicloNovoComEdital, abrirModalCheckin, abrirModalCheckinComBloco,
            salvarSessaoEstudo, editarSessao, excluirSessao, excluirTodasSessoes, voltarAoWizard, iniciarApp, abrirDashboard, carregarEditalVerticalizado, abaRaizResultados, abaRegistrar, abaHistorico, rankingRevisoes, quadrantesRaioX, disciplinasEncerramento, totaisEncerramento, insightsRaioX, prepararFormEncerramento, encerrarCicloOficial, resultadosEncerrados, carregarResultadosEncerrados, deletarCicloEncerrado, editarCicloEncerrado, editandoCiclo,
            idEmEdicaoAvulso, editarResultadoAvulso, cancelarEdicaoAvulso, getDataHojeLocal
        };
    }
});
app.config.errorHandler = (err, instance, info) => {
    console.error(err);
    alert('VUE ERROR:\n' + err.message + '\nInfo: ' + info);
};

app.mount('#app');

