from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
import uuid
from apps.organizations.models import Organization

class Category(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="categories",)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "organization",
                name="category_org_name_ci_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=["organization", "is_active"],
                name="category_org_active_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        if self.name:
            self.name = self.name.strip()



class Product(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="products",)
    category = models.ForeignKey(Category,on_delete=models.PROTECT,related_name="products",null=True,blank=True,)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["organization", "is_active"],
                name="product_org_active_idx",
            ),
            models.Index(
                fields=["organization", "category"],
                name="product_org_category_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        if self.category_id and self.organization_id:
            if self.category.organization_id != self.organization_id:
                from django.core.exceptions import ValidationError

                raise ValidationError({
                    "category": "Category must belong to the same organization."
                })


class ProductVariant(models.Model):

    class Unit(models.TextChoices):
        PIECE = "PIECE", "Piece"
        BOX = "BOX", "Box"
        PACK = "PACK", "Pack"

    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,)
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name="product_variants",)
    product = models.ForeignKey(Product,on_delete=models.PROTECT,related_name="variants",)
    name = models.CharField(max_length=150,default="Default",)
    sku = models.CharField(max_length=80)
    barcode = models.CharField(max_length=100,null=True,blank=True,)
    unit = models.CharField(max_length=20,choices=Unit.choices,default=Unit.PIECE,)
    cost_price = models.DecimalField(max_digits=12,decimal_places=2,)
    selling_price = models.DecimalField(max_digits=12,decimal_places=2,)
    reorder_level = models.PositiveIntegerField(default=0)
    track_serial_numbers = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("sku"),"organization",name="variant_org_sku_ci_unique",),
            models.UniqueConstraint(Lower("barcode"),"organization",condition=Q(barcode__isnull=False),name="variant_org_barcode_ci_unique",),
            models.CheckConstraint(condition=Q(cost_price__gte=0),name="variant_cost_nonnegative",),
            models.CheckConstraint(condition=Q(selling_price__gte=0),name="variant_selling_nonnegative",),
        ]

        indexes = [
            models.Index(fields=["organization", "is_active"],name="variant_org_active_idx",),
            models.Index(fields=["product", "is_active"],name="variant_product_active_idx",),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if self.product_id and self.organization_id:
            if self.product.organization_id != self.organization_id:
                raise ValidationError({
                    "product": "Product must belong to the same organization."
                })

        if self.sku:
            self.sku = self.sku.strip()

        if self.barcode:
            self.barcode = self.barcode.strip() or None
