(function () {
  var variantSelect = document.getElementById('variant-select');
  if (variantSelect) {
    variantSelect.addEventListener('change', function () {
      var url = this.getAttribute('data-price-url');
      var vid = this.value;
      
      document.querySelectorAll('.pdp-variant-id-input').forEach(function(input) {
        input.value = vid;
      });

      var qtyInput = document.getElementById('pdp-qty');
      var qty = qtyInput ? qtyInput.value : '1';
      var queryString = '?quantity=' + qty + (vid ? '&variant_id=' + vid : '');

      fetch(url + queryString)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var el = document.getElementById('pdp-price');
          var elSticky = document.getElementById('pdp-sticky-price');
          var retailContainer = document.getElementById('pdp-retail-price-container');
          var symbol = variantSelect.getAttribute('data-currency-symbol') || '₹';
          var elPriceValue = document.getElementById('pdp-price-value');
          var wholesaleLabel = document.getElementById('pdp-price-wholesale-label');
          var wholesaleBadge = document.getElementById('pdp-price-wholesale-badge');
          
          if (elPriceValue) {
            elPriceValue.textContent = symbol + parseFloat(data.price).toFixed(2).replace(/\.00$/, '');
          }
          
          if (data.is_tier_active === 'true') {
            if (wholesaleLabel) wholesaleLabel.classList.remove("d-none");
            if (wholesaleBadge) wholesaleBadge.classList.remove("d-none");
            if (retailContainer) retailContainer.classList.remove("d-none");
          } else {
            if (wholesaleLabel) wholesaleLabel.classList.add("d-none");
            if (wholesaleBadge) wholesaleBadge.classList.add("d-none");
            if (retailContainer) retailContainer.classList.add("d-none");
          }
          if (elSticky) elSticky.textContent = symbol + parseFloat(data.price).toFixed(2).replace(/\.00$/, '');
          var elRetail = document.getElementById('pdp-retail-price');
          if (elRetail && data.retail_price) {
            elRetail.textContent = symbol + parseFloat(data.retail_price).toFixed(2).replace(/\.00$/, '');
          }
          var elRetailVal = document.getElementById('pdp-retail-price-val');
          if (elRetailVal && data.retail_price) {
            elRetailVal.value = data.retail_price;
          }
        });
    });

    if (variantSelect.value) {
      variantSelect.dispatchEvent(new Event('change'));
    }
  }

  var citySelect = document.getElementById('delivery-city');
  if (citySelect) {
    citySelect.addEventListener('change', function () {
      if (!this.value) {
        return;
      }
      var url = this.getAttribute('data-estimate-url') + '?city=' + encodeURIComponent(this.value);
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var el = document.getElementById('delivery-estimate-text');
          if (el) el.textContent = 'Delivery: ' + data.label + ' to ' + data.city;
        });
    });
  }
})();
