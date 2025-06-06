from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import User, Restaurant, UserRestaurant, Dish, DishCart, DishInvoice, Rate, Invoice
import json
import uuid
from django.views.decorators.csrf import csrf_exempt
import base64
from django.utils import timezone
from django.db import connection, transaction
from django.contrib import messages
from django.views.decorators.http import require_POST
import unicodedata

def customer_home(request):
    query = request.GET.get('q', '')
    if query:
        restaurants = Restaurant.objects.filter(name__icontains=query, is_deleted=False)
    else:
        restaurants = Restaurant.objects.filter(is_deleted=False)
    return render(request, 'customerHome.html', {
        'restaurants': restaurants,
        'query': query
    })


def dish_detail(request):
    return render(request, 'dishDetails.html')

def restaurant_view_details(request):
    restaurant_id = request.GET.get('id')
    restaurant = Restaurant.objects.filter(id=restaurant_id, is_deleted=False).first()
    if not restaurant:
        return render(request, 'restaurantViewDetails.html', {'error': 'Không tìm thấy nhà hàng.'})
    # Lấy danh sách món ăn của nhà hàng
    dishes = Dish.objects.filter(id_restaurant=restaurant.id, is_delected=False)
    # Đếm số lượng món ăn
    num_dishes = dishes.count()
    # Đếm số lượng đánh giá và tính trung bình sao
    dish_ids = [dish.id for dish in dishes]
    dish_carts = DishCart.objects.filter(id_dish__in=dish_ids)
    dish_cart_ids = [dc.id for dc in dish_carts]
    dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
    rate_ids = [di.id_rate for di in dish_invoices if di.id_rate]
    rates = Rate.objects.filter(id__in=rate_ids)
    num_ratings = rates.count()
    avg_rating = round(sum(r.star for r in rates) / num_ratings, 2) if num_ratings > 0 else None
    return render(request, 'restaurantViewDetails.html', {
        'restaurant': restaurant,
        'dishes': dishes,
        'num_dishes': num_dishes,
        'num_ratings': num_ratings,
        'avg_rating': avg_rating
    })

