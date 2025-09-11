from django.urls import path

from app_kiberclub.views import index, open_profile, error_page_view, save_review_from_page

app_name = 'app_kiberclub'

urlpatterns = [
    path('index/', index, name='index'),
    path('profile/', open_profile, name='open_profile'),
    path('error/', error_page_view, name='error_page'),
    path('save_review_from_page/', save_review_from_page, name='save_review_from_page'),
]