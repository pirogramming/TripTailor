document.addEventListener('DOMContentLoaded', function () {
  const list = $("#sortable-list");

  // jQuery UI로 드래그 순서 변경 가능하게
  list.sortable({
    placeholder: "ui-state-highlight",
    axis: "y"
  });

  // ✅ form 제출 전에 순서 정보를 hidden input에 넣어줌!
  const form = document.getElementById("update-route-form");
  form.addEventListener("submit", function (e) {
    const placeIds = list
        .children("li")
        .map(function () {
        return $(this).data("place-id");
        })
        .get(); // [12, 5, 9]

    const input = document.getElementById("place-ids-input");
    input.value = JSON.stringify(placeIds); // 서버는 JSON으로 기대하므로
    });

  // 장소 삭제 버튼 처리
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