def cart(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    # Lấy các dish_cart của user (giả sử DishInvoice liên kết user với dish_cart)
    dish_invoices = DishInvoice.objects.filter(id_customer=user_id, id_invoice__isnull=True)
    dish_cart_ids = [di.id_dish_cart for di in dish_invoices]
    dish_carts = DishCart.objects.filter(id__in=dish_cart_ids)
    # Lấy thông tin món ăn và nhà hàng
    dish_ids = [dc.id_dish for dc in dish_carts]
    dishes = {d.id: d for d in Dish.objects.filter(id__in=dish_ids, is_delected=False)}
    # Gộp theo nhà hàng
    restaurant_map = {}
    for dc in dish_carts:
        dish = dishes.get(dc.id_dish)
        if not dish:
            continue
        # Lấy nhà hàng
        rest_id = dish.id_restaurant
        if rest_id not in restaurant_map:
            restaurant = Restaurant.objects.filter(id=rest_id, is_deleted=False).first()
            if not restaurant:
                continue
            restaurant_map[rest_id] = {
                'restaurant': restaurant,
                'items': []
            }
        restaurant_map[rest_id]['items'].append({
            'dish_cart': dc,
            'dish': dish,
            'checked': dc.is_checked,
            'quantity': dc.quantity or 1,
        })
    # Tính tổng tiền các món được chọn
    total = 0
    for r in restaurant_map.values():
        for item in r['items']:
            if item['checked']:
                total += (item['dish'].price or 0) * (item['quantity'] or 1)
    context = {
        'restaurants': list(restaurant_map.values()),
        'total': total
    }
    return render(request, 'cart.html', context)

def shipping_order(request):
    return render(request, 'shippingOrder.html')

def order_history(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    # Lấy các hóa đơn đã hoàn tất (status=3) hoặc bị từ chối (status=2) của user
    invoices = Invoice.objects.filter(id_customer=user_id, status__in=[2, 3]).order_by('-time')
    orders = []
    for invoice in invoices:
        restaurant = Restaurant.objects.filter(id=invoice.id_restaurant).first()
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        dishes = []
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            # Kiểm tra trạng thái đánh giá
            rated = False
            rate = None
            if di.id_rate:
                rated = True
                rate = Rate.objects.filter(id=di.id_rate).first()
            dishes.append({
                'dish_invoice_id': di.id,
                'name': dish.name if dish else '',
                'quantity': dish_cart.quantity if dish_cart else 0,
                'unit': dish.unit if dish else '',
                'rated': rated,
                'star': rate.star if rate else 0,
                'comment': rate.comment if rate else '',
            })
        orders.append({
            'restaurant_name': restaurant.name if restaurant else '',
            'restaurant_phone': restaurant.id if restaurant else '',
            'restaurant_address': f"{restaurant.street}, {restaurant.district}" if restaurant else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'status': invoice.status,
            'dishes': dishes,
            'total_payment': invoice.total_payment,
        })
    return render(request, 'orderHistory.html', {'orders': orders})

def spending_statistics(request):
    return render(request, 'spendingStatistics.html')

def change_password(request):
    return render(request, 'changePassword.html')

def login(request):
    if request.method == "POST" and request.headers.get("Content-Type") == "application/json":
        try:
            data = json.loads(request.body)
            email = data.get("email", "").strip()
            password = data.get("password", "")
            if not email or not password:
                return JsonResponse({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})

            user = User.objects.filter(email=email, password=password, is_deleted=False).first()
            if not user:
                return JsonResponse({"success": False, "message": "Email hoặc mật khẩu không đúng!"})

            # Lưu thông tin đăng nhập vào session
            request.session['user_id'] = user.id
            request.session['user_name'] = user.name
            request.session['user_role'] = user.role

            # Điều hướng theo role và kiểm tra thông tin bổ sung
            if user.role == 0:
                # Khách hàng: kiểm tra district
                if not user.district or user.district.lower() in ['none', 'null', '']:
                    return JsonResponse({
                        "success": True,
                        "redirect_url": "/customer-info/",
                        "message": "Bạn hãy thêm mới vị trí mình để sử dụng đầy đủ dịch vụ web"
                    })
                else:
                    return JsonResponse({"success": True, "redirect_url": "/customer-home/"})
            elif user.role == 1:
                # Chủ nhà hàng: kiểm tra có nhà hàng chưa
                has_restaurant = UserRestaurant.objects.filter(id_user=user.id).exists()
                if not has_restaurant:
                    return JsonResponse({
                        "success": True,
                        "redirect_url": "/restaurant-info/",
                        "message": "Bạn hãy thêm mới nhà hàng của mình để sử dụng đầy đủ dịch vụ web"
                    })
                else:
                    return JsonResponse({"success": True, "redirect_url": "/restaurant-owner-home/"})
            else:
                return JsonResponse({"success": False, "message": "Tài khoản không hợp lệ!"})
        except Exception as e:
            return JsonResponse({"success": False, "message": "Đăng nhập thất bại!"})
    else:
        return render(request, 'login.html')

def register(request):
    if request.method == "POST" and request.headers.get("Content-Type") == "application/json":
        try:
            data = json.loads(request.body)
            name = data.get("name", "").strip()
            email = data.get("email", "").strip()
            phone = data.get("phone_number", "").strip()
            password = data.get("password", "")
            role = int(data.get("role", 0))

            # Kiểm tra nhập đủ
            if not name or not email or not phone or not password:
                return JsonResponse({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})

            # Kiểm tra trùng email hoặc số điện thoại
            if User.objects.filter(email=email).exists():
                return JsonResponse({"success": False, "message": "Email đã được sử dụng!"})
            if User.objects.filter(phone_number=phone).exists():
                return JsonResponse({"success": False, "message": "Số điện thoại đã được sử dụng!"})

            # Tạo id mới
            user_id = str(uuid.uuid4())
            User.objects.create(
                id=user_id,
                name=name,
                email=email,
                phone_number=phone,
                password=password,
                role=role,
                is_deleted=False
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "message": "Đăng ký thất bại!"})
    else:
        return render(request, 'register.html')

def customer_info(request):
    return render(request, 'customerInfo.html')

def remove_accents(input_str):
    if not input_str:
        return ''
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

def restaurant_owner_home(request):
    user_id = request.session.get('user_id')
    context = {}

    # Lấy từ khóa tìm kiếm
    query = request.GET.get('q', '').strip()
    context['query'] = query

    # Truy vấn user_restaurant
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    if not user_restaurant:
        context['restaurant'] = None
        context['dishes'] = []
        context['restaurant_message'] = "Bạn cần thêm mới nhà hàng để được sử dụng đầy đủ dịch vụ"
    else:
        # Lấy thông tin nhà hàng
        restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
        context['restaurant'] = restaurant

        # Lấy danh sách món ăn của nhà hàng chỉ lấy is_delected=False hoặc 0
        all_dishes = Dish.objects.filter(id_restaurant=restaurant.id, is_delected=False)
        # Nếu có từ khóa tìm kiếm thì lọc theo tên hoặc mô tả (không dấu, không phân biệt hoa thường)
        if query:
            query_no_accents = remove_accents(query)
            filtered_dishes = []
            for dish in all_dishes:
                name_no_accents = remove_accents(dish.name)
                desc_no_accents = remove_accents(dish.decription)
                if query_no_accents in name_no_accents or query_no_accents in desc_no_accents:
                    filtered_dishes.append(dish)
            dishes = filtered_dishes
        else:
            dishes = list(all_dishes)

        dish_list = []
        for dish in dishes:
            # Truy vấn dish_cart cho từng dish
            dish_carts = DishCart.objects.filter(id_dish=dish.id)
            # Tính tổng số lượng mua
            total_quantity = sum(dc.quantity or 0 for dc in dish_carts)
            # Truy vấn dish_invoice cho từng dish_cart
            dish_cart_ids = [dc.id for dc in dish_carts]
            dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
            # Đếm số lượng đánh giá và tính trung bình sao
            rate_ids = [di.id_rate for di in dish_invoices if di.id_rate]
            rates = Rate.objects.filter(id__in=rate_ids)
            num_ratings = rates.count()
            avg_rating = round(sum(r.star for r in rates) / num_ratings, 2) if num_ratings > 0 else None

            dish_list.append({
                'dish': dish,
                'total_quantity': total_quantity,
                'num_ratings': num_ratings,
                'avg_rating': avg_rating,
            })
        context['dishes'] = dish_list
        if not dish_list:
            if query:
                context['dish_message'] = "Không có món ăn nào phù hợp với từ khóa tìm kiếm."
            else:
                context['dish_message'] = "Hiện tại nhà hàng chưa có món ăn nào"

    return render(request, 'restaurantOwnerHome.html', context)

def restaurant_pending_order(request):
    return render(request, 'restaurantPendingOrder.html')

def restaurant_shipping_order(request):
    return render(request, 'restaurantShippingOrder.html')

def shipping_orders_view(request):
    from .models import Invoice, DishInvoice, DishCart, Dish, Restaurant, User
    orders = []
    # Lấy đơn hàng chờ nhận hàng (status=1) trước
    invoices = list(Invoice.objects.filter(status__in=[0,1]).order_by('-status', 'time').select_related())
    for invoice in invoices:
        # Lấy nhà hàng
        restaurant = Restaurant.objects.filter(id=invoice.id_restaurant).first()
        # Lấy các dish_invoice
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        dishes = []
        customer = None
        hide_order = False
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            if not customer:
                customer = User.objects.filter(id=di.id_customer).first()
            if dish and dish_cart:
                # Nếu là đơn chờ nhận hàng, kiểm tra món bị xóa
                if invoice.status == 1 and dish.is_delected:
                    hide_order = True
                    break
                dishes.append({
                    'name': dish.name,
                    'quantity': dish_cart.quantity,
                    'price': dish.price,
                    'unit': dish.unit,
                })
        # Nếu là đơn chờ nhận hàng và có món bị xóa, cập nhật status=2 và bỏ qua
        if invoice.status == 1 and hide_order:
            invoice.status = 2
            invoice.save(update_fields=['status'])
            continue
        orders.append({
            'invoice_id': invoice.id,
            'restaurant_name': restaurant.name if restaurant else '',
            'customer_phone': customer.phone_number if customer else '',
            'customer_address': f"{customer.street}, {customer.district}" if customer else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'dishes': dishes,
            'total_payment': invoice.total_payment,
            'status': invoice.status,
        })
    return render(request, 'shippingOrder.html', {'orders': orders})

def restaurant_order_history(request):
    user_id = request.session.get('user_id')
    # Lấy id nhà hàng của chủ nhà hàng
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    if not user_restaurant:
        return render(request, 'restaurantOrderHistory.html', {'orders': []})
    restaurant_id = user_restaurant.id_restaurant
    # Lấy các hóa đơn đã hoàn tất của nhà hàng này
    invoices = Invoice.objects.filter(id_restaurant=restaurant_id, status=2).order_by('-time')
    orders = []
    for invoice in invoices:
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        dishes = []
        customer = None
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            if not customer:
                customer = User.objects.filter(id=di.id_customer).first()
            if dish and dish_cart:
                dishes.append({
                    'name': dish.name,
                    'quantity': dish_cart.quantity,
                    'price': dish.price,
                    'unit': dish.unit,
                })
        orders.append({
            'customer_name': customer.name if customer else '',
            'customer_phone': customer.phone_number if customer else '',
            'customer_address': f"{customer.street}, {customer.district}" if customer else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'dishes': dishes,
            'total_payment': invoice.total_payment,
        })
    return render(request, 'restaurantOrderHistory.html', {'orders': orders})

def revenue_statistics(request):
    return render(request, 'revenueStatistics.html')

def restaurant_info(request):
    user_id = request.session.get('user_id')
    context = {}
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    restaurant = None
    if user_restaurant:
        restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
    context['restaurant'] = restaurant

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        street = request.POST.get('street', '').strip()
        district = request.POST.get('district', '').strip()
        description = request.POST.get('description', '').strip()
        image_file = request.FILES.get('image')
        # Kiểm tra hợp lệ
        if not name or not street or not district or not description:
            return JsonResponse({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})

        # Xử lý ảnh
        image_data = None
        if image_file:
            image_data = image_file.read()

        if not user_restaurant:
            # Thêm mới
            restaurant_id = str(uuid.uuid4())
            Restaurant.objects.create(
                id=restaurant_id,
                name=name,
                street=street,
                district=district,
                decription=description,
                image=image_data,
                is_deleted=False
            )
            UserRestaurant.objects.create(
                id=str(uuid.uuid4()),
                id_user=user_id,
                id_restaurant=restaurant_id
            )
            return JsonResponse({"success": True, "message": "Thêm mới thành công!"})
        else:
            # Cập nhật
            restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
            if not restaurant:
                return JsonResponse({"success": False, "message": "Không tìm thấy nhà hàng để cập nhật!"})
            restaurant.name = name
            restaurant.street = street
            restaurant.district = district
            restaurant.decription = description
            if image_data:
                restaurant.image = image_data
            restaurant.save()
            return JsonResponse({"success": True, "message": "Cập nhật thành công!"})

    return render(request, 'restaurantInfo.html', context)

def restaurant_owner_info(request):
    return render(request, 'restaurantOwnerInfo.html')

@csrf_exempt
def logout(request):
    request.session.flush()
    return JsonResponse({"success": True})

def restaurant_owner_change_password(request):
    return render(request, 'restaurantOwnerChangePassword.html')

@csrf_exempt
def api_add_dish(request):
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        price = request.POST.get('price', '').strip()
        unit = request.POST.get('unit', '').strip()
        decription = request.POST.get('decription', '').strip()
        id_restaurant = request.POST.get('id_restaurant', '').strip()
        image_file = request.FILES.get('image')

        # Kiểm tra hợp lệ phía backend (bảo vệ tối thiểu)
        if not name or not price or not unit or not decription or not id_restaurant or not image_file:
            return JsonResponse({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})
        try:
            price = int(price)
            if price <= 0:
                return JsonResponse({"success": False, "message": "Giá phải là số dương!"})
        except:
            return JsonResponse({"success": False, "message": "Giá không hợp lệ!"})

        if not image_file.content_type.startswith('image/'):
            return JsonResponse({"success": False, "message": "File không phải là ảnh!"})

        image_data = image_file.read()
        dish_id = str(uuid.uuid4())
        Dish.objects.create(
            id=dish_id,
            name=name,
            decription=decription,
            price=price,
            unit=unit,
            image=image_data,
            id_restaurant=id_restaurant,
            is_delected=False
        )
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "message": "Phương thức không hợp lệ!"})

