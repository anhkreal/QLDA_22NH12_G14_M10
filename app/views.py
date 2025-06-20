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
from collections import defaultdict
from datetime import datetime, timedelta
from django.db import models  # <-- Thêm dòng này để fix lỗi NameError

def customer_home(request):
    query = request.GET.get('q', '')
    user_id = request.session.get('user_id')
    user = User.objects.filter(id=user_id).first() if user_id else None

    # Tìm kiếm nhà hàng và món ăn theo từ khóa
    restaurants = Restaurant.objects.filter(is_deleted=False)
    dishes = Dish.objects.filter(is_delected=False)
    if query:
        # Lọc nhà hàng theo tên chứa từ khóa
        restaurants = restaurants.filter(name__icontains=query)
        # Lọc món ăn theo tên chứa từ khóa hoặc tên nhà hàng chứa từ khóa
        dishes = dishes.filter(
            models.Q(name__icontains=query) |
            models.Q(id_restaurant__in=Restaurant.objects.filter(name__icontains=query).values_list('id', flat=True))
        )
    else:
        # Nếu không tìm kiếm, lấy 10 món phổ biến (ưu tiên cùng quận)
        if user and user.district:
            same_district_restaurants = Restaurant.objects.filter(district=user.district, is_deleted=False)
            same_district_dishes = Dish.objects.filter(id_restaurant__in=[r.id for r in same_district_restaurants], is_delected=False)
            other_dishes = Dish.objects.exclude(id__in=[d.id for d in same_district_dishes]).filter(is_delected=False)
            dishes = list(same_district_dishes[:10])
            if len(dishes) < 10:
                dishes += list(other_dishes[:10-len(dishes)])
        else:
            dishes = list(Dish.objects.filter(is_delected=False)[:10])

    return render(request, 'customerHome.html', {
        'restaurants': restaurants,
        'query': query,
        'dishes': dishes,
        'user': user
    })


def dish_detail(request):
    dish_id = request.GET.get('id')
    user_id = request.session.get('user_id')
    user = User.objects.filter(id=user_id).first() if user_id else None
    dish = Dish.objects.filter(id=dish_id, is_delected=False).first()
    restaurant = None
    avg_star = 0
    sold = 0
    if dish:
        restaurant = Restaurant.objects.filter(id=dish.id_restaurant, is_deleted=False).first()
        # Lấy các dish_cart của món này
        dish_carts = DishCart.objects.filter(id_dish=dish.id)
        dish_cart_ids = [dc.id for dc in dish_carts]
        # Lấy các dish_invoice đã có invoice
        dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
        # Lấy các id_invoice duy nhất
        invoice_ids = [di.id_invoice for di in dish_invoices if di.id_invoice]
        # Lấy các invoice hoàn tất (status=2)
        paid_invoices = Invoice.objects.filter(id__in=invoice_ids, status=2)
        paid_invoice_ids = set(inv.id for inv in paid_invoices)
        # Chỉ lấy các dish_invoice có invoice status=2
        paid_dish_invoices = [di for di in dish_invoices if di.id_invoice in paid_invoice_ids]
        paid_dish_cart_ids = [di.id_dish_cart for di in paid_dish_invoices]
        paid_dish_carts = DishCart.objects.filter(id__in=paid_dish_cart_ids)
        sold = sum(dc.quantity or 0 for dc in paid_dish_carts)
        # Đánh giá
        rate_ids = [di.id_rate for di in paid_dish_invoices if di.id_rate]
        rates = Rate.objects.filter(id__in=rate_ids).order_by('-id')[:10]
        if rate_ids:
            avg_star = Rate.objects.filter(id__in=rate_ids).aggregate(avg=models.Avg('star'))['avg'] or 0
        reviews = []
        for rate in rates:
            di = next((di for di in paid_dish_invoices if di.id_rate == rate.id), None)
            customer = User.objects.filter(id=di.id_customer).first() if di else None
            reviews.append({
                'star': rate.star,
                'comment': rate.comment,
                'customer': customer.phone_number if customer else 'Ẩn danh',
            })
    else:
        reviews = []
    return render(request, 'dishDetails.html', {
        'dish': dish,
        'restaurant': restaurant,
        'reviews': reviews,
        'user': user,
        'avg_star': avg_star,
        'sold': sold,
    })

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
    # Lấy tất cả hóa đơn hoàn tất (status=3) hoặc bị từ chối (status=2)
    invoices = Invoice.objects.filter(status__in=[2, 3]).order_by('-time')
    orders = []
    for invoice in invoices:
        # Kiểm tra user có phải là khách hàng của hóa đơn này không
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id, id_customer=user_id)
        if not dish_invoices.exists():
            continue
        restaurant = Restaurant.objects.filter(id=invoice.id_restaurant).first()
        # Lấy chủ nhà hàng
        owner_phone = ''
        if restaurant:
            user_restaurant = UserRestaurant.objects.filter(id_restaurant=restaurant.id).first()
            if user_restaurant:
                owner = User.objects.filter(id=user_restaurant.id_user).first()
                if owner:
                    owner_phone = owner.phone_number
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
            'owner_phone': owner_phone,
            'restaurant_address': f"{restaurant.street}, {restaurant.district}" if restaurant else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'status': invoice.status,
            'dishes': dishes,
            'total_payment': invoice.total_payment,
        })
    return render(request, 'orderHistory.html', {'orders': orders})

