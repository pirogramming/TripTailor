// static/js/tabbar.js
(function () {
  const RESULTS_SEL = "#results";
  const LIST_SEL    = ".place-list";
  const PAGI_SEL    = ".pagination";

  let $results = document.querySelector(RESULTS_SEL);
  if (!$results) return;

  // -------- 유틸 --------
  const paramsFromForm = (form) => new URLSearchParams(new FormData(form));
  const currentParams  = () => new URLSearchParams(window.location.search);

  const buildUrl = (params) => {
    // 필터 변경 시 page 초기화
    params.delete("page");
    const url = new URL(window.location.href);
    url.search = params.toString();
    return url.toString();
  };

  const toggleArrayParam = (params, key, value) => {
    // 기존 tags 파라미터 모두 모아서 split하고 하나의 배열로 만듬
    let allValues = [];

    params.getAll(key).forEach((item) => {
      item.split(',').forEach((v) => {
        const trimmed = v.trim();
        if (trimmed) allValues.push(trimmed);
      });
    });

    // 중복 없이 set으로 관리
    const set = new Set(allValues);

    if (set.has(value)) {
      set.delete(value);  // 이미 있으면 제거
    } else {
      set.add(value);     // 없으면 추가
    }

    // 기존 파라미터 모두 삭제 후 갱신
    params.delete(key);

    if (set.size > 0) {
      params.set(key, Array.from(set).join(','));
    }
  };



  const swapPartialsFromHTML = (htmlText) => {
    const doc = new DOMParser().parseFromString(htmlText, "text/html");
    const newResults = doc.querySelector(RESULTS_SEL);

    if (newResults) {
      $results.replaceWith(newResults);
      $results = document.querySelector(RESULTS_SEL);
      return;
    }
    // results 래퍼가 없는 경우: 리스트/페이지네이션만 교체
    const newList = doc.querySelector(LIST_SEL);
    const newPagi = doc.querySelector(PAGI_SEL);
    const curList = document.querySelector(LIST_SEL);
    if (curList && newList) curList.replaceWith(newList);
    const curPagi = document.querySelector(PAGI_SEL);
    if (curPagi && newPagi) curPagi.replaceWith(newPagi);
    if (curPagi && !newPagi) curPagi.remove();
    if (!curPagi && newPagi && document.querySelector(LIST_SEL)) {
      document.querySelector(LIST_SEL).insertAdjacentElement("afterend", newPagi);
    }
  };

  const fetchPartial = async (url, push) => {
    document.body.setAttribute("aria-busy", "true");
    try {
      const res = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const data = await res.json();
        if (data.html) $results.innerHTML = data.html;
        else if (data.full) swapPartialsFromHTML(data.full);
      } else {
        const html = await res.text();
        swapPartialsFromHTML(html);
      }
      if (push) history.pushState({ url }, "", url);
      // 교체 후 필요한 초기화가 있으면 호출(예: like.js 재바인딩)
      window.initMap && window.initMap();
      // window.initLikeButtons && window.initLikeButtons();
      if (window.google?.maps && typeof window.initMap === 'function') {
        window.initMap(); // 지도 재초기화
      }

    } catch (e) {
      location.href = url; // 실패 시 폴백
    } finally {
      document.body.removeAttribute("aria-busy");
    }
  };

  // -------- 라디오 탭 변경 --------
  document.addEventListener("change", (e) => {
    const radio = e.target.closest('#filterForm input[name="place_class"]');
    if (!radio) return;

    const form = document.getElementById("filterForm");
    if (!form) return;

    const params = paramsFromForm(form);

    // ✅ 전체(value="" 또는 미존재)는 URL에서 place_class 제거
    if (!radio.value) {
      params.delete("place_class");
    }

    const url = buildUrl(params);
    fetchPartial(url, true);
  });

  // -------- 페이지네이션(A태그) 가로채기 --------
  document.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    const link = e.target.closest(".pagination a");
    if (!link) return;
    e.preventDefault();
    const href = link.getAttribute("href");
    if (!href) return;
    fetchPartial(href, true);
  });

    // -------- 태그칩(버튼) 토글 --------
  document.addEventListener("click", (e) => {
    const chip = e.target.closest(".tag-rail .chip:not(.more)");
    if (!chip || chip.tagName !== "BUTTON") return;
    e.preventDefault();

    const tag = chip.getAttribute("data-tag");
    if (!tag) return;

    // ✅ 먼저 active 클래스를 토글해서 시각적으로 반영
    chip.classList.toggle("active");

    const params = currentParams();
    toggleArrayParam(params, "tags", tag);
    const url = buildUrl(params);
    fetchPartial(url, true);
  });

})();
