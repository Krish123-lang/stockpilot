from django.core.exceptions import ValidationError
from django.db import transaction
from apps.inventory.models import InventoryBalance, StockMovement
from decimal import Decimal, InvalidOperation
from apps.inventory.models import StockAdjustment
from apps.organizations.models import Membership
from django.utils import timezone

@transaction.atomic
def get_or_create_inventory_balance(*, organization, variant):
    if variant.organization_id != organization.id:
        raise ValidationError("Product variant does not belong to this organization.")

    balance, _ = InventoryBalance.objects.get_or_create(organization=organization,variant=variant,)
    return balance


def validate_movement_rules(*, movement_type, quantity_delta, damaged_delta):
    if movement_type == StockMovement.MovementType.RECEIPT:
        if quantity_delta <= 0:
            raise ValidationError("A receipt must increase physical inventory.")

    elif movement_type == StockMovement.MovementType.SALE:
        if quantity_delta >= 0 or damaged_delta != 0:
            raise ValidationError("A sale must decrease physical inventory without changing damaged quantity.")

    elif movement_type == StockMovement.MovementType.CUSTOMER_RETURN:
        if quantity_delta <= 0:
            raise ValidationError("A customer return must increase physical inventory.")

        if damaged_delta < 0 or damaged_delta > quantity_delta:
            raise ValidationError("Damaged quantity in a return must be between zero and the returned quantity.")

    elif movement_type == StockMovement.MovementType.DAMAGE:
        if quantity_delta != 0 or damaged_delta <= 0:
            raise ValidationError("A damage movement must increase damaged quantity without changing physical inventory.")

    elif movement_type == StockMovement.MovementType.REPAIR:
        if quantity_delta != 0 or damaged_delta >= 0:
            raise ValidationError("A repair must decrease damaged quantity without changing physical inventory.")

    elif movement_type == StockMovement.MovementType.ADJUSTMENT:
        if quantity_delta == 0 and damaged_delta == 0:
            raise ValidationError("An adjustment must change inventory.")

    elif movement_type == StockMovement.MovementType.REVERSAL:
        raise ValidationError("Reversal movements require dedicated reversal logic.")


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

@transaction.atomic
def create_stock_adjustment(*,organization,variant,quantity_change,damaged_quantity_change=Decimal("0.000"),reason,created_by):
    # Verify that the organization is active.
    if not organization.is_active:
        raise ValidationError("This organization is inactive.")

    # Verify that the user is active.
    if not created_by.is_active:
        raise ValidationError("This user account is inactive.")

    # Verify organization membership and permission to request adjustments.
    membership = Membership.objects.filter(organization=organization,user=created_by,is_active=True,organization__is_active=True,role__in=[Membership.Role.OWNER,Membership.Role.MANAGER,Membership.Role.INVENTORY,],).first()

    if membership is None:
        raise ValidationError("You are not authorized to request stock adjustments.")

    # Verify variant ownership.
    if variant.organization_id != organization.id:
        raise ValidationError("Product variant does not belong to this organization.")

    # Validate and normalize decimal values.
    try:
        quantity_change = Decimal(str(quantity_change))
        damaged_quantity_change = Decimal(str(damaged_quantity_change))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Invalid inventory quantity.")

    if (not quantity_change.is_finite()or not damaged_quantity_change.is_finite()):
        raise ValidationError("Inventory quantities must be finite numbers.")

    # An adjustment must actually change inventory.
    if quantity_change == 0 and damaged_quantity_change == 0:
        raise ValidationError("An adjustment must change inventory.")

    # Validate the explanation.
    reason = str(reason).strip()

    if not reason:
        raise ValidationError("A reason is required for stock adjustments.")

    adjustment = StockAdjustment(organization=organization,variant=variant,quantity_change=quantity_change,damaged_quantity_change=damaged_quantity_change,reason=reason,created_by=created_by,)
    adjustment.full_clean()
    adjustment.save()
    return adjustment

@transaction.atomic
def approve_stock_adjustment(*, adjustment_id, approved_by):

    # Lock the adjustment to prevent concurrent approvals.
    try:
        adjustment = (StockAdjustment.objects.select_for_update().get(id=adjustment_id))
    except StockAdjustment.DoesNotExist:
        raise ValidationError("Stock adjustment does not exist.")

    # Verify the reviewer account.
    if not approved_by.is_active:
        raise ValidationError("This user account is inactive.")

    # Verify organization membership and approval permission.
    membership = Membership.objects.filter(organization=adjustment.organization,user=approved_by,is_active=True,organization__is_active=True,role__in=[Membership.Role.OWNER,Membership.Role.MANAGER,],).first()

    if membership is None:
        raise ValidationError("You are not authorized to approve stock adjustments.")

    # Prevent self-approval.
    if adjustment.created_by_id == approved_by.id:
        raise ValidationError("You cannot approve your own stock adjustment.")

    # Only pending adjustments can be approved.
    if adjustment.status != StockAdjustment.Status.PENDING:
        raise ValidationError("Only pending adjustments can be approved.")

    # Apply the inventory change and create its ledger entry.
    movement = apply_stock_movement(organization=adjustment.organization,variant=adjustment.variant,movement_type=StockMovement.MovementType.ADJUSTMENT,quantity_delta=adjustment.quantity_change,damaged_delta=adjustment.damaged_quantity_change,created_by=approved_by,reason=adjustment.reason,)

    # Update the adjustment's approval information.
    adjustment.status = StockAdjustment.Status.APPROVED
    adjustment.approved_by = approved_by
    adjustment.approved_at = timezone.now()
    adjustment.save(update_fields=["status","approved_by","approved_at",])

    return adjustment


@transaction.atomic
def reject_stock_adjustment(*,adjustment_id,rejected_by,rejection_reason):
    try:
        adjustment = (StockAdjustment.objects.select_for_update().get(id=adjustment_id))
    except StockAdjustment.DoesNotExist:
        raise ValidationError("Stock adjustment does not exist.")

    if not rejected_by.is_active:
        raise ValidationError("This user account is inactive.")

    membership = Membership.objects.filter(organization=adjustment.organization,user=rejected_by,is_active=True,organization__is_active=True,role__in=[Membership.Role.OWNER,Membership.Role.MANAGER,],).first()

    if membership is None:
        raise ValidationError("You are not authorized to reject stock adjustments.")

    if adjustment.created_by_id == rejected_by.id:
        raise ValidationError("You cannot reject your own stock adjustment.")

    if adjustment.status != StockAdjustment.Status.PENDING:
        raise ValidationError("Only pending adjustments can be rejected.")

    rejection_reason = (rejection_reason or "").strip()

    if not rejection_reason:
        raise ValidationError("A rejection reason is required.")

    adjustment.status = StockAdjustment.Status.REJECTED
    adjustment.rejected_by = rejected_by
    adjustment.rejected_at = timezone.now()
    adjustment.rejection_reason = rejection_reason

    adjustment.save(update_fields=["status","rejected_by","rejected_at","rejection_reason",])

    return adjustment
