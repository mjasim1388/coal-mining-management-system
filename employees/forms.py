from django import forms

from .models import (
    Attendance,
    Customer,
    Employee,
    Equipment,
    InventoryItem,
    MaintenanceLog,
    Mine,
    Payroll,
    ProductionRecord,
    Sale,
    StockTransaction,
)


def clear_zeros(form, field_names):
    """For new records, show empty fields instead of '0' defaults.

    Django stores model field defaults in form.fields[name].initial,
    not form.initial — so we need to clear BOTH.
    """
    if form.instance.pk:
        return  # Don't touch when editing existing records
    for name in field_names:
        if name in form.fields:
            # Clear the field's own initial (this is where model defaults land)
            form.fields[name].initial = ''
        # Also clear form.initial for consistency
        form.initial[name] = ''


class EmployeeForm(forms.ModelForm):
    employee_code = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Leave blank to auto-generate',
        })
    )

    class Meta:
        model = Employee
        fields = [
            'employee_code', 'first_name', 'last_name', 'father_name',
            'cnic', 'date_of_birth', 'phone', 'address',
            'designation', 'department', 'shift',
            'date_of_joining', 'salary', 'status', 'photo', 'notes',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Father's name"}),
            'cnic': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '12345-1234567-1',
                'maxlength': '15',
                'inputmode': 'numeric',
                'id': 'id_cnic',
            }),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 03001234567'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Operator'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Mining'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 35000'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['salary'].required = True          # ← make required
        self.fields['shift'].required = False
        self.fields['status'].required = False
        self.fields['date_of_birth'].required = False
        self.fields['father_name'].required = False
        self.fields['phone'].required = False
        self.fields['address'].required = False
        self.fields['notes'].required = False
        self.fields['photo'].required = False
        self.fields['cnic'].help_text = 'Format: 12345-1234567-1 (dashes added automatically)'
        clear_zeros(self, ['salary'])                  # ← keep this — shows empty placeholder


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
            'reserves_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 500000'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reserves_tons'].required = False
        clear_zeros(self, ['reserves_tons'])


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
            'quantity_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 250'}),
            'overburden_removed': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 100'}),
            'supervisor': forms.TextInput(attrs={'class': 'form-control'}),
            'workers_count': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 15'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['overburden_removed'].required = False
        self.fields['workers_count'].required = False
        clear_zeros(self, ['quantity_tons', 'overburden_removed', 'workers_count'])
        
    def clean(self):
        from decimal import Decimal
        cleaned_data = super().clean()
        
        if cleaned_data.get('overburden_removed') in (None, ''):
            cleaned_data['overburden_removed'] = Decimal('0')
            
        if cleaned_data.get('workers_count') in (None, ''):
            cleaned_data['workers_count'] = 0
            
        return cleaned_data

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
            'overtime_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'leave_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'id': 'id_leave_reason'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'id': 'id_photo'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clear_zeros(self, ['overtime_hours'])


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'category', 'unit', 'quantity', 'reorder_level',
                  'unit_price', 'location', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'pcs, kg, liter...'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clear_zeros(self, ['quantity', 'reorder_level', 'unit_price'])


class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['item', 'date', 'transaction_type', 'quantity',
                  'reason', 'handled_by', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'handled_by': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clear_zeros(self, ['quantity'])


class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'year', 'basic_salary',
                  'present_days', 'absent_days', 'leave_days', 'half_days',
                  'overtime_hours', 'overtime_amount', 'allowances',
                  'deductions', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'month': forms.Select(attrs={'class': 'form-control'}),
            'year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'present_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'absent_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'leave_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'half_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'overtime_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'overtime_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'allowances': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'deductions': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clear_zeros(self, [
            'basic_salary', 'present_days', 'absent_days', 'leave_days',
            'half_days', 'overtime_hours', 'overtime_amount',
            'allowances', 'deductions',
        ])

