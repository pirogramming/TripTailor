// comment_crud.js (data-* 방식, 중복 리스너/전역변수 없이 동작)

(function () {
    // -------------------------
    // Helpers
    // -------------------------
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    function getCsrfToken() {
        // 폼 hidden input 우선, 없으면 쿠키에서
        const inp = document.querySelector('[name=csrfmiddlewaretoken]');
        return inp ? inp.value : (getCookie('csrftoken') || '');
    }

    // -------------------------
    // Reviews: load & delete
    // -------------------------
    function loadReviews() {
        const reviewList = document.getElementById('review-list');
        if (!reviewList) return;

        const placeId = reviewList.dataset.placeId;
        if (!placeId) {
            console.error('[reviews] data-place-id가 없습니다 (#review-list).');
            return;
        }

        fetch(`/reviews/htmx/${placeId}`)
            .then((res) => res.text())
            .then((html) => {
                reviewList.innerHTML = html;
                setupDeleteButtons();
            })
            .catch((err) => {
                console.error('댓글 목록을 불러오는 중 오류 발생:', err);
                reviewList.innerHTML = '<p>댓글 목록을 불러오는 중 오류가 발생했습니다.</p>';
            });
    }

    function setupDeleteButtons() {
        const deleteButtons = document.querySelectorAll('.delete-review-btn');
        // 이벤트 중복 방지를 위해 기존 리스너 제거를 시도할 수도 있지만
        // 여기서는 캡처에 함수를 바인딩하지 않고, 옵션으로 once를 쓰지 않으므로
        // 아래처럼 먼저 모든 버튼에 대해 일단 제거 후 다시 등록
        deleteButtons.forEach((btn) => {
            btn.removeEventListener('click', handleDeleteClick);
            btn.addEventListener('click', handleDeleteClick);
        });
    }

    function handleDeleteClick(event) {
        const button = event.currentTarget;
        const reviewId = button.getAttribute('data-review-id');
        const placeId = button.getAttribute('data-place-id');

        if (!reviewId || !placeId) {
            console.error('[reviews] data-review-id 또는 data-place-id가 없습니다.');
            return;
        }

        if (!confirm('정말 삭제하시겠습니까?')) return;

        const csrfToken = getCsrfToken();

        fetch(`/reviews/place/${placeId}/${reviewId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
            },
        })
            .then((res) => {
                // JSON 응답 가정
                return res.json().catch(() => ({ success: false, message: '잘못된 응답 형식' }));
            })
            .then((data) => {
                if (data.success) {
                    loadReviews(); // 목록만 새로고침
                } else {
                    alert('삭제 중 오류가 발생했습니다: ' + (data.message || '알 수 없는 오류'));
                }
            })
            .catch((err) => {
                console.error('삭제 요청 오류:', err);
                alert('삭제 중 오류가 발생했습니다.');
            });
    }

    // -------------------------
    // Photos: file upload preview
    // -------------------------
    function initPhotoInputs() {
        const input = document.getElementById('id_photos');
        const previews = document.getElementById('photo-previews');
        if (!input || !previews) return;

        const MAX_FILES = 5;

        input.addEventListener('change', function() {
            previews.innerHTML = '';
            const files = Array.from(input.files);

            // 최대 개수 체크
            if (files.length > MAX_FILES) {
                alert(`이미지는 최대 ${MAX_FILES}장까지 업로드할 수 있습니다.`);
                input.value = '';
                return;
            }

            files.forEach(file => {
                if (!file.type.startsWith('image/')) return;

                const reader = new FileReader();
                reader.onload = function(e) {
                    const wrap = document.createElement('div');
                    wrap.className = 'border rounded p-2 d-inline-flex flex-column align-items-center';
                    wrap.style.width = '120px';
                    wrap.innerHTML = `
                        <img src="${e.target.result}" alt="미리보기" style="max-width:100%;max-height:100px;object-fit:cover;">
                        <span class="small mt-1 text-truncate" style="max-width:100%;">${file.name}</span>
                    `;
                    previews.appendChild(wrap);
                };
                reader.readAsDataURL(file);
            });
        });
    }

    // -------------------------
    // Form submit -> reload reviews
    // -------------------------
    function initReviewFormRefresh() {
        const reviewForm = document.getElementById('review-form');
        if (!reviewForm) return;

        // 제출 후 서버 처리 시간 고려해 약간의 지연 후 목록 갱신
        reviewForm.addEventListener('submit', function () {
            setTimeout(loadReviews, 1000);
        });
    }

    // -------------------------
    // Boot
    // -------------------------
    document.addEventListener('DOMContentLoaded', function () {
        loadReviews();
        initPhotoInputs();
        initReviewFormRefresh();
    });
})();
