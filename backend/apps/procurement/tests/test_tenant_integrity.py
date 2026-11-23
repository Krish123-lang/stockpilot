
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.procurement.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)


User = get_user_model()


class ProcurementTenantIntegrityTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
        )

        self.org_a = Organization.objects.create(
            name="Organization A",
            slug="organization-a",
        )

        self.org_b = Organization.objects.create(
            name="Organization B",
            slug="organization-b",
        )

        self.supplier_a = Supplier.objects.create(
            organization=self.org_a,
            name="Supplier A",
        )

        self.product_a = Product.objects.create(
            organization=self.org_a,
            name="Product A",
        )

        self.variant_a = ProductVariant.objects.create(
            organization=self.org_a,
            product=self.product_a,
            name="Variant A",
            sku="VAR-A",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        self.product_b = Product.objects.create(
            organization=self.org_b,
            name="Product B",
        )

        self.variant_b = ProductVariant.objects.create(
            organization=self.org_b,
            product=self.product_b,
            name="Variant B",
            sku="VAR-B",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
        )

        self.purchase_order = PurchaseOrder.objects.create(
            organization=self.org_a,
            supplier=self.supplier_a,
            created_by=self.user,
        )

    def test_database_rejects_foreign_organization_supplier(self):
        foreign_supplier = Supplier.objects.create(
            organization=self.org_b,
            name="Foreign Supplier",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.create(
                    organization=self.org_a,
                    supplier=foreign_supplier,
                    created_by=self.user,
                )

    def test_database_rejects_foreign_organization_variant(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.create(
                    purchase_order=self.purchase_order,
                    variant=self.variant_b,
                    quantity_ordered=Decimal("2.000"),
                    unit_cost=Decimal("100.00"),
                )

    def test_database_rejects_supplier_organization_change(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.filter(
                    pk=self.supplier_a.pk
                ).update(organization=self.org_b)

    def test_database_rejects_variant_organization_change(self):
        PurchaseOrderItem.objects.create(
            purchase_order=self.purchase_order,
            variant=self.variant_a,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("100.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.filter(
                    pk=self.variant_a.pk
                ).update(organization=self.org_b)

    def test_database_rejects_purchase_order_organization_change(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.filter(
                    pk=self.purchase_order.pk
                ).update(organization=self.org_b)
