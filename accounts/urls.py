from django.urls import path
from . import views


urlpatterns = [
    path("", views.login, name="login"),
    path("home/", views.home, name="home"),
    # Authentication URLs
    path("register/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("manage_account/", views.manage_account, name="manage_account"),
    # Password Reset URLs
    path("forgot_password/", views.forgot_password, name="forgot_password"),
    path(
        "reset_password/<uidb64>/<token>/", views.reset_password, name="reset_password"
    ),
    path("reset_password_sent/", views.reset_password_sent, name="reset_password_sent"),
    path(
        "reset_password_complete/",
        views.reset_password_complete,
        name="reset_password_complete",
    ),
    # User Management URLs
    path("user_list/", views.user_list, name="user_list"),
    path("user_add/", views.user_add, name="user_add"),
    path("user_edit/<int:id>/", views.user_edit, name="user_edit"),
    path("user_delete/<int:id>/", views.user_delete, name="user_delete"),
    # Registration Request Management URLs
    path("reg_user_list/", views.reg_user_list, name="reg_user_list"),
    path("reg_user_approve/<int:id>/", views.reg_user_approve, name="reg_user_approve"),
    path("reg_user_reject/<int:id>/", views.reg_user_reject, name="reg_user_reject"),
    path(
        "get_employee_by_mobile/",
        views.get_employee_by_mobile,
        name="get_employee_by_mobile",
    ),
    path("department_add/", views.department_add, name="department_add"),
    path("department_list/", views.department_list, name="department_list"),
    path(
        "department_delete/<int:id>/", views.department_delete, name="department_delete"
    ),
    path("department_edit/<int:id>/", views.department_edit, name="department_edit"),
    path("designation_add/", views.designation_add, name="designation_add"),
    path("designation_list/", views.designation_list, name="designation_list"),
    path("designation_edit/<int:id>/", views.designation_edit, name="designation_edit"),
    path(
        "designation_delete/<int:id>/",
        views.designation_delete,
        name="designation_delete",
    ),
    path("employee_list/", views.employee_list, name="employee_list"),
    path("employee_view/<int:id>/", views.employee_view, name="employee_view"),
    path("employee_add/", views.employee_add, name="employee_add"),
    path("employee_edit/<int:id>/", views.employee_edit, name="employee_edit"),
    path("employee_delete/<int:id>/", views.employee_delete, name="employee_delete"),
    # Attendance URLs
    path("employee_checkin/", views.employee_checkin, name="employee_checkin"),
    path("employee_checkout/", views.employee_checkout, name="employee_checkout"),
    path("attendance_list/", views.attendance_list, name="attendance_list"),
    path("attendance_add/", views.attendance_add, name="attendance_add"),
    path("attendance_edit/<int:id>/", views.attendance_edit, name="attendance_edit"),
    path(
        "attendance_detail/<int:id>/", views.attendance_detail, name="attendance_detail"
    ),
    path("attendance_req_list/", views.attendance_req_list, name="attendance_req_list"),
    path("attendance_req_add/", views.attendance_req_add, name="attendance_req_add"),
    path(
        "attendance_req_status_update/<int:id>/",
        views.attendance_req_status_update,
        name="attendance_req_status_update",
    ),
    # Leaves URLs
    path("leave_list/", views.leave_list, name="leave_list"),
    path("leave_add/", views.leave_add, name="leave_add"),
    path("leave_approval_list/", views.leave_approval_list, name="leave_approval_list"),
    path(
        "leave_status_update/<int:id>/",
        views.leave_status_update,
        name="leave_status_update",
    ),
    path("leave_approve/<int:id>/", views.leave_approve, name="leave_approve"),
    path("leave_reject/<int:id>/", views.leave_reject, name="leave_reject"),
    # Holiday URLs
    path("holiday_list/", views.holiday_list, name="holiday_list"),
    path("holiday_add/", views.holiday_add, name="holiday_add"),
    path("holiday_delete/<int:id>/", views.holiday_delete, name="holiday_delete"),
    # Payslip URLs
    path("payslip_generate/", views.payslip_generate, name="payslip_generate"),
    # Settings URLs
    path("company_settings/", views.company_settings, name="company_settings"),
    # Reports URLs
    path("attendance_report/", views.attendance_report, name="attendance_report"),
    # Location Tracking URLs
    path(
        "save_location_update/", views.save_location_update, name="save_location_update"
    ),
    path(
        "employee_location_map/<str:emp_id>/<str:session_date>/",
        views.employee_location_map,
        name="employee_location_map",
    ),
    # Visitor / Client Management URLs
    path("visitor_add/", views.visitor_add, name="visitor_add"),
    path("visitor_list/", views.visitor_list, name="visitor_list"),
    path("visitor_view/<int:id>/", views.visitor_view, name="visitor_view"),
    path("visitor_edit/<int:id>/", views.visitor_edit, name="visitor_edit"),
    path("visitor_delete/<int:id>/", views.visitor_delete, name="visitor_delete"),
]
