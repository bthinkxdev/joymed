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

          if (data.is_in_cart !== undefined) {
            var addGroup = document.getElementById('pdp-add-to-cart-group');
            var viewGroup = document.getElementById('pdp-view-cart-group');
            var buyBtn = document.querySelector('#buy-form button[type="submit"]');

            if (data.is_in_cart) {
              if (addGroup && data.is_wholesaler !== 'true') addGroup.classList.add('d-none');
              if (viewGroup && data.is_wholesaler !== 'true') viewGroup.classList.remove('d-none');
              if (buyBtn && data.is_wholesaler === 'true') buyBtn.innerText = 'Update Cart';
            } else {
              if (addGroup) addGroup.classList.remove('d-none');
              if (viewGroup) viewGroup.classList.add('d-none');
              if (buyBtn && data.is_wholesaler === 'true') buyBtn.innerText = 'Add to Cart';
            }
          }

          var stockContainer = document.getElementById('pdp-stock-container');
          if (stockContainer && data.stock_quantity !== undefined) {
            var qtyInt = parseInt(data.stock_quantity, 10);
            var inStockText = stockContainer.getAttribute('data-in-stock') || 'In stock';
            var outStockText = stockContainer.getAttribute('data-out-stock') || 'Out of stock';
            
            if (qtyInt > 0) {
              stockContainer.className = 'jm-pdp-buybox__stock is-in';
              stockContainer.innerHTML = inStockText + ' <span id="pdp-stock-quantity">&middot; ' + qtyInt + '</span>';
            } else {
              stockContainer.className = 'jm-pdp-buybox__stock is-out';
              stockContainer.innerHTML = outStockText;
            }
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
