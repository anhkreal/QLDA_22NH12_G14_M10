from django.shortcuts import render
from .models import Invoice, DishInvoice, DishCart, Dish, Restaurant, User, UserRestaurant

def shipping_orders_view_no_customer_id(request):
    """
    Hiển thị danh sách đơn hàng chờ xác nhận/nhận hàng KHÔNG kiểm tra customer_id,
    chỉ truyền các trường có sẵn, tránh KeyError.
    """
    orders = []
    user_id = request.session.get('user_id')
    invoices = list(Invoice.objects.filter(status__in=[0,1]).order_by('-status', 'time').select_related())
    for invoice in invoices:
        restaurant = Restaurant.objects.filter(id=invoice.id_restaurant).first()
        owner_phone = ''
        if restaurant:
            user_restaurant = UserRestaurant.objects.filter(id_restaurant=restaurant.id).first()
            if user_restaurant:
                owner = User.objects.filter(id=user_restaurant.id_user).first()
                if owner:
                    owner_phone = owner.phone_number
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        dishes = []
        customer = None
        customer_id = None
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            if not customer:
                customer = User.objects.filter(id=di.id_customer).first()
                customer_id = di.id_customer
            if dish and dish_cart:
                dishes.append({
                    'name': dish.name,
                    'quantity': dish_cart.quantity,
                    'price': dish.price,
                    'unit': dish.unit,
                })
        # Đảm bảo customer_id không phải None để tránh lỗi so sánh trong template
        if customer_id is not None:
            orders.append({
                'invoice_id': invoice.id,
                'restaurant_name': restaurant.name if restaurant else '',
                'owner_phone': owner_phone,
                'customer_phone': customer.phone_number if customer else '',
                'customer_address': f"{customer.street}, {customer.district}" if customer else '',
                'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
                'dishes': dishes,
                'total_payment': invoice.total_payment,
                'status': invoice.status,
                'customer_id': customer_id,
            })
    return render(request, 'shippingOrder.html', {'orders': orders, 'user': User.objects.filter(id=user_id).first()})
