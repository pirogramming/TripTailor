// ===== SEARCH PAGE FUNCTIONALITY =====
// Additional places container styles and load more functionality
document.addEventListener('DOMContentLoaded', function() {
    // Search page specific functionality
    const loadMoreBtn = document.getElementById('load-more-btn');
    const additionalContainer = document.getElementById('additional-places-container');
    const loadingDiv = document.getElementById('loading');
    
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function() {
            const prompt = this.dataset.prompt;
            const followup = this.dataset.followup;
            const currentPage = parseInt(this.dataset.page || '1');
            
            // 로딩 상태 표시
            loadingDiv.style.display = 'block';
            loadMoreBtn.style.display = 'none';
            
            // URL 파라미터 구성
            const params = new URLSearchParams();
            params.append('prompt', prompt);
            if (followup) {
                params.append('followup', followup);
            }
            params.append('page', currentPage + 1);
            
            // AJAX 요청으로 더 많은 장소 가져오기
            fetch(`/more-recommendations-ajax/?${params.toString()}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.places && data.places.length > 0) {
                        // 3개씩 한 줄로 카드들을 추가
                        for (let i = 0; i < data.places.length; i += 3) {
                            const row = document.createElement('div');
                            row.className = 'additional-places-row';
                            
                            // 현재 줄에 들어갈 카드들 (최대 3개)
                            const rowPlaces = data.places.slice(i, i + 3);
                            
                            rowPlaces.forEach(placeData => {
                                const placeCard = createPlaceCard(placeData);
                                row.appendChild(placeCard);
                            });
                            
                            additionalContainer.appendChild(row);
                        }
                        
                        // 페이지 번호 업데이트
                        this.dataset.page = currentPage + 1;
                        
                        // 더 로드할 수 있는지 확인
                        if (data.has_more) {
                            loadMoreBtn.style.display = 'block';
                            const totalLoaded = 3 + (this.dataset.page - 1) * 3; // 초기 3개 + 추가된 3개씩
                            loadMoreBtn.textContent = `🔍 더 많은 장소 보기 (현재 ${totalLoaded}개)`;
                        } else {
                            const totalLoaded = 3 + (this.dataset.page - 1) * 3;
                            this.textContent = `더 이상 로드할 장소가 없습니다 (총 ${totalLoaded}개)`;
                            this.disabled = true;
                        }
                    } else {
                        // 더 이상 로드할 장소가 없음
                        const totalLoaded = 3 + (this.dataset.page - 1) * 3;
                        this.textContent = `더 이상 로드할 장소가 없습니다 (총 ${totalLoaded}개)`;
                        this.disabled = true;
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    this.textContent = '오류가 발생했습니다. 다시 시도해주세요.';
                    this.style.display = 'block';
                })
                .finally(() => {
                    loadingDiv.style.display = 'none';
                });
        });
    }
    
    function createPlaceCard(placeData) {
        const card = document.createElement('div');
        card.className = 'place-card';
        
        card.innerHTML = `
            <div class="place-card__map"></div>
            <div class="place-card__body">
                <h3 class="place-card__title">${placeData.place.name}</h3>
                <p class="place-card__region">${placeData.place.region}</p>
                ${placeData.reason ? `<p class="place-card__reason">${placeData.reason}</p>` : ''}
                <p class="place-card__summary">${placeData.place.summary || '설명 없음'}</p>
                <ul class="tag-list">
                    ${placeData.place.tags.map(tag => `<li class="tag">#${tag.name}</li>`).join('')}
                </ul>
                ${placeData.place.is_authenticated ? `
                <form method="post" action="/${placeData.place.id}/like/" class="like-form">
                    <input type="hidden" name="csrfmiddlewaretoken" value="${getCookie('csrftoken')}">
                    <button type="submit" class="like-button">
                        ${placeData.place.is_liked ? '❤️ 취소' : '🤍 좋아요'}
                    </button>
                </form>
                ` : ''}
                <a href="/${placeData.place.id}/" class="link">자세히 보기</a>
            </div>
        `;
        
        return card;
    }
    
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});

// ===== MAIN PAGE FUNCTIONALITY =====
// Route management and tag functionality
document.addEventListener('DOMContentLoaded', function() {
    // CSRF token function
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
    const csrftoken = getCookie('csrftoken');

    // Route dropdown functionality
    document.querySelectorAll('.add-to-route-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const dropdown = btn.nextElementSibling;
            const placeId = btn.dataset.placeId;

            // 다른 드롭다운 닫기
            document.querySelectorAll('.route-dropdown').forEach(d => {
                if (d !== dropdown) d.style.display = 'none';
            });

            // 토글
            dropdown.style.display = (dropdown.style.display === 'block') ? 'none' : 'block';
            if (dropdown.style.display === 'block') {
                const listBox = dropdown.querySelector('.route-list');
                listBox.textContent = '불러오는 중...';
                try {
                    const res = await fetch("/routes/my-routes-json/", { credentials: 'same-origin' });
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
        });
    });

    // Route selection → place addition
    document.addEventListener('click', async (e) => {
        if (e.target.classList.contains('select-route-btn')) {
            const routeId = e.target.dataset.routeId;
            const placeId = e.target.dataset.placeId;
            const endpoint = `/routes/${routeId}/add/${placeId}/`;

            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest'},
                    credentials: 'same-origin'
                });
                const data = await res.json();
                alert(data.duplicated ? '이미 해당 루트에 있음' : '루트에 추가됨');
            } catch (err) {
                alert('추가 실패');
            }
        }
    });

    // New route creation → list refresh
    document.addEventListener('click', async (e) => {
        if (e.target.classList.contains('create-route-btn')) {
            const dropdown = e.target.closest('.route-dropdown');
            const titleInput = dropdown.querySelector('.new-route-title');
            const summaryInput = dropdown.querySelector('.new-route-summary');

            const title = titleInput.value.trim();
            const summary = (summaryInput?.value || '').trim();
            if (!title) {
                alert('제목을 입력하세요');
                return;
            }
            try {
                const fd = new FormData();
                fd.append('title', title);
                fd.append('location_summary', summary);

                const res = await fetch("/routes/create/", {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest'},
                    body: fd,
                    credentials: 'same-origin'
                });
                const data = await res.json();
                if (data.ok) {
                    alert('루트 생성됨');
                    titleInput.value = '';
                    if (summaryInput) summaryInput.value = '';
                    const listBox = dropdown.querySelector('.route-list');
                    const placeId = dropdown.previousElementSibling.dataset.placeId;
                    const btnHtml = `<div><button type="button" class="select-route-btn" data-route-id="${data.route.id}" data-place-id="${placeId}">${data.route.title}</button></div>`;
                    listBox.insertAdjacentHTML('afterbegin', btnHtml);
                } else {
                    alert('생성 실패');
                }
            } catch (err) {
                alert('오류 발생');
            }
        }
    });

    // Tag functionality
    (async function () {
        try {
            const res = await fetch("/places/tags-json/");
            const tags = await res.json();

            const initialCount = 5;
            const rail = document.querySelector('.tag-rail');
            const track = document.getElementById('tagTrack');
            const moreBtn = rail?.querySelector('.chip.more');

            if (!rail || !track) return;

            // 현재 URL에서 선택된 태그 복원
            const params = new URLSearchParams(location.search);
            const preselected = (params.get('tags') || "")
                                .split(',').filter(Boolean);

            // 칩 렌더
            tags.forEach((t, i) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'chip' + (i >= initialCount ? ' extra' : '');
                btn.dataset.tag = t.name;
                btn.textContent = `#${t.name}`;
                if (preselected.includes(t.name)) {
                    btn.classList.add('active');
                    btn.setAttribute('aria-pressed', 'true');
                } else {
                    btn.setAttribute('aria-pressed', 'false');
                }
                track.appendChild(btn);
            });

            // 더보기/접기
            if (moreBtn) {
                moreBtn.addEventListener('click', () => {
                    const expanded = rail.dataset.expanded === 'true';
                    rail.dataset.expanded = (!expanded).toString();
                    moreBtn.textContent = expanded ? '+ 더보기' : '접기';
                    moreBtn.setAttribute('aria-expanded', (!expanded).toString());
                });
                if (tags.length <= initialCount) moreBtn.style.display = 'none';
            }

            // 칩 클릭 → URL 파라미터 갱신 → 즉시 새로고침
            track.addEventListener('click', (e) => {
                const chip = e.target.closest('.chip');
                if (!chip || chip.classList.contains('more')) return;

                // 다중 선택(OR 매칭)
                chip.classList.toggle('active');
                chip.setAttribute('aria-pressed', chip.classList.contains('active') ? 'true' : 'false');

                const selected = [...track.querySelectorAll('.chip.active')].map(b => b.dataset.tag);

                const url = new URL(window.location.href);
                if (selected.length) {
                    url.searchParams.set('tags', selected.join(','));  // 예: tags=a,b,c
                    url.searchParams.set('match', 'any');              // OR 매칭 (원하면 'all')
                } else {
                    url.searchParams.delete('tags');
                    url.searchParams.delete('match');
                }

                // 다른 파라미터들(prompt, followup, place_class 등)은 그대로 유지됨
                window.location.assign(url.toString());
            });
        } catch (error) {
            console.error('Tag loading error:', error);
        }
    })();

    // Category filter functionality
    document.querySelectorAll('.btn.cat').forEach(a => {
        a.addEventListener('click', (e) => {
            e.preventDefault();
            const url = new URL(window.location.href);
            const cls = a.dataset.class;

            if (cls) url.searchParams.set('place_class', cls);
            else url.searchParams.delete('place_class'); // 전체

            // 기존 파라미터(prompt, followup, tags, match)는 그대로 보존됨
            window.location.assign(url.toString());
        });
    });
});

