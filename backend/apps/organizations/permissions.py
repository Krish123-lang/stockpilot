from rest_framework.permissions import BasePermission
from apps.organizations.models import Membership

class IsActiveOrganizationMember(BasePermission):
    """
    Allows access only to authenticated users
    with an active membership in the requested organization.
    """

    message = "You are not an active member of this organization."

    def has_permission(self, request, view):
        # 1. Authentication check
        if not request.user or not request.user.is_authenticated:
            return False

        # 2. Get organization ID from the URL
        organization_id = view.kwargs.get("organization_id")

        if not organization_id:
            return False

        # 3. Verify active membership and active organization
        membership = (Membership.objects.select_related("organization").filter(user=request.user,organization_id=organization_id,is_active=True,organization__is_active=True,).first())

        if membership is None:
            return False

        # 4. Make verified membership available to the view
        request.organization_membership = membership

        return True


class HasOrganizationRole(BasePermission):
    """
    Checks whether the verified organization membership
    has a role permitted for the current view action.

    IsActiveOrganizationMember must run before this permission.
    """

    message = "Your role does not have permission to perform this action."

    def has_permission(self, request, view):
        membership = getattr(request,"organization_membership",None,)

        if membership is None:
            return False

        role_permissions = getattr(view,"role_permissions",{},)
        allowed_roles = role_permissions.get(getattr(view, "action", None),set(),)
        return membership.role in allowed_roles
