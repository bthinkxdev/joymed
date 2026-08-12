"""Read-only query functions for the cart app; views must not call the ORM directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Prefetch, Sum
from django.http import HttpRequest

from cart.models import Cart, CartItem
from catalog.models import ProductImage
from delivery.selectors import get_delivery_charge

_CART_CACHE_ATTR = "_floward_resolved_cart"


def get_cart_for_request(*, request: HttpRequest) -> Optional[Cart]:
    """
    Resolve the persistent cart for the current request (guest or authenticated).

    Query guarantee: at most 1 SELECT on cart_cart per request (request-scoped cache).
    """
    if hasattr(request, _CART_CACHE_ATTR):
        return getattr(request, _CART_CACHE_ATTR)

    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    cart = None
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        cart = (
            Cart.objects.filter(customer_profile=request.user.customer_profile)
            .select_related("currency", "destination_city")
            .first()
        )

    if cart is None:
        cart = (
            Cart.objects.filter(session_key=session_key)
            .select_related("currency", "destination_city")
            .first()
        )

    setattr(request, _CART_CACHE_ATTR, cart)
    return cart


@dataclass
class CartSummaryLine:
    """Hydrated cart line for templates and checkout."""

    item: CartItem
    product: Any
    variant: Any
    quantity: int
    unit_price_at_add: Decimal
    line_subtotal: Decimal
    has_insufficient_stock: bool = False
    max_stock: int = 0


@dataclass
class CartSummary:
    """Computed cart totals — single selector call, no N+1."""

    cart: Cart
    lines: list[CartSummaryLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0.00")
    coupon_code: str = ""
    coupon_discount: Decimal = Decimal("0.00")
    delivery_charge: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")
    item_count: int = 0
    has_insufficient_stock: bool = False


def get_cart_by_id(*, cart_id: int) -> Optional[Cart]:
    """
    Return a cart by primary key.

    Query guarantee: exactly 1 SELECT on cart_cart.
    """
    return Cart.objects.filter(pk=cart_id).select_related("currency", "destination_city").first()


def get_cart_item_count(*, cart: Cart | None) -> int:
    """
    Return total item quantity for a cart without hydrating line items.

    Query guarantee: exactly 1 aggregate SELECT on cart_cartitem (0 rows → 0).
    """
    if cart is None:
        return 0
    total = CartItem.objects.filter(cart=cart).aggregate(total=Sum("quantity"))["total"]
    return int(total or 0)


def get_cart_count(*, request: HttpRequest) -> int:
    """
    Return total item quantity in the persistent cart.

    Query guarantee: 0–1 SELECT (cart lookup) + 0–1 aggregate on cart items.
    """
    cart = get_cart_for_request(request=request)
    return get_cart_item_count(cart=cart)


def get_cart_product_ids(*, request: HttpRequest) -> set[int]:
    """Return a set of product IDs where ALL variants are in the cart, or it has no variants."""
    cart = get_cart_for_request(request=request)
    if not cart:
        return set()
        
    from django.db.models import Count
    from catalog.models import ProductVariant
    from cart.models import CartItem
    
    product_ids_in_cart = set(CartItem.objects.filter(cart=cart).values_list("product_id", flat=True))
    if not product_ids_in_cart:
        return set()
        
    completed = set()
    
    cart_items = CartItem.objects.filter(cart=cart, variant__isnull=False).values("product_id").annotate(variant_count=Count("variant", distinct=True))
    cart_variant_counts = {item["product_id"]: item["variant_count"] for item in cart_items}
    
    product_variants = ProductVariant.objects.filter(product_id__in=product_ids_in_cart, stock_quantity__gt=0).values("product_id").annotate(total_variants=Count("id"))
    total_variant_counts = {item["product_id"]: item["total_variants"] for item in product_variants}
    
    for pid in product_ids_in_cart:
        total = total_variant_counts.get(pid, 0)
        if total == 0:
            completed.add(pid)
        else:
            in_cart = cart_variant_counts.get(pid, 0)
            if in_cart >= total:
                completed.add(pid)
                
    return completed


def get_cart_item_keys(*, request: HttpRequest) -> set[str]:
    """Return a set of item keys in format 'pid_vid' or 'pid' for cart items."""
    cart = get_cart_for_request(request=request)
    if not cart:
        return set()
    from cart.models import CartItem
    qs = CartItem.objects.filter(cart=cart).values_list("product_id", "variant_id")
    keys = set()
    for pid, vid in qs:
        if vid:
            keys.add(f"{pid}_{vid}")
        else:
            keys.add(str(pid))
    return keys


def _wishlist_items_qs(*, request: HttpRequest):
    """Shared queryset for the current request's wishlist items."""
    from accounts.models import WishlistItem

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        return WishlistItem.objects.filter(
            wishlist__customer_profile=request.user.customer_profile
        )
    guest_id = request.session.get("guest_wishlist_id")
    if guest_id:
        return WishlistItem.objects.filter(wishlist_id=guest_id)
    if not request.session.session_key:
        return WishlistItem.objects.none()
    return WishlistItem.objects.filter(wishlist__session_key=request.session.session_key)