// ===== PLACE DETAIL PAGE FUNCTIONALITY =====
// Blog reviews loading
document.addEventListener('DOMContentLoaded', function() {
    const btn = document.getElementById("load-blog-reviews");
    const ul = document.getElementById("blog-review-list");
    
    if (!btn || !ul) return;
    
    const clean = (s='') => s.replace(/<[^>]+>/g, '');

    btn.addEventListener("click", async () => {
        ul.innerHTML = "<li>로딩 중...</li>";
        try {
            const pid = btn.dataset.placeId;
            const res = await fetch(`/reviews/blogs/${pid}/`);
            const data = await res.json();
            ul.innerHTML = "";
            (data.items || []).forEach(it => {
                const li = document.createElement("li");
                li.innerHTML = `
                    <a href="${it.link}" target="_blank" rel="noopener">${clean(it.title)}</a>
                    <div>${clean(it.summary)}</div>
                    <small>${it.blogger} · ${it.postdate}</small>
                `;
                ul.appendChild(li);
            });
            if ((data.items || []).length === 0) {
                ul.innerHTML = "<li>관련 블로그 후기가 없어요.</li>";
            }
        } catch (e) {
            console.error(e);
            ul.innerHTML = "<li>불러오는 중 오류가 발생했어요.</li>";
        }
    });
});

