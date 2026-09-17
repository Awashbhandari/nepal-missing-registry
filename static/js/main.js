// Live counter: poll /api/stats every 30s, update numbers in place (no animation).
(function () {
  var missingEl = document.getElementById("missing-count");
  var foundEl = document.getElementById("found-count");
  if (!missingEl || !foundEl) return;

  function refreshCounts() {
    fetch("/api/stats")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        missingEl.textContent = data.missing;
        foundEl.textContent = data.found_safe;
      })
      .catch(function () { /* fail silently, keep last known value */ });
  }

  setInterval(refreshCounts, 30000);
})();

// Live "already reported?" list on the report form. As the reporter types
// the name and fills in gender/address, this queries existing records and
// narrows the shown list down - so duplicates get caught before submit,
// not just after.
(function () {
  var section = document.getElementById("live-match-section");
  var list = document.getElementById("live-match-list");
  if (!section || !list) return;

  var fields = document.querySelectorAll(".match-field");

  function debounce(fn, wait) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, wait);
    };
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
  }

  function renderMatches(matches) {
    list.innerHTML = "";
    if (!matches.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    matches.forEach(function (p) {
      var statusClass = p.status === "missing" ? "status-missing" : "status-found";
      var statusText = p.status === "missing" ? "MISSING" : "FOUND SAFE";
      var thumb = p.photo_url
        ? '<img class="person-thumb" src="' + p.photo_url + '" alt="">'
        : '<span class="person-thumb person-thumb-empty" aria-hidden="true">?</span>';
      var ageGender = (p.age ? "Age " + p.age + " &middot; " : "") + (p.gender ? p.gender.charAt(0).toUpperCase() + p.gender.slice(1) : "");

      var li = document.createElement("li");
      li.className = "person-row";
      li.innerHTML =
        '<a class="person-link" target="_blank" href="' + p.detail_url + '">' +
          thumb +
          '<span class="person-info">' +
            '<span class="person-name">' + escapeHtml(p.full_name) + "</span>" +
            '<span class="person-meta">' + ageGender + "</span>" +
            '<span class="person-meta">' + escapeHtml(p.address || "Location not specified") + "</span>" +
          "</span>" +
          '<span class="person-status ' + statusClass + '">' + statusText + "</span>" +
        "</a>";
      list.appendChild(li);
    });
  }

  var runCheck = debounce(function () {
    var nameEl = document.getElementById("full_name");
    var name = nameEl ? nameEl.value.trim() : "";
    if (name.length < 2) {
      section.hidden = true;
      return;
    }

    var params = new URLSearchParams();
    params.set("full_name", name);
    var fieldMap = {
      gender: "gender",
      last_seen_district: "district",
      last_seen_municipality: "municipality",
      last_seen_ward_no: "ward_no",
      last_seen_landmark: "landmark"
    };
    Object.keys(fieldMap).forEach(function (elId) {
      var el = document.getElementById(elId);
      if (el && el.value.trim()) params.set(fieldMap[elId], el.value.trim());
    });

    fetch("/api/live-match?" + params.toString())
      .then(function (r) { return r.json(); })
      .then(renderMatches)
      .catch(function () { /* fail silently */ });
  }, 350);

  fields.forEach(function (el) {
    el.addEventListener("input", runCheck);
    el.addEventListener("change", runCheck);
  });
})();

// Compress photo client-side before upload, so people on slow/expensive
// mobile data don't have to upload large camera photos.
(function () {
  var input = document.getElementById("photo");
  if (!input) return;

  var MAX_DIMENSION = 900;   // px
  var JPEG_QUALITY = 0.7;

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file || !file.type.startsWith("image/")) return;

    var img = new Image();
    var reader = new FileReader();

    reader.onload = function (e) {
      img.onload = function () {
        var canvas = document.createElement("canvas");
        var scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height));
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;

        var ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        canvas.toBlob(function (blob) {
          if (!blob) return;
          var compressedFile = new File([blob], "photo.jpg", { type: "image/jpeg" });
          var dt = new DataTransfer();
          dt.items.add(compressedFile);
          input.files = dt.files;
        }, "image/jpeg", JPEG_QUALITY);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
})();
