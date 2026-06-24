from datetime import date
import os
import uuid

from django.conf import settings

from .models import Users, EmpMaster, SystemSettings, LogoMaster


def _resolve_logo_url(logo=None, company=None):
    if logo is None:
        logo = LogoMaster.objects.order_by("-created_at").first()
    if company is None:
        company = SystemSettings.objects.first()

    if logo and logo.image_path:
        path = logo.image_path.strip()
        if path.startswith(("http://", "https://", "/")):
            return path
        return f"{settings.MEDIA_URL.rstrip('/')}/{path.lstrip('/')}"

    if company and company.cover_img:
        path = company.cover_img.strip()
        if path.startswith(("http://", "https://", "/")):
            return path
        return f"{settings.MEDIA_URL.rstrip('/')}/{path.lstrip('/')}"

    return None


def save_company_logo(uploaded_file):
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".png"

    filename = f"logo_{uuid.uuid4().hex}{ext}"
    rel_path = os.path.join("company", filename).replace("\\", "/")
    abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, "wb+") as dest:
        for chunk in uploaded_file.chunks():
            dest.write(chunk)

    logo = LogoMaster()
    logo.image_name = uploaded_file.name
    logo.image_path = rel_path
    logo.created_at = date.today()
    logo.save()
    return rel_path


def user_approval_status(request):
    user_approved = False
    user_is_employee = False

    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            user_approved = True
            user_is_employee = True
        else:
            # Approved if exists in legacy Users table
            try:
                Users.objects.get(contact=request.user.username)
                user_approved = True
            except Users.DoesNotExist:
                user_approved = False

            # Employee if: (a) in django 'employee' group  OR  (b) contact exists in EmpMaster
            if request.user.groups.filter(name="employee").exists():
                user_is_employee = True
            else:
                try:
                    EmpMaster.objects.get(contact=request.user.username)
                    user_is_employee = True
                except EmpMaster.DoesNotExist:
                    user_is_employee = False

    return {"user_approved": user_approved, "user_is_employee": user_is_employee}


def company_info(request):
    company = SystemSettings.objects.first()
    logo = LogoMaster.objects.order_by("-created_at").first()
    name = (company.name or "").strip() if company else ""

    return {
        "company_settings": company,
        "company": company,
        "company_logo": logo,
        "company_logo_url": _resolve_logo_url(logo, company),
        "system_name": name or "HRMS",
    }
