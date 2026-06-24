from django.db import models




class AttendanceMaster(models.Model):
    emp_id = models.IntegerField()
    full_name = models.CharField(max_length=255)
    check_in = models.TimeField()
    check_out = models.TimeField(blank=True, null=True)
    worked_hours = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True
    )
    worked_day = models.CharField(max_length=20, blank=True, null=True)
    att_date = models.DateField()
    photo = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.CharField(max_length=255)
    longitude = models.CharField(max_length=255)
    out_photo = models.CharField(max_length=255, blank=True, null=True)
    out_lati = models.CharField(max_length=250)
    out_long = models.CharField(max_length=250)
    attendance_status = models.CharField(max_length=250)
    is_paid = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    

    class Meta:
        managed = False
        db_table = "attendance_master"


class AttendanceReq(models.Model):
    emp_id = models.CharField(max_length=50)
    reg_date = models.DateField()
    full_name = models.CharField(max_length=100)
    reason = models.TextField()
    attachment = models.CharField(max_length=250)
    check_in = models.TimeField()
    check_out = models.TimeField()
    approval_status = models.CharField(max_length=250)
    status = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "attendance_req"


class DeptMaster(models.Model):
    dept_name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = "dept_master"

    def __str__(self):
        return self.dept_name


class DesigMaster(models.Model):
    dept_name = models.CharField(max_length=255)
    desig_name = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "desig_master"

    def __str__(self):
        return self.desig_name


