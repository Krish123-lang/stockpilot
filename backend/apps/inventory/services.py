from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import InventoryBalance, StockMovement


@transaction.atomic
def get_or_create_inventory_balance(*, organization, variant):
    if variant.organization_id != organization.id:
        raise ValidationError(
            "Product variant does not belong to this organization."
        )

    balance, _ = InventoryBalance.objects.get_or_create(
        organization=organization,
        variant=variant,
    )

    return balance


def validate_movement_rules(*, movement_type, quantity_delta, damaged_delta):
    if movement_type == StockMovement.MovementType.RECEIPT:
        if quantity_delta <= 0:
            raise ValidationError(
                "A receipt must increase physical inventory."
            )

    elif movement_type == StockMovement.MovementType.SALE:
        if quantity_delta >= 0 or damaged_delta != 0:
            raise ValidationError(
                "A sale must decrease physical inventory without changing damaged quantity."
            )

    elif movement_type == StockMovement.MovementType.CUSTOMER_RETURN:
        if quantity_delta <= 0:
            raise ValidationError(
                "A customer return must increase physical inventory."
            )

        if damaged_delta < 0 or damaged_delta > quantity_delta:
            raise ValidationError(
                "Damaged quantity in a return must be between zero and the returned quantity."
            )

    elif movement_type == StockMovement.MovementType.DAMAGE:
        if quantity_delta != 0 or damaged_delta <= 0:
            raise ValidationError(
                "A damage movement must increase damaged quantity without changing physical inventory."
            )

    elif movement_type == StockMovement.MovementType.REPAIR:
        if quantity_delta != 0 or damaged_delta >= 0:
            raise ValidationError(
                "A repair must decrease damaged quantity without changing physical inventory."
            )

    elif movement_type == StockMovement.MovementType.ADJUSTMENT:
        if quantity_delta == 0 and damaged_delta == 0:
            raise ValidationError(
                "An adjustment must change inventory."
            )

    elif movement_type == StockMovement.MovementType.REVERSAL:
        raise ValidationError(
            "Reversal movements require dedicated reversal logic."
        )


@transaction.atomic
def apply_stock_movement(*,organization, variant, movement_type, quantity_delta, damaged_delta=Decimal("0.000"), created_by, reason=""):
    quantity_delta = Decimal(str(quantity_delta))
    damaged_delta = Decimal(str(damaged_delta))
    
    if movement_type not in StockMovement.MovementType.values:
        raise ValidationError("Invalid stock movement type.")
    
    if not quantity_delta.is_finite() or not damaged_delta.is_finite():
        raise ValidationError("Stock quantities must be finite numbers.")

    if variant.organization_id != organization.id:
        raise ValidationError("Product variant does not belong to this organization.")

    if quantity_delta == 0 and damaged_delta == 0:
        raise ValidationError("A stock movement must change inventory.")
    
    validate_movement_rules(movement_type=movement_type, quantity_delta=quantity_delta, damaged_delta=damaged_delta,)

    try:
        balance = (InventoryBalance.objects.select_for_update().get(organization=organization,variant=variant,))
    except InventoryBalance.DoesNotExist:
        raise ValidationError("Inventory balance does not exist. Initialize inventory before applying movements.")

    new_quantity = balance.quantity_on_hand + quantity_delta
    new_damaged = balance.quantity_damaged + damaged_delta

    if new_quantity < 0:
        raise ValidationError("Insufficient physical inventory.")

    if new_damaged < 0:
        raise ValidationError("Damaged inventory cannot become negative.")

    if new_damaged > new_quantity:
        raise ValidationError("Damaged inventory cannot exceed physical inventory.")

    balance.quantity_on_hand = new_quantity
    balance.quantity_damaged = new_damaged
    balance.save(update_fields=["quantity_on_hand","quantity_damaged","updated_at",])

    movement = StockMovement.objects.create(organization=organization,variant=variant,movement_type=movement_type,quantity_delta=quantity_delta,damaged_delta=damaged_delta,quantity_after=new_quantity,damaged_after=new_damaged,created_by=created_by,reason=reason,)
    
    

    return movement
