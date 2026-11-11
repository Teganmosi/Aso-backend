from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ProductVariant, ProductMedia, ApprovalStatus, ProductStatus, MediaType


class ProductVariantsAndMediaAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Category
        self.category = Category.objects.create(name="Traditional Men", description="Traditional menswear")

        # Approved Vendor A User & Profile
        self.vendor_a_user = User.objects.create_user(
            email="designer.a@lagosluxe.com",
            password="Password123!",
            first_name="Lagos",
            last_name="Luxe",
            phone_number="+2348011112222"
        )
        self.vendor_a = VendorProfile.objects.create(
            user=self.vendor_a_user,
            store_name="Lagos Luxe Native",
            city="Lagos",
            state="Lagos",
            status=VendorStatus.APPROVED
        )

        # Approved Vendor B User & Profile (for cross-vendor isolation test)
        self.vendor_b_user = User.objects.create_user(
            email="designer.b@abuja.com",
            password="Password123!",
            first_name="Abuja",
            last_name="Couture",
            phone_number="+2348033334444"
        )
        self.vendor_b = VendorProfile.objects.create(
            user=self.vendor_b_user,
            store_name="Abuja Threads",
            city="Abuja",
            state="FCT",
            status=VendorStatus.APPROVED
        )

        # Regular Customer
        self.customer = User.objects.create_user(
            email="customer@gmail.com",
            password="Password123!",
            first_name="John",
            last_name="Doe",
            phone_number="+2348055556666"
        )

        # Create base product owned by Vendor A
        self.product = Product.objects.create(
            vendor=self.vendor_a,
            category=self.category,
            title="Royal Silk Agbada",
            description="Handcrafted silk agbada set",
            base_price_kobo=7500000,
            preparation_time_days=5,
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )

    def test_presigned_upload_url_generator_mime_validation(self):
        """
        Sprint 4 Test 1: Call POST /api/v1/products/upload-url/ as approved vendor.
        Validates MIME whitelist and returns vendor-scoped object key.
        """
        self.client.force_authenticate(user=self.vendor_a_user)

        # Valid image request
        payload_jpg = {"filename": "agbada.jpg", "file_type": "image/jpeg"}
        res_jpg = self.client.post("/api/v1/products/upload-url/", payload_jpg, format="json")
        self.assertEqual(res_jpg.status_code, status.HTTP_200_OK)
        self.assertTrue(res_jpg.data["success"])
        self.assertIn("upload_url", res_jpg.data["data"])
        self.assertIn("public_url", res_jpg.data["data"])
        self.assertIn(f"vendors/{self.vendor_a.id}/products/", res_jpg.data["data"]["object_key"])
        self.assertTrue(res_jpg.data["data"]["object_key"].endswith(".jpg"))

        # Valid video request
        payload_mp4 = {"filename": "agbada_runway.mp4", "file_type": "video/mp4"}
        res_mp4 = self.client.post("/api/v1/products/upload-url/", payload_mp4, format="json")
        self.assertEqual(res_mp4.status_code, status.HTTP_200_OK)
        self.assertTrue(res_mp4.data["data"]["object_key"].endswith(".mp4"))

        # Invalid MIME type request (e.g. PDF)
        payload_pdf = {"filename": "document.pdf", "file_type": "application/pdf"}
        res_pdf = self.client.post("/api/v1/products/upload-url/", payload_pdf, format="json")
        self.assertEqual(res_pdf.status_code, status.HTTP_400_BAD_REQUEST)

    def test_variant_creation_and_stock_management(self):
        """
        Sprint 4 Test 2: Call POST /api/v1/products/{id}/variants/ to add variants.
        """
        self.client.force_authenticate(user=self.vendor_a_user)

        # Variant 1: XL / Navy / Stock: 5
        v1_payload = {"size": "XL", "color": "Navy Blue", "stock_quantity": 5}
        res_v1 = self.client.post(f"/api/v1/products/{self.product.id}/variants/", v1_payload, format="json")
        self.assertEqual(res_v1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_v1.data["variant"]["size"], "XL")
        self.assertEqual(res_v1.data["variant"]["color"], "Navy Blue")
        self.assertEqual(res_v1.data["variant"]["stock_quantity"], 5)
        self.assertIn("ASO-", res_v1.data["variant"]["sku"])

        # Variant 2: L / Black / Stock: 3
        v2_payload = {"size": "L", "color": "Black", "stock_quantity": 3}
        res_v2 = self.client.post(f"/api/v1/products/{self.product.id}/variants/", v2_payload, format="json")
        self.assertEqual(res_v2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_v2.data["variant"]["size"], "L")

        # List variants for product
        res_list = self.client.get(f"/api/v1/products/{self.product.id}/variants/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data["variants"]), 2)

        # Update variant stock
        v1_id = res_v1.data["variant"]["id"]
        res_patch = self.client.patch(
            f"/api/v1/products/{self.product.id}/variants/{v1_id}/",
            {"stock_quantity": 10},
            format="json"
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["variant"]["stock_quantity"], 10)

    def test_media_attachment_and_primary_badge(self):
        """
        Tests attaching photo gallery items and video to product.
        """
        self.client.force_authenticate(user=self.vendor_a_user)

        # Attach Primary Image (URL must live in this vendor's storage namespace)
        img1_payload = {
            "media_type": "IMAGE",
            "url": f"https://cdn.aso.ng/vendors/{self.vendor_a.id}/agbada_front.jpg",
            "display_order": 1,
            "is_primary": True
        }
        res_img1 = self.client.post(f"/api/v1/products/{self.product.id}/media/", img1_payload, format="json")
        self.assertEqual(res_img1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_img1.data["media"]["is_primary"])

        # Attach Video
        vid_payload = {
            "media_type": "VIDEO",
            "url": f"https://cdn.aso.ng/vendors/{self.vendor_a.id}/agbada_walk.mp4",
            "display_order": 2,
            "is_primary": False
        }
        res_vid = self.client.post(f"/api/v1/products/{self.product.id}/media/", vid_payload, format="json")
        self.assertEqual(res_vid.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_vid.data["media"]["media_type"], "VIDEO")

    def test_public_product_detail_returns_full_gallery_and_variant_matrix(self):
        """
        Sprint 4 Test 3: Public GET /api/v1/products/{slug}/ returns media gallery and variant breakdown.
        """
        # Pre-populate variants
        ProductVariant.objects.create(product=self.product, size="XL", color="Navy Blue", stock_quantity=5)
        ProductVariant.objects.create(product=self.product, size="L", color="Black", stock_quantity=3)

        # Pre-populate media
        ProductMedia.objects.create(
            product=self.product,
            media_type=MediaType.IMAGE,
            url="https://cdn.aso.ng/vendors/123/agbada_front.jpg",
            display_order=1,
            is_primary=True
        )
        ProductMedia.objects.create(
            product=self.product,
            media_type=MediaType.VIDEO,
            url="https://cdn.aso.ng/vendors/123/agbada_walk.mp4",
            display_order=2,
            is_primary=False
        )

        response = self.client.get(f"/api/v1/products/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        product_data = response.data["product"]

        # Verify primary image URL
        self.assertEqual(product_data["primary_image_url"], "https://cdn.aso.ng/vendors/123/agbada_front.jpg")

        # Verify media gallery array
        self.assertEqual(len(product_data["media"]), 2)
        self.assertEqual(product_data["media"][0]["url"], "https://cdn.aso.ng/vendors/123/agbada_front.jpg")
        self.assertEqual(product_data["media"][1]["media_type"], "VIDEO")

        # Verify variant matrix array
        self.assertEqual(len(product_data["variants"]), 2)
        sizes = [v["size"] for v in product_data["variants"]]
        self.assertIn("XL", sizes)
        self.assertIn("L", sizes)

    def test_cross_vendor_isolation_on_variants_and_media(self):
        """
        Vendor B cannot manage variants or media on Vendor A's product.
        """
        self.client.force_authenticate(user=self.vendor_b_user)

        # Attempt to add variant to Vendor A's product
        res_v = self.client.post(
            f"/api/v1/products/{self.product.id}/variants/",
            {"size": "M", "stock_quantity": 2},
            format="json"
        )
        self.assertEqual(res_v.status_code, status.HTTP_404_NOT_FOUND)

        # Attempt to add media to Vendor A's product
        res_m = self.client.post(
            f"/api/v1/products/{self.product.id}/media/",
            {"media_type": "IMAGE", "url": "https://hack.com/test.jpg"},
            format="json"
        )
        self.assertEqual(res_m.status_code, status.HTTP_404_NOT_FOUND)
