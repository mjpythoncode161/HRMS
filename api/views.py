from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from accounts.models import Users, EmpTemp
import hashlib

from django.core.files.storage import default_storage
from django.conf import settings

from django.contrib.auth.models import User as AuthUser, Group
from django.db import transaction


from datetime import datetime, timedelta
from django.db.models import Q
from django.db.models.functions import ExtractMonth, ExtractDay
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.models import AttendanceMaster

from accounts.models import LeaveRequest
from accounts.models import LeaveMaster


@api_view(["POST"])
def login_api(request):
    try:
        # Accept email (or contact) and password from JSON/form/query
        email = (
            request.data.get("email")
            or request.POST.get("email")
            or request.GET.get("email")
        )
        contact = (
            request.data.get("contact")
            or request.POST.get("contact")
            or request.GET.get("contact")
        )
        password = (
            request.data.get("password")
            or request.POST.get("password")
            or request.GET.get("password")
        )

        if not (email or contact) or not password:
            return Response(
                {"status": False, "message": "Email/contact and password required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hashed = hashlib.md5(password.encode()).hexdigest()

        # 1) Check approved users (legacy `Users` table) by email OR contact
        user = None
        if email:
            user = Users.objects.filter(email=email, password=hashed).first()
        if not user and contact:
            user = Users.objects.filter(contact=contact, password=hashed).first()

        if user:
            return Response(
                {
                    "status": True,
                    "user_id": user.id,
                    "name": user.full_name,
                    "email": user.email,
                    "role": user.type,
                    "approval_status": "APPROVED",
                },
                status=status.HTTP_200_OK,
            )

        # 2) Check pending registrations in EmpTemp (PENDING)
        pending = None
        if email:
            pending = EmpTemp.objects.filter(email=email, password=hashed).first()
        if not pending and contact:
            pending = EmpTemp.objects.filter(contact=contact, password=hashed).first()

        if pending:
            return Response(
                {
                    "status": True,
                    "name": pending.full_name,
                    "email": pending.email,
                    "approval_status": pending.status or "PENDING",
                    "message": "Account pending admin approval",
                },
                status=status.HTTP_200_OK,
            )

        # Credentials invalid
        return Response(
            {"status": False, "message": "Invalid email or password"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    except Exception as e:
        # Return error details for debugging (replace with logging in production)
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def register_api(request):
    # Accept JSON, form-data or query params
    full_name = (
        request.data.get("full_name")
        or request.POST.get("full_name")
        or request.GET.get("full_name")
    )
    email = (
        request.data.get("email")
        or request.POST.get("email")
        or request.GET.get("email")
    )
    password = (
        request.data.get("password")
        or request.POST.get("password")
        or request.GET.get("password")
    )
    phone = (
        request.data.get("phone")
        or request.data.get("contact")
        or request.POST.get("phone")
        or request.POST.get("contact")
        or request.GET.get("phone")
        or request.GET.get("contact")
    )
    dob = request.data.get("dob") or request.POST.get("dob") or request.GET.get("dob")
    gender = (
        request.data.get("gender")
        or request.POST.get("gender")
        or request.GET.get("gender")
    )
    address = (
        request.data.get("address")
        or request.POST.get("address")
        or request.GET.get("address")
    )
    father_name = (
        request.data.get("father_name")
        or request.POST.get("father_name")
        or request.GET.get("father_name")
    )
    emergency_contact = (
        request.data.get("emergency_contact")
        or request.POST.get("emergency_contact")
        or request.GET.get("emergency_contact")
    )

    if not full_name or not email or not password or not phone:
        return Response(
            {
                "status": False,
                "message": "full_name, email, phone and password are required",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate phone (must be exactly 10 digits)
    if not phone.isdigit() or len(phone) != 10:
        return Response(
            {"status": False, "message": "Phone number must be exactly 10 digits"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prevent duplicate registrations
    if (
        EmpTemp.objects.filter(contact=phone).exists()
        or Users.objects.filter(contact=phone).exists()
    ):
        return Response(
            {"status": False, "message": "Phone number already registered"},
            status=status.HTTP_409_CONFLICT,
        )

    if (
        EmpTemp.objects.filter(email=email).exists()
        or Users.objects.filter(email=email).exists()
    ):
        return Response(
            {"status": False, "message": "Email already registered"},
            status=status.HTTP_409_CONFLICT,
        )

    # Hash password for legacy storage
    hashed_password = hashlib.md5(password.encode()).hexdigest()

    # Parse dob into date if provided
    dob_date = None
    if dob:
        try:
            dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
        except Exception:
            dob_date = None

    # Create Django auth user (inactive until admin approves) and EmpTemp in an atomic transaction
    try:
        with transaction.atomic():
            # Create Django auth user if not exists
            if (
                not AuthUser.objects.filter(username=phone).exists()
                and not AuthUser.objects.filter(email=email).exists()
            ):
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                auth_user = AuthUser.objects.create_user(
                    username=phone,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
                auth_user.is_active = False
                auth_user.save()
                try:
                    auth_user.groups.add(Group.objects.get(name="customer"))
                except Group.DoesNotExist:
                    pass

            # Create EmpTemp record for admin approval
            emp_temp = EmpTemp.objects.create(
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

    except Exception as e:
        return Response(
            {"status": False, "message": f"Registration failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "status": True,
            "message": "Registration successful. Pending admin approval.",
            "reg_id": emp_temp.id,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def logout_api(request):

    return Response({"status": True, "message": "Logout successful"})


from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime as _dt


@api_view(["POST"])
def attendance_checkin(request):
    """Record employee/admin check-in"""

    try:
        from accounts.models import (
            Users,
            AttendanceMaster,
            EmployeeLocationTracking,
            AttendanceReq,
        )
        from datetime import datetime as _dt
        from datetime import timedelta

        data = request.data

        emp_id = data.get("emp_id")
        full_name = data.get("full_name")
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        photo = data.get("photo") or ""

        # ✅ Admin flag
        is_admin = data.get("is_admin")
        is_admin_flag = str(is_admin).lower() in ["1", "true"]

        check_in = data.get("check_in") or _dt.now().time()
        att_date = data.get("att_date") or _dt.now().date()

        user_obj = None

        # 🔍 Detect logged-in user
        if hasattr(request, "user") and request.user.is_authenticated:
            try:
                user_obj = Users.objects.filter(
                    email=getattr(request.user, "email", None)
                ).first()
            except:
                pass

        # ================= ADMIN =================
        if (user_obj and user_obj.type == 1) or is_admin_flag:
            emp_id = user_obj.id if user_obj else 1
            if not full_name:
                full_name = user_obj.full_name if user_obj else "Admin"

        # ================= EMPLOYEE =================
        else:
            if not emp_id:
                return Response(
                    {"status": False, "message": "emp_id required for employee"},
                    status=400,
                )

        # 🧠 Parse date
        try:
            att_date_parsed = (
                _dt.fromisoformat(str(att_date)).date()
                if isinstance(att_date, str)
                else att_date
            )
        except:
            att_date_parsed = _dt.now().date()

        # 🧠 Parse time
        try:
            checkin_time = (
                _dt.fromisoformat(str(check_in)).time()
                if isinstance(check_in, str)
                else check_in
            )
        except:
            checkin_time = _dt.now().time()

        # =========================================================
        # ✅ FIX: Check previous incomplete attendance + request
        # =========================================================

        previous_incomplete = (
            AttendanceMaster.objects.filter(
                emp_id=emp_id,
                check_in__isnull=False,
                check_out__isnull=True,
                att_date__lt=att_date_parsed,
            )
            .order_by("-att_date")
            .first()
        )

        if previous_incomplete:
            # 🔍 Check if regularization request exists
            req_exists = AttendanceReq.objects.filter(
                emp_id=emp_id, reg_date=previous_incomplete.att_date
            ).exists()

            # ❌ Block ONLY if request NOT submitted
            if not req_exists:
                return Response(
                    {
                        "status": False,
                        "message": "Previous day checkout missing. Please raise request.",
                        "missed_checkout": True,
                        "missing_date": previous_incomplete.att_date,
                    },
                    status=403,
                )
        # =========================================================

        # 🚫 Prevent duplicate check-in (same day)
        existing = AttendanceMaster.objects.filter(
            emp_id=emp_id, att_date=att_date_parsed, check_out__isnull=True
        ).first()

        if existing:
            return Response(
                {
                    "status": False,
                    "message": "Already checked in",
                    "attendance_id": existing.id,
                },
                status=409,
            )

        # ✅ Create attendance
        att = AttendanceMaster.objects.create(
            emp_id=emp_id,
            full_name=full_name or "",
            check_in=checkin_time,
            att_date=att_date_parsed,
            photo=photo,
            latitude=latitude or "0",
            longitude=longitude or "0",
            attendance_status="Present",
        )

        # 📍 Location tracking
        try:
            EmployeeLocationTracking.objects.create(
                user_id=0,
                emp_id=str(emp_id),
                full_name=full_name or "",
                latitude=latitude or 0,
                longitude=longitude or 0,
                is_checkin_point=True,
                session_date=att_date_parsed,
            )
        except:
            pass

        return Response(
            {
                "status": True,
                "message": "Check-in recorded",
                "attendance_id": att.id,
            },
            status=201,
        )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=500,
        )


@api_view(["GET"])
def attendance_list(request):
    """Return list of attendance rows with late calculation + status."""

    try:
        from accounts.models import AttendanceMaster
        from datetime import datetime as _dt, time
        from django.core.files.storage import default_storage
        from rest_framework import status as http_status

        emp_id = request.GET.get("emp_id")
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        OFFICE_TIME = time(9, 30)
        GRACE_MINUTES = 10

        qs = AttendanceMaster.objects.all()

        if emp_id:
            qs = qs.filter(emp_id=emp_id)

        if from_date:
            try:
                fd = _dt.fromisoformat(from_date).date()
                qs = qs.filter(att_date__gte=fd)
            except:
                pass

        if to_date:
            try:
                td = _dt.fromisoformat(to_date).date()
                qs = qs.filter(att_date__lte=td)
            except:
                pass

        rows = []

        for item in qs.order_by("-att_date", "-id"):

            # -----------------------
            # IMAGE URLS (SAFE)
            # -----------------------
            try:
                photo_url = (
                    request.build_absolute_uri(default_storage.url(item.photo))
                    if item.photo
                    else ""
                )
            except:
                photo_url = ""

            try:
                out_photo_url = (
                    request.build_absolute_uri(default_storage.url(item.out_photo))
                    if item.out_photo
                    else ""
                )
            except:
                out_photo_url = ""

            # -----------------------
            # LOCATION
            # -----------------------
            check_in_location = (
                f"{item.latitude}, {item.longitude}"
                if item.latitude and item.longitude
                else ""
            )

            check_out_location = (
                f"{item.out_lati}, {item.out_long}"
                if item.out_lati and item.out_long
                else ""
            )

            # -----------------------
            # ATTENDANCE STATUS LOGIC
            # -----------------------
            late_minutes = 0
            attendance_status = "Absent"

            if item.check_in and item.att_date:
                try:
                    office_dt = _dt.combine(item.att_date, OFFICE_TIME)

                    # safe handling if check_in is already datetime or time
                    checkin_dt = _dt.combine(item.att_date, item.check_in)

                    diff_minutes = int((checkin_dt - office_dt).total_seconds() / 60)

                    if diff_minutes > GRACE_MINUTES:
                        late_minutes = diff_minutes
                        attendance_status = "Late"
                    else:
                        attendance_status = "Present"

                except:
                    attendance_status = "Present"
                    late_minutes = 0

            rows.append(
                {
                    "id": item.id,
                    "emp_id": item.emp_id,
                    "full_name": item.full_name,
                    "att_date": item.att_date,
                    "check_in": item.check_in,
                    "check_out": item.check_out,
                    "worked_hours": item.worked_hours,
                    "attendance_status": attendance_status,
                    "late_minutes": late_minutes,
                    "photo": photo_url,
                    "out_photo": out_photo_url,
                    "check_in_location": check_in_location,
                    "check_out_location": check_out_location,
                }
            )

        return Response(
            {"status": True, "attendances": rows}, status=http_status.HTTP_200_OK
        )

    except Exception as e:
        import traceback

        print(traceback.format_exc())

        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def attendance_edit_api(request):
    """Edit an existing attendance row (e.g., add missed checkout).

    Params: id (attendance id) OR emp_id + att_date; optional check_in, check_out
    """
    try:
        from accounts.models import AttendanceMaster
        from datetime import datetime as _dt, timedelta

        att_id = request.data.get("id") or request.POST.get("id")
        emp_id = request.data.get("emp_id") or request.POST.get("emp_id")
        att_date = request.data.get("att_date") or request.POST.get("att_date")
        admin_check_in = request.data.get("check_in") or request.POST.get("check_in")
        admin_check_out = request.data.get("check_out") or request.POST.get("check_out")

        att = None
        if att_id:
            att = AttendanceMaster.objects.filter(id=att_id).first()
        else:
            if emp_id and att_date:
                try:
                    ad = _dt.fromisoformat(att_date).date()
                except Exception:
                    ad = None
                att = (
                    AttendanceMaster.objects.filter(emp_id=emp_id, att_date=ad)
                    .order_by("-id")
                    .first()
                )

        if not att:
            return Response(
                {"status": False, "message": "Attendance record not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if admin_check_in:
            try:
                att.check_in = _dt.fromisoformat(admin_check_in).time()
            except Exception:
                pass
        if admin_check_out:
            try:
                att.check_out = _dt.fromisoformat(admin_check_out).time()
            except Exception:
                pass

        # recompute worked_hours
        try:
            dt_in = _dt.combine(att.att_date, att.check_in)
            dt_out = _dt.combine(att.att_date, att.check_out)
            if dt_out < dt_in:
                dt_out += timedelta(days=1)
            att.worked_hours = round((dt_out - dt_in).total_seconds() / 3600.0, 2)
        except Exception:
            pass

        att.save()
        return Response(
            {"status": True, "message": "Attendance updated", "attendance_id": att.id},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def attendance_req_submit(request):
    """Submit regularization request (employee).

    Params: emp_id, reg_date (YYYY-MM-DD), check_in, check_out, reason, attendance_status
    """
    try:
        from accounts.models import AttendanceReq, EmpMaster
        from datetime import datetime as _dt

        emp_id = request.data.get("emp_id") or request.POST.get("emp_id")
        reg_date = request.data.get("reg_date") or request.POST.get("reg_date")
        check_in = request.data.get("check_in") or request.POST.get("check_in")
        check_out = request.data.get("check_out") or request.POST.get("check_out")
        reason = request.data.get("reason") or request.POST.get("reason")
        attendance_status = (
            request.data.get("attendance_status")
            or request.POST.get("attendance_status")
            or "Full Day"
        )

        if not (emp_id and reg_date):
            return Response(
                {"status": False, "message": "emp_id and reg_date required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reg_date_obj = _dt.fromisoformat(reg_date).date()
        except Exception:
            return Response(
                {"status": False, "message": "Invalid reg_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent duplicate request
        if AttendanceReq.objects.filter(emp_id=emp_id, reg_date=reg_date_obj).exists():
            return Response(
                {"status": False, "message": "Regularization request already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            emp = EmpMaster.objects.get(emp_id=emp_id)
            full_name = emp.full_name
        except Exception:
            full_name = ""

        req = AttendanceReq.objects.create(
            emp_id=emp_id,
            full_name=full_name,
            reg_date=reg_date_obj,
            check_in=check_in or "",
            check_out=check_out or "",
            reason=reason or "",
            approval_status="Pending",
            status=attendance_status,
        )
        return Response(
            {"status": True, "message": "Request submitted", "request_id": req.id},
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def attendance_req_list_api(request):
    """List regularization requests. Optional emp_id and status filter."""
    try:
        from accounts.models import AttendanceReq

        emp_id = request.GET.get("emp_id")
        status_filter = request.GET.get("status")

        qs = AttendanceReq.objects.all()
        if emp_id:
            qs = qs.filter(emp_id=emp_id)
        if status_filter:
            qs = qs.filter(approval_status__iexact=status_filter)

        rows = list(
            qs.order_by("-created_at").values(
                "id",
                "emp_id",
                "full_name",
                "reg_date",
                "check_in",
                "check_out",
                "reason",
                "approval_status",
                "status",
            )
        )
        return Response({"status": True, "requests": rows}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def attendance_req_update_api(request, id):
    """Admin: approve/reject a regularization request. If approved, update/create AttendanceMaster."""
    try:
        from accounts.models import AttendanceReq, AttendanceMaster
        from datetime import datetime as _dt, timedelta

        new_status = request.data.get("status") or request.POST.get("status")
        admin_check_in = request.data.get("admin_check_in") or request.POST.get(
            "admin_check_in"
        )
        admin_check_out = request.data.get("admin_check_out") or request.POST.get(
            "admin_check_out"
        )

        req = AttendanceReq.objects.get(id=id)
        if new_status:
            req.approval_status = new_status
        if admin_check_in:
            req.check_in = admin_check_in
        if admin_check_out:
            req.check_out = admin_check_out
        req.save()

        if new_status == "Approved":
            # update or create attendance
            att = (
                AttendanceMaster.objects.filter(
                    emp_id=req.emp_id, att_date=req.reg_date
                )
                .order_by("-id")
                .first()
            )
            if att:
                att.check_in = req.check_in or att.check_in
                att.check_out = req.check_out or att.check_out
                try:
                    if att.check_in and att.check_out:
                        dt_in = _dt.combine(
                            att.att_date,
                            (
                                _dt.fromisoformat(str(att.check_in)).time()
                                if isinstance(att.check_in, str)
                                else att.check_in
                            ),
                        )
                        dt_out = _dt.combine(
                            att.att_date,
                            (
                                _dt.fromisoformat(str(att.check_out)).time()
                                if isinstance(att.check_out, str)
                                else att.check_out
                            ),
                        )
                        if dt_out < dt_in:
                            dt_out += timedelta(days=1)
                        att.worked_hours = round(
                            (dt_out - dt_in).total_seconds() / 3600.0, 2
                        )
                except Exception:
                    pass
                att.save()
            else:
                AttendanceMaster.objects.create(
                    emp_id=req.emp_id,
                    full_name=req.full_name,
                    att_date=req.reg_date,
                    check_in=req.check_in or None,
                    check_out=req.check_out or None,
                    attendance_status=req.status if req.status else "Present",
                    latitude="0",
                    longitude="0",
                )

        return Response(
            {"status": True, "message": "Request updated"}, status=status.HTTP_200_OK
        )
    except AttendanceReq.DoesNotExist:
        return Response(
            {"status": False, "message": "Request not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def attendance_get(request):
    """Return attendance details for given emp_id and att_date.

    Query params: emp_id (required), att_date (YYYY-MM-DD, optional defaults to today)
    """
    try:
        emp_id = request.GET.get("emp_id") or request.POST.get("emp_id")
        att_date = request.GET.get("att_date") or request.POST.get("att_date")
        from accounts.models import AttendanceMaster, AttendanceReq
        from datetime import datetime as _dt

        if not emp_id:
            return Response(
                {"status": False, "message": "emp_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # parse date
        try:
            att_date_parsed = (
                _dt.fromisoformat(att_date).date() if att_date else _dt.now().date()
            )
        except Exception:
            try:
                att_date_parsed = _dt.strptime(att_date, "%Y-%m-%d").date()
            except Exception:
                att_date_parsed = _dt.now().date()

        att = (
            AttendanceMaster.objects.filter(emp_id=emp_id, att_date=att_date_parsed)
            .order_by("-id")
            .values(
                "id",
                "emp_id",
                "full_name",
                "att_date",
                "check_in",
                "check_out",
                "worked_hours",
                "attendance_status",
            )
            .first()
        )

        approved = AttendanceReq.objects.filter(
            emp_id=emp_id, reg_date=att_date_parsed, approval_status="Approved"
        ).exists()

        return Response(
            {"status": True, "attendance": att, "approved_regularization": approved},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def attendance_checkout(request):
    """Record employee check-out and update worked hours."""
    try:
        emp_id = (
            request.data.get("emp_id")
            or request.POST.get("emp_id")
            or request.GET.get("emp_id")
        )
        check_out = request.data.get("check_out") or datetime.now().time().isoformat()
        att_date = request.data.get("att_date") or datetime.now().date().isoformat()
        out_lati = request.data.get("out_lati") or request.data.get("latitude")
        out_long = request.data.get("out_long") or request.data.get("longitude")
        out_photo = request.data.get("out_photo") or ""

        if not emp_id:
            return Response(
                {"status": False, "message": "emp_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounts.models import AttendanceMaster, EmployeeLocationTracking
        from datetime import datetime as _dt
        from datetime import timedelta

        # parse date/time
        try:
            att_date_parsed = (
                _dt.fromisoformat(att_date).date()
                if isinstance(att_date, str)
                else att_date
            )
        except Exception:
            try:
                att_date_parsed = _dt.strptime(att_date, "%Y-%m-%d").date()
            except Exception:
                att_date_parsed = _dt.now().date()

        try:
            checkout_time = (
                _dt.fromisoformat(check_out).time()
                if isinstance(check_out, str)
                else check_out
            )
        except Exception:
            try:
                checkout_time = _dt.strptime(check_out, "%H:%M:%S").time()
            except Exception:
                checkout_time = _dt.now().time()

        # find attendance row for emp + date (most recent)

        att = AttendanceMaster.objects.filter(
            emp_id=emp_id, att_date=att_date_parsed, check_out__isnull=True
        ).first()

        if not att:
            return Response(
                {"status": False, "message": "No check-in found for today"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prevent duplicate check-outs for the same attendance record
        if att.check_out:
            return Response(
                {
                    "status": False,
                    "message": "Already checked out for this date",
                    "attendance_id": att.id,
                },
                status=status.HTTP_409_CONFLICT,
            )

        att.check_out = checkout_time
        att.out_photo = out_photo
        att.out_lati = out_lati or att.latitude
        att.out_long = out_long or att.longitude

        # compute worked_hours (hours as decimal)
        try:
            dt_in = _dt.combine(att.att_date, att.check_in)
            dt_out = _dt.combine(att.att_date, att.check_out)
            if dt_out < dt_in:
                # assume checkout next day
                dt_out = dt_out + timedelta(days=1)
            total_seconds = (dt_out - dt_in).total_seconds()
            hours = round(total_seconds / 3600.0, 2)
            att.worked_hours = hours
        except Exception:
            pass

        att.save()

        # record checkout location ping
        try:
            EmployeeLocationTracking.objects.create(
                user_id=0,
                emp_id=str(emp_id),
                full_name=att.full_name or "",
                latitude=att.out_lati,
                longitude=att.out_long,
                is_checkin_point=False,
                session_date=att.att_date,
            )
        except Exception:
            pass

        return Response(
            {"status": True, "message": "Check-out recorded", "attendance_id": att.id},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET", "POST"])
def location_tracking_api(request):
    """Single API for continuous location tracking (save + view).

    POST /api/location/
      Body (JSON/form): emp_id, latitude, longitude, optional session_date/full_name/user_id/is_checkin_point

    GET /api/location/?emp_id=101&session_date=2026-04-09
      Returns list of points for that employee & date.
    """

    try:
        from datetime import datetime as _dt

        def _parse_date(value):
            """Parse ISO-like date/datetime strings into a date.

            Supports: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS(.ffffff)(Z|+HH:MM)
            """

            if value is None:
                return None
            s = str(value).strip()
            if not s:
                return None
            # Dart often sends UTC timestamps like 2026-04-15T10:20:30.000Z
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            try:
                return _dt.fromisoformat(s).date()
            except Exception:
                try:
                    return _dt.strptime(s, "%Y-%m-%d").date()
                except Exception:
                    return None

        def _to_bool(value):
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            return s in ("1", "true", "yes", "y", "on", "t")

        # ===================== POST: save ping =====================
        if request.method == "POST":
            from decimal import Decimal, InvalidOperation
            from accounts.models import EmployeeLocationTracking, Users, EmpMaster

            data = request.data or request.POST

            emp_id = data.get("emp_id")
            latitude_raw = data.get("latitude")
            longitude_raw = data.get("longitude")
            session_date_raw = data.get("session_date") or data.get("att_date")
            full_name = data.get("full_name")
            user_id = data.get("user_id")
            is_checkin_point = (
                data.get("is_checkin_point")
                if "is_checkin_point" in data
                else data.get("is_checkin")
            )

            if not emp_id:
                return Response(
                    {"status": False, "message": "emp_id required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if latitude_raw in (None, "") or longitude_raw in (None, ""):
                return Response(
                    {"status": False, "message": "latitude and longitude required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                latitude = Decimal(str(latitude_raw).strip())
                longitude = Decimal(str(longitude_raw).strip())
            except (InvalidOperation, ValueError, TypeError):
                return Response(
                    {"status": False, "message": "Invalid latitude/longitude"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if latitude < Decimal("-90") or latitude > Decimal("90"):
                return Response(
                    {"status": False, "message": "latitude out of range"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if longitude < Decimal("-180") or longitude > Decimal("180"):
                return Response(
                    {"status": False, "message": "longitude out of range"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            session_date = _parse_date(session_date_raw) or _dt.now().date()

            try:
                user_id_s = str(user_id).strip() if user_id is not None else ""
                user_id_val = int(user_id_s) if user_id_s != "" else 0
            except Exception:
                user_id_val = 0

            is_checkin_flag = _to_bool(is_checkin_point)

            if not full_name:
                try:
                    u = Users.objects.filter(id=str(emp_id)).first()
                    if u and getattr(u, "full_name", None):
                        full_name = u.full_name
                except Exception:
                    pass

            if not full_name:
                try:
                    em = EmpMaster.objects.filter(emp_id=str(emp_id)).first()
                    if em and getattr(em, "full_name", None):
                        full_name = em.full_name
                except Exception:
                    pass

            loc = EmployeeLocationTracking.objects.create(
                user_id=user_id_val,
                emp_id=str(emp_id),
                full_name=full_name or "",
                latitude=latitude,
                longitude=longitude,
                session_date=session_date,
                is_checkin_point=is_checkin_flag,
            )

            return Response(
                {
                    "status": True,
                    "message": "Location saved",
                    "location_id": loc.id,
                    "session_date": session_date.isoformat(),
                    "timestamp": loc.timestamp.isoformat() if loc.timestamp else None,
                    "latitude": float(loc.latitude),
                    "longitude": float(loc.longitude),
                    "is_checkin_point": bool(loc.is_checkin_point),
                },
                status=status.HTTP_201_CREATED,
            )

        # ===================== GET: list points =====================
        from accounts.models import EmployeeLocationTracking

        emp_id = request.GET.get("emp_id")
        session_date_raw = request.GET.get("session_date") or request.GET.get(
            "att_date"
        )

        if not emp_id:
            return Response(
                {"status": False, "message": "emp_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_date = _dt.now().date()
        if session_date_raw:
            parsed = _parse_date(session_date_raw)
            if not parsed:
                return Response(
                    {"status": False, "message": "Invalid session_date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            session_date = parsed

        qs = EmployeeLocationTracking.objects.filter(
            emp_id=str(emp_id),
            session_date=session_date,
        ).order_by("timestamp")

        points = []
        for loc in qs:
            points.append(
                {
                    "id": loc.id,
                    "emp_id": loc.emp_id,
                    "full_name": loc.full_name or "",
                    "latitude": float(loc.latitude),
                    "longitude": float(loc.longitude),
                    "timestamp": loc.timestamp.isoformat() if loc.timestamp else None,
                    "session_date": (
                        loc.session_date.isoformat() if loc.session_date else None
                    ),
                    "is_checkin_point": bool(loc.is_checkin_point),
                }
            )

        return Response(
            {
                "status": True,
                "emp_id": str(emp_id),
                "session_date": session_date.isoformat(),
                "count": len(points),
                "points": points,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET", "PUT", "PATCH"])
def yearly_leave_api(request):
    """Get/update an employee's yearly leave balance.

    GET:   /api/yearly-leave/?emp_id=EMP
    PUT:   JSON body {emp_id, yearly_leaves?, total_yearly_leaves?}
    PATCH: same as PUT (partial)
    """

    try:
        from accounts.models import EmpMaster

        emp_id = request.GET.get("emp_id") or request.data.get("emp_id")
        if not emp_id:
            return Response(
                {"status": False, "message": "emp_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        emp = EmpMaster.objects.filter(emp_id=str(emp_id)).first()
        if not emp:
            return Response(
                {"status": False, "message": "Employee not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method in ("PUT", "PATCH"):
            if "yearly_leaves" in request.data:
                try:
                    emp.yearly_leaves = int(request.data.get("yearly_leaves"))
                except Exception:
                    return Response(
                        {"status": False, "message": "Invalid yearly_leaves"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if "total_yearly_leaves" in request.data:
                emp.total_yearly_leaves = str(request.data.get("total_yearly_leaves"))

            emp.save()

        return Response(
            {
                "status": True,
                "emp_id": emp.emp_id,
                "full_name": emp.full_name,
                "yearly_leaves": emp.yearly_leaves,
                "total_yearly_leaves": emp.total_yearly_leaves,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def yearly_leaves(request):
    try:
        emp_id = request.data.get("emp_id")  # similar to $_POST['emp_id']

        if not emp_id:
            return Response(
                {"status": "error", "message": "Employee ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        emp = Employee.objects.filter(emp_id=emp_id).first()
        if not emp:
            return Response(
                {"status": "error", "message": "Employee not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        total = emp.total_yearly_leaves
        remaining = emp.yearly_leaves
        used = total - remaining

        return Response(
            {
                "status": "success",
                "total_leaves": total,
                "used_leaves": used,
                "remaining_leaves": remaining,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"status": "error", "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def leave_types_api(request):
    """Fetch leave types.

    GET: /api/leave-types/
    Optional filters:
      - ?is_paid=1 or 0
    """

    try:
        from accounts.models import LeaveMaster

        qs = LeaveMaster.objects.all().order_by("leave_type")

        is_paid = request.GET.get("is_paid")
        if is_paid is not None and str(is_paid).strip() != "":
            if str(is_paid) in ("0", "1"):
                qs = qs.filter(is_paid=int(is_paid))

        rows = list(
            qs.values(
                "id",
                "leave_type",
                "description",
                "is_paid",
                "allow_half_day",
            )
        )

        return Response({"status": True, "leave_types": rows}, status=200)
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=500,
        )


@api_view(["GET", "POST"])
def leave_list_create(request):
    """List leave requests (GET) or create a new leave request (POST)."""

    try:
        # ===================== GET =====================
        if request.method == "GET":
            emp_id = request.GET.get("emp_id")
            qs = LeaveRequest.objects.all()

            if emp_id:
                qs = qs.filter(emp_id=emp_id)

            rows = []
            for l in qs.order_by("-applied_at").values(
                "id",
                "emp_id",
                "full_name",
                "leave_type",
                "leave_duration",
                "start_date",
                "end_date",
                "leave_status",
                "reason",
                "applied_at",
                "approved_by",
                "approved_at",
                "total_leaves",
                "yearly_leaves",
                "is_paid",
            ):
                if l.get("applied_at"):
                    try:
                        l["applied_at"] = l["applied_at"].isoformat()
                    except:
                        pass

                if l.get("approved_at"):
                    try:
                        l["approved_at"] = l["approved_at"].isoformat()
                    except:
                        pass

                rows.append(l)

            return Response({"status": True, "leaves": rows}, status=200)

        # ===================== POST =====================
        if request.method == "POST":

            data = request.data  # ✅ FIXED

            emp_id = data.get("emp_id")
            leave_type = data.get("leave_type")
            start_date = data.get("start_date")
            end_date = data.get("end_date")
            leave_duration = data.get("leave_duration", "Full Day")
            reason = data.get("reason", "")
            is_paid = data.get("is_paid", 0)

            # required fields check
            if not (emp_id and start_date and end_date):
                return Response(
                    {
                        "status": False,
                        "message": "emp_id, start_date and end_date required",
                    },
                    status=400,
                )

            # parse dates
            try:
                sd = _dt.fromisoformat(start_date).date()
            except:
                try:
                    sd = _dt.strptime(start_date, "%Y-%m-%d").date()
                except:
                    return Response(
                        {"status": False, "message": "Invalid start_date"},
                        status=400,
                    )

            try:
                ed = _dt.fromisoformat(end_date).date()
            except:
                try:
                    ed = _dt.strptime(end_date, "%Y-%m-%d").date()
                except:
                    return Response(
                        {"status": False, "message": "Invalid end_date"},
                        status=400,
                    )

            # optional full_name fetch
            full_name = data.get("full_name", "")
            try:
                from accounts.models import EmpMaster

                if not full_name:
                    em = EmpMaster.objects.filter(emp_id=str(emp_id)).first()
                    if em:
                        full_name = em.full_name or ""
            except:
                pass

            # duplicate check
            if LeaveRequest.objects.filter(
                emp_id=emp_id, start_date=sd, end_date=ed
            ).exists():
                return Response(
                    {
                        "status": False,
                        "message": "Leave already applied for these dates",
                    },
                    status=400,
                )

            # create leave
            lr = LeaveRequest.objects.create(
                emp_id=emp_id,
                full_name=full_name,
                leave_type=leave_type or "",
                leave_duration=leave_duration,
                start_date=sd,
                end_date=ed,
                leave_status=0,
                reason=reason,
                total_leaves=0,
                yearly_leaves=0,
                is_paid=int(is_paid) if str(is_paid).isdigit() else 0,
            )

            return Response(
                {"status": True, "message": "Leave requested", "leave_id": lr.id},
                status=201,
            )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=500,
        )


@api_view(["GET", "POST"])
def leave_list_create(request):
    """List leave requests (GET) or create a new leave request (POST)."""

    try:
        # ===================== GET =====================
        if request.method == "GET":
            emp_id = request.GET.get("emp_id")
            qs = LeaveRequest.objects.all()

            if emp_id:
                qs = qs.filter(emp_id=emp_id)

            rows = []
            for l in qs.order_by("-applied_at").values(
                "id",
                "emp_id",
                "full_name",
                "leave_type",
                "leave_duration",
                "start_date",
                "end_date",
                "leave_status",
                "reason",
                "applied_at",
                "approved_by",
                "approved_at",
                "total_leaves",
                "yearly_leaves",
                "is_paid",
            ):
                if l.get("applied_at"):
                    try:
                        l["applied_at"] = l["applied_at"].isoformat()
                    except:
                        pass

                if l.get("approved_at"):
                    try:
                        l["approved_at"] = l["approved_at"].isoformat()
                    except:
                        pass

                rows.append(l)

            return Response({"status": True, "leaves": rows}, status=200)

        # ===================== POST =====================
        if request.method == "POST":

            # ✅ HANDLE ALL TYPES (JSON, form-data, raw)
            data = request.data
            if not data:
                data = request.POST
            if not data:
                try:
                    import json

                    data = json.loads(request.body)
                except:
                    data = {}

            emp_id = data.get("emp_id")
            leave_type = data.get("leave_type")
            start_date = data.get("start_date")
            end_date = data.get("end_date")
            leave_duration = data.get("leave_duration", "Full Day")
            reason = data.get("reason", "")
            is_paid = data.get("is_paid", 0)

            # required fields check
            if not (emp_id and start_date and end_date):
                return Response(
                    {
                        "status": False,
                        "message": "emp_id, start_date and end_date required",
                    },
                    status=400,
                )

            # parse dates
            try:
                sd = _dt.fromisoformat(start_date).date()
            except:
                try:
                    sd = _dt.strptime(start_date, "%Y-%m-%d").date()
                except:
                    return Response(
                        {"status": False, "message": "Invalid start_date"},
                        status=400,
                    )

            try:
                ed = _dt.fromisoformat(end_date).date()
            except:
                try:
                    ed = _dt.strptime(end_date, "%Y-%m-%d").date()
                except:
                    return Response(
                        {"status": False, "message": "Invalid end_date"},
                        status=400,
                    )

            # optional full_name fetch
            full_name = data.get("full_name", "")
            try:
                from accounts.models import EmpMaster

                if not full_name:
                    em = EmpMaster.objects.filter(emp_id=str(emp_id)).first()
                    if em:
                        full_name = em.full_name or ""
            except:
                pass

            # duplicate check
            if LeaveRequest.objects.filter(
                emp_id=emp_id, start_date=sd, end_date=ed
            ).exists():
                return Response(
                    {
                        "status": False,
                        "message": "Leave already applied for these dates",
                    },
                    status=400,
                )

            # create leave
            lr = LeaveRequest.objects.create(
                emp_id=emp_id,
                full_name=full_name,
                leave_type=leave_type or "",
                leave_duration=leave_duration,
                start_date=sd,
                end_date=ed,
                leave_status=0,
                reason=reason,
                total_leaves=0,
                yearly_leaves=0,
                is_paid=int(is_paid) if str(is_paid).isdigit() else 0,
            )

            return Response(
                {"status": True, "message": "Leave requested", "leave_id": lr.id},
                status=201,
            )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=500,
        )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def leave_detail(request, id):
    try:
        from accounts.models import LeaveRequest
        from datetime import datetime as _dt

        lr = LeaveRequest.objects.filter(id=id).first()
        if not lr:
            return Response(
                {"status": False, "message": "Leave request not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            data = {
                "id": lr.id,
                "emp_id": lr.emp_id,
                "full_name": lr.full_name,
                "leave_type": lr.leave_type,
                "leave_duration": lr.leave_duration,
                "start_date": lr.start_date.isoformat() if lr.start_date else None,
                "end_date": lr.end_date.isoformat() if lr.end_date else None,
                "leave_status": lr.leave_status,
                "reason": lr.reason,
                "applied_at": lr.applied_at.isoformat() if lr.applied_at else None,
                "approved_by": lr.approved_by,
                "approved_at": lr.approved_at.isoformat() if lr.approved_at else None,
                "total_leaves": lr.total_leaves,
                "yearly_leaves": lr.yearly_leaves,
                "is_paid": lr.is_paid,
            }
            return Response({"status": True, "leave": data}, status=status.HTTP_200_OK)

        if request.method in ("PUT", "PATCH"):
            changed = False
            for f in (
                "leave_type",
                "leave_duration",
                "start_date",
                "end_date",
                "reason",
                "leave_status",
                "approved_by",
                "is_paid",
            ):
                v = request.data.get(f) or request.POST.get(f)
                if v is not None:
                    if f in ("start_date", "end_date"):
                        try:
                            setattr(lr, f, _dt.fromisoformat(v).date())
                        except Exception:
                            pass
                    elif f == "leave_status":
                        try:
                            lr.leave_status = int(v)
                        except Exception:
                            lr.leave_status = v
                    elif f == "is_paid":
                        try:
                            lr.is_paid = int(v)
                        except Exception:
                            pass
                    else:
                        setattr(lr, f, v)
                    changed = True
            if changed:
                lr.save()
            return Response(
                {"status": True, "message": "Leave updated"}, status=status.HTTP_200_OK
            )

        lr.delete()
        return Response(
            {"status": True, "message": "Leave request deleted"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def leave_status_update_api(request, id):
    try:
        from accounts.models import LeaveRequest

        new_status = request.data.get("status") or request.POST.get("status")
        if new_status is None:
            return Response(
                {"status": False, "message": "status required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lr = LeaveRequest.objects.get(id=id)
        try:
            lr.leave_status = int(new_status)
        except Exception:
            lr.leave_status = new_status
        lr.save()
        return Response(
            {"status": True, "message": "Status updated"}, status=status.HTTP_200_OK
        )
    except LeaveRequest.DoesNotExist:
        return Response(
            {"status": False, "message": "Leave request not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def leave_approve_api(request, id):
    try:
        from accounts.models import LeaveRequest
        from datetime import datetime as _dt

        lr = LeaveRequest.objects.get(id=id)
        lr.leave_status = 1
        lr.approved_by = (
            request.data.get("approved_by")
            or request.POST.get("approved_by")
            or "admin"
        )
        lr.approved_at = _dt.now()
        lr.save()
        return Response(
            {"status": True, "message": "Leave approved"}, status=status.HTTP_200_OK
        )
    except LeaveRequest.DoesNotExist:
        return Response(
            {"status": False, "message": "Leave request not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def leave_reject_api(request, id):
    try:
        from accounts.models import LeaveRequest
        from datetime import datetime as _dt

        lr = LeaveRequest.objects.get(id=id)
        lr.leave_status = 2
        lr.approved_by = (
            request.data.get("approved_by")
            or request.POST.get("approved_by")
            or "admin"
        )
        lr.approved_at = _dt.now()
        lr.save()
        return Response(
            {"status": True, "message": "Leave rejected"}, status=status.HTTP_200_OK
        )
    except LeaveRequest.DoesNotExist:
        return Response(
            {"status": False, "message": "Leave request not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def admin_profile_api(request):
    """Return admin profile using id (no authentication)."""
    try:
        from accounts.models import Users

        user_id = request.GET.get("id")

        if not user_id:
            return Response(
                {"status": False, "message": "User ID required"}, status=400
            )

        user_obj = Users.objects.filter(id=user_id, type=1).first()

        if not user_obj:
            return Response({"status": False, "message": "Admin not found"}, status=404)

        item = (
            Users.objects.filter(id=user_obj.id)
            .values("id", "full_name", "email", "contact", "type", "created_at")
            .first()
        )

        return Response({"status": True, "profile": item}, status=200)

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET"])
def user_profile_api(request):
    """Public API: return profile using emp_id (no authentication)."""
    try:
        from accounts.models import Users, EmpMaster

        emp_id = request.GET.get("emp_id")

        if not emp_id:
            return Response(
                {"status": False, "message": "emp_id is required"}, status=400
            )

        # 🔹 Find user from Users table
        user_obj = Users.objects.filter(id=emp_id).first()

        if not user_obj:
            return Response({"status": False, "message": "User not found"}, status=404)

        # 🔹 Try to get EmpMaster profile
        profile = None
        try:
            if getattr(user_obj, "contact", None):
                profile = (
                    EmpMaster.objects.filter(contact=user_obj.contact)
                    .values(
                        "id",
                        "full_name",
                        "email",
                        "contact",
                        "dob",
                        "gender",
                        "present_addr",
                        "total_yearly_leaves",
                        "profile_photo",
                    )
                    .first()
                )

            if not profile and getattr(user_obj, "email", None):
                profile = (
                    EmpMaster.objects.filter(email=user_obj.email)
                    .values(
                        "id",
                        "full_name",
                        "email",
                        "contact",
                        "dob",
                        "gender",
                        "present_addr",
                        "total_yearly_leaves",
                        "profile_photo",
                    )
                    .first()
                )
        except Exception:
            profile = None

        # 🔹 Final data
        if profile:
            item = profile

            # ✅ Fix profile_photo URL
            if item.get("profile_photo"):
                item["profile_photo"] = request.build_absolute_uri(
                    "/media/" + str(item["profile_photo"])
                )

        else:
            item = (
                Users.objects.filter(id=user_obj.id)
                .values("id", "full_name", "email", "contact", "type", "created_at")
                .first()
            )

        if not item:
            return Response(
                {"status": False, "message": "Profile not found"}, status=404
            )

        # 🔹 Convert datetime to string
        for k, v in list(item.items()):
            if hasattr(v, "isoformat"):
                try:
                    item[k] = v.isoformat()
                except:
                    pass

        return Response({"status": True, "profile": item}, status=200)

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET", "POST"])
def employee_list_create_api(request):
    try:
        from accounts.models import EmpMaster
        from datetime import datetime as _dt

        if request.method == "POST":
            data = request.data or request.POST

            emp_id = data.get("emp_id")
            if not emp_id:
                return Response(
                    {"status": False, "message": "emp_id required"}, status=400
                )

            if EmpMaster.objects.filter(emp_id=str(emp_id)).exists():
                return Response(
                    {"status": False, "message": "emp_id already exists"}, status=409
                )

            allowed = [
                "emp_id",
                "full_name",
                "dob",
                "gender",
                "email",
                "contact",
                "present_addr",
                "perm_addr",
                "join_date",
                "end_date",
                "emp_type",
                "check_in",
                "check_out",
                "longitude",
                "latitude",
                "dept",
                "desig",
                "salary_type",
                "salary_amt",
                "full_abs_fine",
                "half_abd_fine",
                "yearly_leaves",
                "bank",
                "bank_name",
                "branch_name",
                "account_name",
                "account_no",
                "ifsc_code",
                "entried_by",
                "total_yearly_leaves",
                "profile_photo",
                "blood_group",
                "father_name",
                "emergency_contact",
            ]

            payload = {}
            for k in allowed:
                if k in data:
                    payload[k] = data.get(k)

            for field in ["dob", "join_date", "end_date"]:
                if payload.get(field):
                    try:
                        payload[field] = _dt.fromisoformat(str(payload[field]))
                    except:
                        pass

            payload.setdefault("emergency_contact", "0")
            payload.setdefault("salary_amt", "")
            payload.setdefault(
                "account_no", data.get("account_no") or data.get("account_number") or ""
            )

            emp = EmpMaster.objects.create(**payload)

            return Response(
                {"status": True, "message": "Employee created", "emp_id": emp.emp_id},
                status=201,
            )

        qs = EmpMaster.objects.all()

        emp_id = request.GET.get("emp_id")
        contact = request.GET.get("contact")
        search = request.GET.get("q")

        if emp_id:
            qs = qs.filter(emp_id=str(emp_id))
        if contact:
            qs = qs.filter(contact__icontains=contact)
        if search:
            qs = qs.filter(full_name__icontains=search)

        employees = list(qs.values())

        return Response({"status": True, "employees": employees}, status=200)

    except Exception as e:
        print("ERROR IN EMPLOYEE API:", str(e))
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET"])
def employee_list_api(request):
    try:
        from accounts.models import EmpMaster

        # 🔥 Only fetch all employees
        employees = list(
            EmpMaster.objects.all().values(
                "emp_id",
                "full_name",
                "email",
                "contact",
                "dept",
                "desig",
                "join_date",
                "dob",
                "blood_group",
                "father_name",
                "emergency_contact",
                "bank_name",
                "branch_name",
                "account_no",
                "ifsc_code",
            )
        )

        return Response({"status": True, "employees": employees}, status=200)

    except Exception as e:
        print("ERROR:", str(e))
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def employee_detail_api(request, emp_id):
    """Retrieve, update or delete an employee by `emp_id`."""
    try:
        from accounts.models import EmpMaster
        from datetime import datetime as _dt

        em = EmpMaster.objects.filter(emp_id=str(emp_id)).first()
        if not em:
            return Response(
                {"status": False, "message": "Employee not found"}, status=404
            )

        if request.method == "GET":
            data = dict()
            for k, v in em.__dict__.items():
                if k.startswith("_"):
                    continue
                if hasattr(v, "isoformat"):
                    try:
                        data[k] = v.isoformat()
                    except:
                        data[k] = v
                else:
                    data[k] = v
            return Response({"status": True, "employee": data}, status=200)

        if request.method in ("PUT", "PATCH"):
            data = request.data or request.POST
            changed = False
            allowed = [
                "full_name",
                "dob",
                "gender",
                "email",
                "contact",
                "present_addr",
                "perm_addr",
                "join_date",
                "end_date",
                "emp_type",
                "check_in",
                "check_out",
                "longitude",
                "latitude",
                "dept",
                "desig",
                "salary_type",
                "salary_amt",
                "full_abs_fine",
                "half_abd_fine",
                "yearly_leaves",
                "bank",
                "bank_name",
                "branch_name",
                "account_name",
                "account_no",
                "ifsc_code",
                "entried_by",
                "total_yearly_leaves",
                "profile_photo",
                "blood_group",
                "father_name",
                "emergency_contact",
            ]

            for k in allowed:
                if k in data:
                    val = data.get(k)
                    if k in ("dob", "join_date", "end_date") and val:
                        try:
                            val = _dt.fromisoformat(str(val))
                        except:
                            pass
                    setattr(em, k, val)
                    changed = True

            if changed:
                em.save()
            return Response(
                {"status": True, "message": "Employee updated", "emp_id": em.emp_id},
                status=200,
            )

        # DELETE
        em.delete()
        return Response({"status": True, "message": "Employee deleted"}, status=200)

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["POST"])
def employee_create_admin_api(request):
    # employee_create_admin_api(request)
    # Creates an employee record directly (admin only).
    # - Creates `EmpMaster` (with safe defaults for non-null fields).
    # - Creates a legacy `Users` row and a Django auth `User` when possible.
    # Required: `emp_id` in request data.
    # Optional: `full_name`, `contact`, `email`, `password`, `dob` (ISO), `join_date` (ISO),
    #           `dept`, `desig`, `account_no`, and other EmpMaster fields.
    # Returns: 201 on success with created `emp_id`, 400 if missing `emp_id`, 409 if already exists.
    try:
        from accounts.models import EmpMaster, Users

        data = request.data or request.POST
        emp_id = data.get("emp_id")
        if not emp_id:
            return Response({"status": False, "message": "emp_id required"}, status=400)

        # prevent duplicate
        if (
            EmpMaster.objects.filter(emp_id=str(emp_id)).exists()
            or Users.objects.filter(contact=data.get("contact") or "").exists()
            or Users.objects.filter(email=data.get("email") or "").exists()
        ):
            return Response(
                {"status": False, "message": "Employee or user already exists"},
                status=409,
            )

        # build emp with safe defaults (to avoid NOT NULL DB errors)
        emp = EmpMaster()
        emp.emp_id = str(emp_id)
        emp.full_name = data.get("full_name") or ""
        emp.contact = data.get("contact") or ""
        emp.email = data.get("email") or ""
        dob = data.get("dob")
        if dob:
            try:
                emp.dob = _dt.fromisoformat(str(dob)).date()
            except:
                pass
        emp.gender = data.get("gender") or ""
        emp.present_addr = data.get("present_addr") or data.get("address") or ""
        emp.perm_addr = data.get("perm_addr") or ""
        join_date = data.get("join_date")
        if join_date:
            try:
                emp.join_date = _dt.fromisoformat(str(join_date)).date()
            except:
                pass
        emp.emp_type = data.get("emp_type") or ""
        emp.dept = data.get("dept") or ""
        emp.desig = data.get("desig") or ""
        emp.salary_type = data.get("salary_type") or ""
        emp.salary_amt = data.get("salary_amt") or ""
        emp.full_abs_fine = data.get("full_abs_fine") or None
        emp.half_abd_fine = data.get("half_abd_fine") or None
        emp.yearly_leaves = data.get("yearly_leaves") or None
        emp.bank = data.get("bank") or ""
        emp.bank_name = data.get("bank_name") or ""
        emp.branch_name = data.get("branch_name") or ""
        emp.account_name = data.get("account_name") or ""
        emp.account_no = data.get("account_no") or data.get("account_number") or ""
        emp.ifsc_code = data.get("ifsc_code") or ""
        emp.entried_by = data.get("entried_by") or "admin"
        emp.total_yearly_leaves = data.get("total_yearly_leaves") or "0"
        emp.profile_photo = data.get("profile_photo") or ""
        emp.blood_group = data.get("blood_group") or ""
        emp.father_name = data.get("father_name") or ""
        emp.emergency_contact = data.get("emergency_contact") or "0"

        emp.save()

        # create legacy Users row
        try:
            Users.objects.create(
                full_name=emp.full_name,
                email=emp.email,
                password=(data.get("password") or ""),
                contact=emp.contact,
                type=2,
            )
        except Exception:
            pass

        # create Django auth user if not exists
        try:
            if emp.contact:
                if not AuthUser.objects.filter(username=emp.contact).exists():
                    pwd = (
                        data.get("password") or AuthUser.objects.make_random_password()
                    )
                    au = AuthUser.objects.create_user(
                        username=emp.contact,
                        email=emp.email,
                        password=pwd,
                        first_name=(
                            emp.full_name.split(" ", 1)[0] if emp.full_name else ""
                        ),
                    )
                    try:
                        au.groups.add(Group.objects.get(name="employee"))
                    except Exception:
                        pass
        except Exception:
            pass

        return Response(
            {
                "status": True,
                "message": "Employee created by admin",
                "emp_id": emp.emp_id,
            },
            status=201,
        )

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET"])
def emp_temp_list_api(request):
    """List pending registration requests (EmpTemp). Admin-only intended."""
    try:
        from accounts.models import EmpTemp
        from accounts.models import EmpMaster, Users

        # Only show pending registrations that do not already have an EmpMaster or Users record
        qs = EmpTemp.objects.filter(status__iexact="PENDING")
        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status__iexact=status_filter)

        # exclude any requests where an account already exists
        filtered = []
        for r in qs.order_by("-created_at").values():
            contact = r.get("contact")
            email = r.get("email")
            exists = False
            if contact and EmpMaster.objects.filter(contact=contact).exists():
                exists = True
            if contact and Users.objects.filter(contact=contact).exists():
                exists = True
            if email and Users.objects.filter(email=email).exists():
                exists = True
            if not exists:
                filtered.append(r)
        # make datetimes JSON-serializable
        for r in filtered:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    try:
                        r[k] = v.isoformat()
                    except:
                        pass

        return Response({"status": True, "requests": filtered}, status=200)
    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["GET"])
def emp_temp_detail_api(request, id):
    try:
        from accounts.models import EmpTemp

        emp = EmpTemp.objects.get(id=id)

        data = emp.__dict__
        data.pop("_state", None)

        # convert datetime
        for k, v in data.items():
            if hasattr(v, "isoformat"):
                data[k] = v.isoformat()

        return Response({"status": True, "data": data}, status=200)

    except EmpTemp.DoesNotExist:
        return Response({"status": False, "message": "Not found"}, status=404)

    except Exception as e:
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["POST"])
def emp_temp_approve_api(request, id):
    try:
        from accounts.models import EmpTemp, EmpMaster, Users
        from django.db.models import Max, IntegerField
        from django.db.models.functions import Cast

        req = EmpTemp.objects.get(id=id)
        data = request.data

        if req.status != "PENDING":
            return Response(
                {"status": False, "message": "Already processed"}, status=400
            )

        max_id = (
            EmpMaster.objects.aggregate(max_id=Max(Cast("emp_id", IntegerField())))[
                "max_id"
            ]
            or 0
        )

        new_emp_id = str(max_id + 1)

        emp = EmpMaster.objects.create(
            emp_id=new_emp_id,
            full_name=data.get("full_name") or "",
            dob=data.get("dob") or "",
            gender=data.get("gender") or "",
            contact=data.get("contact") or "",
            email=data.get("email") or "",
            salary_amt=int(data.get("salary_amt") or 0),
            account_no=data.get("account_number") or "",
            emergency_contact=data.get("emergency_contact") or "0",
        )

        Users.objects.create(
            full_name=data.get("full_name"),
            email=data.get("email"),
            password=data.get("password"),
            contact=data.get("contact"),
            type=2,
        )

        req.status = "APPROVED"
        req.save()

        return Response({"status": True, "emp_id": emp.emp_id})

    except Exception as e:
        print("ERROR:", str(e))
        return Response({"status": False, "error": str(e)}, status=500)


@api_view(["POST"])
def emp_temp_reject_api(request, id):
    try:
        from accounts.models import EmpTemp

        req = EmpTemp.objects.get(id=id)

        if req.status != "PENDING":
            return Response(
                {"status": False, "message": "Already processed"}, status=400
            )

        req.status = "REJECTED"
        req.save()

        return Response({"status": True, "message": "Employee Rejected"}, status=200)

    except EmpTemp.DoesNotExist:
        return Response({"status": False, "message": "Request not found"}, status=404)

    except Exception as e:
        print("REJECT ERROR:", str(e))  # 🔥 debug
        return Response(
            {"status": False, "message": "Server error", "error": str(e)}, status=500
        )


@api_view(["POST"])
def emp_temp_reject_api(request, id):
    try:
        from accounts.models import EmpTemp

        req = EmpTemp.objects.get(id=id)

        if req.status != "PENDING":
            return Response(
                {"status": False, "message": "Already processed"}, status=400
            )

        req.status = "REJECTED"
        req.save()

        return Response({"status": True, "message": "Employee Rejected"})

    except EmpTemp.DoesNotExist:
        return Response({"status": False, "message": "Request not found"}, status=404)

    except Exception as e:
        print("REJECT ERROR:", str(e))
        return Response({"status": False, "error": str(e)}, status=500)


@api_view(["GET"])
def upcoming_birthdays_api(request):
    try:
        from accounts.models import EmpMaster

        today = datetime.today()
        today_m, today_d = today.month, today.day

        three_months_later = today + timedelta(days=90)
        end_m, end_d = three_months_later.month, three_months_later.day

        qs = EmpMaster.objects.exclude(dob__isnull=True).annotate(
            month=ExtractMonth("dob"), day=ExtractDay("dob")
        )

        if (end_m, end_d) < (today_m, today_d):
            employees = qs.filter(
                Q(month__gt=today_m)
                | Q(month=today_m, day__gte=today_d)
                | Q(month__lt=end_m)
                | Q(month=end_m, day__lte=end_d)
            )
        else:
            employees = qs.filter(
                Q(month__gt=today_m, month__lt=end_m)
                | Q(month=today_m, day__gte=today_d)
                | Q(month=end_m, day__lte=end_d)
            )

        employees = employees.values("emp_id", "full_name", "dob")

        return Response({"status": True, "birthdays": list(employees)})

    except Exception as e:
        print("BIRTHDAY API ERROR:", str(e))
        return Response({"status": False, "error": str(e)}, status=500)
