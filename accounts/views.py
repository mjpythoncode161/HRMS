from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from .models import (
    DeptMaster,
    DesigMaster,
    EmpMaster,
    AttendanceMaster,
    AttendanceReq,
    LeaveRequest,
    HolidayMaster,
    EmpItemMaster,
    EmpTemp,
    Users,
    SystemSettings,
)
from .forms import departmentForm, designationForm, employeeForm
from .context_processors import save_company_logo
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.urls import reverse

# Create your views here.


def _save_base64_photo(photo_data, prefix):
    """Save a base64 data-URL image under MEDIA_ROOT; return relative path."""
    import base64
    import os
    import uuid

    from django.conf import settings

    if not photo_data or not photo_data.startswith("data:image/"):
        return ""
    try:
        header, imgstr = photo_data.split(";base64,", 1)
        ext = header.split("/")[-1].lower()
        if ext not in ("jpeg", "jpg", "png", "webp"):
            ext = "jpeg"
        filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
        rel_path = os.path.join("attendance_photos", filename).replace("\\", "/")
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(base64.b64decode(imgstr))
        return rel_path
    except Exception:
        return ""


def _format_inr(amount):
    return f"{float(amount):,.2f}"


def _amount_in_words(amount):
    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = [
        "",
        "",
        "Twenty",
        "Thirty",
        "Forty",
        "Fifty",
        "Sixty",
        "Seventy",
        "Eighty",
        "Ninety",
    ]

    def two_digit(n):
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()

    def three_digit(n):
        if n < 100:
            return two_digit(n)
        return (
            ones[n // 100]
            + " Hundred"
            + (" " + two_digit(n % 100) if n % 100 else "")
        ).strip()

    n = int(round(float(amount)))
    if n == 0:
        return "Rupees Zero only"

    parts = []
    crore = n // 10000000
    n %= 10000000
    lakh = n // 100000
    n %= 100000
    thousand = n // 1000
    n %= 1000
    remainder = n

    if crore:
        parts.append(three_digit(crore) + " Crore")
    if lakh:
        parts.append(two_digit(lakh) + " Lakh")
    if thousand:
        parts.append(two_digit(thousand) + " Thousand")
    if remainder:
        parts.append(three_digit(remainder))

    return "Rupees " + " ".join(parts) + " only"


@login_required(login_url="login")
def home(request):
    from datetime import date, datetime

    today = date.today()
    month_start = today.replace(day=1)

    is_admin_dashboard = (
        request.user.is_superuser
        or request.user.is_staff
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    upcoming_holidays = HolidayMaster.objects.filter(holiday_date__gte=today).order_by(
        "holiday_date"
    )[:5]

    context = {
        "is_admin_dashboard": is_admin_dashboard,
        "upcoming_holidays": upcoming_holidays,
        "today": today.strftime("%Y-%m-%d"),
    }

    if is_admin_dashboard:
        context.update(
            {
                "total_employees": EmpMaster.objects.count(),
                "today_attendance": AttendanceMaster.objects.filter(att_date=today).count(),
                "pending_leaves": LeaveRequest.objects.filter(leave_status=0).count(),
                "pending_registrations": EmpTemp.objects.filter(status="PENDING").count(),
            }
        )
    else:
        own_emp = None
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            own_emp = None

        my_attendance_month = 0
        total_late = 0
        total_leave = 0
        today_attendance_record = None
        check_in_iso = ""

        if own_emp:
            emp_id = int(own_emp.emp_id)
            month_qs = AttendanceMaster.objects.filter(
                emp_id=emp_id,
                att_date__gte=month_start,
                att_date__lte=today,
            )
            my_attendance_month = month_qs.filter(
                attendance_status__in=["Present", "Late", "Half Day"]
            ).count()
            total_late = month_qs.filter(attendance_status="Late").count()
            total_leave = LeaveRequest.objects.filter(emp_id=emp_id).count()
            today_attendance_record = AttendanceMaster.objects.filter(
                emp_id=emp_id, att_date=today
            ).first()
            if today_attendance_record and today_attendance_record.check_in:
                check_in_iso = datetime.combine(
                    today, today_attendance_record.check_in
                ).isoformat()

        context.update(
            {
                "own_emp": own_emp,
                "my_attendance_month": my_attendance_month,
                "total_late": total_late,
                "total_leave": total_leave,
                "today_attendance_record": today_attendance_record,
                "check_in_iso": check_in_iso,
                "month_name": today.strftime("%B %Y"),
            }
        )

    return render(request, "accounts/index.html", context)


def get_employee_by_mobile(request):
    """AJAX endpoint to fetch employee details from User table by mobile number"""
    mobile = request.GET.get("mobile", "")
    if mobile:
        # Check User table (username is phone number)
        try:
            user = User.objects.get(username=mobile)
            data = {
                "found": True,
                "full_name": f"{user.first_name} {user.last_name}".strip() or "",
                "email": user.email or "",
                "dob": "",
                "gender": "",
                "address": "",
                "father_name": "",
                "emergency_contact": "",
                "blood_group": "",
                "bank_name": "",
                "branch_name": "",
                "account_name": "",
                "account_number": "",
                "ifsc_code": "",
            }
            return JsonResponse(data)
        except User.DoesNotExist:
            return JsonResponse({"found": False})
    return JsonResponse({"found": False})


def designation_add(request):
    if request.method == "POST":
        dept_name = request.POST.get("department_name", "")
        desig_name = request.POST.get("designation_name", "")
        if dept_name and desig_name:
            desig = DesigMaster()
            desig.dept_name = dept_name
            desig.desig_name = desig_name
            desig.save()
            messages.success(request, "Designation successfully added")
            return redirect("designation_list")
        else:
            messages.error(request, "All fields are required")
    departments = DeptMaster.objects.all()
    return render(
        request, "accounts/designation_add.html", {"departments": departments}
    )


def department_list(request):
    form = DeptMaster.objects.all()
    context = {"form": form}
    return render(request, "accounts/department_list.html", context)


def department_add(request):
    if request.method == "POST":
        dept_name = request.POST.get("department_name", "")
        if dept_name:
            dept = DeptMaster()
            dept.dept_name = dept_name
            dept.save()
            messages.success(request, "Department successfully added")
            return redirect("department_list")
        else:
            messages.error(request, "Department name is required")
    return render(request, "accounts/department_add.html")


def department_edit(request, id):
    obj = get_object_or_404(DeptMaster, id=id)
    if request.method == "POST":
        dept_name = request.POST.get("dept_name", "")
        if dept_name:
            obj.dept_name = dept_name
            obj.save()
            messages.success(request, "Department updated successfully")
            return redirect("department_list")
        else:
            messages.error(request, "Department name is required")
    form = departmentForm(instance=obj)
    context = {"form": form}
    return render(request, "accounts/department_edit.html", context)


def department_delete(request, id):
    obj = get_object_or_404(DeptMaster, id=id)
    obj.delete()
    messages.success(request, "Department deleted successfully")
    return redirect("department_list")


@login_required(login_url="login")
@permission_required("accounts.view_empmaster", raise_exception=True)
def employee_list(request):
    # Check if user is a restricted employee (not admin/superuser)
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    if is_restricted_user:
        # For restricted users, show only their own employee record
        # Match by username (phone number) with contact field
        employees = EmpMaster.objects.filter(contact=request.user.username)
    else:
        # For admins/managers, show all employees
        employees = EmpMaster.objects.all()

    context = {"employees": employees, "is_restricted_user": is_restricted_user}
    return render(request, "accounts/employee_list.html", context)


def employee_view(request, id):
    employee = get_object_or_404(EmpMaster, id=id)
    context = {"employee": employee}
    return render(request, "accounts/employee_view.html", context)


@login_required(login_url="login")
@permission_required("accounts.add_empmaster", raise_exception=True)
def employee_add(request):
    departments = DeptMaster.objects.all()
    designations = DesigMaster.objects.all()
    prefill = None
    reg_id = request.GET.get("reg_id") or request.POST.get("reg_id")
    if reg_id:
        try:
            prefill = EmpTemp.objects.get(id=reg_id)
        except EmpTemp.DoesNotExist:
            reg_id = None

    def render_form():
        return render(
            request,
            "accounts/employee_add.html",
            {
                "departments": departments,
                "designations": designations,
                "prefill": prefill,
                "reg_id": reg_id,
            },
        )

    if request.method == "POST":
        import hashlib

        mobile_no = request.POST.get("mobile_no", "").strip()
        email = request.POST.get("email", "").strip()
        full_name = request.POST.get("full_name", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not mobile_no or len(mobile_no) != 10 or not mobile_no.isdigit():
            messages.error(request, "Mobile number must be exactly 10 digits")
            return render_form()

        if not reg_id:
            if not password:
                messages.error(request, "Password is required for employee login")
                return render_form()
            if password != confirm_password:
                messages.error(request, "Passwords do not match")
                return render_form()
            if Users.objects.filter(contact=mobile_no).exists():
                messages.error(
                    request, "A login account with this mobile number already exists"
                )
                return render_form()
            if Users.objects.filter(email=email).exists():
                messages.error(
                    request, "A login account with this email already exists"
                )
                return render_form()
            if User.objects.filter(username=mobile_no).exists():
                messages.error(
                    request, "A login account with this mobile number already exists"
                )
                return render_form()

        # Create employee object from POST data
        emp = EmpMaster()
        emp.contact = mobile_no
        emp.full_name = full_name
        emp.email = email
        emp.dob = request.POST.get("dob", None) or None
        emp.gender = request.POST.get("gender", "")
        emp.present_addr = request.POST.get("present_address", "")
        emp.perm_addr = request.POST.get("permanent_address", "")
        emp.join_date = request.POST.get("joining_date", None) or None
        emp.end_date = request.POST.get("end_date", None) or None
        emp.emp_type = ""
        emp.check_in = request.POST.get("check_in", None) or None
        emp.check_out = request.POST.get("check_out", None) or None
        emp.dept = request.POST.get("department_name", "")
        emp.desig = request.POST.get("designation_name", "")
        emp.salary_type = request.POST.get("salary_type", "")
        emp.salary_amt = request.POST.get("salary_amount", "")
        emp.full_abs_fine = request.POST.get("full_day_absence_fine", "") or None
        emp.half_abd_fine = request.POST.get("half_day_absence_fine", "") or None
        emp.yearly_leaves = request.POST.get("yearly_leave_limit", "") or None
        emp.bank_name = request.POST.get("bank_name", "")
        emp.branch_name = request.POST.get("branch_name", "")
        emp.account_name = request.POST.get("account_name", "")
        emp.account_no = request.POST.get("account_number", "")
        emp.ifsc_code = request.POST.get("ifsc_code", "")
        # Get max emp_id and add 1 (handle string IDs)
        from django.db.models import Max
        from django.db.models.functions import Cast
        from django.db.models import IntegerField

        max_id = (
            EmpMaster.objects.aggregate(max_id=Max(Cast("emp_id", IntegerField())))[
                "max_id"
            ]
            or 0
        )
        emp.emp_id = str(max_id + 1)
        emp.total_yearly_leaves = emp.yearly_leaves or "0"
        emp.profile_photo = ""
        emp.blood_group = request.POST.get("blood_group", "")
        emp.father_name = request.POST.get("father_name", "")
        emp.emergency_contact = int(request.POST.get("emergency_contact", 0) or 0)
        emp.save()

        # Save Additional Details (EmpItemMaster)
        item_names = request.POST.getlist("item_name[]")
        item_amts = request.POST.getlist("item_amt[]")
        item_amt_types = request.POST.getlist("item_amt_type[]")
        item_types = request.POST.getlist("item_type[]")

        for i in range(len(item_names)):
            if item_names[i]:  # Only save if name is provided
                emp_item = EmpItemMaster()
                emp_item.emp_id = emp.emp_id
                emp_item.item_name = item_names[i]
                emp_item.item_amt = item_amts[i] if item_amts[i] else None
                emp_item.item_amt_type = (
                    item_amt_types[i] if item_amt_types[i] else None
                )
                emp_item.item_type = item_types[i] if item_types[i] else None
                emp_item.save()

        # Create login account when adding employee directly (not from registration)
        if not reg_id:
            hashed_password = hashlib.md5(password.encode()).hexdigest()
            Users.objects.create(
                full_name=full_name,
                email=email,
                password=hashed_password,
                contact=mobile_no,
                type=2,
            )

            name_parts = full_name.split(" ", 1)
            auth_user = User.objects.create_user(
                username=mobile_no,
                email=email,
                password=password,
                first_name=name_parts[0] if name_parts else "",
                last_name=name_parts[1] if len(name_parts) > 1 else "",
            )
            employee_group, _ = Group.objects.get_or_create(name="employee")
            auth_user.groups.add(employee_group)

        # If coming from registration approval, mark EmpTemp as approved and create Users entry
        reg_id = request.POST.get("reg_id")
        if reg_id:
            try:
                reg_request = EmpTemp.objects.get(id=reg_id)
                if reg_request.status == "PENDING":
                    Users.objects.create(
                        full_name=reg_request.full_name,
                        email=reg_request.email,
                        password=reg_request.password,
                        contact=reg_request.contact,
                        type=2,
                    )
                    reg_request.status = "APPROVED"
                    reg_request.save()
                    # User is now an employee (EmpMaster was just created above)
                    # Remove from customer group, add to employee group
                    try:
                        django_user = User.objects.get(username=reg_request.contact)
                        django_user.groups.remove(Group.objects.get(name="customer"))
                        django_user.groups.add(Group.objects.get(name="employee"))
                    except (Group.DoesNotExist, User.DoesNotExist):
                        pass
            except EmpTemp.DoesNotExist:
                pass

        messages.success(request, "Employee successfully added")
        return redirect("employee_list")

    return render_form()


@login_required(login_url="login")
@permission_required("accounts.change_empmaster", raise_exception=True)
def employee_edit(request, id):
    obj = get_object_or_404(EmpMaster, id=id)

    if request.method == "POST":
        obj.full_name = request.POST.get("full_name", "")
        obj.contact = request.POST.get("mobile_no", "")
        obj.email = request.POST.get("email", "")
        obj.dob = request.POST.get("dob", "") or None
        obj.gender = request.POST.get("gender", "")
        obj.present_addr = request.POST.get("present_address", "")
        obj.perm_addr = request.POST.get("permanent_address", "")
        obj.join_date = request.POST.get("joining_date", "") or None
        obj.end_date = request.POST.get("end_date", "") or None
        obj.emp_type = request.POST.get("employee_type", "")
        obj.check_in = request.POST.get("check_in", "") or None
        obj.check_out = request.POST.get("check_out", "") or None
        obj.dept = request.POST.get("department_name", "")
        obj.desig = request.POST.get("designation_name", "")
        obj.salary_type = request.POST.get("salary_type", "")
        obj.salary_amt = request.POST.get("salary_amount", "")
        obj.full_abs_fine = request.POST.get("full_day_absence_fine", "") or None
        obj.half_abd_fine = request.POST.get("half_day_absence_fine", "") or None
        obj.yearly_leaves = request.POST.get("yearly_leave_limit", "") or None
        obj.bank_name = request.POST.get("bank_name", "")
        obj.branch_name = request.POST.get("branch_name", "")
        obj.account_name = request.POST.get("account_name", "")
        obj.account_no = request.POST.get("account_number", "")
        obj.ifsc_code = request.POST.get("ifsc_code", "")

        obj.save()

        # Handle Additional Details (EmpItemMaster)
        # Delete existing items for this employee
        EmpItemMaster.objects.filter(emp_id=obj.emp_id).delete()

        # Save new items
        item_names = request.POST.getlist("item_name[]")
        item_amts = request.POST.getlist("item_amt[]")
        item_amt_types = request.POST.getlist("item_amt_type[]")
        item_types = request.POST.getlist("item_type[]")

        for i in range(len(item_names)):
            if item_names[i]:  # Only save if name is provided
                emp_item = EmpItemMaster()
                emp_item.emp_id = obj.emp_id
                emp_item.item_name = item_names[i]
                emp_item.item_amt = item_amts[i] if item_amts[i] else None
                emp_item.item_amt_type = (
                    item_amt_types[i] if item_amt_types[i] else None
                )
                emp_item.item_type = item_types[i] if item_types[i] else None
                emp_item.save()

        messages.success(request, "Employee updated successfully")
        return redirect("employee_list")

    # Get existing additional details for this employee
    emp_items = EmpItemMaster.objects.filter(emp_id=obj.emp_id)
    departments = DeptMaster.objects.all()
    designations = DesigMaster.objects.all()
    context = {
        "employee": obj,
        "emp_items": emp_items,
        "departments": departments,
        "designations": designations,
    }
    return render(request, "accounts/employee_edit.html", context)


@login_required(login_url="login")
@permission_required("accounts.delete_empmaster", raise_exception=True)
def employee_delete(request, id):
    obj = get_object_or_404(EmpMaster, id=id)
    obj.delete()
    messages.success(request, "Employee deleted")
    return redirect("employee_list")


def designation_list(request):
    designations = DesigMaster.objects.all()
    context = {"designations": designations}
    return render(request, "accounts/designation_list.html", context)


def designation_edit(request, id):
    obj = get_object_or_404(DesigMaster, id=id)
    if request.method == "POST":
        dept = request.POST.get("department_name", "")
        name = request.POST.get("designation_name", "")
        obj.dept_name = dept
        obj.desig_name = name
        obj.save()
        messages.success(request, "Designation updated")
        return redirect("designation_list")
    context = {"designation": obj}
    return render(request, "accounts/designation_edit.html", context)


def designation_delete(request, id):
    obj = get_object_or_404(DesigMaster, id=id)
    obj.delete()
    messages.success(request, "Designation deleted")
    return redirect("designation_list")


# ==================== ATTENDANCE ====================
@login_required(login_url="login")
def attendance_list(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )
    if is_restricted_user:
        # Only show this employee's own records
        try:
            emp = EmpMaster.objects.get(contact=request.user.username)
            attendance = AttendanceMaster.objects.filter(
                emp_id=int(emp.emp_id)
            ).order_by("-att_date")
        except (EmpMaster.DoesNotExist, ValueError):
            attendance = AttendanceMaster.objects.none()
    else:
        attendance = AttendanceMaster.objects.all().order_by("-att_date")

    # Apply filters from GET params
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if date_from:
        attendance = attendance.filter(att_date__gte=date_from)
    if date_to:
        attendance = attendance.filter(att_date__lte=date_to)
    if status_filter:
        attendance = attendance.filter(attendance_status__iexact=status_filter)

    context = {
        "attendance": attendance,
        "is_restricted_user": is_restricted_user,
        "date_from": date_from,
        "date_to": date_to,
        "status_filter": status_filter,
    }
    return render(request, "accounts/attendance_list.html", context)


@login_required(login_url="login")
def attendance_detail(request, id):
    """View a single attendance record with check-in info and movement map."""
    import json as _json
    from .models import EmployeeLocationTracking

    att = get_object_or_404(AttendanceMaster, id=id)

    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    # Restricted users can only view their own records
    if is_restricted_user:
        try:
            emp = EmpMaster.objects.get(contact=request.user.username)
            if att.emp_id != int(emp.emp_id):
                messages.error(request, "Access denied!")
                return redirect("attendance_list")
        except (EmpMaster.DoesNotExist, ValueError):
            messages.error(request, "Access denied!")
            return redirect("attendance_list")

    locations = EmployeeLocationTracking.objects.filter(
        emp_id=str(att.emp_id), session_date=att.att_date
    ).order_by("timestamp")

    location_points = [
        {
            "lat": float(loc.latitude),
            "lng": float(loc.longitude),
            "timestamp": loc.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "is_checkin": loc.is_checkin_point,
        }
        for loc in locations
    ]

    context = {
        "att": att,
        "location_points_json": _json.dumps(location_points),
        "location_count": len(location_points),
        "is_restricted_user": is_restricted_user,
    }
    return render(request, "accounts/attendance_detail.html", context)


def _get_own_employee(request):
    try:
        return EmpMaster.objects.get(contact=request.user.username)
    except EmpMaster.DoesNotExist:
        return None


def _employee_attendance_state(own_emp):
    from datetime import date

    today = date.today()
    today_attendance = AttendanceMaster.objects.filter(
        emp_id=int(own_emp.emp_id), att_date=today
    ).first()
    checkout_mode = bool(
        today_attendance and today_attendance.check_in and not today_attendance.check_out
    )
    attendance_completed = bool(
        today_attendance and today_attendance.check_in and today_attendance.check_out
    )
    return today, today_attendance, checkout_mode, attendance_completed


def _handle_employee_attendance_post(request, own_emp, action):
    from datetime import date as date_cls, datetime, timedelta
    from decimal import Decimal

    redirect_name = "employee_checkout" if action == "check_out" else "employee_checkin"
    photo_data = request.POST.get("photo_data", "").strip()
    latitude = request.POST.get("latitude", "0") or "0"
    longitude = request.POST.get("longitude", "0") or "0"
    today = date_cls.today()
    now_time = datetime.now().time()
    emp_id_int = int(own_emp.emp_id)

    if not photo_data:
        messages.error(request, "Selfie is required. Please capture your photo.")
        return redirect(redirect_name)
    if latitude in ("0", "0.0", "") or longitude in ("0", "0.0", ""):
        messages.error(request, "Location is required. Please enable GPS.")
        return redirect(redirect_name)

    if action == "check_out":
        att = AttendanceMaster.objects.filter(
            emp_id=emp_id_int, att_date=today, check_out__isnull=True
        ).first()
        if not att:
            messages.error(request, "No active check-in found for today.")
            return redirect("employee_checkin")

        att.check_out = now_time
        att.out_photo = _save_base64_photo(photo_data, "checkout")
        att.out_lati = latitude
        att.out_long = longitude
        ci = datetime.combine(today, att.check_in)
        co = datetime.combine(today, now_time)
        if co < ci:
            co += timedelta(days=1)
        att.worked_hours = round(Decimal(str((co - ci).total_seconds() / 3600)), 2)
        att.worked_day = "Full Day"
        att.save()
        messages.success(request, "Checked out successfully!")
        return redirect("attendance_list")

    existing = AttendanceMaster.objects.filter(emp_id=emp_id_int, att_date=today).first()
    if existing:
        if existing.check_out:
            messages.error(request, "You have already completed attendance for today.")
        else:
            messages.info(request, "You are already checked in. Please check out.")
            return redirect("employee_checkout")
        return redirect("employee_checkin")

    AttendanceMaster.objects.create(
        emp_id=emp_id_int,
        full_name=own_emp.full_name or "",
        att_date=today,
        check_in=now_time,
        attendance_status="Present",
        worked_day="",
        latitude=latitude,
        longitude=longitude,
        photo=_save_base64_photo(photo_data, "checkin"),
        out_lati="0",
        out_long="0",
    )
    messages.success(request, "Checked in successfully!")
    return redirect("attendance_list")


def _employee_attendance_page(request, page_mode):
    own_emp = _get_own_employee(request)
    if own_emp is None:
        messages.error(
            request, "Access denied! No employee record linked to your account."
        )
        return redirect("home")

    if request.method == "POST":
        return _handle_employee_attendance_post(request, own_emp, page_mode)

    today, today_attendance, checkout_mode, attendance_completed = (
        _employee_attendance_state(own_emp)
    )

    if page_mode == "check_in":
        if attendance_completed:
            messages.info(request, "Today's attendance is already completed.")
            return redirect("attendance_list")
        if checkout_mode:
            messages.info(request, "You are already checked in. Use Check Out.")
            return redirect("employee_checkout")
    elif page_mode == "check_out":
        if attendance_completed:
            messages.info(request, "Today's attendance is already completed.")
            return redirect("attendance_list")
        if not checkout_mode:
            messages.warning(request, "Please check in first.")
            return redirect("employee_checkin")

    return render(
        request,
        "accounts/employee_checkin.html",
        {
            "own_emp": own_emp,
            "today": today.strftime("%Y-%m-%d"),
            "today_attendance": today_attendance,
            "checkout_mode": checkout_mode,
            "attendance_completed": attendance_completed,
            "page_mode": page_mode,
        },
    )


@login_required(login_url="login")
def employee_checkin(request):
    return _employee_attendance_page(request, "check_in")


@login_required(login_url="login")
def employee_checkout(request):
    return _employee_attendance_page(request, "check_out")


@login_required(login_url="login")
def attendance_add(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    # Check permissions: Either have add_attendancemaster permission OR be a restricted user
    if not (
        request.user.has_perm("accounts.add_attendancemaster") or is_restricted_user
    ):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You don't have permission to add attendance records.")

    # For restricted users, resolve their own employee record
    own_emp = None
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            own_emp = None

    # Customers (no EmpMaster record) must not access employee attendance
    if is_restricted_user and own_emp is None:
        messages.error(
            request, "Access denied! No employee record linked to your account."
        )
        return redirect("home")

    if is_restricted_user:
        return redirect("employee_checkin")

    if request.method == "POST":
        from datetime import date as date_cls, datetime

        emp_id = request.POST.get("emp_id", "")
        att_date = request.POST.get("att_date", "")
        check_in = request.POST.get("check_in", "")
        check_out = request.POST.get("check_out", "") or None
        attendance_status = request.POST.get("attendance_status", "")
        worked_day = request.POST.get("worked_day", "")
        latitude = request.POST.get("latitude", "0")
        longitude = request.POST.get("longitude", "0")

        # --- Validation: One attendance record per employee per day ---
        if emp_id and att_date:
            duplicate = AttendanceMaster.objects.filter(
                emp_id=int(emp_id), att_date=att_date
            ).exists()
            if duplicate:
                messages.error(
                    request,
                    "Attendance for this employee on the selected date has already been added. "
                    "If you need to add a check-out time, please use the Edit option.",
                )
                return redirect("attendance_add")

        # Get employee name from emp_id
        try:
            emp = EmpMaster.objects.get(emp_id=emp_id)
            full_name = emp.full_name
        except:
            full_name = ""

        att = AttendanceMaster()
        att.emp_id = int(emp_id) if emp_id else 0
        att.full_name = full_name
        att.att_date = att_date
        att.check_in = check_in
        att.check_out = check_out
        att.attendance_status = attendance_status
        att.worked_day = worked_day
        att.latitude = latitude
        att.longitude = longitude
        att.out_lati = "0"
        att.out_long = "0"
        att.save()

        messages.success(request, "Attendance added successfully")
        return redirect("attendance_list")

    from datetime import date

    employees = EmpMaster.objects.all()
    context = {
        "employees": employees,
        "today": date.today().strftime("%Y-%m-%d"),
        "is_restricted_user": is_restricted_user,
        "own_emp": own_emp,
    }
    return render(request, "accounts/attendance_add.html", context)


@login_required(login_url="login")
def attendance_edit(request, id):
    """
    Allow adding a missed check-out time to an existing attendance record.
    Only allowed when check_out is currently blank/null.
    """
    from datetime import datetime, date as date_cls

    attendance = get_object_or_404(AttendanceMaster, id=id)

    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    # Restricted users can only edit their own record
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
            if attendance.emp_id != int(own_emp.emp_id):
                messages.error(
                    request, "You can only edit your own attendance records."
                )
                return redirect("attendance_list")
        except EmpMaster.DoesNotExist:
            messages.error(request, "No employee record linked to your account.")
            return redirect("home")

    # Only allow editing if check_out is missing
    if attendance.check_out:
        messages.warning(
            request, "Check-out time has already been recorded for this attendance."
        )
        return redirect("attendance_list")

    # Restricted users can only check out for today's record
    if is_restricted_user and attendance.att_date != date_cls.today():
        messages.error(
            request, "Check-out can only be recorded for today's attendance."
        )
        return redirect("attendance_list")

    if request.method == "POST":
        check_out = request.POST.get("check_out", "").strip()
        if not check_out:
            messages.error(request, "Please enter a valid check-out time.")
        else:
            # Parse and validate check_out > check_in
            try:
                check_out_time = datetime.strptime(check_out, "%H:%M").time()
                if check_out_time <= attendance.check_in:
                    messages.error(
                        request, "Check-out time must be after check-in time."
                    )
                else:
                    attendance.check_out = check_out_time
                    # Calculate worked hours
                    from decimal import Decimal

                    ci = datetime.combine(date_cls.today(), attendance.check_in)
                    co = datetime.combine(date_cls.today(), check_out_time)
                    diff = (co - ci).total_seconds() / 3600
                    attendance.worked_hours = round(Decimal(str(diff)), 2)
                    attendance.save()
                    messages.success(request, "Check-out time updated successfully.")
                    return redirect("attendance_list")
            except ValueError:
                messages.error(request, "Invalid check-out time format.")

    context = {
        "attendance": attendance,
    }
    return render(request, "accounts/attendance_edit.html", context)


def attendance_req_list(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )
    if is_restricted_user:
        try:
            emp = EmpMaster.objects.get(contact=request.user.username)
            requests = AttendanceReq.objects.filter(emp_id=emp.emp_id).order_by(
                "-created_at"
            )
        except EmpMaster.DoesNotExist:
            requests = AttendanceReq.objects.none()
    else:
        requests = AttendanceReq.objects.all().order_by("-created_at")
    context = {"requests": requests, "is_restricted_user": is_restricted_user}
    return render(request, "accounts/attendance_req_list.html", context)


def attendance_req_status_update(request, id):
    if request.method == "POST":
        try:
            req = AttendanceReq.objects.get(id=id)
            status = request.POST.get("status", "Pending")
            req.approval_status = status
            req.save()
            messages.success(request, "Attendance request status updated successfully")
        except AttendanceReq.DoesNotExist:
            messages.error(request, "Attendance request not found")
    return redirect("attendance_req_list")


def attendance_req_add(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    own_emp = None
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            own_emp = None

    if request.method == "POST":
        if is_restricted_user:
            emp_id = str(own_emp.emp_id) if own_emp else ""
        else:
            emp_id = request.POST.get("emp_id", "")
        reg_date = request.POST.get("reg_date", "")
        check_in = request.POST.get("check_in", "")
        check_out = request.POST.get("check_out", "")
        reason = request.POST.get("reason", "")
        attachment = request.POST.get("attachment", "")
        status = request.POST.get("status", "Pending")

        # Get employee name from emp_id
        try:
            emp = EmpMaster.objects.get(emp_id=emp_id)
            full_name = emp.full_name
        except:
            full_name = ""

        req = AttendanceReq()
        req.emp_id = emp_id
        req.full_name = full_name
        req.reg_date = reg_date
        req.check_in = check_in
        req.check_out = check_out
        req.reason = reason
        req.attachment = attachment or ""
        req.approval_status = "Pending"
        req.status = status
        req.save()

        messages.success(request, "Attendance request submitted successfully")
        return redirect("attendance_req_list")

    from datetime import date

    if is_restricted_user:
        employees = [own_emp] if own_emp else []
    else:
        employees = EmpMaster.objects.all()
    context = {
        "employees": employees,
        "today": date.today().strftime("%Y-%m-%d"),
        "is_restricted_user": is_restricted_user,
        "own_emp": own_emp,
    }
    return render(request, "accounts/attendance_req_add.html", context)


# ==================== LEAVES ====================
@login_required(login_url="login")
def leave_list(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
            leaves = LeaveRequest.objects.filter(emp_id=int(own_emp.emp_id)).order_by(
                "-applied_at"
            )
        except EmpMaster.DoesNotExist:
            leaves = LeaveRequest.objects.none()
    else:
        if not request.user.has_perm("accounts.view_leaverequest"):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        leaves = LeaveRequest.objects.all().order_by("-applied_at")

    context = {
        "leaves": leaves,
        "is_restricted_user": is_restricted_user,
    }
    return render(request, "accounts/leave_list.html", context)


@login_required(login_url="login")
def leave_add(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    own_emp = None
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            messages.error(request, "No employee record linked to your account.")
            return redirect("home")
    elif not request.user.has_perm("accounts.add_leaverequest"):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied

    if request.method == "POST":
        if is_restricted_user:
            emp_id = str(own_emp.emp_id)
        else:
            emp_id = request.POST.get("emp_id", "")
        leave_type = request.POST.get("leave_type", "")
        start_date = request.POST.get("start_date", "")
        end_date = request.POST.get("end_date", "")
        leave_duration = request.POST.get("leave_duration", "")
        reason = request.POST.get("reason", "")
        is_paid = request.POST.get("is_paid", "1")

        # Get employee name from emp_id
        try:
            emp = EmpMaster.objects.get(emp_id=emp_id)
            full_name = emp.full_name
            yearly_leaves = emp.yearly_leaves or 0
        except:
            full_name = ""
            yearly_leaves = 0

        leave = LeaveRequest()
        leave.emp_id = int(emp_id) if emp_id else 0
        leave.full_name = full_name
        leave.leave_type = leave_type
        leave.start_date = start_date
        leave.end_date = end_date
        leave.leave_duration = leave_duration
        leave.reason = reason
        leave.is_paid = int(is_paid)
        leave.leave_status = 0  # Pending
        leave.yearly_leaves = yearly_leaves
        leave.total_leaves = 0
        leave.save()

        messages.success(request, "Leave request submitted successfully")
        return redirect("leave_list")

    employees = [own_emp] if is_restricted_user else EmpMaster.objects.all()
    context = {
        "employees": employees,
        "is_restricted_user": is_restricted_user,
        "own_emp": own_emp,
    }
    return render(request, "accounts/leave_add.html", context)


def leave_approval_list(request):
    # Show all leave requests for approval management
    leaves = LeaveRequest.objects.all().order_by("-applied_at")
    context = {"leaves": leaves}
    return render(request, "accounts/leave_approval_list.html", context)


def leave_status_update(request, id):
    if request.method == "POST":
        try:
            leave = LeaveRequest.objects.get(id=id)
            status = request.POST.get("status", "0")
            leave.leave_status = int(status)
            leave.save()
            messages.success(request, "Leave status updated successfully")
        except LeaveRequest.DoesNotExist:
            messages.error(request, "Leave request not found")
    return redirect("leave_approval_list")


def leave_approve(request, id):
    try:
        leave = LeaveRequest.objects.get(id=id)
        leave.leave_status = 1  # Approved
        leave.save()
        messages.success(request, "Leave request approved successfully")
    except LeaveRequest.DoesNotExist:
        messages.error(request, "Leave request not found")
    return redirect("leave_approval_list")


def leave_reject(request, id):
    try:
        leave = LeaveRequest.objects.get(id=id)
        leave.leave_status = 2  # Rejected
        leave.save()
        messages.success(request, "Leave request rejected")
    except LeaveRequest.DoesNotExist:
        messages.error(request, "Leave request not found")
    return redirect("leave_approval_list")


# ==================== HOLIDAY ====================
@login_required(login_url="login")
def holiday_list(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )
    holidays = HolidayMaster.objects.all().order_by("holiday_date")
    context = {"holidays": holidays, "is_restricted_user": is_restricted_user}
    return render(request, "accounts/holiday_list.html", context)


@login_required(login_url="login")
@permission_required("accounts.add_holidaymaster", raise_exception=True)
def holiday_add(request):
    if request.method == "POST":
        title = request.POST.get("holiday_title", "")
        date = request.POST.get("holiday_date", "")
        if title and date:
            holiday = HolidayMaster()
            holiday.holiday_tital = title
            holiday.holiday_date = date
            holiday.save()
            messages.success(request, "Holiday added successfully")
            return redirect("holiday_list")
    return render(request, "accounts/holiday_add.html")


def holiday_delete(request, id):
    obj = get_object_or_404(HolidayMaster, id=id)
    obj.delete()
    messages.success(request, "Holiday deleted")
    return redirect("holiday_list")


# ==================== PAYSLIP ====================
@login_required(login_url="login")
def payslip_generate(request):
    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    own_emp = None
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            messages.error(request, "No employee record linked to your account.")
            return redirect("home")

    employees = EmpMaster.objects.all()
    payslip_data = None

    if request.method == "POST":
        if is_restricted_user:
            employee_id = str(own_emp.emp_id)
        else:
            employee_id = request.POST.get("employee_id", "")
        month = request.POST.get("month", "")
        year = request.POST.get("year", "")

        if employee_id and month and year:
            try:
                employee = EmpMaster.objects.get(emp_id=employee_id)

                # Get month name
                month_names = [
                    "",
                    "January",
                    "February",
                    "March",
                    "April",
                    "May",
                    "June",
                    "July",
                    "August",
                    "September",
                    "October",
                    "November",
                    "December",
                ]
                month_name = month_names[int(month)]

                # Calculate basic salary (full month)
                basic_salary = float(employee.salary_amt) if employee.salary_amt else 0

                # Calculate attendance for the month
                import calendar as cal_module
                from datetime import date

                # Safe int conversion for emp_id (handles both numeric "1" and "EMP001" style)
                try:
                    emp_id_int = int(employee_id)
                except (ValueError, TypeError):
                    emp_id_int = None

                if emp_id_int is not None:
                    attendance_count = AttendanceMaster.objects.filter(
                        emp_id=emp_id_int,
                        att_date__month=int(month),
                        att_date__year=int(year),
                    ).count()
                else:
                    # Fall back to full_name match for non-numeric emp_ids
                    attendance_count = AttendanceMaster.objects.filter(
                        full_name=employee.full_name,
                        att_date__month=int(month),
                        att_date__year=int(year),
                    ).count()

                # Total calendar days in the month (for proration)
                total_days_in_month = cal_module.monthrange(int(year), int(month))[1]
                proration_factor = (
                    attendance_count / total_days_in_month
                    if total_days_in_month > 0 and attendance_count > 0
                    else 0
                )

                # Prorate basic salary based on days actually worked
                prorated_basic = round(basic_salary * proration_factor, 2)

                # Get additional details from EmpItemMaster
                emp_items = EmpItemMaster.objects.filter(emp_id=employee_id)

                # Separate earnings and deductions (all prorated)
                earnings_list = []
                deductions_list = []
                total_earnings = 0
                total_deductions = 0

                for item in emp_items:
                    # Percentage items are calculated on prorated basic; fixed items are also prorated
                    if item.item_amt_type == "Percentage":
                        calculated_amt = prorated_basic * (
                            float(item.item_amt or 0) / 100
                        )
                    else:  # Fixed — prorate by attendance ratio
                        calculated_amt = float(item.item_amt or 0) * proration_factor

                    item_data = {
                        "name": item.item_name,
                        "amount": round(calculated_amt, 2),
                    }

                    if item.item_type == "Earning":
                        earnings_list.append(item_data)
                        total_earnings += calculated_amt
                    elif item.item_type == "Deduction":
                        deductions_list.append(item_data)
                        total_deductions += calculated_amt

                # Calculate gross and net salary on prorated amounts
                gross_salary = prorated_basic + total_earnings
                net_salary = gross_salary - total_deductions

                # Leave days in selected month (approved)
                leave_days = 0
                if emp_id_int is not None:
                    leave_days = LeaveRequest.objects.filter(
                        emp_id=emp_id_int,
                        leave_status=1,
                        start_date__month=int(month),
                        start_date__year=int(year),
                    ).count()

                lop_days = max(0, total_days_in_month - attendance_count - leave_days)
                paid_days = max(0, total_days_in_month - lop_days)

                earnings_display = [
                    {
                        "name": "Basic Salary",
                        "amount": round(prorated_basic, 2),
                        "amount_fmt": _format_inr(prorated_basic),
                    }
                ]
                for item in earnings_list:
                    earnings_display.append(
                        {
                            "name": item["name"],
                            "amount": item["amount"],
                            "amount_fmt": _format_inr(item["amount"]),
                        }
                    )

                deductions_display = [
                    {
                        "name": item["name"],
                        "amount": item["amount"],
                        "amount_fmt": _format_inr(item["amount"]),
                    }
                    for item in deductions_list
                ]

                max_rows = max(len(earnings_display), len(deductions_display), 1)
                salary_rows = []
                for i in range(max_rows):
                    salary_rows.append(
                        {
                            "earning": earnings_display[i]
                            if i < len(earnings_display)
                            else None,
                            "deduction": deductions_display[i]
                            if i < len(deductions_display)
                            else None,
                        }
                    )

                payslip_data = {
                    "employee": employee,
                    "month": month_name,
                    "year": year,
                    "month_num": month,
                    "attendance_days": attendance_count,
                    "total_days": total_days_in_month,
                    "paid_days": paid_days,
                    "leave_days": leave_days,
                    "lop_days": lop_days,
                    "basic_salary_full": round(basic_salary, 2),
                    "basic_salary": round(prorated_basic, 2),
                    "earnings_list": earnings_list,
                    "deductions_list": deductions_list,
                    "earnings_display": earnings_display,
                    "deductions_display": deductions_display,
                    "salary_rows": salary_rows,
                    "total_earnings": round(total_earnings, 2),
                    "gross_salary": round(gross_salary, 2),
                    "gross_salary_fmt": _format_inr(gross_salary),
                    "total_deductions": round(total_deductions, 2),
                    "total_deductions_fmt": _format_inr(total_deductions),
                    "net_salary": round(net_salary, 2),
                    "net_salary_fmt": _format_inr(net_salary),
                    "amount_in_words": _amount_in_words(net_salary),
                }
            except EmpMaster.DoesNotExist:
                messages.error(request, "Employee not found")

    context = {
        "employees": employees if not is_restricted_user else [own_emp],
        "payslip": payslip_data,
        "is_restricted_user": is_restricted_user,
        "own_emp": own_emp,
        "selected_month": request.POST.get("month", "") if request.method == "POST" else "",
        "selected_year": request.POST.get("year", "") if request.method == "POST" else "",
    }
    return render(request, "accounts/payslip_generate.html", context)


# ==================== COMPANY SETTINGS ====================
@login_required(login_url="login")
def company_settings(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "You do not have permission to access settings.")
        return redirect("home")

    company = SystemSettings.objects.first()

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        contact = request.POST.get("contact", "").strip()
        address = request.POST.get("address", "").strip()

        if not name:
            messages.error(request, "Company name is required.")
        else:
            if not company:
                company = SystemSettings(
                    name=name,
                    email=email,
                    contact=contact,
                    address=address,
                    cover_img="",
                )
            else:
                company.name = name
                company.email = email
                company.contact = contact
                company.address = address

            logo_file = request.FILES.get("logo")
            if logo_file:
                logo_path = save_company_logo(logo_file)
                company.cover_img = logo_path

            company.save()
            messages.success(request, "Company settings saved successfully.")
            return redirect("company_settings")

    return render(request, "accounts/company_settings.html", {"company": company})


# ==================== REPORTS ====================
@login_required(login_url="login")
def attendance_report(request):
    from datetime import date, timedelta
    import calendar

    is_restricted_user = not (
        request.user.is_superuser
        or request.user.has_perm("accounts.add_empmaster")
        or request.user.has_perm("accounts.change_empmaster")
    )

    own_emp = None
    if is_restricted_user:
        try:
            own_emp = EmpMaster.objects.get(contact=request.user.username)
        except EmpMaster.DoesNotExist:
            messages.error(request, "No employee record linked to your account.")
            return redirect("home")

    employees = EmpMaster.objects.all() if not is_restricted_user else [own_emp]

    # Get filter parameters
    month = request.GET.get("month", str(date.today().month))
    year = request.GET.get("year", str(date.today().year))

    # Restricted users always see only their own report — ignore any employee_id param
    if is_restricted_user:
        employee_id = str(own_emp.emp_id)
    else:
        employee_id = request.GET.get("employee_id", "")

    month = int(month)
    year = int(year)

    # Get month name and number of days
    month_names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    month_name = month_names[month]
    num_days = calendar.monthrange(year, month)[1]
    days_list = list(range(1, num_days + 1))

    # Get employees to show
    if is_restricted_user:
        emp_list = [own_emp]
    elif employee_id:
        emp_list = EmpMaster.objects.filter(emp_id=employee_id)
    else:
        emp_list = EmpMaster.objects.all()

    # Build attendance data for each employee
    report_data = []
    for emp in emp_list:
        # Get all attendance records for this employee in this month
        att_records = AttendanceMaster.objects.filter(
            emp_id=int(emp.emp_id), att_date__month=month, att_date__year=year
        )

        # Create a dict of date -> status
        att_dict = {}
        for att in att_records:
            day = att.att_date.day
            status = att.attendance_status
            if status == "Present":
                att_dict[day] = "P"
            elif status == "Absent":
                att_dict[day] = "A"
            elif status == "Half Day":
                att_dict[day] = "H"
            elif status == "Late":
                att_dict[day] = "L"
            elif status == "On Leave":
                att_dict[day] = "L"
            else:
                att_dict[day] = "P"

        # Build days status list
        days_status = []
        for day in days_list:
            day_date = date(year, month, day)
            weekday = day_date.weekday()  # 0=Monday, 6=Sunday

            if weekday == 5 or weekday == 6:  # Saturday or Sunday
                days_status.append(
                    {"day": day, "status": "W", "class": "bg-primary text-white"}
                )
            elif day in att_dict:
                status = att_dict[day]
                if status == "P":
                    days_status.append(
                        {
                            "day": day,
                            "status": "P",
                            "class": "text-success font-weight-bold",
                        }
                    )
                elif status == "A":
                    days_status.append(
                        {
                            "day": day,
                            "status": "A",
                            "class": "text-danger font-weight-bold",
                        }
                    )
                elif status == "H":
                    days_status.append(
                        {
                            "day": day,
                            "status": "H",
                            "class": "text-warning font-weight-bold",
                        }
                    )
                elif status == "L":
                    days_status.append(
                        {
                            "day": day,
                            "status": "L",
                            "class": "text-info font-weight-bold",
                        }
                    )
                else:
                    days_status.append({"day": day, "status": status, "class": ""})
            else:
                # No record - show as Absent for past days, empty for future
                if day_date <= date.today():
                    days_status.append(
                        {
                            "day": day,
                            "status": "A",
                            "class": "text-danger font-weight-bold",
                        }
                    )
                else:
                    days_status.append(
                        {"day": day, "status": "-", "class": "text-muted"}
                    )

        report_data.append(
            {
                "emp_id": emp.emp_id,
                "full_name": emp.full_name,
                "days_status": days_status,
            }
        )

    context = {
        "employees": employees,
        "report_data": report_data,
        "days_list": days_list,
        "month": month,
        "month_name": month_name,
        "year": year,
        "selected_employee": employee_id,
        "is_restricted_user": is_restricted_user,
        "own_emp": own_emp,
    }
    return render(request, "accounts/attendance_report.html", context)


# User Authentication Views
def login(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        # Try to resolve User by email OR username (phone)
        db_user = None
        try:
            db_user = User.objects.get(email=email)
        except User.DoesNotExist:
            try:
                db_user = User.objects.get(username=email)
            except User.DoesNotExist:
                pass

        if db_user is not None:
            user = authenticate(request, username=db_user.username, password=password)
            if user is not None:
                auth_login(request, user)
                return redirect("home")
            else:
                messages.error(request, "Invalid email or password")
        else:
            messages.error(request, "Invalid email or password")

    return render(request, "accounts/login.html")


def register(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")
        dob = request.POST.get("dob")
        gender = request.POST.get("gender")
        address = request.POST.get("address")
        father_name = request.POST.get("father_name")
        emergency_contact = request.POST.get("emergency_contact")

        # Validate phone number - must be exactly 10 digits
        if not phone or len(phone) != 10 or not phone.isdigit():
            messages.error(request, "Phone number must be exactly 10 digits")
            return render(request, "accounts/register.html")

        # Check if phone or email already exists in EmpTemp or Users
        if EmpTemp.objects.filter(contact=phone).exists():
            # Check if Django User also exists, if not create it
            if not User.objects.filter(username=phone).exists():
                try:
                    # Get the existing EmpTemp to create missing User
                    existing_emp = EmpTemp.objects.get(contact=phone)
                    name_parts = existing_emp.full_name.split(" ", 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ""

                    User.objects.create_user(
                        username=phone,
                        email=existing_emp.email,
                        password=password,  # Use the current password
                        first_name=first_name,
                        last_name=last_name,
                    )
                    messages.success(request, "Account created! You can now login.")
                    return redirect("login")
                except Exception as e:
                    messages.error(request, f"Error creating account: {str(e)}")
                    return render(request, "accounts/register.html")
            else:
                messages.error(request, "Phone number already registered")
                return render(request, "accounts/register.html")

        if EmpTemp.objects.filter(email=email).exists():
            # Check if Django User also exists, if not create it
            if not User.objects.filter(email=email).exists():
                try:
                    # Get the existing EmpTemp to create missing User
                    existing_emp = EmpTemp.objects.get(email=email)
                    name_parts = existing_emp.full_name.split(" ", 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ""

                    User.objects.create_user(
                        username=existing_emp.contact,
                        email=email,
                        password=password,  # Use the current password
                        first_name=first_name,
                        last_name=last_name,
                    )
                    messages.success(request, "Account created! You can now login.")
                    return redirect("login")
                except Exception as e:
                    messages.error(request, f"Error creating account: {str(e)}")
                    return render(request, "accounts/register.html")
            else:
                messages.error(request, "Email already registered")
                return render(request, "accounts/register.html")

        if User.objects.filter(username=phone).exists():
            messages.error(request, "Phone number already registered")
            return render(request, "accounts/register.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
            return render(request, "accounts/register.html")

        # Create both Django User and EmpTemp entry for approval workflow
        try:
            from django.db import transaction
            import hashlib

            # Use atomic transaction to ensure both User and EmpTemp are created together
            with transaction.atomic():
                hashed_password = hashlib.md5(password.encode()).hexdigest()

                # Parse date string to date object
                from datetime import datetime

                dob_date = None
                if dob:
                    try:
                        dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
                    except:
                        dob_date = None

                # Create Django User account first
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""

                user = User.objects.create_user(
                    username=phone,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
                # Mark as INACTIVE until admin approves
                user.is_active = False
                user.save()

                # Assign to 'customer' group while pending approval
                try:
                    user.groups.add(Group.objects.get(name="customer"))
                except Group.DoesNotExist:
                    pass

                # Create EmpTemp entry for admin approval tracking
                EmpTemp.objects.create(
                    full_name=full_name,
                    contact=phone,
                    email=email,
                    password=hashed_password,
                    dob=dob_date,
                    gender=gender or "",
                    address=address or "",
                    father_name=father_name or "",
                    emergency_contact=emergency_contact or "",
                    status="PENDING",
                )

            messages.success(
                request,
                "Registration successful! Your account is pending admin approval. You will be able to login once approved.",
            )
            return redirect("login")
        except Exception as e:
            messages.error(request, f"Registration failed: {str(e)}")
            return render(request, "accounts/register.html")

    return render(request, "accounts/register.html")


def logout_view(request):
    auth_logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect("login")


# User Management Views
@login_required(login_url="login")
@permission_required("auth.view_user", raise_exception=True)
def user_list(request):
    users = Users.objects.all().order_by("-id")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required(login_url="login")
@permission_required("auth.add_user", raise_exception=True)
def user_add(request):
    departments = DeptMaster.objects.all()

    if request.method == "POST":
        import hashlib

        full_name = request.POST.get("full_name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")
        user_type = int(request.POST.get("type", 2))
        if user_type not in (1, 2, 3):
            messages.error(request, "Invalid user type selected")
            return render(
                request, "accounts/user_add.html", {"departments": departments}
            )

        # Validate phone number
        if not phone or len(phone) != 10 or not phone.isdigit():
            messages.error(request, "Phone number must be exactly 10 digits")
            return render(
                request, "accounts/user_add.html", {"departments": departments}
            )

        # Check if user already exists
        if Users.objects.filter(contact=phone).exists():
            messages.error(request, "User with this phone number already exists")
            return render(
                request, "accounts/user_add.html", {"departments": departments}
            )

        if Users.objects.filter(email=email).exists():
            messages.error(request, "User with this email already exists")
            return render(
                request, "accounts/user_add.html", {"departments": departments}
            )

        # Hash password (MD5 to match legacy system)
        hashed_password = hashlib.md5(password.encode()).hexdigest()

        # Create user in the users table (legacy)
        user = Users.objects.create(
            full_name=full_name,
            email=email,
            password=hashed_password,
            contact=phone,
            type=user_type,
        )

        # Also create a Django auth user so the new user can log in
        from django.contrib.auth.models import User as AuthUser

        # prefer phone as username; ensure uniqueness
        username = phone or (email.split("@")[0] if email else f"legacy_{user.id}")
        base_username = username
        counter = 1
        while AuthUser.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        # create auth user if not exists by email
        if not AuthUser.objects.filter(email=email).exists():
            name_parts = (full_name or "").split(" ", 1)
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            auth_user = AuthUser.objects.create_user(
                username=username,
                email=email or "",
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

        messages.success(request, "User added successfully!")
        return redirect("user_list")

    return render(request, "accounts/user_add.html", {"departments": departments})


@login_required(login_url="login")
@permission_required("auth.change_user", raise_exception=True)
def user_edit(request, id):
    user = get_object_or_404(Users, id=id)
    if request.method == "POST":
        user.full_name = request.POST.get("full_name", "")
        user.email = request.POST.get("email", "")
        user.contact = request.POST.get("contact", "")
        user_type = int(request.POST.get("type", 2))
        if user_type not in (1, 2, 3):
            messages.error(request, "Invalid user type selected")
            return render(request, "accounts/user_edit.html", {"user": user})
        user.type = user_type
        user.save()
        messages.success(request, "User updated successfully!")
        return redirect("user_list")
    return render(request, "accounts/user_edit.html", {"user": user})


@login_required(login_url="login")
@permission_required("auth.delete_user", raise_exception=True)
def user_delete(request, id):
    user = get_object_or_404(Users, id=id)
    # Also delete the corresponding Django auth_user (matched by phone/email)
    try:
        auth_user = (
            User.objects.filter(username=user.contact).first()
            or User.objects.filter(email=user.email).first()
        )
        if auth_user:
            auth_user.delete()
    except Exception:
        pass
    user.delete()
    messages.success(request, "User deleted successfully!")
    return redirect("user_list")


# Password Reset Views
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")

        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)

            # Generate token and uid
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Create reset link
            reset_link = request.build_absolute_uri(
                reverse("reset_password", kwargs={"uidb64": uid, "token": token})
            )

            # Send email (will display in console for development)
            subject = "Reset Your HRMS Password"
            message = f"""
Hello {user.first_name or user.username},

You have requested to reset your password for your HRMS account. 
Click the link below to reset your password:

{reset_link}

This link will expire in 24 hours for security reasons.
If you didn't request this, please ignore this email.

Best regards,
HRMS Team
            """

            email_message = EmailMessage(subject, message, to=[email])

            try:
                email_message.send()
                return redirect("reset_password_sent")
            except Exception as e:
                messages.error(request, "Error sending email. Please try again later.")
        else:
            messages.error(request, "No account found with this email address.")

    return render(request, "accounts/forgot_password.html")


def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if request.method == "POST":
            password1 = request.POST.get("password1")
            password2 = request.POST.get("password2")

            if password1 and password2:
                if password1 == password2:
                    if len(password1) >= 8:
                        user.set_password(password1)
                        user.save()
                        messages.success(request, "Password reset successful!")
                        return redirect("reset_password_complete")
                    else:
                        messages.error(
                            request, "Password must be at least 8 characters long."
                        )
                else:
                    messages.error(request, "Passwords do not match.")
            else:
                messages.error(request, "Please fill in both password fields.")

        return render(request, "accounts/reset_password.html", {"valid_link": True})
    else:
        messages.error(request, "Invalid or expired reset link.")
        return render(request, "accounts/reset_password.html", {"valid_link": False})


def reset_password_sent(request):
    return render(request, "accounts/reset_password_sent.html")


def reset_password_complete(request):
    return render(request, "accounts/reset_password_complete.html")


@login_required(login_url="login")
def manage_account(request):
    user = request.user

    if request.method == "POST":
        # Get form data
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")
        email = request.POST.get("email", "")
        username = request.POST.get("username", "")
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        # Check if email already exists for another user
        if email != user.email and User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists for another user.")
            return render(request, "accounts/manage_account.html", {"user": user})

        # Check if username already exists for another user
        if (
            username != user.username
            and User.objects.filter(username=username).exists()
        ):
            messages.error(
                request, "Username/Contact number already exists for another user."
            )
            return render(request, "accounts/manage_account.html", {"user": user})

        # Update basic information
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.username = username

        # Handle password change
        if new_password:
            # Verify current password
            if not user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
                return render(request, "accounts/manage_account.html", {"user": user})

            # Check new password confirmation
            if new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                return render(request, "accounts/manage_account.html", {"user": user})

            # Check password length
            if len(new_password) < 8:
                messages.error(
                    request, "New password must be at least 8 characters long."
                )
                return render(request, "accounts/manage_account.html", {"user": user})

            # Set new password
            user.set_password(new_password)
            messages.success(
                request, "Password updated successfully! Please login again."
            )

        # Save user changes
        try:
            user.save()
            if new_password:
                # If password was changed, logout and redirect to login
                auth_logout(request)
                messages.info(
                    request,
                    "Password changed successfully. Please login with your new password.",
                )
                return redirect("login")
            else:
                messages.success(request, "Account information updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating account: {str(e)}")

    context = {"user": user}
    return render(request, "accounts/manage_account.html", context)


# Registration Request Management Views
@login_required(login_url="login")
def reg_user_list(request):
    """List all registration requests for admin approval"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Access denied!")
        return redirect("home")

    reg_requests = EmpTemp.objects.all().order_by("-created_at")
    return render(
        request, "accounts/reg_user_list.html", {"reg_requests": reg_requests}
    )


@login_required(login_url="login")
def reg_user_approve(request, id):
    """Approve a registration request and create user account"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Access denied!")
        return redirect("home")

    try:
        reg_request = get_object_or_404(EmpTemp, id=id)

        if reg_request.status != "PENDING":
            messages.error(request, "Registration request already processed!")
            return redirect("reg_user_list")

        # Check if Django User already exists (created during registration)
        try:
            django_user = User.objects.get(username=reg_request.contact)
        except User.DoesNotExist:
            # If somehow User doesn't exist, create it
            name_parts = reg_request.full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            django_user = User.objects.create_user(
                username=reg_request.contact,
                email=reg_request.email,
                password="temp123",
                first_name=first_name,
                last_name=last_name,
                is_active=False,
            )

        # ACTIVATE the user account so they can now log in
        django_user.is_active = True
        django_user.save()

        # Create Users entry for legacy compatibility (this enables full sidebar access)
        if not Users.objects.filter(contact=reg_request.contact).exists():
            Users.objects.create(
                full_name=reg_request.full_name,
                email=reg_request.email,
                password=reg_request.password,  # Keep the MD5 hash
                contact=reg_request.contact,
                type=2,
            )

        # Update status to approved
        reg_request.status = "APPROVED"
        reg_request.save()

        # Add to 'customer' group so they have basic access
        try:
            django_user.groups.add(Group.objects.get(name="customer"))
        except Group.DoesNotExist:
            pass

        messages.success(
            request,
            f"Registration approved for {reg_request.full_name}. They can now log in.",
        )
    except Exception as e:
        messages.error(request, f"Error approving registration: {str(e)}")

    return redirect("reg_user_list")


@login_required(login_url="login")
def reg_user_reject(request, id):
    """Reject a registration request"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Access denied!")
        return redirect("home")

    try:
        reg_request = get_object_or_404(EmpTemp, id=id)

        if reg_request.status != "PENDING":
            messages.error(request, "Registration request already processed!")
            return redirect("reg_user_list")

        reg_request.status = "REJECTED"
        reg_request.save()

        messages.success(request, f"Registration rejected for {reg_request.full_name}")
    except Exception as e:
        messages.error(request, f"Error rejecting registration: {str(e)}")

    return redirect("reg_user_list")


# ==================== LOCATION TRACKING ====================
import json
import math


@login_required(login_url="login")
def save_location_update(request):
    """
    API endpoint to receive a single location update from the frontend.
    Accepts POST with JSON body: {latitude, longitude, is_checkin_point}
    Returns JSON {status: 'ok'}.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        latitude = float(data.get("latitude", 0))
        longitude = float(data.get("longitude", 0))
        is_checkin_point = bool(data.get("is_checkin_point", False))
    except (ValueError, KeyError, json.JSONDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid data"}, status=400)

    # Resolve employee id from current user
    emp_id = ""
    full_name = ""
    try:
        emp = EmpMaster.objects.get(contact=request.user.username)
        emp_id = emp.emp_id
        full_name = emp.full_name or ""
    except EmpMaster.DoesNotExist:
        pass

    from .models import EmployeeLocationTracking
    from datetime import date

    EmployeeLocationTracking.objects.create(
        user_id=request.user.id,
        emp_id=emp_id,
        full_name=full_name,
        latitude=latitude,
        longitude=longitude,
        session_date=date.today(),
        is_checkin_point=is_checkin_point,
    )

    return JsonResponse({"status": "ok"})


@login_required(login_url="login")
def employee_location_map(request, emp_id, session_date):
    """
    Admin/staff-only page to view an employee's movement map for a given session date.
    emp_id      – employee's emp_id string
    session_date – YYYY-MM-DD string
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access denied!")
        return redirect("home")

    from .models import EmployeeLocationTracking

    locations = EmployeeLocationTracking.objects.filter(
        emp_id=emp_id, session_date=session_date
    ).order_by("timestamp")

    # Build a JSON-safe list for the template
    location_points = [
        {
            "lat": float(loc.latitude),
            "lng": float(loc.longitude),
            "timestamp": loc.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "is_checkin": loc.is_checkin_point,
        }
        for loc in locations
    ]

    # Try to resolve employee name
    try:
        emp = EmpMaster.objects.get(emp_id=emp_id)
        emp_name = emp.full_name or emp_id
    except EmpMaster.DoesNotExist:
        emp_name = emp_id

    context = {
        "emp_id": emp_id,
        "emp_name": emp_name,
        "session_date": session_date,
        "location_points_json": json.dumps(location_points),
        "location_count": len(location_points),
    }
    return render(request, "accounts/employee_location_map.html", context)


# ==================== VISITOR / CLIENT MANAGEMENT ====================


@login_required(login_url="login")
def visitor_add(request):
    """
    Any logged-in employee can add a client-visit record.
    The logged-in user is auto-attached; employees cannot change who added the record.
    """
    import base64
    import uuid
    from django.core.files.base import ContentFile
    from .models import ClientVisitor
    from datetime import date

    # Resolve linked employee (if any)
    own_emp = None
    try:
        own_emp = EmpMaster.objects.get(contact=request.user.username)
    except EmpMaster.DoesNotExist:
        pass

    if request.method == "POST":
        client_name = request.POST.get("client_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        location = request.POST.get("location", "").strip()
        notes = request.POST.get("notes", "").strip()
        visit_date = request.POST.get("visit_date", "") or str(date.today())
        photo_data = request.POST.get("photo_data", "").strip()

        if not client_name:
            messages.error(request, "Client Name is required.")
            return redirect("visitor_add")

        visitor = ClientVisitor(
            user=request.user,
            emp_id=own_emp.emp_id if own_emp else "",
            emp_name=(
                own_emp.full_name
                if own_emp
                else request.user.get_full_name() or request.user.username
            ),
            client_name=client_name,
            phone=phone,
            location=location,
            notes=notes,
            visit_date=visit_date,
        )
        visitor.save()

        # Save base64 camera photo if provided
        if photo_data and photo_data.startswith("data:image/"):
            try:
                header, imgstr = photo_data.split(";base64,", 1)
                ext = header.split("/")[-1].lower()
                if ext not in ("jpeg", "jpg", "png", "webp"):
                    ext = "jpeg"
                filename = f"visitor_{uuid.uuid4().hex}.{ext}"
                visitor.photo.save(
                    filename, ContentFile(base64.b64decode(imgstr)), save=True
                )
            except Exception:
                pass  # Photo is optional; ignore decode errors

        messages.success(request, f"Client '{client_name}' added successfully.")
        return redirect("visitor_list")

    context = {
        "today": date.today().strftime("%Y-%m-%d"),
        "own_emp": own_emp,
    }
    return render(request, "accounts/visitor_add.html", context)


@login_required(login_url="login")
def visitor_list(request):
    """
    Employees see only their own records.
    Admin / staff see all records with search + employee filter.
    """
    from .models import ClientVisitor

    is_admin = request.user.is_staff or request.user.is_superuser
    search = request.GET.get("q", "").strip()
    emp_filter = request.GET.get(
        "emp_filter", ""
    ).strip()  # admin-only filter by emp_name

    if is_admin:
        qs = ClientVisitor.objects.all()
        if emp_filter:
            qs = qs.filter(emp_name=emp_filter)
        if search:
            qs = (
                qs.filter(client_name__icontains=search)
                | qs.filter(emp_name__icontains=search)
                | qs.filter(phone__icontains=search)
            )
        # Distinct employee names for the filter dropdown
        emp_choices = (
            ClientVisitor.objects.values_list("emp_name", flat=True)
            .exclude(emp_name__isnull=True)
            .exclude(emp_name="")
            .distinct()
            .order_by("emp_name")
        )
    else:
        qs = ClientVisitor.objects.filter(user=request.user)
        if search:
            qs = qs.filter(client_name__icontains=search) | qs.filter(
                phone__icontains=search
            )
        emp_choices = []

    context = {
        "visitors": qs.order_by("-created_at"),
        "is_admin": is_admin,
        "search": search,
        "emp_filter": emp_filter,
        "emp_choices": emp_choices,
    }
    return render(request, "accounts/visitor_list.html", context)


@login_required(login_url="login")
def visitor_view(request, id):
    """Read-only detail view for a visitor record."""
    from .models import ClientVisitor

    visitor = get_object_or_404(ClientVisitor, id=id)
    is_admin = request.user.is_staff or request.user.is_superuser

    if not is_admin and visitor.user != request.user:
        messages.error(request, "Access denied.")
        return redirect("visitor_list")

    return render(
        request,
        "accounts/visitor_view.html",
        {"visitor": visitor, "is_admin": is_admin},
    )


@login_required(login_url="login")
def visitor_edit(request, id):
    """
    Edit an existing visitor record.
    Employees can only edit their own. Admins can edit any.
    """
    import base64
    import uuid
    from django.core.files.base import ContentFile
    from .models import ClientVisitor
    from datetime import date

    visitor = get_object_or_404(ClientVisitor, id=id)
    is_admin = request.user.is_staff or request.user.is_superuser

    if not is_admin and visitor.user != request.user:
        messages.error(request, "You are not allowed to edit this record.")
        return redirect("visitor_list")

    if request.method == "POST":
        client_name = request.POST.get("client_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        location = request.POST.get("location", "").strip()
        notes = request.POST.get("notes", "").strip()
        visit_date = request.POST.get("visit_date", "").strip() or str(date.today())
        photo_data = request.POST.get("photo_data", "").strip()

        if not client_name:
            messages.error(request, "Client Name is required.")
            return redirect("visitor_edit", id=id)

        visitor.client_name = client_name
        visitor.phone = phone
        visitor.location = location
        visitor.notes = notes
        visitor.visit_date = visit_date
        visitor.save()

        # Save new camera photo if captured
        if photo_data and photo_data.startswith("data:image/"):
            try:
                header, imgstr = photo_data.split(";base64,", 1)
                ext = header.split("/")[-1].lower()
                if ext not in ("jpeg", "jpg", "png", "webp"):
                    ext = "jpeg"
                filename = f"visitor_{uuid.uuid4().hex}.{ext}"
                # Delete old photo file before saving new one
                if visitor.photo:
                    visitor.photo.delete(save=False)
                visitor.photo.save(
                    filename, ContentFile(base64.b64decode(imgstr)), save=True
                )
            except Exception:
                pass  # Photo is optional; ignore decode errors

        messages.success(request, f"Visitor record for '{client_name}' updated.")
        return redirect("visitor_list")

    context = {
        "visitor": visitor,
        "today": date.today().strftime("%Y-%m-%d"),
    }
    return render(request, "accounts/visitor_edit.html", context)


@login_required(login_url="login")
def visitor_delete(request, id):
    """
    Employees can only delete their own records.
    Admins can delete any record.
    """
    from .models import ClientVisitor

    visitor = get_object_or_404(ClientVisitor, id=id)
    is_admin = request.user.is_staff or request.user.is_superuser

    if not is_admin and visitor.user != request.user:
        messages.error(request, "You are not allowed to delete this record.")
        return redirect("visitor_list")

    client_name = visitor.client_name
    visitor.delete()
    messages.success(request, f"Visitor record for '{client_name}' deleted.")
    return redirect("visitor_list")
