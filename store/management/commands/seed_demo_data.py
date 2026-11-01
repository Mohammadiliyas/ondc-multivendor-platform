from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from store.models import Category, Product, Vendor

DATA = [
("Deccan Digital Store","demo_vendor_electronics","electronics.demo@example.test","Electronics",[
("Wireless Bluetooth Headphones","ELEC-001","Wireless over-ear headphones with microphone.","1499.00",35),
("USB-C Fast Charger 30W","ELEC-002","30W USB-C wall charger for compatible devices.","899.00",50),
("Bluetooth Speaker Mini","ELEC-003","Compact portable Bluetooth speaker.","1199.00",24),
("Wireless Mouse","ELEC-004","2.4GHz wireless optical mouse.","499.00",60),
("Smart LED Bulb 9W","ELEC-005","Energy-efficient smart LED bulb.","349.00",45)]),
("Telangana Trends","demo_vendor_fashion","fashion.demo@example.test","Fashion",[
("Men's Cotton Casual Shirt","FASH-001","Regular-fit cotton casual shirt.","799.00",30),
("Women's Everyday Kurta","FASH-002","Printed kurta for daily wear.","899.00",28),
("Unisex Cotton T-Shirt","FASH-003","Soft cotton crew-neck T-shirt.","399.00",70),
("Canvas Casual Backpack","FASH-004","Lightweight backpack with front pocket.","999.00",18),
("Everyday Sports Shoes","FASH-005","Lightweight lace-up walking shoes.","1299.00",22)]),
("Fresh Basket Mart","demo_vendor_grocery","grocery.demo@example.test","Grocery",[
("Basmati Rice 5kg","GROC-001","Aromatic long-grain basmati rice, 5kg pack.","649.00",40),
("Toor Dal 1kg","GROC-002","Cleaned and packed toor dal, 1kg.","169.00",55),
("Groundnut Oil 1L","GROC-003","Sealed 1 litre bottle of groundnut cooking oil.","219.00",32),
("Whole Wheat Atta 5kg","GROC-004","Whole wheat flour, 5kg pack.","259.00",38),
("Mixed Dry Fruits 250g","GROC-005","Assorted packaged dry fruits, 250g pouch.","349.00",26)]),
("Nizam Home Essentials","demo_vendor_home","home.demo@example.test","Home & Kitchen",[
("Stainless Steel Water Bottle 1L","HOME-001","Reusable stainless steel water bottle, 1 litre.","399.00",42),
("Non-stick Frying Pan 24cm","HOME-002","24cm non-stick frying pan.","699.00",20),
("Cotton Bedsheet Double","HOME-003","Double-bed cotton bedsheet with two pillow covers.","1099.00",16),
("LED Desk Lamp","HOME-004","Adjustable LED desk lamp for study and work.","549.00",25),
("Storage Container Set","HOME-005","Set of five reusable kitchen storage containers.","449.00",33)]),
("Everyday Care Shop","demo_vendor_beauty","beauty.demo@example.test","Beauty & Personal Care",[
("Aloe Vera Face Wash 100ml","BEAU-001","Gentle daily face wash, 100ml pack.","179.00",40),
("Moisturizing Body Lotion 200ml","BEAU-002","Daily moisturizing body lotion, 200ml bottle.","249.00",36),
("Neem Herbal Soap Pack","BEAU-003","Pack of three neem-based bathing soaps.","129.00",48),
("SPF 50 Sunscreen 50g","BEAU-004","SPF 50 sunscreen, 50g tube.","399.00",29),
("Coconut Hair Oil 200ml","BEAU-005","Coconut hair oil, 200ml bottle.","159.00",44)])
]
BUYERS=[("demo_buyer_1","buyer1.demo@example.test"),("demo_buyer_2","buyer2.demo@example.test"),("demo_buyer_3","buyer3.demo@example.test")]

class Command(BaseCommand):
    help = "Idempotently seed staging with sample categories, vendors, products and buyers."

    @transaction.atomic
    def handle(self, *args, **options):
        categories={name:Category.objects.get_or_create(name=name)[0] for name in {row[3] for row in DATA}}
        vc=pc=bc=0
        for store,username,email,category_name,products in DATA:
            owner,new_user=User.objects.get_or_create(username=username,defaults={"email":email,"is_active":True})
            if new_user:
                owner.set_password("DemoOnly@2026")
                owner.save(update_fields=["password"])
            vendor,new_vendor=Vendor.objects.get_or_create(owner=owner,defaults={"store_name":store,"description":f"Sample {category_name.lower()} seller for staging demonstrations.","is_approved":True,"is_suspended":False})
            vc+=int(new_vendor)
            if not vendor.is_approved or vendor.is_suspended:
                vendor.is_approved=True
                vendor.is_suspended=False
                vendor.save(update_fields=["is_approved","is_suspended"])
            for name,sku,description,price,stock in products:
                _,created=Product.objects.get_or_create(sku=sku,defaults={"vendor":vendor,"category":categories[category_name],"name":name,"description":description,"price":Decimal(price),"stock":stock,"is_active":True})
                pc+=int(created)
        for username,email in BUYERS:
            buyer,created=User.objects.get_or_create(username=username,defaults={"email":email,"is_active":True})
            if created:
                buyer.set_password("DemoOnly@2026")
                buyer.save(update_fields=["password"])
                bc+=1
        self.stdout.write(self.style.SUCCESS(f"Seed complete. Totals: {Category.objects.count()} categories, {Vendor.objects.count()} vendors, {Product.objects.count()} products. Created now: {vc} vendors, {pc} products, {bc} buyers. Existing records preserved; no fake orders or payments created."))
