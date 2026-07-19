(function () {
  var variantSelect = document.getElementById('variant-select');
  if (variantSelect) {
    variantSelect.addEventListener('change', function () {
      var url = this.getAttribute('data-price-url');
      var vid = this.value;
      
      document.querySelectorAll('.pdp-variant-id-input').forEach(function(input) {
        input.value = vid;
      });

      fetch(url + (vid ? '?variant_id=' + vid : ''))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var el = document.getElementById('pdp-price');
          var elSticky = document.getElementById('pdp-sticky-price');
          var symbol = variantSelect.getAttribute('data-currency-symbol') || '₹';
          if (el) {
            if (data.is_wholesaler === 'true') {
              el.innerHTML = '<span class="text-muted small fw-normal">Wholesale Price:</span> ' + symbol + data.price + ' <span class="badge bg-success ms-1 small align-middle" style="font-size: 0.75rem;">Wholesale</span>';
            } else {
              el.textContent = symbol + data.price;
            }
          }
          if (elSticky) elSticky.textContent = symbol + data.price;
          var elRetail = document.getElementById('pdp-retail-price');
          if (elRetail && data.retail_price) {
            elRetail.textContent = symbol + data.retail_price;
          }
        });
    });
  }

  var citySelect = document.getElementById('delivery-city');
  if (citySelect) {
    citySelect.addEventListener('change', function () {
      var url = this.getAttribute('data-estimate-url') + '?city=' + this.value;
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var el = document.getElementById('delivery-estimate-text');
          if (el) el.textContent = 'Delivery: ' + data.label + ' to ' + data.city;
        });
    });
  }
})();
