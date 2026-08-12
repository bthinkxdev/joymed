"""HTTP views for the checkout app."""

from __future__ import annotations

import re
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.selectors import get_address_by_id, get_saved_addresses
from cart.selectors import get_cart_for_request, get_cart_summary
from cart.services import get_or_create_cart
from checkout.forms import CheckoutAddressForm, CheckoutDeliveryForm, CheckoutPaymentForm
from checkout.selectors import get_checkout_session_by_id
from checkout.services import create_checkout_session, place_order, update_checkout_session

from payments.registry import PAYMENT_GATEWAYS
from payments.services import process_payment


@require_GET
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Multi-step checkout page with gift Order Preview partial."""
    cart = get_or_create_cart(request=request)

    buy_now_product_id = request.GET.get("buy_now_product_id")
    buy_now_data = None
    is_buy_now = False
    
    if buy_now_product_id:
        is_buy_now = True
        buy_now_data = {
            "product_id": buy_now_product_id,
            "quantity": request.GET.get("buy_now_quantity", 1),
            "variant_id": request.GET.get("buy_now_variant_id")
        }



    if request.user.is_authenticated:
        from accounts.services import ensure_customer_profile_for_user
        profile = ensure_customer_profile_for_user(user=request.user)
    else:
        profile = None

    session = create_checkout_session(
        cart=cart,
        customer_profile=profile,
        session_key=request.session.session_key or "",
    )


    addresses = []
    if profile:
        from accounts.models import Address
        dashboard_address = profile.default_address
        if not dashboard_address:
            dashboard_address = Address.objects.select_related("city").filter(customer_profile=profile).first()
        if dashboard_address:
            addresses = [dashboard_address]
        elif hasattr(request.user, "wholesaler_profile"):
            from delivery.models import City
            from accounts.services import create_address
            wholesaler_addr = request.user.wholesaler_profile.address
            matched_city = None
            if wholesaler_addr:
                for city in City.objects.filter(is_active=True):
                    if city.name.lower() in wholesaler_addr.lower():
                        matched_city = city
                        break
            
            if matched_city:
                dashboard_address = create_address(
                    customer_profile=profile,
                    label="Registered Address",
                    line1=wholesaler_addr[:255],
                    line2="",
                    city_id=matched_city.pk,
                    is_default=True
                )
                addresses = [dashboard_address]
            
    if not request.headers.get("HX-Request") and not cart.destination_city_id and addresses and addresses[0].city_id:
        from cart.services import recalculate_delivery_charge
        recalculate_delivery_charge(cart=cart, destination_city=addresses[0].city)

    summary = get_cart_summary(cart=cart, buy_now_data=buy_now_data)
    if not summary.lines:
        return redirect("cms:homepage")
    
    from delivery.models import City
    active_cities = City.objects.filter(is_active=True)

    selected_gateway_key = None
    if session.order:
        last_tx = session.order.payment_transactions.last()
        if last_tx:
            selected_gateway_key = last_tx.gateway_key

    from payments.adapters.concrete import _get_razorpay_credentials
    razorpay_key, razorpay_secret = _get_razorpay_credentials()

    from core.services import get_site_settings
    vendor_upi_id = get_site_settings().vendor_upi_id.strip()

    available_gateways = {}
    for key, adapter in PAYMENT_GATEWAYS.items():
        if key.startswith("razorpay") and (not razorpay_key or not razorpay_secret):
            continue
        if key == "upi" and not vendor_upi_id:
            continue
        available_gateways[key] = adapter

    wholesaler_address = ""
    if hasattr(request.user, "wholesaler_profile"):
        wholesaler_address = request.user.wholesaler_profile.address

    from marketing.selectors import has_any_active_coupons
    
    return render(
        request,
        "checkout/checkout.html",
        {
            "cart": cart,
            "summary": summary,
            "checkout_session": session,
            "addresses": addresses,
            "active_cities": active_cities,

            "payment_gateways": available_gateways,
            "selected_gateway_key": selected_gateway_key,
            "wholesaler_address": wholesaler_address,
            "has_active_coupons": has_any_active_coupons(),
            "is_buy_now": is_buy_now,
            "buy_now_data": buy_now_data,
        },
    )


@require_http_methods(["POST"])
def checkout_update_city_view(request: HttpRequest) -> HttpResponse:
    """Update cart destination city via HTMX and redirect back to checkout to re-render summary."""
    cart = get_cart_for_request(request=request)
    if not cart:
        return HttpResponse(status=400)

    address_id_str = request.POST.get("address_id", "")
    guest_city_id_str = request.POST.get("guest_city_id", "")

    city_id = None
    if address_id_str and address_id_str != "new":
        from accounts.models import Address
        address = Address.objects.filter(pk=int(address_id_str)).first()
        if address:
            city_id = address.city_id
    elif guest_city_id_str:
        try:
            city_id = int(guest_city_id_str)
        except ValueError:
            pass

    if city_id:
        from delivery.models import City
        from cart.services import recalculate_delivery_charge
        city = City.objects.filter(pk=city_id).first()
        if city:
            recalculate_delivery_charge(cart=cart, destination_city=city)
    else:
        # if they selected "new" but didn't pick a city, or cleared the city, reset it
        cart.destination_city = None
        cart.delivery_charge = 0
        cart.save(update_fields=["destination_city", "delivery_charge", "updated_at"])

    url = reverse("checkout:checkout")
    buy_now_product_id = request.POST.get("buy_now_product_id")
    if buy_now_product_id:
        from urllib.parse import urlencode
        params = {
            "buy_now_product_id": buy_now_product_id,
            "buy_now_quantity": request.POST.get("buy_now_quantity", "1"),
        }
        buy_now_variant_id = request.POST.get("buy_now_variant_id")
        if buy_now_variant_id:
            params["buy_now_variant_id"] = buy_now_variant_id
        url += "?" + urlencode(params)

    return redirect(url)


@require_http_methods(["POST"])
def checkout_place_order_view(request: HttpRequest) -> HttpResponse:
    """Place order and process payment in one HTMX step."""
    form = CheckoutPaymentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "checkout/partials/errors.html",
            {"errors": form.errors},
            status=200,
        )

    cart = get_cart_for_request(request=request)
    if cart is None:
        raise Http404("Cart not found.")

    buy_now_product_id = request.POST.get("buy_now_product_id")
    buy_now_data = None
    
    if buy_now_product_id:
        buy_now_data = {
            "product_id": buy_now_product_id,
            "quantity": request.POST.get("buy_now_quantity", 1),
            "variant_id": request.POST.get("buy_now_variant_id")
        }

    if request.user.is_authenticated:
        from accounts.services import ensure_customer_profile_for_user
        profile = ensure_customer_profile_for_user(user=request.user)
    else:
        profile = None

    session = create_checkout_session(
        cart=cart,
        customer_profile=profile,
        session_key=request.session.session_key or "",
    )

    address = None
    address_form = CheckoutAddressForm(request.POST)
    if address_form.is_valid() and address_form.cleaned_data.get("address_id") and profile:
        address = get_address_by_id(
            address_id=address_form.cleaned_data["address_id"],
            customer_profile=profile,
        )
        if address:
            update_checkout_session(checkout_session=session, address=address)

    if not address:
        guest_name = request.POST.get("guest_name", "").strip()
        guest_email = request.POST.get("guest_email", "").strip()
        guest_phone = request.POST.get("guest_phone", "").strip()
        guest_address_line1 = request.POST.get("guest_address_line1", "").strip()
        guest_address_line2 = request.POST.get("guest_address_line2", "").strip()
        guest_city_id = request.POST.get("guest_city_id", "").strip()

        errors = {}
        if not guest_name: 
            errors["guest_name"] = ["Name is required."]
        elif not re.search(r'[A-Za-z]', guest_name):
            errors["guest_name"] = ["Name must contain alphabetic characters."]
            
        if not guest_email: 
            errors["guest_email"] = ["Email is required."]
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', guest_email):
            errors["guest_email"] = ["Enter a valid email address."]
            
        if not guest_phone: 
            errors["guest_phone"] = ["Phone is required."]
        elif not re.match(r'^\d{10}$', guest_phone):
            errors["guest_phone"] = ["Enter a valid 10-digit phone number."]
            
        if not guest_address_line1: 
            errors["guest_address_line1"] = ["Address Line 1 is required."]
        elif not re.search(r'[A-Za-z]', guest_address_line1):
            errors["guest_address_line1"] = ["Address must contain alphabetic characters."]
            
        if not guest_city_id: 
            errors["guest_city_id"] = ["City is required."]

        if errors:
            return render(
                request,
                "checkout/partials/errors.html",
                {"errors": errors},
                status=200,
            )

        if not request.user.is_authenticated:
            from accounts.services import login_or_create_customer_by_email
            from accounts.models import Address

            profile = login_or_create_customer_by_email(email=guest_email, name=guest_name)
            if guest_phone:
                profile.phone = guest_phone
                profile.save(update_fields=["phone", "updated_at"])

            address = Address.objects.filter(
                customer_profile=profile,
                line1=guest_address_line1,
                line2=guest_address_line2,
                city_id=int(guest_city_id),
            ).first()
            if not address:
                address = Address.objects.create(
                    customer_profile=profile,
                    line1=guest_address_line1,
                    line2=guest_address_line2,
                    city_id=int(guest_city_id),
                    label="Delivery Address"
                )
                
            if profile.default_address is None:
                from accounts.services import set_default_address
                set_default_address(customer_profile=profile, address_id=address.pk)
                
            update_checkout_session(checkout_session=session, address=address)
            
            #update session customer profile
            session.customer_profile = profile
            session.save(update_fields=["customer_profile", "updated_at"])
        else:
            from accounts.models import Address

            profile_updated = False
            if guest_phone and profile.phone != guest_phone:
                profile.phone = guest_phone
                profile_updated = True
            
            if profile_updated:
                profile.save(update_fields=["phone", "updated_at"])
                
            if guest_name and profile.user.first_name != guest_name:
                profile.user.first_name = guest_name
                profile.user.save(update_fields=["first_name"])

            address = Address.objects.filter(
                customer_profile=profile,
                line1=guest_address_line1,
                line2=guest_address_line2,
                city_id=int(guest_city_id),
            ).first()
            if not address:
                address = Address.objects.create(
                    customer_profile=profile,
                    line1=guest_address_line1,
                    line2=guest_address_line2,
                    city_id=int(guest_city_id),
                    label="Delivery Address"
                )
            
            if profile.default_address is None:
                from accounts.services import set_default_address
                set_default_address(customer_profile=profile, address_id=address.pk)
                
            update_checkout_session(checkout_session=session, address=address)

    delivery_form = CheckoutDeliveryForm(request.POST)
    if delivery_form.is_valid():
        update_checkout_session(
            checkout_session=session,
            delivery_date=delivery_form.cleaned_data.get("delivery_date"),
        )

    from catalog.exceptions import InsufficientStockError
    try:
        order = place_order(
            checkout_session_id=session.pk,
            idempotency_key=form.cleaned_data["idempotency_key"],
            customer_profile=profile,
            buy_now_data=buy_now_data,
        )
    except InsufficientStockError as e:
        return render(
            request,
            "checkout/partials/errors.html",
            {"errors": {"__all__": [str(e)]}},
            status=200,
        )

    payment_data = {}

    gateway_key = form.cleaned_data["gateway_key"]
    process_payment(
        order=order,
        gateway_key=gateway_key,
        payment_data=payment_data,
    )

    if gateway_key.startswith("razorpay"):
        pay_url = reverse("checkout:razorpay-pay", kwargs={"order_id": order.pk})
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = pay_url
            return response
        return redirect(pay_url)

    if gateway_key == "upi":
        pay_url = reverse("checkout:upi-pay", kwargs={"order_id": order.pk})
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = pay_url
            return response
        return redirect(pay_url)

    confirmation_url = reverse("checkout:confirmation", kwargs={"order_id": order.pk})
    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Redirect"] = confirmation_url
        return response
    return redirect(confirmation_url)


@require_GET
def checkout_confirmation_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Separate order confirmation / success page."""
    from orders.models import Order
    from django.shortcuts import get_object_or_404
    order = get_object_or_404(Order, pk=order_id)
    return render(
        request,
        "checkout/confirmation_page.html",
        {
            "order": order,
        },
    )


