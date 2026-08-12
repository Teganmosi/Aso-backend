from django.core.management.base import BaseCommand
from apps.products.models import Category


class Command(BaseCommand):
    help = 'Seeds initial Nigerian Fashion Marketplace category tree hierarchy'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding category hierarchy..."))

        categories_data = [
            {
                'name': 'Men',
                'description': 'Men\'s fashion, traditional attire, senators, and contemporary wear.',
                'display_order': 1,
                'children': [
                    {'name': 'Agbada', 'description': 'Grand Agbada sets and traditional ceremonial attire.', 'display_order': 1},
                    {'name': 'Men\'s Two-Piece', 'description': 'Senator sets, two-piece co-ords, and tailored tunics.', 'display_order': 2},
                    {'name': 'Kaftan', 'description': 'Classic Nigerian kaftans and stylish casual traditional wear.', 'display_order': 3},
                    {'name': 'Men\'s Streetwear', 'description': 'Urban Nigerian streetwear, graphic tees, and jackets.', 'display_order': 4},
                ]
            },
            {
                'name': 'Women',
                'description': 'Women\'s fashion, traditional wear, gowns, and bespoke tailoring.',
                'display_order': 2,
                'children': [
                    {'name': 'Women\'s Traditional', 'description': 'Iro & Buba, Aso Ebi styles, and Ankara masterpieces.', 'display_order': 1},
                    {'name': 'Women\'s Two-Piece', 'description': 'Co-ord sets, female senator suits, and matching ensembles.', 'display_order': 2},
                    {'name': 'Dresses', 'description': 'African print dresses, evening gowns, and ready-to-wear.', 'display_order': 3},
                    {'name': 'Women\'s Streetwear', 'description': 'Modern Nigerian streetwear and athleisure for women.', 'display_order': 4},
                ]
            },
            {
                'name': 'Unisex',
                'description': 'Unisex fashion items, hoodies, accessories, and versatile wear.',
                'display_order': 3,
                'children': []
            },
            {
                'name': 'Accessories',
                'description': 'Traditional caps (Fila), hand-woven sashes, bags, and fashion accessories.',
                'display_order': 4,
                'children': []
            }
        ]

        created_count = 0
        for cat_info in categories_data:
            children = cat_info.pop('children', [])
            parent_cat, created = Category.objects.get_or_create(
                name=cat_info['name'],
                defaults=cat_info
            )
            if created:
                created_count += 1

            for child_info in children:
                child_cat, child_created = Category.objects.get_or_create(
                    name=child_info['name'],
                    parent=parent_cat,
                    defaults=child_info
                )
                if child_created:
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded category tree ({created_count} new categories created)."))
