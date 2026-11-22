from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.organizations.models import Organization, Membership
from apps.products.models import Product, ProductVariant
from apps.inventory.models import InventoryBalance, StockMovement

User = get_user_model()

class InventoryAPITests(APITestCase):
    def setUp(self):
        self.organization_a = Organization.objects.create(name="Everest Electronics",slug="everest-electronics",)
        self.organization_b = Organization.objects.create(name="Himalayan Tech",slug="himalayan-tech",)
        self.user_a = User.objects.create_user(email="usera@example.com",password="TestPassword123!",)
        self.user_b = User.objects.create_user(email="userb@example.com",password="TestPassword123!",)
        Membership.objects.create(organization=self.organization_a,user=self.user_a,role=Membership.Role.OWNER,)
        self.product_a = Product.objects.create(organization=self.organization_a,name="Samsung Galaxy S25",)
        self.product_b = Product.objects.create(organization=self.organization_b,name="MacBook Air",)
        self.variant_a = ProductVariant.objects.create(organization=self.organization_a,product=self.product_a,name="256 GB",sku="SAM-S25-256",unit="PIECE",cost_price=Decimal("85000.00"),selling_price=Decimal("95000.00"),)
        self.variant_b = ProductVariant.objects.create(organization=self.organization_b,product=self.product_b,name="Base Model",sku="MACBOOK-AIR",unit="PIECE",cost_price=Decimal("100000.00"),selling_price=Decimal("120000.00"),)
        self.client.force_authenticate(user=self.user_a)

    def inventory_url(self):
        return reverse("inventory-list",kwargs={"organization_id": self.organization_a.id},)

    def initialize_url(self):
        return reverse("inventory-initialize",kwargs={"organization_id": self.organization_a.id},)

    def movement_url(self):
        return reverse("stock-movement-list",kwargs={"organization_id": self.organization_a.id},)

    def test_user_can_list_own_inventory(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        response = self.client.get(self.inventory_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_user_cannot_access_another_organizations_inventory(self):
        url = reverse("inventory-list",kwargs={"organization_id": self.organization_b.id},)
        response = self.client.get(url)
        self.assertEqual(response.status_code,status.HTTP_403_FORBIDDEN,)

    def test_user_can_initialize_inventory(self):
        response = self.client.post(self.initialize_url(),{"variant": str(self.variant_a.id)},format="json",)
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,)
        balance = InventoryBalance.objects.get(organization=self.organization_a,variant=self.variant_a,)
        self.assertEqual(balance.quantity_on_hand,Decimal("0.000"),)

    def test_user_cannot_initialize_foreign_variant(self):
        response = self.client.post(self.initialize_url(),{"variant": str(self.variant_b.id)},format="json",)
        self.assertEqual(response.status_code,status.HTTP_400_BAD_REQUEST,)

    def test_user_can_create_stock_receipt(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        response = self.client.post(self.movement_url(),{"variant": str(self.variant_a.id),"movement_type": "RECEIPT","quantity_delta": "5.000","reason": "Initial stock receipt",},format="json",)
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,)
        balance = InventoryBalance.objects.get(organization=self.organization_a,variant=self.variant_a,)
        self.assertEqual(balance.quantity_on_hand,Decimal("5.000"),)
        self.assertEqual(StockMovement.objects.filter(organization=self.organization_a,).count(),1,)

    def test_user_cannot_create_movement_for_foreign_variant(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        response = self.client.post(self.movement_url(),{"variant": str(self.variant_b.id),"movement_type": "RECEIPT","quantity_delta": "5.000",},format="json",)
        self.assertEqual(response.status_code,status.HTTP_400_BAD_REQUEST,)

    def test_sale_cannot_reduce_stock_below_zero(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        response = self.client.post(self.movement_url(),{"variant": str(self.variant_a.id),"movement_type": "SALE","quantity_delta": "-5.000",},format="json",)
        self.assertEqual(response.status_code,status.HTTP_400_BAD_REQUEST,)
        balance = InventoryBalance.objects.get(organization=self.organization_a,variant=self.variant_a,)
        self.assertEqual(balance.quantity_on_hand,Decimal("0.000"),)

    def test_generic_endpoint_rejects_adjustment(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        response = self.client.post(self.movement_url(),{"variant": str(self.variant_a.id),"movement_type": "ADJUSTMENT","quantity_delta": "5.000","reason": "Attempted direct adjustment",},format="json",)
        self.assertEqual(response.status_code,status.HTTP_400_BAD_REQUEST,)

    def test_user_can_list_stock_movements(self):
        InventoryBalance.objects.create(organization=self.organization_a,variant=self.variant_a,)
        self.client.post(self.movement_url(),{"variant": str(self.variant_a.id),"movement_type": "RECEIPT","quantity_delta": "5.000",},format="json",)
        response = self.client.get(self.movement_url())
        self.assertEqual(response.status_code,status.HTTP_200_OK,)
        self.assertEqual(len(response.data), 1)
