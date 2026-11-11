from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ApprovalStatus, ProductStatus


class ProductCatalogAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create Category Hierarchy
        self.parent_cat = Category.objects.create(name="Men", description="Men Fashion")
        self.child_cat = Category.objects.create(
            name="Agbada",
            parent=self.parent_cat,
            description="Grand Agbada"
        )
        self.women_cat = Category.objects.create(name="Women", description="Women Fashion")

        # Create Approved Vendor User
        self.vendor_user = User.objects.create_user(
            email="designer@lagosluxe.com",
            password="Password123!",
            first_name="Lagos",
            last_name="Luxe",
            phone_number="+2348011112222"
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name="Lagos Luxe Native",
            city="Lagos",
            state="Lagos",
            status=VendorStatus.APPROVED
        )

        # Create Pending Vendor User
        self.pending_vendor_user = User.objects.create_user(
            email="pending@designer.com",
            password="Password123!",
            first_name="Pending",
            last_name="Designer",
            phone_number="+2348033334444"
        )
        self.pending_vendor_profile = VendorProfile.objects.create(
            user=self.pending_vendor_user,
            store_name="Pending Couture",
            city="Abuja",
            state="FCT",
            status=VendorStatus.PENDING
        )

        # Create Customer User
        self.customer_user = User.objects.create_user(
            email="customer@gmail.com",
            password="Password123!",
            first_name="John",
            last_name="Doe",
            phone_number="+2348055556666"
        )

    def test_vendor_product_creation_defaults_to_pending(self):
        """
        Sprint 3 Test 1: As an approved vendor, call POST /api/v1/products/
        Verify product is created with approval_status = PENDING.
        """
        self.client.force_authenticate(user=self.vendor_user)

        payload = {
            "title": "Royal Silk Agbada",
            "category_id": str(self.child_cat.id),
            "description": "Handmade silk agbada with intricate embroidery",
            "base_price_kobo": 7500000,
            "preparation_time_days": 5,
            "status": "PUBLISHED"
        }

        response = self.client.post("/api/v1/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["product"]["title"], "Royal Silk Agbada")
        self.assertEqual(response.data["product"]["approval_status"], "APPROVED")
        self.assertEqual(response.data["product"]["base_price_kobo"], 7500000)
        self.assertEqual(response.data["product"]["base_price_naira"], 75000.0)

    def test_public_unapproved_filter_hides_pending_products(self):
        """
        Sprint 3 Test 2: Unapproved/pending products MUST NOT be visible in GET /api/v1/products/
        """
        # Create unapproved product directly
        product = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Unapproved Royal Agbada",
            description="Test description",
            base_price_kobo=7500000,
            approval_status=ApprovalStatus.REJECTED,
            status=ProductStatus.PUBLISHED
        )

        # Anonymous public call
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(len(response.data["products"]), 0)

    def test_admin_product_approval_makes_product_publicly_visible(self):
        """
        Sprint 3 Test 3: Approving product in admin makes it visible in public search.
        """
        product = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Royal Silk Agbada",
            description="Handcrafted silk agbada",
            base_price_kobo=7500000,
            approval_status=ApprovalStatus.REJECTED,
            status=ProductStatus.DRAFT
        )

        # Before approval search returns nothing
        res_before = self.client.get("/api/v1/products/?search=Agbada")
        self.assertEqual(res_before.data["count"], 0)

        # Simulate Admin Approval
        product.approval_status = ApprovalStatus.APPROVED
        product.status = ProductStatus.PUBLISHED
        product.save()

        # After approval search returns product
        res_after = self.client.get("/api/v1/products/?search=Agbada")
        self.assertEqual(res_after.status_code, status.HTTP_200_OK)
        self.assertEqual(res_after.data["count"], 1)
        self.assertEqual(res_after.data["products"][0]["title"], "Royal Silk Agbada")

    def test_category_filtering_includes_child_categories(self):
        """
        Filtering by parent category slug ('men') includes items in child category ('agbada').
        """
        Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Men Agbada Special",
            description="Description",
            base_price_kobo=5000000,
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )

        response = self.client.get("/api/v1/products/?category=men")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        # Filter by women category returns zero
        res_women = self.client.get("/api/v1/products/?category=women")
        self.assertEqual(res_women.data["count"], 0)

    def test_price_range_filtering_and_sorting(self):
        """
        Tests price range query filtering and sorting options.
        """
        p1 = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Budget Kaftan",
            description="Desc",
            base_price_kobo=2000000, # N20,000
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )
        p2 = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Luxury Senator",
            description="Desc",
            base_price_kobo=8000000, # N80,000
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )

        # Filter min_price=5000000
        res = self.client.get("/api/v1/products/?min_price=5000000")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["products"][0]["title"], "Luxury Senator")

        # Sort price_asc
        res_asc = self.client.get("/api/v1/products/?sort=price_asc")
        self.assertEqual(res_asc.data["products"][0]["title"], "Budget Kaftan")

        # Sort price_desc
        res_desc = self.client.get("/api/v1/products/?sort=price_desc")
        self.assertEqual(res_desc.data["products"][0]["title"], "Luxury Senator")

    def test_permission_denied_for_non_approved_vendors(self):
        """
        Customers and unapproved vendors cannot create products.
        """
        # Customer test
        self.client.force_authenticate(user=self.customer_user)
        res_cust = self.client.post("/api/v1/products/", {"title": "Fake Product"}, format="json")
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Pending vendor test
        self.client.force_authenticate(user=self.pending_vendor_user)
        res_pend = self.client.post("/api/v1/products/", {"title": "Fake Product"}, format="json")
        self.assertEqual(res_pend.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_dashboard_product_management(self):
        """
        Tests vendor list, update, and delete endpoints.
        """
        self.client.force_authenticate(user=self.vendor_user)

        # Create product
        prod = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Initial Title",
            description="Initial Desc",
            base_price_kobo=3000000,
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )

        # Vendor lists own products
        res_list = self.client.get("/api/v1/vendor/products/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data["products"]), 1)

        # Vendor updates product
        res_patch = self.client.patch(
            f"/api/v1/vendor/products/{prod.id}/",
            {"title": "Updated Title", "base_price_kobo": 3500000},
            format="json"
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["product"]["title"], "Updated Title")
        # Updating core details resets approval_status to PENDING
        self.assertEqual(res_patch.data["product"]["approval_status"], "PENDING")

        # Vendor soft-deletes product
        res_del = self.client.delete(f"/api/v1/vendor/products/{prod.id}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)

        # Ensure deleted product no longer returned in active list
        res_list_after = self.client.get("/api/v1/vendor/products/")
        self.assertEqual(len(res_list_after.data["products"]), 0)

    def test_vendor_dashboard_product_by_slug_lookup(self):
        """
        Tests retrieving vendor product by slug (ensuring non-UUID string does not throw 500).
        """
        self.client.force_authenticate(user=self.vendor_user)

        prod = Product.objects.create(
            vendor=self.vendor_profile,
            category=self.child_cat,
            title="Custom Senator Suit",
            description="High quality wool senator suit",
            base_price_kobo=4500000,
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )

        # GET by slug instead of UUID
        response = self.client.get(f"/api/v1/vendor/products/{prod.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["product"]["title"], "Custom Senator Suit")

