"""ModelForms used by the admin dashboard CRUD screens."""

from __future__ import annotations

from django import forms
from django.utils.text import slugify

from accounts.models import CustomerProfile, Wholesaler
from catalog.models import (
    Brand,
    Category,
    Product,
    ProductDocument,
    ProductImage,
    ProductSpecification,
    ProductVariant,
    ProductWholesaleTier,
    Review,
)
from cms.models import BlogPost, FAQItem, HeroSlide, HomepageSection, Page, PolicyDocument
from core.models import SiteSettings
from delivery.models import City
from marketing.models import Coupon, FlashSale, NewsletterSubscriber

_DATE = forms.DateInput(attrs={"type": "date"})
_DATETIME = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
_TIME = forms.TimeInput(attrs={"type": "time"})


class SlugAutoMixin(forms.ModelForm):
    """Auto-populate an empty ``slug`` from ``name``/``title`` on save."""

    def clean(self):
        cleaned = super().clean()
        if "slug" in self.fields and not cleaned.get("slug"):
            source = cleaned.get("name") or cleaned.get("title")
            if source:
                cleaned["slug"] = slugify(source)
        return cleaned


class ProductForm(SlugAutoMixin):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "sku",
            "category",
            "brand",
            "base_price",
            "mrp",
            "purchase_price",
            "wholesale_rate",
            "is_rental",
            "rental_price",
            "show_rental_storefront",
            "color",
            "stock_quantity",
            "low_stock_threshold",
            "is_active",
            "is_featured",
            "is_bestseller",
            "is_new_arrival",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        error_messages = {
            "name": {"required": "Product name is required."},
            "sku": {"required": "SKU is required."},
            "category": {"required": "Category is required."},
            "base_price": {"required": "Base price is required."},
            "mrp": {"required": "MRP is required."},
            "purchase_price": {"required": "Purchase price is required."},
            "stock_quantity": {"required": "Stock quantity is required."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_wholesale_rate(self):
        rate = self.cleaned_data.get("wholesale_rate")
        if rate is None:
            return 0
        return rate



class CategoryForm(SlugAutoMixin):
    class Meta:
        model = Category
        fields = [
            "name",
            "slug",
            "parent",
            "display_order",
            "is_active",
            "meta_title",
            "meta_description",
            "og_image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False



class BrandForm(SlugAutoMixin):
    class Meta:
        model = Brand
        fields = ["name", "slug", "logo", "is_featured"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False



class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["moderation_status"]


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["variant_type", "name", "price_delta", "sku_suffix", "stock_quantity"]
        widgets = {
            "variant_type": forms.TextInput(attrs={
                "list": "variant-type-list",
                "class": "form-control",
                "placeholder": "e.g. Size, Packaging, Color"
            }),
        }
        error_messages = {
            "variant_type": {"required": "Variant type is required."},
            "name": {"required": "Name is required."},
            "price_delta": {"required": "Price delta is required."},
            "sku_suffix": {"required": "SKU suffix is required."},
            "stock_quantity": {"required": "Stock quantity is required."},
        }

    def has_changed(self):
        """Ignore empty extra forms even if fields have model defaults (like stock_quantity=0)."""
        changed = super().has_changed()
        if changed:
            #if every field in the POST data is empty, it's an untouched extra form.
            for name in self.fields:
                prefixed_name = self.add_prefix(name)
                val = self.data.get(prefixed_name)
                if val:  #any non-empty string means user interacted
                    return True
            return False
        return changed

ProductVariantFormSet = forms.inlineformset_factory(
    Product,
    ProductVariant,
    form=ProductVariantForm,
    extra=1,
    can_delete=True,
)

class ProductWholesaleTierForm(forms.ModelForm):
    class Meta:
        model = ProductWholesaleTier
        fields = ["min_quantity", "max_quantity", "price"]
        error_messages = {
            "min_quantity": {"required": "Minimum quantity is required."},
            "max_quantity": {"required": "Maximum quantity is required."},
            "price": {"required": "Wholesale price is required."},
        }

ProductWholesaleTierFormSet = forms.inlineformset_factory(
    Product,
    ProductWholesaleTier,
    form=ProductWholesaleTierForm,
    extra=1,
    can_delete=True,
)

class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "display_order", "is_primary"]
        error_messages = {
            "image": {"required": "Image file is required."},
            "alt_text": {"required": "Alt text is required."},
            "display_order": {"required": "Display order is required."},
        }

ProductImageFormSet = forms.inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,
    extra=1,
    can_delete=True,
)
class ProductSpecificationForm(forms.ModelForm):
    class Meta:
        model = ProductSpecification
        fields = ["name", "value", "display_order"]
        error_messages = {
            "name": {"required": "Specification name is required."},
            "value": {"required": "Value is required."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_order"].required = False
        if not self.instance.pk:
            self.initial["display_order"] = None

    def clean_display_order(self):
        val = self.cleaned_data.get("display_order")
        return val if val is not None else 0


class ProductDocumentForm(forms.ModelForm):
    class Meta:
        model = ProductDocument
        fields = ["title", "document_file", "display_order"]
        widgets = {
            "document_file": forms.FileInput(),
        }
        error_messages = {
            "title": {"required": "Document title is required."},
            "document_file": {"required": "Document file is required."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_order"].required = False
        if not self.instance.pk:
            self.initial["display_order"] = None

    def clean_display_order(self):
        val = self.cleaned_data.get("display_order")
        return val if val is not None else 0



ProductSpecificationFormSet = forms.inlineformset_factory(
    Product,
    ProductSpecification,
    form=ProductSpecificationForm,
    extra=1,
    can_delete=True,
)
ProductDocumentFormSet = forms.inlineformset_factory(
    Product,
    ProductDocument,
    form=ProductDocumentForm,
    extra=1,
    can_delete=True,
)


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = [
            "phone",
            "phone_verified",
            "notify_via_email",
            "notify_via_sms",
            "notify_via_whatsapp",
        ]



class WholesalerForm(forms.ModelForm):
    name = forms.CharField(max_length=150, required=True, label="Contact Name")
    email = forms.EmailField(required=True, label="Email Address")

    class Meta:
        model = Wholesaler
        fields = ["company_name", "phone_number", "gst", "address", "approval_status"]

    field_order = [
        "name",
        "company_name",
        "email",
        "phone_number",
        "gst",
        "address",
        "approval_status",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields["name"].initial = (
                self.instance.user.get_full_name() or self.instance.user.first_name
            )
            self.fields["email"].initial = self.instance.user.email

    def save(self, commit=True):
        wholesaler = super().save(commit=False)
        name = self.cleaned_data.get("name", "").strip()
        email = self.cleaned_data.get("email", "").strip().lower()
        if wholesaler.user:
            if name:
                name_parts = name.split(" ", 1)
                wholesaler.user.first_name = name_parts[0]
                wholesaler.user.last_name = name_parts[1] if len(name_parts) > 1 else ""
            if email:
                wholesaler.user.email = email
                wholesaler.user.username = email
            wholesaler.user.save()

            if hasattr(wholesaler.user, "customer_profile"):
                profile = wholesaler.user.customer_profile
                if profile.phone != wholesaler.phone_number:
                    profile.phone = wholesaler.phone_number
                    profile.save(update_fields=["phone"])
        if commit:
            wholesaler.save()
        return wholesaler



class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code",
            "discount_type",
            "discount_value",
            "min_order_value",
            "max_uses",
            "max_uses_per_customer",
            "valid_from",
            "valid_until",
            "applicable_categories",
            "is_active",
        ]
        widgets = {"valid_from": _DATETIME, "valid_until": _DATETIME}



class FlashSaleForm(forms.ModelForm):
    class Meta:
        model = FlashSale
        fields = ["name", "products", "discount_percentage", "starts_at", "ends_at", "is_active"]
        widgets = {"starts_at": _DATETIME, "ends_at": _DATETIME}


class NewsletterSubscriberForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email", "is_active"]


class HomepageSectionForm(forms.ModelForm):
    class Meta:
        model = HomepageSection
        fields = ["section_type", "title", "display_order", "is_active", "config"]


class HeroSlideForm(forms.ModelForm):
    class Meta:
        model = HeroSlide
        fields = ["title", "image", "video", "poster", "display_order", "is_active"]


class BlogPostForm(SlugAutoMixin):
    class Meta:
        model = BlogPost
        fields = [
            "title",
            "slug",
            "excerpt",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class PageForm(SlugAutoMixin):
    class Meta:
        model = Page
        fields = [
            "title",
            "slug",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class FAQItemForm(forms.ModelForm):
    class Meta:
        model = FAQItem
        fields = ["question", "answer", "display_order", "is_published", "publish_at"]
        widgets = {"publish_at": _DATETIME}


class PolicyDocumentForm(SlugAutoMixin):
    class Meta:
        model = PolicyDocument
        fields = [
            "title",
            "slug",
            "policy_type",
            "body",
            "is_published",
            "publish_at",
            "meta_title",
            "meta_description",
            "og_image",
        ]
        widgets = {"publish_at": _DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class CityForm(SlugAutoMixin):
    class Meta:
        model = City
        fields = [
            "country",
            "name",
            "slug",
            "delivery_charge_base",
            "same_day_cutoff_hour",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False





class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            "site_name",
            "logo",
            "primary_color",
            "secondary_color",
            "font_family",
            "facebook_url",
            "instagram_url",
            "twitter_url",
            "whatsapp_number",
            "vendor_email",
            "tax_rate_percent",
            "default_shipping_charge",
            "razorpay_key_id",
            "razorpay_key_secret",
            "vendor_upi_id",
        ]
        labels = {
            "vendor_email": "Email",
            "vendor_upi_id": "Merchant UPI ID",
        }


class OrderStatusForm(forms.Form):
    """Free-standing form for applying an order status transition."""

    new_status = forms.ChoiceField(choices=[])
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, allowed_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_status"].choices = allowed_choices or []
