\# 🏭 Coal Mining Management System



A full-stack web application for managing coal mining operations — from employee records and daily production logs to inventory, payroll, attendance, and sales. Built with Django and PostgreSQL, featuring role-based access control and interactive dashboards.



!\[Django](https://img.shields.io/badge/Django-6.1-092E20?style=for-the-badge\&logo=django\&logoColor=white)

!\[PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=for-the-badge\&logo=postgresql\&logoColor=white)

!\[Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge\&logo=python\&logoColor=white)

!\[Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?style=for-the-badge\&logo=bootstrap\&logoColor=white)



\---



\## 📋 Overview



The \*\*Coal Mining Management System\*\* is a complete operations platform designed for coal mining companies. It centralizes workforce management, production tracking, inventory control, payroll processing, and sales reporting into a single, role-secured web application.



The system implements \*\*Role-Based Access Control (RBAC)\*\* so admins, managers, and workers each see only what they need — nothing more, nothing less.



\---



\## ✨ Features



\### 👥 Employee Management

\- Add, edit, and delete employee records

\- Approve new employee registrations

\- Track roles: Admin, Manager, Supervisor, Worker

\- Assign employees to specific mines



\### ⛏️ Mine \& Production Tracking

\- Manage multiple mine locations

\- Log daily production records (tons extracted, shifts, dates)

\- Filter production history by mine, date, or worker



\### 🕐 Attendance System

\- Automatic check-in / check-out timestamps

\- Photo capture on punch-in and punch-out

\- Attendance history per employee

\- Daily and monthly reports



\### 💰 Payroll Management

\- Auto-generate monthly payroll

\- Calculate salaries based on attendance and role

\- Payroll history and downloadable records

\- Approval workflow before payment



\### 📦 Inventory Management

\- Track mining equipment and supplies

\- Stock in / stock out transactions

\- Low-stock alerts

\- Transaction history with audit trail



\### 🤝 Sales \& Customers

\- Customer database

\- Record coal sales with quantity, rate, and total

\- Sales reports by customer, date, or product

\- Invoice-ready detail pages



\### 📊 Dashboards \& Analytics

\- Real-time dashboard with key metrics

\- Chart.js visualizations (production, sales, attendance)

\- Role-specific dashboard views



\### 🔔 Notifications \& Approvals

\- Employee approval workflow

\- In-app notifications for pending actions

\- Admin approval panel



\### 🔐 Security

\- Role-Based Access Control (RBAC)

\- Custom decorators for view permissions

\- Session management with 30-day persistence

\- CSRF protection (Django default)



\### 💾 Backup System

\- One-click database backup

\- Backup history and restore options

\- Timestamped backup files



\---



\## 🛠️ Tech Stack



| Layer | Technology |

|---|---|

| \*\*Backend\*\* | Python 3.12, Django 6.1 |

| \*\*Database\*\* | PostgreSQL 16 |

| \*\*Frontend\*\* | HTML5, CSS3, JavaScript, Bootstrap 5 |

| \*\*Admin Theme\*\* | Django Jazzmin |

| \*\*Charts\*\* | Chart.js |

| \*\*Authentication\*\* | Django Auth + RBAC |

| \*\*File Storage\*\* | Django Media (local) |

| \*\*Version Control\*\* | Git + GitHub |

| \*\*Environment\*\* | python-dotenv |



\---



\## 📁 Project Structure



