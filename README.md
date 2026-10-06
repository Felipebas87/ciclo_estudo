# Sistema de Gestão de Ciclo de Estudos para Concursos Públicos

Aplicação web completa para planejamento, execução e monitoramento de estudos para concursos públicos, baseada na ingestão de editais verticalizados, geração automática de ciclos com intercalação cognitiva e acompanhamento analítico de desempenho com resolução de questões.

---

## 🚀 Como Executar

Como o Python 3.13 já está instalado em seu computador, basta executar:

```powershell
python run.py
```

Em seguida, abra o navegador e acesse:
- **Interface Web:** [http://localhost:8000](http://localhost:8000)
- **Documentação Interativa da API (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📋 Funcionalidades Implementadas

1. **RF01 - Ingestão de Edital Verticalizado**:
   - Upload de planilhas **CSV** e **Excel (.xlsx)** com detecção automática de delimitadores e mapeamento inteligente de colunas (`Disciplina`, `Tópico`, `Categoria`, `Peso`, `Dificuldade`).
   - Botão para carregar um edital de exemplo completo com 1 clique (TSE Unificado / Analista de TI).
   - Cadastro manual de editais, matérias e tópicos.

2. **RF02 - Configuração de Pesos e Relevância**:
   - Ajuste em tempo real do **Peso da Prova** (ex: 1.0 a 5.0) por matéria.
   - Ajuste da **Relevância/Dificuldade Pessoal** de 1 a 5 estrelas.
   - Classificação cognitiva da disciplina: **Exatas/Lógica/TI** ou **Teórica/Direito**.

3. **RF03 - Geração Automática do Ciclo com Intercalação Cognitiva**:
   - Cálculo do **Fator de Importância**:
     $$F_i = \text{Peso} \times \frac{\text{Dificuldade}}{3} \times (1 + \ln(1 + \text{Qtd de Tópicos}))$$
   - Distribuição proporcional de horas em blocos discretos (ex: blocos de 50, 60, 90 ou 120 min).
   - **Intercalação Cognitiva**: O algoritmo alterna automaticamente entre matérias teóricas e exatas/lógicas, evitando matérias repetidas em sequência para combater a fadiga mental e maximizar a retenção.
   - Esteira circular rotativa com ponteiro em tempo real e opção de avançar ou pular matérias.

4. **RF04 - Diário de Estudos (Check-in) & Cronômetro**:
   - Cronômetro integrado na tela do ciclo (iniciar, pausar, reiniciar) que preenche automaticamente o tempo estudado no check-in.
   - Registro de sessões de estudo vinculadas aos blocos do ciclo ou avulsas por data.

5. **RF05 - Módulo de Resolução de Questões**:
   - Registro granular de: **Questões Resolvidas**, **Acertos** e **Erros**.
   - Cálculo automático e instantâneo do percentual de aproveitamento (%) na tela.

6. **RF06 - Dashboard de Desempenho Analítico**:
   - Cards de KPIs: Total de Horas Estudadas, Total de Sessões, Questões Feitas e Taxa Global de Acerto.
   - **Gráfico de Rendimento por Disciplina** (Chart.js): Barras coloridas por aproveitamento (verde >= 80%, amarelo 60-79%, vermelho < 60%).
   - **Gráfico de Evolução Histórica (Curva de Aprendizado)**: Linha de tendência ao longo dos dias de estudo.
   - **Gráfico de Distribuição do Tempo**: Rosca/Donut com a divisão de horas entre as disciplinas.
   - Tabela de desempenho isolado por matéria.

---

## 📁 Estrutura do Projeto

```
app estudo/
├── app/
│   ├── config.py                 # Configurações de caminhos e banco de dados
│   ├── database.py               # Sessão do SQLAlchemy (SQLite local ou PostgreSQL)
│   ├── main.py                   # Inicialização FastAPI, CORS e rotas estáticas
│   ├── models/                   # Modelos relacionais ORM (Edital, Disciplina, Topico, Ciclo, Sessao)
│   ├── schemas/                  # Schemas Pydantic para validação das APIs
│   ├── services/                 # Algoritmo de ciclo, parser de planilhas e métricas
│   ├── routers/                  # Endpoints REST (editais, ciclos, sessoes, dashboard)
│   └── static/                   # SPA Frontend (HTML5, Tailwind CSS, Vue 3, Chart.js)
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
├── data/                         # Banco de dados local gerado automaticamente (study_cycle.db)
├── sample_data/                  # Edital de exemplo pronto para testes (edital_exemplo.csv)
├── tests/                        # Testes automatizados (pytest)
│   ├── test_ciclo_service.py
│   └── test_api.py
├── requirements.txt              # Dependências instaladas
├── run.py                        # Execução rápida do servidor
└── README.md
```

---

## 🧪 Como Rodar os Testes Automatizados

```powershell
python -m pytest -v
```
