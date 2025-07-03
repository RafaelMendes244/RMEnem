// static/js/exame.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Referências aos elementos do HTML ---
    const simuladoForm = document.getElementById('simulado-form');
    const anoSelect = document.getElementById('ano-select');
    const disciplinaSelect = document.getElementById('disciplina-select');
    const questoesInput = document.getElementById('questoes-input');
    const gerarBtn = simuladoForm.querySelector('button[type="submit"]');

    const provaSelection = document.getElementById('prova-selection');
    const questoesContainer = document.getElementById('questoes-container');
    const provaTitle = document.getElementById('prova-title');
    const questoesList = document.getElementById('questoes-list');
    const submitBtn = document.getElementById('submit-btn');
    const progressText = document.getElementById('progress-text');
    const progressBar = document.getElementById('progress-bar');
    const timerDisplaySpan = document.querySelector('#timer-display span');
    
    // --- Variáveis de estado ---
    let questionsToSolve = [];
    let userAnswers = {};
    let timerInterval = null;
    let startTime = null;

    // --- URL da SUA API na Vercel ---
    const API_BASE_URL = 'https://enem-api-gules.vercel.app/v1';

    // --- Funções do Timer ---
    const formatTime = (totalSeconds) => {
        if (totalSeconds < 0) totalSeconds = 0;
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    };

    const startTimer = () => {
        startTime = Date.now();
        const DURATION_SECONDS = questionsToSolve.length * 3 * 60;
        let remainingTime = DURATION_SECONDS;
        if (timerDisplaySpan) timerDisplaySpan.textContent = formatTime(remainingTime);
        
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            remainingTime--;
            if (timerDisplaySpan) timerDisplaySpan.textContent = formatTime(remainingTime);
            if (remainingTime <= 0) {
                clearInterval(timerInterval);
                alert('O tempo para o simulado acabou!');
                submitAnswers(true);
            }
        }, 1000);
    };
    
    const stopTimer = () => clearInterval(timerInterval);

    // --- LÓGICA DO SIMULADO ---

    const loadAvailableYears = async () => {
        try {
            const response = await fetch('/api/provas');
            const data = await response.json();
            if (data.error || !Array.isArray(data)) throw new Error('Resposta inválida da API de provas.');

            const years = [...new Set(data.map(prova => prova.year))];
            
            anoSelect.innerHTML = '<option value="">Selecione um ano</option>';
            years.sort((a, b) => b - a)
               .forEach(year => {
                const option = document.createElement('option');
                option.value = year;
                option.textContent = year;
                anoSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Erro ao carregar anos:', error);
            anoSelect.innerHTML = '<option value="">Erro ao carregar</option>';
        }
    };

    const fetchAllQuestionsForYear = async (ano) => {
        const url = `${API_BASE_URL}/exams/${ano}/questions?limit=180`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`A API retornou um erro: ${response.statusText}`);
        }
        const data = await response.json();
        if (data.error) throw new Error(data.error.message);
        return data.questions || [];
    };

    const gerarSimuladoPersonalizado = async (event) => {
        event.preventDefault();
        const ano = anoSelect.value;
        const disciplina = disciplinaSelect.value;
        const numQuestoes = parseInt(questoesInput.value, 10);

        if (!ano) {
            alert('Por favor, selecione um ano para começar.');
            return;
        }
        
        gerarBtn.disabled = true;
        gerarBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Gerando...`;

        provaTitle.textContent = `Buscando questões de ${ano}...`;
        provaSelection.style.display = 'none';
        questoesContainer.style.display = 'block';
        questoesList.innerHTML = `<div class="card text-center"><div class="card-body py-5"><i class="fas fa-spinner fa-spin fa-2x"></i></div></div>`;

        try {
            const todasAsQuestoesDoAno = await fetchAllQuestionsForYear(ano);
            if (todasAsQuestoesDoAno.length === 0) throw new Error(`Nenhuma questão encontrada para o ano de ${ano}.`);
            
            const questoesDaDisciplina = todasAsQuestoesDoAno.filter(q => q.discipline === disciplina);
            if (questoesDaDisciplina.length === 0) throw new Error(`Nenhuma questão de "${disciplina.replace(/-/g, ' ')}" foi encontrada na prova de ${ano}.`);

            let numQuestoesFinal = numQuestoes;
            if (questoesDaDisciplina.length < numQuestoes) {
                alert(`A disciplina selecionada tem apenas ${questoesDaDisciplina.length} questões. O simulado será gerado com este número.`);
                numQuestoesFinal = questoesDaDisciplina.length;
            }
            
            questionsToSolve = shuffleArray(questoesDaDisciplina).slice(0, numQuestoesFinal);
            provaTitle.textContent = `Simulado ENEM ${ano} - ${questionsToSolve.length} questões de ${disciplina.replace(/-/g, ' ')}`;
            renderQuestionsToDom(questionsToSolve);
        } catch (error) {
            console.error('Erro ao gerar simulado:', error);
            alert(`Erro: ${error.message}`);
            provaSelection.style.display = 'block';
            questoesContainer.style.display = 'none';
        } finally {
            gerarBtn.disabled = false;
            gerarBtn.innerHTML = `<i class="fas fa-play"></i> Gerar Simulado`;
        }
    };

    const renderQuestionsToDom = (questions) => {
        questoesList.innerHTML = '';
        userAnswers = {};

        questions.forEach((q, index) => {
            const questionCard = document.createElement('div');
            questionCard.className = 'card question-card';
            
            const cardHeader = document.createElement('div');
            cardHeader.className = 'card-header';
            cardHeader.innerHTML = `<strong>Questão ${index + 1}</strong>`;

            const cardBody = document.createElement('div');
            cardBody.className = 'card-body';

            if (q.context) {
                const contextDiv = document.createElement('div');
                const contextHtml = (q.context).replace(/!\[.*?\]\((.*?)\)/g, '<img src="$1" alt="Imagem da questão" class="img-fluid my-2">');
                contextDiv.innerHTML = marked.parse(contextHtml);
                cardBody.appendChild(contextDiv);
            }

            if (q.files && q.files.length > 0) {
                q.files.forEach(fileUrl => {
                    const img = document.createElement('img');
                    img.src = fileUrl;
                    img.alt = "Imagem da questão";
                    img.className = 'img-fluid my-2';
                    cardBody.appendChild(img);
                });
            }

            if (q.alternativesIntroduction) {
                const introDiv = document.createElement('div');
                introDiv.className = 'mt-3';
                introDiv.innerHTML = marked.parse(q.alternativesIntroduction);
                cardBody.appendChild(introDiv);
            }
            
            const alternativesContainer = document.createElement('div');
            alternativesContainer.className = 'mt-3';

            q.alternatives?.forEach(alt => {
                const label = document.createElement('label');
                label.className = 'alternative';

                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = `question-${index}`;
                radio.value = alt.letter;
                
                // CORREÇÃO DEFINITIVA DO BUG DE CONTAGEM E SELEÇÃO
                radio.addEventListener('change', () => {
                    // Usamos o TÍTULO como ID único, pois o backend já usa ele
                    const questionUniqueId = q.title;
                    userAnswers[questionUniqueId] = radio.value;
                    
                    // Remove o realce de todas as alternativas desta questão
                    alternativesContainer.querySelectorAll('.alternative').forEach(l => l.classList.remove('selected'));
                    
                    // Adiciona o realce na alternativa clicada
                    label.classList.add('selected');

                    // Atualiza a barra de progresso
                    updateProgress();
                });

                const strong = document.createElement('strong');
                strong.textContent = `${alt.letter}) `;

                const divText = document.createElement('div');
                divText.innerHTML = marked.parse(alt.text || '');

                label.appendChild(radio);
                label.appendChild(strong);
                label.appendChild(divText);
                alternativesContainer.appendChild(label);
            });

            cardBody.appendChild(alternativesContainer);
            questionCard.appendChild(cardHeader);
            questionCard.appendChild(cardBody);
            questoesList.appendChild(questionCard);
        });

        updateProgress();
        startTimer();
    };
    
    const shuffleArray = (array) => {
        for (let i = array.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [array[i], array[j]] = [array[j], array[i]];
        }
        return array;
    };

    const updateProgress = () => {
        const answeredCount = Object.keys(userAnswers).length;
        const totalQuestions = questionsToSolve.length;
        const percentage = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;
        
        if(progressText) progressText.textContent = `${answeredCount} de ${totalQuestions} questões`;
        if(progressBar) progressBar.style.width = `${percentage}%`;
        if(submitBtn) submitBtn.disabled = answeredCount !== totalQuestions;
    };

    const submitAnswers = async (timeUp = false) => {
        if (!timeUp && !confirm('Tem certeza que deseja enviar suas respostas?')) return;

        stopTimer();
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Enviando...`;

        const ano = anoSelect.value;
        const duracaoSegundos = Math.floor((Date.now() - startTime) / 1000);

        // CORREÇÃO: Usar os títulos das questões como ID na submissão
        const respostasParaEnviar = {};
        questionsToSolve.forEach(q => {
            if (userAnswers[q.title]) {
                respostasParaEnviar[q.title] = userAnswers[q.title];
            }
        });

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    year: ano,
                    respostas: respostasParaEnviar,
                    duracaoSegundos: duracaoSegundos
                })
            });
            const data = await response.json();
            if (data.success) {
                window.location.href = data.redirect_url;
            } else {
                throw new Error(data.error || 'Erro desconhecido ao enviar respostas.');
            }
        } catch (error) {
            alert(`Erro ao enviar respostas: ${error.message}`);
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<i class="fas fa-paper-plane"></i> Enviar Respostas e Ver Resultado`;
        }
    };
    
    // --- Event Listeners ---
    if (simuladoForm) {
        simuladoForm.addEventListener('submit', gerarSimuladoPersonalizado);
    }
    if (submitBtn) {
        submitBtn.addEventListener('click', () => submitAnswers(false));
    }
    
    // --- Inicialização ---
    if(anoSelect) {
        loadAvailableYears();
    }
});