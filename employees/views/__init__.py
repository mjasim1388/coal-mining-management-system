"""
View package — re-exports all views from submodules so `views.<name>`
continues to work in urls.py.
"""
from .notifications import (  # noqa: F401
    create_notification,
    notify_role,
    notify_accountants,
    notify_managers,
    notification_list,
)
from .dashboard import dashboard  # noqa: F401
from .employees import (  # noqa: F401
    employee_list, employee_detail, employee_add, employee_edit, employee_void,
)
from .mines import (  # noqa: F401
    mine_list, mine_add, mine_edit, mine_void,
)
from .production import (  # noqa: F401
    production_list, production_add, production_edit, production_void,
)
from .attendance import (  # noqa: F401
    attendance_list, attendance_add, attendance_edit, attendance_void,
    attendance_punch, attendance_punch_save,
)
from .inventory import (  # noqa: F401
    inventory_list, inventory_add, inventory_edit, inventory_void,
    stock_transaction_list, stock_transaction_add, stock_transaction_delete,
    stock_quick_in, stock_quick_out, coal_stock_list,
)
from .payroll import (  # noqa: F401
    payroll_list, payroll_generate, payroll_add, payroll_edit,
    payroll_mark_paid, payroll_void, payroll_detail, payroll_slip,
    payroll_autofill_api,
)
from .customers import (  # noqa: F401
    customer_list, customer_add, customer_edit, customer_void,
    customer_autofill_api,
)
from .sales import (  # noqa: F401
    sale_list, sale_detail, sale_add, sale_edit, sale_delete, sale_slip,
    sales_live_api, sale_add_payment, sale_payment_delete,
)
from .equipment import (  # noqa: F401
    equipment_list, equipment_detail, equipment_add, equipment_edit, equipment_void,
    maintenance_list, maintenance_add, maintenance_edit, maintenance_void,
    fuel_report,
)
from .exports import (  # noqa: F401
    export_employees, export_mines, export_production, export_attendance,
    export_inventory, export_payroll, export_sales, export_daily_report,
)
from .approvals import (  # noqa: F401
    approval_list,
    approve_employee, reject_employee,
    approve_inventory, reject_inventory,
    approve_payroll, approve_payroll_paid,
)
from .backups import (  # noqa: F401
    backup_now, backup_list, backup_download,
)
from .reports import (  # noqa: F401
    reports_hub, report_sales, report_production, report_payroll,
    report_inventory, report_attendance, report_equipment,
)
from .search import global_search  # noqa: F401

from .safety import (  # noqa: F401
    safety_hub,
    incident_list, incident_detail, incident_add, incident_edit, incident_close,
    hazard_list, hazard_detail, hazard_add, hazard_edit, hazard_resolve,
    inspection_list, inspection_detail, inspection_add, inspection_edit,
    ppe_list, ppe_add, ppe_edit, ppe_return,
    training_list, training_add, training_edit,
)