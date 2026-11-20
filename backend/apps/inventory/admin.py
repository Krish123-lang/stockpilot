from django.contrib import admin

from apps.inventory.models import InventoryBalance, StockAdjustment, StockMovement


@admin.register(InventoryBalance)
class InventoryBalanceAdmin(admin.ModelAdmin):
    list_display = ("variant", "organization", "quantity_on_hand", "quantity_damaged", "updated_at",)
    list_filter = ("organization",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("variant", "organization", "movement_type", "quantity_delta", "damaged_delta", "created_by", "created_at",)
    list_filter = ("movement_type", "organization")
    readonly_fields = ("organization", "variant", "movement_type", "quantity_delta", "damaged_delta", "quantity_after", "damaged_after", "reason", "created_by", "created_at",)
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("variant","organization","quantity_change","damaged_quantity_change","status","created_by","approved_by","created_at",)
    list_filter = ("status", "organization")
    readonly_fields = ("organization","variant","quantity_change","damaged_quantity_change","reason","status","created_by","approved_by","created_at","approved_at",)

    def has_delete_permission(self, request, obj=None):
        return False