// Layout responsivo e utilitários do São Geraldo Service
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('appSidebar') || document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const toggle = document.getElementById('menuToggle');
    const COLLAPSE_KEY = document.body.dataset.sidebarCollapse || '';
    const collapseEnabled = !!COLLAPSE_KEY;
    const mqMobile = window.matchMedia('(max-width: 768px)');

    function isMobile() {
        return mqMobile.matches;
    }

    function updateToggleAria() {
        if (!toggle) return;
        if (isMobile()) {
            const open = !!(sidebar && sidebar.classList.contains('active'));
            toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            return;
        }
        if (!collapseEnabled) return;
        const collapsed = document.body.classList.contains('sidebar-collapsed');
        toggle.setAttribute('aria-label', collapsed ? 'Expandir menu' : 'Recuar menu');
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    function setCollapsed(collapsed) {
        document.body.classList.toggle('sidebar-collapsed', !!collapsed);
        try {
            localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (err) { /* ignore */ }
        updateToggleAria();
    }

    if (collapseEnabled) {
        try {
            if (localStorage.getItem(COLLAPSE_KEY) === '1') setCollapsed(true);
            else setCollapsed(false);
        } catch (err) {
            setCollapsed(false);
        }
    } else {
        updateToggleAria();
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('active');
        if (overlay) overlay.classList.remove('show');
        document.body.style.overflow = '';
        updateToggleAria();
    }

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('active');
        if (overlay) overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
        updateToggleAria();
    }

    if (toggle && sidebar) {
        toggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (isMobile()) {
                if (sidebar.classList.contains('active')) closeSidebar();
                else openSidebar();
            } else if (collapseEnabled) {
                setCollapsed(!document.body.classList.contains('sidebar-collapsed'));
            }
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
                if (isMobile()) closeSidebar();
            });
        });
    }

    window.addEventListener('resize', function() {
        if (!isMobile()) closeSidebar();
        updateToggleAria();
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
