function handleCredentialResponse(response) {
    fetch('/auth/google', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: response.credential })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('login-section').style.display = 'none';
        document.getElementById('user-info').style.display = 'block';
        document.getElementById('username').textContent = data.name;
    })
    .catch(error => {
        console.error('Erro:', error);
        alert('Falha no login');
    });
}