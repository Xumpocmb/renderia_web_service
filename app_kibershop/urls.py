from django.urls import path

from app_kibershop.views import catalog_view, cart_view, add_to_cart, remove_from_cart, cart_minus, cart_plus, make_order, profile_page

app_name = "app_kibershop"


urlpatterns = [
    path('catalog/', catalog_view, name='catalog'),
    path('add_to_cart/<int:product_id>/', add_to_cart, name='add_to_cart'),
    path('cart/', cart_view, name='cart'),
    path('remove_from_cart/<int:cart_id>/', remove_from_cart, name='remove_from_cart'),
    path('cart_plus/<int:cart_id>/', cart_plus, name='cart_plus'),
    path('cart_minus/<int:cart_id>/', cart_minus, name='cart_minus'),
    path('make_order/', make_order, name='make_order'),
    path('profile_page/', profile_page, name='profile_page'),
]