from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from collections import defaultdict
import json

def spending_statistics(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    user = User.objects.filter(id=user_id).first()
    if not user or user.role != 0:
        return redirect('login')

    # 1. Truy vấn tất cả các hóa đơn hoàn tất (status=2, id_deleted=False)
    invoices = Invoice.objects.filter(status=2, id_deleted=False)
    print(f"[spending_statistics] Step 1: Found {invoices.count()} invoices with status=2 and id_deleted=False")

    total_orders = 0
    total_spending = 0

    # 2. Với mỗi hóa đơn, kiểm tra xem có món ăn hóa đơn nào thuộc về khách hàng này không
    for invoice in invoices:
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        print(f"[spending_statistics] Step 2: Invoice {invoice.id} has {dish_invoices.count()} dish_invoices")
        # Kiểm tra có ít nhất 1 dish_invoice của khách hàng này không
        if dish_invoices.filter(id_customer=user_id).exists():
            print(f"[spending_statistics] Step 3: Invoice {invoice.id} contains dish_invoice for user {user_id}")
            total_orders += 1
            total_spending += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
        else:
            print(f"[spending_statistics] Step 3: Invoice {invoice.id} does NOT contain dish_invoice for user {user_id}")

    # ...existing code for chart/statistics...
    today = datetime.now().date()
    daily_order_count = defaultdict(int)
    for invoice in invoices:
        # Chỉ tính ngày cho các hóa đơn mà khách hàng này đã đặt
        if invoice.time and DishInvoice.objects.filter(id_invoice=invoice.id, id_customer=user_id).exists():
            invoice_date = invoice.time.date()
            if (today - invoice_date).days <= 30:
                daily_order_count[invoice_date] += 1
    print(f"[spending_statistics] Step 4: daily_order_count = {dict(daily_order_count)}")
    day_labels = []
    day_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        day_labels.append(date.strftime('%d/%m'))
        day_data.append(daily_order_count.get(date, 0))
    print(f"[spending_statistics] Step 5: day_labels = {day_labels}")
    print(f"[spending_statistics] Step 5: day_data = {day_data}")

    weekly_order_count = defaultdict(int)
    for invoice in invoices:
        if invoice.time and DishInvoice.objects.filter(id_invoice=invoice.id, id_customer=user_id).exists():
            invoice_date = invoice.time.date()
            if (today - invoice_date).days <= 84:
                year, week, _ = invoice_date.isocalendar()
                week_key = f"{year}-W{week:02d}"
                weekly_order_count[week_key] += 1
    print(f"[spending_statistics] Step 6: weekly_order_count = {dict(weekly_order_count)}")
    week_labels = []
    week_data = []
    for i in range(11, -1, -1):
        date = today - timedelta(weeks=i)
        year, week, _ = date.isocalendar()
        week_key = f"{year}-W{week:02d}"
        week_labels.append(f"Tuần {week}/{year}")
        week_data.append(weekly_order_count.get(week_key, 0))
    print(f"[spending_statistics] Step 7: week_labels = {week_labels}")
    print(f"[spending_statistics] Step 7: week_data = {week_data}")

    print(f"[spending_statistics] Step 8: total_orders = {total_orders}, total_spending = {total_spending}")

    context = {
        'day_labels': json.dumps(day_labels),
        'day_data': json.dumps(day_data),
        'week_labels': json.dumps(week_labels),
        'week_data': json.dumps(week_data),
        'total_spending': total_spending,
        'total_orders': total_orders,
        'user': user
    }
    return render(request, 'spendingStatistics.html', context)

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
    if request.method == 'GET':
        # Lấy thông tin user từ session
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('login')

        user = User.objects.filter(id=user_id).first()
        if not user:
            return redirect('login')

        context = {
            'user': user
        }
        return render(request, 'customerInfo.html', context)

    elif request.method == 'POST':
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"success": False, "message": "Vui lòng đăng nhập"})

        try:
            # Lấy dữ liệu từ form
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()
            street = request.POST.get('street', '').strip()
            district = request.POST.get('district', '').strip()

            # Validate dữ liệu
            if not name:
                return JsonResponse({"success": False, "message": "Họ và tên không được để trống"})
            if not phone:
                return JsonResponse({"success": False, "message": "Số điện thoại không được để trống"})
            if not street:
                return JsonResponse({"success": False, "message": "Tên đường không được để trống"})
            if not district:
                return JsonResponse({"success": False, "message": "Quận không được để trống"})

            # Cập nhật thông tin user
            user = User.objects.filter(id=user_id).first()
            if user:
                user.name = name
                user.phone_number = phone
                user.street = street
                user.district = district
                user.save()

                return JsonResponse({"success": True, "message": "Cập nhật thông tin thành công"})
            else:
                return JsonResponse({"success": False, "message": "Không tìm thấy thông tin người dùng"})

        except Exception as e:
            return JsonResponse({"success": False, "message": f"Có lỗi xảy ra: {str(e)}"})

    return JsonResponse({"success": False, "message": "Phương thức không được hỗ trợ"})

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
            dish_cart_ids = [dc.id for dc in dish_carts]
            # Lấy các dish_invoice liên quan đến dish_cart
            dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
            # Lọc các dish_invoice có invoice.status=2
            invoice_ids = [di.id_invoice for di in dish_invoices if di.id_invoice]
            paid_invoices = Invoice.objects.filter(id__in=invoice_ids, status=2)
            paid_invoice_ids = set(inv.id for inv in paid_invoices)
            paid_dish_invoices = [di for di in dish_invoices if di.id_invoice in paid_invoice_ids]
            # Tính tổng số lượng mua chỉ từ các dish_invoice có invoice.status=2
            paid_dish_cart_ids = [di.id_dish_cart for di in paid_dish_invoices]
            paid_dish_carts = DishCart.objects.filter(id__in=paid_dish_cart_ids)
            total_quantity = sum(dc.quantity or 0 for dc in paid_dish_carts)
            # Đếm số lượng đánh giá và tính trung bình sao
            rate_ids = [di.id_rate for di in paid_dish_invoices if di.id_rate]
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
    user_id = request.session.get('user_id')
    # Lấy id nhà hàng của chủ nhà hàng
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    if not user_restaurant:
        return render(request, 'restaurantShippingOrder.html', {'orders': []})
    restaurant_id = user_restaurant.id_restaurant
    # Lấy các hóa đơn đang giao (status=1) của nhà hàng này
    invoices = Invoice.objects.filter(id_restaurant=restaurant_id, status=1).order_by('-time')
    orders = []
    for invoice in invoices:
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        items = []
        customer = None
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            if not customer:
                customer = User.objects.filter(id=di.id_customer).first()
            if dish and dish_cart:
                items.append({
                    'name': dish.name,
                    'quantity': dish_cart.quantity,
                    'price': dish.price,
                    'unit': dish.unit,
                })
        orders.append({
            'customer_name': customer.name if customer else '',
            'phone': customer.phone_number if customer else '',
            'address': f"{customer.street}, {customer.district}" if customer else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'items': items,
            'total_payment': invoice.total_payment,
            'status': invoice.status,
        })
    return render(request, 'restaurantShippingOrder.html', {'orders': orders})

