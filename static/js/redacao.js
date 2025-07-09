document.addEventListener('DOMContentLoaded', () => {
    const redacaoForm = document.getElementById('redacao-form');

    if (redacaoForm) {
        redacaoForm.addEventListener('submit', async (e) => {
            e.preventDefault(); // Impede o envio tradicional do formulário que recarrega a página

            const temaSelect = document.getElementById('tema-select');
            const redacaoTextarea = document.getElementById('redacao-textarea');
            const submitButton = redacaoForm.querySelector('button[type="submit"]');

            const tema = temaSelect.value;
            const texto_redacao = redacaoTextarea.value;

            // Validação simples no front-end
            if (texto_redacao.trim().length < 100) {
                alert('Sua redação parece muito curta. Escreva pelo menos 100 caracteres antes de salvar.');
                return;
            }

            // Desativa o botão e mostra feedback de carregamento para o usuário
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvando...';

            try {
                // Envia os dados para a nossa nova rota no Flask
                const response = await fetch('/api/salvar_redacao', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ tema, texto_redacao }),
                });

                const result = await response.json();

                if (response.ok) {
                    alert(result.message); // Exibe "Redação salva com sucesso!"
                    // Redireciona para a página de histórico para o usuário ver seu progresso
                    window.location.href = '/historico'; 
                } else {
                    // Mostra o erro que veio do servidor
                    throw new Error(result.error || 'Ocorreu um erro desconhecido.');
                }
            } catch (error) {
                console.error('Erro:', error);
                alert(`Erro ao salvar redação: ${error.message}`);
            } finally {
                // Reativa o botão em caso de sucesso ou erro, caso o usuário não seja redirecionado
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="fas fa-save"></i> Salvar Redação';
            }
        });
    }
});