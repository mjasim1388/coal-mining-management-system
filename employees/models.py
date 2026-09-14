from django.db import models


class Employee(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('On Leave', 'On Leave'),
    ]

    SHIFT_CHOICES = [
        ('Morning', 'Morning'),
        ('Evening', 'Evening'),
        ('Night', 'Night'),
    ]

    employee_code = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    father_name = models.CharField(max_length=100, blank=True)
    cnic = models.CharField(max_length=15, unique=True, help_text="e.g. 12345-1234567-1")
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='Morning')
    date_of_joining = models.DateField()
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    photo = models.ImageField(upload_to='employees/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approval_status = models.CharField(max_length=20, default='Approved')
    added_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='employees_added')

    class Meta:
        ordering = ['employee_code']

    def __str__(self):
        return f"{self.employee_code} - {self.first_name} {self.last_name}"


class Mine(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Suspended', 'Suspended'),
        ('Closed', 'Closed'),
    ]

    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200)
    license_no = models.CharField(max_length=50, blank=True)
    manager_name = models.CharField(max_length=100, blank=True)
    reserves_tons = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Estimated reserves in tons")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductionRecord(models.Model):
    COAL_TYPE_CHOICES = [
        ('Anthracite', 'Anthracite'),
        ('Bituminous', 'Bituminous'),
        ('Sub-bituminous', 'Sub-bituminous'),
        ('Lignite', 'Lignite'),
    ]

    SHIFT_CHOICES = [
        ('Morning', 'Morning'),
        ('Evening', 'Evening'),
        ('Night', 'Night'),
    ]

    mine = models.ForeignKey(Mine, on_delete=models.CASCADE, related_name='productions')
    date = models.DateField()
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='Morning')
    coal_type = models.CharField(max_length=30, choices=COAL_TYPE_CHOICES, default='Bituminous')
    quantity_tons = models.DecimalField(max_digits=12, decimal_places=2, help_text="Coal produced in tons")
    overburden_removed = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Waste removed in tons")
    supervisor = models.CharField(max_length=100, blank=True)
    workers_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'shift']

    def __str__(self):
        return f"{self.mine.name} - {self.date} ({self.shift})"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Leave', 'Leave'),
        ('Half Day', 'Half Day'),
    ]

    SHIFT_CHOICES = [
        ('Morning', 'Morning'),
        ('Evening', 'Evening'),
        ('Night', 'Night'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='Morning')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Present')
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    leave_reason = models.TextField(blank=True, help_text="Reason if status is Leave")
    auto_check_in = models.BooleanField(default=True, help_text="Auto-filled on save")
    auto_check_out = models.BooleanField(default=False)
    photo = models.ImageField(upload_to='attendance/', blank=True, null=True, help_text="Real-time photo at check-in")
    photo_out = models.ImageField(upload_to='attendance/out/', blank=True, null=True, help_text="Photo at check-out")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'employee__employee_code']
        unique_together = ('employee', 'date', 'shift')

    def __str__(self):
        return f"{self.employee.employee_code} - {self.date} ({self.shift})"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        now = timezone.localtime()

        if self.status == 'Present':
            if self.auto_check_in and not self.check_in:
                self.check_in = now.time().replace(second=0, microsecond=0)
            if self.auto_check_out and not self.check_out:
                self.check_out = now.time().replace(second=0, microsecond=0)

        if self.status == 'Half Day' and not self.check_in:
            self.check_in = now.time().replace(second=0, microsecond=0)

        super().save(*args, **kwargs)


class InventoryItem(models.Model):
    CATEGORY_CHOICES = [
        ('Spare Part', 'Spare Part'),
        ('Fuel', 'Fuel'),
        ('Explosive', 'Explosive'),
        ('Safety Gear', 'Safety Gear'),
        ('Consumable', 'Consumable'),
        ('Other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='Spare Part')
    unit = models.CharField(max_length=20, default='pcs', help_text="e.g. pcs, kg, liter, box")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                        help_text="Alert when quantity falls below this")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.CharField(max_length=100, blank=True, help_text="Storage location")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approval_status = models.CharField(max_length=20, default='Approved')
    added_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='inventory_added')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level


class StockTransaction(models.Model):
    TYPE_CHOICES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    transaction_type = models.CharField(max_length=5, choices=TYPE_CHOICES, default='IN')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200, blank=True, help_text="e.g. purchase, issued to mine, damaged")
    handled_by = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.item.name} - {self.transaction_type} {self.quantity}"


class Payroll(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Paid Pending', 'Paid (Awaiting Approval)'),
        ('Paid', 'Paid'),
    ]

    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    present_days = models.IntegerField(default=0)
    absent_days = models.IntegerField(default=0)
    leave_days = models.IntegerField(default=0)
    half_days = models.IntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls_created')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls_paid_requested')
    received_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    employee_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    signed_slip_photo = models.ImageField(upload_to='payroll/slips/', blank=True, null=True,
                                          help_text="Photo of signed/thumbprinted salary slip")
    paid_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='payrolls_paid')
    confirmation_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', '-month', 'employee__employee_code']
        unique_together = ('employee', 'month', 'year')

    def __str__(self):
        return f"{self.employee.employee_code} - {self.month}/{self.year}"

    def save(self, *args, **kwargs):
        self.net_salary = (
            self.basic_salary + self.overtime_amount
            + self.allowances - self.deductions
        )
        super().save(*args, **kwargs)