@require_GET
def upi_pay_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Render the direct merchant UPI payment page (QR code + app deep link)."""
    import base64
    import io
    from urllib.parse import quote

    import qrcode
    from django.shortcuts import get_object_or_404

    from core.services import get_site_settings
    from orders.models import Order

    order = get_object_or_404(Order, pk=order_id)
    site_settings = get_site_settings()
    vendor_upi_id = site_settings.vendor_upi_id.strip()
    if not vendor_upi_id:
        raise Http404("UPI payments are not configured.")

    payee_name = site_settings.site_name or "JOYMED HEALTHCARE"
    amount = str(order.total_amount)
    note = f"Order {order.order_number}"

    upi_uri = (
        "upi://pay?"
        f"pa={quote(vendor_upi_id)}"
        f"&pn={quote(payee_name)}"
        f"&am={quote(amount)}"
        "&cu=INR"
        f"&tn={quote(note)}"
    )

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_code_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return render(
        request,
        "checkout/upi_pay.html",
        {
            "order": order,
            "vendor_upi_id": vendor_upi_id,
            "upi_uri": upi_uri,
            "qr_code_data_uri": qr_code_data_uri,
        },
    )


@require_GET
def razorpay_pay_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Render Razorpay checkout payment page."""
    from orders.models import Order
    from payments.models import PaymentTransaction
    from payments.adapters.concrete import _get_razorpay_credentials
    from django.shortcuts import get_object_or_404

    order = get_object_or_404(Order, pk=order_id)
    payment_tx = PaymentTransaction.objects.filter(order=order, gateway_key__startswith="razorpay").last()
    key_id, _ = _get_razorpay_credentials()

    customer_name = ""
    customer_email = ""
    customer_phone = ""
    if order.customer_profile:
        customer_name = f"{order.customer_profile.user.first_name} {order.customer_profile.user.last_name}".strip() or order.customer_profile.user.username
        customer_email = order.customer_profile.user.email
        customer_phone = order.customer_profile.phone
    elif order.delivery_address_snapshot:
        customer_name = order.delivery_address_snapshot.get("recipient_name", "")
        customer_email = order.delivery_address_snapshot.get("email", "")
        customer_phone = order.delivery_address_snapshot.get("phone", "")

    amount_in_paise = int(order.total_amount * 100)
    currency_code = order.currency.code if order.currency else "INR"
    razorpay_order_id = payment_tx.external_intent_id if payment_tx else f"rzp_order_{order.pk}"

    #determine prefill method based on gateway key
    prefill_method = ""
    payment_method_name = "Razorpay"
    if payment_tx and payment_tx.gateway_key:
        if payment_tx.gateway_key == "razorpay_upi":
            prefill_method = "upi"
            payment_method_name = "UPI"
        elif payment_tx.gateway_key == "razorpay_card":
            prefill_method = "card"
            payment_method_name = "Credit/Debit Card"
        elif payment_tx.gateway_key == "razorpay_netbanking":
            prefill_method = "netbanking"
            payment_method_name = "Net Banking"
        elif payment_tx.gateway_key == "razorpay_wallet":
            prefill_method = "wallet"
            payment_method_name = "Wallet"

    #store order_id in session so the callback can retrieve it
    request.session["razorpay_order_pk"] = order.pk

    #build absolute callback URL for Razorpay redirect
    callback_url = request.build_absolute_uri(reverse("checkout:razorpay-callback"))
    cancel_url = request.build_absolute_uri(reverse("checkout:checkout"))

    return render(
        request,
        "checkout/razorpay_pay.html",
        {
            "order": order,
            "razorpay_key_id": key_id or "rzp_test_mock",
            "razorpay_order_id": razorpay_order_id,
            "amount_in_paise": amount_in_paise,
            "currency_code": currency_code,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "callback_url": callback_url,
            "cancel_url": cancel_url,
            "prefill_method": prefill_method,
            "payment_method_name": payment_method_name,
        },
    )