class EmpItemMaster(models.Model):
    emp_id = models.CharField(max_length=255)
    item_name = models.CharField(max_length=255, blank=True, null=True)
    item_amt = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    item_amt_type = models.CharField(max_length=50, blank=True, null=True)
    item_type = models.CharField(max_length=50, blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "emp_item_master"


class EmpMaster(models.Model):
    emp_id = models.CharField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    email = models.CharField(max_length=255, blank=True, null=True)
    contact = models.CharField(max_length=20, blank=True, null=True)
    present_addr = models.TextField(blank=True, null=True)
    perm_addr = models.TextField(blank=True, null=True)
    join_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    emp_type = models.CharField(max_length=50, blank=True, null=True)
    check_in = models.TimeField(blank=True, null=True)
    check_out = models.TimeField(blank=True, null=True)
    longitude = models.DecimalField(
        max_digits=10, decimal_places=8, blank=True, null=True
    )
    latitude = models.DecimalField(
        max_digits=11, decimal_places=8, blank=True, null=True
    )
    dept = models.CharField(max_length=255, blank=True, null=True)
    desig = models.CharField(max_length=255, blank=True, null=True)
    salary_type = models.CharField(max_length=50, blank=True, null=True)
    salary_amt = models.CharField(max_length=255)
    full_abs_fine = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    half_abd_fine = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    yearly_leaves = models.IntegerField(blank=True, null=True)
    bank = models.CharField(max_length=255, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    branch_name = models.CharField(max_length=255, blank=True, null=True)
    account_name = models.CharField(max_length=255)
    account_no = models.CharField(max_length=50, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    entried_by = models.CharField(max_length=255, blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    total_yearly_leaves = models.CharField(max_length=250)
    profile_photo = models.CharField(max_length=250)
    blood_group = models.CharField(max_length=250)
    father_name = models.CharField(max_length=250)
    emergency_contact = models.CharField(max_length=15, blank=True, null=True)
    

    class Meta:
        managed = False
        db_table = "emp_master"

    def __str__(self):
        return self.full_name or self.emp_id


class EmpTemp(models.Model):
    full_name = models.CharField(max_length=150)
    contact = models.CharField(unique=True, max_length=15)
    email = models.CharField(unique=True, max_length=150)
    password = models.CharField(max_length=255)
    dob = models.DateField()
    gender = models.CharField(max_length=50)
    address = models.TextField(blank=True, null=True)
    father_name = models.CharField(max_length=150, blank=True, null=True)
    emergency_contact = models.CharField(max_length=15, blank=True, null=True)
    religion = models.CharField(max_length=50, blank=True, null=True)
    caste = models.CharField(max_length=50, blank=True, null=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    qualification = models.CharField(max_length=100, blank=True, null=True)
    work = models.CharField(max_length=150, blank=True, null=True)
    experience = models.CharField(max_length=20, blank=True, null=True)
    bank = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=150, blank=True, null=True)
    branch_name = models.CharField(max_length=150, blank=True, null=True)
    account_name = models.CharField(max_length=150, blank=True, null=True)
    account_number = models.CharField(max_length=30, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(
        max_length=8, default="PENDING"
    )  # PENDING, APPROVED, REJECTED
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "emp_temp"

    def __str__(self):
        return self.full_name


class Events(models.Model):
    event_title = models.CharField(max_length=255)
    event_desc = models.TextField()
    event_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "events"

    def __str__(self):
        return self.event_title


class HolidayMaster(models.Model):
    holiday_tital = models.CharField(max_length=255)
    holiday_date = models.DateField()

    class Meta:
        managed = False
        db_table = "holiday_master"

    def __str__(self):
        return self.holiday_tital


class LeaveMaster(models.Model):
    leave_type = models.CharField(unique=True, max_length=100)
    description = models.TextField(blank=True, null=True)
    is_paid = models.IntegerField(default=1, blank=True, null=True)
    allow_half_day = models.IntegerField(default=0, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "leave_master"

    def __str__(self):
        return self.leave_type


class LeaveRequest(models.Model):
    emp_id = models.IntegerField()
    full_name = models.CharField(max_length=255, blank=True, null=True)
    leave_type = models.CharField(max_length=255, blank=True, null=True)
    leave_duration = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    leave_status = models.IntegerField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    applied_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    total_leaves = models.IntegerField(default=0)
    yearly_leaves = models.IntegerField(default=0)
    is_paid = models.IntegerField()

    class Meta:
        managed = False
        db_table = "leave_request"


class LogoMaster(models.Model):
    image_name = models.CharField(max_length=250)
    image_path = models.CharField(max_length=250)
    created_at = models.DateField()

    class Meta:
        managed = False
        db_table = "logo_master"


class SystemSettings(models.Model):
    name = models.TextField()
    email = models.CharField(max_length=200)
    contact = models.CharField(max_length=20)
    address = models.TextField()
    cover_img = models.TextField()

    class Meta:
        managed = False
        db_table = "system_settings"


class TitleMaster(models.Model):
    title_update = models.CharField(max_length=250)
    created_at = models.DateField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "title_master"


class Users(models.Model):
    full_name = models.CharField(max_length=200)
    email = models.CharField(max_length=200)
    password = models.TextField()
    type = models.IntegerField(
        default=2
    )  # 1=Admin, 2=Employee, 3=Account
    contact = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self):
        return self.full_name


class ClientVisitor(models.Model):
    """Records client / visitor meetings added by field employees."""

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="client_visitors",
        db_column="user_id",
    )
    emp_id = models.CharField(max_length=255, blank=True, null=True)
    emp_name = models.CharField(max_length=255, blank=True, null=True)
    client_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=500, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    visit_date = models.DateField()
    photo = models.ImageField(upload_to="visitor_photos/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "client_visitor"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client_name} — {self.emp_name or self.user.username}"


class EmployeeLocationTracking(models.Model):
    """Stores GPS location updates for employees during their work session."""

    user_id = models.IntegerField()
    emp_id = models.CharField(max_length=255, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.DecimalField(max_digits=11, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    timestamp = models.DateTimeField(auto_now_add=True)
    session_date = models.DateField(blank=True, null=True)
    is_checkin_point = models.BooleanField(default=False)

    class Meta:
        db_table = "employee_location_tracking"
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.full_name or self.emp_id} @ {self.timestamp}"
