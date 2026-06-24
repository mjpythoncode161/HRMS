from django.forms import ModelForm
from .models import DeptMaster, DesigMaster, EmpMaster, AttendanceMaster
from django import forms


class departmentForm(ModelForm):
    class Meta:
        model = DeptMaster
        fields = "__all__"


class designationForm(ModelForm):
    class Meta:
        model = DesigMaster
        fields = "__all__"


class employeeForm(ModelForm):
    class Meta:
        model = EmpMaster
        fields = "__all__"


class AttendanceForm(ModelForm):
    class Meta:
        model = AttendanceMaster
        fields = [
            "emp_id",
            "att_date",
            "check_in",
            "check_out",
            "attendance_status",
            "worked_day",
            "latitude",
            "longitude",
        ]
        widgets = {
            "att_date": forms.DateInput(attrs={"type": "date"}),
            "check_in": forms.TimeInput(attrs={"type": "time"}),
            "check_out": forms.TimeInput(attrs={"type": "time"}),
            "latitude": forms.TextInput(
                attrs={"readonly": True, "placeholder": "0.000000"}
            ),
            "longitude": forms.TextInput(
                attrs={"readonly": True, "placeholder": "0.000000"}
            ),
        }
