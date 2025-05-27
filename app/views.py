from django.shortcuts import render

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