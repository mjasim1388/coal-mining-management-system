from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Employees
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/add/', views.employee_add, name='employee_add'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/void/', views.employee_void, name='employee_void'),

    # Mines
    path('mines/', views.mine_list, name='mine_list'),
    path('mines/add/', views.mine_add, name='mine_add'),
    path('mines/<int:pk>/edit/', views.mine_edit, name='mine_edit'),
    path('mines/<int:pk>/void/', views.mine_void, name='mine_void'),

    # Production
    path('production/', views.production_list, name='production_list'),
    path('production/add/', views.production_add, name='production_add'),
    path('production/<int:pk>/edit/', views.production_edit, name='production_edit'),
    path('production/<int:pk>/void/', views.production_void, name='production_void'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/punch/', views.attendance_punch, name='attendance_punch'),
    path('attendance/punch/<int:pk>/save/', views.attendance_punch_save, name='attendance_punch_save'),
    path('attendance/add/', views.attendance_add, name='attendance_add'),
    path('attendance/<int:pk>/edit/', views.attendance_edit, name='attendance_edit'),
    path('attendance/<int:pk>/void/', views.attendance_void, name='attendance_void'),

    # Inventory
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/add/', views.inventory_add, name='inventory_add'),
    path('inventory/<int:pk>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/<int:pk>/void/', views.inventory_void, name='inventory_void'),
    path('inventory/transactions/', views.stock_transaction_list, name='stock_transaction_list'),
    path('inventory/transactions/add/', views.stock_transaction_add, name='stock_transaction_add'),
    path('inventory/transactions/<int:pk>/delete/', views.stock_transaction_delete, name='stock_transaction_delete'),
    path('inventory/quick-in/<int:item_pk>/', views.stock_quick_in, name='stock_quick_in'),
    path('inventory/quick-out/<int:item_pk>/', views.stock_quick_out, name='stock_quick_out'),

    # Payroll
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/add/', views.payroll_add, name='payroll_add'),
    path('payroll/generate/', views.payroll_generate, name='payroll_generate'),
    path('payroll/autofill-api/', views.payroll_autofill_api, name='payroll_autofill_api'),
    path('payroll/<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<int:pk>/edit/', views.payroll_edit, name='payroll_edit'),
    path('payroll/<int:pk>/void/', views.payroll_void, name='payroll_void'),
    path('payroll/<int:pk>/mark-paid/', views.payroll_mark_paid, name='payroll_mark_paid'),
    path('payroll/<int:pk>/pay-confirm/', views.payroll_pay_confirm, name='payroll_pay_confirm'),
    path('payroll/<int:pk>/pay-save/', views.payroll_pay_save, name='payroll_pay_save'),
    path('payroll/<int:pk>/slip/', views.payroll_slip, name='payroll_slip'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_add, name='customer_add'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/void/', views.customer_void, name='customer_void'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/add/', views.sale_add, name='sale_add'),
    path('sales/live/', views.sales_live_api, name='sales_live_api'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('sales/<int:pk>/void/', views.sale_delete, name='sale_delete'),
    path('sales/<int:pk>/slip/', views.sale_slip, name='sale_slip'),

    # Equipment
    path('equipment/', views.equipment_list, name='equipment_list'),
    path('equipment/add/', views.equipment_add, name='equipment_add'),
    path('equipment/fuel-report/', views.fuel_report, name='fuel_report'),
    path('equipment/<int:pk>/', views.equipment_detail, name='equipment_detail'),
    path('equipment/<int:pk>/edit/', views.equipment_edit, name='equipment_edit'),
    path('equipment/<int:pk>/void/', views.equipment_void, name='equipment_void'),

    # Maintenance
    path('maintenance/', views.maintenance_list, name='maintenance_list'),
    path('maintenance/add/', views.maintenance_add, name='maintenance_add'),
    path('maintenance/<int:pk>/edit/', views.maintenance_edit, name='maintenance_edit'),
    path('maintenance/<int:pk>/void/', views.maintenance_void, name='maintenance_void'),

    # Excel Exports
    path('export/employees/', views.export_employees, name='export_employees'),
    path('export/mines/', views.export_mines, name='export_mines'),
    path('export/production/', views.export_production, name='export_production'),
    path('export/attendance/', views.export_attendance, name='export_attendance'),
    path('export/inventory/', views.export_inventory, name='export_inventory'),
    path('export/payroll/', views.export_payroll, name='export_payroll'),
    path('export/sales/', views.export_sales, name='export_sales'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),

    # Approvals (Manager only)
    path('approvals/', views.approval_list, name='approval_list'),
    path('approvals/employee/<int:pk>/approve/', views.approve_employee, name='approve_employee'),
    path('approvals/employee/<int:pk>/reject/', views.reject_employee, name='reject_employee'),
    path('approvals/inventory/<int:pk>/approve/', views.approve_inventory, name='approve_inventory'),
    path('approvals/inventory/<int:pk>/reject/', views.reject_inventory, name='reject_inventory'),
    path('approvals/payroll/<int:pk>/approve/', views.approve_payroll, name='approve_payroll'),
    path('approvals/payroll/<int:pk>/paid/', views.approve_payroll_paid, name='approve_payroll_paid'),

    # Backup
    path('backup/', views.backup_now, name='backup_now'),
    path('backup/list/', views.backup_list, name='backup_list'),
    path('backup/download/<str:filename>/', views.backup_download, name='backup_download'),
    # Reports
    path('reports/', views.reports_hub, name='reports_hub'),
    path('reports/sales/', views.report_sales, name='report_sales'),
    path('reports/production/', views.report_production, name='report_production'),
    path('reports/payroll/', views.report_payroll, name='report_payroll'),
    path('reports/inventory/', views.report_inventory, name='report_inventory'),
    path('reports/attendance/', views.report_attendance, name='report_attendance'),
    path('reports/equipment/', views.report_equipment, name='report_equipment'),

]