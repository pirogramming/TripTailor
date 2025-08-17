document.addEventListener('DOMContentLoaded', () => {
  const deleteBtn = document.querySelector('.btn-delete');
  if (!deleteBtn) return;

  // CSRF cookie 헬퍼
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
  }

  deleteBtn.addEventListener('click', async (e) => {
    e.preventDefault();

    if (!confirm('정말 이 루트를 삭제하시겠습니까?')) return;

    // 1) data-*, 2) hidden input, 3) href/URL에서 파싱 순으로 시도
    const routeId =
      deleteBtn.dataset.routeId ||
      document.getElementById('route-id')?.value ||
      (deleteBtn.getAttribute('href') || location.pathname).match(/\/routes\/(\d+)/)?.[1];

    if (!routeId) {
      alert('route id를 찾을 수 없습니다.');
      return;
    }

    const fromPage =
      document.getElementById('from-page')?.value ||
      new URLSearchParams(location.search).get('from') ||
      '';

    const csrf =
      document.querySelector('input[name=csrfmiddlewaretoken]')?.value ||
      getCookie('csrftoken') ||
      '';

    try {
      const res = await fetch(`/routes/${routeId}/delete/?from=${encodeURIComponent(fromPage)}`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrf,
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
      });

      const data = await res.json();
      if (data.ok && data.redirect_url) {
        window.location.href = data.redirect_url;
      } else {
        alert('삭제 중 문제가 발생했습니다.');
      }
    } catch (err) {
      alert('네트워크 오류로 삭제에 실패했습니다.');
    }
  });
});