from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_callback_view(request: HttpRequest) -> HttpResponse:
    """
    Handle POST callback from Razorpay after payment.

    Razorpay redirects the full browser here with razorpay_payment_id,
    razorpay_order_id, and razorpay_signature as POST parameters.
    """
    from payments.models import PaymentTransaction
    from payments.adapters.concrete import RazorpayAdapter
    from payments.services import confirm_payment_success, confirm_payment_failed
    from django.shortcuts import get_object_or_404
    from orders.models import Order

    razorpay_payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_order_id = request.POST.get("razorpay_order_id", "")
    razorpay_signature = request.POST.get("razorpay_signature", "")

    #try order_id from POST (JS form submit) or session (Razorpay redirect)
    order_id = request.POST.get("order_id") or request.session.get("razorpay_order_pk")

    if not order_id:
        #fallback: look up order via Razorpay order ID stored in PaymentTransaction
        payment_tx = PaymentTransaction.objects.filter(
            external_intent_id=razorpay_order_id,
            gateway_key__startswith="razorpay",
        ).last()
        if payment_tx:
            order_id = payment_tx.order_id
        else:
            return redirect("checkout:checkout")

    order = get_object_or_404(Order, pk=order_id)
    payment_tx = PaymentTransaction.objects.filter(order=order, gateway_key__startswith="razorpay").last()

    #clean up session
    request.session.pop("razorpay_order_pk", None)

    adapter = RazorpayAdapter()
    is_valid = adapter.verify_payment_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
    )

    if is_valid and payment_tx:
        adapter.capture_payment(
            razorpay_payment_id=razorpay_payment_id,
            amount=payment_tx.amount,
            currency=payment_tx.currency.code if payment_tx.currency else "INR",
        )
        payment_tx.external_transaction_id = razorpay_payment_id
        payment_tx.save(update_fields=["external_transaction_id", "updated_at"])
        confirm_payment_success(payment_transaction=payment_tx)
        return redirect("checkout:confirmation", order_id=order.pk)
    else:
        if payment_tx:
            confirm_payment_failed(payment_transaction=payment_tx)
        return redirect("checkout:checkout")


