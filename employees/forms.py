from django import forms
from .models import (Employee, Mine, ProductionRecord, Attendance,
                     InventoryItem, StockTransaction, Payroll,
                     Customer, Sale)

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'employee_code', 'first_name', 'last_name', 'father_name',
            'cnic', 'date_of_birth', 'phone', 'address',
            'designation', 'department', 'shift',
            'date_of_joining', 'salary', 'status', 'photo', 'notes',
        ]
        widgets = {
            'employee_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. EMP001'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'cnic': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345-1234567-1'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class MineForm(forms.ModelForm):
    class Meta:
        model = Mine
        fields = ['name', 'location', 'license_no', 'manager_name',
                  'reserves_tons', 'status', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'license_no': forms.TextInput(attrs={'class': 'form-control'}),
            'manager_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reserves_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionForm(forms.ModelForm):
    class Meta:
        model = ProductionRecord
        fields = ['mine', 'date', 'shift', 'coal_type', 'quantity_tons',
                  'overburden_removed', 'supervisor', 'workers_count', 'notes']
        widgets = {
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'coal_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'overburden_removed': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'supervisor': forms.TextInput(attrs={'class': 'form-control'}),
            'workers_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'shift', 'status',
                  'check_in', 'check_out', 'overtime_hours',
                  'leave_reason', 'photo', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control', 'id': 'id_status'}),
            'check_in': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'check_out': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'overtime_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'leave_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'id': 'id_leave_reason'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'id': 'id_photo'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'category', 'unit', 'quantity', 'reorder_level',
                  'unit_price', 'location', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'pcs, kg, liter...'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['item', 'date', 'transaction_type', 'quantity',
                  'reason', 'handled_by', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'handled_by': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'year', 'basic_salary',
                  'present_days', 'absent_days', 'leave_days', 'half_days',
                  'overtime_hours', 'overtime_amount', 'allowances',
                  'deductions', 'status', 'payment_date', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'month': forms.Select(attrs={'class': 'form-control'}),
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'present_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'absent_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'leave_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'half_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'overtime_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'overtime_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'allowances': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'deductions': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'company', 'phone', 'email', 'address', 'ntn', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'ntn': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['invoice_no', 'customer', 'mine', 'date', 'coal_type',
                  'quantity_tons', 'price_per_ton', 'truck_no', 'driver_name',
                  'driver_phone', 'dispatch_date', 'payment_status',
                  'amount_paid', 'notes']
        widgets = {
            'invoice_no': forms.TextInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-control'}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'coal_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'price_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'truck_no': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_name': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'dispatch_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_status': forms.Select(attrs={'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

         
        