@csrf_exempt
def api_update_dish(request):
    if request.method == "POST":
        dish_id = request.POST.get('id', '').strip()
        name = request.POST.get('name', '').strip()
        price = request.POST.get('price', '').strip()
        unit = request.POST.get('unit', '').strip()
        decription = request.POST.get('decription', '').strip()
        image_file = request.FILES.get('image')
        if not dish_id or not name or not price or not unit or not decription:
            return JsonResponse({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})
        try:
            price = int(price)
            if price <= 0:
                return JsonResponse({"success": False, "message": "Giá phải là số dương!"})
        except:
            return JsonResponse({"success": False, "message": "Giá không hợp lệ!"})
        dish = Dish.objects.filter(id=dish_id).first()
        if not dish:
            return JsonResponse({"success": False, "message": "Không tìm thấy món ăn!"})
        dish.name = name
        dish.price = price
        dish.unit = unit
        dish.decription = decription
        if image_file:
            if not image_file.content_type.startswith('image/'):
                return JsonResponse({"success": False, "message": "File không phải là ảnh!"})
            dish.image = image_file.read()
        dish.save()
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "message": "Phương thức không hợp lệ!"})

@csrf_exempt
def api_delete_dish(request):
    if request.method == "POST":
        dish_id = request.POST.get('id', '').strip()
        if not dish_id:
            return JsonResponse({"success": False, "message": "Thiếu id món ăn!"})
        dish = Dish.objects.filter(id=dish_id).first()
        if not dish:
            return JsonResponse({"success": False, "message": "Không tìm thấy món ăn!"})
        dish.is_delected = True
        dish.save()
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "message": "Phương thức không hợp lệ!"})

