// Toggle submenu visibility on click for sidebar submenu items
document.addEventListener('DOMContentLoaded', function() {
    const submenuItems = document.querySelectorAll('.sidebar-menu .submenu > a');

    submenuItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const parentLi = this.parentElement;

            // Close other open submenus
            document.querySelectorAll('.sidebar-menu .submenu.open').forEach(openSubmenu => {
                if (openSubmenu !== parentLi) {
                    openSubmenu.classList.remove('open');
                }
            });

            // Toggle the clicked submenu
            parentLi.classList.toggle('open');
        });
    });
});