@require_POST
def checkout_coupon_apply_view(request: HttpRequest) -> HttpResponse:
    """Validate and apply a coupon code from checkout."""
    from cart.forms import CartCouponForm
    from cart.services import apply_coupon
    from marketing.exceptions import InvalidCouponError
    from django.contrib import messages
    from cart.selectors import get_cart_for_request
    from django.utils.translation import gettext as _

    form = CartCouponForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Enter a valid coupon code."))
        return redirect("checkout:checkout")

    cart = get_cart_for_request(request=request)
    if cart is None:
        raise Http404("Cart not found.")

    try:
        apply_coupon(cart=cart, code=form.cleaned_data["code"])
        messages.success(request, _("Coupon applied successfully!"))
    except InvalidCouponError as exc:
        messages.error(request, str(exc))

    return redirect("checkout:checkout")


@require_POST
def checkout_coupon_remove_view(request: HttpRequest) -> HttpResponse:
    """Remove any applied coupon from the cart from checkout."""
    from cart.services import remove_coupon
    from cart.selectors import get_cart_for_request
    from django.contrib import messages
    from django.utils.translation import gettext as _
    
    cart = get_cart_for_request(request=request)
    if cart:
        remove_coupon(cart=cart)
        messages.success(request, _("Coupon removed."))
    return redirect("checkout:checkout")
