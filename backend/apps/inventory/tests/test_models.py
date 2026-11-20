from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.products.models import Product, ProductVariant
from apps.inventory.models import StockMovement, StockAdjustment


class StockMovementModelTests(TestCase):

    def setUp(self):
        self.organization = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.user = User.objects.create_user(
            email="inventory@example.com",
            password="test-password-123",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Samsung Monitor",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="24-inch",
            sku="SAMSUNG-24",
            unit="PIECE",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("12000.00"),
        )

        self.valid_data = {
            "organization": self.organization,
            "variant": self.variant,
            "movement_type": StockMovement.MovementType.RECEIPT,
            "quantity_delta": Decimal("10.000"),
            "damaged_delta": Decimal("0.000"),
            "quantity_after": Decimal("10.000"),
            "damaged_after": Decimal("0.000"),
            "created_by": self.user,
            "reason": "Initial stock receipt",
        }

    def test_create_valid_stock_movement(self):
        movement = StockMovement.objects.create(
            **self.valid_data
        )

        self.assertEqual(movement.quantity_delta, Decimal("10.000"))
        self.assertEqual(movement.quantity_after, Decimal("10.000"))

    def test_negative_quantity_after_is_rejected(self):
        data = {
            **self.valid_data,
            "quantity_after": Decimal("-1.000"),
        }

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(**data)

    def test_negative_damaged_after_is_rejected(self):
        data = {
            **self.valid_data,
            "damaged_after": Decimal("-1.000"),
        }

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(**data)

    def test_damaged_quantity_cannot_exceed_physical_quantity(self):
        data = {
            **self.valid_data,
            "quantity_after": Decimal("5.000"),
            "damaged_after": Decimal("6.000"),
        }

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(**data)

    def test_negative_quantity_delta_is_allowed(self):
        data = {
            **self.valid_data,
            "movement_type": StockMovement.MovementType.SALE,
            "quantity_delta": Decimal("-2.000"),
            "quantity_after": Decimal("8.000"),
        }

        movement = StockMovement.objects.create(**data)

        self.assertEqual(
            movement.quantity_delta,
            Decimal("-2.000"),
        )

    def test_negative_damaged_delta_is_allowed(self):
        data = {
            **self.valid_data,
            "movement_type": StockMovement.MovementType.REPAIR,
            "quantity_delta": Decimal("0.000"),
            "damaged_delta": Decimal("-1.000"),
            "quantity_after": Decimal("10.000"),
            "damaged_after": Decimal("0.000"),
        }

        movement = StockMovement.objects.create(**data)

        self.assertEqual(
            movement.damaged_delta,
            Decimal("-1.000"),
        )

    def test_movement_type_choices_are_available(self):
        expected_types = {
            "RECEIPT",
            "SALE",
            "CUSTOMER_RETURN",
            "ADJUSTMENT",
            "DAMAGE",
            "REPAIR",
            "REVERSAL",
        }

        actual_types = {
            choice[0]
            for choice in StockMovement.MovementType.choices
        }

        self.assertEqual(actual_types, expected_types)
        

class StockAdjustmentModelTests(TestCase):

    def setUp(self):
        self.organization = Organization.objects.create(
            name="Adjustment Test Store",
            slug="adjustment-test-store",
        )

        self.user = User.objects.create_user(
            email="adjustment@example.com",
            password="test-password-123",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Dell Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="Core i5",
            sku="DELL-I5",
            unit="PIECE",
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

    def test_create_adjustment(self):
        adjustment = StockAdjustment.objects.create(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal("-2.000"),
            damaged_quantity_change=Decimal("0.000"),
            reason="Physical stock count correction",
            created_by=self.user,
        )

        self.assertEqual(
            adjustment.quantity_change,
            Decimal("-2.000"),
        )

        self.assertEqual(
            adjustment.organization,
            self.organization,
        )

    def test_new_adjustment_defaults_to_pending(self):
        adjustment = StockAdjustment.objects.create(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal("5.000"),
            reason="Additional stock discovered",
            created_by=self.user,
        )

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

    def test_new_adjustment_has_no_approver(self):
        adjustment = StockAdjustment.objects.create(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal("3.000"),
            reason="Stock count correction",
            created_by=self.user,
        )

        self.assertIsNone(adjustment.approved_by)
        self.assertIsNone(adjustment.approved_at)