@csrf_exempt
def api_dish_reviews(request):
    dish_id = request.GET.get('dish_id')
    reviews = []
    if dish_id:
        # Lấy các dish_cart của dish này
        dish_carts = DishCart.objects.filter(id_dish=dish_id)
        dish_cart_ids = [dc.id for dc in dish_carts]
        # Lấy các dish_invoice đã có id_invoice (đã đặt hàng)
        dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
        # Lấy các đánh giá (rate) liên quan
        for di in dish_invoices:
            if di.id_rate:
                rate = Rate.objects.filter(id=di.id_rate).first()
                if rate:
                    # Lấy thông tin khách hàng và thời gian đặt hàng
                    customer = User.objects.filter(id=di.id_customer).first()
                    invoice = None
                    if di.id_invoice:
                        invoice = Invoice.objects.filter(id=di.id_invoice).first()
                    reviews.append({
                        "customer": customer.phone_number if customer else "Ẩn danh",
                        "star": rate.star,
                        "comment": rate.comment,
                        "time": invoice.time.strftime("%H:%M %d/%m/%Y") if invoice and invoice.time else "",
                        "address": customer.street + ", " + customer.district if customer and customer.street and customer.district else "",
                    })
    return JsonResponse({"success": True, "reviews": reviews})

def api_update_invoice_status(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        invoice_id = data.get('invoice_id')
        status = data.get('status')
        with transaction.atomic():
            invoice = Invoice.objects.filter(id=invoice_id).first()
            if invoice and status in [1, 2]:
                invoice.status = status
                invoice.save(update_fields=['status'])
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'message': 'Không tìm thấy đơn hàng hoặc trạng thái không hợp lệ'})
    return JsonResponse({'success': False, 'message': 'Phương thức không hợp lệ'})

