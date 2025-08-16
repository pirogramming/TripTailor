document.addEventListener('DOMContentLoaded', function () {
  const deleteBtn = document.querySelector(".btn-delete");
  if (!deleteBtn) return;

  deleteBtn.addEventListener("click", function (e) {
    e.preventDefault();  // a 태그 본래 이동 막기

    const confirmed = confirm("정말 이 루트를 삭제하시겠습니까?");
    if (!confirmed) return;

    const routeId = document.getElementById("route-id").value;
    const fromPage = document.getElementById("from-page").value;

    fetch(`/routes/${routeId}/delete/?from=${fromPage}`, {
      method: "POST",
      headers: {
        "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.ok && data.redirect_url) {
          window.location.href = data.redirect_url;
        } else {
          alert("삭제 중 문제가 발생했습니다.");
        }
      });
  });
});
