from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import User
import json
import uuid

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
    return render(request, 'restaurantOwnerHome.html')

def restaurant_pending_order(request):
    return render(request, 'restaurantPendingOrder.html')

def restaurant_shipping_order(request):
    return render(request, 'restaurantShippingOrder.html')

def restaurant_order_history(request):
    return render(request, 'restaurantOrderHistory.html')

def revenue_statistics(request):
    return render(request, 'revenueStatistics.html')