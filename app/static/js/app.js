const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
    setup() {
        // Estado Global
        const estadoAplicacao = ref('app'); // 'wizard' ou 'app'
        const abaAtiva = ref('ciclo');
        const abaVerticalizado = ref('basicos'); // 'basicos', 'especificos'
        const mensagemAlerta = ref('');
        const tipoAlerta = ref('sucesso');
        
        // Dados API
        const editais = ref([]);
        const cicloAtivo = ref(null);
        const sessoes = ref([]);
        
        // Dados de Relatório
        const dashboardData = ref({});
        const matrizSemanalData = ref({});
        const calendarioData = ref({});
        const editalVerticalizadoData = ref({});
        
        // Wizard Form
        const wizardPasso = ref(0);
        const wizardDados = ref({ nome: '', texto_basicos: '', texto_especificos: '' });
        const wizardEditalGerado = ref(null);
        const processandoEdital = ref(false);
        const cicloForm = ref({ carga_horaria_semanal: 20, duracao_bloco_minutos: 60 });

        // Cronometro
        const timerSegundos = ref(0);
        const timerRodando = ref(false);
        let timerInterval = null;

        // Modal Checkin
        const modalCheckinAberto = ref(false);
        const formSessao = ref({
            disciplina_id: null, bloco_ciclo_id: null, topico_id: null,
            data: new Date().toISOString().split('T')[0],
            tempo_estudado_minutos: 60, qtd_questoes_total: 0,
            qtd_acertos: 0, qtd_erros: 0, observacoes: '', avancar_ciclo: true,
            is_revisao_anki: false
        });

        const modalResumoAberto = ref(false);
        const resumoSessaoAtual = ref(null);

        // Charts
        let chartDiscInstance = null;
        let chartEvolucaoInstance = null;
        let chartCicloDonutInstance = null;

        // Computed
        const blocoAtual = computed(() => {
            if (!cicloAtivo.value || !cicloAtivo.value.blocos || cicloAtivo.value.blocos.length === 0) return null;
            return cicloAtivo.value.blocos[cicloAtivo.value.bloco_atual_index || 0];
        });

        const todasDisciplinas = computed(() => {
            const list = [];
            editais.value.forEach(e => {
                if (e.disciplinas) e.disciplinas.forEach(d => {
                    if (d.nome !== "REVISÃO ANKI") list.push(d);
                });
            });
            return list;
        });

        const topicosDaDisciplina = computed(() => {
            if (!formSessao.value.disciplina_id) return [];
            const d = todasDisciplinas.value.find(x => x.id === formSessao.value.disciplina_id);
            return d && d.topicos ? d.topicos : [];
        });

        const percentualGlobalEdital = computed(() => {
            if (!editais.value || editais.value.length === 0) return 0;
            const ed = editais.value[0]; // Edital atual
            if (!ed || !ed.disciplinas) return 0;

            let totalTopicos = 0;
            let topicosVistos = new Set();

            ed.disciplinas.forEach(d => {
                if (d.categoria !== 'REVISAO_ANKI' && d.topicos) {
                    totalTopicos += d.topicos.length;
                    const sessoesDisc = sessoes.value.filter(s => s.disciplina_id === d.id && s.topico_id !== null);
                    sessoesDisc.forEach(s => topicosVistos.add(s.topico_id));
                }
            });

            if (totalTopicos === 0) return 0;
            return (topicosVistos.size / totalTopicos * 100).toFixed(1);
        });

        // Helpers
        function mostrarAlerta(msg, tipo = 'sucesso') {
            mensagemAlerta.value = msg;
            tipoAlerta.value = tipo;
            setTimeout(() => { if (mensagemAlerta.value === msg) mensagemAlerta.value = ''; }, 4000);
        }

        function formatarTempoTimer(s) {
            const hrs = Math.floor(s / 3600);
            const mins = Math.floor((s % 3600) / 60);
            const secs = s % 60;
            return `${String(hrs).padStart(2,'0')}:${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
        }

        
        function formatarHorasDecimais(h) {
            if(!h) return '0h00m';
            if (typeof h === 'string' && h.includes('h')) return h;
            const val = parseFloat(h);
            const horas = Math.floor(val);
            const minutos = Math.round((val - horas) * 60);
            return `${horas}h${minutos.toString().padStart(2, '0')}m`;
        }

        function formatarData(isoStr) {
            if (!isoStr) return '';
            const p = isoStr.split('-');
            if (p.length >= 3) return `${p[2].substring(0,2)}/${p[1]}`;
            return isoStr;
        }

        function badgeTaxaAcertoBg(perc) {
            if (perc >= 80) return 'bg-emerald-100 text-emerald-800';
            if (perc >= 60) return 'bg-amber-100 text-amber-800';
            return 'bg-rose-100 text-rose-800';
        }

        function badgeTextTaxa(perc) {
            if (perc >= 80) return 'text-emerald-600';
            if (perc >= 60) return 'text-amber-500';
            return 'text-rose-500';
        }

        function getAproveitamentoClasses(perc) {
            if (perc >= 81) return { text: 'from-blue-400 to-blue-200', border: 'border-blue-500/20 hover:border-blue-500/50', bg: 'bg-blue-500/5' };
            if (perc >= 71) return { text: 'from-emerald-400 to-emerald-200', border: 'border-emerald-500/20 hover:border-emerald-500/50', bg: 'bg-emerald-500/5' };
            if (perc >= 60) return { text: 'from-amber-400 to-amber-200', border: 'border-amber-500/20 hover:border-amber-500/50', bg: 'bg-amber-500/5' };
            return { text: 'from-rose-400 to-rose-200', border: 'border-rose-500/20 hover:border-rose-500/50', bg: 'bg-rose-500/5' };
        }

        function getNomeDisciplina(id) {
            const d = todasDisciplinas.value.find(x => x.id === id);
            return d ? d.nome : `ID: ${id}`;
        }

        // Api Calls - Lifecycle
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

                if (abaAtiva.value === 'ciclo') renderDonut();

                if (cicloAtivo.value) {
                    await carregarDashboardData(cicloAtivo.value.edital_id);
                } else if (editais.value.length > 0) {
                    await carregarDashboardData(editais.value[0].id);
                }
            } catch (e) {
                console.error(e);
            }
        }

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

        function abrirDashboard() {
            abaAtiva.value = 'dashboard';
            setTimeout(renderCharts, 100);
        }
        
        function carregarEditalVerticalizado(id) {
            carregarDashboardData(id);
            mostrarAlerta("Relatório verticalizado atualizado!");
        }

        const verticalizadoAberto = ref({});
        function toggleVerticalizado(id) {
            verticalizadoAberto.value[id] = !verticalizadoAberto.value[id];
        }

        // Timer actions
        function toggleTimer() {
            if (timerRodando.value) {
                clearInterval(timerInterval);
                timerRodando.value = false;
            } else {
                timerRodando.value = true;
                timerInterval = setInterval(() => { timerSegundos.value++; }, 1000);
            }
        }
        function resetTimer() {
            if (timerInterval) clearInterval(timerInterval);
            timerRodando.value = false;
            timerSegundos.value = 0;
        }

        // Wizard Flow
        function preencherExemploWizard() {
            wizardDados.value.nome = "TSE Unificado 2024 - Analista TI";
            wizardDados.value.texto_basicos = "LÍNGUA PORTUGUESA: 1 Compreensão de texto. 2 Ortografia.\\nDIREITO CONSTITUCIONAL: 1 Organização dos poderes.";
            wizardDados.value.texto_especificos = "TECNOLOGIA DA INFORMAÇÃO: 1 Banco de Dados Relacional. 2 Engenharia de Software.\\nRACIOCÍNIO LÓGICO: 1 Probabilidade.";
        }

        async function processarEditalWizard() {
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
                    const err = await res.json();
                    mostrarAlerta(err.detail || "Falha ao processar edital", "erro");
                }
            } catch(e) {
                mostrarAlerta("Erro de rede: " + e.message, "erro");
            } finally {
                processandoEdital.value = false;
            }
        }

        async function salvarPesoDisciplina(disc) {
            try {
                await fetch(`/api/editais/disciplinas/${disc.id}`, {
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
            } catch(e) {}
        }

        async function finalizarWizard() {
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

        function voltarAoWizard() {
            estadoAplicacao.value = 'wizard';
            wizardPasso.value = 0;
        }

        function iniciarApp() {
            estadoAplicacao.value = 'app';
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
            if (!cicloAtivo.value) return;
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
            if (!cicloAtivo.value) return;
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
                    method: 'POST',
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
                return { qtd: d.total_questoes, perc: d.percentual_acerto, perc_vistos };
            }
            return { qtd: 0, perc: 0, perc_vistos };
        }

        function getEstatisticasEdital(ed) {
            let horas = 0;
            let topicos_total = 0;
            const topicosVistos = new Set();
            
            // Horas estudadas: soma do tempo de todas as sessoes desse edital
            const discIds = ed.disciplinas.map(d => d.id);
            const sessoesEdital = sessoes.value.filter(s => discIds.includes(s.disciplina_id));
            horas = sessoesEdital.reduce((acc, s) => acc + s.tempo_estudado_minutos, 0) / 60;
            
            // Topicos vistos vs totais
            ed.disciplinas.forEach(d => {
                if (d.categoria !== 'REVISAO_ANKI' && d.topicos) {
                    topicos_total += d.topicos.length;
                }
            });
            
            sessoesEdital.forEach(s => {
                if (s.topico_id !== null) topicosVistos.add(s.topico_id);
            });
            
            const perc_visto = topicos_total > 0 ? (topicosVistos.size / topicos_total) * 100 : 0;
            return { horas: formatarHorasDecimais(horas), topicos_vistos: topicosVistos.size, topicos_total, perc_visto };
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
            formSessao.value.disciplina_id = (blocoAtual.value && blocoAtual.value.disciplina_id) ? blocoAtual.value.disciplina_id : todasDisciplinas.value[0]?.id;
            formSessao.value.bloco_ciclo_id = null;
            formSessao.value.topico_id = null;
            formSessao.value.tempo_estudado_minutos = 60;
            formSessao.value.qtd_questoes_total = 0;
            formSessao.value.qtd_acertos = 0;
            formSessao.value.qtd_erros = 0;
            formSessao.value.is_revisao_anki = false;
            modalCheckinAberto.value = true;
        }

        function abrirModalCheckinComBloco(b) {
            const isRevisao = b.disciplina.categoria === 'REVISAO_ANKI';
            formSessao.value.is_revisao_anki = isRevisao;
            formSessao.value.disciplina_id = isRevisao ? todasDisciplinas.value[0]?.id : b.disciplina_id;
            formSessao.value.bloco_ciclo_id = b.id;
            formSessao.value.topico_id = "";
            formSessao.value.tempo_estudado_minutos = timerSegundos.value > 0 ? Math.max(1, Math.round(timerSegundos.value / 60)) : 60;
            formSessao.value.qtd_questoes_total = 0;
            formSessao.value.qtd_acertos = 0;
            formSessao.value.qtd_erros = 0;
            modalCheckinAberto.value = true;
        }

        async function salvarSessaoEstudo() {
            try {
                if (!formSessao.value.is_revisao_anki && !formSessao.value.topico_id && topicosDaDisciplina.value.length > 0) {
                    mostrarAlerta('Você precisa selecionar o Tópico Estudado para contabilizar o rendimento do edital.', 'erro');
                    return;
                }

                if (!formSessao.value.is_revisao_anki && formSessao.value.qtd_acertos === 0 && formSessao.value.qtd_erros === 0) {
                    mostrarAlerta('Você deve registrar pelo menos 1 acerto ou erro nas questões.', 'erro');
                    return;
                }

                const hoje = new Date().toISOString().split('T')[0];
                if (formSessao.value.data > hoje) {
                    mostrarAlerta('Não é possível registrar uma sessão em uma data futura.', 'erro');
                    return;
                }

                let total_q = formSessao.value.qtd_questoes_total;
                let a = formSessao.value.qtd_acertos;
                let e = formSessao.value.qtd_erros;
                if(total_q === 0 && (a > 0 || e > 0)) formSessao.value.qtd_questoes_total = a + e;
                
                const oldVoltas = cicloAtivo.value ? cicloAtivo.value.voltas_completas : 0;
                let oldPerc = 0;
                if (cicloAtivo.value) {
                    const ed = editais.value.find(e => e.id === cicloAtivo.value.edital_id);
                    if (ed) oldPerc = getEstatisticasEdital(ed).perc_visto;
                }
                
                const method = formSessao.value.id ? 'PUT' : 'POST';
                const url = formSessao.value.id ? `/api/sessoes/${formSessao.value.id}` : '/api/sessoes';

                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formSessao.value)
                });
                if(res.ok) {
                    modalCheckinAberto.value = false;
                    resetTimer();
                    await loadAllData();
                    
                    let newPerc = 0;
                    if (cicloAtivo.value) {
                        const ed = editais.value.find(e => e.id === cicloAtivo.value.edital_id);
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
                        mostrarAlerta("Sessão registrada!");
                    }
                } else {
                    mostrarAlerta("Erro", "erro");
                }
            } catch(e){}
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
                    const nome = b.disciplina.nome;
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
                            if (!cicloAtivo.value) return;
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

        Vue.watch(abaAtiva, (newVal) => {
            if (newVal === 'ciclo') {
                renderDonut();
                scrollToCurrentBlock();
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
                if (!cicloAtivo.value) return;
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
            }
        });

        onMounted(() => {
            loadAllData().then(() => {
                if (abaAtiva.value === 'ciclo') scrollToCurrentBlock();
            });
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
                return { ...t, percentual: perc };
            });

            const percGeral = totalGeralResolvidas > 0 ? ((totalGeralCertas / totalGeralResolvidas) * 100).toFixed(1) : 0;

            return {
                semanas: semanasProcessadas,
                totalGeral: { certas: totalGeralCertas, resolvidas: totalGeralResolvidas, percentual: percGeral }
            };
        }

        function getRankingDisciplinas() {
            if (!dashboardData.value || !dashboardData.value.rendimento_disciplinas) {
                return { melhores: [], piores: [] };
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
            
            return { piores, melhores };
        }

        return {
            estadoAplicacao, abaAtiva, abaVerticalizado, mensagemAlerta, tipoAlerta, editais, cicloAtivo, sessoes,
            dashboardData, matrizSemanalData, calendarioData, editalVerticalizadoData,
            wizardPasso, wizardDados, wizardEditalGerado, processandoEdital, cicloForm,
            timerSegundos, timerRodando, modalCheckinAberto, formSessao, blocoAtual, todasDisciplinas, topicosDaDisciplina, percentualGlobalEdital,
            verticalizadoAberto, toggleVerticalizado, modalResumoAberto, resumoSessaoAtual,
            toggleTimer, resetTimer, formatarTempoTimer, formatarHorasDecimais, formatarData, badgeTaxaAcertoBg, badgeTextTaxa, getAproveitamentoClasses, getNomeDisciplina, getEstatisticasDisciplina, getEstatisticasEdital, excluirEdital, getTempoEstudadoCicloAtual, getTempoTotalCicloAtual, getTotaisMatrizSemanal, getRankingDisciplinas,
            preencherExemploWizard, processarEditalWizard, salvarPesoDisciplina, finalizarWizard,
            avancarBloco, selecionarBlocoManual, gerarCicloNovoComEdital, abrirModalCheckin, abrirModalCheckinComBloco,
            salvarSessaoEstudo, editarSessao, excluirSessao, excluirTodasSessoes, voltarAoWizard, iniciarApp, abrirDashboard, carregarEditalVerticalizado
        };
    }
}).mount('#app');
