from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.procurement.models import (PurchaseOrder,PurchaseOrderItem,PurchaseOrderSequence,Supplier)


@transaction.atomic
def submit_purchase_order(purchase_order_id):
    """
    Submit a draft purchase order.

    Responsibilities:
    - Lock the purchase order.
    - Validate the supplier and purchase order items.
    - Generate a unique organization-specific order number.
    - Transition the PO from DRAFT to ORDERED.
    - Roll back everything if any operation fails.
    """

    # Lock the purchase order to prevent concurrent submissions.
    try:
        purchase_order = (PurchaseOrder.objects.select_for_update().get(pk=purchase_order_id))
    except PurchaseOrder.DoesNotExist:
        raise ValidationError("Purchase order does not exist.")

    # Only drafts can be submitted.
    if purchase_order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("Only draft purchase orders can be submitted.")

    if purchase_order.order_number is not None:
        raise ValidationError("This purchase order already has an order number.")

    # Lock the supplier so its active state cannot change
    # concurrently while this submission is being processed.
    try:
        supplier = (Supplier.objects.select_for_update().get(pk=purchase_order.supplier_id))
    except Supplier.DoesNotExist:
        raise ValidationError("Purchase order supplier does not exist.")

    if not supplier.is_active:
        raise ValidationError("Cannot submit a purchase order to an inactive supplier.")

    if supplier.organization_id != purchase_order.organization_id:
        raise ValidationError("Supplier must belong to the purchase order organization.")

    # Lock and load the purchase order items.
    items = list(PurchaseOrderItem.objects.select_for_update().select_related("variant").filter(purchase_order=purchase_order))

    if not items:
        raise ValidationError("A purchase order must contain at least one item.")

    # Validate the purchase order and every item.
    purchase_order.full_clean()

    for item in items:
        item.full_clean()

    # Use the configured local timezone.
    now = timezone.now()
    year = timezone.localdate().year

    # get_or_create handles the race when two transactions
    # attempt to create the same organization/year sequence.
    sequence, _ = PurchaseOrderSequence.objects.get_or_create(organization_id=purchase_order.organization_id,year=year,defaults={"last_number": 0},)

    # Lock the sequence row before incrementing it.
    sequence = (PurchaseOrderSequence.objects.select_for_update().get(pk=sequence.pk))

    sequence.last_number += 1
    sequence.save(update_fields=["last_number", "updated_at"])

    # Generate the organization-specific purchase order number.
    order_number = f"PO-{year}-{sequence.last_number:06d}"

    # Update the purchase order.
    purchase_order.order_number = order_number
    purchase_order.status = PurchaseOrder.Status.ORDERED
    purchase_order.submitted_at = now
    purchase_order.ordered_at = now

    purchase_order.full_clean()

    purchase_order.save(
        update_fields=["order_number","status","submitted_at","ordered_at","updated_at",])

    return purchase_order
