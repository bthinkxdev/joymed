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
          if (el) el.textContent = symbol + data.price;
          if (elSticky) elSticky.textContent = symbol + data.price;
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
