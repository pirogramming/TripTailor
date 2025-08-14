document.addEventListener('DOMContentLoaded', function () {
    // 좋아요 폼 처리
    document.querySelectorAll('.like-form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const button = form.querySelector('.like-button');
            const actionUrl = form.getAttribute('action');
            const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]').value;

            fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
                .then(res => res.json())
                .then(data => {
                    button.textContent = data.liked ? '❤️ 찜취소' : '🤍 찜하기';
                })
                .catch(() => {
                    alert('좋아요 처리 중 오류가 발생했습니다.');
                });
        });
    });

    // 팝업 열기/닫기
    document.querySelectorAll('.add-to-route-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation(); // 바깥 클릭 이벤트 방지
            const card = btn.closest('.place-item');
            const dropdown = card.querySelector('.route-dropdown');

            // 다른 팝업 닫기
            document.querySelectorAll('.route-dropdown').forEach(d => {
                if (d !== dropdown) d.style.display = 'none';
            });

            // 현재 팝업 토글
            dropdown.style.display = (dropdown.style.display === 'block') ? 'none' : 'block';
        });
    });

    // 팝업 내부 클릭 시 닫힘 방지
    document.querySelectorAll('.route-dropdown').forEach(function (dropdown) {
        dropdown.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    });

    // 바깥 클릭 시 닫기
    document.addEventListener('click', function () {
        document.querySelectorAll('.route-dropdown').forEach(d => {
            d.style.display = 'none';
        });
    });

    // ESC 키로 닫기
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.route-dropdown').forEach(d => {
                d.style.display = 'none';
            });
        }
    });
});
