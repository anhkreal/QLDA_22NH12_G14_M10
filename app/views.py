from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import User, Restaurant, UserRestaurant, Dish, DishCart, DishInvoice, Rate, Invoice
import json
import uuid
from django.views.decorators.csrf import csrf_exempt
import base64
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q
from collections import defaultdict
from django.core.serializers.json import DjangoJSONEncoder

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
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    user = User.objects.filter(id=user_id).first()
    if not user or user.role != 0:  # Chỉ khách hàng mới có thống kê chi tiêu
        return redirect('login')

    # Lấy tất cả invoice của khách hàng thông qua DishInvoice
    dish_invoices = DishInvoice.objects.filter(id_customer=user_id).exclude(id_invoice__isnull=True).exclude(id_invoice__exact='')
    invoice_ids = [di.id_invoice for di in dish_invoices]
    invoices = Invoice.objects.filter(id__in=invoice_ids, id_deleted__isnull=True)

    # Tính toán thống kê theo ngày (30 ngày gần nhất)
    today = datetime.now().date()
    daily_spending = defaultdict(int)

    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 30 ngày gần nhất
            if (today - invoice_date).days <= 30:
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                daily_spending[invoice_date] += total_amount

    # Tạo dữ liệu cho 30 ngày gần nhất
    day_labels = []
    day_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        day_labels.append(date.strftime('%d/%m'))
        day_data.append(daily_spending.get(date, 0))

    # Tính toán thống kê theo tuần (12 tuần gần nhất)
    weekly_spending = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 12 tuần gần nhất (84 ngày)
            if (today - invoice_date).days <= 84:
                # Tính tuần trong năm
                year, week, _ = invoice_date.isocalendar()
                week_key = f"{year}-W{week:02d}"
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                weekly_spending[week_key] += total_amount

    # Tạo dữ liệu cho 12 tuần gần nhất
    week_labels = []
    week_data = []
    for i in range(11, -1, -1):
        date = today - timedelta(weeks=i)
        year, week, _ = date.isocalendar()
        week_key = f"{year}-W{week:02d}"
        week_labels.append(f"Tuần {week}/{year}")
        week_data.append(weekly_spending.get(week_key, 0))

    # Tính toán thống kê theo tháng (12 tháng gần nhất)
    monthly_spending = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 12 tháng gần nhất (365 ngày)
            if (today - invoice_date).days <= 365:
                year_month = f"{invoice_date.year}-{invoice_date.month:02d}"
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                monthly_spending[year_month] += total_amount

    # Tạo dữ liệu cho 12 tháng gần nhất
    month_labels = []
    month_data = []
    current_date = today.replace(day=1)  # Đầu tháng hiện tại
    for i in range(11, -1, -1):
        # Tính tháng trước đó
        if current_date.month - i <= 0:
            year = current_date.year - 1
            month = 12 + (current_date.month - i)
        else:
            year = current_date.year
            month = current_date.month - i

        year_month = f"{year}-{month:02d}"
        month_labels.append(f"{month:02d}/{year}")
        month_data.append(monthly_spending.get(year_month, 0))

    # Tính toán thống kê theo năm (tất cả các năm có dữ liệu)
    yearly_spending = defaultdict(int)
    years_with_data = set()

    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            year = invoice_date.year
            years_with_data.add(year)
            year_str = str(year)
            total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
            yearly_spending[year_str] += total_amount

    # Tạo dữ liệu cho tất cả các năm có dữ liệu, sắp xếp từ cũ đến mới
    year_labels = []
    year_data = []
    if years_with_data:
        sorted_years = sorted(years_with_data)
        for year in sorted_years:
            year_str = str(year)
            year_labels.append(year_str)
            year_data.append(yearly_spending.get(year_str, 0))
    else:
        # Nếu không có dữ liệu, hiển thị năm hiện tại
        current_year = str(today.year)
        year_labels.append(current_year)
        year_data.append(0)

    # Tạo dữ liệu chi tiết theo từng năm (theo tháng trong năm)
    yearly_detail_data = {}
    if years_with_data:
        for year in sorted(years_with_data):
            # Lấy dữ liệu theo tháng trong năm này
            monthly_data_for_year = defaultdict(int)
            for invoice in invoices:
                if invoice.time and invoice.time.year == year:
                    month = invoice.time.month
                    total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                    monthly_data_for_year[month] += total_amount

            # Tạo labels và data cho 12 tháng
            month_labels_year = []
            month_data_year = []
            for month in range(1, 13):
                month_labels_year.append(f"Tháng {month}")
                month_data_year.append(monthly_data_for_year.get(month, 0))

            yearly_detail_data[str(year)] = {
                'labels': month_labels_year,
                'data': month_data_year
            }

    # Tính tổng chi tiêu
    total_spending = sum(daily_spending.values())
    total_orders = len(invoice_ids)

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

def restaurant_order_history(request):
    return render(request, 'restaurantOrderHistory.html')

