"""Django forms for the marketing app."""

from __future__ import annotations

from django import forms


class NewsletterSignupForm(forms.Form):
    """Public-facing newsletter signup form."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            from marketing.models import NewsletterSubscriber
            if NewsletterSubscriber.objects.filter(email=email).exists():
                raise forms.ValidationError("This email is already subscribed.")
        return email