COAL_TYPE_CHOICES = [
    ('', '— Select —'),
    ('Anthracite', 'Anthracite'),
    ('Bituminous', 'Bituminous'),
    ('Sub-bituminous', 'Sub-bituminous'),
    ('Lignite', 'Lignite'),
]
class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'company', 'phone', 'email', 'address', 'ntn',
                  'default_coal_type', 'default_rate', 'default_mine',
                  'default_truck_no', 'default_driver_name', 'default_driver_phone',
                  'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'ntn': forms.TextInput(attrs={'class': 'form-control'}),
            'default_coal_type': forms.Select(attrs={'class': 'form-control'}, choices=COAL_TYPE_CHOICES),
            'default_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 25000'}),
            'default_mine': forms.Select(attrs={'class': 'form-control'}),
            'default_truck_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. TRK-001'}),
            'default_driver_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Driver name'}),
            'default_driver_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Driver phone'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_coal_type'].required = False
        self.fields['default_rate'].required = False
        self.fields['default_mine'].required = False
        self.fields['default_truck_no'].required = False
        self.fields['default_driver_name'].required = False
        self.fields['default_driver_phone'].required = False
class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['customer', 'mine', 'coal_type', 'quantity_tons',
                  'price_per_ton', 'truck_no', 'driver_name', 'driver_phone',
                  'payment_status', 'amount_paid', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'coal_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity_tons': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'required': True, 'placeholder': 'e.g. 50'}),
            'price_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'required': True, 'placeholder': 'e.g. 25000'}),
            'truck_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. TRK-001', 'list': 'truckList', 'autocomplete': 'off'}),
            'driver_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Driver full name', 'list': 'driverList', 'autocomplete': 'off'}),
            'driver_phone': forms.TextInput(attrs={'class': 'form-control', 'list': 'driverPhoneList', 'autocomplete': 'off'}),
            'payment_status': forms.Select(attrs={'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].empty_label = 'Select Customer...'
        clear_zeros(self, ['amount_paid'])
        self.fields['amount_paid'].required = False
    def clean(self):
        from decimal import Decimal
        cleaned_data = super().clean()
        if cleaned_data.get('amount_paid') in (None, ''):
            cleaned_data['amount_paid'] = Decimal('0')
        status = cleaned_data.get('payment_status')
        amount = cleaned_data.get('amount_paid') or 0
        qty = cleaned_data.get('quantity_tons') or 0
        rate = cleaned_data.get('price_per_ton') or 0
        total = qty * rate

        if status == 'Unpaid':
            if amount != 0:
                self.add_error('amount_paid', 'For UNPAID dispatches, Amount Paid should be 0.')
        elif status == 'Paid':
            if amount != total:
                self.add_error('amount_paid', f'For PAID dispatches, Amount Paid must equal the total (PKR {total}).')
        elif status == 'Partial':
            if amount <= 0:
                self.add_error('amount_paid', 'For PARTIAL payment, enter an amount greater than 0.')
            elif amount >= total:
                self.add_error('amount_paid', f'For PARTIAL payment, amount must be less than the total (PKR {total}).')

        return cleaned_data


class EquipmentForm(forms.ModelForm):
    equipment_code = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Leave blank to auto-generate',
        })
    )

    class Meta:
        model = Equipment
        fields = ['equipment_code', 'name', 'equipment_type', 'model_number',
                  'serial_number', 'mine', 'status', 'fuel_type',
                  'purchase_date', 'purchase_cost', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Excavator 1'}),
            'equipment_type': forms.Select(attrs={'class': 'form-control'}),
            'model_number': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'fuel_type': forms.Select(attrs={'class': 'form-control'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 15000000'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_cost'].required = False
        clear_zeros(self, ['purchase_cost'])


class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = ['equipment', 'date', 'maintenance_type', 'description',
                  'cost', 'performed_by', 'status', 'notes']
        widgets = {
            'equipment': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'maintenance_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
            'performed_by': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost'].required = False
        clear_zeros(self, ['cost'])
