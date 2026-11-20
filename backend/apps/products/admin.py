from django.contrib import admin
from .models import Category, Product, ProductVariant

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name","organization","is_active","created_at",)
    list_filter = ("is_active",)
    search_fields = ("name","organization__name",)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name","organization","category","is_active",)
    list_filter = ("is_active",)
    search_fields = ("name","organization__name",)
    inlines = [ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku","product","organization","selling_price","is_active",)
    list_filter = ("is_active", "unit")
    search_fields = ("sku","barcode","product__name",)