def revenue_statistics(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    user = User.objects.filter(id=user_id).first()
    if not user or user.role != 1:
        return redirect('login')

    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    if not user_restaurant:
        return redirect('restaurant-info')

    restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
    if not restaurant:
        return redirect('restaurant-info')

    # Debug: In ra id nhà hàng và kiểu dữ liệu
    print(f"[DEBUG] restaurant.id = {restaurant.id} ({type(restaurant.id)})")

    # Debug: In ra tất cả các invoice trong DB (id, id_restaurant, type)
    all_invoices = Invoice.objects.all()
    print("[DEBUG] All invoices in DB:")
    for inv in all_invoices:
        print(f"  Invoice id={inv.id}, id_restaurant={inv.id_restaurant} ({type(inv.id_restaurant)})")

    # Debug: So sánh id_restaurant trong DB với id nhà hàng hiện tại
    matching_invoices = []
    for inv in all_invoices:
        if str(inv.id_restaurant) == str(restaurant.id):
            matching_invoices.append(inv)
    print(f"[DEBUG] Số lượng invoice có id_restaurant == restaurant.id: {len(matching_invoices)}")

    # Debug: In ra các giá trị id_deleted của các invoice trùng id_restaurant
    print("[DEBUG] id_deleted values for matching invoices:")
    for inv in matching_invoices:
        print(f"  Invoice id={inv.id}, id_deleted={inv.id_deleted}")

    # Lấy tất cả invoice của nhà hàng (không bị xóa)
    invoices = Invoice.objects.filter(id_restaurant=restaurant.id, id_deleted=False)
    print(f"[revenue_statistics] Tổng số hóa đơn: {invoices.count()}")

    # Tổng doanh thu và tổng đơn hàng
    total_orders = invoices.count()
    total_revenue = 0
    for invoice in invoices:
        payment = invoice.total_payment or 0
        shipping = invoice.shipping_fee or 0
        total_revenue += payment + shipping
        print(f"[revenue_statistics] Invoice {invoice.id}: payment={payment}, shipping={shipping}, subtotal={payment+shipping}")
    print(f"[revenue_statistics] Tổng doanh thu: {total_revenue}")

    # Thống kê doanh thu theo ngày (30 ngày gần nhất)
    today = datetime.now().date()
    daily_revenue = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            if (today - invoice_date).days <= 30:
                daily_revenue[invoice_date] += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
    day_labels = []
    day_data = []
    for i in range(30, -1, -1):
        d = today - timedelta(days=i)
        day_labels.append(d.strftime('%d/%m'))
        day_data.append(daily_revenue.get(d, 0))

    # Thống kê doanh thu theo tuần (12 tuần gần nhất)
    weekly_revenue = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            if (today - invoice_date).days <= 84:
                year, week, _ = invoice_date.isocalendar()
                week_key = f"{year}-W{week:02d}"
                weekly_revenue[week_key] += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
    week_labels = []
    week_data = []
    for i in range(11, -1, -1):
        d = today - timedelta(weeks=i)
        year, week, _ = d.isocalendar()
        week_key = f"{year}-W{week:02d}"
        week_labels.append(f"Tuần {week}/{year}")
        week_data.append(weekly_revenue.get(week_key, 0))

    # Thống kê doanh thu theo tháng (12 tháng gần nhất)
    monthly_revenue = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            if (today - invoice_date).days <= 365:
                ym = f"{invoice_date.year}-{invoice_date.month:02d}"
                monthly_revenue[ym] += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
    month_labels = []
    month_data = []
    current = today.replace(day=1)
    for i in range(11, -1, -1):
        if current.month - i <= 0:
            year = current.year - 1
            month = 12 + (current.month - i)
        else:
            year = current.year
            month = current.month - i
        ym = f"{year}-{month:02d}"
        month_labels.append(f"{month:02d}/{year}")
        month_data.append(monthly_revenue.get(ym, 0))

    # Thống kê doanh thu theo năm (tất cả các năm có dữ liệu)
    yearly_revenue = defaultdict(int)
    years_with_data = set()
    for invoice in invoices:
        if invoice.time:
            y = invoice.time.year
            years_with_data.add(y)
            yearly_revenue[str(y)] += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
    year_labels = []
    year_data = []
    if years_with_data:
        for y in sorted(years_with_data):
            year_labels.append(str(y))
            year_data.append(yearly_revenue.get(str(y), 0))
    else:
        year_labels.append(str(today.year))
        year_data.append(0)

    # Dữ liệu chi tiết theo từng năm (doanh thu từng tháng trong năm)
    yearly_detail_data = {}
    for y in sorted(years_with_data):
        monthly = defaultdict(int)
        for invoice in invoices:
            if invoice.time and invoice.time.year == y:
                m = invoice.time.month
                monthly[m] += (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
        labels = [f"Tháng {m}" for m in range(1, 13)]
        data = [monthly.get(m, 0) for m in range(1, 13)]
        yearly_detail_data[str(y)] = {'labels': labels, 'data': data}

    # Top 5 món ăn bán chạy nhất (theo doanh thu)
    invoice_ids = [inv.id for inv in invoices]
    dish_invoices = DishInvoice.objects.filter(id_invoice__in=invoice_ids)
    dish_sales = defaultdict(int)
    dish_revenue = defaultdict(int)
    for di in dish_invoices:
        dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
        if dish_cart:
            dish = Dish.objects.filter(id=dish_cart.id_dish).first()
            if dish:
                qty = dish_cart.quantity or 0
                dish_sales[dish.name] += qty
                dish_revenue[dish.name] += qty * (dish.price or 0)
    top_dishes = sorted(dish_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

    # Đánh giá trung bình và tổng số đánh giá
    restaurant_dishes = Dish.objects.filter(id_restaurant=restaurant.id)
    dish_ids = [d.id for d in restaurant_dishes]
    dish_carts = DishCart.objects.filter(id_dish__in=dish_ids)
    dish_cart_ids = [dc.id for dc in dish_carts]
    rated_dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_rate__isnull=True).exclude(id_rate__exact='')
    total_ratings = 0
    rating_sum = 0
    for di in rated_dish_invoices:
        rate = Rate.objects.filter(id=di.id_rate).first()
        if rate:
            total_ratings += 1
            rating_sum += rate.star
    avg_rating = round(rating_sum / total_ratings, 2) if total_ratings > 0 else 0

    context = {
        'day_labels': json.dumps(day_labels),
        'day_data': json.dumps(day_data),
        'week_labels': json.dumps(week_labels),
        'week_data': json.dumps(week_data),
        'month_labels': json.dumps(month_labels),
        'month_data': json.dumps(month_data),
        'year_labels': json.dumps(year_labels),
        'year_data': json.dumps(year_data),
        'yearly_detail_data': json.dumps(yearly_detail_data),
        'available_years': sorted(years_with_data, reverse=True) if years_with_data else [today.year],
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'top_dishes': top_dishes,
        'avg_rating': avg_rating,
        'total_ratings': total_ratings,
        'restaurant': restaurant,
        'user': user
    }
    return render(request, 'revenueStatistics.html', context)
def shipping_orders_view(request):
    from .models import Invoice, DishInvoice, DishCart, Dish, Restaurant, User, UserRestaurant
    orders = []
    user_id = request.session.get('user_id')
    # Lấy đơn hàng chờ nhận hàng (status=1) trước
    invoices = list(Invoice.objects.filter(status__in=[0,1]).order_by('-status', 'time').select_related())
    for invoice in invoices:
        # Lấy nhà hàng
        restaurant = Restaurant.objects.filter(id=invoice.id_restaurant).first()
        # Lấy chủ nhà hàng
        owner_phone = ''
        if restaurant:
            user_restaurant = UserRestaurant.objects.filter(id_restaurant=restaurant.id).first()
            if user_restaurant:
                owner = User.objects.filter(id=user_restaurant.id_user).first()
                if owner:
                    owner_phone = owner.phone_number
        # Lấy các dish_invoice
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice.id)
        dishes = []
        customer = None
        customer_id = None
        hide_order = False
        for di in dish_invoices:
            dish_cart = DishCart.objects.filter(id=di.id_dish_cart).first()
            dish = Dish.objects.filter(id=dish_cart.id_dish).first() if dish_cart else None
            if not customer:
                customer = User.objects.filter(id=di.id_customer).first()
                customer_id = di.id_customer
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
            'owner_phone': owner_phone,
            'customer_phone': customer.phone_number if customer else '',
            'customer_address': f"{customer.street}, {customer.district}" if customer else '',
            'order_time': invoice.time.strftime('%H:%M %d/%m/%Y') if invoice.time else '',
            'dishes': dishes,
            'total_payment': invoice.total_payment,
            'status': invoice.status,
        })
    # In ra danh sách chi tiết order cùng với user_id dưới terminal
    print("=== SHIPPING ORDERS DEBUG ===")
    print(f"Current user_id: {user_id}")
    for order in orders:
        print(f"Order invoice_id: {order['invoice_id']}, customer_id: {order['customer_id']}, status: {order['status']}")
        print(f"  Restaurant: {order['restaurant_name']}, Owner phone: {order['owner_phone']}")
        print(f"  Customer phone: {order['customer_phone']}, Address: {order['customer_address']}")
        print(f"  Order time: {order['order_time']}, Total: {order['total_payment']}")
        print(f"  Dishes:")
        for dish in order['dishes']:
            print(f"    - {dish['name']} x{dish['quantity']} ({dish['unit']}) - {dish['price']}đ")
        print("------")
    return render(request, 'shippingOrder.html', {'orders': orders, 'user': User.objects.filter(id=user_id).first()})

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

