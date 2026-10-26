"""
Excel export views — one per module.
"""
from datetime import date, datetime
from django.db.models import Sum
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from ..decorators import role_required
from ..exports import make_excel_response
from ..models import (
    Attendance, Employee, InventoryItem, Mine, Payroll, ProductionRecord, Sale,
    SafetyIncident, Hazard, SalePayment
)


@role_required('Manager', 'Accountant')
def export_employees(request):
    headers = ['Code', 'First Name', 'Last Name', 'Father Name', 'CNIC',
               'Phone', 'Designation', 'Department', 'Shift',
               'Joining Date', 'Salary', 'Status']
    rows = []
    for e in Employee.objects.all():
        rows.append([e.employee_code, e.first_name, e.last_name, e.father_name,
                     e.cnic, e.phone, e.designation, e.department, e.shift,
                     str(e.date_of_joining), float(e.salary), e.status])
    return make_excel_response(f'employees_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_mines(request):
    headers = ['Name', 'Location', 'License No', 'Manager', 'Reserves (tons)', 'Status']
    rows = []
    for m in Mine.objects.all():
        rows.append([m.name, m.location, m.license_no, m.manager_name,
                     float(m.reserves_tons), m.status])
    return make_excel_response(f'mines_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_production(request):
    headers = ['Date', 'Shift', 'Mine', 'Coal Type', 'Quantity (tons)',
               'Overburden', 'Supervisor', 'Workers']
    rows = []
    for r in ProductionRecord.objects.select_related('mine').all():
        rows.append([str(r.date), r.shift, r.mine.name, r.coal_type,
                     float(r.quantity_tons), float(r.overburden_removed),
                     r.supervisor, r.workers_count])
    return make_excel_response(f'production_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_attendance(request):
    headers = ['Date', 'Employee Code', 'Employee Name', 'Shift', 'Status',
               'Check In', 'Check Out', 'Overtime (h)']
    rows = []
    for r in Attendance.objects.select_related('employee').all():
        rows.append([str(r.date), r.employee.employee_code,
                     f'{r.employee.first_name} {r.employee.last_name}',
                     r.shift, r.status,
                     str(r.check_in) if r.check_in else '',
                     str(r.check_out) if r.check_out else '',
                     float(r.overtime_hours)])
    return make_excel_response(f'attendance_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_inventory(request):
    headers = ['Name', 'Category', 'Quantity', 'Unit', 'Reorder Level',
               'Unit Price', 'Location']
    rows = []
    for i in InventoryItem.objects.all():
        rows.append([i.name, i.category, float(i.quantity), i.unit,
                     float(i.reorder_level), float(i.unit_price), i.location])
    return make_excel_response(f'inventory_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_payroll(request):
    headers = ['Employee Code', 'Employee Name', 'Month', 'Year',
               'Basic Salary', 'Present', 'Absent', 'Leave', 'Half Day',
               'Overtime Amount', 'Allowances', 'Deductions', 'Net Salary', 'Status']
    rows = []
    for p in Payroll.objects.select_related('employee').all():
        rows.append([p.employee.employee_code,
                     f'{p.employee.first_name} {p.employee.last_name}',
                     p.get_month_display(), p.year,
                     float(p.basic_salary), p.present_days, p.absent_days,
                     p.leave_days, p.half_days,
                     float(p.overtime_amount), float(p.allowances),
                     float(p.deductions), float(p.net_salary), p.status])
    return make_excel_response(f'payroll_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_sales(request):
    headers = ['Invoice No', 'Date', 'Customer', 'Mine', 'Coal Type',
               'Quantity (tons)', 'Price/Ton', 'Total', 'Paid', 'Balance', 'Status']
    rows = []
    for s in Sale.objects.select_related('customer', 'mine').filter(voided=False):
        rows.append([s.invoice_no, str(s.date), s.customer.name,
                     s.mine.name if s.mine else '',
                     s.coal_type, float(s.quantity_tons),
                     float(s.price_per_ton), float(s.total_amount),
                     float(s.amount_paid), float(s.balance), s.payment_status])
    return make_excel_response(f'sales_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_daily_report(request):
    """Generates a professional multi-sheet Excel report for a specific day."""
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # --- 1. Fetch Data ---
    productions = ProductionRecord.objects.filter(date=target_date, voided=False).select_related('mine')
    sales = Sale.objects.filter(date=target_date, voided=False).select_related('customer', 'mine')
    attendances = Attendance.objects.filter(date=target_date, voided=False).select_related('employee')
    incidents = SafetyIncident.objects.filter(date=target_date)
    hazards = Hazard.objects.filter(date_observed=target_date)
    payments = SalePayment.objects.filter(date=target_date, sale__voided=False)
    
    # New data sources for a complete record
    from ..models import StockTransaction, MaintenanceLog
    stock_moves = StockTransaction.objects.filter(date=target_date).select_related('item', 'issued_to_equipment')
    maintenances = MaintenanceLog.objects.filter(date=target_date, voided=False).select_related('equipment')

    # --- 2. Calculate Summary Totals ---
    total_tons_produced = productions.aggregate(t=Sum('quantity_tons'))['t'] or 0
    total_overburden = productions.aggregate(t=Sum('overburden_removed'))['t'] or 0
    
    total_sales_amount = sales.aggregate(t=Sum('total_amount'))['t'] or 0
    total_tons_sold = sales.aggregate(t=Sum('quantity_tons'))['t'] or 0
    total_cash_received = payments.aggregate(t=Sum('amount'))['t'] or 0
    
    present_count = attendances.filter(status='Present').count()
    absent_count = attendances.filter(status='Absent').count()
    
    incident_count = incidents.count()
    hazard_count = hazards.count()
    
    total_maint_cost = maintenances.aggregate(t=Sum('cost'))['t'] or 0

    # --- 3. Build Workbook & Styles ---
    wb = Workbook()
    
    # Colors (Coal Mine Theme)
    COLOR_PRIMARY = "1F2937"   # Dark Slate (Headers)
    COLOR_ACCENT = "10B981"    # Emerald Green (Totals)
    COLOR_BG_LIGHT = "F3F4F6"  # Light Gray (Zebra Striping)
    
    font_header = Font(bold=True, color="FFFFFF", size=11)
    fill_header = PatternFill(start_color=COLOR_PRIMARY, end_color=COLOR_PRIMARY, fill_type="solid")
    
    font_total = Font(bold=True, color="FFFFFF", size=11)
    fill_total = PatternFill(start_color=COLOR_ACCENT, end_color=COLOR_ACCENT, fill_type="solid")
    
    font_title = Font(bold=True, size=16, color=COLOR_PRIMARY)
    font_subtitle = Font(italic=True, size=11, color="666666")
    
    thin_border = Border(bottom=Side(style='thin', color='CCCCCC'))
    align_center = Alignment(horizontal="center", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    def add_company_header(ws, sheet_title):
        """Adds a professional header to the top of any sheet."""
        ws.merge_cells('A1:F1')
        c1 = ws['A1']
        c1.value = "COAL MINE COMPANY"
        c1.font = font_title
        c1.alignment = align_center
        
        ws.merge_cells('A2:F2')
        c2 = ws['A2']
        c2.value = sheet_title
        c2.font = Font(bold=True, size=12)
        c2.alignment = align_center
        
        ws.merge_cells('A3:F3')
        c3 = ws['A3']
        c3.value = f"Date: {target_date.strftime('%d %B %Y')}"
        c3.font = font_subtitle
        c3.alignment = align_center
        
        # Border under header
        for col in range(1, 7):
            ws.cell(row=3, column=col).border = Border(bottom=Side(style='medium', color=COLOR_PRIMARY))
        
        return 5 # Data starts at row 5

    def format_table(ws, start_row, headers, rows, totals_row=None):
        """Formats a standard data table with headers, zebra stripes, and optional totals."""
        # Headers
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=col, value=header)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_center
            cell.border = thin_border
            
        # Data
        for r_idx, row_data in enumerate(rows):
            current_row = start_row + 1 + r_idx
            for c_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=current_row, column=c_idx, value=val)
                cell.border = thin_border
                cell.alignment = align_right if isinstance(val, (int, float)) else align_left
                
                # Zebra striping
                if r_idx % 2 == 1:
                    cell.fill = PatternFill(start_color=COLOR_BG_LIGHT, end_color=COLOR_BG_LIGHT, fill_type="solid")
                    
        # Totals Row
        if totals_row:
            final_row = start_row + 1 + len(rows)
            for c_idx, val in enumerate(totals_row, start=1):
                cell = ws.cell(row=final_row, column=c_idx, value=val)
                cell.font = font_total
                cell.fill = fill_total
                cell.alignment = align_right if isinstance(val, (int, float)) else align_left
                cell.border = thin_border

        # Auto-width columns (safe for MergedCells)
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                except AttributeError:
                    pass
            ws.column_dimensions[col_letter].width = min(max_len + 4, 45)
    # ==========================================
    # SHEET 1: EXECUTIVE SUMMARY
    # ==========================================
    ws = wb.active
    ws.title = "Summary"
    start_row = add_company_header(ws, "EXECUTIVE DAILY SUMMARY")
    
    # Build a clean KPI grid
    kpis = [
        ("OPERATIONS", ""),
        ("Coal Produced", f"{total_tons_produced:,.2f} Tons"),
        ("Overburden Removed", f"{total_overburden:,.2f} Tons"),
        ("", ""),
        ("SALES & CASH", ""),
        ("Tons Dispatched", f"{total_tons_sold:,.2f} Tons"),
        ("Total Invoiced", f"PKR {total_sales_amount:,.2f}"),
        ("Cash Collected", f"PKR {total_cash_received:,.2f}"),
        ("", ""),
        ("WORKFORCE", ""),
        ("Employees Present", str(present_count)),
        ("Employees Absent", str(absent_count)),
        ("", ""),
        ("SAFETY & MAINTENANCE", ""),
        ("New Incidents", str(incident_count)),
        ("New Hazards", str(hazard_count)),
        ("Maintenance Cost", f"PKR {total_maint_cost:,.2f}"),
    ]
    
    r = start_row
    for label, val in kpis:
        c1 = ws.cell(row=r, column=1, value=label)
        if val == "":
            c1.font = Font(bold=True, color=COLOR_PRIMARY)
        else:
            c1.font = Font(bold=False)
            c2 = ws.cell(row=r, column=2, value=val)
            c2.alignment = align_right
        r += 1
        
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 5

    # ==========================================
    # SHEET 2: SALES & DISPATCH
    # ==========================================
    ws_sales = wb.create_sheet("Sales")
    start_row = add_company_header(ws_sales, "SALES & DISPATCH RECORD")
    
    sales_headers = ['Dispatch No', 'Customer', 'Mine', 'Truck No', 'Tons', 'Total (PKR)', 'Paid (PKR)', 'Balance (PKR)', 'Status']
    sales_rows = []
    for s in sales:
        sales_rows.append([
            s.dispatch_no or s.invoice_no, s.customer.name, s.mine.name if s.mine else '—',
            s.truck_no or '—', float(s.quantity_tons), float(s.total_amount),
            float(s.amount_paid), float(s.balance), s.payment_status
        ])
    sales_totals = ["TOTALS", "", "", "", float(total_tons_sold), float(total_sales_amount), float(total_cash_received), "", ""]
    format_table(ws_sales, start_row, sales_headers, sales_rows, sales_totals)

    # ==========================================
    # SHEET 3: PRODUCTION
    # ==========================================
    ws_prod = wb.create_sheet("Production")
    start_row = add_company_header(ws_prod, "PRODUCTION RECORD")
    
    prod_headers = ['Mine', 'Shift', 'Coal Type', 'Quantity (Tons)', 'Overburden', 'Supervisor', 'Workers']
    prod_rows = []
    for p in productions:
        prod_rows.append([
            p.mine.name, p.shift, p.coal_type, 
            float(p.quantity_tons), float(p.overburden_removed),
            p.supervisor or '—', p.workers_count
        ])
    prod_totals = ["TOTALS", "", "", float(total_tons_produced), float(total_overburden), "", ""]
    format_table(ws_prod, start_row, prod_headers, prod_rows, prod_totals)

    # ==========================================
    # SHEET 4: ATTENDANCE
    # ==========================================
    ws_att = wb.create_sheet("Attendance")
    start_row = add_company_header(ws_att, "EMPLOYEE ATTENDANCE")
    
    att_headers = ['Emp Code', 'Employee Name', 'Shift', 'Status', 'Check In', 'Check Out', 'Overtime (h)']
    att_rows = []
    for a in attendances:
        att_rows.append([
            a.employee.employee_code, 
            f"{a.employee.first_name} {a.employee.last_name}",
            a.shift, a.status, 
            str(a.check_in) if a.check_in else '—', 
            str(a.check_out) if a.check_out else '—', 
            float(a.overtime_hours)
        ])
    att_totals = ["TOTALS", f"Present: {present_count}", "", "", "", "", ""]
    format_table(ws_att, start_row, att_headers, att_rows, att_totals)

    # ==========================================
    # SHEET 5: SAFETY
    # ==========================================
    ws_safety = wb.create_sheet("Safety")
    start_row = add_company_header(ws_safety, "SAFETY EVENTS")
    
    safety_headers = ['Type', 'Ref No', 'Time', 'Mine', 'Description / Location', 'Status']
    safety_rows = []
    for i in incidents:
        safety_rows.append(['INCIDENT', i.incident_no, str(i.time) if i.time else '—', i.mine.name, i.description[:100], i.status])
    for h in hazards:
        safety_rows.append(['HAZARD', h.hazard_no, '—', h.mine.name, h.location, h.status])
    format_table(ws_safety, start_row, safety_headers, safety_rows)

    # ==========================================
    # SHEET 6: INVENTORY MOVEMENTS
    # ==========================================
    ws_inv = wb.create_sheet("Inventory")
    start_row = add_company_header(ws_inv, "INVENTORY MOVEMENTS")
    
    inv_headers = ['Item', 'Type', 'Quantity', 'Unit', 'Issued To / Reason', 'Handled By']
    inv_rows = []
    for t in stock_moves:
        issue_target = t.issued_to_display if t.transaction_type == 'OUT' else 'Stock Received'
        inv_rows.append([t.item.name, t.transaction_type, float(t.quantity), t.item.unit, issue_target, t.handled_by or '—'])
    format_table(ws_inv, start_row, inv_headers, inv_rows)

    # ==========================================
    # SHEET 7: MAINTENANCE
    # ==========================================
    ws_maint = wb.create_sheet("Maintenance")
    start_row = add_company_header(ws_maint, "EQUIPMENT MAINTENANCE")
    
    maint_headers = ['Equipment', 'Type', 'Description', 'Cost (PKR)', 'Performed By', 'Status']
    maint_rows = []
    for m in maintenances:
        maint_rows.append([m.equipment.name, m.maintenance_type, m.description[:60], float(m.cost), m.performed_by or '—', m.status])
    maint_totals = ["TOTALS", "", "", float(total_maint_cost), "", ""]
    format_table(ws_maint, start_row, maint_headers, maint_rows, maint_totals)

    # --- 4. Return Response ---
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"Daily_Report_{target_date.strftime('%Y-%m-%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response