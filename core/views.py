"""HTTP views for the core app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from core.page_rerender import is_htmx_request, rerender_app_shell
from core.seo import seo_context


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
    """Render the static Contact Us page."""
    context = seo_context(
        request=request,
        title=_("Contact Us | JOYMED HEALTHCARE"),
        description=_("Get in touch with JOYMED HEALTHCARE customer support."),
    )
    return render(request, "core/contact_us.html", context)


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