def pending_orders_view(request):
    orders = []
    with connection.cursor() as cursor:
        cursor.execute('''
            SELECT i.id, i.time, i.total_payment, i.id_customer
            FROM invoice i
            WHERE i.status = 0
            ORDER BY i.time ASC
        ''')
        invoices = cursor.fetchall()
        for inv in invoices:
            invoice_id, order_time, total_payment, customer_id = inv
            # Lấy thông tin khách hàng
            customer = None
            if customer_id:
                cursor.execute('SELECT first_name, last_name, email FROM auth_user WHERE id = %s', [customer_id])
                customer = cursor.fetchone()
            # Lấy danh sách món ăn
            cursor.execute('''
                SELECT d.name, dc.quantity, d.price, d.unit
                FROM dish_invoice di
                JOIN dish_cart dc ON di.id_dish_cart = dc.id
                JOIN dish d ON dc.id_dish = d.id
                WHERE di.id_invoice = %s
            ''', [invoice_id])
            items = [
                {
                    'name': row[0],
                    'quantity': row[1],
                    'price': row[2],
                    'unit': row[3],
                } for row in cursor.fetchall()
            ]
            orders.append({
                'invoice_id': invoice_id,
                'customer_name': (customer[0] + ' ' + customer[1]) if customer else '',
                'customer_phone': customer[2] if customer else '',
                'customer_address': '',  # Nếu có trường địa chỉ thì lấy thêm
                'order_time': order_time.strftime('%H:%M %d/%m/%Y') if order_time else '',
                'dishes': items,
                'total_payment': total_payment,
            })
    return render(request, 'restaurantPendingOrder.html', {'orders': orders})

