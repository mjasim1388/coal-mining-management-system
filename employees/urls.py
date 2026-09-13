from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Employees
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/add/', views.employee_add, name='employee_add'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),

    # Mines
    path('mines/', views.mine_list, name='mine_list'),
    path('mines/add/', views.mine_add, name='mine_add'),
    path('mines/<int:pk>/edit/', views.mine_edit, name='mine_edit'),
    path('mines/<int:pk>/delete/', views.mine_delete, name='mine_delete'),

    # Production
    path('production/', views.production_list, name='production_list'),
    path('production/add/', views.production_add, name='production_add'),
    path('production/<int:pk>/edit/', views.production_edit, name='production_edit'),
    path('production/<int:pk>/delete/', views.production_delete, name='production_delete'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/punch/', views.attendance_punch, name='attendance_punch'),
    path('attendance/punch/<int:pk>/save/', views.attendance_punch_save, name='attendance_punch_save'),
    path('attendance/add/', views.attendance_add, name='attendance_add'),
    path('attendance/<int:pk>/edit/', views.attendance_edit, name='attendance_edit'),
    path('attendance/<int:pk>/delete/', views.attendance_delete, name='attendance_delete'),

    # Inventory
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/add/', views.inventory_add, name='inventory_add'),
    path('inventory/<int:pk>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/<int:pk>/delete/', views.inventory_delete, name='inventory_delete'),
    path('inventory/transactions/', views.stock_transaction_list, name='stock_transaction_list'),
    path('inventory/transactions/add/', views.stock_transaction_add, name='stock_transaction_add'),
    path('inventory/transactions/<int:pk>/delete/', views.stock_transaction_delete, name='stock_transaction_delete'),

    # Payroll
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/add/', views.payroll_add, name='payroll_add'),
    path('payroll/generate/', views.payroll_generate, name='payroll_generate'),
    path('payroll/<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<int:pk>/edit/', views.payroll_edit, name='payroll_edit'),
    path('payroll/<int:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    path('payroll/<int:pk>/mark-paid/', views.payroll_mark_paid, name='payroll_mark_paid'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_add, name='customer_add'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/add/', views.sale_add, name='sale_add'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),

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
    path('backup/delete/<str:filename>/', views.backup_delete, name='backup_delete'),
]