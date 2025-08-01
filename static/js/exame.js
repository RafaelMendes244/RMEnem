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
        const DURATION_SECONDS = questionsToSolve.length * 3 * 60; // 3 minutos por questão
        startTime = Date.now(); // Marca o tempo de início do simulado

        if (timerInterval) clearInterval(timerInterval);

        timerInterval = setInterval(() => {
            const elapsedTime = Math.floor((Date.now() - startTime) / 1000); // Tempo decorrido em segundos
            const remainingTime = DURATION_SECONDS - elapsedTime; // Recalcula o tempo restante

            if (timerDisplaySpan) timerDisplaySpan.textContent = formatTime(remainingTime);

            if (remainingTime <= 0) {
                clearInterval(timerInterval);
                if (timerDisplaySpan) timerDisplaySpan.textContent = "00:00:00"; // Garante que exiba 00:00:00
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
            window.addEventListener('beforeunload', beforeUnloadHandler);
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

    // --- Lógica de confirmação ao sair da página ---
    const beforeUnloadHandler = (event) => {
        event.preventDefault();
        // A maioria dos navegadores modernos ignora o texto retornado e mostra uma mensagem padrão.
        event.returnValue = 'Tem certeza que deseja sair? Seu progresso no simulado será perdido.';
        return event.returnValue;
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

            // Adiciona o contexto e as imagens principais da questão
            if (q.context) {
                const contextHtml = (q.context).replace(/!\[.*?\]\((.*?)\)/g, '<img src="$1" alt="Imagem da questão" class="img-fluid my-2">');
                cardBody.innerHTML += marked.parse(contextHtml);
            }
            if (q.files && q.files.length > 0) {
                q.files.forEach(fileUrl => {
                    cardBody.innerHTML += `<img src="${fileUrl}" alt="Imagem da questão" class="img-fluid my-2">`;
                });
            }
            if (q.alternativesIntroduction) {
                cardBody.innerHTML += `<div class="mt-3">${marked.parse(q.alternativesIntroduction)}</div>`;
            }

            const alternativesContainer = document.createElement('div');
            alternativesContainer.className = 'mt-3';

            // Lógica corrigida para criar as alternativas
            q.alternatives?.forEach(alt => {
                const label = document.createElement('label');
                label.className = 'alternative';

                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = `question-${index}`;
                radio.value = alt.letter;

                radio.addEventListener('change', () => {
                    userAnswers[q.title] = radio.value;
                    questionCard.querySelectorAll('.alternative').forEach(l => l.classList.remove('selected'));
                    label.classList.add('selected');
                    updateProgress();
                });

                const strong = document.createElement('strong');
                strong.textContent = `${alt.letter}) `;

                const contentDiv = document.createElement('div');
                contentDiv.className = 'alternative-content';

                // LÓGICA CORRIGIDA: Trata texto e imagem separadamente
                if (alt.text) {
                    // Usa textContent para segurança e simplicidade, evitando erros de formatação
                    contentDiv.textContent = alt.text;
                }
                if (alt.file) {
                    const img = document.createElement('img');
                    img.src = alt.file;
                    img.alt = `Alternativa ${alt.letter}`;
                    img.className = 'img-fluid-alternative';
                    contentDiv.appendChild(img);
                }

                label.appendChild(radio);
                label.appendChild(strong);
                label.appendChild(contentDiv);
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

        if (progressText) progressText.textContent = `${answeredCount} de ${totalQuestions} questões`;
        if (progressBar) progressBar.style.width = `${percentage}%`;
        if (submitBtn) submitBtn.disabled = answeredCount !== totalQuestions;
    };

    const submitAnswers = async (timeUp = false) => {
        if (!timeUp && !confirm('Tem certeza que deseja enviar suas respostas?')) return;

        stopTimer();
        window.removeEventListener('beforeunload', beforeUnloadHandler);
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Enviando...`;

        const ano = anoSelect.value;
        const duracaoSegundos = Math.floor((Date.now() - startTime) / 1000);

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
    if (anoSelect) {
        loadAvailableYears();
    }
});