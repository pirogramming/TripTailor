// 전역 콜백 (Google Maps script의 &callback=initMap 이 호출)
window.initMap = function () {
  const nodes = document.querySelectorAll('.place-item__map');
  if (!nodes.length) return;

  nodes.forEach((node) => {
    // ✅ 이미 초기화된 노드는 건너뛰기
    if (node.dataset.mapInitialized === 'true') return;

    const lat = parseFloat(node.dataset.lat);
    const lng = parseFloat(node.dataset.lng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      console.warn('잘못된 좌표:', node, lat, lng);
      return;
    }

    const map = new google.maps.Map(node, {
      center: { lat, lng },
      zoom: 16,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: 'greedy'
    });

    new google.maps.Marker({
      map,
      position: { lat, lng },
    });

    // ✅ 중복 생성 방지를 위한 플래그
    node.dataset.mapInitialized = 'true';
  });
};

// 혹시 스크립트 로딩이 매우 빨라서 DOM이 아직 안 만들어진 경우 대비
document.addEventListener('DOMContentLoaded', () => {
  if (window.google && window.google.maps && typeof window.initMap === 'function') {
    window.initMap();
  }
});