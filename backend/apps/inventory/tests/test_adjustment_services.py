
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant
from apps.inventory.models import StockAdjustment, InventoryBalance
from apps.inventory.services import create_stock_adjustment


User = get_user_model()


class StockAdjustmentRequestTests(TestCase):

    def setUp(self):
        self.organization = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.user = User.objects.create_user(
            email="inventory@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.INVENTORY,
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="8GB RAM",
            sku="LAPTOP-001",
            unit="PIECE",
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

    def test_inventory_member_can_request_adjustment(self):
        adjustment = create_stock_adjustment(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal("-2.000"),
            reason="Physical stock count discrepancy",
            created_by=self.user,
        )

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

        self.assertEqual(
            adjustment.quantity_change,
            Decimal("-2.000"),
        )

        self.assertIsNone(adjustment.approved_by)
        self.assertIsNone(adjustment.approved_at)

    def test_request_does_not_change_inventory(self):
        adjustment = create_stock_adjustment(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal("2.000"),
            reason="Missing stock correction",
            created_by=self.user,
        )

        self.assertEqual(
            InventoryBalance.objects.count(),
            0,
        )

    def test_reject_variant_from_another_organization(self):
        another_organization = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        another_product = Product.objects.create(
            organization=another_organization,
            name="Phone",
        )

        another_variant = ProductVariant.objects.create(
            organization=another_organization,
            product=another_product,
            name="128GB",
            sku="PHONE-128",
            unit="PIECE",
            cost_price=Decimal("20000.00"),
            selling_price=Decimal("25000.00"),
        )

        with self.assertRaises(ValidationError):
            create_stock_adjustment(
                organization=self.organization,
                variant=another_variant,
                quantity_change=Decimal("1.000"),
                reason="Invalid organization test",
                created_by=self.user,
            )

    def test_reject_zero_adjustment(self):
        with self.assertRaises(ValidationError):
            create_stock_adjustment(
                organization=self.organization,
                variant=self.variant,
                quantity_change=Decimal("0.000"),
                damaged_quantity_change=Decimal("0.000"),
                reason="No change",
                created_by=self.user,
            )

    def test_reject_blank_reason(self):
        with self.assertRaises(ValidationError):
            create_stock_adjustment(
                organization=self.organization,
                variant=self.variant,
                quantity_change=Decimal("1.000"),
                reason="   ",
                created_by=self.user,
            )

    def test_sales_member_cannot_request_adjustment(self):
        sales_user = User.objects.create_user(
            email="sales@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization,
            user=sales_user,
            role=Membership.Role.SALES,
        )

        with self.assertRaises(ValidationError):
            create_stock_adjustment(
                organization=self.organization,
                variant=self.variant,
                quantity_change=Decimal("1.000"),
                reason="Unauthorized request",
                created_by=sales_user,
            )

    def test_user_without_membership_cannot_request_adjustment(self):
        unauthorized_user = User.objects.create_user(
            email="outsider@example.com",
            password="TestPassword123!",
        )

        with self.assertRaises(ValidationError):
            create_stock_adjustment(
                organization=self.organization,
                variant=self.variant,
                quantity_change=Decimal("1.000"),
                reason="Unauthorized request",
                created_by=unauthorized_user,
            )
