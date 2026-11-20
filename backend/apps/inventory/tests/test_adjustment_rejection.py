
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant

from apps.inventory.models import (
    InventoryBalance,
    StockAdjustment,
    StockMovement,
)

from apps.inventory.services import (
    create_stock_adjustment,
    approve_stock_adjustment,
    get_or_create_inventory_balance,
    apply_stock_movement,
)


User = get_user_model()


class StockAdjustmentApprovalTests(TestCase):

    def setUp(self):
        self.organization = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.inventory_user = User.objects.create_user(
            email="inventory@example.com",
            password="TestPassword123!",
        )

        self.manager = User.objects.create_user(
            email="manager@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.inventory_user,
            role=Membership.Role.INVENTORY,
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=Membership.Role.MANAGER,
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

        get_or_create_inventory_balance(
            organization=self.organization,
            variant=self.variant,
        )

        apply_stock_movement(
            organization=self.organization,
            variant=self.variant,
            movement_type=StockMovement.MovementType.RECEIPT,
            quantity_delta=Decimal("10.000"),
            created_by=self.manager,
            reason="Initial inventory",
        )

    def create_adjustment(self, quantity="-2.000"):
        return create_stock_adjustment(
            organization=self.organization,
            variant=self.variant,
            quantity_change=Decimal(quantity),
            reason="Physical stock count discrepancy",
            created_by=self.inventory_user,
        )

    def test_manager_can_approve_adjustment(self):
        adjustment = self.create_adjustment()

        approved = approve_stock_adjustment(
            adjustment_id=adjustment.id,
            approved_by=self.manager,
        )

        self.assertEqual(
            approved.status,
            StockAdjustment.Status.APPROVED,
        )

        self.assertEqual(
            approved.approved_by,
            self.manager,
        )

        self.assertIsNotNone(approved.approved_at)

    def test_approval_updates_inventory(self):
        adjustment = self.create_adjustment()

        approve_stock_adjustment(
            adjustment_id=adjustment.id,
            approved_by=self.manager,
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("8.000"),
        )

    def test_approval_creates_stock_movement(self):
        adjustment = self.create_adjustment()

        movement_count_before = StockMovement.objects.count()

        approve_stock_adjustment(
            adjustment_id=adjustment.id,
            approved_by=self.manager,
        )

        self.assertEqual(
            StockMovement.objects.count(),
            movement_count_before + 1,
        )

        movement = StockMovement.objects.get(
            movement_type=StockMovement.MovementType.ADJUSTMENT,
        )

        self.assertEqual(
            movement.quantity_delta,
            Decimal("-2.000"),
        )

        self.assertEqual(
            movement.created_by,
            self.manager,
        )

    def test_creator_cannot_approve_own_adjustment(self):
        adjustment = self.create_adjustment()

        with self.assertRaises(ValidationError):
            approve_stock_adjustment(
                adjustment_id=adjustment.id,
                approved_by=self.inventory_user,
            )

    def test_sales_member_cannot_approve_adjustment(self):
        sales_user = User.objects.create_user(
            email="sales@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization,
            user=sales_user,
            role=Membership.Role.SALES,
        )

        adjustment = self.create_adjustment()

        with self.assertRaises(ValidationError):
            approve_stock_adjustment(
                adjustment_id=adjustment.id,
                approved_by=sales_user,
            )

    def test_insufficient_stock_keeps_adjustment_pending(self):
        adjustment = self.create_adjustment(quantity="-15.000")

        movement_count_before = StockMovement.objects.count()

        with self.assertRaises(ValidationError):
            approve_stock_adjustment(
                adjustment_id=adjustment.id,
                approved_by=self.manager,
            )

        adjustment.refresh_from_db()

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

        self.assertIsNone(adjustment.approved_by)
        self.assertIsNone(adjustment.approved_at)

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("10.000"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            movement_count_before,
        )

    def test_adjustment_cannot_be_approved_twice(self):
        adjustment = self.create_adjustment()

        approve_stock_adjustment(
            adjustment_id=adjustment.id,
            approved_by=self.manager,
        )

        with self.assertRaises(ValidationError):
            approve_stock_adjustment(
                adjustment_id=adjustment.id,
                approved_by=self.manager,
            )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("8.000"),
        )