def restaurant_info(request):
    user_id = request.session.get('user_id')
    context = {}
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    restaurant = None
    if user_restaurant:
        restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
    context['restaurant'] = restaurant

    # Thêm đoạn này trước return render(...)
    avg_rating = None
    total_ratings = 0
    if restaurant:
        dishes = Dish.objects.filter(id_restaurant=restaurant.id, is_delected=False)
        dish_ids = [d.id for d in dishes]
        dish_carts = DishCart.objects.filter(id_dish__in=dish_ids)
        dish_cart_ids = [dc.id for dc in dish_carts]
        rated_dish_invoices = DishInvoice.objects.filter(id_dish_cart__in=dish_cart_ids).exclude(id_rate__isnull=True).exclude(id_rate__exact='')
        rate_ids = [di.id_rate for di in rated_dish_invoices if di.id_rate]
        rates = Rate.objects.filter(id__in=rate_ids)
        total_ratings = rates.count()
        avg_rating = round(sum(r.star for r in rates) / total_ratings, 2) if total_ratings > 0 else None
    context['avg_rating'] = avg_rating
    context['total_ratings'] = total_ratings

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
    if request.method == 'GET':
        # Lấy thông tin user từ session
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('login')

        user = User.objects.filter(id=user_id).first()
        if not user or user.role != 1:  # Chỉ chủ cửa hàng
            return redirect('login')

        # Lấy thông tin nhà hàng nếu có
        user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
        restaurant = None
        if user_restaurant:
            restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()

        context = {
            'user': user,
            'restaurant': restaurant
        }
        return render(request, 'restaurantOwnerInfo.html', context)

    elif request.method == 'POST':
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({"success": False, "message": "Vui lòng đăng nhập"})

        # Phân biệt cập nhật user hay nhà hàng dựa vào trường name
        if 'name' in request.POST and 'phone' in request.POST:
            # Cập nhật thông tin user
            try:
                name = request.POST.get('name', '').strip()
                phone = request.POST.get('phone', '').strip()
                street = request.POST.get('street', '').strip()
                district = request.POST.get('district', '').strip()

                if not name:
                    return JsonResponse({"success": False, "message": "Họ và tên không được để trống"})
                if not phone:
                    return JsonResponse({"success": False, "message": "Số điện thoại không được để trống"})
                if not street:
                    return JsonResponse({"success": False, "message": "Tên đường không được để trống"})
                if not district:
                    return JsonResponse({"success": False, "message": "Quận không được để trống"})

                user = User.objects.filter(id=user_id).first()
                if user and user.role == 1:
                    user.name = name
                    user.phone_number = phone
                    user.street = street
                    user.district = district
                    user.save()
                    return JsonResponse({"success": True, "message": "Cập nhật thông tin thành công"})
                else:
                    return JsonResponse({"success": False, "message": "Không tìm thấy thông tin người dùng hoặc không có quyền"})
            except Exception as e:
                return JsonResponse({"success": False, "message": f"Có lỗi xảy ra: {str(e)}"})

        # Nếu là thêm mới/cập nhật nhà hàng thì chuyển sang view restaurant_info
        # (Form nhà hàng gửi POST tới /restaurant-info/)

    return JsonResponse({"success": False, "message": "Phương thức không được hỗ trợ"})

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
            if invoice and status in [1, 2, 3]:
                invoice.status = status
                invoice.save(update_fields=['status'])
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'message': 'Không tìm thấy đơn hàng hoặc trạng thái không hợp lệ'})
    return JsonResponse({'success': False, 'message': 'Phương thức không hợp lệ'})

