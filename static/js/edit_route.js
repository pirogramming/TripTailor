document.addEventListener('DOMContentLoaded', function () {
  const list = $("#sortable-list");

  list.sortable({
    placeholder: "ui-state-highlight",
    axis: "y"
  });

  $("#save-order-btn").on("click", function () {
    const placeIds = list
      .children("li")
      .map(function () {
        return $(this).data("place-id");
      })
      .get();

    fetch(window.location.pathname.replace(/\/edit\/?$/, "/update_order/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken()
      },
      body: JSON.stringify({ place_ids: placeIds })
    })
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          alert("순서가 저장되었습니다!");
        } else {
          alert("오류: " + data.error);
        }
      });
  });

  list.on("click", ".delete-btn", function () {
  const placeId = $(this).data("place-id");
  const confirmed = confirm("정말 삭제하시겠습니까?");
  if (!confirmed) return;

  const self = this;

  fetch(window.location.pathname.replace(/\/edit\/?$/, `/remove_place/${placeId}/`), {
    method: "POST",
    headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCSRFToken()
    }
  })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        // 🔥 직접 DOM 제거
        const $li = $(self).closest("li");
        $li.slideUp(300, function () {
          $li.remove();
        });
      } else {
        alert("삭제에 실패했어요: " + data.error);
      }
    })
    .catch(err => {
      alert("오류 발생: " + err);
    });
});


  function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
  }
});
