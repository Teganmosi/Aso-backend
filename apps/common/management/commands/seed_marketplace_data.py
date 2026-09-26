import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import User, Address
from apps.vendors.models import VendorProfile, VendorStatus, BankAccount, KYCTier
from apps.products.models import (
    Category,
    Product,
    ProductVariant,
    ProductMedia,
    MediaType,
    Review,
    ApprovalStatus,
    ProductStatus,
)
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.payouts.services import get_or_create_vendor_balance


class Command(BaseCommand):
    help = 'Seeds realistic Nigerian fashion marketplace sample data (Vendors, Categories, Products, Variants, Media, Reviews, Users)'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Nigerian Fashion Marketplace sample data..."))

        # 1. Superuser / Admin
        admin_user, _ = User.objects.get_or_create(
            email='admin@aso.ng',
            defaults={
                'first_name': 'Aso',
                'last_name': 'Admin',
                'phone_number': '+2348000000001',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('Admin123!')
        admin_user.save()
        self.stdout.write(self.style.SUCCESS("[SUCCESS] Admin created: admin@aso.ng (Password: Admin123!)"))

        # 2. Sample Customer User
        customer_user, _ = User.objects.get_or_create(
            email='customer@aso.ng',
            defaults={
                'first_name': 'Zainab',
                'last_name': 'Aliyu',
                'phone_number': '+2348099887700',
            }
        )
        customer_user.set_password('Password123!')
        customer_user.save()

        Address.objects.get_or_create(
            user=customer_user,
            is_default=True,
            defaults={
                'full_name': 'Zainab Aliyu',
                'phone_number': '+2348099887700',
                'street_address': '12 Admiralty Way, Lekki Phase 1',
                'city': 'Lekki',
                'state': 'Lagos',
                'landmark': 'Beside Filmhouse Cinema',
            }
        )
        self.stdout.write(self.style.SUCCESS("[SUCCESS] Test Customer created: customer@aso.ng (Password: Password123!)"))

        # 3. Categories Hierarchy
        categories_data = [
            {
                'name': 'Men',
                'slug': 'men',
                'description': 'Bespoke and ready-to-wear traditional and contemporary menswear.',
                'subcategories': [
                    ('Agbada', 'agbada', 'Regal ceremonial 3-piece and 4-piece Agbada sets.'),
                    ('Senator Suits', 'senator-suits', 'Tailored Nigerian senator suits and kaftans.'),
                    ('Two-Piece Sets', 'two-piece-sets', 'Contemporary casual native two-piece sets.'),
                ]
            },
            {
                'name': 'Women',
                'slug': 'women',
                'description': 'Exquisite couture gowns, Aso Ebi, Boubou, and modern silhouettes.',
                'subcategories': [
                    ('Aso Ebi & Corset Gowns', 'aso-ebi-corset-gowns', 'Sculpted corsets, French lace, and bridal guest elegance.'),
                    ('Boubou & Silk Kaftans', 'boubou-silk-kaftans', 'Rich silk and velvet flowing boubous.'),
                    ('Iro & Buba', 'iro-and-buba', 'Modernized classic Yoruba Iro and Buba ensembles.'),
                ]
            },
            {
                'name': 'Traditional & Bridal',
                'slug': 'traditional-bridal',
                'description': 'Handcrafted heritage bridal wear, Aso Oke, and ceremonial attire.',
                'subcategories': [
                    ('Handwoven Aso Oke', 'handwoven-aso-oke', 'Authentic metallic and textured Aso Oke fabrics.'),
                    ('Coral Beads & Caps', 'coral-beads-caps', 'Traditional accessories, beaded crowns, and embroidered filan.'),
                ]
            }
        ]

        cat_map = {}
        order_idx = 1
        for cat_info in categories_data:
            parent_cat, _ = Category.objects.get_or_create(
                slug=cat_info['slug'],
                defaults={
                    'name': cat_info['name'],
                    'description': cat_info['description'],
                    'display_order': order_idx,
                    'is_active': True,
                }
            )
            cat_map[cat_info['slug']] = parent_cat
            order_idx += 1

            for sub_name, sub_slug, sub_desc in cat_info['subcategories']:
                sub_cat, _ = Category.objects.get_or_create(
                    slug=sub_slug,
                    defaults={
                        'name': sub_name,
                        'slug': sub_slug,
                        'description': sub_desc,
                        'parent': parent_cat,
                        'display_order': order_idx,
                        'is_active': True,
                    }
                )
                cat_map[sub_slug] = sub_cat
                order_idx += 1

        self.stdout.write(self.style.SUCCESS("[SUCCESS] Category tree seeded."))

        # 4. Vendors / Designers
        vendors_data = [
            {
                'email': 'seyi@lagosluxe.ng',
                'first_name': 'Seyi',
                'last_name': 'Tinubu',
                'phone': '+2348011223344',
                'store_name': 'Lagos Luxe Native',
                'slug': 'lagos-luxe-native',
                'description': 'Master tailoring blending heritage Yoruba craftsmanship with contemporary high-fashion silhouettes.',
                'city': 'Lagos',
                'state': 'Lagos',
                'instagram': '@lagosluxenative',
                'logo': 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&q=80',
                'banner': 'https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=1200&q=80',
                'kyc_tier': KYCTier.TIER_2_VERIFIED,
                'bank': ('Guaranty Trust Bank', '0123456789', 'Seyi Tinubu', '058')
            },
            {
                'email': 'veekee@veekeejames.ng',
                'first_name': 'Victoria',
                'last_name': 'James',
                'phone': '+2348022334455',
                'store_name': 'VeeKee James Bespoke',
                'slug': 'veekee-james-bespoke',
                'description': 'Exquisite African couture, corset gowns, luxury bridal Aso Ebi, and dramatic red-carpet elegance.',
                'city': 'Lagos',
                'state': 'Lagos',
                'instagram': '@veekeejames_official',
                'logo': 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&q=80',
                'banner': 'https://images.unsplash.com/photo-1496217590455-aa63a8350eea?w=1200&q=80',
                'kyc_tier': KYCTier.TIER_3_ENTERPRISE,
                'bank': ('Zenith Bank', '1002233445', 'Victoria James', '057')
            },
            {
                'email': 'mai@atafo.ng',
                'first_name': 'Mai',
                'last_name': 'Atafo',
                'phone': '+2348033445566',
                'store_name': 'Atafo Official',
                'slug': 'atafo-official',
                'description': 'The quintessential destination for precision-tailored bespoke Senator suits, tuxedos, and modern traditional menswear.',
                'city': 'Lagos',
                'state': 'Lagos',
                'instagram': '@atafo.official',
                'logo': 'https://images.unsplash.com/photo-1560250097-0b93528c311a?w=400&q=80',
                'banner': 'https://images.unsplash.com/photo-1598808503746-f34c53b9323e?w=1200&q=80',
                'kyc_tier': KYCTier.TIER_3_ENTERPRISE,
                'bank': ('Access Bank', '0011223344', 'Mai Atafo Bespoke', '044')
            }
        ]

        vendor_map = {}
        for v in vendors_data:
            v_user, _ = User.objects.get_or_create(
                email=v['email'],
                defaults={
                    'first_name': v['first_name'],
                    'last_name': v['last_name'],
                    'phone_number': v['phone'],
                }
            )
            v_user.set_password('Password123!')
            v_user.save()

            vendor_profile, _ = VendorProfile.objects.get_or_create(
                slug=v['slug'],
                defaults={
                    'user': v_user,
                    'store_name': v['store_name'],
                    'description': v['description'],
                    'city': v['city'],
                    'state': v['state'],
                    'instagram_handle': v['instagram'],
                    'logo_url': v['logo'],
                    'banner_url': v['banner'],
                    'status': VendorStatus.APPROVED,
                    'kyc_tier': v['kyc_tier'],
                    'is_verified': True,
                }
            )
            # Update URLs and branding
            vendor_profile.logo_url = v['logo']
            vendor_profile.banner_url = v['banner']
            vendor_profile.store_name = v['store_name']
            vendor_profile.description = v['description']
            vendor_profile.save()

            # Ensure balance row exists
            get_or_create_vendor_balance(vendor_profile)

            # Bank Account
            bank_name, acc_num, acc_name, bank_code = v['bank']
            BankAccount.objects.get_or_create(
                vendor=vendor_profile,
                defaults={
                    'bank_name': bank_name,
                    'account_number': acc_num,
                    'account_name': acc_name,
                    'bank_code': bank_code,
                }
            )
            vendor_map[v['slug']] = vendor_profile

        self.stdout.write(self.style.SUCCESS("[SUCCESS] Top Nigerian Designer vendors seeded."))

        # 5. Products & Variants Catalog
        products_data = [
            {
                'vendor_slug': 'lagos-luxe-native',
                'category_slug': 'agbada',
                'title': 'Royal Silk Agbada (4-Piece Set)',
                'slug': 'royal-silk-agbada-4-piece-set',
                'price_kobo': 12500000,  # ₦125,000
                'prep_days': 5,
                'description': 'Handcrafted 4-piece ceremonial Agbada ensemble crafted from pure raw silk with gold bullion chest embroidery. Includes embroidered outer Agbada robe, inner buba, tailored sokoto trousers, and matching fila cap.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1584297091622-af8e5fd63363?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1531384441138-2736e62e0919?w=800&q=80', False),
                ],
                'variants': [
                    ('M', 'Burgundy & Gold', 6),
                    ('L', 'Burgundy & Gold', 8),
                    ('XL', 'Burgundy & Gold', 5),
                    ('XXL', 'Royal Navy', 4),
                ]
            },
            {
                'vendor_slug': 'atafo-official',
                'category_slug': 'senator-suits',
                'title': 'Imperial Emerald Senator Suit',
                'slug': 'imperial-emerald-senator-suit',
                'price_kobo': 6500000,  # ₦65,000
                'prep_days': 4,
                'description': 'Sleek, sharply cut Senator suit tailored with premium Italian wool-cashmere blend in deep emerald green. Features minimalist geometric front placket embroidery with concealed mother-of-pearl buttons.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1566492031773-4f4e44671857?w=800&q=80', False),
                ],
                'variants': [
                    ('S', 'Emerald Green', 5),
                    ('M', 'Emerald Green', 10),
                    ('L', 'Emerald Green', 12),
                    ('XL', 'Midnight Black', 7),
                ]
            },
            {
                'vendor_slug': 'veekee-james-bespoke',
                'category_slug': 'aso-ebi-corset-gowns',
                'title': 'Crystal-Embellished Aso Ebi Corset Gown',
                'slug': 'crystal-embellished-aso-ebi-corset-gown',
                'price_kobo': 18000000,  # ₦180,000
                'prep_days': 7,
                'description': 'Signature sculpted corset gown with hand-beaded crystal mesh, French lace overlay, and structured mermaid train. Engineered to flatter with built-in internal boning.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1589156280159-27698a70f29e?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&q=80', False),
                ],
                'variants': [
                    ('S', 'Rose Gold & Champagne', 4),
                    ('M', 'Rose Gold & Champagne', 6),
                    ('L', 'Royal Blue', 3),
                ]
            },
            {
                'vendor_slug': 'veekee-james-bespoke',
                'category_slug': 'boubou-silk-kaftans',
                'title': 'Luxury Velvet Boubou with Gold Beading',
                'slug': 'luxury-velvet-boubou-with-gold-beading',
                'price_kobo': 8500000,  # ₦85,000
                'prep_days': 3,
                'description': 'Flowing regal silhouette crafted from plush devoré velvet. Adorned with intricate neckline beadwork and flared kimono sleeves. Comes with a matching silk headwrap.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1607746882042-944635dfe10e?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=800&q=80', False),
                ],
                'variants': [
                    ('Free Size', 'Sapphire Blue', 15),
                    ('Free Size', 'Wine Burgundy', 12),
                ]
            },
            {
                'vendor_slug': 'lagos-luxe-native',
                'category_slug': 'handwoven-aso-oke',
                'title': 'Handwoven Royal Aso Oke Bridal Ensemble',
                'slug': 'handwoven-royal-aso-oke-bridal-ensemble',
                'price_kobo': 22000000,  # ₦220,000
                'prep_days': 10,
                'description': 'Authentic Iseyin handwoven metallic Aso Oke comprising Ipele (shoulder sash), Gele (pre-pleated auto-gele or traditional wrap), and matching embroidered Buba and Iro.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1550928431-ee0ec6db30d3?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1496217590455-aa63a8350eea?w=800&q=80', False),
                ],
                'variants': [
                    ('Standard', 'Magenta & Silver', 4),
                    ('Standard', 'Teal & Gold', 5),
                ]
            },
            {
                'vendor_slug': 'atafo-official',
                'category_slug': 'two-piece-sets',
                'title': 'Contemporary Urban Two-Piece Native',
                'slug': 'contemporary-urban-two-piece-native',
                'price_kobo': 4500000,  # ₦45,000
                'prep_days': 3,
                'description': 'Modern casual luxury two-piece native set in breathable cotton-linen. Features an asymmetrical hem tunic with matching slim-fit tapered drawstring pants.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1607346256330-dee7af15f7c5?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1559127452-56b800eb2f23?w=800&q=80', False),
                ],
                'variants': [
                    ('M', 'Sand Beige', 8),
                    ('L', 'Sand Beige', 10),
                    ('XL', 'Olive Green', 6),
                ]
            },
            {
                'vendor_slug': 'veekee-james-bespoke',
                'category_slug': 'iro-and-buba',
                'title': 'Hand-Dyed Silk Adire Buba & Iro Set',
                'slug': 'hand-dyed-silk-adire-buba-iro-set',
                'price_kobo': 7500000,  # ₦75,000
                'prep_days': 4,
                'description': 'Contemporary Yoruba Iro and Buba set rendered in artisanal hand-dyed indigo Adire silk with delicate gold trim.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1616683693504-3ea7e9ad6fec?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1579783902614-a3fb3927b675?w=800&q=80', False),
                ],
                'variants': [
                    ('S', 'Indigo Blue', 4),
                    ('M', 'Indigo Blue', 8),
                    ('L', 'Indigo Blue', 5),
                ]
            },
            {
                'vendor_slug': 'lagos-luxe-native',
                'category_slug': 'coral-beads-caps',
                'title': 'Royal Beaded Coral Crown & Velvet Fila',
                'slug': 'royal-beaded-coral-crown-velvet-fila',
                'price_kobo': 3500000,  # ₦35,000
                'prep_days': 2,
                'description': 'Traditional royal accessories comprising hand-strung original Benin red coral beads and an intricately embroidered velvet Fila cap.',
                'media': [
                    ('IMAGE', 'https://images.unsplash.com/photo-1622519407650-3df9883f76a5?w=800&q=80', True),
                    ('IMAGE', 'https://images.unsplash.com/photo-1584297091622-af8e5fd63363?w=800&q=80', False),
                ],
                'variants': [
                    ('Standard', 'Royal Red & Gold', 10),
                ]
            }
        ]

        created_products = []
        for p in products_data:
            vendor = vendor_map[p['vendor_slug']]
            category = cat_map[p['category_slug']]

            prod, _ = Product.objects.get_or_create(
                slug=p['slug'],
                defaults={
                    'vendor': vendor,
                    'category': category,
                    'title': p['title'],
                    'base_price_kobo': p['price_kobo'],
                    'preparation_time_days': p['prep_days'],
                    'description': p['description'],
                    'status': ProductStatus.PUBLISHED,
                    'approval_status': ApprovalStatus.APPROVED,
                    'is_active': True,
                }
            )
            # Update product details
            prod.title = p['title']
            prod.base_price_kobo = p['price_kobo']
            prod.description = p['description']
            prod.category = category
            prod.vendor = vendor
            prod.save()

            created_products.append(prod)

            # Refresh Media with authentic imagery
            ProductMedia.objects.filter(product=prod).delete()
            for m_type, m_url, is_prim in p['media']:
                ProductMedia.objects.create(
                    product=prod,
                    url=m_url,
                    media_type=m_type,
                    is_primary=is_prim,
                )

            # Variants
            for v_size, v_color, v_stock in p['variants']:
                sku = f"ASO-{vendor.slug[:4].upper()}-{prod.slug[:4].upper()}-{slugify(v_size).upper()}-{slugify(v_color).upper()}"
                ProductVariant.objects.get_or_create(
                    product=prod,
                    size=v_size,
                    color=v_color,
                    defaults={
                        'sku': sku,
                        'stock_quantity': v_stock,
                        'is_active': True,
                    }
                )

        self.stdout.write(self.style.SUCCESS(f"[SUCCESS] {len(created_products)} high-fashion products seeded with variants and gallery images."))

        # 6. Seed Sample Completed Orders & Verified Reviews
        for idx, prod in enumerate(created_products[:4]):
            first_variant = prod.variants.first()
            if not first_variant:
                continue

            order = Order.objects.create(
                order_number=f"ASO-DEMO-ORD-00{idx+1}",
                customer=customer_user,
                vendor=prod.vendor,
                subtotal_kobo=prod.base_price_kobo,
                delivery_fee_kobo=200000,
                total_amount_kobo=prod.base_price_kobo + 200000,
                order_status=OrderStatus.COMPLETED,
                payment_expires_at=customer_user.date_joined,
                shipping_address_snapshot={
                    'full_name': 'Zainab Aliyu',
                    'phone_number': '+2348099887700',
                    'street_address': '12 Admiralty Way, Lekki Phase 1',
                    'city': 'Lekki',
                    'state': 'Lagos',
                }
            )
            order_item = OrderItem.objects.create(
                order=order,
                variant=first_variant,
                product_title_snapshot=prod.title,
                variant_size_snapshot=first_variant.size,
                variant_color_snapshot=first_variant.color,
                sku_snapshot=first_variant.sku,
                quantity=1,
                unit_price_kobo=prod.base_price_kobo,
                total_price_kobo=prod.base_price_kobo
            )

            comments = [
                "Exceptional quality tailoring! The fabric weight and stitching details exceeded my expectations.",
                "Absolutely gorgeous fit. Received endless compliments at the wedding in Victoria Island.",
                "Top-tier bespoke craftsmanship. Delivered right on time for my event.",
                "Luxurious and regal! Highly recommend this designer to anyone looking for authentic quality."
            ]

            Review.objects.create(
                order_item=order_item,
                product=prod,
                vendor=prod.vendor,
                customer=customer_user,
                rating=5,
                comment=comments[idx % len(comments)],
                is_verified_purchase=True
            )

            # Update rating metrics
            prod.average_rating = Decimal('5.00')
            prod.review_count = 1
            prod.save(update_fields=['average_rating', 'review_count'])

            prod.vendor.average_rating = Decimal('5.00')
            prod.vendor.review_count = prod.vendor.reviews.count()
            prod.vendor.save(update_fields=['average_rating', 'review_count'])

        self.stdout.write(self.style.SUCCESS("[SUCCESS] Verified buyer reviews and order snapshots seeded."))
        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] MARKETPLACE SEEDING COMPLETE!"))