def pending_orders_view(request):
    user_id = request.session.get('user_id')
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    restaurant_id = user_restaurant.id_restaurant if user_restaurant else None
    orders = []
    with connection.cursor() as cursor:
        cursor.execute('''
            SELECT i.id, i.time, i.total_payment, i.id_restaurant
            FROM invoice i
            WHERE i.status = 0
            ORDER BY i.time ASC
        ''')
        invoices = cursor.fetchall()
        for inv in invoices:
            invoice_id, order_time, total_payment, invoice_restaurant_id = inv
            # Chỉ lấy đơn hàng có id_restaurant trùng với nhà hàng tài khoản
            if not restaurant_id or str(invoice_restaurant_id) != str(restaurant_id):
                continue
            # Lấy id_customer đầu tiên từ dish_invoice
            cursor.execute('SELECT id_customer FROM dish_invoice WHERE id_invoice = %s LIMIT 1', [invoice_id])
            customer_row = cursor.fetchone()
            customer = None
            if customer_row:
                customer_id = customer_row[0]
                cursor.execute('SELECT name, phone_number, street, district FROM user WHERE id = %s', [customer_id])
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
                'restaurant_id': invoice_restaurant_id,
                'customer_name': customer[0] if customer else '',
                'customer_phone': customer[1] if customer else '',
                'customer_address': f"{customer[2]}, {customer[3]}" if customer and customer[2] and customer[3] else '',
                'order_time': order_time.strftime('%H:%M %d/%m/%Y') if order_time else '',
                'dishes': items,
                'total_payment': total_payment,
            })
    return render(request, 'restaurantPendingOrder.html', {
        'orders': orders,
        'user_restaurant': user_restaurant,
    })

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
#ok
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
            # Nếu đã có đánh giá, cập nhật lại
            rate = Rate.objects.filter(id=dish_invoice.id_rate).first()
            if rate:
                rate.star = star
                rate.comment = comment
                rate.save(update_fields=['star', 'comment'])
                return JsonResponse({'success': True})
        # Nếu chưa có đánh giá, tạo mới
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