class Customer(models.Model):
    name = models.CharField(max_length=150, unique=True)
    company = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    ntn = models.CharField(max_length=30, blank=True, help_text="Tax number")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Sale(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('Unpaid', 'Unpaid'),
        ('Partial', 'Partial'),
        ('Paid', 'Paid'),
    ]

    COAL_TYPE_CHOICES = [
        ('Anthracite', 'Anthracite'),
        ('Bituminous', 'Bituminous'),
        ('Sub-bituminous', 'Sub-bituminous'),
        ('Lignite', 'Lignite'),
    ]

    invoice_no = models.CharField(max_length=30, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='sales')
    mine = models.ForeignKey(Mine, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    date = models.DateField()
    coal_type = models.CharField(max_length=30, choices=COAL_TYPE_CHOICES, default='Bituminous')
    quantity_tons = models.DecimalField(max_digits=12, decimal_places=2)
    price_per_ton = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    truck_no = models.CharField(max_length=50, blank=True)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    dispatch_date = models.DateField(null=True, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Unpaid')
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.invoice_no} - {self.customer.name}"

    @property
    def balance(self):
        return (self.total_amount or 0) - (self.amount_paid or 0)

    def save(self, *args, **kwargs):
        self.total_amount = (self.quantity_tons or 0) * (self.price_per_ton or 0)
        super().save(*args, **kwargs)


class Notification(models.Model):
    STATUS_CHOICES = [
        ('Info', 'Info'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=300)
    link = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Info')
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"


class ApprovalLog(models.Model):
    OBJECT_TYPES = [
        ('Employee', 'Employee'),
        ('InventoryItem', 'Inventory Item'),
        ('Payroll', 'Payroll'),
        ('PayrollPaid', 'Payroll Marked Paid'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    object_type = models.CharField(max_length=30, choices=OBJECT_TYPES)
    object_id = models.IntegerField()
    object_label = models.CharField(max_length=200, blank=True)
    requested_by = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='approval_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    reviewed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approval_reviews')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.object_type} #{self.object_id} - {self.status}"


class Equipment(models.Model):
    TYPE_CHOICES = [
        ('Excavator', 'Excavator'),
        ('Loader', 'Loader'),
        ('Truck', 'Truck'),
        ('Drill', 'Drill'),
        ('Conveyor', 'Conveyor'),
        ('Generator', 'Generator'),
        ('Pump', 'Pump'),
        ('Compressor', 'Compressor'),
        ('Vehicle', 'Vehicle'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('Working', 'Working'),
        ('Under Maintenance', 'Under Maintenance'),
        ('Out of Service', 'Out of Service'),
    ]

    FUEL_CHOICES = [
        ('Diesel', 'Diesel'),
        ('Petrol', 'Petrol'),
        ('Electric', 'Electric'),
        ('None', 'None'),
    ]

    equipment_code = models.CharField(max_length=30, unique=True, blank=True,
                                      help_text="Leave blank to auto-generate from name")
    name = models.CharField(max_length=100)
    equipment_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='Other')
    model_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    mine = models.ForeignKey(Mine, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='equipment')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Working')
    fuel_type = models.CharField(max_length=20, choices=FUEL_CHOICES, default='Diesel')
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['equipment_code']
        verbose_name_plural = 'Equipment'

    def __str__(self):
        return f"{self.equipment_code} - {self.name}"

    @property
    def total_maintenance_cost(self):
        return sum(m.cost for m in self.maintenance_logs.all())

    def save(self, *args, **kwargs):
        if not self.equipment_code:
            letters = ''.join(c for c in self.name.upper() if c.isalpha())
            prefix = letters[:3] if len(letters) >= 3 else letters.ljust(3, 'X')
            existing = Equipment.objects.filter(equipment_code__startswith=f'{prefix}-')
            max_num = 0
            for eq in existing:
                try:
                    num = int(eq.equipment_code.split('-')[-1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass
            self.equipment_code = f'{prefix}-{max_num + 1:03d}'
        super().save(*args, **kwargs)


class MaintenanceLog(models.Model):
    TYPE_CHOICES = [
        ('Routine', 'Routine Service'),
        ('Repair', 'Repair'),
        ('Inspection', 'Inspection'),
        ('Overhaul', 'Overhaul'),
        ('Fuel Top-up', 'Fuel Top-up'),
    ]

    STATUS_CHOICES = [
        ('Completed', 'Completed'),
        ('In Progress', 'In Progress'),
        ('Pending Parts', 'Pending Parts'),
    ]

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='maintenance_logs')
    date = models.DateField()
    maintenance_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='Routine')
    description = models.TextField()
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performed_by = models.CharField(max_length=150, blank=True,
                                    help_text="Internal staff name or contractor name")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Completed')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.equipment.equipment_code} - {self.maintenance_type} on {self.date}"