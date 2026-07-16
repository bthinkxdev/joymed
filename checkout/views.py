"""HTTP views for the checkout app."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.selectors import get_address_by_id, get_saved_addresses
from cart.selectors import get_cart_for_request, get_cart_summary
from cart.services import get_or_create_cart
from checkout.forms import CheckoutAddressForm, CheckoutDeliveryForm, CheckoutPaymentForm
from checkout.selectors import get_checkout_session_by_id
from checkout.services import create_checkout_session, place_order, update_checkout_session
from delivery.selectors import get_available_slots
from payments.registry import PAYMENT_GATEWAYS
from payments.services import process_payment


@require_GET
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Multi-step checkout page with gift Order Preview partial."""
    cart = get_or_create_cart(request=request)
    summary = get_cart_summary(cart=cart)
    if not summary.lines:
        return redirect("catalog:plp")

    profile = request.user.customer_profile if request.user.is_authenticated and hasattr(request.user, "customer_profile") else None
    session = create_checkout_session(
        cart=cart,
        customer_profile=profile,
        session_key=request.session.session_key or "",
    )
    preview_lines = [
        {"product": line.product, "snapshot": line.gift_snapshot} for line in summary.lines
    ]
    city = session.address.city if session.address_id else None
    delivery_date = session.delivery_date.isoformat() if session.delivery_date else None
    delivery_slots = []
    if city and delivery_date:
        delivery_slots = get_available_slots(city=city, delivery_date=delivery_date)

    addresses = get_saved_addresses(customer_profile=profile, page=1)["results"] if profile else []
    from delivery.models import City
    active_cities = City.objects.filter(is_active=True)

    return render(
        request,
        "checkout/checkout.html",
        {
            "checkout_session": session,
            "summary": summary,
            "preview_lines": preview_lines,
            "addresses": addresses,
            "active_cities": active_cities,
            "delivery_slots": delivery_slots,
            "payment_gateways": PAYMENT_GATEWAYS,
        },
    )


@require_http_methods(["POST"])
def checkout_place_order_view(request: HttpRequest) -> HttpResponse:
    """Place order and process payment in one HTMX step."""
    form = CheckoutPaymentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "checkout/partials/errors.html",
            {"errors": form.errors},
            status=400,
        )

    cart = get_cart_for_request(request=request)
    if cart is None:
        raise Http404("Cart not found.")

    profile = request.user.customer_profile if request.user.is_authenticated and hasattr(request.user, "customer_profile") else None
    session = create_checkout_session(cart=cart, customer_profile=profile, session_key=request.session.session_key or "")
    
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
        if not request.user.is_authenticated:
            guest_name = request.POST.get("guest_name", "").strip()
            guest_email = request.POST.get("guest_email", "").strip()
            guest_phone = request.POST.get("guest_phone", "").strip()
            guest_address_line1 = request.POST.get("guest_address_line1", "").strip()
            guest_address_line2 = request.POST.get("guest_address_line2", "").strip()
            guest_city_id = request.POST.get("guest_city_id", "").strip()

            errors = {}
            if not guest_name: errors["guest_name"] = ["Name is required."]
            if not guest_email: errors["guest_email"] = ["Email is required."]
            if not guest_phone: errors["guest_phone"] = ["Phone is required."]
            if not guest_address_line1: errors["guest_address_line1"] = ["Address Line 1 is required."]
            if not guest_city_id: errors["guest_city_id"] = ["City is required."]

            if errors:
                return render(
                    request,
                    "checkout/partials/errors.html",
                    {"errors": errors},
                    status=400,
                )

            from accounts.services import login_or_create_customer_by_email
            from accounts.models import Address
            from django.contrib.auth import login

            profile = login_or_create_customer_by_email(email=guest_email, name=guest_name)
            if guest_phone:
                profile.phone = guest_phone
                profile.save(update_fields=["phone", "updated_at"])

            #log the guest in so their session matches
            login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")

            address = Address.objects.create(
                customer_profile=profile,
                label="Guest Address",
                line1=guest_address_line1,
                line2=guest_address_line2,
                city_id=int(guest_city_id),
            )
            update_checkout_session(checkout_session=session, address=address)
            
            #update session customer profile
            session.customer_profile = profile
            session.save(update_fields=["customer_profile", "updated_at"])
        else:
            guest_address_line1 = request.POST.get("guest_address_line1", "").strip()
            guest_address_line2 = request.POST.get("guest_address_line2", "").strip()
            guest_city_id = request.POST.get("guest_city_id", "").strip()

            errors = {}
            if not guest_address_line1: errors["guest_address_line1"] = ["Address Line 1 is required."]
            if not guest_city_id: errors["guest_city_id"] = ["City is required."]

            if errors:
                return render(
                    request,
                    "checkout/partials/errors.html",
                    {"errors": errors},
                    status=400,
                )

            from accounts.models import Address
            address = Address.objects.create(
                customer_profile=profile,
                label="Delivery Address",
                line1=guest_address_line1,
                line2=guest_address_line2,
                city_id=int(guest_city_id),
            )
            update_checkout_session(checkout_session=session, address=address)

    delivery_form = CheckoutDeliveryForm(request.POST)
    if delivery_form.is_valid():
        update_checkout_session(
            checkout_session=session,
            delivery_date=delivery_form.cleaned_data.get("delivery_date"),
            delivery_slot_id=delivery_form.cleaned_data.get("delivery_slot_id"),
        )

    order = place_order(
        checkout_session_id=session.pk,
        idempotency_key=form.cleaned_data["idempotency_key"],
        customer_profile=profile,
    )

    payment_data = {}
    if form.cleaned_data.get("voucher_code"):
        payment_data["voucher_code"] = form.cleaned_data["voucher_code"]

    process_payment(
        order=order,
        gateway_key=form.cleaned_data["gateway_key"],
        payment_data=payment_data,
    )

    return render(
        request,
        "checkout/confirmation.html",
        {
            "order": order,
            "checkout_session": get_checkout_session_by_id(session_id=session.pk),
        },
    )
