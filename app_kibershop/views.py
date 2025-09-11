import gspread
from django.contrib import messages
from django.db.models import Sum, F
from django.shortcuts import render, redirect, get_object_or_404

from oauth2client.service_account import ServiceAccountCredentials
from gspread.utils import rowcol_to_a1
from app_kiberclub.models import Client, Location
from app_kibershop.models import Category, Product, Cart, Order, OrderItem, ClientKiberons




CREDENTIALS_FILE = 'kiberone-tg-bot-a43691efe721.json'


def catalog_view(request):
    categories = Category.objects.all()
    context = {
        'categories': categories,
    }
    return render(request, 'app_kibershop/catalog.html', context)


def cart_view(request):
    return render(request, 'app_kibershop/cart_page.html')


def add_to_cart(request, product_id):
    user_id = request.session.get('client_id')
    if not user_id:
        messages.error(request, 'Вы не авторизованы', extra_tags='danger')
        return redirect(request.META.get('HTTP_REFERER'))

    try:
        product = get_object_or_404(Product, id=product_id)
    except Product.DoesNotExist:
        messages.error(request, 'Товар не найден', extra_tags='danger')
        return redirect(request.META.get('HTTP_REFERER'))

    try:
        client = get_object_or_404(Client, crm_id=user_id)
    except Client.DoesNotExist:
        messages.error(request, 'Вы не авторизованы', extra_tags='danger')
        return redirect(request.META.get('HTTP_REFERER'))

    cart_item, created = Cart.objects.get_or_create(
        user=client,
        product=product,
    )

    if not created:
        cart_item.quantity += 1
        cart_item.save()

    return redirect(request.META.get('HTTP_REFERER'))


def remove_from_cart(request, cart_id):
    cart_item = Cart.objects.get(id=cart_id)
    cart_item.delete()
    messages.success(request, 'Товар удален из корзины', extra_tags='success')
    return redirect(request.META.get('HTTP_REFERER'))


def cart_minus(request, cart_id):
    cart_item = Cart.objects.get(id=cart_id)
    if cart_item.quantity == 1:
        return redirect(request.META.get('HTTP_REFERER'))
    cart_item.quantity -= 1
    cart_item.save()
    return redirect(request.META.get('HTTP_REFERER'))


def cart_plus(request, cart_id):
    cart_item = Cart.objects.get(id=cart_id)
    cart_item.quantity += 1
    cart_item.save()
    return redirect(request.META.get('HTTP_REFERER'))


def make_order(request):
    if request.method == 'POST':

        # клиент в бд
        try:
            client_id = request.session.get('client_id')
            if client_id is None:
                raise ValueError("client_id is not in session")
            user_in_db = Client.objects.filter(crm_id=client_id).first()
        except Client.DoesNotExist:
            messages.error(request, "Клиент не найден.", extra_tags="danger")
            return redirect(request.META.get('HTTP_REFERER'))

        # кибероны
        try:
            user_orders = Order.objects.filter(user=user_in_db)
            user_kiberons_db = ClientKiberons.objects.filter(client=user_in_db).first()
            if not user_kiberons_db:
                messages.error(request, "Нам не удалось получить количество ваших киберонов.", extra_tags="danger")
                return redirect(request.META.get('HTTP_REFERER'))
            if user_orders.exists():
                user_kiberons_count = int(user_kiberons_db.remain_kiberons_count)
            else:
                user_kiberons_count = int(user_kiberons_db.start_kiberons_count)
        except Order.DoesNotExist:
            messages.error(request, f"Ошибка при получении заказов пользователя", extra_tags="danger")
            return redirect(request.META.get('HTTP_REFERER'))

        # общая сумма заказа
        try:
            cart_items = Cart.objects.filter(user=user_in_db)
            if not cart_items.exists():
                messages.error(request, "Ваша корзина пуста.", extra_tags="danger")
                return redirect(request.META.get('HTTP_REFERER'))
            total_sum = cart_items.total_sum()
        except Cart.DoesNotExist as e:
            return redirect(request.META.get('HTTP_REFERER'))

        if user_kiberons_count < total_sum:
            messages.error(request, 'Недостаточно киберонов', extra_tags='danger')
            return redirect(request.META.get('HTTP_REFERER'))

        # списание киберонов
        try:
            user_kiberons_db.remain_kiberons_count = str(user_kiberons_count - total_sum)
            user_kiberons_db.save()
        except Exception as e:
            messages.error(request, 'Ошибка при списании киберонов', extra_tags='danger')
            return redirect(request.META.get('HTTP_REFERER'))

        # создание заказа
        order = Order.objects.create(user=user_in_db)

        for item in Cart.objects.filter(user=user_in_db):
            product_in_db = Product.objects.get(id=item.product.id)

            if product_in_db.quantity_in_stock < item.quantity:
                messages.error(request, f'Недостаточно товара на складе: {product_in_db.name}', extra_tags='danger')
                return redirect(request.META.get('HTTP_REFERER'))

            if product_in_db.quantity_in_stock - item.quantity == 0:
                product_in_db.quantity_in_stock -= item.quantity
                product_in_db.in_stock = False
            else:
                product_in_db.quantity_in_stock -= item.quantity
            product_in_db.save()

            OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, )

        # сохранение в таблице
        sheet_url = user_in_db.branch.sheet_url
        room_id = request.session.get("room_id")
        location = Location.objects.filter(location_crm_id=room_id).first()
        location_sheet_name = location.sheet_name
        child_id = user_in_db.crm_id
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(credentials)

        try:
            sheet = client.open_by_url(sheet_url).worksheet(location_sheet_name)
        except Exception as e:
            print(f"Ошибка при открытии таблицы: {e}")
            return False

        headers = sheet.row_values(1)

        try:
            kibershop_column_index = headers.index("Кибершоп") + 1
        except ValueError:
            messages.error(request, "Столбец 'Кибершоп' не найден в таблице.", extra_tags="danger")
            return redirect(request.META.get('HTTP_REFERER'))

        data = sheet.get_all_records()
        for index, row in enumerate(data, start=2):
            if str(row.get("ID ребенка")) == str(child_id):
                try:
                    user_orders = Order.objects.filter(user__crm_id=client_id)
                    order_data = []
                    for order in user_orders:
                        for item in order.items.all():
                            product_name = item.product.name
                            quantity = item.quantity
                            order_data.append(f"Товар: {product_name} | Количество ({quantity} шт.) | Стоимость: {item.product.price}")

                    order_info = "\n".join(order_data)

                    cell = rowcol_to_a1(index, kibershop_column_index)
                    sheet.update(cell, [[order_info]])
                except Exception as e:
                    messages.error(request, f"Ошибка при обновлении ячейки: {e}", extra_tags="danger")
                    return redirect(request.META.get('HTTP_REFERER'))

        Cart.objects.filter(user=user_in_db).delete()
        messages.success(request, "Заказ успешно создан!", extra_tags="success")
        return redirect("app_kibershop:profile_page")
    return redirect(request.META.get('HTTP_REFERER'))


def profile_page(request):
    orders = Order.objects.filter(user=Client.objects.get(crm_id=request.session.get('client_id')))
    order_items = OrderItem.objects.filter(order__in=orders)
    total_sum = order_items.aggregate(total_sum=Sum(F('product__price') * F('quantity')))['total_sum'] or 0
    total_quantity = order_items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0

    context = {
        'order_items': order_items,
        'total_sum': total_sum,
        'total_quantity': total_quantity,
    }
    return render(request, 'app_kibershop/profile_page.html', context=context)