def get_wishlist_count(*, request: HttpRequest) -> int:
    """Return wishlist item count from the persistent Wishlist model."""
    return _wishlist_items_qs(request=request).count()


def get_wishlist_product_ids(*, request: HttpRequest) -> set[int]:
    """Return product IDs currently on the request wishlist."""
    return set(_wishlist_items_qs(request=request).values_list("product_id", flat=True))


def get_cart_summary(*, cart: Cart, only_item_ids: Optional[list[int]] = None, buy_now_data: Optional[dict] = None) -> CartSummary:
    """
    Return a fully computed cart summary for drawer, checkout, and payment.

    ``only_item_ids``, when given, scopes the summary to those specific cart
    lines only.
    ``buy_now_data``, when given, skips the DB and generates an in-memory
    CartSummaryLine for the "Buy Now" flow.
    """
    lines: list[CartSummaryLine] = []
    subtotal = Decimal("0.00")
    item_count = 0
    has_insufficient_stock = False

    if buy_now_data:
        from catalog.models import Product, ProductVariant
        product_id = buy_now_data.get("product_id")
        variant_id = buy_now_data.get("variant_id")
        quantity = int(buy_now_data.get("quantity", 1))

        product = Product.objects.filter(pk=product_id).prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True).order_by("display_order"),
                to_attr="primary_images",
            )
        ).first()
        
        if product:
            variant = ProductVariant.objects.filter(pk=variant_id).first() if variant_id else None
            user = cart.customer_profile.user if (cart.customer_profile and cart.customer_profile.user_id) else None
            
            from cart.services import _resolve_unit_price
            unit_price = _resolve_unit_price(product=product, variant=variant, user=user, quantity=quantity)
            line_subtotal = unit_price * quantity
            
            subtotal += line_subtotal
            item_count += quantity
            
            max_stock = variant.stock_quantity if variant else product.stock_quantity
            line_has_insufficient_stock = quantity > max_stock
            if line_has_insufficient_stock:
                has_insufficient_stock = True
                
            lines.append(
                CartSummaryLine(
                    item=None,  # type: ignore
                    product=product,
                    variant=variant,
                    quantity=quantity,
                    unit_price_at_add=unit_price,
                    line_subtotal=line_subtotal,
                    has_insufficient_stock=line_has_insufficient_stock,
                    max_stock=max_stock,
                )
            )
    else:
        items_qs = CartItem.objects.filter(cart=cart)
        if only_item_ids is not None:
            items_qs = items_qs.filter(pk__in=only_item_ids)
    
        items = list(
            items_qs
            .select_related(
                "product",
                "product__category",
                "product__brand",
                "variant",
            )
            .prefetch_related(
                Prefetch(
                    "product__images",
                    queryset=ProductImage.objects.filter(is_primary=True).order_by("display_order"),
                    to_attr="primary_images",
                ),
            )
            .order_by("id")
        )
    
        user = cart.customer_profile.user if (cart.customer_profile and cart.customer_profile.user_id) else None
        from cart.services import _resolve_unit_price

        for item in items:
            unit_price = _resolve_unit_price(
                product=item.product,
                variant=item.variant,
                user=user,
                quantity=item.quantity,
            )    
            line_subtotal = unit_price * item.quantity
            subtotal += line_subtotal
            item_count += item.quantity
            
            max_stock = item.variant.stock_quantity if item.variant else item.product.stock_quantity
            line_has_insufficient_stock = item.quantity > max_stock
            if line_has_insufficient_stock:
                has_insufficient_stock = True
    
            lines.append(
                CartSummaryLine(
                    item=item,
                    product=item.product,
                    variant=item.variant,
                    quantity=item.quantity,
                    unit_price_at_add=unit_price,
                    line_subtotal=line_subtotal,
                    has_insufficient_stock=line_has_insufficient_stock,
                    max_stock=max_stock,
                )
            )

    delivery_charge = cart.delivery_charge
    if cart.destination_city_id and delivery_charge == Decimal("0.00"):
        delivery_charge = get_delivery_charge(
            item_count=item_count,
            destination_city=cart.destination_city,
        )

    coupon_code = cart.coupon_code
    coupon_discount = Decimal("0.00")
    if coupon_code:
        from marketing.services import validate_coupon_for_cart
        from marketing.exceptions import InvalidCouponError
        category_ids = [line.product.category_id for line in lines]
        try:
            result = validate_coupon_for_cart(
                code=coupon_code,
                cart_subtotal=subtotal,
                customer_profile_id=cart.customer_profile_id,
                cart_category_ids=category_ids,
            )
            coupon_discount = result["discount_amount"]
        except InvalidCouponError:
            coupon_code = ""
            coupon_discount = Decimal("0.00")

    grand_total = max(subtotal - coupon_discount + delivery_charge, Decimal("0.00"))

    return CartSummary(
        cart=cart,
        lines=lines,
        subtotal=subtotal,
        coupon_code=coupon_code,
        coupon_discount=coupon_discount,
        delivery_charge=delivery_charge,
        grand_total=grand_total,
        item_count=item_count,
        has_insufficient_stock=has_insufficient_stock,
    )
