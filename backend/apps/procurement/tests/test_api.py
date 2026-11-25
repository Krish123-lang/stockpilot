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

class PurchaseOrderRetrievalAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="po-reader@example.com",
            password="TestPassword123!",
        )

        self.organization = Organization.objects.create(
            name="PO Reader Electronics",
            slug="po-reader-electronics",
        )

        self.membership = Membership.objects.create(
            organization=self.organization,
            user=self.user,
            role=Membership.Role.OWNER,
        )

        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Samsung Distributor",
        )

        self.product = Product.objects.create(
            organization=self.organization,
            name="Samsung Laptop",
        )

        self.variant = ProductVariant.objects.create(
            organization=self.organization,
            product=self.product,
            name="Samsung Laptop 16GB",
            sku="SAMSUNG-LAPTOP-001",
            unit=ProductVariant.Unit.PIECE,
            cost_price=Decimal("50000.00"),
            selling_price=Decimal("60000.00"),
        )

        self.purchase_order = PurchaseOrder.objects.create(
            organization=self.organization,
            supplier=self.supplier,
            created_by=self.user,
            notes="Test purchase order",
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

        self.list_url = reverse(
            "purchase-order-list",
            kwargs={
                "organization_id": self.organization.id,
            },
        )

        self.detail_url = reverse(
            "purchase-order-detail",
            kwargs={
                "organization_id": self.organization.id,
                "pk": self.purchase_order.id,
            },
        )

        self.client.force_authenticate(user=self.user)

    def test_owner_can_list_purchase_orders(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)

        self.assertEqual(
            response.data["results"][0]["id"],
            str(self.purchase_order.id),
        )

    def test_all_active_roles_can_list_purchase_orders(self):
        roles = [
            Membership.Role.OWNER,
            Membership.Role.MANAGER,
            Membership.Role.SALES,
            Membership.Role.INVENTORY,
        ]

        for role in roles:
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])

                response = self.client.get(self.list_url)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_200_OK,
                )

    def test_all_active_roles_can_retrieve_purchase_order(self):
        roles = [
            Membership.Role.OWNER,
            Membership.Role.MANAGER,
            Membership.Role.SALES,
            Membership.Role.INVENTORY,
        ]

        for role in roles:
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])

                response = self.client.get(self.detail_url)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_200_OK,
                )

    def test_unauthenticated_user_cannot_list_purchase_orders(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.list_url)

        self.assertIn(
            response.status_code,
            [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ],
        )

    def test_inactive_membership_cannot_list_purchase_orders(self):
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_foreign_organization_purchase_order_returns_404(self):
        other_user = User.objects.create_user(
            email="foreign-po-user@example.com",
            password="TestPassword123!",
        )

        other_organization = Organization.objects.create(
            name="Foreign Electronics",
            slug="foreign-electronics",
        )

        other_supplier = Supplier.objects.create(
            organization=other_organization,
            name="Foreign Supplier",
        )

        foreign_order = PurchaseOrder.objects.create(
            organization=other_organization,
            supplier=other_supplier,
            created_by=other_user,
        )

        response = self.client.get(
            reverse(
                "purchase-order-detail",
                kwargs={
                    "organization_id": self.organization.id,
                    "pk": foreign_order.id,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_does_not_include_foreign_organization_orders(self):
        other_user = User.objects.create_user(
            email="foreign-list-user@example.com",
            password="TestPassword123!",
        )

        other_organization = Organization.objects.create(
            name="Another Electronics",
            slug="another-electronics",
        )

        other_supplier = Supplier.objects.create(
            organization=other_organization,
            name="Another Supplier",
        )

        PurchaseOrder.objects.create(
            organization=other_organization,
            supplier=other_supplier,
            created_by=other_user,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 1)

        returned_ids = {
            item["id"] for item in response.data["results"]
        }

        self.assertEqual(
            returned_ids,
            {str(self.purchase_order.id)},
        )

    def test_filter_by_status(self):
        response = self.client.get(
            self.list_url,
            {"status": PurchaseOrder.Status.ORDERED},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 1)

        self.assertEqual(
            response.data["results"][0]["status"],
            PurchaseOrder.Status.ORDERED,
        )

    def test_invalid_status_filter_returns_400(self):
        response = self.client.get(
            self.list_url,
            {"status": "INVALID_STATUS"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_search_by_order_number(self):
        response = self.client.get(
            self.list_url,
            {"search": self.purchase_order.order_number},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 1)

    def test_search_by_supplier_name(self):
        response = self.client.get(
            self.list_url,
            {"search": "Samsung"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 1)

    def test_search_with_no_match_returns_empty_results(self):
        response = self.client.get(
            self.list_url,
            {"search": "Nonexistent Supplier"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_pagination(self):
        for index in range(2):
            PurchaseOrder.objects.create(
                organization=self.organization,
                supplier=self.supplier,
                created_by=self.user,
                notes=f"Additional order {index}",
            )

        response = self.client.get(
            self.list_url,
            {"page": 1, "page_size": 2},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])

    def test_page_size_cannot_exceed_maximum(self):
        response = self.client.get(
            self.list_url,
            {"page_size": 500},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        # The maximum configured page size is 100.
        self.assertLessEqual(
            len(response.data["results"]),
            100,
        )

    def test_detail_contains_purchase_order_items_and_totals(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        data = response.data

        self.assertEqual(
            data["id"],
            str(self.purchase_order.id),
        )

        self.assertEqual(
            data["supplier"]["name"],
            "Samsung Distributor",
        )

        self.assertEqual(
            data["created_by_email"],
            self.user.email,
        )

        self.assertEqual(
            data["total_amount"],
            "500000.00",
        )

        self.assertEqual(len(data["items"]), 1)

        item = data["items"][0]

        self.assertEqual(
            item["product_name"],
            "Samsung Laptop",
        )

        self.assertEqual(
            item["variant_name"],
            "Samsung Laptop 16GB",
        )

        self.assertEqual(
            item["sku"],
            "SAMSUNG-LAPTOP-001",
        )

        self.assertEqual(
            item["quantity_ordered"],
            "10.000",
        )

        self.assertEqual(
            item["unit_cost"],
            "50000.00",
        )

        self.assertEqual(
            item["line_total"],
            "500000.00",
        )

    def test_detail_for_nonexistent_purchase_order_returns_404(self):
        import uuid

        response = self.client.get(
            reverse(
                "purchase-order-detail",
                kwargs={
                    "organization_id": self.organization.id,
                    "pk": uuid.uuid4(),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )