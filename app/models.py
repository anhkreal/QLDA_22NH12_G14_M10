from django.db import models

# Create your models here.

class Dish(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=100)
    decription = models.CharField(max_length=500)
    price = models.IntegerField()
    unit = models.CharField(max_length=100)
    image = models.BinaryField()
    id_restaurant = models.CharField(max_length=100)
    is_delected = models.BooleanField(null=True, default=None)

    class Meta:
        db_table = 'dish'
        managed = False


class DishCart(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    id_dish = models.CharField(max_length=100)
    quantity = models.IntegerField(null=True, default=None)
    note = models.CharField(max_length=100, null=True, default=None)
    is_checked = models.BooleanField()

    class Meta:
        db_table = 'dish_cart'
        managed = False


class DishInvoice(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    id_dish_cart = models.CharField(max_length=100)
    id_invoice = models.CharField(max_length=100, null=True, default=None)
    id_customer = models.CharField(max_length=100)
    id_rate = models.CharField(max_length=100, null=True, default=None)

    class Meta:
        db_table = 'dish_invoice'
        managed = False


class Invoice(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    id_restaurant = models.CharField(max_length=100, null=True, default=None)
    time = models.DateTimeField(null=True, default=None)
    status = models.IntegerField(null=True, default=None)
    total_payment = models.IntegerField(null=True, default=None)
    shipping_fee = models.IntegerField(null=True, default=None)
    id_deleted = models.BooleanField(null=True, default=None)

    class Meta:
        db_table = 'invoice'
        managed = False


class Rate(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    comment = models.CharField(max_length=100, null=True, default=None)
    star = models.IntegerField()

    class Meta:
        db_table = 'rate'
        managed = False


class Restaurant(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=100, null=True, default=None)
    decription = models.CharField(max_length=500, null=True, default=None)
    street = models.CharField(max_length=100, null=True, default=None)
    district = models.CharField(max_length=100, null=True, default=None)
    image = models.BinaryField(null=True, default=None)
    is_deleted = models.BooleanField()

    class Meta:
        db_table = 'restaurant'
        managed = False


class User(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    role = models.IntegerField()
    street = models.CharField(max_length=100, null=True, default=None)
    district = models.CharField(max_length=100, null=True, default=None)
    is_deleted = models.BooleanField()

    class Meta:
        db_table = 'user'
        managed = False

