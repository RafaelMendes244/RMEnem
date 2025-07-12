document.addEventListener('DOMContentLoaded', () => {
    const redacaoForm = document.getElementById('redacao-form');
    const temaSelect = document.getElementById('tema-select');
    const temaDisplay = document.getElementById('tema-selecionado-display'); // Pega a nova div
    const redacaoTextarea = document.getElementById('redacao-textarea');
    const randomThemeBtn = document.getElementById('random-theme-btn');
    const submitButton = redacaoForm.querySelector('button[type="submit"]');

    // --- NOVA FUNÇÃO PARA ATUALIZAR O DISPLAY DO TEMA ---
    function updateThemeDisplay() {
        if (temaSelect && temaSelect.value) {
            temaDisplay.textContent = `Tema Ativo: ${temaSelect.value}`;
        } else if (temaDisplay) {
            temaDisplay.textContent = 'Nenhum tema selecionado.';
        }
    }

    // --- LÓGICA DE EVENTOS ---
    if (temaSelect) {
        // Atualiza o display quando a página carrega e quando o usuário muda a seleção
        updateThemeDisplay();
        temaSelect.addEventListener('change', updateThemeDisplay);
    }

    if (randomThemeBtn) {
        randomThemeBtn.addEventListener('click', async () => {
            const originalButtonText = randomThemeBtn.innerHTML;
            randomThemeBtn.disabled = true;
            randomThemeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando...';

            try {
                const response = await fetch('/api/gerar_tema_aleatorio');
                const data = await response.json();
                if (!response.ok) throw new Error(data.tema || 'Não foi possível gerar um tema.');

                const newTheme = data.tema;
                const newOption = document.createElement('option');
                newOption.value = newTheme;
                newOption.textContent = `(Tema Gerado por IA) ${newTheme}`;
                
                temaSelect.prepend(newOption);
                newOption.selected = true;

                // Chama a função para atualizar o display com o novo tema
                updateThemeDisplay();

            } catch (error) {
                alert(`Erro ao gerar tema: ${error.message}`);
            } finally {
                randomThemeBtn.disabled = false;
                randomThemeBtn.innerHTML = originalButtonText;
            }
        });
    }

    if (redacaoForm) {
        redacaoForm.addEventListener('submit', async (e) => {
            e.preventDefault(); 
            const tema = temaSelect.value;
            const texto_redacao = redacaoTextarea.value;

            if (!tema || !tema.trim()) {
                alert('Por favor, selecione ou gere um tema para a redação.');
                return;
            }
            if (texto_redacao.trim().length < 100) {
                alert('Sua redação precisa ter pelo menos 100 caracteres.');
                return;
            }

            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvando...';

            try {
                const response = await fetch('/api/salvar_redacao', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tema, texto_redacao }),
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'Ocorreu um erro desconhecido.');

                alert(result.message);
                window.location.href = '/historico'; 
            } catch (error) {
                alert(`Erro ao salvar redação: ${error.message}`);
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="fas fa-save"></i> Salvar Redação';
            }
        });
    }
});