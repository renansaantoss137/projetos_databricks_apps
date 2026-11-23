(function () {
  'use strict';

  var errorDiv  = document.getElementById('errorMsg');
  var loginForm = document.getElementById('loginForm');

  function showError(msg) {
    if (errorDiv) {
      errorDiv.textContent = msg;
      errorDiv.style.display = 'block';
    } else {
      alert(msg);
    }
  }

  function hideError() {
    if (errorDiv) {
      errorDiv.style.display = 'none';
      errorDiv.textContent = '';
    }
  }

  // Verifica parâmetro ?error= na URL
  (function () {
    var params = new URLSearchParams(window.location.search);
    var errMsg = params.get('error');
    if (errMsg) showError(errMsg);
  })();

  if (!loginForm) return;

  loginForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    hideError();

    var emailInput = document.getElementById('email');
    var email = emailInput ? emailInput.value.trim().toLowerCase() : '';

    if (!email) {
      showError('Por favor, informe seu e-mail corporativo.');
      return;
    }

    // Validação Básica de Domínio @grupobimbo.com
    var emailRegex = /^[a-zA-Z0-9._%+-]+@grupobimbo\.com$/i;
    if (!emailRegex.test(email)) {
      showError('Formato de e-mail inválido. Utilize um e-mail corporativo do domínio @grupobimbo.com.');
      return;
    }

    try {
      var response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      });

      var data = await response.json();

      if (response.status === 403) {
        showError('Acesso não configurado');
        return;
      }

      if (!response.ok) {
        showError(data.error || 'Erro ao realizar login. Verifique seu e-mail.');
        return;
      }

      if (data.success && data.user) {
        sessionStorage.setItem('logged_user', JSON.stringify(data.user));
        window.location.href = '/dashboard.html';
      } else {
        showError('Resposta inesperada do servidor.');
      }
    } catch (err) {
      console.error('Erro de conexão ao efetuar login:', err);
      showError('Erro de conexão com o servidor. Tente novamente.');
    }
  });

})();
