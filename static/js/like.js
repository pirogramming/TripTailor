document.addEventListener('DOMContentLoaded', function () {
    // 모든 찜 폼에 대해 이벤트 등록
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
                    // 버튼 텍스트 변경
                    if (data.liked) {
                        button.textContent = '❤️ 취소';
                    } else {
                        button.textContent = '🤍 좋아요';
                    }
                    // 필요시 좋아요 개수 등도 업데이트 가능
                })
                .catch(() => {
                    alert('좋아요 처리 중 오류가 발생했습니다.');
                });
        });
    });
});