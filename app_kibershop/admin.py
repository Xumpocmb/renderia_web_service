from django.contrib import admin

from app_kibershop.models import Category, Product, OrderItem, Order, ClientKiberons, Cart


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'in_stock', 'quantity_in_stock', 'category')
    search_fields = ('name',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ['product', 'quantity']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = ['__str__']
    # search_fields = ['user__phone_number']


@admin.register(ClientKiberons)
class ClientKiberonsAdmin(admin.ModelAdmin):
    model = ClientKiberons


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    model = Cart