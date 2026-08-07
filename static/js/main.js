// Layout responsivo e utilitários do São Geraldo Service
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('appSidebar') || document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const toggle = document.getElementById('menuToggle');

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('active');
        if (overlay) overlay.classList.remove('show');
        document.body.style.overflow = '';
    }

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('active');
        if (overlay) overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    if (toggle && sidebar) {
        toggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (sidebar.classList.contains('active')) closeSidebar();
            else openSidebar();
        });
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeSidebar();
    });

    // Fecha menu ao navegar em mobile
    if (sidebar) {
        sidebar.querySelectorAll('a[href]:not([href^="javascript"])').forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.matchMedia('(max-width: 768px)').matches) closeSidebar();
            });
        });
    }

    window.addEventListener('resize', function() {
        if (window.innerWidth > 768) closeSidebar();
    });
});

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

function confirmarAcao(mensagem = 'Tem certeza que deseja realizar esta ação?') {
    return confirm(mensagem);
}

function formatarData(data) {
    if (!data) return '-';
    const d = new Date(data);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
}

function formatarMoeda(valor) {
    if (!valor) return 'R$ 0,00';
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
        if (this.dataset.submitting) {
            e.preventDefault();
            return;
        }
        this.dataset.submitting = 'true';
        setTimeout(() => {
            delete this.dataset.submitting;
        }, 5000);
    });
});
