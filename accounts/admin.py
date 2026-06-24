from django.contrib import admin
from .models import (
    AttendanceMaster,
    AttendanceReq,
    ClientVisitor,
    DeptMaster,
    DesigMaster,
    EmpItemMaster,
    EmpMaster,
    EmpTemp,
    Events,
    HolidayMaster,
    LeaveMaster,
    LeaveRequest,
    LogoMaster,
    SystemSettings,
    TitleMaster,
    Users,
    EmployeeLocationTracking,
)
from django.utils.html import format_html
from django.urls import reverse

# Register your models here.
admin.site.register(AttendanceReq)
admin.site.register(DeptMaster)
admin.site.register(DesigMaster)
admin.site.register(EmpItemMaster)
admin.site.register(EmpMaster)
admin.site.register(Events)
admin.site.register(HolidayMaster)
admin.site.register(LeaveMaster)
admin.site.register(LeaveRequest)
admin.site.register(LogoMaster)
admin.site.register(SystemSettings)
admin.site.register(TitleMaster)
admin.site.register(Users)


# ---- AttendanceMaster admin with "View Location" link ----
@admin.register(AttendanceMaster)
class AttendanceMasterAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "emp_id",
        "att_date",
        "check_in",
        "check_out",
        "attendance_status",
        "view_location_button",
    )
    list_filter = ("att_date", "attendance_status")
    search_fields = ("full_name", "emp_id")
    ordering = ("-att_date",)

    def view_location_button(self, obj):
        """Render a 'View Location' link that opens the movement map for this attendance record."""
        if not obj.emp_id or not obj.att_date:
            return "-"
        session_date_str = obj.att_date.strftime("%Y-%m-%d") if obj.att_date else ""
        url = reverse(
            "employee_location_map",
            kwargs={"emp_id": str(obj.emp_id), "session_date": session_date_str},
        )
        return format_html(
            '<a href="{}" target="_blank" '
            'style="background:#17a2b8;color:#fff;padding:3px 10px;'
            'border-radius:4px;text-decoration:none;font-size:12px;">'
            '<i class="fas fa-map-marker-alt"></i> View Location</a>',
            url,
        )

    view_location_button.short_description = "Location Map"
    view_location_button.allow_tags = True


# ---- EmpTemp admin — with quick-approve link ----
@admin.register(EmpTemp)
class EmpTempAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "contact",
        "email",
        "status",
        "created_at",
        "approve_link",
    )
    list_filter = ("status",)
    search_fields = ("full_name", "contact", "email")
    ordering = ("-created_at",)

    def approve_link(self, obj):
        if obj.status == "PENDING":
            url = reverse("reg_user_approve", kwargs={"id": obj.id})
            return format_html(
                '<a href="{}" style="background:#28a745;color:#fff;padding:3px 10px;'
                'border-radius:4px;text-decoration:none;font-size:12px;">Approve</a>',
                url,
            )
        return obj.status

    approve_link.short_description = "Action"
    approve_link.allow_tags = True


# ---- Custom Django User admin ----
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin


try:
    admin.site.unregister(User)
except Exception:
    pass


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("get_full_name", "username", "email", "is_active", "is_staff")
    list_display_links = ("get_full_name",)
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_active", "is_staff", "is_superuser")

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    get_full_name.short_description = "Full Name"
    get_full_name.admin_order_field = "first_name"


# ---- Employee Location Tracking admin with "View Map" button ----
@admin.register(EmployeeLocationTracking)
class EmployeeLocationTrackingAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "emp_id",
        "session_date",
        "timestamp",
        "latitude",
        "longitude",
        "is_checkin_point",
        "view_map_button",
    )
    list_filter = ("session_date", "emp_id", "is_checkin_point")
    search_fields = ("emp_id", "full_name")
    ordering = ("-session_date", "emp_id", "timestamp")
    readonly_fields = ("timestamp",)

    def view_map_button(self, obj):
        """Render a 'View Map' link beside every row that opens the movement map."""
        session_date_str = (
            obj.session_date.strftime("%Y-%m-%d") if obj.session_date else ""
        )
        if not obj.emp_id or not session_date_str:
            return "-"
        url = reverse(
            "employee_location_map",
            kwargs={"emp_id": obj.emp_id, "session_date": session_date_str},
        )
        return format_html(
            '<a href="{}" target="_blank" '
            'style="background:#17a2b8;color:#fff;padding:3px 10px;'
            'border-radius:4px;text-decoration:none;font-size:12px;">'
            '<i class="fas fa-map-marked-alt"></i> View Map</a>',
            url,
        )

    view_map_button.short_description = "Movement Map"
    view_map_button.allow_tags = True


# ---- ClientVisitor admin — full management view ----
@admin.register(ClientVisitor)
class ClientVisitorAdmin(admin.ModelAdmin):
    list_display = (
        "client_name",
        "employee_display",
        "phone",
        "location",
        "visit_date",
        "created_at",
        "photo_preview",
    )
    list_filter = ("visit_date", "emp_name")
    search_fields = ("client_name", "phone", "emp_name", "location")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "photo_preview")

    def employee_display(self, obj):
        name = obj.emp_name or (obj.user.get_full_name() if obj.user else "")
        username = obj.user.username if obj.user else ""
        return f"{name} ({username})" if name else username

    employee_display.short_description = "Employee"
    employee_display.admin_order_field = "emp_name"

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:80px;height:80px;object-fit:cover;'
                'border-radius:6px;border:1px solid #ccc;" />',
                obj.photo.url,
            )
        return "No photo"

    photo_preview.short_description = "Client Photo"