@csrf_exempt
@require_POST
def api_add_to_cart(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({'success': False, 'message': 'Bạn cần đăng nhập để thêm vào giỏ hàng.'})
        data = json.loads(request.body)
        dish_id = data.get('dish_id')
        quantity = int(data.get('quantity', 1))
        note = data.get('note', '')

        # Kiểm tra món ăn tồn tại
        dish = Dish.objects.filter(id=dish_id, is_delected=False).first()
        if not dish:
            return JsonResponse({'success': False, 'message': 'Món ăn không tồn tại.'})

        # Kiểm tra đã có dish_cart chưa (chưa đặt hàng, cùng user, cùng món)
        # Tìm dish_cart chưa có invoice, của user này, cùng món này
        existing_cart_ids = DishCart.objects.filter(id_dish=dish_id).values_list('id', flat=True)
        existing_invoice = DishInvoice.objects.filter(id_dish_cart__in=existing_cart_ids, id_customer=user_id, id_invoice__isnull=True).first()
        if existing_invoice:
            # Nếu đã có, tăng số lượng
            dish_cart = DishCart.objects.filter(id=existing_invoice.id_dish_cart).first()
            if dish_cart:
                dish_cart.quantity = (dish_cart.quantity or 0) + quantity
                dish_cart.save()
            return JsonResponse({'success': True})
        # Nếu chưa có, tạo mới
        dish_cart_id = str(uuid.uuid4())
        DishCart.objects.create(
            id=dish_cart_id,
            id_dish=dish_id,
            quantity=quantity,
            note=note,
            is_checked=True
        )
        DishInvoice.objects.create(
            id=str(uuid.uuid4()),
            id_dish_cart=dish_cart_id,
            id_customer=user_id
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'Lỗi: ' + str(e)})

