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

    employee_code = models.CharField(max_length=20, unique=True, blank=True,
                                     help_text="Leave blank to auto-generate")
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
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
    related_name='employees_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='employees_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['employee_code']

    def __str__(self):
        return f"{self.employee_code} - {self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.employee_code:
            last = Employee.objects.filter(employee_code__startswith='EMP-').order_by('-employee_code').first()
            if last:
                try:
                    last_num = int(last.employee_code.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0
            self.employee_code = f'EMP-{last_num + 1:04d}'
        super().save(*args, **kwargs)

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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='mines_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='production_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', 'shift']

    def __str__(self):
        return f"{self.mine.name} - {self.date} ({self.shift})"


    def save(self, *args, **kwargs):
        from decimal import Decimal
        is_new = self.pk is None
        old = None
        
        if not is_new:
            old = ProductionRecord.objects.get(pk=self.pk)

        # Calculate how much to add/subtract from the stockpile
        delta = Decimal('0')
        
        if is_new:
            if not self.voided:
                delta = self.quantity_tons
        else:
            if not old.voided and not self.voided:
                delta = self.quantity_tons - old.quantity_tons
            elif not old.voided and self.voided:
                delta = -old.quantity_tons
            elif old.voided and not self.voided:
                delta = self.quantity_tons

        # Handle moving stock between mines/types if edited
        if not is_new and not self.voided and not old.voided:
            if self.mine_id != old.mine_id or self.coal_type != old.coal_type:
                old_pile, _ = CoalStockpile.objects.get_or_create(mine=old.mine, coal_type=old.coal_type)
                old_pile.quantity_tons -= old.quantity_tons
                old_pile.save()
                delta = self.quantity_tons # Add full amount to the new pile

        super().save(*args, **kwargs)

        if delta != 0:
            pile, _ = CoalStockpile.objects.get_or_create(mine=self.mine, coal_type=self.coal_type)
            pile.quantity_tons += delta
            pile.save()
    


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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='attendance_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', 'employee__employee_code']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date', 'shift'],
                condition=models.Q(voided=False),
                name='unique_attendance_active',
            )
        ]

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
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='inventory_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='inventory_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

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

    ISSUED_TO_CHOICES = [
        ('General', 'General / Not specified'),
        ('Equipment', 'Equipment / Machine'),
        ('Employee', 'Employee'),
        ('Mine', 'Mine site'),
        ('Sold', 'Sold'),
        ('Damaged', 'Damaged / Lost'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    transaction_type = models.CharField(max_length=5, choices=TYPE_CHOICES, default='IN')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200, blank=True,
                              help_text="e.g. purchase, issued to mine, damaged")

    # Where the stock went (only used when type = OUT)
    issued_to_type = models.CharField(max_length=20, choices=ISSUED_TO_CHOICES, default='General')
    issued_to_equipment = models.ForeignKey('Equipment', on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='stock_issues')
    issued_to_employee = models.ForeignKey('Employee', on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='stock_received')
    issued_to_mine = models.ForeignKey('Mine', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='stock_received')

    handled_by = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='stock_transactions_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.item.name} - {self.transaction_type} {self.quantity}"

    @property
    def issued_to_display(self):
        """Human-readable 'issued to' value."""
        if self.transaction_type == 'IN':
            return '—'
        if self.issued_to_type == 'Equipment' and self.issued_to_equipment:
            return self.issued_to_equipment.name
        if self.issued_to_type == 'Employee' and self.issued_to_employee:
            return f'{self.issued_to_employee.first_name} {self.issued_to_employee.last_name}'
        if self.issued_to_type == 'Mine' and self.issued_to_mine:
            return self.issued_to_mine.name
        return self.issued_to_type

class Payroll(models.Model):
    STATUS_CHOICES = [
        ('Approved', 'Ready to Pay'),
        ('Paid', 'Paid'),
        # ---- Legacy (old records only, never set going forward) ----
        ('Pending', 'Pending (legacy)'),
        ('Paid Pending', 'Paid Pending (legacy)'),
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
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Approved')
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
    payment_method = models.CharField(max_length=20, default='Cash')
    paid_from_ip = models.GenericIPAddressField(null=True, blank=True)
    confirmation_notes = models.TextField(blank=True)
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='payrolls_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', '-month', 'employee__employee_code']
        unique_together = ('employee', 'month', 'year')

    def __str__(self):
        return f"{self.employee.employee_code} - {self.month}/{self.year}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        basic = self.basic_salary or Decimal('0')
        daily = basic / Decimal('30') if basic else Decimal('0')

        # Absence deduction: full absent + half day counts as 0.5
        absent_ded = (self.absent_days or 0) * daily
        half_ded = (self.half_days or 0) * daily * Decimal('0.5')
        self.absence_deduction = absent_ded + half_ded

        # Net salary
        self.net_salary = (
            basic
            - self.absence_deduction
            + (self.overtime_amount or Decimal('0'))
            + (self.allowances or Decimal('0'))
            - (self.deductions or Decimal('0'))
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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='customers_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)
    # ----- Dispatch defaults (per-customer memory) -----
    default_coal_type = models.CharField(max_length=30, blank=True,
                                         help_text="Pre-fill coal type for this customer")
    default_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                       help_text="Pre-fill price per ton")
    default_truck_no = models.CharField(max_length=50, blank=True,
                                        help_text="Pre-fill truck number")
    default_driver_name = models.CharField(max_length=100, blank=True)
    default_driver_phone = models.CharField(max_length=20, blank=True)
    default_mine = models.ForeignKey('Mine', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='default_for_customers',
                                     help_text="Pre-fill mine for this customer")
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

    invoice_no = models.CharField(max_length=30, unique=True, blank=True)
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

    # Dispatch system
    dispatch_no = models.CharField(max_length=30, unique=True, blank=True)
    is_locked = models.BooleanField(default=False)
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='sales_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='sales_created')

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.invoice_no} - {self.customer.name}"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        from decimal import Decimal

        # Auto-calculate total
        self.total_amount = (self.quantity_tons or 0) * (self.price_per_ton or 0)

        # Auto-generate dispatch number on first save
        if not self.dispatch_no:
            today = timezone.localtime().strftime('%Y%m%d')
            prefix = f'DISP-{today}-'
            last = Sale.objects.filter(dispatch_no__startswith=prefix).order_by('-dispatch_no').first()
            if last:
                try:
                    last_num = int(last.dispatch_no.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0
            self.dispatch_no = f'{prefix}{last_num + 1:04d}'
            self.is_locked = True

        # Auto-generate invoice_no (mirrors the dispatch number)
        if not self.invoice_no:
            self.invoice_no = self.dispatch_no

        # --- COAL STOCKPILE LOGIC ---
        is_new = self.pk is None
        old = None
        if not is_new:
            old = Sale.objects.get(pk=self.pk)

        delta = Decimal('0')
        
        if is_new:
            if not self.voided:
                delta = -self.quantity_tons # Sales reduce stock
        else:
            if not old.voided and not self.voided:
                delta = -(self.quantity_tons - old.quantity_tons)
            elif not old.voided and self.voided:
                delta = old.quantity_tons # Voiding a sale adds stock back
            elif old.voided and not self.voided:
                delta = -self.quantity_tons

        # Handle moving stock between mines/types if edited
        if not is_new and not self.voided and not old.voided:
            if self.mine_id != old.mine_id or self.coal_type != old.coal_type:
                old_pile, _ = CoalStockpile.objects.get_or_create(mine=old.mine, coal_type=old.coal_type)
                old_pile.quantity_tons += old.quantity_tons
                old_pile.save()
                delta = -self.quantity_tons

        super().save(*args, **kwargs)

        if delta != 0 and self.mine:
            pile, _ = CoalStockpile.objects.get_or_create(mine=self.mine, coal_type=self.coal_type)
            pile.quantity_tons += delta
            pile.save()
        # --- END COAL STOCKPILE LOGIC ---

    @property
    def balance(self):
        return (self.total_amount or 0) - (self.amount_paid or 0)


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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='equipment_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['equipment_code']
        verbose_name_plural = 'Equipment'

    def __str__(self):
        return f"{self.equipment_code} - {self.name}"

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

    @property
    def total_maintenance_cost(self):
        return sum(m.cost for m in self.maintenance_logs.all())

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
        # Void (soft-delete) fields
    voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='maintenance_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.equipment.equipment_code} - {self.maintenance_type} on {self.date}"

class VoidLog(models.Model):
    """Central audit log for every void action. Never deletable — even by superuser."""

    object_type = models.CharField(max_length=50)
    object_id = models.IntegerField()
    object_label = models.CharField(max_length=200, blank=True)
    voided_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='void_logs')
    voided_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-voided_at']
        verbose_name = 'Void Log'
        verbose_name_plural = 'Void Logs'

    def __str__(self):
        return f"{self.object_type} #{self.object_id} voided by {self.voided_by}"

    
