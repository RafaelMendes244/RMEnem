// /static/js/redacao.js

document.addEventListener('DOMContentLoaded', () => {
    const redacaoForm = document.getElementById('redacao-form');
    const temaSelect = document.getElementById('tema-select');
    const redacaoTextarea = document.getElementById('redacao-textarea');
    const randomThemeBtn = document.getElementById('random-theme-btn');
    const submitButton = redacaoForm.querySelector('button[type="submit"]');

    // --- Funcionalidade do botão de Gerar Tema Aleatório com IA ---
    if (randomThemeBtn && temaSelect) {
        randomThemeBtn.addEventListener('click', async () => {
            const originalButtonText = randomThemeBtn.innerHTML;
            randomThemeBtn.disabled = true;
            randomThemeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando...';

            try {
                const response = await fetch('/api/gerar_tema_aleatorio');
                const data = await response.json();
                
                if (!response.ok) throw new Error(data.tema || 'Não foi possível gerar um tema.');

                const newTheme = data.tema;
                
                // Cria um novo elemento <option>
                const newOption = document.createElement('option');
                newOption.value = newTheme; // O valor é o tema completo
                newOption.textContent = `(Tema Gerado por IA) ${newTheme}`; // O texto que o usuário vê
                
                // Adiciona a nova opção no topo da lista
                temaSelect.prepend(newOption);
                
                // Define a nova opção como a selecionada
                newOption.selected = true;

            } catch (error) {
                console.error("Erro ao gerar tema:", error);
                alert(`Erro ao gerar tema: ${error.message}`);
            } finally {
                randomThemeBtn.disabled = false;
                randomThemeBtn.innerHTML = originalButtonText;
            }
        });
    }

    // --- Funcionalidade do formulário para Salvar a Redação ---
    if (redacaoForm) {
        redacaoForm.addEventListener('submit', async (e) => {
            e.preventDefault(); 
            const tema = temaSelect.value;
            const texto_redacao = redacaoTextarea.value;

            if (!tema.trim()) {
                alert('Por favor, selecione ou gere um tema para a redação.');
                return;
            }
            if (texto_redacao.trim().length < 100) {
                alert('Sua redação parece muito curta. Escreva pelo menos 100 caracteres antes de salvar.');
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
                console.error('Erro ao salvar:', error);
                alert(`Erro ao salvar redação: ${error.message}`);
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="fas fa-save"></i> Salvar Redação';
            }
        });
    }
});