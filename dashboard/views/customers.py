"""Customer and corporate account management."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.models import CorporateAccount, CorporateApprovalStatus, CustomerProfile, Wholesaler
from dashboard import forms
from dashboard.access import dashboard_required
from dashboard.views.base import DashboardListView, DashboardUpdateView


class CustomerListView(DashboardListView):
    model = CustomerProfile
    nav_section = "customers"
    url_basename = "customer"
    singular_name = "Customer"
    plural_name = "Customers"
    search_fields = ["user__email", "user__username", "phone"]
    select_related = ["user", "user__wholesaler_profile"]
    can_create = False
    can_delete = False
    template_name = "dashboard/customers/list.html"
    columns = [
        {"label": "Name", "name": "user.get_full_name"},
        {"label": "Email", "name": "user.email"},
        {"label": "Phone", "name": "get_phone"},
        {"label": "Type", "name": "get_customer_type_label"},
        {"label": "Verified", "name": "phone_verified", "type": "bool"},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        active_tab = self.request.GET.get("tab", "all").strip().lower()
        if active_tab == "retail":
            from django.db.models import Q
            qs = qs.filter(
                Q(user__wholesaler_profile__isnull=True) |
                ~Q(user__wholesaler_profile__approval_status="approved")
            )
        elif active_tab == "wholesale":
            qs = qs.filter(
                user__wholesaler_profile__isnull=False,
                user__wholesaler_profile__approval_status="approved"
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = self.request.GET.get("tab", "all").strip().lower()
        return context


class CustomerUpdateView(DashboardUpdateView):
    model = CustomerProfile
    form_class = forms.CustomerProfileForm
    nav_section = "customers"
    url_basename = "customer"
    singular_name = "Customer"


@dashboard_required
def customer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Customer profile with addresses and recent orders."""
    profile = get_object_or_404(CustomerProfile.objects.select_related("user"), pk=pk)
    context = {
        "nav_section": "customers",
        "page_title": str(profile),
        "profile": profile,
        "addresses": profile.addresses.select_related("city").all(),
        "orders": profile.orders.order_by("-created_at")[:10],
    }
    return render(request, "dashboard/customers/detail.html", context)


class CorporateListView(DashboardListView):
    model = CorporateAccount
    nav_section = "corporate"
    url_basename = "corporate"
    singular_name = "Corporate Account"
    plural_name = "Corporate Accounts"
    search_fields = ["company_name", "trade_license_number", "user__email"]
    select_related = ["user"]
    can_create = False
    can_delete = False
    columns = [
        {"label": "Company", "name": "company_name"},
        {"label": "License", "name": "trade_license_number"},
        {"label": "Contact", "name": "user.email"},
        {"label": "Status", "name": "get_approval_status_display", "type": "badge"},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(approval_status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["extra_filters"] = CorporateApprovalStatus.choices
        context["current_status"] = self.request.GET.get("status", "")
        return context


class CorporateUpdateView(DashboardUpdateView):
    model = CorporateAccount
    form_class = forms.CorporateAccountForm
    nav_section = "corporate"
    url_basename = "corporate"
    singular_name = "Corporate Account"

    def form_valid(self, form):
        status = form.cleaned_data.get("approval_status")
        if status in {CorporateApprovalStatus.APPROVED, CorporateApprovalStatus.REJECTED}:
            form.instance.approved_by = self.request.user
        return super().form_valid(form)


class WholesalerListView(DashboardListView):
    model = Wholesaler
    nav_section = "wholesalers"
    url_basename = "wholesaler"
    singular_name = "Wholesaler"
    plural_name = "Wholesalers"
    search_fields = ["company_name", "user__email", "phone_number"]
    select_related = ["user"]
    can_create = False
    can_delete = False
    columns = [
        {"label": "Wholesaler Name", "name": "user.get_full_name"},
        {"label": "Company Name", "name": "company_name"},
        {"label": "Email", "name": "user.email"},
        {"label": "Phone", "name": "phone_number"},
        {"label": "Place", "name": "place"},
        {"label": "Status", "name": "get_approval_status_display", "type": "badge"},
    ]


class WholesalerUpdateView(DashboardUpdateView):
    model = Wholesaler
    form_class = forms.WholesalerForm
    nav_section = "wholesalers"
    url_basename = "wholesaler"
    singular_name = "Wholesaler"

    def form_valid(self, form):
        old_status = self.get_object().approval_status
        new_status = form.cleaned_data.get("approval_status")

        if new_status == "approved":
            form.instance.approved_by = self.request.user

            if old_status != "approved":
                from django.utils.crypto import get_random_string
                from django.core.mail import send_mail
                from django.conf import settings
                from accounts.services import ensure_customer_profile_for_user

                #generate password
                password = get_random_string(8)
                user = form.instance.user
                user.set_password(password)
                user.save()

                #ensure customer profile
                ensure_customer_profile_for_user(user=user)

                #send email
                subject = "Your Wholesaler Account Has Been Approved!"
                message = (
                    f"Hello {user.get_full_name() or form.instance.company_name},\n\n"
                    f"Congratulations! Your wholesaler application for '{form.instance.company_name}' has been approved.\n\n"
                    f"You can now log in using the credentials below and access wholesale pricing:\n"
                    f"Email: {user.email}\n"
                    f"Password: {password}\n\n"
                    f"Please log in and update your password under your dashboard for security.\n\n"
                    f"Best regards,\nThe Joymed Team"
                )
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )

        elif new_status == "rejected":
            form.instance.approved_by = self.request.user

        return super().form_valid(form)

