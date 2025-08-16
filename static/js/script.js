// ===============================
// TripTailor main JS (unified)
// ===============================
(function () {
    // ---------- Helpers ----------
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
    const csrftoken = getCookie('csrftoken');

    // ---------- After DOM Ready ----------
    document.addEventListener('DOMContentLoaded', function () {
        // ===== 좋아요 AJAX =====
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

        // ===== TAGS: “더보기/접기 & Ajax 필터” (교체된 부분) =====
        (function initTagChipsAjax() {
            const rail = document.querySelector('.tag-rail');
            const track = document.getElementById('tagTrack');
            if (!rail || !track) return;

            const moreBtn = rail.querySelector('.chip.more');

            // 더보기/접기 초기화
            (function initMore() {
                if (!moreBtn || rail.dataset.jsInit === '1') return;
                rail.dataset.jsInit = '1';

                const extraChips = track.querySelectorAll('.chip.extra');
                if (!extraChips.length) {
                    moreBtn.style.display = 'none';
                    return;
                }

                // 초기 상태 설정
                rail.setAttribute('data-expanded', 'false');
                moreBtn.setAttribute('aria-expanded', 'false');
                moreBtn.textContent = '+ 더보기';
                
                moreBtn.addEventListener('click', () => {
                    const expanded = rail.getAttribute('data-expanded') === 'true';
                    const next = !expanded;
                    rail.setAttribute('data-expanded', String(next));
                    moreBtn.setAttribute('aria-expanded', String(next));
                    moreBtn.textContent = next ? '접기' : '+ 더보기';
                });

                console.log('[initMore] 더보기/접기 토글 초기화 완료');
            })();


            // 목록만 Ajax 교체
            async function fetchAndSwapList(nextParams) {
                const url = new URL(window.location.href);

                // 기존 쿼리 초기화 후 새 파라미터 채우기
                for (const k of Array.from(url.searchParams.keys())) url.searchParams.delete(k);
                nextParams.forEach((v, k) => url.searchParams.set(k, v));

                const listEl = document.querySelector('.place-list');
                if (listEl) listEl.insertAdjacentHTML('beforebegin', '<div id="list-loading" style="padding:1rem">불러오는 중...</div>');

                try {
                    const res = await fetch(url.toString(), { credentials: 'same-origin' });
                    const html = await res.text();
                    const doc = new DOMParser().parseFromString(html, 'text/html');
                    const fetchedList = doc.querySelector('.place-list');
                    const currentList = document.querySelector('.place-list');
                    if (fetchedList && currentList) currentList.outerHTML = fetchedList.outerHTML;

                    history.pushState(null, '', url.toString());
                } finally {
                    document.getElementById('list-loading')?.remove();
                }
            }

            // 칩 클릭 → URL 파라미터 갱신 → Ajax로 목록만 갱신
            track.addEventListener('click', async (e) => {
                const chip = e.target.closest('.chip');
                if (!chip || chip.classList.contains('more')) return;

                chip.classList.toggle('active');
                chip.setAttribute('aria-pressed', chip.classList.contains('active') ? 'true' : 'false');

                const selected = [...track.querySelectorAll('.chip.active')].map(b => b.dataset.tag);

                const next = new URLSearchParams(window.location.search);
                if (selected.length) next.set('tags', selected.join(','));
                else next.delete('tags');

                await fetchAndSwapList(next);
            });

            // 뒤로가기/앞으로가기 시, 리스트와 칩 상태 동기화
            window.addEventListener('popstate', async () => {
                const next = new URLSearchParams(window.location.search);
                await fetchAndSwapList(next);

                const selected = (next.get('tags') || '').split(',').filter(Boolean);
                document.querySelectorAll('#tagTrack .chip').forEach((c) => {
                    const on = selected.includes(c.dataset.tag);
                    c.classList.toggle('active', on);
                    c.setAttribute('aria-pressed', on ? 'true' : 'false');
                });
            });
        })();

        // ===== ROUTE: 드롭다운/추가/새로만들기 (이벤트 위임) =====
        document.addEventListener('click', async (e) => {
            // 열기/불러오기
            const addBtn = e.target.closest('.add-to-route-btn');
            if (addBtn) {
                const dropdown = addBtn.nextElementSibling;
                const placeId = addBtn.dataset.placeId;

                document.querySelectorAll('.route-dropdown').forEach((d) => {
                    if (d !== dropdown) d.style.display = 'none';
                });

                dropdown.style.display = (dropdown.style.display === 'block') ? 'none' : 'block';
                if (dropdown.style.display === 'block') {
                    const listBox = dropdown.querySelector('.route-list');
                    listBox.textContent = '불러오는 중...';
                    try {
                        const res = await fetch('/routes/mine/json/', { credentials: 'same-origin' });
                        const data = await res.json();
                        if (!data.routes.length) {
                            listBox.innerHTML = '<p>루트 없음</p>';
                        } else {
                            listBox.innerHTML = data.routes.map(r => `
                <div>
                  <button type="button" class="select-route-btn" data-route-id="${r.id}" data-place-id="${placeId}">
                    ${r.title}
                  </button>
                </div>
              `).join('');
                        }
                    } catch (err) {
                        listBox.textContent = '불러오기 실패';
                    }
                }
            }

            // 루트 선택 → 장소 추가
            if (e.target.classList.contains('select-route-btn')) {
                // 중복 방지: 이미 처리 중이면 return
                if (e.target.dataset.clicked === 'true') return;
                e.target.dataset.clicked = 'true';

                const routeId = e.target.dataset.routeId;
                const placeId = e.target.dataset.placeId;
                const endpoint = `/routes/${routeId}/add/${placeId}/`;
                try {
                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'same-origin'
                    });
                    const data = await res.json();
                    alert(data.duplicated ? '이미 해당 루트에 있음' : '루트에 추가됨');
                } catch (err) {
                    alert('추가 실패');
                } finally {
                    // 0.5초 후 다시 클릭 가능하게
                    setTimeout(() => { e.target.dataset.clicked = 'false'; }, 500);
                }
            }

            // 새 루트 생성 → 목록 갱신
            if (e.target.classList.contains('create-route-btn')) {
                // 중복 방지: 이미 처리 중이면 return
                if (e.target.dataset.clicked === 'true') return;
                e.target.dataset.clicked = 'true';

                const dropdown = e.target.closest('.route-dropdown');
                const titleInput = dropdown.querySelector('.new-route-title');
                const summaryInput = dropdown.querySelector('.new-route-summary');
                const title = (titleInput.value || '').trim();
                const summary = (summaryInput?.value || '').trim();
                const isPublic = dropdown.querySelector('.new-route-public').checked;

                if (!title) {
                    alert('제목을 입력하세요');
                    e.target.dataset.clicked = 'false';
                    return;
                }
                try {
                    const fd = new FormData();
                    fd.append('title', title);
                    fd.append('location_summary', summary);
                    fd.append('is_public', isPublic ? 'true' : 'false');
                    const res = await fetch('/routes/create/', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest' },
                        body: fd,
                        credentials: 'same-origin'
                    });
                    const data = await res.json();
                    if (data.ok) {
                        alert('루트 생성됨');
                        titleInput.value = '';
                        if (summaryInput) summaryInput.value = '';
                        const listBox = dropdown.querySelector('.route-list');
                        const placeId = dropdown.previousElementSibling?.dataset.placeId || '';
                        const btnHtml = `<div><button type="button" class="select-route-btn" data-route-id="${data.route.id}" data-place-id="${placeId}">${data.route.title}</button></div>`;
                        listBox.insertAdjacentHTML('afterbegin', btnHtml);
                    } else {
                        alert('생성 실패');
                    }
                } catch (err) {
                    alert('오류 발생');
                } finally {
                    // 0.5초 후 다시 클릭 가능하게
                    setTimeout(() => { e.target.dataset.clicked = 'false'; }, 500);
                }
            }
        });

        // ===== CATEGORY filter (기존 유지: 전체 페이지 이동) =====
        (function initCategoryFilter() {
            document.querySelectorAll('.btn.cat').forEach((a) => {
                a.addEventListener('click', (e) => {
                    e.preventDefault();
                    const url = new URL(window.location.href);
                    const cls = a.dataset.class;
                    if (cls) url.searchParams.set('place_class', cls);
                    else url.searchParams.delete('place_class');
                    window.location.assign(url.toString());
                });
            });
        })();

        // ===== PLACE DETAIL: 네이버 블로그 후기 로딩 =====
        (function initBlogReviews() {
            const btn = document.getElementById('load-blog-reviews');
            const ul = document.getElementById('blog-review-list');
            if (!btn || !ul) return;

            const clean = (s = '') => s.replace(/<[^>]+>/g, '');

            btn.addEventListener('click', async () => {
                ul.innerHTML = '<li>로딩 중...</li>';
                try {
                    const pid = btn.dataset.placeId;
                    const res = await fetch(`/reviews/blogs/${pid}/`);
                    const data = await res.json();
                    ul.innerHTML = '';
                    (data.items || []).forEach((it) => {
                        const li = document.createElement('li');
                        li.innerHTML = `
    <a href="${it.link}" target="_blank" rel="noopener">${clean(it.title)}</a>
    <div>${clean(it.summary)}</div>
    <small>${it.blogger} · ${it.postdate}</small>
    `;
                        ul.appendChild(li);
                    });
                    if (!(data.items || []).length) ul.innerHTML = '<li>관련 블로그 후기가 없어요.</li>';
                } catch (e) {
                    console.error(e);
                    ul.innerHTML = '<li>불러오는 중 오류가 발생했어요.</li>';
                }
            });
        })();

        // ===== REVIEW FORM: 사진 미리보기 =====
        (function initReviewPhotos() {
            document.querySelectorAll('.photo-form').forEach((form) => {
                const urlInput = form.querySelector('input[type="url"]');
                const deleteCheckbox = form.querySelector('input[type="checkbox"]');
                const previewDiv = form.querySelector('div[id^="preview-"]');
                const previewImg = previewDiv ? previewDiv.querySelector('img') : null;

                if (urlInput && previewImg) {
                    urlInput.addEventListener('input', function () {
                        const url = (this.value || '').trim();
                        if (isValidImageUrl(url)) {
                            previewImg.src = url;
                            previewDiv.style.display = 'block';
                        } else {
                            previewDiv.style.display = 'none';
                        }
                    });
                    if ((urlInput.value || '').trim()) urlInput.dispatchEvent(new Event('input'));
                }

                if (deleteCheckbox && urlInput) {
                    deleteCheckbox.addEventListener('change', function () {
                        if (this.checked) {
                            urlInput.value = '';
                            if (previewDiv) previewDiv.style.display = 'none';
                        }
                    });
                }
            });

            function isValidImageUrl(url) {
                const lower = (url || '').toLowerCase();
                const exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'];
                return exts.some(ext => lower.includes(ext)) || lower.startsWith('data:image') || lower.startsWith('http');
            }
        })();

        // ===== Dynamic CSS (기존 유지) =====
        (function addDynamicStyles() {
            const style = document.createElement('style');
            style.textContent = `
    .additional-places-container{margin:20px auto;max-width:1200px;padding:0 20px;}
    .additional-places-row{display:flex;gap:16px;margin-bottom:20px;justify-content:center;}
    .additional-places-row .place-card{width:calc(33.333% - 11px);min-width:300px;max-width:400px;}
    .more-places-section{text - align:center;margin:30px 0;}
    .more-places-button{background:#4ca2a7;color:#fff;border:none;padding:12px 24px;border-radius:25px;font-size:16px;cursor:pointer;transition:.3s;text-decoration:none;display:inline-block;}
    .more-places-button:hover{background:#3a8a8f;transform:translateY(-2px);box-shadow:0 4px 8px rgba(0,0,0,.2);}
    .more-places-button:disabled{background:#ccc;cursor:not-allowed;transform:none;box-shadow:none;}
    #loading{color:#666;font-style:italic;}
    .btn{display:inline-block;padding:8px 16px;margin-right:8px;background:#eee;color:#333;border-radius:4px;text-decoration:none;border:1px solid #ccc;}
    .btn.active{background:#007bff;color:#fff;border-color:#007bff;}
    `;
            document.head.appendChild(style);
        })();
    });
})();

document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const menuToggle = document.getElementById('menu-toggle');

    if (menuToggle && sidebar) {
        // 체크 상태 변화에 따라 사이드바 열고 닫기
        menuToggle.addEventListener('change', () => {
            if (menuToggle.checked) {
                sidebar.classList.add('open');
            } else {
                sidebar.classList.remove('open');
            }
        });

        // 사이드바 바깥 클릭 시 닫기
        document.addEventListener('click', (e) => {
            const isClickInside = sidebar.contains(e.target) || menuToggle.parentElement.contains(e.target);
            if (!isClickInside) {
                sidebar.classList.remove('open');
                menuToggle.checked = false; // 버튼 상태 복원
            }
        });
    }
});

