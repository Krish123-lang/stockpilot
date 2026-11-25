from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant
from apps.inventory.models import InventoryBalance, StockMovement
from apps.procurement.models import ( Supplier, PurchaseOrder, PurchaseOrderItem, GoodsReceipt)
from apps.procurement.services import submit_purchase_order

User = get_user_model()

class GoodsReceiptAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="api-receiver@example.com",
            password="TestPassword123!",
        )

        self.organization = Organization.objects.create(
            name="API Electronics",
            slug="api-electronics",
        )

        self.membership = Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.INVENTORY,
        )

        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="API Supplier",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="API Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="API Laptop Variant",
            sku="API-LAPTOP-001",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

        self.purchase_order = PurchaseOrder.objects.create(
            organization=self.organization,
            supplier=self.supplier,
            created_by=self.user,
        )

        self.order_item = PurchaseOrderItem.objects.create(
            purchase_order=self.purchase_order,
            variant=self.variant,
            quantity_ordered=Decimal("10.000"),
            unit_cost=Decimal("50000.00"),
        )

        self.purchase_order = submit_purchase_order(
            self.purchase_order.id
        )

        self.url = reverse(
            "goods-receipt-create",
            kwargs={
                "organization_id": self.organization.id,
                "purchase_order_id": self.purchase_order.id,
            },
        )

        self.payload = {
            "items": [
                {
                    "purchase_order_item_id": str(self.order_item.id),
                    "quantity_received": "4.000",
                    "quantity_damaged": "1.000",
                }
            ],
            "supplier_reference": "API-DELIVERY-001",
            "notes": "Initial API delivery",
        }

        self.client.force_authenticate(user=self.user)

    def test_inventory_member_can_create_receipt(self):
        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 1)

        receipt = GoodsReceipt.objects.get()

        self.assertEqual(
            receipt.purchase_order_id,
            self.purchase_order.id,
        )

        self.assertEqual(response.data["id"], str(receipt.id))
        self.assertEqual(len(response.data["items"]), 1)

        self.assertEqual(
            response.data["items"][0]["quantity_accepted"],
            "3.000",
        )

        balance = InventoryBalance.objects.get(
            organization=self.organization,
            variant=self.variant,
        )

        self.assertEqual(
            balance.quantity_on_hand,
            Decimal("4.000"),
        )

        self.assertEqual(
            balance.quantity_damaged,
            Decimal("1.000"),
        )

        self.purchase_order.refresh_from_db()

        self.assertEqual(
            self.purchase_order.status,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
        )

    def test_owner_can_create_receipt(self):
        self.membership.role = Membership.Role.OWNER
        self.membership.save(update_fields=["role"])

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_manager_can_create_receipt(self):
        self.membership.role = Membership.Role.MANAGER
        self.membership.save(update_fields=["role"])

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_sales_member_cannot_create_receipt(self):
        self.membership.role = Membership.Role.SALES
        self.membership.save(update_fields=["role"])

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_unauthenticated_user_cannot_create_receipt(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertIn(
            response.status_code,
            [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ],
        )

        self.assertEqual(GoodsReceipt.objects.count(), 0)

    def test_inactive_membership_cannot_create_receipt(self):
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 0)

    def test_purchase_order_from_another_organization_is_not_accessible(self):
        other_user = User.objects.create_user(
            email="other-api-user@example.com",
            password="TestPassword123!",
        )

        other_organization = Organization.objects.create(
            name="Other API Electronics",
            slug="other-api-electronics",
        )

        other_supplier = Supplier.objects.create(
            organization=other_organization,
            name="Other Supplier",
        )

        other_product = Product.objects.create(
            organization=other_organization,
            name="Other Laptop",
        )

        other_variant = ProductVariant.objects.create(
            organization=other_organization,
            product=other_product,
            name="Other Laptop Variant",
            sku="OTHER-API-LAPTOP-001",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("40000.00"),
            selling_price=Decimal("50000.00"),
        )

        other_purchase_order = PurchaseOrder.objects.create(
            organization=other_organization,
            supplier=other_supplier,
            created_by=other_user,
        )

        PurchaseOrderItem.objects.create(
            purchase_order=other_purchase_order,
            variant=other_variant,
            quantity_ordered=Decimal("5.000"),
            unit_cost=Decimal("40000.00"),
        )

        submit_purchase_order(other_purchase_order.id)

        response = self.client.post(
            reverse(
                "goods-receipt-create",
                kwargs={
                    "organization_id": self.organization.id,
                    "purchase_order_id": other_purchase_order.id,
                },
            ),
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_invalid_payload_is_rejected(self):
        response = self.client.post(
            self.url,
            {"items": []},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_idempotent_retry_does_not_create_duplicate_receipt(self):
        response_one = self.client.post(
            self.url,
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-receipt-001",
        )

        response_two = self.client.post(
            self.url,
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-receipt-001",
        )

        self.assertEqual(
            response_one.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response_two.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response_one.data["id"],
            response_two.data["id"],
        )

        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_idempotency_key_with_different_payload_is_rejected(self):
        first_response = self.client.post(
            self.url,
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-receipt-002",
        )

        changed_payload = {
            **self.payload,
            "notes": "Different request",
        }

        second_response = self.client.post(
            self.url,
            changed_payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-receipt-002",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