class SalePayment(models.Model):
    METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Bank', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Online', 'Online / Mobile Wallet'),
    ]

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='Cash')
    reference_no = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.sale.dispatch_no} — PKR {self.amount}"    



# =====================================================================
# SAFETY MODULE
#
# No `voided` fields — safety records must never be deleted.
# Use `status` transitions instead: Open → In Progress → Resolved → Closed.
# =====================================================================


class SafetyIncident(models.Model):
    INCIDENT_TYPE_CHOICES = [
        ('Injury', 'Injury / Accident'),
        ('Near Miss', 'Near Miss'),
        ('Property Damage', 'Property / Equipment Damage'),
        ('Environmental', 'Environmental (Gas, Water, Dust)'),
        ('Fire', 'Fire'),
        ('Explosion', 'Explosion'),
        ('Roof Fall', 'Roof Fall / Rockfall'),
        ('Vehicle', 'Vehicle Accident'),
        ('Electrical', 'Electrical Incident'),
        ('Other', 'Other'),
    ]

    SEVERITY_CHOICES = [
        ('Minor', 'Minor (First Aid)'),
        ('Moderate', 'Moderate (Medical Treatment)'),
        ('Serious', 'Serious (Hospitalization)'),
        ('Critical', 'Critical (Permanent Disability)'),
        ('Fatal', 'Fatal'),
    ]

    STATUS_CHOICES = [
        ('Reported', 'Reported'),
        ('Investigating', 'Under Investigation'),
        ('Action Pending', 'Corrective Action Pending'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]

    incident_no = models.CharField(max_length=30, unique=True, blank=True,
                                   help_text="Auto-generated: INC-YYYY-0001")
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    mine = models.ForeignKey('Mine', on_delete=models.PROTECT, related_name='safety_incidents')
    shift = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=200, blank=True,
                                help_text="Exact spot: e.g. tunnel 3 entrance")
    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPE_CHOICES, default='Injury')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='Minor')
    description = models.TextField(help_text="What happened? Write what you saw.")
    employee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='safety_incidents',
                                 help_text="Injured person, if any")
    witnesses = models.TextField(blank=True, help_text="Names of witnesses, one per line")
    immediate_action = models.TextField(blank=True, help_text="What was done immediately?")
    root_cause = models.TextField(blank=True, help_text="Filled during investigation")
    corrective_action = models.TextField(blank=True, help_text="Steps taken to prevent recurrence")
    photo = models.ImageField(upload_to='safety/incidents/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Reported')
    reported_to_government = models.BooleanField(
        default=False,
        help_text="Reported to Mines Department? Required for serious/fatal.",
    )
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                               help_text="Medical, damage, or fine cost in PKR")
    reported_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                    related_name='incidents_reported')
    investigated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='incidents_investigated')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Safety Incident'
        verbose_name_plural = 'Safety Incidents'
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"{self.incident_no} — {self.incident_type} ({self.date})"

    def save(self, *args, **kwargs):
        if not self.incident_no:
            from django.utils import timezone
            year = timezone.localdate().year
            prefix = f'INC-{year}-'
            last = SafetyIncident.objects.filter(
                incident_no__startswith=prefix
            ).order_by('-incident_no').first()
            if last:
                try:
                    last_num = int(last.incident_no.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0
            self.incident_no = f'{prefix}{last_num + 1:04d}'
        super().save(*args, **kwargs)


class Hazard(models.Model):
    HAZARD_TYPE_CHOICES = [
        ('Roof', 'Roof / Overhang Issue'),
        ('Ventilation', 'Poor Ventilation'),
        ('Gas', 'Gas Presence'),
        ('Water', 'Water Ingress'),
        ('Equipment', 'Equipment Defect'),
        ('Electrical', 'Electrical Hazard'),
        ('Slip', 'Slip / Trip Hazard'),
        ('Noise', 'Excessive Noise'),
        ('Dust', 'Excessive Dust'),
        ('Lighting', 'Inadequate Lighting'),
        ('Other', 'Other'),
    ]

    RISK_LEVEL_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'Fix In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]

    hazard_no = models.CharField(max_length=30, unique=True, blank=True,
                                 help_text="Auto-generated: HAZ-YYYY-0001")
    date_observed = models.DateField()
    mine = models.ForeignKey('Mine', on_delete=models.PROTECT, related_name='hazards')
    shift = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=200)
    hazard_type = models.CharField(max_length=30, choices=HAZARD_TYPE_CHOICES, default='Roof')
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default='Medium')
    description = models.TextField(help_text="What did you see? Be specific.")
    photo = models.ImageField(upload_to='safety/hazards/', blank=True, null=True)
    action_taken = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    observed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                    related_name='hazards_observed')
    assigned_to = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='hazards_assigned',
                                    help_text="Who is responsible for fixing this?")
    due_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_observed', '-created_at']
        indexes = [
            models.Index(fields=['date_observed']),
            models.Index(fields=['status']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f"{self.hazard_no} — {self.hazard_type} ({self.location})"

    def save(self, *args, **kwargs):
        if not self.hazard_no:
            from django.utils import timezone
            year = timezone.localdate().year
            prefix = f'HAZ-{year}-'
            last = Hazard.objects.filter(
                hazard_no__startswith=prefix
            ).order_by('-hazard_no').first()
            if last:
                try:
                    last_num = int(last.hazard_no.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0
            self.hazard_no = f'{prefix}{last_num + 1:04d}'
        super().save(*args, **kwargs)


class SafetyInspection(models.Model):
    INSPECTION_TYPE_CHOICES = [
        ('Daily', 'Daily Walk-around'),
        ('Weekly', 'Weekly Inspection'),
        ('Monthly', 'Monthly Audit'),
        ('Quarterly', 'Quarterly Review'),
        ('Annual', 'Annual Certification'),
        ('Special', 'Special / Ad-hoc'),
    ]

    OVERALL_STATUS_CHOICES = [
        ('Pass', 'Pass'),
        ('Conditional', 'Pass with Conditions'),
        ('Fail', 'Fail — Action Required'),
    ]

    inspection_no = models.CharField(max_length=30, unique=True, blank=True,
                                     help_text="Auto-generated: INS-YYYY-0001")
    date = models.DateField()
    mine = models.ForeignKey('Mine', on_delete=models.PROTECT, related_name='safety_inspections')
    location = models.CharField(max_length=200, blank=True,
                                help_text="Specific area if not whole mine")
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPE_CHOICES,
                                       default='Weekly')
    inspector = models.CharField(max_length=150, help_text="Who conducted the inspection")
    findings = models.TextField(help_text="What was checked and what was found")
    issues_count = models.PositiveIntegerField(default=0, help_text="Number of issues discovered")
    overall_status = models.CharField(max_length=20, choices=OVERALL_STATUS_CHOICES, default='Pass')
    follow_up_required = models.BooleanField(default=False)
    follow_up_deadline = models.DateField(null=True, blank=True)
    follow_up_notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to='safety/inspections/', blank=True, null=True)
    conducted_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                     related_name='inspections_conducted')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['overall_status']),
        ]

    def __str__(self):
        return f"{self.inspection_no} — {self.inspection_type} ({self.date})"

    def save(self, *args, **kwargs):
        if not self.inspection_no:
            from django.utils import timezone
            year = timezone.localdate().year
            prefix = f'INS-{year}-'
            last = SafetyInspection.objects.filter(
                inspection_no__startswith=prefix
            ).order_by('-inspection_no').first()
            if last:
                try:
                    last_num = int(last.inspection_no.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0
            self.inspection_no = f'{prefix}{last_num + 1:04d}'
        super().save(*args, **kwargs)


class PPEIssuance(models.Model):
    PPE_TYPE_CHOICES = [
        ('Helmet', 'Safety Helmet'),
        ('Boots', 'Safety Boots'),
        ('Gloves', 'Safety Gloves'),
        ('Glasses', 'Safety Glasses'),
        ('Respirator', 'Respirator / Dust Mask'),
        ('Earplugs', 'Hearing Protection'),
        ('Vest', 'Reflective Vest'),
        ('Harness', 'Safety Harness'),
        ('GasDetector', 'Personal Gas Detector'),
        ('Lamp', 'Miners Lamp'),
        ('Other', 'Other'),
    ]

    CONDITION_CHOICES = [
        ('New', 'New'),
        ('Used', 'Used'),
        ('Replacement', 'Replacement'),
    ]

    employee = models.ForeignKey('Employee', on_delete=models.CASCADE,
                                 related_name='ppe_issuances')
    date_issued = models.DateField()
    ppe_type = models.CharField(max_length=30, choices=PPE_TYPE_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    size = models.CharField(max_length=20, blank=True, help_text="e.g. M, L, 42")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='New')
    replacement_due = models.DateField(null=True, blank=True,
                                       help_text="Legally mandated replacement date")
    returned = models.BooleanField(default=False,
                                    help_text="Mark when employee leaves or returns")
    returned_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                  related_name='ppe_issued')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_issued']
        indexes = [
            models.Index(fields=['date_issued']),
            models.Index(fields=['ppe_type']),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} — {self.ppe_type} ({self.date_issued})"


