"""HTTP views for the core app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

import json

from urllib.parse import urlencode
import threading
from django.core.mail import EmailMessage
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.contrib import messages
from django.shortcuts import get_object_or_404

from core.forms import ContactInquiryForm
from core.page_rerender import is_htmx_request, rerender_app_shell
from catalog.models import Product
from core.seo import seo_context
from core.services import get_site_settings


def health_view(request: HttpRequest) -> HttpResponse:
    """Return a simple 200 OK for load-balancer health probes."""
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def about_us_view(request: HttpRequest) -> HttpResponse:
    """Render the static About Us page."""
    context = seo_context(
        request=request,
        title=_("About Us | JOYMED HEALTHCARE"),
        description=_("Learn more about JOYMED HEALTHCARE and our mission to deliver products and services."),
    )
    return render(request, "core/about_us.html", context)


@require_GET
def privacy_policy_view(request: HttpRequest) -> HttpResponse:
    """Render the static Privacy Policy page."""
    context = seo_context(
        request=request,
        title=_("Privacy Policy | JOYMED HEALTHCARE"),
        description=_("Read JOYMED HEALTHCARE's privacy policy to learn how we collect and use your data."),
    )
    return render(request, "core/privacy_policy.html", context)


@require_GET
def contact_us_view(request: HttpRequest) -> HttpResponse:
    """Render the static Contact Us page with a contact form."""
    form = ContactInquiryForm()
    if request.user.is_authenticated:
        form.initial["name"] = request.user.get_full_name() or request.user.email
        form.initial["email"] = request.user.email

    is_quote_request = False
    product_id = request.GET.get("product")
    if product_id:
        try:
            product = Product.objects.get(pk=product_id)
            form.initial["product"] = product
            form.initial["message"] = f"I need a quotation for the product {product.name}."
            is_quote_request = True
        except Product.DoesNotExist:
            pass

    context = seo_context(
        request=request,
        title=_("Request a Quote | JOYMED HEALTHCARE") if is_quote_request else _("Contact Us | JOYMED HEALTHCARE"),
        description=_("Get in touch with JOYMED HEALTHCARE customer support."),
    )
    context["form"] = form
    context["is_quote_request"] = is_quote_request
    return render(request, "core/contact_us.html", context)


@require_POST
def submit_inquiry_view(request: HttpRequest) -> HttpResponse:
    """Handle contact form submissions."""
    form = ContactInquiryForm(request.POST)
    if form.is_valid():
        inquiry = form.save()
        
        site_settings = get_site_settings()
        
        #dispatch background email to vendor
        if site_settings.vendor_email:
            subject = f"New Inquiry from {inquiry.name}"
            product_info = f"Related Product: {inquiry.product.name}\n" if inquiry.product else ""
            message = (
                f"Name: {inquiry.name}\n"
                f"Email: {inquiry.email}\n"
                f"{product_info}\n"
                f"Message:\n{inquiry.message}"
            )
            
            def send_bg_email():
                #display name as the user, but actual sender as SMTP mail
                from_email_str = f'"{inquiry.name}" <{settings.DEFAULT_FROM_EMAIL}>'
                
                msg = EmailMessage(
                    subject=subject,
                    body=message,
                    from_email=from_email_str,
                    to=[site_settings.vendor_email],
                    reply_to=[inquiry.email]
                )
                try:
                    msg.send(fail_silently=True)
                except Exception:
                    pass
            threading.Thread(target=send_bg_email, daemon=True).start()

        #whatsApp redirect for Quote Requests
        if inquiry.product and site_settings.whatsapp_number:
            text_message = (
                f"Name: {inquiry.name}\n"
                f"Email: {inquiry.email}\n"
                f"Product: {inquiry.product.name}\n\n"
                f"{inquiry.message}"
            )
            query_string = urlencode({'text': text_message})
            wa_url = f"https://wa.me/{site_settings.whatsapp_number}?{query_string}"
            return redirect(wa_url)

        messages.success(request, _("Your message has been sent successfully. We will get back to you soon."))
    else:
        messages.error(request, _("There was an error sending your message. Please check the form and try again."))
    
    return redirect(request.META.get("HTTP_REFERER", "core:contact-us"))


@require_GET
def faq_view(request: HttpRequest) -> HttpResponse:
    """Render the static FAQ page."""
    context = seo_context(
        request=request,
        title=_("FAQ | JOYMED HEALTHCARE"),
        description=_("Frequently asked questions about ordering, delivery, and payments at JOYMED HEALTHCARE."),
    )
    return render(request, "core/faq.html", context)


@require_POST
def set_currency_view(request: HttpRequest) -> HttpResponse:
    """Persist currency code to session."""
    code = request.POST.get("currency", "INR")
    request.session["storefront_currency"] = code

    if not is_htmx_request(request):
        return redirect(request.META.get("HTTP_REFERER", "/"))

    return rerender_app_shell(request)


@require_POST
def set_country_view(request: HttpRequest) -> HttpResponse:
    """Persist the delivery country choice to session."""
    code = request.POST.get("country", "").strip().upper()
    request.session["storefront_country"] = code

    if not is_htmx_request(request):
        return redirect(request.META.get("HTTP_REFERER", "/"))

    return rerender_app_shell(request)
