import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from apps.organizations.models import Organization
from apps.products.models import ProductVariant
from django.utils import timezone
from django.core.exceptions import ValidationError

class Supplier(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="suppliers",)
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("name"),"organization",name="supplier_org_name_ci_unique",),]
        indexes = [models.Index(fields=["organization", "is_active"],name="supplier_org_active_idx",),]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        if self.name:
            self.name = self.name.strip()


class PurchaseOrderSequence(models.Model):
    """
    Internal numbering sequence.

    One sequence exists per organization and calendar year.
    Actual number allocation will happen inside a transaction
    in the purchase order submission service.
    """

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="purchase_order_sequences",)
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "year"],name="po_sequence_org_year_unique",),
            models.CheckConstraint(condition=Q(last_number__gte=0),name="po_sequence_number_nonnegative",),
        ]

    def __str__(self):
        return f"{self.organization_id} - {self.year}"


class PurchaseOrder(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ORDERED = "ORDERED", "Ordered"
        PARTIALLY_RECEIVED = (
            "PARTIALLY_RECEIVED",
            "Partially Received",
        )
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="purchase_orders",)
    supplier = models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name="purchase_orders",)
    order_number = models.CharField(max_length=30,null=True,blank=True,)
    status = models.CharField(max_length=25,choices=Status.choices,default=Status.DRAFT,)
    ordered_at = models.DateTimeField(null=True,blank=True,)
    submitted_at = models.DateTimeField(null=True,blank=True,)
    expected_delivery_date = models.DateField(null=True,blank=True,)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="created_purchase_orders",)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(fields=["organization", "order_number"],condition=Q(order_number__isnull=False),name="po_org_number_unique",),

            models.CheckConstraint(
                condition=(
                    Q(
                        status="DRAFT",
                        order_number__isnull=True,
                        submitted_at__isnull=True,
                    )
                    | Q(
                        status__in=[
                            "ORDERED",
                            "PARTIALLY_RECEIVED",
                            "RECEIVED",
                        ],
                        order_number__isnull=False,
                        submitted_at__isnull=False,
                    )
                    | (
                        Q(status="CANCELLED")
                        & (
                            Q(
                                order_number__isnull=True,
                                submitted_at__isnull=True,
                            )
                            | Q(
                                order_number__isnull=False,
                                submitted_at__isnull=False,
                            )
                        )
                    )
                ),
                name="po_status_number_consistent",
            ),
        ]

        indexes = [
            models.Index(
                fields=["organization", "status", "created_at"],
                name="po_org_status_date_idx",
            ),
        ]

    def __str__(self):
        return self.order_number or f"Draft {self.id}" 

    @property
    def total_amount(self):
        return sum(
            (item.line_total for item in self.items.all()),
            Decimal("0.00"),
        )

    def clean(self):
        super().clean()

        if self.supplier_id and self.organization_id:
            if self.supplier.organization_id != self.organization_id:
                from django.core.exceptions import ValidationError

                raise ValidationError({"supplier": ("Supplier must belong to the same organization.")})


class PurchaseOrderItem(models.Model):

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    purchase_order = models.ForeignKey(PurchaseOrder,on_delete=models.PROTECT,related_name="items",)
    variant = models.ForeignKey(ProductVariant,on_delete=models.PROTECT,related_name="purchase_order_items",)
    quantity_ordered = models.DecimalField(max_digits=14,decimal_places=3,)
    unit_cost = models.DecimalField(max_digits=14,decimal_places=2,)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["purchase_order", "variant"],name="po_item_variant_unique",),
            models.CheckConstraint(condition=Q(quantity_ordered__gt=0),name="po_item_quantity_positive",),
            models.CheckConstraint(condition=Q(unit_cost__gte=0),name="po_item_cost_nonnegative",),
        ]

    def __str__(self):
        return (
            f"{self.purchase_order} - "
            f"{self.variant.sku}"
        )

    @property
    def line_total(self):
        return (self.quantity_ordered * self.unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP,)

    def clean(self):
        super().clean()

        if self.purchase_order_id and self.variant_id:
            if (self.purchase_order.organization_id!= self.variant.organization_id):
                from django.core.exceptions import ValidationError

                raise ValidationError({
                    "variant": (
                        "Product variant must belong to the "
                        "same organization as the purchase order."
                    )
                })



