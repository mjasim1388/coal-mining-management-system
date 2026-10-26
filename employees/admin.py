from django.contrib import admin

from .models import (
    ApprovalLog,
    Attendance,
    Customer,
    Employee,
    Equipment,
    Hazard,
    InventoryItem,
    MaintenanceLog,
    Mine,
    Notification,
    Payroll,
    PPEIssuance,
    ProductionRecord,
    SafetyIncident,
    SafetyInspection,
    SafetyTraining,
    Sale,
    StockTransaction,
)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'first_name', 'last_name', 'designation',
                    'department', 'shift', 'status', 'date_of_joining',
                    'added_by', 'approved_by', 'approved_at')
    list_filter = ('status', 'shift', 'department', 'approval_status')
    search_fields = ('employee_code', 'first_name', 'last_name', 'cnic', 'phone')
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at', 'added_by', 'approved_by', 'approved_at')


@admin.register(Mine)
class MineAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'manager_name', 'reserves_tons', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'location', 'license_no')


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = ('date', 'shift', 'mine', 'coal_type', 'quantity_tons',
                    'overburden_removed', 'supervisor', 'workers_count')
    list_filter = ('mine', 'shift', 'coal_type', 'date')
    search_fields = ('mine__name', 'supervisor')
    date_hierarchy = 'date'


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'shift', 'status', 'check_in',
                    'check_out', 'overtime_hours')
    list_filter = ('status', 'shift', 'date')
    search_fields = ('employee__employee_code', 'employee__first_name', 'employee__last_name')
    date_hierarchy = 'date'


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'reorder_level',
                    'unit_price', 'location')
    list_filter = ('category',)
    search_fields = ('name', 'location')


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'item', 'transaction_type', 'quantity',
                    'reason', 'handled_by')
    list_filter = ('transaction_type', 'date', 'item__category')
    search_fields = ('item__name', 'reason', 'handled_by')
    date_hierarchy = 'date'


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'basic_salary',
                    'present_days', 'overtime_amount', 'net_salary', 'status')
    list_filter = ('status', 'year', 'month')
    search_fields = ('employee__employee_code', 'employee__first_name', 'employee__last_name')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'phone', 'email', 'ntn')
    search_fields = ('name', 'company', 'phone', 'ntn')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_no', 'date', 'customer', 'mine', 'coal_type',
                    'quantity_tons', 'price_per_ton', 'total_amount',
                    'payment_status')
    list_filter = ('payment_status', 'coal_type', 'date', 'mine')
    search_fields = ('invoice_no', 'customer__name', 'truck_no')
    date_hierarchy = 'date'

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'message')
    date_hierarchy = 'created_at'


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ('object_type', 'object_id', 'object_label', 'requested_by',
                    'status', 'reviewed_by', 'created_at')
    list_filter = ('object_type', 'status', 'created_at')
    search_fields = ('object_label', 'requested_by__username')
    date_hierarchy = 'created_at'

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('equipment_code', 'name', 'equipment_type', 'mine', 'status', 'fuel_type')
    list_filter = ('status', 'equipment_type', 'fuel_type', 'mine')
    search_fields = ('equipment_code', 'name', 'model_number', 'serial_number')
    list_per_page = 25


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ('date', 'equipment', 'maintenance_type', 'cost',
                    'performed_by', 'status')
    list_filter = ('maintenance_type', 'status', 'date', 'equipment')
    search_fields = ('equipment__name', 'equipment__equipment_code', 'description', 'performed_by')
    date_hierarchy = 'date'


@admin.register(SafetyIncident)
class SafetyIncidentAdmin(admin.ModelAdmin):
    list_display = ('incident_no', 'date', 'mine', 'incident_type', 'severity',
                    'employee', 'status', 'reported_to_government')
    list_filter = ('incident_type', 'severity', 'status', 'mine',
                   'reported_to_government', 'date')
    search_fields = ('incident_no', 'description', 'location',
                     'employee__first_name', 'employee__last_name')
    date_hierarchy = 'date'
    list_per_page = 25
    readonly_fields = ('incident_no', 'created_at', 'updated_at')


@admin.register(Hazard)
class HazardAdmin(admin.ModelAdmin):
    list_display = ('hazard_no', 'date_observed', 'mine', 'hazard_type',
                    'risk_level', 'location', 'status', 'assigned_to')
    list_filter = ('hazard_type', 'risk_level', 'status', 'mine', 'date_observed')
    search_fields = ('hazard_no', 'description', 'location')
    date_hierarchy = 'date_observed'
    list_per_page = 25
    readonly_fields = ('hazard_no', 'created_at', 'updated_at')


@admin.register(SafetyInspection)
class SafetyInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_no', 'date', 'mine', 'inspection_type',
                    'inspector', 'overall_status', 'issues_count',
                    'follow_up_required')
    list_filter = ('inspection_type', 'overall_status', 'follow_up_required',
                   'mine', 'date')
    search_fields = ('inspection_no', 'inspector', 'findings', 'location')
    date_hierarchy = 'date'
    list_per_page = 25
    readonly_fields = ('inspection_no', 'created_at')


@admin.register(PPEIssuance)
class PPEIssuanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date_issued', 'ppe_type', 'quantity',
                    'condition', 'replacement_due', 'returned')
    list_filter = ('ppe_type', 'condition', 'returned', 'date_issued')
    search_fields = ('employee__employee_code', 'employee__first_name',
                     'employee__last_name', 'size')
    date_hierarchy = 'date_issued'
    list_per_page = 25


@admin.register(SafetyTraining)
class SafetyTrainingAdmin(admin.ModelAdmin):
    list_display = ('employee', 'training_type', 'training_date', 'expiry_date',
                    'duration_hours', 'passed')
    list_filter = ('training_type', 'passed', 'training_date', 'expiry_date')
    search_fields = ('employee__employee_code', 'employee__first_name',
                     'employee__last_name', 'trainer_name', 'certificate_no')
    date_hierarchy = 'training_date'
    list_per_page = 25