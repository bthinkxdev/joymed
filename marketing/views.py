"""HTTP views for the marketing app; thin request parsing delegating to selectors/services."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from marketing.forms import NewsletterSignupForm
from marketing.services import subscribe_newsletter


@require_POST
def newsletter_subscribe_view(request: HttpRequest) -> HttpResponse:
    """Subscribe an email to the newsletter from the homepage form."""
    form = NewsletterSignupForm(request.POST)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept', '').startswith('application/json')
    
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({"success": False, "errors": form.errors})
        return redirect(request.META.get("HTTP_REFERER", "/"))
        
    subscribe_newsletter(email=form.cleaned_data["email"])
    if is_ajax:
        return JsonResponse({"success": True, "message": "Successfully subscribed to the newsletter."})
    return redirect(request.META.get("HTTP_REFERER", "/"))