// static/js/exame.js

document.addEventListener('DOMContentLoaded', () => {
    const provasList = document.getElementById('provas-list');
    const provaSelection = document.getElementById('prova-selection');
    const questoesContainer = document.getElementById('questoes-container');
    const provaTitle = document.getElementById('prova-title');
    const questoesList = document.getElementById('questoes-list');
    const submitBtn = document.getElementById('submit-btn');
    const progressText = document.getElementById('progress-text');
    const progressBar = document.getElementById('progress-bar');
    const timerDisplaySpan = document.querySelector('#timer-display span');

    let allQuestionsForSelectedYear = [];
    let questionsToSolve = [];
    let userAnswers = {};
    let selectedYear = null;
    let startTime = null;
    let timerInterval = null;

    const SIMULADO_DURATION_SECONDS = 45 * 60;
    const NUMBER_OF_QUESTIONS_FOR_SIMULADO = 10;

    const formatTime = (totalSeconds) => {
        if (totalSeconds < 0) totalSeconds = 0;
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    };

    const startTimer = () => {
        let remainingTime = SIMULADO_DURATION_SECONDS;
        timerDisplaySpan.textContent = formatTime(remainingTime);
        timerInterval = setInterval(() => {
            remainingTime--;
            timerDisplaySpan.textContent = formatTime(remainingTime);
            if (remainingTime <= 0) {
                clearInterval(timerInterval);
                alert('O tempo para o simulado acabou! Suas respostas serão enviadas automaticamente.');
                submitAnswers(true);
            }
        }, 1000);
    };

    const stopTimer = () => {
        clearInterval(timerInterval);
        timerInterval = null;
    };

    const loadProvas = async () => {
        try {
            const response = await fetch('/api/provas');
            const data = await response.json();
            if (data.error) throw new Error(data.error);

            if (data.length > 0) {
                provasList.innerHTML = '';
                data.forEach(prova => {
                    const provaCard = document.createElement('div');
                    provaCard.className = 'card prova-card';
                    // AJUSTE NO HTML GERADO PARA PADRONIZAR COM .card-footer
                    provaCard.innerHTML = `
                        <div class="card-body">
                            <h3 class="card-title">${prova.title} (${prova.year})</h3>
                            <p>Disciplinas: ${prova.disciplines.map(d => d.label).join(', ')}</p>
                        </div>
                        <div class="card-footer">
                             <button class="btn btn-primary btn-block select-prova-btn" data-year="${prova.year}">
                                <i class="fas fa-hand-pointer"></i> Selecionar Prova
                            </button>
                        </div>
                    `;
                    provasList.appendChild(provaCard);
                });

                document.querySelectorAll('.select-prova-btn').forEach(button => {
                    button.addEventListener('click', (e) => {
                        selectedYear = e.currentTarget.dataset.year;
                        loadAndPrepareQuestionsForYear(selectedYear);
                    });
                });
            } else {
                provasList.innerHTML = '<p>Nenhuma prova disponível no momento.</p>';
            }
        } catch (error) {
            console.error('Erro ao carregar provas:', error);
            provasList.innerHTML = '<p class="text-danger">Não foi possível carregar as provas. Tente novamente mais tarde.</p>';
        }
    };

    const loadAndPrepareQuestionsForYear = async (year) => {
        provaSelection.style.display = 'none';
        questoesContainer.style.display = 'block';
        provaTitle.textContent = `Simulado ENEM ${year}`;

        try {
            const response = await fetch(`/api/provas/${year}/questoes`);
            const data = await response.json();
            if (data.error) throw new Error(data.error);

            allQuestionsForSelectedYear = data.questions;
            if (!allQuestionsForSelectedYear || allQuestionsForSelectedYear.length < NUMBER_OF_QUESTIONS_FOR_SIMULADO) {
                alert(`Não há questões suficientes para o ano ${year}. Tente outro ano.`);
                provaSelection.style.display = 'block';
                questoesContainer.style.display = 'none';
                return;
            }
            questionsToSolve = shuffleArray(allQuestionsForSelectedYear).slice(0, NUMBER_OF_QUESTIONS_FOR_SIMULADO);
            renderQuestionsToDom(questionsToSolve);
        } catch (error) {
            console.error('Erro ao carregar questões:', error);
            alert('Não foi possível carregar as questões do simulado.');
        }
    };

    const renderQuestionsToDom = (questions) => {
        questoesList.innerHTML = '';
        userAnswers = {};

        questions.forEach((q, index) => {
            const questionCard = document.createElement('div');
            questionCard.className = 'card';
            
            let alternativesHtml = '';
            const letters = ['A', 'B', 'C', 'D', 'E'];
            const questionUniqueId = q.id || q.title || `questao-${q.year}-${q.index}`;

            letters.forEach(letter => {
                const alt = q.alternatives?.find(a => a.letter === letter);
                if (alt?.text) {
                    alternativesHtml += `
                        <label class="alternative">
                            <input type="radio" name="question-${questionUniqueId}" value="${alt.letter}" data-question-id="${questionUniqueId}">
                            <strong>${alt.letter})</strong> <div>${marked.parse(alt.text)}</div>
                        </label>`;
                }
            });

            questionCard.innerHTML = `
                <div class="card-header">
                    <strong>Questão ${index + 1}</strong> - ${q.discipline || 'Área não especificada'}
                </div>
                <div class="card-body">
                    <div>${marked.parse(q.context || '')}</div>
                    <div class="mt-3">${marked.parse(q.alternativesIntroduction || '')}</div>
                    <div class="mt-3">${alternativesHtml}</div>
                </div>`;
            questoesList.appendChild(questionCard);
        });

        document.querySelectorAll('input[type="radio"]').forEach(input => {
            input.addEventListener('change', (e) => {
                userAnswers[e.target.dataset.questionId] = e.target.value;
                document.querySelectorAll(`label.alternative.selected`).forEach(l => l.classList.remove('selected'));
                e.target.closest('label').classList.add('selected');
                updateProgress();
            });
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
        
        progressText.textContent = `${answeredCount} de ${totalQuestions} questões`;
        progressBar.style.width = `${percentage}%`;
        submitBtn.disabled = answeredCount !== totalQuestions;
    };

    const submitAnswers = async (timeUp = false) => {
        if (!timeUp && !confirm('Tem certeza que deseja enviar suas respostas?')) return;

        stopTimer();
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Enviando...`;

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    year: selectedYear,
                    respostas: userAnswers,
                    duracaoSegundos: Math.floor((Date.now() - startTime) / 1000)
                })
            });
            const data = await response.json();
            if (data.success) {
                window.location.href = data.redirect_url;
            } else {
                throw new Error(data.error);
            }
        } catch (error) {
            alert(`Erro ao enviar respostas: ${error.message}`);
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<i class="fas fa-paper-plane"></i> Enviar Respostas e Ver Resultado`;
        }
    };

    submitBtn.addEventListener('click', () => submitAnswers());
    loadProvas();
});