def revenue_statistics(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    user = User.objects.filter(id=user_id).first()
    if not user or user.role != 1:  # Chỉ chủ cửa hàng mới có thống kê doanh thu
        return redirect('login')

    # Lấy nhà hàng của user
    user_restaurant = UserRestaurant.objects.filter(id_user=user_id).first()
    if not user_restaurant:
        return redirect('restaurant-info')

    restaurant = Restaurant.objects.filter(id=user_restaurant.id_restaurant).first()
    if not restaurant:
        return redirect('restaurant-info')

    # Lấy tất cả invoice của nhà hàng
    invoices = Invoice.objects.filter(id_restaurant=restaurant.id, id_deleted__isnull=True)

    # Tính toán thống kê theo ngày (30 ngày gần nhất)
    today = datetime.now().date()
    daily_revenue = defaultdict(int)

    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 30 ngày gần nhất
            if (today - invoice_date).days <= 30:
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                daily_revenue[invoice_date] += total_amount

    # Tạo dữ liệu cho 30 ngày gần nhất
    day_labels = []
    day_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        day_labels.append(date.strftime('%d/%m'))
        day_data.append(daily_revenue.get(date, 0))

    # Tính toán thống kê theo tuần (12 tuần gần nhất)
    weekly_revenue = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 12 tuần gần nhất (84 ngày)
            if (today - invoice_date).days <= 84:
                # Tính tuần trong năm
                year, week, _ = invoice_date.isocalendar()
                week_key = f"{year}-W{week:02d}"
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                weekly_revenue[week_key] += total_amount

    # Tạo dữ liệu cho 12 tuần gần nhất
    week_labels = []
    week_data = []
    for i in range(11, -1, -1):
        date = today - timedelta(weeks=i)
        year, week, _ = date.isocalendar()
        week_key = f"{year}-W{week:02d}"
        week_labels.append(f"Tuần {week}/{year}")
        week_data.append(weekly_revenue.get(week_key, 0))

    # Tính toán thống kê theo tháng (12 tháng gần nhất)
    monthly_revenue = defaultdict(int)
    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            # Chỉ lấy 12 tháng gần nhất (365 ngày)
            if (today - invoice_date).days <= 365:
                year_month = f"{invoice_date.year}-{invoice_date.month:02d}"
                total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                monthly_revenue[year_month] += total_amount

    # Tạo dữ liệu cho 12 tháng gần nhất
    month_labels = []
    month_data = []
    current_date = today.replace(day=1)  # Đầu tháng hiện tại
    for i in range(11, -1, -1):
        # Tính tháng trước đó
        if current_date.month - i <= 0:
            year = current_date.year - 1
            month = 12 + (current_date.month - i)
        else:
            year = current_date.year
            month = current_date.month - i

        year_month = f"{year}-{month:02d}"
        month_labels.append(f"{month:02d}/{year}")
        month_data.append(monthly_revenue.get(year_month, 0))

    # Tính toán thống kê theo năm (tất cả các năm có dữ liệu)
    yearly_revenue = defaultdict(int)
    years_with_data = set()

    for invoice in invoices:
        if invoice.time:
            invoice_date = invoice.time.date()
            year = invoice_date.year
            years_with_data.add(year)
            year_str = str(year)
            total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
            yearly_revenue[year_str] += total_amount

    # Tạo dữ liệu cho tất cả các năm có dữ liệu, sắp xếp từ cũ đến mới
    year_labels = []
    year_data = []
    if years_with_data:
        sorted_years = sorted(years_with_data)
        for year in sorted_years:
            year_str = str(year)
            year_labels.append(year_str)
            year_data.append(yearly_revenue.get(year_str, 0))
    else:
        # Nếu không có dữ liệu, hiển thị năm hiện tại
        current_year = str(today.year)
        year_labels.append(current_year)
        year_data.append(0)

    # Tính các thống kê tổng quan
    total_revenue = sum(daily_revenue.values())
    total_orders = invoices.count()

    # Thống kê món ăn bán chạy nhất
    dish_sales = defaultdict(int)
    dish_revenue = defaultdict(int)

    # Lấy tất cả DishInvoice liên quan đến nhà hàng
    invoice_ids = [inv.id for inv in invoices]
    dish_invoices = DishInvoice.objects.filter(id_invoice__in=invoice_ids)

    for dish_invoice in dish_invoices:
        dish_cart = DishCart.objects.filter(id=dish_invoice.id_dish_cart).first()
        if dish_cart:
            dish = Dish.objects.filter(id=dish_cart.id_dish).first()
            if dish:
                quantity = dish_cart.quantity or 0
                dish_sales[dish.name] += quantity
                dish_revenue[dish.name] += quantity * dish.price

    # Sắp xếp món ăn theo doanh thu
    top_dishes = sorted(dish_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

    # Tính đánh giá trung bình của nhà hàng
    restaurant_dishes = Dish.objects.filter(id_restaurant=restaurant.id)
    dish_ids = [dish.id for dish in restaurant_dishes]
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

    # Tạo dữ liệu chi tiết theo từng năm (theo tháng trong năm)
    yearly_detail_data = {}
    if years_with_data:
        for year in sorted(years_with_data):
            # Lấy dữ liệu theo tháng trong năm này
            monthly_data_for_year = defaultdict(int)
            for invoice in invoices:
                if invoice.time and invoice.time.year == year:
                    month = invoice.time.month
                    total_amount = (invoice.total_payment or 0) + (invoice.shipping_fee or 0)
                    monthly_data_for_year[month] += total_amount

            # Tạo labels và data cho 12 tháng
            month_labels_year = []
            month_data_year = []
            for month in range(1, 13):
                month_labels_year.append(f"Tháng {month}")
                month_data_year.append(monthly_data_for_year.get(month, 0))

            yearly_detail_data[str(year)] = {
                'labels': month_labels_year,
                'data': month_data_year
            }

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
    if request.method == 'GET':
        # Lấy thông tin user từ session
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('login')

        user = User.objects.filter(id=user_id).first()
        if not user or user.role != 1:  # Chỉ chủ cửa hàng
            return redirect('login')

        context = {
            'user': user
        }
        return render(request, 'restaurantOwnerInfo.html', context)

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
            if user and user.role == 1:  # Chỉ chủ cửa hàng
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