class SafetyTraining(models.Model):
    TRAINING_TYPE_CHOICES = [
        ('Induction', 'General Safety Induction'),
        ('FirstAid', 'First Aid'),
        ('FireSafety', 'Fire Safety'),
        ('Equipment', 'Equipment Operation'),
        ('Confined', 'Confined Space Entry'),
        ('Heights', 'Working at Heights'),
        ('Explosives', 'Explosives Handling'),
        ('Hazmat', 'Hazardous Materials'),
        ('Evacuation', 'Emergency Evacuation'),
        ('GasDetection', 'Gas Detection'),
        ('Other', 'Other'),
    ]

    employee = models.ForeignKey('Employee', on_delete=models.CASCADE,
                                 related_name='safety_trainings')
    training_type = models.CharField(max_length=30, choices=TRAINING_TYPE_CHOICES)
    training_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True,
                                   help_text="When does this certification expire?")
    trainer_name = models.CharField(max_length=150, blank=True)
    trainer_company = models.CharField(max_length=150, blank=True,
                                        help_text="If external")
    duration_hours = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    certificate_no = models.CharField(max_length=50, blank=True)
    certificate_photo = models.ImageField(upload_to='safety/training/', blank=True, null=True)
    passed = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                    related_name='safety_trainings_recorded')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-training_date']
        indexes = [
            models.Index(fields=['training_date']),
            models.Index(fields=['expiry_date']),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} — {self.training_type} ({self.training_date})"



class CoalStockpile(models.Model):
    """
    Automatically tracks the physical coal stockpile (in tons).
    Updates automatically when Production or Sales are saved/voided.
    """
    mine = models.ForeignKey(Mine, on_delete=models.CASCADE, related_name='coal_stockpiles')
    coal_type = models.CharField(max_length=30, choices=ProductionRecord.COAL_TYPE_CHOICES, default='Bituminous')
    quantity_tons = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Audit
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('mine', 'coal_type')
        ordering = ['mine__name', 'coal_type']

    def __str__(self):
        return f"{self.mine.name} - {self.coal_type}: {self.quantity_tons} tons"