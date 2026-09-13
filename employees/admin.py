from django.contrib import admin
from .models import (Employee, Mine, ProductionRecord, Attendance,
                     InventoryItem, StockTransaction, Payroll,
                     Customer, Sale, Notification, ApprovalLog)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'first_name', 'last_name', 'designation',
                    'department', 'shift', 'status', 'date_of_joining')
    list_filter = ('status', 'shift', 'department')
    search_fields = ('employee_code', 'first_name', 'last_name', 'cnic', 'phone')
    list_per_page = 25


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
