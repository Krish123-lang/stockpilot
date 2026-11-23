
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.procurement.models import (
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderSequence,
)

User = get_user_model()


class ProcurementModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="procurement@example.com",
            password="testpassword123",
        )

        self.organization = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.other_organization = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="ABC Electronics",
            contact_person="Ram Sharma",
            email="supplier@example.com",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Dell Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="16GB RAM",
            sku="DELL-16GB",
            cost_price=Decimal("80000.00"),
            selling_price=Decimal("95000.00"),
        )

    def create_purchase_order(self):
        return PurchaseOrder.objects.create(
            organization=self.organization,
            supplier=self.supplier,
            created_by=self.user,
        )

    def test_supplier_belongs_to_organization(self):
        self.assertEqual(
            self.supplier.organization,
            self.organization,
        )

    def test_supplier_name_is_case_insensitive_unique_per_org(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(
                    organization=self.organization,
                    name="abc electronics",
                )

    def test_same_supplier_name_allowed_in_different_orgs(self):
        supplier = Supplier.objects.create(
            organization=self.other_organization,
            name="ABC Electronics",
        )

        self.assertEqual(
            supplier.organization,
            self.other_organization,
        )

    def test_supplier_can_be_deactivated(self):
        self.supplier.is_active = False
        self.supplier.save()

        self.supplier.refresh_from_db()

        self.assertFalse(self.supplier.is_active)

    def test_purchase_order_starts_as_draft(self):
        order = self.create_purchase_order()

        self.assertEqual(
            order.status,
            PurchaseOrder.Status.DRAFT,
        )

        self.assertIsNone(order.order_number)
        self.assertIsNone(order.submitted_at)

    def test_purchase_order_rejects_foreign_supplier(self):
        foreign_supplier = Supplier.objects.create(
            organization=self.other_organization,
            name="Foreign Supplier",
        )

        order = PurchaseOrder(
            organization=self.organization,
            supplier=foreign_supplier,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_purchase_order_item_accepts_valid_quantity_and_cost(self):
        order = self.create_purchase_order()

        item = PurchaseOrderItem.objects.create(
            purchase_order=order,
            variant=self.variant,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("78000.00"),
        )

        self.assertEqual(
            item.quantity_ordered,
            Decimal("2.000"),
        )

        self.assertEqual(
            item.unit_cost,
            Decimal("78000.00"),
        )

    def test_duplicate_variant_in_purchase_order_is_rejected(self):
        order = self.create_purchase_order()

        PurchaseOrderItem.objects.create(
            purchase_order=order,
            variant=self.variant,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("78000.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    variant=self.variant,
                    quantity_ordered=Decimal("3.000"),
                    unit_cost=Decimal("78000.00"),
                )

    def test_purchase_order_item_rejects_foreign_variant(self):
        foreign_product = Product.objects.create(
            organization=self.other_organization,
            name="Foreign Laptop",
        )

        foreign_variant = ProductVariant.objects.create(
            organization=self.other_organization,
            product=foreign_product,
            sku="FOREIGN-LAPTOP",
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

        order = self.create_purchase_order()

        item = PurchaseOrderItem(
            purchase_order=order,
            variant=foreign_variant,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("50000.00"),
        )

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_zero_quantity_is_rejected_by_database(self):
        order = self.create_purchase_order()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    variant=self.variant,
                    quantity_ordered=Decimal("0.000"),
                    unit_cost=Decimal("50000.00"),
                )

    def test_negative_quantity_is_rejected_by_database(self):
        order = self.create_purchase_order()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    variant=self.variant,
                    quantity_ordered=Decimal("-1.000"),
                    unit_cost=Decimal("50000.00"),
                )

    def test_negative_unit_cost_is_rejected_by_database(self):
        order = self.create_purchase_order()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    variant=self.variant,
                    quantity_ordered=Decimal("1.000"),
                    unit_cost=Decimal("-100.00"),
                )

    def test_line_total_is_calculated_correctly(self):
        order = self.create_purchase_order()

        item = PurchaseOrderItem.objects.create(
            purchase_order=order,
            variant=self.variant,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("78000.00"),
        )

        self.assertEqual(
            item.line_total,
            Decimal("156000.00"),
        )

    def test_purchase_order_total_is_calculated_from_items(self):
        order = self.create_purchase_order()

        PurchaseOrderItem.objects.create(
            purchase_order=order,
            variant=self.variant,
            quantity_ordered=Decimal("2.000"),
            unit_cost=Decimal("78000.00"),
        )

        second_product = Product.objects.create(
            organization=self.organization,
            name="Wireless Mouse",
        )

        second_variant = ProductVariant.objects.create(
            organization=self.organization,
            product=second_product,
            sku="MOUSE-001",
            cost_price=Decimal("800.00"),
            selling_price=Decimal("1200.00"),
        )

        PurchaseOrderItem.objects.create(
            purchase_order=order,
            variant=second_variant,
            quantity_ordered=Decimal("5.000"),
            unit_cost=Decimal("1000.00"),
        )

        self.assertEqual(
            order.total_amount,
            Decimal("161000.00"),
        )

    def test_purchase_order_sequence_is_unique_per_org_and_year(self):
        PurchaseOrderSequence.objects.create(
            organization=self.organization,
            year=2026,
            last_number=1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderSequence.objects.create(
                    organization=self.organization,
                    year=2026,
                    last_number=2,
                )

    def test_same_sequence_year_allowed_for_different_orgs(self):
        sequence = PurchaseOrderSequence.objects.create(
            organization=self.other_organization,
            year=2026,
            last_number=1,
        )

        self.assertEqual(
            sequence.organization,
            self.other_organization,
        )
