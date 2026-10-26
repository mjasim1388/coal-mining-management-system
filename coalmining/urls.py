from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.views.static import serve as media_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('', include('employees.urls')),
]

# Serve media files (employee photos, receipts, signed slips)
# Uses Django's serve view wrapped with login_required so:
#   1. Files work in production (DEBUG=False)
#   2. Only logged-in users can access them
urlpatterns += [
    re_path(
        r'^media/(?P<path>.*)$',
        login_required(media_serve),
        {'document_root': settings.MEDIA_ROOT},
    ),
]