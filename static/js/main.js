// Menu Toggle para dispositivos móveis
document.addEventListener('DOMContentLoaded', function() {
    // Adiciona botão de toggle do menu em telas pequenas
    const mainContent = document.querySelector('.main-content');
    const menuButton = document.createElement('button');
    menuButton.className = 'menu-toggle';
    menuButton.innerHTML = '<i class="fas fa-bars"></i>';
    menuButton.style.cssText = `
        position: fixed;
        left: 1rem;
        top: 1rem;
        z-index: 1000;
        padding: 0.5rem;
        background: var(--primary-color);
        color: white;
        border: none;
        border-radius: 0.375rem;
        cursor: pointer;
        display: none;
    `;

    mainContent.insertBefore(menuButton, mainContent.firstChild);

    // Adiciona media query para mostrar/esconder o botão
    const mediaQuery = window.matchMedia('(max-width: 768px)');
    function handleScreenChange(e) {
        menuButton.style.display = e.matches ? 'block' : 'none';
    }
    mediaQuery.addListener(handleScreenChange);
    handleScreenChange(mediaQuery);

    // Toggle do menu
    menuButton.addEventListener('click', function() {
        const sidebar = document.querySelector('.sidebar');
        sidebar.classList.toggle('active');
    });

    // Fecha o menu ao clicar fora
    document.addEventListener('click', function(e) {
        const sidebar = document.querySelector('.sidebar');
        const isClickInside = sidebar.contains(e.target) || menuButton.contains(e.target);
        
        if (!isClickInside && sidebar.classList.contains('active')) {
            sidebar.classList.remove('active');
        }
    });
});

// Formatação de inputs numéricos
document.querySelectorAll('input[type="number"]').forEach(input => {
    input.addEventListener('input', function() {
        if (this.value.includes('.')) {
            const parts = this.value.split('.');
            if (parts[1].length > 2) {
                this.value = parseFloat(this.value).toFixed(2);
            }
        }
    });
});

// Função para mostrar alertas
function showAlert(message, type = 'info') {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.position = 'fixed';
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '9999';
    
    document.body.appendChild(alert);
    
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 300);
    }, 3000);
}

// Confirmação antes de ações importantes
function confirmarAcao(mensagem = 'Tem certeza que deseja realizar esta ação?') {
    return confirm(mensagem);
}

// Formatação de data e hora
function formatarData(data) {
    if (!data) return '-';
    const d = new Date(data);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
}

// Formatação de valor monetário
function formatarMoeda(valor) {
    if (!valor) return 'R$ 0,00';
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

// Proteção contra duplo submit em formulários
document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
        if (this.dataset.submitting) {
            e.preventDefault();
            return;
        }
        
        this.dataset.submitting = 'true';
        
        // Remove a proteção após 5 segundos (caso algo dê errado)
        setTimeout(() => {
            delete this.dataset.submitting;
        }, 5000);
    });
});
