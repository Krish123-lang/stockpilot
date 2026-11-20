
from django.urls import path

from apps.products.views import (CategoryViewSet, ProductViewSet, ProductVariantViewSet)


urlpatterns = [
    # Categories
    path("organizations/<uuid:organization_id>/categories/",
        CategoryViewSet.as_view({
            "get": "list",
            "post": "create",
        }),
        name="category-list",
    ),

    path("organizations/<uuid:organization_id>/categories/<uuid:pk>/",
        CategoryViewSet.as_view({
            "get": "retrieve",
            "put": "update",
            "patch": "partial_update",
        }),
        name="category-detail",
    ),

    # Products
    path("organizations/<uuid:organization_id>/products/",
        ProductViewSet.as_view({
            "get": "list",
            "post": "create",
        }),
        name="product-list",
    ),

    path("organizations/<uuid:organization_id>/products/<uuid:pk>/",
        ProductViewSet.as_view({
            "get": "retrieve",
            "put": "update",
            "patch": "partial_update",
        }),
        name="product-detail",
    ),

    # Variants
    path("organizations/<uuid:organization_id>/variants/",
        ProductVariantViewSet.as_view({
            "get": "list",
            "post": "create",
        }),
        name="variant-list",
    ),

    path("organizations/<uuid:organization_id>/variants/<uuid:pk>/",
        ProductVariantViewSet.as_view({
            "get": "retrieve",
            "put": "update",
            "patch": "partial_update",
        }),
        name="variant-detail",
    ),
]
