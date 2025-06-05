from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import User, Restaurant, UserRestaurant, Dish, DishCart, DishInvoice, Rate, Invoice
import json
import uuid
from django.views.decorators.csrf import csrf_exempt
import base64
from django.utils import timezone
import MySQLdb
from django.conf import settings

def customer_home(request):
    return render(request, 'customerHome.html')


def dish_detail(request):
    return render(request, 'dishDetails.html')

def restaurant_view_details(request):
    return render(request, 'restaurantViewDetails.html')

def cart(request):
    return render(request, 'cart.html')

def shipping_order(request):
    return render(request, 'shippingOrder.html')

def order_history(request):
    return render(request, 'orderHistory.html')

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

def restaurant_owner_home(request):
    user_id = request.session.get('user_id')
    context = {}

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
        dishes = Dish.objects.filter(id_restaurant=restaurant.id, is_delected=False)
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
            context['dish_message'] = "Hiện tại nhà hàng chưa có món ăn nào"

    return render(request, 'restaurantOwnerHome.html', context)

def restaurant_pending_order(request):
    return render(request, 'restaurantPendingOrder.html')

def restaurant_shipping_order(request):
    return render(request, 'restaurantShippingOrder.html')

def shipping_orders_view(request):
    # Kết nối DB thủ công, không dùng ORM
    db = MySQLdb.connect(
        host=settings.DATABASES['default']['HOST'],
        user=settings.DATABASES['default']['USER'],
        passwd=settings.DATABASES['default']['PASSWORD'],
        db=settings.DATABASES['default']['NAME'],
        charset='utf8mb4'
    )
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    # Lấy các đơn hàng status=1
    cursor.execute("""
        SELECT i.id, i.time, i.total_payment, i.id_restaurant, i.id_customer
        FROM invoice i
        WHERE i.status = 1
        ORDER BY i.time ASC
    """)
    invoices = cursor.fetchall()
    orders = []
    for inv in invoices:
        # Lấy thông tin khách hàng
        customer = None
        if inv['id_customer']:
            cursor.execute("SELECT name, phone_number, street, district FROM user WHERE id=%s", (inv['id_customer'],))
            customer = cursor.fetchone()
        # Lấy các món ăn trong đơn
        cursor.execute("SELECT id FROM dish_invoice WHERE id_invoice=%s", (inv['id'],))
        dish_invoice_ids = [row['id'] for row in cursor.fetchall()]
        items = []
        for di_id in dish_invoice_ids:
            cursor.execute("SELECT id_dish_cart FROM dish_invoice WHERE id=%s", (di_id,))
            row = cursor.fetchone()
            if not row:
                continue
            dish_cart_id = row['id_dish_cart']
            cursor.execute("SELECT id_dish, quantity FROM dish_cart WHERE id=%s", (dish_cart_id,))
            cart = cursor.fetchone()
            if not cart:
                continue
            cursor.execute("SELECT name, price, unit FROM dish WHERE id=%s", (cart['id_dish'],))
            dish = cursor.fetchone()
            if dish:
                items.append({
                    'name': dish['name'],
                    'price': dish['price'],
                    'quantity': cart['quantity'],
                    'unit': dish['unit'],
                })
        orders.append({
            'customer_name': customer['name'] if customer else '',
            'phone': customer['phone_number'] if customer else '',
            'address': f"{customer['street']}, {customer['district']}" if customer else '',
            'order_time': inv['time'].strftime('%H:%M %d/%m/%Y') if inv['time'] else '',
            'total_payment': inv['total_payment'],
            'items': items,
        })
    cursor.close()
    db.close()
    return render(request, 'restaurantShippingOrder.html', {'orders': orders})

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

@csrf_exempt
def api_update_invoice_status(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        invoice_id = data.get('invoice_id')
        status = data.get('status')
        invoice = Invoice.objects.filter(id=invoice_id).first()
        if invoice and status in [1, 2]:
            invoice.status = status
            invoice.save(update_fields=['status'])
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'message': 'Không tìm thấy đơn hàng hoặc trạng thái không hợp lệ'})
    return JsonResponse({'success': False, 'message': 'Phương thức không hợp lệ'})
