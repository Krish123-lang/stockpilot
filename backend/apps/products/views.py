from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from apps.organizations.permissions import (IsActiveOrganizationMember,)
from apps.products.models import (Category,Product,ProductVariant,)
from apps.products.serializers import (CategorySerializer,ProductSerializer,ProductVariantSerializer,)


class OrganizationScopedViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet for organization-owned resources.
    """

    permission_classes = [IsAuthenticated,IsActiveOrganizationMember,]

    # Prevent hard deletion through these APIs.
    # Records should be deactivated instead.
    http_method_names = ["get","post","put","patch","head","options",]

    @property
    def organization(self):
        return self.request.organization_membership.organization


class CategoryViewSet(OrganizationScopedViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    
    def get_queryset(self):
        return (Category.objects.filter(organization=self.organization).order_by("name"))


class ProductViewSet(OrganizationScopedViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def get_queryset(self):
        return (Product.objects.filter(organization=self.organization).select_related("category").order_by("name"))


class ProductVariantViewSet(OrganizationScopedViewSet):
    serializer_class = ProductVariantSerializer
    queryset = ProductVariant.objects.all()

    def get_queryset(self):
        return (ProductVariant.objects.filter(organization=self.organization).select_related("product").order_by("sku"))
