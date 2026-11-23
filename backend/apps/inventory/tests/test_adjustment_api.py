
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant
from apps.inventory.models import (
    InventoryBalance,
    StockMovement,
    StockAdjustment,
)

User = get_user_model()


class StockAdjustmentAPITests(APITestCase):

    def setUp(self):
        self.organization_a = Organization.objects.create(
            name="Everest Electronics",
            slug="everest-electronics",
        )

        self.organization_b = Organization.objects.create(
            name="Himalayan Tech",
            slug="himalayan-tech",
        )

        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="TestPassword123!",
        )

        self.inventory_user = User.objects.create_user(
            email="inventory@example.com",
            password="TestPassword123!",
        )

        self.manager = User.objects.create_user(
            email="manager@example.com",
            password="TestPassword123!",
        )

        self.sales_user = User.objects.create_user(
            email="sales@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            organization=self.organization_a,
            user=self.owner,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            organization=self.organization_a,
            user=self.inventory_user,
            role=Membership.Role.INVENTORY,
        )

        Membership.objects.create(
            organization=self.organization_a,
            user=self.manager,
            role=Membership.Role.MANAGER,
        )

        Membership.objects.create(
            organization=self.organization_a,
            user=self.sales_user,
            role=Membership.Role.SALES,
        )

        self.product_a = Product.objects.create(
            organization=self.organization_a,
            name="Samsung Galaxy S25",
        )

        self.product_b = Product.objects.create(
            organization=self.organization_b,
            name="MacBook Air",
        )

        self.variant_a = ProductVariant.objects.create(
            organization=self.organization_a,
            product=self.product_a,
            name="256 GB",
            sku="SAM-S25-256",
            unit="PIECE",
            cost_price=Decimal("85000.00"),
            selling_price=Decimal("95000.00"),
        )

        self.variant_b = ProductVariant.objects.create(
            organization=self.organization_b,
            product=self.product_b,
            name="Base Model",
            sku="MACBOOK-AIR",
            unit="PIECE",
            cost_price=Decimal("100000.00"),
            selling_price=Decimal("120000.00"),
        )

        self.balance = InventoryBalance.objects.create(
            organization=self.organization_a,
            variant=self.variant_a,
            quantity_on_hand=Decimal("10.000"),
        )

        self.client.force_authenticate(user=self.inventory_user)

    def adjustment_url(self):
        return reverse(
            "stock-adjustment-list",
            kwargs={
                "organization_id": self.organization_a.id,
            },
        )

    def adjustment_detail_url(self, adjustment):
        return reverse(
            "stock-adjustment-detail",
            kwargs={
                "organization_id": self.organization_a.id,
                "pk": adjustment.id,
            },
        )

    def approval_url(self, adjustment):
        return reverse(
            "stock-adjustment-approve",
            kwargs={
                "organization_id": self.organization_a.id,
                "pk": adjustment.id,
            },
        )

    def rejection_url(self, adjustment):
        return reverse(
            "stock-adjustment-reject",
            kwargs={
                "organization_id": self.organization_a.id,
                "pk": adjustment.id,
            },
        )

    def create_adjustment(self):
        return StockAdjustment.objects.create(
            organization=self.organization_a,
            variant=self.variant_a,
            quantity_change=Decimal("-2.000"),
            damaged_quantity_change=Decimal("0.000"),
            reason="Physical stock count correction",
            created_by=self.inventory_user,
        )

    # --------------------------------------------------
    # CREATE
    # --------------------------------------------------

    def test_inventory_member_can_submit_adjustment(self):
        response = self.client.post(
            self.adjustment_url(),
            {
                "variant": str(self.variant_a.id),
                "quantity_change": "-2.000",
                "damaged_quantity_change": "0.000",
                "reason": "Physical stock count correction",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        adjustment = StockAdjustment.objects.get()

        self.assertEqual(
            adjustment.created_by,
            self.inventory_user,
        )

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

        self.balance.refresh_from_db()

        self.assertEqual(
            self.balance.quantity_on_hand,
            Decimal("10.000"),
        )

    def test_sales_member_cannot_submit_adjustment(self):
        self.client.force_authenticate(user=self.sales_user)

        response = self.client.post(
            self.adjustment_url(),
            {
                "variant": str(self.variant_a.id),
                "quantity_change": "-2.000",
                "reason": "Stock correction",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            # status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(
            StockAdjustment.objects.count(),
            0,
        )

    def test_user_cannot_submit_foreign_variant(self):
        response = self.client.post(
            self.adjustment_url(),
            {
                "variant": str(self.variant_b.id),
                "quantity_change": "-2.000",
                "reason": "Stock correction",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            StockAdjustment.objects.count(),
            0,
        )

    # --------------------------------------------------
    # LIST AND RETRIEVE
    # --------------------------------------------------

    def test_user_can_list_own_adjustments(self):
        self.create_adjustment()

        response = self.client.get(self.adjustment_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(len(response.data), 1)

    def test_user_cannot_list_another_organizations_adjustments(self):
        url = reverse(
            "stock-adjustment-list",
            kwargs={
                "organization_id": self.organization_b.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_cannot_retrieve_foreign_adjustment(self):
        foreign_adjustment = StockAdjustment.objects.create(
            organization=self.organization_b,
            variant=self.variant_b,
            quantity_change=Decimal("-1.000"),
            reason="Foreign adjustment",
            created_by=self.owner,
        )

        response = self.client.get(
            self.adjustment_detail_url(foreign_adjustment)
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # --------------------------------------------------
    # APPROVAL
    # --------------------------------------------------

    def test_manager_can_approve_adjustment(self):
        adjustment = self.create_adjustment()

        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.approval_url(adjustment),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        adjustment.refresh_from_db()

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.APPROVED,
        )

        self.assertEqual(
            adjustment.approved_by,
            self.manager,
        )

        self.assertEqual(
            StockMovement.objects.filter(
                organization=self.organization_a,
                movement_type=StockMovement.MovementType.ADJUSTMENT,
            ).count(),
            1,
        )

        self.balance.refresh_from_db()

        self.assertEqual(
            self.balance.quantity_on_hand,
            Decimal("8.000"),
        )

    def test_sales_member_cannot_approve_adjustment(self):
        adjustment = self.create_adjustment()

        self.client.force_authenticate(user=self.sales_user)

        response = self.client.post(
            self.approval_url(adjustment),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            # status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN
        )

        adjustment.refresh_from_db()

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

    # --------------------------------------------------
    # REJECTION
    # --------------------------------------------------

    def test_manager_can_reject_adjustment(self):
        adjustment = self.create_adjustment()

        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.rejection_url(adjustment),
            {
                "rejection_reason": "Physical count needs verification.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        adjustment.refresh_from_db()

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.REJECTED,
        )

        self.assertEqual(
            adjustment.rejected_by,
            self.manager,
        )

        self.assertEqual(
            adjustment.rejection_reason,
            "Physical count needs verification.",
        )

        self.assertIsNotNone(adjustment.rejected_at)

    def test_rejection_requires_reason(self):
        adjustment = self.create_adjustment()

        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.rejection_url(adjustment),
            {
                "rejection_reason": "   ",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        adjustment.refresh_from_db()

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )

    def test_rejection_does_not_change_inventory(self):
        adjustment = self.create_adjustment()

        initial_quantity = self.balance.quantity_on_hand
        initial_movements = StockMovement.objects.count()

        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.rejection_url(adjustment),
            {
                "rejection_reason": "Incorrect stock count.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.balance.refresh_from_db()

        self.assertEqual(
            self.balance.quantity_on_hand,
            initial_quantity,
        )

        self.assertEqual(
            StockMovement.objects.count(),
            initial_movements,
        )

    def test_sales_member_cannot_reject_adjustment(self):
        adjustment = self.create_adjustment()

        self.client.force_authenticate(user=self.sales_user)

        response = self.client.post(
            self.rejection_url(adjustment),
            {
                "rejection_reason": "Rejected.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            # status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN
        )

        adjustment.refresh_from_db()

        self.assertEqual(
            adjustment.status,
            StockAdjustment.Status.PENDING,
        )
