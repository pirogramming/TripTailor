// static/js/like.js
(function () {
    // 좋아요: 폼 submit 위임
    document.addEventListener('submit', async function (e) {
        const form = e.target.closest('.like-form');
        if (!form) return;

        e.preventDefault();

        const button = form.querySelector('.like-button');
        const actionUrl = form.getAttribute('action');
        const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]')?.value;

        try {
            const res = await fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken || '',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            const data = await res.json();
            if (button) {
                button.textContent = data.liked ? '❤️ 찜취소' : '🤍 찜하기';
                button.dataset.liked = data.liked ? '1' : '0';
            }
            const countEl = form.closest('.place-item')?.querySelector('.like-count');
            if (countEl && typeof data.like_count !== 'undefined') {
                countEl.textContent = data.like_count;
            }
        } catch (err) { }
    });

    // 루트 추가: 드롭다운 토글/닫기 위임
    let lastOpenTs = 0;

    document.addEventListener('pointerdown', function (e) {
        const btn = e.target.closest('.add-to-route-btn');
        if (!btn) return;

        e.preventDefault();
        e.stopPropagation();

        const card = btn.closest('.place-item');
        if (!card) return;

        const dropdown = card.querySelector('.route-dropdown');
        if (!dropdown) return;

        document.querySelectorAll('.route-dropdown').forEach(d => {
            if (d !== dropdown) {
                d.style.display = 'none';
            }
        });

        dropdown.style.display = (dropdown.style.display === 'block') ? 'none' : 'block';
        lastOpenTs = Date.now();
    });

    document.addEventListener('click', function (e) {
        if (e.target.closest('.add-to-route-btn') || e.target.closest('.route-dropdown')) {
            return;
        }
        if (Date.now() - lastOpenTs <= 120) return;
        document.querySelectorAll('.route-dropdown').forEach(d => {
            d.style.display = 'none';
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.route-dropdown').forEach(d => {
                d.style.display = 'none';
            });
        }
    });

    // 드롭다운 항목 클릭 시 서버로 추가 요청
    document.addEventListener('click', async function (e) {
        const item = e.target.closest('.route-add-item');
        if (!item) return;

        e.preventDefault();

        const url = item.dataset.action;
        if (!url) return;

        const getCookie = (name) => {
            const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
            return m ? m.pop() : '';
        };
        const csrf =
            document.querySelector('input[name=csrfmiddlewaretoken]')?.value ||
            getCookie('csrftoken');

        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrf || '',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!res.ok) return;
            const dd = item.closest('.route-dropdown');
            if (dd) dd.style.display = 'none';
        } catch (err) { }
    });
})();