def confirm_pending_order(request, invoice_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute('UPDATE invoice SET status = 1 WHERE id = %s', [invoice_id])
        messages.success(request, 'Đã xác nhận đơn hàng!')
    return redirect('pending-orders')

def reject_pending_order(request, invoice_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute('UPDATE invoice SET status = -1 WHERE id = %s', [invoice_id])
        messages.success(request, 'Đã từ chối đơn hàng!')
    return redirect('pending-orders')

@csrf_exempt
def api_submit_rating(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        dish_invoice_id = data.get('dish_invoice_id')
        star = int(data.get('star', 0))
        comment = data.get('comment', '').strip()
        user_id = request.session.get('user_id')
        if not (dish_invoice_id and 1 <= star <= 5 and user_id):
            return JsonResponse({'success': False, 'message': 'Thiếu thông tin hoặc số sao không hợp lệ!'})
        dish_invoice = DishInvoice.objects.filter(id=dish_invoice_id, id_customer=user_id).first()
        if not dish_invoice:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy món ăn trong đơn hàng!'})
        if dish_invoice.id_rate:
            return JsonResponse({'success': False, 'message': 'Bạn đã đánh giá món này!'})
        rate_id = str(uuid.uuid4())
        rate = Rate.objects.create(id=rate_id, star=star, comment=comment)
        dish_invoice.id_rate = rate_id
        dish_invoice.save(update_fields=['id_rate'])
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': 'Phương thức không hợp lệ!'})

def restaurant_list(request):
    query = request.GET.get('q', '')
    if query:
        restaurants = Restaurant.objects.filter(name__icontains=query, is_deleted=False)
    else:
        restaurants = Restaurant.objects.filter(is_deleted=False)
    return render(request, 'restaurant_list.html', {
        'restaurants': restaurants,
        'query': query
    })

@csrf_exempt
@require_POST
def api_delete_cart_item(request):
    dish_cart_id = request.POST.get('dish_cart_id')
    user_id = request.session.get('user_id')
    if not dish_cart_id or not user_id:
        return JsonResponse({'success': False, 'message': 'Thiếu thông tin.'})
    # Chỉ xóa dish_invoice của user hiện tại và chưa có invoice (chưa đặt hàng)
    deleted = DishInvoice.objects.filter(id_dish_cart=dish_cart_id, id_customer=user_id, id_invoice__isnull=True).delete()
    return JsonResponse({'success': True})
