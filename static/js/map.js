// 전역 콜백 (Google Maps script의 &callback=initMap 이 호출)
window.initMap = function () {
  const nodes = document.querySelectorAll('.place-item__map');
  if (!nodes.length) return;

  nodes.forEach((node) => {
    // if (node.offsetHeight === 0) {
    //     node.style.height = '300px'; // 최소 높이 설정
    // }

    const lat = parseFloat(node.dataset.lat);
    const lng = parseFloat(node.dataset.lng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      console.warn('잘못된 좌표:', node, lat, lng);
      return;
    }

    // 지도 생성
    const map = new google.maps.Map(node, {
      center: { lat, lng },
      zoom: 16,
      disableDefaultUI: true,   // 작은 박스용으로 UI 최소화
      zoomControl: true,        // 확대/축소만 허용
      gestureHandling: 'greedy' // 스크롤 안에서 편하게 확대/축소
    });

    // 마커
    new google.maps.Marker({
      map,
      position: { lat, lng },
      // label: "", // 필요 시 라벨 사용
    });

    // (선택) 화면에 보일 때만 그리려면 IntersectionObserver로 lazy-init 가능
  });
};

// 혹시 스크립트 로딩이 매우 빨라서 DOM이 아직 안 만들어진 경우 대비
document.addEventListener('DOMContentLoaded', () => {
  if (window.google && window.google.maps && typeof window.initMap === 'function') {
    // Google JS가 이미 로드되어 있으면 직접 실행
    window.initMap();
  }
});