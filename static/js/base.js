/* =========================================================
   THEME TOGGLE + SIDEBAR
   ========================================================= */
(function () {
    var root = document.documentElement;
    var icon = document.getElementById('themeIcon');

    function syncIcon() {
        if (!icon) return;
        var dark = root.getAttribute('data-theme') === 'dark';
        icon.className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    }
    syncIcon();

    var themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            root.setAttribute('data-bs-theme', next);
            try { localStorage.setItem('cm-theme', next); } catch (e) {}
            syncIcon();
        });
    }

    function setSidebar(open) { 
        document.body.classList.toggle('sidebar-open', open); 
    }
    
    var sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function () {
            setSidebar(!document.body.classList.contains('sidebar-open'));
        });
    }
    
    var sidebarBackdrop = document.getElementById('sidebarBackdrop');
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', function () { 
            setSidebar(false); 
        });
    }
    
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') setSidebar(false);
    });
})();


/* =========================================================
   SCROLL POSITION PRESERVATION (Main + Sidebar)
   ========================================================= */
(function () {
    var key = 'scrollPos:' + window.location.pathname + window.location.search;
    var saveTimer = null;

    // Save main window scroll
    window.addEventListener('scroll', function () {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
            try { sessionStorage.setItem(key, String(window.scrollY)); } catch (e) {}
        }, 150);
    }, { passive: true });

    window.addEventListener('pagehide', function () {
        try { sessionStorage.setItem(key, String(window.scrollY)); } catch (e) {}
    });

    // Restore main window scroll on load
    window.addEventListener('load', function () {
        if (window.location.hash) return;
        try {
            var saved = sessionStorage.getItem(key);
            if (saved && parseInt(saved) > 0) {
                requestAnimationFrame(function () {
                    window.scrollTo(0, parseInt(saved));
                });
            }
        } catch (e) {}
    });

    // Clear main scroll memory if clicking a new sidebar link
    try {
        var navEntries = performance.getEntriesByType('navigation');
        if (navEntries.length && navEntries[0].type !== 'back_forward') {
            document.querySelectorAll('.sidebar a, .sidebar form button').forEach(function (el) {
                el.addEventListener('click', function () {
                    try { sessionStorage.removeItem(key); } catch (e) {}
                });
            });
        }
    } catch (e) {}

    // Sidebar Scroll Preservation
    var nav = document.querySelector('.sidebar-nav');
    if (nav) {
        try {
            var pos = sessionStorage.getItem('sidebarScrollPos');
            if (pos) nav.scrollTop = parseInt(pos, 10) || 0;
        } catch (e) {}

        nav.addEventListener('scroll', function () {
            clearTimeout(saveTimer);
            saveTimer = setTimeout(function () {
                try { sessionStorage.setItem('sidebarScrollPos', String(nav.scrollTop)); } catch (e) {}
            }, 100);
        }, { passive: true });

        nav.addEventListener('click', function (e) {
            if (e.target.closest('a, button')) {
                try { sessionStorage.setItem('sidebarScrollPos', String(nav.scrollTop)); } catch (e) {}
            }
        });
    }
})();


/* =========================================================
   FORM BUTTON LOADING STATES
   ========================================================= */
document.addEventListener('submit', function (e) {
    var form = e.target;
    // Skip GET forms (search/filter) or forms with .no-spinner class
    if (form.method.toLowerCase() === 'get' || form.classList.contains('no-spinner')) return;

    var submitBtn = e.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
    
    if (submitBtn && !submitBtn.disabled) {
        setTimeout(function() {
            submitBtn.disabled = true;
            var text = submitBtn.getAttribute('data-loading-text') || 'Please wait...';
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="margin-right: 6px;"></span> ' + text;
            submitBtn.style.opacity = '0.75';
            submitBtn.style.cursor = 'not-allowed';
        }, 10);
    }
});

// Reset buttons if the user hits the "Back" button in the browser
window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
        document.querySelectorAll('button[disabled]').forEach(function(btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        });
    }
});


/* =========================================================
   AUTO-DISMISS TOASTS
   ========================================================= */
document.addEventListener('DOMContentLoaded', function() {
    var toasts = document.querySelectorAll('.toast-message');
    toasts.forEach(function(toast) {
        // Errors stay for 8 seconds, success for 4 seconds
        var isError = toast.style.borderColor.includes('var(--danger)') || toast.classList.contains('alert-danger');
        var timeout = isError ? 8000 : 4000;

        setTimeout(function() {
            toast.classList.remove('show');
            setTimeout(function() { toast.remove(); }, 150);
        }, timeout);
    });
});


/* =========================================================
   LIVE SERVER CLOCK FOR FOOTER
   ========================================================= */
document.addEventListener('DOMContentLoaded', function() {
    var clockEl = document.getElementById('footerClock');
    if (!clockEl) return;

    function updateClock() {
        var now = new Date();
            var timeString = now.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit', 
                hour12: true 
            });
        clockEl.textContent = timeString;
    }

    updateClock();
    setInterval(updateClock, 1000);
});


/* =========================================================
   ACCORDION SIDEBAR NAVIGATION (Click-Only)
   ========================================================= */
document.addEventListener('DOMContentLoaded', function() {
    var groups = document.querySelectorAll('.nav-group');
    
    // 1. Auto-open the group that has an active link on page load
    groups.forEach(function(group) {
        var hasActiveLink = group.querySelector('.nav-item-link.active');
        if (hasActiveLink) {
            group.classList.add('open');
        }
    });

    // 2. Handle clicking the group buttons
    document.querySelectorAll('.nav-group-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var currentGroup = this.closest('.nav-group');
            var isOpen = currentGroup.classList.contains('open');

            // Close all other groups
            groups.forEach(function(g) {
                g.classList.remove('open');
            });

            // If the clicked group wasn't open, open it now
            if (!isOpen) {
                currentGroup.classList.add('open');
            }
        });
    });
});


/* =========================================================
   RECENTLY VISITED PAGES TRACKER (Saved in Browser)
   ========================================================= */
(function trackRecentPages() {
    var path = window.location.pathname;
    
    // Do not track the dashboard itself, login, logout, or admin
    if (path === '/' || path.includes('/login') || path.includes('/logout') || path.includes('/admin')) {
        return;
    }

    // Get the page title (e.g., "Sales - Coal Mine" -> "Sales")
    var title = document.title.split(' - ')[0] || path;
    
    var recent = JSON.parse(localStorage.getItem('cm_recent_pages') || '[]');

    // Remove the page if it already exists in the list (to move it to the top)
    recent = recent.filter(item => item.url !== path);
    
    // Add to the front of the list
    recent.unshift({ url: path, title: title });
    
    // Keep only the top 5 most recent
    recent = recent.slice(0, 5);
    
    // Save back to browser
    localStorage.setItem('cm_recent_pages', JSON.stringify(recent));
})();