// ===== REVIEW FORM FUNCTIONALITY =====
// Photo preview functionality
document.addEventListener('DOMContentLoaded', function() {
    const photoForms = document.querySelectorAll('.photo-form');
    
    photoForms.forEach(function(form) {
        const urlInput = form.querySelector('input[type="url"]');
        const deleteCheckbox = form.querySelector('input[type="checkbox"]');
        const previewDiv = form.querySelector('div[id^="preview-"]');
        const previewImg = previewDiv ? previewDiv.querySelector('img') : null;
        
        if (urlInput && previewImg) {
            urlInput.addEventListener('input', function() {
                const url = this.value.trim();
                        if (url && isValidImageUrl(url)) {
            previewImg.src = url;
            previewDiv.style.display = 'block';
        } else {
            previewDiv.style.display = 'none';
        }
    });
    
    if (urlInput.value.trim()) {
        urlInput.dispatchEvent(new Event('input'));
    }
}

if (deleteCheckbox && urlInput) {
    deleteCheckbox.addEventListener('change', function() {
        if (this.checked) {
            urlInput.value = '';
            if (previewDiv) {
                previewDiv.style.display = 'none';
            }
        }
    });
}
});

function isValidImageUrl(url) {
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'];
    const lowerUrl = url.toLowerCase();
    return imageExtensions.some(ext => lowerUrl.includes(ext)) || 
           lowerUrl.includes('http') || 
           lowerUrl.includes('data:image');
}
});

// ===== DYNAMIC CSS STYLES =====
// Add dynamic styles for additional places container
function addDynamicStyles() {
    const style = document.createElement('style');
    style.textContent = `
        /* 추가 카드들을 위한 세로 컨테이너 */
        .additional-places-container {
            margin: 20px auto;
            max-width: 1200px;
            padding: 0 20px;
        }

        /* 추가 카드들을 3개씩 가로 배치 */
        .additional-places-row {
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            justify-content: center;
        }

        .additional-places-row .place-card {
            width: calc(33.333% - 11px);
            min-width: 300px;
            max-width: 400px;
        }

        /* 더보기 버튼 스타일 */
        .more-places-section {
            text-align: center;
            margin: 30px 0;
        }

        .more-places-button {
            background-color: #4ca2a7;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
        }

        .more-places-button:hover {
            background-color: #3a8a8f;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        .more-places-button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        #loading {
            color: #666;
            font-style: italic;
        }

        /* Filter button styles */
        .btn {
            display: inline-block;
            padding: 8px 16px;
            margin-right: 8px;
            background: #eee;
            color: #333;
            border-radius: 4px;
            text-decoration: none;
            border: 1px solid #ccc;
        }
        .btn.active {
            background: #007bff;
            color: #fff;
            border-color: #007bff;
        }
    `;
    document.head.appendChild(style);
}

// Initialize dynamic styles when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    addDynamicStyles();
});       