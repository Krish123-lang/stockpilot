from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.organizations.models import Membership
from apps.organizations.permissions import ( IsActiveOrganizationMember, HasOrganizationRole)
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem
from apps.procurement.serializers import ( GoodsReceiptCreateSerializer, GoodsReceiptResponseSerializer)
from apps.procurement.services import receive_purchase_order
from django.db.models import Q, Prefetch
from rest_framework import mixins, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import GenericViewSet
from apps.procurement.serializers import ( PurchaseOrderListSerializer, PurchaseOrderDetailSerializer)

class GoodsReceiptViewSet(viewsets.GenericViewSet):
    permission_classes = [ IsAuthenticated, IsActiveOrganizationMember, HasOrganizationRole, ]

    role_permissions = {
        "create": { Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.INVENTORY, },
    }

    serializer_class = GoodsReceiptCreateSerializer

    @property
    def organization(self):
        return self.request.organization_membership.organization

    def create(self, request, *args, **kwargs):
        # Resolve the purchase order within the active organization.
        purchase_order = PurchaseOrder.objects.filter( id=self.kwargs["purchase_order_id"], organization=self.organization, ).first()

        if purchase_order is None:
            raise DRFValidationError( {"purchase_order": "Purchase order does not exist."} )

        # Validate request body.
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        # Read the optional idempotency key from the HTTP header.
        idempotency_key = request.headers.get("Idempotency-Key")

        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()

            if not idempotency_key:
                raise DRFValidationError( {"Idempotency-Key": "This header cannot be empty."} )

            if len(idempotency_key) > 128:
                raise DRFValidationError( {"Idempotency-Key": "Maximum length is 128 characters."} )

        try:
            receipt, created = receive_purchase_order(
                purchase_order_id=purchase_order.id,
                received_by=request.user,
                items=input_serializer.validated_data["items"],
                supplier_reference=input_serializer.validated_data["supplier_reference"],
                notes=input_serializer.validated_data["notes"],
                idempotency_key=idempotency_key,
                return_created=True,
            )

        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)

        # Load related receipt items efficiently for the response.
        receipt = ( receipt.__class__.objects .prefetch_related("items") .get(id=receipt.id))
        response_serializer = GoodsReceiptResponseSerializer( receipt, context=self.get_serializer_context(), )
        response_status = (
            status.HTTP_201_CREATED
            if created
            else status.HTTP_200_OK
        )

        return Response(
            response_serializer.data,
            status=response_status,
        )

class PurchaseOrderPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class PurchaseOrderViewSet( mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    permission_classes = [ IsAuthenticated, IsActiveOrganizationMember, HasOrganizationRole,]
    pagination_class = PurchaseOrderPagination
    role_permissions = {
        "list": ["OWNER", "MANAGER", "SALES", "INVENTORY"],
        "retrieve": ["OWNER", "MANAGER", "SALES", "INVENTORY"],
    }

    def get_queryset(self):
        queryset = (PurchaseOrder.objects.filter( organization_id=self.kwargs["organization_id"],).select_related("supplier", "created_by"))

        if self.action == "list":
            # The list serializer calculates total_amount from items.
            queryset = queryset.prefetch_related("items")

            status_filter = self.request.query_params.get("status")
            if status_filter:
                queryset = queryset.filter(status=status_filter)

            search = self.request.query_params.get("search")
            if search:
                queryset = queryset.filter( Q(order_number__icontains=search) | Q(supplier__name__icontains=search))

        elif self.action == "retrieve":
            queryset = queryset.prefetch_related( Prefetch( "items", queryset=( PurchaseOrderItem.objects .select_related("variant", "variant__product")),) )

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PurchaseOrderDetailSerializer

        return PurchaseOrderListSerializer

    def list(self, request, *args, **kwargs):
        allowed_statuses = { choice[0] for choice in PurchaseOrder.Status.choices}

        status_filter = request.query_params.get("status")

        if status_filter and status_filter not in allowed_statuses:
            return Response(
                {
                    "status": [
                        f"Invalid status. Allowed values: "
                        f"{', '.join(sorted(allowed_statuses))}."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().list(request, *args, **kwargs)