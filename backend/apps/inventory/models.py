import uuid
from django.db import models
from django.db.models import F, Q
from apps.organizations.models import Organization
from apps.products.models import ProductVariant
from django.core.exceptions import ValidationError

class InventoryBalance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="inventory_balances",)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="inventory_balances",)
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=0,)
    quantity_damaged = models.DecimalField(max_digits=14, decimal_places=3, default=0,)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "variant"],name="unique_inventory_balance_per_org_variant",),models.CheckConstraint(condition=Q(quantity_on_hand__gte=0),name="inventory_quantity_nonnegative",),models.CheckConstraint(condition=Q(quantity_damaged__gte=0),name="inventory_damaged_nonnegative",),models.CheckConstraint(condition=Q(quantity_damaged__lte=F("quantity_on_hand")),name="inventory_damaged_not_above_on_hand",),]

    @property
    def quantity_sellable(self):
        return self.quantity_on_hand - self.quantity_damaged

    def __str__(self):
        return f"{self.variant.sku} - {self.quantity_sellable}"


class ImmutableStockMovementQuerySet(models.QuerySet):
    """
    Prevent updates and deletions of existing stock ledger entries.
    """

    def update(self, **kwargs):
        raise ValidationError("Stock movements are immutable and cannot be updated.")

    def delete(self):
        raise ValidationError("Stock movements are immutable and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Stock movements are immutable and cannot be bulk updated.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Stock movements must be created through the inventory service.")


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Goods receipt"
        SALE = "SALE", "Sale"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer return"
        ADJUSTMENT = "ADJUSTMENT", "Stock adjustment"
        DAMAGE = "DAMAGE", "Damage classification"
        REPAIR = "REPAIR", "Repair"
        REVERSAL = "REVERSAL", "Movement reversal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_movements",)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_movements",)
    movement_type = models.CharField(max_length=30, choices=MovementType.choices,)
    quantity_delta = models.DecimalField(max_digits=14, decimal_places=3,)
    damaged_delta = models.DecimalField(max_digits=14, decimal_places=3, default=0,)
    quantity_after = models.DecimalField(max_digits=14, decimal_places=3,)
    damaged_after = models.DecimalField(max_digits=14, decimal_places=3,)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="stock_movements",)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableStockMovementQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "variant", "created_at"],name="movement_org_variant_date_idx",),models.Index(fields=["organization", "movement_type"],name="movement_org_type_idx",),]
        constraints = [models.CheckConstraint(condition=Q(quantity_after__gte=0),name="movement_quantity_after_nonnegative",),models.CheckConstraint(condition=Q(damaged_after__gte=0),name="movement_damaged_after_nonnegative",),models.CheckConstraint(condition=Q(damaged_after__lte=F("quantity_after")),name="movement_damaged_after_not_above_quantity",),]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Stock movements are immutable and cannot be updated.")
        super().save(*args, **kwargs)


    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements are immutable and cannot be deleted.")

    def __str__(self):
        return (f"{self.movement_type}: "f"{self.variant.sku} ({self.quantity_delta})")


class StockAdjustment(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="stock_adjustments",)
    variant = models.ForeignKey(ProductVariant,on_delete=models.PROTECT,related_name="stock_adjustments",)
    quantity_change = models.DecimalField(max_digits=14,decimal_places=3,)
    damaged_quantity_change = models.DecimalField(max_digits=14,decimal_places=3,default=0,)
    reason = models.TextField()
    status = models.CharField(max_length=10,choices=Status.choices,default=Status.PENDING,)
    created_by = models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="created_stock_adjustments",)
    approved_by = models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="approved_stock_adjustments",null=True,blank=True,)
    rejected_by = models.ForeignKey("accounts.User",on_delete=models.PROTECT,related_name="rejected_stock_adjustments",null=True,blank=True,)
    approved_at = models.DateTimeField(null=True,blank=True,)
    rejected_at = models.DateTimeField(null=True,blank=True,)
    rejection_reason = models.TextField(blank=True,default="",)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"],name="adjustment_org_status_idx",),models.Index(fields=["organization", "created_at"],name="adjustment_org_date_idx",),]
        constraints = [models.CheckConstraint(condition=(Q(quantity_change__gt=0)| Q(quantity_change__lt=0)| Q(damaged_quantity_change__gt=0)| Q(damaged_quantity_change__lt=0)),name="adjustment_must_change_inventory",),models.CheckConstraint(condition=(Q(status="PENDING",approved_by__isnull=True,approved_at__isnull=True,rejected_by__isnull=True,rejected_at__isnull=True,rejection_reason="",)| Q(status="APPROVED",approved_by__isnull=False,approved_at__isnull=False,rejected_by__isnull=True,rejected_at__isnull=True,rejection_reason="",)| Q(status="REJECTED",approved_by__isnull=True,approved_at__isnull=True,rejected_by__isnull=False,rejected_at__isnull=False,)),name="adjustment_status_fields_consistent",),models.CheckConstraint(condition=(Q(approved_by__isnull=True)| ~Q(approved_by=models.F("created_by"))),name="adjustment_approver_not_creator",),models.CheckConstraint(condition=(Q(rejected_by__isnull=True)| ~Q(rejected_by=models.F("created_by")) ),name="adjustment_rejector_not_creator",),]

    def __str__(self):
        return (f"Adjustment {self.id} - "f"{self.variant.sku} ({self.status})")