@csrf_exempt
@require_POST
def api_create_invoice(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({'success': False, 'message': 'Bạn cần đăng nhập để đặt hàng.'})
        data = json.loads(request.body)
        restaurant_id = data.get('restaurant_id')
        dish_cart_ids = data.get('dish_cart_ids', [])
        total_payment = int(data.get('total_payment', 0))
        shipping_fee = int(data.get('shipping_fee', 0))

        if not restaurant_id or not dish_cart_ids:
            return JsonResponse({'success': False, 'message': 'Thiếu thông tin đặt hàng.'})

        # Tạo hóa đơn mới
        invoice_id = str(uuid.uuid4())
        now = timezone.now()
        Invoice.objects.create(
            id=invoice_id,
            id_restaurant=restaurant_id,
            time=now,
            status=0,
            total_payment=total_payment,
            shipping_fee=shipping_fee,
            id_deleted=False
        )
        # Cập nhật id_invoice cho các DishInvoice tương ứng
        updated = 0
        for dish_cart_id in dish_cart_ids:
            di = DishInvoice.objects.filter(id_dish_cart=dish_cart_id, id_customer=user_id, id_invoice__isnull=True).first()
            if di:
                di.id_invoice = invoice_id
                di.save(update_fields=['id_invoice'])
                updated += 1
        return JsonResponse({'success': True, 'updated': updated})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'Lỗi: ' + str(e)})

@csrf_exempt
@require_POST
def api_confirm_payment(request):
    try:
        data = json.loads(request.body)
        invoice_id = data.get('invoice_id')
        user_id = request.session.get('user_id')
        if not invoice_id or not user_id:
            return JsonResponse({'success': False, 'message': 'Thiếu thông tin.'})
        # Cập nhật trạng thái hóa đơn sang 2 (hoàn tất)
        invoice = Invoice.objects.filter(id=invoice_id).first()
        if not invoice:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy hóa đơn.'})
        invoice.status = 2
        invoice.save(update_fields=['status'])
        # Tạo đánh giá mặc định cho các món chưa có đánh giá
        dish_invoices = DishInvoice.objects.filter(id_invoice=invoice_id, id_customer=user_id)
        for di in dish_invoices:
            if not di.id_rate:
                rate_id = str(uuid.uuid4())
                Rate.objects.create(id=rate_id, star=5, comment="Đánh giá tự động khi hoàn tất đơn hàng")
                di.id_rate = rate_id
                di.save(update_fields=['id_rate'])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'Lỗi: ' + str(e)})