class GoodsReceipt(models.Model):
    """
    Records one physical delivery against a purchase order.

    A purchase order can have multiple goods receipts because
    suppliers may deliver its items in separate shipments.
    """

    id = models.UUIDField( primary_key=True, default=uuid.uuid4, editable=False, )
    organization = models.ForeignKey( Organization, on_delete=models.PROTECT, related_name="goods_receipts", )
    purchase_order = models.ForeignKey( PurchaseOrder, on_delete=models.PROTECT, related_name="goods_receipts", )
    received_by = models.ForeignKey( "accounts.User", on_delete=models.PROTECT, related_name="received_goods_receipts",)
    received_at = models.DateTimeField(default=timezone.now)
    supplier_reference = models.CharField( max_length=100, blank=True, )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField( max_length=128, null=True, blank=True,)
    request_fingerprint = models.CharField( max_length=64, null=True, blank=True, editable=False, )

    class Meta:
        ordering = ["-received_at", "-created_at"]

        indexes = [
            models.Index(
                fields=["organization", "received_at"],
                name="goodsreceipt_org_date_idx",
            ),
            models.Index(
                fields=["purchase_order", "received_at"],
                name="goodsreceipt_po_date_idx",
            ),
        ]
        
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="goodsreceipt_org_idempotency_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        idempotency_key__isnull=True,
                        request_fingerprint__isnull=True,
                    )
                    | Q(
                        idempotency_key__isnull=False,
                        request_fingerprint__isnull=False,
                    )
                ),
                name="goodsreceipt_idempotency_pair_valid",
            ),
        ]

    def clean(self):
        super().clean()

        if ( self.organization_id and self.purchase_order_id and self.organization_id != self.purchase_order.organization_id):
            raise ValidationError(
                "Goods receipt and purchase order must belong "
                "to the same organization."
            )

    def __str__(self):
        return (
            f"Goods receipt for "
            f"{self.purchase_order.order_number or self.purchase_order_id}"
        )


class GoodsReceiptItem(models.Model):
    """
    Records the quantity physically received for one purchase-order item.

    Damaged quantity is included in quantity_received, not added on top.
    """

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    goods_receipt = models.ForeignKey(GoodsReceipt,on_delete=models.PROTECT,related_name="items",)
    purchase_order_item = models.ForeignKey(PurchaseOrderItem,on_delete=models.PROTECT,related_name="goods_receipt_items",)
    quantity_received = models.DecimalField(max_digits=14,decimal_places=3,)
    quantity_damaged = models.DecimalField(max_digits=14,decimal_places=3,default=Decimal("0.000"),)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(fields=["goods_receipt", "purchase_order_item"],name="goodsreceipt_item_unique",),
            models.CheckConstraint(condition=Q(quantity_received__gt=0),name="goodsreceipt_qty_received_positive",),
            models.CheckConstraint(condition=Q(quantity_damaged__gte=0),name="goodsreceipt_qty_damaged_nonnegative",),
            models.CheckConstraint(condition=Q(quantity_damaged__lte=models.F("quantity_received")),name="goodsreceipt_damaged_lte_received",),
        ]

    def clean(self):
        super().clean()

        if not self.goods_receipt_id or not self.purchase_order_item_id:
            return

        receipt = self.goods_receipt
        order_item = self.purchase_order_item

        if receipt.purchase_order_id != order_item.purchase_order_id:
            raise ValidationError(
                "The purchase-order item must belong to the "
                "goods receipt's purchase order."
            )

        if receipt.organization_id != order_item.purchase_order.organization_id:
            raise ValidationError(
                "Goods receipt and purchase-order item must belong "
                "to the same organization."
            )

    @property
    def quantity_accepted(self):
        return self.quantity_received - self.quantity_damaged

    def __str__(self):
        return (
            f"{self.quantity_received} received for "
            f"{self.purchase_order_item.variant}"
        )
